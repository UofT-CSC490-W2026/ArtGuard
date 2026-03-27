"""Unit tests for src.apps.rag_pipeline (KB retrieve, format_input, generate_response).

AWS and network calls are mocked.
"""

from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch

import pytest

from src.apps.rag_pipeline.knowledge_base import RetrievedChunk


# ---------------------------------------------------------------------------
# knowledge_base
# ---------------------------------------------------------------------------


class TestKnowledgeBaseHelpers:
    def test_require_knowledge_base_id_missing(self, monkeypatch):
        monkeypatch.delenv("KNOWLEDGE_BASE_ID", raising=False)
        from src.apps.rag_pipeline import knowledge_base

        with pytest.raises(EnvironmentError, match="KNOWLEDGE_BASE_ID"):
            knowledge_base._require_knowledge_base_id()

    def test_clip_no_limit(self):
        from src.apps.rag_pipeline.knowledge_base import _clip

        assert _clip("hello world", 0) == "hello world"

    def test_clip_truncates(self):
        from src.apps.rag_pipeline.knowledge_base import _clip

        assert _clip("abcdefgh", 4) == "abcd..."


class TestRetrieveTopChunks:
    def test_retrieve_dedupes_and_respects_top_k(self, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_BASE_ID", "kb-test")
        from src.apps.rag_pipeline import knowledge_base

        client = MagicMock()
        client.retrieve.return_value = {
            "retrievalResults": [
                {
                    "location": {"s3Location": {"uri": "s3://b/doc.txt"}},
                    "content": {"text": "alpha " * 50},
                },
                {
                    "location": {"s3Location": {"uri": "s3://b/doc.txt"}},
                    "content": {"text": "alpha " * 50},
                },
                {
                    "location": {"s3Location": {"uri": "s3://b/other.txt"}},
                    "content": {"text": "beta"},
                },
            ]
        }
        with patch.object(knowledge_base.boto3, "client", return_value=client):
            chunks = knowledge_base.retrieve_top_chunks(
                "query",
                top_k=2,
                candidate_k=5,
                snippet_chars=10,
                search_type="HYBRID",
            )
        assert len(chunks) == 2
        assert chunks[0].rank == 1
        cfg = client.retrieve.call_args[1]["retrievalConfiguration"]["vectorSearchConfiguration"]
        assert cfg["overrideSearchType"] == "HYBRID"
        assert cfg["numberOfResults"] == 5

    def test_prefer_s3_uri_substring_reorders(self, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_BASE_ID", "kb-test")
        from src.apps.rag_pipeline import knowledge_base

        client = MagicMock()
        client.retrieve.return_value = {
            "retrievalResults": [
                {
                    "location": {"s3Location": {"uri": "s3://b/a.txt"}},
                    "content": {"text": "first"},
                },
                {
                    "location": {"s3Location": {"uri": "s3://b/pick_me.txt"}},
                    "content": {"text": "second"},
                },
            ]
        }
        with patch.object(knowledge_base.boto3, "client", return_value=client):
            chunks = knowledge_base.retrieve_top_chunks(
                "q",
                top_k=2,
                candidate_k=2,
                prefer_s3_uri_substring="pick_me",
            )
        assert "pick_me" in chunks[0].s3_uri

    def test_prefer_s3_empty_needle_skipped(self, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_BASE_ID", "kb-test")
        from src.apps.rag_pipeline import knowledge_base

        client = MagicMock()
        client.retrieve.return_value = {
            "retrievalResults": [
                {
                    "location": {"s3Location": {"uri": "s3://b/z.txt"}},
                    "content": {"text": "z"},
                },
            ]
        }
        with patch.object(knowledge_base.boto3, "client", return_value=client):
            chunks = knowledge_base.retrieve_top_chunks(
                "q",
                top_k=1,
                candidate_k=1,
                prefer_s3_uri_substring="   ",
            )
        assert chunks[0].s3_uri.endswith("z.txt")

    def test_missing_location_and_content_keys(self, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_BASE_ID", "kb-test")
        from src.apps.rag_pipeline import knowledge_base

        client = MagicMock()
        client.retrieve.return_value = {"retrievalResults": [{}]}
        with patch.object(knowledge_base.boto3, "client", return_value=client):
            chunks = knowledge_base.retrieve_top_chunks("q", top_k=3, candidate_k=1)
        assert len(chunks) == 1
        assert chunks[0].s3_uri == ""
        assert chunks[0].snippet == ""


class TestKnowledgeBaseMain:
    def test_main_no_chunks(self, capsys, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_BASE_ID", "kb")
        from src.apps.rag_pipeline import knowledge_base

        with patch.object(knowledge_base, "retrieve_top_chunks", return_value=[]):
            knowledge_base.main(["hello"])
        assert "No retrieved chunks" in capsys.readouterr().out

    def test_main_prints_chunks(self, capsys, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_BASE_ID", "kb")
        from src.apps.rag_pipeline import knowledge_base

        chunk = RetrievedChunk(1, "s3://bucket/key.txt", "body text")
        with patch.object(knowledge_base, "retrieve_top_chunks", return_value=[chunk]):
            knowledge_base.main(["my query", "--snippet-chars", "0"])
        out = capsys.readouterr().out
        assert "key.txt" in out
        assert "body text" in out

    def test_main_writes_json(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_BASE_ID", "kb")
        from src.apps.rag_pipeline import knowledge_base

        chunk = RetrievedChunk(1, "s3://b/f.txt", "hi")
        out_file = tmp_path / "nested" / "chunks.json"
        with patch.object(knowledge_base, "retrieve_top_chunks", return_value=[chunk]):
            knowledge_base.main(["q", "--output-json", str(out_file)])
        assert out_file.is_file()
        data = json.loads(out_file.read_text(encoding="utf-8"))
        assert data[0]["snippet"] == "hi"


# ---------------------------------------------------------------------------
# format_input
# ---------------------------------------------------------------------------


class TestFormatInputBasics:
    def test_prediction_to_label(self):
        from src.apps.rag_pipeline.format_input import prediction_to_label

        assert prediction_to_label(1) == "authentic"
        assert prediction_to_label(0) == "inauthentic"

    def test_confidence_clamped(self):
        from src.apps.rag_pipeline.format_input import confidence_from_mean_prob

        assert confidence_from_mean_prob(0.5) == 0.0
        assert confidence_from_mean_prob(0.0) == 100.0
        assert confidence_from_mean_prob(2.0) == 100.0

    def test_to_float_bad_values(self):
        from src.apps.rag_pipeline.format_input import _to_float

        assert _to_float("nope", 3.5) == 3.5
        assert _to_float(None, 1.0) == 1.0

    def test_bbox_from_patch(self):
        from src.apps.rag_pipeline.format_input import _bbox_from_patch

        assert "x=1" in _bbox_from_patch({"patch_x": 1, "patch_y": 2, "patch_width": 3, "patch_height": 4})

    def test_region_hint_degenerate_axes(self):
        from src.apps.rag_pipeline.format_input import _region_hint_from_patch_coords

        assert _region_hint_from_patch_coords(
            patch_x=10, patch_y=10, x_min=10, x_max=10, y_min=10, y_max=10
        ) == "center"

    def test_region_hint_positions(self):
        from src.apps.rag_pipeline.format_input import _region_hint_from_patch_coords

        assert "left" in _region_hint_from_patch_coords(
            patch_x=0, patch_y=50, x_min=0, x_max=100, y_min=0, y_max=100
        )
        assert "right" in _region_hint_from_patch_coords(
            patch_x=99, patch_y=50, x_min=0, x_max=100, y_min=0, y_max=100
        )
        assert _region_hint_from_patch_coords(
            patch_x=50, patch_y=10, x_min=0, x_max=100, y_min=0, y_max=100
        ).startswith("top")
        assert _region_hint_from_patch_coords(
            patch_x=50, patch_y=95, x_min=0, x_max=100, y_min=0, y_max=100
        ).startswith("bottom")


class TestTopKPatchEvidence:
    def test_fallback_all_rows_when_none_on_predicted_side(self):
        from src.apps.rag_pipeline.format_input import top_k_patch_evidence

        patches = [{"patch_id": "a", "patch_path": "s3://b/a.jpg", "patch_type": "t"}]
        probs = [0.2]
        ev = top_k_patch_evidence(patches, probs, prediction=1, top_k=2)
        assert len(ev) == 1

    def test_same_side_selection(self):
        from src.apps.rag_pipeline.format_input import top_k_patch_evidence

        patches = [
            {"patch_id": "1", "patch_path": "p1", "patch_x": 0, "patch_y": 0},
            {"patch_id": "2", "patch_path": "p2", "patch_x": 100, "patch_y": 100},
        ]
        probs = [0.9, 0.51]
        ev = top_k_patch_evidence(
            patches, probs, prediction=1, top_k=2, x_min=0, x_max=200, y_min=0, y_max=200
        )
        assert len(ev) == 2


class TestNormalizeKbChunks:
    def test_string_chunk(self):
        from src.apps.rag_pipeline.format_input import normalize_kb_chunks

        assert normalize_kb_chunks(["  a  b  "]) == ["a b"]

    def test_dict_variants(self):
        from src.apps.rag_pipeline.format_input import normalize_kb_chunks

        rows = [
            {"s3_uri": "s3://b/part.txt", "snippet": "snip"},
            {"s3Uri": "s3://b/x.txt", "text": "t2"},
            {"uri": "s3://b/y.txt", "text": "t3"},
            {"uri": "relative/path.txt", "text": "non-s3 uri key"},
        ]
        out = normalize_kb_chunks(rows, max_chars=100)
        assert any("part.txt" in x for x in out)
        assert any("snippet=snip" in x for x in out)

    def test_object_like_chunk(self):
        from src.apps.rag_pipeline.format_input import normalize_kb_chunks

        class C:
            s3_uri = "s3://b/obj.txt"
            snippet = "from obj"
            text = ""

        assert any("obj.txt" in x and "from obj" in x for x in normalize_kb_chunks([C()]))

    def test_skips_empty_snippet(self):
        from src.apps.rag_pipeline.format_input import normalize_kb_chunks

        assert normalize_kb_chunks(["   ", {"snippet": "   "}]) == []

    def test_truncates_long_snippet(self):
        from src.apps.rag_pipeline.format_input import normalize_kb_chunks

        out = normalize_kb_chunks(["x" * 50], max_chars=5)
        assert out[0].endswith("...")


class TestBuildGenerationInput:
    def test_empty_patches_and_kb(self):
        from src.apps.rag_pipeline.format_input import build_generation_input

        text = build_generation_input(
            source_image="s3://b/in.jpg",
            prediction=0,
            mean_prob=0.3,
            patches_info=[],
            patch_probs=[],
            retrieved_kb_chunks=[],
            overall_image_attached=False,
        )
        assert "Overall image attached: False" in text
        assert "- None" in text

    def test_artist_artwork_lines(self):
        from src.apps.rag_pipeline.format_input import build_generation_input

        text = build_generation_input(
            source_image="s3://b/in.jpg",
            prediction=1,
            mean_prob=0.8,
            patches_info=[{"patch_id": "p", "patch_path": "s3://b/p.jpg", "patch_type": "c"}],
            patch_probs=[0.8],
            retrieved_kb_chunks=[],
            artist_name="Van Gogh",
            artwork_name="Starry Night",
        )
        assert "Van Gogh" in text
        assert "Starry Night" in text


# ---------------------------------------------------------------------------
# generate_response
# ---------------------------------------------------------------------------


class TestGenerateResponseExtractText:
    def test_no_body(self):
        from src.apps.rag_pipeline.generate_response import _extract_text_from_invoke_response

        assert _extract_text_from_invoke_response({}) == ""

    def test_body_bytes_json_content(self):
        from src.apps.rag_pipeline.generate_response import _extract_text_from_invoke_response

        payload = {"content": [{"type": "text", "text": "Hello"}]}
        raw = json.dumps(payload).encode()
        assert _extract_text_from_invoke_response({"body": raw}) == "Hello"

    def test_body_read_stream(self):
        from src.apps.rag_pipeline.generate_response import _extract_text_from_invoke_response

        payload = {"content": [{"type": "text", "text": "Streamed"}]}
        body = MagicMock()
        body.read.return_value = json.dumps(payload).encode()
        assert _extract_text_from_invoke_response({"body": body}) == "Streamed"

    def test_output_text_fallback(self):
        from src.apps.rag_pipeline.generate_response import _extract_text_from_invoke_response

        raw = json.dumps({"outputText": "  alt  "}).encode()
        assert _extract_text_from_invoke_response({"body": raw}) == "alt"

    def test_unknown_payload_empty(self):
        from src.apps.rag_pipeline.generate_response import _extract_text_from_invoke_response

        raw = json.dumps({"content": []}).encode()
        assert _extract_text_from_invoke_response({"body": raw}) == ""


class TestS3UriHelpers:
    def test_s3_uri_to_bucket_key(self):
        from src.apps.rag_pipeline.generate_response import _s3_uri_to_bucket_key

        assert _s3_uri_to_bucket_key("s3://mybucket/path/to/k.jpg") == ("mybucket", "path/to/k.jpg")

    def test_s3_uri_invalid(self):
        from src.apps.rag_pipeline.generate_response import _s3_uri_to_bucket_key

        with pytest.raises(ValueError, match="Not an s3 uri"):
            _s3_uri_to_bucket_key("https://x")
        with pytest.raises(ValueError, match="Invalid s3 uri"):
            _s3_uri_to_bucket_key("s3://onlybucket")

    def test_infer_media_type(self):
        from src.apps.rag_pipeline.generate_response import _infer_media_type_from_uri

        assert _infer_media_type_from_uri("x.PNG") == "image/png"
        assert _infer_media_type_from_uri("a.WEBP") == "image/webp"
        assert _infer_media_type_from_uri("b.jpg") == "image/jpeg"


class TestLoadPatchImages:
    def test_load_patch_image_blocks_empty(self):
        from src.apps.rag_pipeline.generate_response import _load_patch_image_blocks

        assert _load_patch_image_blocks([]) == ([], [])

    @patch("src.apps.rag_pipeline.generate_response.boto3")
    def test_load_patch_image_blocks_success(self, mock_boto3):
        from src.apps.rag_pipeline.generate_response import _load_patch_image_blocks

        s3 = MagicMock()
        mock_boto3.client.return_value = s3
        s3.get_object.return_value = {"Body": io.BytesIO(b"\xff\xd8\xff" + b"x" * 20)}

        blocks, used = _load_patch_image_blocks(["s3://b/p.jpg"], max_images=2)
        assert len(blocks) == 1
        assert used == ["s3://b/p.jpg"]
        assert blocks[0]["type"] == "image"

    @patch("src.apps.rag_pipeline.generate_response.boto3")
    def test_load_patch_image_blocks_skips_errors_and_empty(self, mock_boto3):
        from src.apps.rag_pipeline.generate_response import _load_patch_image_blocks

        s3 = MagicMock()
        mock_boto3.client.return_value = s3
        empty_body = MagicMock()
        empty_body.read.return_value = b""
        s3.get_object.side_effect = [
            Exception("fail"),
            {"Body": empty_body},
        ]

        blocks, used = _load_patch_image_blocks(
            ["s3://b/bad.jpg", "s3://b/empty.jpg"],
            max_images=3,
        )
        assert blocks == []
        assert used == []

    @patch("src.apps.rag_pipeline.generate_response.boto3")
    def test_load_patch_image_blocks_skips_oversized(self, mock_boto3):
        from src.apps.rag_pipeline.generate_response import _load_patch_image_blocks

        s3 = MagicMock()
        mock_boto3.client.return_value = s3
        huge = b"y" * 100
        s3.get_object.return_value = {"Body": io.BytesIO(huge)}

        blocks, used = _load_patch_image_blocks(["s3://b/huge.jpg"], max_bytes=10)
        assert blocks == []

    def test_load_single_invalid_uri(self):
        from src.apps.rag_pipeline.generate_response import _load_single_image_block

        assert _load_single_image_block("") == ([], False)
        assert _load_single_image_block("https://x") == ([], False)

    @patch("src.apps.rag_pipeline.generate_response.boto3")
    def test_load_single_success_and_failure(self, mock_boto3):
        from src.apps.rag_pipeline.generate_response import _load_single_image_block

        s3 = MagicMock()
        mock_boto3.client.return_value = s3
        s3.get_object.return_value = {"Body": io.BytesIO(b"\xff\xd8\xff" + b"z" * 30)}
        blocks, ok = _load_single_image_block("s3://b/o.jpg", max_bytes=1000)
        assert ok is True
        assert blocks[0]["type"] == "image"

        s3.get_object.side_effect = Exception("boom")
        assert _load_single_image_block("s3://b/x.jpg") == ([], False)

        s3.get_object.side_effect = None
        s3.get_object.return_value = {"Body": io.BytesIO(b"x" * 200)}
        assert _load_single_image_block("s3://b/big.jpg", max_bytes=10) == ([], False)


class TestBuildUserPromptAndClaude:
    def test_build_user_prompt(self):
        from src.apps.rag_pipeline.generate_response import _build_user_prompt

        assert "analysis_input" in _build_user_prompt("ctx")
        assert "ctx" in _build_user_prompt("ctx")

    @patch("src.apps.rag_pipeline.generate_response.boto3")
    @patch("src.apps.rag_pipeline.generate_response.bedrock_invoke_model_id")
    @patch("src.apps.rag_pipeline.generate_response._extract_text_from_invoke_response")
    def test_generate_with_claude(self, mock_extract, mock_model_id, mock_boto3):
        from src.apps.rag_pipeline.generate_response import _generate_with_claude

        mock_model_id.return_value = "model-id"
        mock_extract.return_value = "final"
        rt = MagicMock()
        mock_boto3.client.return_value = rt
        rt.invoke_model.return_value = {"body": b"{}"}

        out = _generate_with_claude("prompt text", patch_image_blocks=None, max_tokens=100, temperature=0.1)
        assert out == "final"
        call_kw = rt.invoke_model.call_args[1]
        assert json.loads(call_kw["body"])["max_tokens"] == 100


class TestGenerateExplanation:
    @patch("src.apps.rag_pipeline.generate_response._generate_with_claude")
    @patch("src.apps.rag_pipeline.generate_response._load_single_image_block")
    @patch("src.apps.rag_pipeline.generate_response._load_patch_image_blocks")
    @patch("src.apps.rag_pipeline.generate_response.retrieve_top_chunks")
    def test_happy_path(
        self,
        mock_retrieve,
        mock_load_patches,
        mock_load_single,
        mock_gen,
    ):
        from src.apps.rag_pipeline.generate_response import generate_explanation

        mock_retrieve.return_value = [
            RetrievedChunk(1, "s3://b/kb.txt", "kb snippet"),
        ]
        mock_load_patches.return_value = ([], [])
        mock_load_single.return_value = ([], False)
        mock_gen.return_value = "Explained."

        result = generate_explanation(
            source_image="s3://b/raw.jpg",
            prediction=1,
            mean_prob=0.88,
            patches_info=[{"patch_id": "p1", "patch_path": "s3://b/p1.jpg", "patch_type": "c"}],
            patch_probs=[0.88],
            retrieval_query="artist",
            top_k_patches=3,
            include_patch_images=True,
            include_overall_image=True,
        )
        assert result.response_text == "Explained."
        assert "kb snippet" in result.retrieved_kb_chunks

    @patch("src.apps.rag_pipeline.generate_response._generate_with_claude")
    @patch("src.apps.rag_pipeline.generate_response._load_single_image_block")
    @patch("src.apps.rag_pipeline.generate_response._load_patch_image_blocks")
    @patch("src.apps.rag_pipeline.generate_response.retrieve_top_chunks")
    def test_strict_patch_images_raises_when_no_images(
        self,
        mock_retrieve,
        mock_load_patches,
        mock_load_single,
        mock_gen,
    ):
        from src.apps.rag_pipeline.generate_response import generate_explanation

        mock_retrieve.return_value = []
        mock_load_patches.return_value = ([], [])
        mock_load_single.return_value = ([], False)

        with pytest.raises(RuntimeError, match="patch images"):
            generate_explanation(
                source_image="s3://b/raw.jpg",
                prediction=1,
                mean_prob=0.9,
                patches_info=[{"patch_id": "p1", "patch_path": "s3://b/p1.jpg"}],
                patch_probs=[0.9],
                retrieval_query="q",
                include_patch_images=True,
                strict_patch_images=True,
                min_patch_images=1,
            )
        mock_gen.assert_not_called()

    @patch("src.apps.rag_pipeline.generate_response._generate_with_claude")
    @patch("src.apps.rag_pipeline.generate_response._load_single_image_block")
    @patch("src.apps.rag_pipeline.generate_response._load_patch_image_blocks")
    @patch("src.apps.rag_pipeline.generate_response.retrieve_top_chunks")
    def test_skip_patch_images_branch(
        self,
        mock_retrieve,
        mock_load_patches,
        mock_load_single,
        mock_gen,
    ):
        from src.apps.rag_pipeline.generate_response import generate_explanation

        mock_retrieve.return_value = []
        mock_gen.return_value = "ok"

        generate_explanation(
            source_image="s3://b/raw.jpg",
            prediction=0,
            mean_prob=0.2,
            patches_info=[{"patch_id": "p1", "patch_path": "s3://b/p1.jpg"}],
            patch_probs=[0.2],
            retrieval_query="q",
            include_patch_images=False,
            include_overall_image=False,
        )
        mock_load_patches.assert_not_called()
        mock_load_single.assert_not_called()
