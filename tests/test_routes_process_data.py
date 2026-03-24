"""Tests for process_data route handler."""

from unittest.mock import MagicMock, patch

import pytest


class TestProcessData:
    """Tests for POST /process_data."""

    @pytest.mark.asyncio
    async def test_missing_subnets_500(self, client, monkeypatch):
        monkeypatch.setenv("ECS_PRIVATE_SUBNETS", "")
        monkeypatch.setenv("ECS_TASK_SECURITY_GROUPS", "")
        resp = await client.post("/process_data")
        assert resp.status_code == 500
        assert "not properly configured" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_sts_failure_500(self, client, monkeypatch):
        monkeypatch.setenv("ECS_PRIVATE_SUBNETS", "subnet-abc")
        monkeypatch.setenv("ECS_TASK_SECURITY_GROUPS", "sg-123")

        with patch("src.apps.backend.routes.process_data_router.boto3") as mock_boto3:
            mock_sts = MagicMock()
            mock_sts.get_caller_identity.side_effect = Exception("STS down")
            mock_boto3.client.return_value = mock_sts

            resp = await client.post("/process_data")
            assert resp.status_code == 500
            assert "credentials" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_successful_launch(self, client, monkeypatch):
        monkeypatch.setenv("ECS_PRIVATE_SUBNETS", "subnet-abc")
        monkeypatch.setenv("ECS_TASK_SECURITY_GROUPS", "sg-123")

        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}

        mock_ecs = MagicMock()
        mock_ecs.run_task.return_value = {
            "tasks": [{"taskArn": "arn:aws:ecs:us-east-1:123456789012:task/abc"}],
            "failures": [],
        }

        with patch("src.apps.backend.routes.process_data_router.boto3") as mock_boto3:
            # First call is STS, second is ECS
            mock_boto3.client.side_effect = [mock_sts, mock_ecs]

            resp = await client.post("/process_data")
            assert resp.status_code == 200
            data = resp.json()
            assert "run_id" in data
            assert "task_arn" in data

    @pytest.mark.asyncio
    async def test_ecs_failures_500(self, client, monkeypatch):
        monkeypatch.setenv("ECS_PRIVATE_SUBNETS", "subnet-abc")
        monkeypatch.setenv("ECS_TASK_SECURITY_GROUPS", "sg-123")

        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}

        mock_ecs = MagicMock()
        mock_ecs.run_task.return_value = {
            "tasks": [],
            "failures": [{"reason": "RESOURCE:MEMORY", "arn": "arn:aws:ecs:..."}],
        }

        with patch("src.apps.backend.routes.process_data_router.boto3") as mock_boto3:
            mock_boto3.client.side_effect = [mock_sts, mock_ecs]

            resp = await client.post("/process_data")
            assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_ecs_no_tasks_500(self, client, monkeypatch):
        monkeypatch.setenv("ECS_PRIVATE_SUBNETS", "subnet-abc")
        monkeypatch.setenv("ECS_TASK_SECURITY_GROUPS", "sg-123")

        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}

        mock_ecs = MagicMock()
        mock_ecs.run_task.return_value = {"tasks": [], "failures": []}

        with patch("src.apps.backend.routes.process_data_router.boto3") as mock_boto3:
            mock_boto3.client.side_effect = [mock_sts, mock_ecs]

            resp = await client.post("/process_data")
            assert resp.status_code == 500
            assert "try again" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_ecs_run_task_exception_500(self, client, monkeypatch):
        monkeypatch.setenv("ECS_PRIVATE_SUBNETS", "subnet-abc")
        monkeypatch.setenv("ECS_TASK_SECURITY_GROUPS", "sg-123")

        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}

        mock_ecs = MagicMock()
        mock_ecs.run_task.side_effect = Exception("ECS error")

        with patch("src.apps.backend.routes.process_data_router.boto3") as mock_boto3:
            mock_boto3.client.side_effect = [mock_sts, mock_ecs]

            resp = await client.post("/process_data")
            assert resp.status_code == 500
            assert "try again" in resp.json()["detail"].lower()
