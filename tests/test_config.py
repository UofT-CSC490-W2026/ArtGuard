"""Tests for src.apps.backend.config — env vars, enums, pagination helpers."""

import os
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.apps.backend.config import (
    DEFAULT_REGION,
    DDB_INFERENCES_TABLE,
    InferenceStatus,
    RunStatus,
    bedrock_model_arn,
    get_region,
    paginated_query,
    paginated_query_count,
    require_env,
)


class TestRequireEnv:
    """Tests for the require_env helper."""

    def test_returns_value_when_set(self, monkeypatch):
        monkeypatch.setenv("MY_TEST_VAR", "hello")
        assert require_env("MY_TEST_VAR") == "hello"

    def test_strips_whitespace(self, monkeypatch):
        monkeypatch.setenv("MY_TEST_VAR", "  hello  ")
        assert require_env("MY_TEST_VAR") == "hello"

    def test_raises_when_unset(self, monkeypatch):
        monkeypatch.delenv("DEFINITELY_NOT_SET", raising=False)
        with pytest.raises(EnvironmentError, match="DEFINITELY_NOT_SET"):
            require_env("DEFINITELY_NOT_SET")

    def test_raises_when_empty(self, monkeypatch):
        monkeypatch.setenv("EMPTY_VAR", "")
        with pytest.raises(EnvironmentError, match="EMPTY_VAR"):
            require_env("EMPTY_VAR")

    def test_raises_when_whitespace_only(self, monkeypatch):
        monkeypatch.setenv("SPACE_VAR", "   ")
        with pytest.raises(EnvironmentError, match="SPACE_VAR"):
            require_env("SPACE_VAR")


class TestGetRegion:
    """Tests for get_region."""

    def test_returns_env_var_when_set(self, monkeypatch):
        monkeypatch.setenv("AWS_REGION", "eu-west-1")
        assert get_region() == "eu-west-1"

    def test_returns_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("AWS_REGION", raising=False)
        assert get_region() == DEFAULT_REGION


class TestBedrockModelArn:
    """Tests for bedrock_model_arn."""

    def test_contains_region(self, monkeypatch):
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        arn = bedrock_model_arn()
        assert "us-east-1" in arn
        assert "foundation-model/" in arn
        assert arn.startswith("arn:aws:bedrock:")


class TestInferenceStatus:
    """Tests for InferenceStatus enum."""

    def test_values(self):
        assert InferenceStatus.PROCESSING == "processing"
        assert InferenceStatus.COMPLETED == "completed"
        assert InferenceStatus.FAILED == "failed"

    def test_is_string(self):
        assert isinstance(InferenceStatus.PROCESSING, str)


class TestRunStatus:
    """Tests for RunStatus enum."""

    def test_values(self):
        assert RunStatus.RUNNING == "running"
        assert RunStatus.COMPLETED == "completed"
        assert RunStatus.COMPLETED_WITH_ERRORS == "completed_with_errors"
        assert RunStatus.FAILED == "failed"


class TestPaginatedQuery:
    """Tests for DynamoDB pagination helpers."""

    def test_single_page(self):
        table = MagicMock()
        table.query.return_value = {
            "Items": [{"id": "1"}, {"id": "2"}],
        }
        result = paginated_query(table, KeyConditionExpression="pk = :pk")
        assert len(result) == 2
        assert result[0]["id"] == "1"

    def test_multiple_pages(self):
        table = MagicMock()
        table.query.side_effect = [
            {"Items": [{"id": "1"}], "LastEvaluatedKey": {"id": "1"}},
            {"Items": [{"id": "2"}]},
        ]
        result = paginated_query(table, KeyConditionExpression="pk = :pk")
        assert len(result) == 2
        assert table.query.call_count == 2

    def test_empty_result(self):
        table = MagicMock()
        table.query.return_value = {"Items": []}
        result = paginated_query(table)
        assert result == []


class TestPaginatedQueryCount:
    """Tests for paginated_query_count."""

    def test_single_page_count(self):
        table = MagicMock()
        table.query.return_value = {"Count": 42}
        result = paginated_query_count(table, KeyConditionExpression="pk = :pk")
        assert result == 42

    def test_multi_page_count(self):
        table = MagicMock()
        table.query.side_effect = [
            {"Count": 100, "LastEvaluatedKey": {"id": "x"}},
            {"Count": 50},
        ]
        result = paginated_query_count(table, KeyConditionExpression="pk = :pk")
        assert result == 150

    def test_sets_select_count(self):
        table = MagicMock()
        table.query.return_value = {"Count": 0}
        paginated_query_count(table, IndexName="MyIndex")
        call_kwargs = table.query.call_args[1]
        assert call_kwargs["Select"] == "COUNT"
