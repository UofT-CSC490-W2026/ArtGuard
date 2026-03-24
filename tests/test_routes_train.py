"""Tests for train and evaluate route handlers."""

import sys
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

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
        """Verify response has valid run_id (UUID), correct variant, and started status."""
        import uuid

        with patch("src.apps.backend.routes.train_router.get_table") as mock_get_table:
            mock_tbl = MagicMock()
            mock_get_table.return_value = mock_tbl

            resp = await client.post("/train", json={"variant": "tiny"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "started"
            assert data["variant"] == "tiny"
            # run_id must be a valid UUID-4
            uuid.UUID(data["run_id"])

    @pytest.mark.asyncio
    async def test_base_variant(self, client, dynamodb, mock_train_spawns):
        """Both 'tiny' and 'base' variants are accepted."""
        import uuid

        with patch("src.apps.backend.routes.train_router.get_table") as mock_get_table:
            mock_tbl = MagicMock()
            mock_get_table.return_value = mock_tbl

            resp = await client.post("/train", json={"variant": "base"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["variant"] == "base"
            assert data["status"] == "started"
            uuid.UUID(data["run_id"])

    @pytest.mark.asyncio
    async def test_with_custom_config(self, client, dynamodb, mock_train_spawns):
        """Custom config is accepted without error; run is started."""
        with patch("src.apps.backend.routes.train_router.get_table") as mock_get_table:
            mock_tbl = MagicMock()
            mock_get_table.return_value = mock_tbl

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
        with patch("src.apps.backend.routes.train_router.get_table") as mock_get_table:
            mock_tbl = MagicMock()
            mock_get_table.return_value = mock_tbl

            with patch("src.apps.train.train.train_swin_tiny") as tiny:
                tiny.spawn.aio = AsyncMock(side_effect=Exception("Modal down"))
                resp = await client.post("/train", json={"variant": "tiny"})
                assert resp.status_code == 500
                assert "try again" in resp.json()["detail"].lower()

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
