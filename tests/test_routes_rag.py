"""Tests for RAG query route handler.

Covers: missing KB config, successful queries with citations, Bedrock
failures, empty citations, empty query rejection, snippet truncation,
and multiple citation sources.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestRagQuery:
    """Tests for POST /rag-query."""

    @pytest.mark.asyncio
    async def test_missing_kb_500(self, client, monkeypatch):
        """When KNOWLEDGE_BASE_ID is unset, the endpoint returns a clear 500."""
        monkeypatch.delenv("KNOWLEDGE_BASE_ID", raising=False)
        resp = await client.post("/rag-query", json={"query": "test question"})
        assert resp.status_code == 500
        assert "not configured" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_empty_query_422(self, client):
        """Empty or whitespace-only queries are rejected by Pydantic validation."""
        resp = await client.post("/rag-query", json={"query": ""})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_query_field_422(self, client):
        """Request body without 'query' field is rejected."""
        resp = await client.post("/rag-query", json={})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_successful_query(self, client, monkeypatch):
        """Happy path: Bedrock returns an answer with one citation source."""
        monkeypatch.setenv("KNOWLEDGE_BASE_ID", "kb-test-123")

        mock_bedrock = MagicMock()
        mock_bedrock.retrieve_and_generate.return_value = {
            "output": {"text": "Art forgery involves..."},
            "citations": [
                {
                    "retrievedReferences": [
                        {
                            "location": {"s3Location": {"uri": "s3://kb/doc1.txt"}},
                            "content": {"text": "Short snippet about art forgery techniques..."},
                        }
                    ]
                }
            ],
        }

        with patch("src.apps.backend.routes.rag_router.boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_bedrock

            resp = await client.post("/rag-query", json={"query": "What is art forgery?"})
            assert resp.status_code == 200
            data = resp.json()
            assert "forgery" in data["answer"].lower()
            assert len(data["sources"]) == 1
            assert data["sources"][0]["s3_uri"] == "s3://kb/doc1.txt"
            assert len(data["sources"][0]["snippet"]) > 0

    @pytest.mark.asyncio
    async def test_snippet_truncated_to_200_chars(self, client, monkeypatch):
        """Source snippets longer than 200 characters are truncated to prevent
        bloated responses (the raw KB chunks can be thousands of chars)."""
        monkeypatch.setenv("KNOWLEDGE_BASE_ID", "kb-test-123")

        long_text = "A" * 500  # 500 chars, should be truncated to 200

        mock_bedrock = MagicMock()
        mock_bedrock.retrieve_and_generate.return_value = {
            "output": {"text": "Answer text."},
            "citations": [
                {
                    "retrievedReferences": [
                        {
                            "location": {"s3Location": {"uri": "s3://kb/long.txt"}},
                            "content": {"text": long_text},
                        }
                    ]
                }
            ],
        }

        with patch("src.apps.backend.routes.rag_router.boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_bedrock
            resp = await client.post("/rag-query", json={"query": "test"})
            assert resp.status_code == 200
            assert len(resp.json()["sources"][0]["snippet"]) == 200

    @pytest.mark.asyncio
    async def test_multiple_citations(self, client, monkeypatch):
        """Multiple citation sources across multiple citation groups are flattened."""
        monkeypatch.setenv("KNOWLEDGE_BASE_ID", "kb-test-123")

        mock_bedrock = MagicMock()
        mock_bedrock.retrieve_and_generate.return_value = {
            "output": {"text": "Answer."},
            "citations": [
                {
                    "retrievedReferences": [
                        {"location": {"s3Location": {"uri": "s3://kb/a.txt"}}, "content": {"text": "A"}},
                        {"location": {"s3Location": {"uri": "s3://kb/b.txt"}}, "content": {"text": "B"}},
                    ]
                },
                {
                    "retrievedReferences": [
                        {"location": {"s3Location": {"uri": "s3://kb/c.txt"}}, "content": {"text": "C"}},
                    ]
                },
            ],
        }

        with patch("src.apps.backend.routes.rag_router.boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_bedrock
            resp = await client.post("/rag-query", json={"query": "test"})
            assert resp.status_code == 200
            sources = resp.json()["sources"]
            assert len(sources) == 3
            uris = {s["s3_uri"] for s in sources}
            assert uris == {"s3://kb/a.txt", "s3://kb/b.txt", "s3://kb/c.txt"}

    @pytest.mark.asyncio
    async def test_bedrock_failure_500(self, client, monkeypatch):
        """When Bedrock throws, the user gets a friendly error, not a stack trace."""
        monkeypatch.setenv("KNOWLEDGE_BASE_ID", "kb-test-123")

        with patch("src.apps.backend.routes.rag_router.boto3") as mock_boto3:
            mock_client = MagicMock()
            mock_client.retrieve_and_generate.side_effect = Exception("Bedrock down")
            mock_boto3.client.return_value = mock_client

            resp = await client.post("/rag-query", json={"query": "test"})
            assert resp.status_code == 500
            assert "try again" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_empty_citations(self, client, monkeypatch):
        """Bedrock may return an answer with no citations — sources should be []."""
        monkeypatch.setenv("KNOWLEDGE_BASE_ID", "kb-test-123")

        mock_bedrock = MagicMock()
        mock_bedrock.retrieve_and_generate.return_value = {
            "output": {"text": "No sources found."},
            "citations": [],
        }

        with patch("src.apps.backend.routes.rag_router.boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_bedrock

            resp = await client.post("/rag-query", json={"query": "obscure question"})
            assert resp.status_code == 200
            assert resp.json()["sources"] == []
            assert resp.json()["answer"] == "No sources found."
