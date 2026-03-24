"""Tests for src.apps.backend.validation — shared validation constraints and helpers."""

import pytest

from src.apps.backend.validation import (
    ARTIST_NAME_MAX,
    EMAIL_MAX,
    MAX_UPLOAD_SIZE_BYTES,
    PASSWORD_MAX,
    RAG_QUERY_MAX,
    USERNAME_MAX,
    clamp_score,
    sanitize_filename,
    truncate,
    validate_prediction,
)


class TestClampScore:
    """Tests for clamp_score."""

    def test_within_range(self):
        assert clamp_score(0.5) == 0.5

    def test_at_zero(self):
        assert clamp_score(0.0) == 0.0

    def test_at_one(self):
        assert clamp_score(1.0) == 1.0

    def test_below_zero(self):
        assert clamp_score(-0.5) == 0.0

    def test_above_one(self):
        assert clamp_score(1.5) == 1.0

    def test_large_negative(self):
        assert clamp_score(-100.0) == 0.0


class TestValidatePrediction:
    """Tests for validate_prediction."""

    def test_authentic(self):
        assert validate_prediction(1) == 1

    def test_forgery(self):
        assert validate_prediction(0) == 0

    def test_pending(self):
        assert validate_prediction(-1) == -1

    def test_invalid_high(self):
        assert validate_prediction(99) == -1

    def test_invalid_negative(self):
        assert validate_prediction(-5) == -1


class TestTruncate:
    """Tests for truncate."""

    def test_short_string(self):
        assert truncate("hello", 10) == "hello"

    def test_exact_length(self):
        assert truncate("hello", 5) == "hello"

    def test_long_string(self):
        assert truncate("hello world", 5) == "hello"

    def test_empty_string(self):
        assert truncate("", 10) == ""


class TestSanitizeFilename:
    """Tests for sanitize_filename."""

    def test_normal_filename(self):
        assert sanitize_filename("photo.jpg") == "photo.jpg"

    def test_path_traversal(self):
        assert sanitize_filename("../../etc/passwd") == "passwd"

    def test_backslash_traversal(self):
        # os.path.basename on Unix doesn't split on backslash, but the
        # string still has traversal removed by stripping leading dots
        result = sanitize_filename("..\\..\\windows\\system32")
        assert ".." not in result

    def test_null_bytes(self):
        assert sanitize_filename("file\x00.jpg") == "file.jpg"

    def test_empty_string(self):
        assert sanitize_filename("") == "unnamed"

    def test_hidden_file(self):
        assert sanitize_filename(".hidden") == "hidden"

    def test_spaces_preserved(self):
        assert sanitize_filename("my photo.jpg") == "my photo.jpg"


class TestConstants:
    """Verify key constants have sensible values."""

    def test_max_upload_size(self):
        assert MAX_UPLOAD_SIZE_BYTES == 20 * 1024 * 1024

    def test_string_limits_positive(self):
        assert USERNAME_MAX > 0
        assert EMAIL_MAX > 0
        assert ARTIST_NAME_MAX > 0
        assert PASSWORD_MAX > 0
        assert RAG_QUERY_MAX > 0


class TestSchemaPostInitValidation:
    """Tests for __post_init__ validators on dataclass schemas."""

    def test_inference_record_clamps_score(self):
        from src.apps.data_pipeline.schemas import InferenceRecord
        r = InferenceRecord(score=1.5)
        assert r.score == 1.0
        r2 = InferenceRecord(score=-0.3)
        assert r2.score == 0.0

    def test_inference_record_truncates_explanation(self):
        from src.apps.data_pipeline.schemas import InferenceRecord
        long_text = "x" * 20_000
        r = InferenceRecord(explanation=long_text)
        assert len(r.explanation) == 10_000

    def test_image_record_clamps_dimensions(self):
        from src.apps.data_pipeline.schemas import ImageRecord
        r = ImageRecord(image_width=-10, image_height=-5)
        assert r.image_width == 0
        assert r.image_height == 0

    def test_image_record_validates_label(self):
        from src.apps.data_pipeline.schemas import ImageRecord
        r = ImageRecord(label="invalid_label")
        assert r.label is None

    def test_image_record_validates_sublabel(self):
        from src.apps.data_pipeline.schemas import ImageRecord
        r = ImageRecord(sublabel="not_a_real_sublabel")
        assert r.sublabel is None

    def test_image_record_validates_split(self):
        from src.apps.data_pipeline.schemas import ImageRecord
        r = ImageRecord(split="garbage")
        assert r.split == "unassigned"

    def test_image_record_valid_enums_pass(self):
        from src.apps.data_pipeline.schemas import ImageRecord
        r = ImageRecord(label="authentic", sublabel="original", split="train")
        assert r.label == "authentic"
        assert r.sublabel == "original"
        assert r.split == "train"

    def test_patch_record_clamps_coordinates(self):
        from src.apps.data_pipeline.schemas import PatchRecord
        r = PatchRecord(patch_x=-10, patch_y=-5, patch_width=-1, patch_height=-1)
        assert r.patch_x == 0
        assert r.patch_y == 0
        assert r.patch_width == 0
        assert r.patch_height == 0

    def test_run_record_validates_status(self):
        from src.apps.data_pipeline.schemas import RunRecord
        r = RunRecord(status="invalid")
        assert r.status == "running"

    def test_run_record_clamps_k_folds(self):
        from src.apps.data_pipeline.schemas import RunRecord
        r = RunRecord(k_folds=1)
        assert r.k_folds == 2  # Minimum 2 folds

    def test_run_record_clamps_metrics(self):
        from src.apps.data_pipeline.schemas import RunRecord
        r = RunRecord(mean_accuracy=1.5, mean_auc=-0.1)
        assert r.mean_accuracy == 1.0
        assert r.mean_auc == 0.0

    def test_config_record_clamps_fold_id(self):
        from src.apps.data_pipeline.schemas import ConfigRecord
        r = ConfigRecord(fold_id=-1)
        assert r.fold_id == 0

    def test_config_record_clamps_best_epoch(self):
        from src.apps.data_pipeline.schemas import ConfigRecord
        r = ConfigRecord(best_epoch=-5)
        assert r.best_epoch == 0

    def test_user_strips_and_truncates(self):
        from src.apps.data_pipeline.schemas import User
        u = User(username="  " + "a" * 100, email="  TEST@EXAMPLE.COM  ")
        assert len(u.username) <= 50
        assert u.email == "test@example.com"


class TestPydanticRequestValidation:
    """Tests for Pydantic model validation on API request bodies."""

    @pytest.mark.asyncio
    async def test_signup_username_too_long(self, client):
        resp = await client.post("/auth/signup", json={
            "username": "a" * 100,
            "email": "test@example.com",
            "password": "password123",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_signup_password_too_long(self, client):
        resp = await client.post("/auth/signup", json={
            "username": "test",
            "email": "test@example.com",
            "password": "a" * 200,
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_login_empty_password_rejected(self, client):
        resp = await client.post("/auth/login", json={
            "email": "test@example.com",
            "password": "",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_rag_query_empty_rejected(self, client, s3, dynamodb):
        resp = await client.post("/rag-query", json={"query": ""})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_rag_query_too_long_rejected(self, client, s3, dynamodb):
        resp = await client.post("/rag-query", json={"query": "x" * 3000})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_inference_file_too_large(self, client, auth_headers, s3, dynamodb):
        """POST /inference rejects files over MAX_UPLOAD_SIZE_BYTES."""
        huge_content = b"x" * (MAX_UPLOAD_SIZE_BYTES + 1)
        resp = await client.post(
            "/inference",
            data={"artist_name": "Test", "artwork_name": "Test"},
            files={"file": ("huge.jpg", huge_content, "image/jpeg")},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "too large" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_train_invalid_variant_rejected(self, client):
        resp = await client.post("/train", json={"variant": "mega"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_evaluate_bad_checkpoint_pattern(self, client):
        resp = await client.post("/evaluate", json={
            "variant": "tiny",
            "checkpoint": "/tmp/evil.sh",
        })
        assert resp.status_code == 422
