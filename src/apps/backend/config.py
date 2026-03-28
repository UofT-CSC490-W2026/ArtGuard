"""Centralized configuration, AWS client factory, and shared constants.

Provides a single source of truth for environment variable access,
AWS client creation, and status/index name constants used across
the backend.
"""

from __future__ import annotations

import logging
import os
from enum import Enum
from functools import lru_cache
from typing import Any

import boto3

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Required env var helper
# ---------------------------------------------------------------------------


def require_env(name: str) -> str:
    """Read a required environment variable, raising if it is not set.

    >>> import os; os.environ["TEST_VAR"] = "hello"
    >>> require_env("TEST_VAR")
    'hello'

    Args:
        name: The environment variable name.

    Returns:
        The environment variable value.

    Raises:
        EnvironmentError: If the variable is not set or is empty.
    """
    value = os.getenv(name, "").strip()
    if not value:
        raise EnvironmentError(f"Required environment variable {name} is not set")
    return value


# ---------------------------------------------------------------------------
# AWS region
# ---------------------------------------------------------------------------

DEFAULT_REGION = "ca-central-1"


def get_region() -> str:
    """Return the configured AWS region, falling back to ca-central-1."""
    return os.getenv("AWS_REGION", DEFAULT_REGION)


# ---------------------------------------------------------------------------
# AWS client factory (cached to avoid redundant client creation)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=None)
def s3_client():
    """Return a shared boto3 S3 client for the configured region."""
    return boto3.client("s3", region_name=get_region())


@lru_cache(maxsize=None)
def dynamodb_resource():
    """Return a shared boto3 DynamoDB resource for the configured region."""
    return boto3.resource("dynamodb", region_name=get_region())


def get_table(env_var: str):
    """Return a DynamoDB Table resource for the table named by env_var.

    Args:
        env_var: Environment variable that holds the table name
                 (e.g. ``"DDB_INFERENCES_TABLE"``).

    Returns:
        A boto3 DynamoDB Table resource.

    Raises:
        EnvironmentError: If the environment variable is not set.
    """
    table_name = require_env(env_var)
    return dynamodb_resource().Table(table_name)


# ---------------------------------------------------------------------------
# Status enums (eliminates magic strings)
# ---------------------------------------------------------------------------


class InferenceStatus(str, Enum):
    """Status values for inference records in DynamoDB."""

    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class RunStatus(str, Enum):
    """Status values for training/processing run records in DynamoDB."""

    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# DynamoDB index name constants
# ---------------------------------------------------------------------------

USER_INFERENCES_INDEX = "UserInferencesIndex"
EMAIL_INDEX = "EmailIndex"
IMAGE_PATCHES_INDEX = "image_id-index"

# ---------------------------------------------------------------------------
# Table env var names
# ---------------------------------------------------------------------------

DDB_USERS_TABLE = "DDB_USERS_TABLE"
DDB_INFERENCES_TABLE = "DDB_INFERENCES_TABLE"
DDB_IMAGES_TABLE = "DDB_IMAGES_TABLE"
DDB_PATCHES_TABLE = "DDB_PATCHES_TABLE"
DDB_RUNS_TABLE = "DDB_RUNS_TABLE"

# ---------------------------------------------------------------------------
# S3 bucket env var names
# ---------------------------------------------------------------------------

S3_IMAGES_RAW_BUCKET = "S3_IMAGES_RAW_BUCKET"
S3_IMAGES_PROCESSED_BUCKET = "S3_IMAGES_PROCESSED_BUCKET"

# ---------------------------------------------------------------------------
# Bedrock model ARN
# ---------------------------------------------------------------------------

BEDROCK_MODEL_ID = "anthropic.claude-sonnet-4-5-20250929-v1:0"

# Sonnet 4.5 (and sometimes other Claude models) may require a Bedrock
# inference profile (often a cross-region profile) rather than direct
# foundation-model invocation in certain regions. If this env var is set,
# we route both RAG + multimodal generation through the inference profile.
# Sonnet 4.5+ requires an inference profile for on-demand invocation.
# Default to the US cross-region profile if not explicitly configured.
_DEFAULT_INFERENCE_PROFILE = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
BEDROCK_INFERENCE_PROFILE_ARN = os.getenv(
    "BEDROCK_INFERENCE_PROFILE_ARN", _DEFAULT_INFERENCE_PROFILE
).strip()

def bedrock_invoke_model_id() -> str:
    """Return the value for Bedrock Runtime `modelId`.

    If `BEDROCK_INFERENCE_PROFILE_ARN` is configured, Bedrock accepts the
    inference profile ARN in `modelId` and routes the request accordingly.
    Otherwise we fall back to the foundation model id.
    """
    if BEDROCK_INFERENCE_PROFILE_ARN:
        return BEDROCK_INFERENCE_PROFILE_ARN
    return BEDROCK_MODEL_ID


def bedrock_model_arn() -> str:
    """Return the full Bedrock foundation model ARN for the configured region."""
    # Bedrock KnowledgeBaseRetrieveAndGenerate accepts either a foundation-model
    # ARN or an inference profile ARN.
    if BEDROCK_INFERENCE_PROFILE_ARN:
        return BEDROCK_INFERENCE_PROFILE_ARN
    region = get_region()
    return f"arn:aws:bedrock:{region}::foundation-model/{BEDROCK_MODEL_ID}"


# ---------------------------------------------------------------------------
# DynamoDB pagination helper
# ---------------------------------------------------------------------------


def paginated_query(table, **kwargs) -> list[dict[str, Any]]:
    """Run a DynamoDB query and paginate through all result pages.

    Handles the ExclusiveStartKey pagination loop automatically.

    >>> results = paginated_query(table, IndexName="MyIndex", ...)  # doctest: +SKIP

    Args:
        table:    A boto3 DynamoDB Table resource.
        **kwargs: Arguments passed to ``table.query()``.

    Returns:
        A flat list of all item dicts across all pages.
    """
    items: list[dict[str, Any]] = []
    resp = table.query(**kwargs)
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        resp = table.query(**kwargs)
        items.extend(resp.get("Items", []))
    return items


def paginated_query_count(table, **kwargs) -> int:
    """Run a DynamoDB query with Select=COUNT and return the total count.

    Args:
        table:    A boto3 DynamoDB Table resource.
        **kwargs: Arguments passed to ``table.query()``, excluding Select.

    Returns:
        Total item count across all pages.
    """
    kwargs["Select"] = "COUNT"
    total = 0
    resp = table.query(**kwargs)
    total += int(resp.get("Count", 0))
    while "LastEvaluatedKey" in resp:
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        resp = table.query(**kwargs)
        total += int(resp.get("Count", 0))
    return total
