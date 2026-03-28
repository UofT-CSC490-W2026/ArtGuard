"""Tests for train and evaluate route handlers."""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

# Mock the modal module before importing anything that uses it
mock_modal = MagicMock()
sys.modules.setdefault("modal", mock_modal)


@pytest.fixture
def mock_train_spawns():
    """Modal train functions use await spawn.aio(...); patch with awaitable mocks."""
    with (
        patch("src.apps.train.train.train_swin_tiny") as tiny,
        patch("src.apps.train.train.train_swin_base") as base,
    ):
        tiny.spawn.aio = AsyncMock(return_value=None)
        base.spawn.aio = AsyncMock(return_value=None)
        yield


@pytest.fixture
def modal_credentials(monkeypatch):
    """POST /evaluate checks Modal env before spawn."""
    monkeypatch.setenv("MODAL_TOKEN_ID", "test-token-id")
    monkeypatch.setenv("MODAL_TOKEN_SECRET", "test-token-secret")


class TestStartTraining:
    """Tests for POST /train."""

    @pytest.mark.asyncio
    async def test_invalid_variant_422(self, client):
        """Pydantic rejects invalid Literal values with 422."""
        resp = await client.post("/train", json={"variant": "huge"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_successful_training(self, client, dynamodb, mock_train_spawns):
        """Verify response has valid run_id (UUID), correct variant, and started status.

        Uses real DynamoDB fixture so lines 128-157 (DDB write + Modal spawn) are covered.
        """
        import uuid

        resp = await client.post("/train", json={"variant": "tiny"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "started"
        assert data["variant"] == "tiny"
        uuid.UUID(data["run_id"])

        # Verify the RunRecord was actually written to DynamoDB
        table = dynamodb.Table("test-runs")
        items = table.scan()["Items"]
        assert len(items) == 1
        assert items[0]["status"] == "running"

    @pytest.mark.asyncio
    async def test_base_variant(self, client, dynamodb, mock_train_spawns):
        """Both 'tiny' and 'base' variants are accepted; covers the else branch in spawn."""
        import uuid

        resp = await client.post("/train", json={"variant": "base"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["variant"] == "base"
        assert data["status"] == "started"
        uuid.UUID(data["run_id"])

    @pytest.mark.asyncio
    async def test_with_custom_config(self, client, dynamodb, mock_train_spawns):
        """Custom config is merged with DEFAULT_CONFIG and run is started."""
        resp = await client.post("/train", json={
            "variant": "tiny",
            "config": {"lr": 0.001, "batch_size": 16},
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "started"

    @pytest.mark.asyncio
    async def test_empty_body_defaults_to_tiny(self, client, dynamodb):
        """POST /train with no body should use Pydantic defaults or return 422."""
        resp = await client.post("/train", json={})
        # variant is required by Pydantic — should be 422
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_modal_spawn_failure_500(self, client, dynamodb):
        """Modal spawn failure marks run as FAILED in DynamoDB and returns 500."""
        with patch("src.apps.train.train.train_swin_tiny") as tiny:
            tiny.spawn.aio = AsyncMock(side_effect=Exception("Modal down"))
            resp = await client.post("/train", json={"variant": "tiny"})
            assert resp.status_code == 500
            assert "try again" in resp.json()["detail"].lower()

        # Verify the run was marked as failed in DynamoDB
        table = dynamodb.Table("test-runs")
        items = table.scan()["Items"]
        assert len(items) == 1
        assert items[0]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_missing_runs_table_500(self, client, monkeypatch):
        monkeypatch.delenv("DDB_RUNS_TABLE", raising=False)
        resp = await client.post("/train", json={"variant": "tiny"})
        assert resp.status_code == 500


class TestStartEvaluation:
    """Tests for POST /evaluate."""

    @pytest.mark.asyncio
    async def test_invalid_variant_422(self, client):
        """Pydantic rejects invalid Literal values with 422."""
        resp = await client.post("/evaluate", json={
            "variant": "huge",
            "checkpoint": "/checkpoints/tiny/best.pt",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_bad_checkpoint_path_422(self, client):
        """Pydantic rejects checkpoint paths that don't match the pattern."""
        resp = await client.post("/evaluate", json={
            "variant": "tiny",
            "checkpoint": "/wrong/path.pt",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_successful_evaluation(self, client, modal_credentials):
        """Happy path: valid variant + checkpoint pattern starts evaluation."""
        eval_fn = MagicMock()
        eval_fn.spawn.aio = AsyncMock(return_value=None)
        with patch(
            "src.apps.backend.routes.train_router.modal.Function.from_name",
            return_value=eval_fn,
        ):
            resp = await client.post("/evaluate", json={
                "variant": "tiny",
                "checkpoint": "/checkpoints/tiny/best.pt",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "started"
        assert data["variant"] == "tiny"
        assert data["checkpoint"] == "/checkpoints/tiny/best.pt"

    @pytest.mark.asyncio
    async def test_modal_spawn_failure_500(self, client, modal_credentials):
        eval_fn = MagicMock()
        eval_fn.spawn.aio = AsyncMock(side_effect=Exception("Modal down"))
        with patch(
            "src.apps.backend.routes.train_router.modal.Function.from_name",
            return_value=eval_fn,
        ):
            resp = await client.post("/evaluate", json={
                "variant": "tiny",
                "checkpoint": "/checkpoints/tiny/best.pt",
            })
        assert resp.status_code == 500
        assert "try again" in resp.json()["detail"].lower()


def _clear_modal_creds(monkeypatch):
    for key in ("MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET", "MODAL_API_KEY"):
        monkeypatch.delenv(key, raising=False)


class TestEnsureModalCredentials:
    """Tests for train_router._ensure_modal_credentials."""

    def test_token_pair_in_env_returns_true(self, monkeypatch):
        _clear_modal_creds(monkeypatch)
        monkeypatch.setenv("MODAL_TOKEN_ID", "id")
        monkeypatch.setenv("MODAL_TOKEN_SECRET", "sec")
        from src.apps.backend.routes import train_router

        assert train_router._ensure_modal_credentials() is True

    def test_no_credentials_returns_false(self, monkeypatch):
        _clear_modal_creds(monkeypatch)
        from src.apps.backend.routes import train_router

        assert train_router._ensure_modal_credentials() is False

    def test_whitespace_only_api_key_returns_false(self, monkeypatch):
        _clear_modal_creds(monkeypatch)
        monkeypatch.setenv("MODAL_API_KEY", "   \n  ")
        from src.apps.backend.routes import train_router

        assert train_router._ensure_modal_credentials() is False

    def test_malformed_json_returns_false(self, monkeypatch):
        _clear_modal_creds(monkeypatch)
        monkeypatch.setenv("MODAL_API_KEY", "{not-json")
        from src.apps.backend.routes import train_router

        assert train_router._ensure_modal_credentials() is False

    def test_json_without_token_fields_returns_false(self, monkeypatch):
        _clear_modal_creds(monkeypatch)
        monkeypatch.setenv("MODAL_API_KEY", '{"token_id": "x"}')
        from src.apps.backend.routes import train_router

        assert train_router._ensure_modal_credentials() is False

    def test_json_empty_object_returns_false(self, monkeypatch):
        _clear_modal_creds(monkeypatch)
        monkeypatch.setenv("MODAL_API_KEY", "{}")
        from src.apps.backend.routes import train_router

        assert train_router._ensure_modal_credentials() is False

    def test_json_legacy_api_key_shape_returns_false(self, monkeypatch):
        _clear_modal_creds(monkeypatch)
        monkeypatch.setenv("MODAL_API_KEY", '{"api_key": "only"}')
        from src.apps.backend.routes import train_router

        assert train_router._ensure_modal_credentials() is False

    def test_json_token_pair_sets_env_and_returns_true(self, monkeypatch):
        _clear_modal_creds(monkeypatch)
        monkeypatch.setenv(
            "MODAL_API_KEY",
            '{"token_id": "tid", "token_secret": "tsec"}',
        )
        from src.apps.backend.routes import train_router

        assert train_router._ensure_modal_credentials() is True
        assert os.environ["MODAL_TOKEN_ID"] == "tid"
        assert os.environ["MODAL_TOKEN_SECRET"] == "tsec"

    def test_two_line_format_sets_env(self, monkeypatch):
        _clear_modal_creds(monkeypatch)
        monkeypatch.setenv("MODAL_API_KEY", "firstline\nsecondline")
        from src.apps.backend.routes import train_router

        assert train_router._ensure_modal_credentials() is True
        assert os.environ["MODAL_TOKEN_ID"] == "firstline"
        assert os.environ["MODAL_TOKEN_SECRET"] == "secondline"

    def test_two_line_blank_first_returns_false(self, monkeypatch):
        _clear_modal_creds(monkeypatch)
        monkeypatch.setenv("MODAL_API_KEY", "\nsecret")
        from src.apps.backend.routes import train_router

        assert train_router._ensure_modal_credentials() is False

    def test_two_line_blank_second_returns_false(self, monkeypatch):
        _clear_modal_creds(monkeypatch)
        monkeypatch.setenv("MODAL_API_KEY", "id\n")
        from src.apps.backend.routes import train_router

        assert train_router._ensure_modal_credentials() is False

    def test_plain_string_without_newline_returns_false(self, monkeypatch):
        _clear_modal_creds(monkeypatch)
        monkeypatch.setenv("MODAL_API_KEY", "opaque")
        from src.apps.backend.routes import train_router

        assert train_router._ensure_modal_credentials() is False


class TestTrainRouterDefensiveBranches:
    """Handler branches not reachable via normal request validation."""

    @pytest.mark.asyncio
    async def test_start_training_unknown_variant_500(self):
        from src.apps.backend.routes.train_router import TrainRequest, start_training

        fake_table = MagicMock()
        with patch(
            "src.apps.backend.routes.train_router.get_table",
            return_value=fake_table,
        ):
            body = TrainRequest.model_construct(variant="huge")
            with pytest.raises(HTTPException) as exc:
                await start_training(body)
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_start_evaluation_unknown_variant_400(self):
        from src.apps.backend.routes.train_router import EvaluateRequest, start_evaluation

        body = EvaluateRequest.model_construct(
            variant="huge",
            checkpoint="/checkpoints/tiny/best.pt",
        )
        with pytest.raises(HTTPException) as exc:
            await start_evaluation(body)
        assert exc.value.status_code == 400
        assert "huge" in exc.value.detail

    @pytest.mark.asyncio
    async def test_start_evaluation_bad_checkpoint_prefix_400(self):
        from src.apps.backend.routes.train_router import EvaluateRequest, start_evaluation

        body = EvaluateRequest.model_construct(
            variant="tiny",
            checkpoint="/other/best.pt",
        )
        with pytest.raises(HTTPException) as exc:
            await start_evaluation(body)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_start_evaluation_missing_modal_credentials_500(self, monkeypatch):
        _clear_modal_creds(monkeypatch)
        from src.apps.backend.routes.train_router import EvaluateRequest, start_evaluation

        body = EvaluateRequest.model_construct(
            variant="tiny",
            checkpoint="/checkpoints/tiny/best.pt",
        )
        with pytest.raises(HTTPException) as exc:
            await start_evaluation(body)
        assert exc.value.status_code == 500
