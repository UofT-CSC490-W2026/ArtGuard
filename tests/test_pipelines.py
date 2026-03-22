"""Tests for MET and Wikidata data pipelines."""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from src.apps.data_pipeline.met_pipeline import build_rag_document as met_build_rag
from src.apps.data_pipeline.wikidata_pipeline import (
    build_query,
    build_rag_document as wiki_build_rag,
    export_jsonl,
    query_wikidata,
)


class TestMetBuildRagDocument:
    """Tests for met_pipeline.build_rag_document."""

    def test_includes_title(self):
        row = {"Title": "Starry Night", "Artist Display Name": "Van Gogh"}
        doc = met_build_rag(row)
        assert "Starry Night" in doc
        assert "Van Gogh" in doc

    def test_handles_missing_fields(self):
        doc = met_build_rag({})
        assert "Unknown" in doc

    def test_includes_all_sections(self):
        row = {
            "Title": "Test",
            "Object Name": "Painting",
            "Classification": "Art",
            "Artist Display Name": "Alice",
            "Artist Nationality": "French",
            "Culture": "European",
            "Medium": "Oil on canvas",
        }
        doc = met_build_rag(row)
        assert "Artwork Title:" in doc
        assert "Object Type:" in doc
        assert "Artist:" in doc
        assert "Medium:" in doc


class TestWikidataBuildQuery:
    """Tests for wikidata_pipeline.build_query."""

    def test_contains_qid(self):
        query = build_query("Q5582")
        assert "wd:Q5582" in query

    def test_valid_sparql_structure(self):
        query = build_query("Q12345")
        assert "SELECT" in query
        assert "WHERE" in query
        assert "LIMIT" in query


class TestWikidataBuildRagDocument:
    """Tests for wikidata_pipeline.build_rag_document."""

    def test_basic_document(self):
        result = {
            "results": {
                "bindings": [
                    {
                        "artistLabel": {"value": "Van Gogh"},
                        "description": {"value": "Dutch painter"},
                        "birth": {"value": "1853-03-30"},
                        "death": {"value": "1890-07-29"},
                        "citizenshipLabel": {"value": "Netherlands"},
                    }
                ]
            }
        }
        doc = wiki_build_rag(result)
        assert "Van Gogh" in doc
        assert "Dutch painter" in doc

    def test_empty_bindings_returns_none(self):
        result = {"results": {"bindings": []}}
        assert wiki_build_rag(result) is None

    def test_multi_value_fields_collected(self):
        result = {
            "results": {
                "bindings": [
                    {
                        "artistLabel": {"value": "Artist"},
                        "movementLabel": {"value": "Impressionism"},
                        "genreLabel": {"value": "Portrait"},
                    },
                    {
                        "artistLabel": {"value": "Artist"},
                        "movementLabel": {"value": "Post-Impressionism"},
                        "genreLabel": {"value": "Landscape"},
                    },
                ]
            }
        }
        doc = wiki_build_rag(result)
        assert "Impressionism" in doc
        assert "Post-Impressionism" in doc


class TestExportJsonl:
    """Tests for wikidata_pipeline.export_jsonl."""

    def test_writes_jsonl(self, tmp_path):
        records = [{"id": "1", "text": "hello"}, {"id": "2", "text": "world"}]
        output_path = str(tmp_path / "output.jsonl")
        export_jsonl(records, output_path)

        with open(output_path, "r") as f:
            lines = f.readlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["id"] == "1"

    def test_creates_parent_dirs(self, tmp_path):
        output_path = str(tmp_path / "deep" / "nested" / "output.jsonl")
        export_jsonl([{"id": "1", "text": "test"}], output_path)
        assert os.path.exists(output_path)


class TestQueryWikidata:
    """Tests for wikidata_pipeline.query_wikidata."""

    @patch("src.apps.data_pipeline.wikidata_pipeline.requests.get")
    def test_successful_query(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "application/sparql-results+json"}
        mock_resp.json.return_value = {"results": {"bindings": []}}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = query_wikidata("SELECT ?x WHERE { ?x ?y ?z }")
        assert result is not None

    @patch("src.apps.data_pipeline.wikidata_pipeline.requests.get")
    def test_retries_on_failure(self, mock_get):
        mock_get.side_effect = Exception("Connection error")
        result = query_wikidata("SELECT ...", retries=2)
        assert result is None
        assert mock_get.call_count == 2

    @patch("src.apps.data_pipeline.wikidata_pipeline.requests.get")
    def test_unexpected_content_type(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.text = "<html>error</html>"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = query_wikidata("SELECT ...", retries=1)
        assert result is None
