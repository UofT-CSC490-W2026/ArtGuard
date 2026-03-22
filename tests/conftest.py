"""Shared pytest fixtures for ArtGuard test suite.

Provides mocked AWS services (S3, DynamoDB, STS via moto), a FastAPI
test client, and helper factories for generating test data.
"""

import os
import uuid

import boto3
import pytest
from moto import mock_aws


# ---------------------------------------------------------------------------
# Environment setup — run before any application imports
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _set_test_env(monkeypatch):
    """Set required environment variables for all tests."""
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

    monkeypatch.setenv("DDB_USERS_TABLE", "test-users")
    monkeypatch.setenv("DDB_INFERENCES_TABLE", "test-inferences")
    monkeypatch.setenv("DDB_IMAGES_TABLE", "test-images")
    monkeypatch.setenv("DDB_PATCHES_TABLE", "test-patches")
    monkeypatch.setenv("DDB_RUNS_TABLE", "test-runs")
    monkeypatch.setenv("S3_IMAGES_RAW_BUCKET", "test-raw-bucket")
    monkeypatch.setenv("S3_IMAGES_PROCESSED_BUCKET", "test-processed-bucket")

    # Clear lru_cache between tests so moto mocks are picked up
    from src.apps.backend.config import s3_client, dynamodb_resource
    s3_client.cache_clear()
    dynamodb_resource.cache_clear()


# ---------------------------------------------------------------------------
# AWS moto fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def aws_credentials():
    """Mocked AWS credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture
def mock_aws_services():
    """Start moto mock for S3, DynamoDB, and STS."""
    with mock_aws():
        # Clear caches so boto3 picks up moto
        from src.apps.backend.config import s3_client, dynamodb_resource
        s3_client.cache_clear()
        dynamodb_resource.cache_clear()
        yield


@pytest.fixture
def s3(mock_aws_services):
    """Mocked S3 client with test buckets created."""
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="test-raw-bucket")
    client.create_bucket(Bucket="test-processed-bucket")
    return client


@pytest.fixture
def dynamodb(mock_aws_services):
    """Mocked DynamoDB resource with all test tables created."""
    ddb = boto3.resource("dynamodb", region_name="us-east-1")

    # Users table
    ddb.create_table(
        TableName="test-users",
        KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "email", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "EmailIndex",
                "KeySchema": [{"AttributeName": "email", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    # Inferences table
    ddb.create_table(
        TableName="test-inferences",
        KeySchema=[{"AttributeName": "inference_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "inference_id", "AttributeType": "S"},
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "created_at", "AttributeType": "N"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "UserInferencesIndex",
                "KeySchema": [
                    {"AttributeName": "user_id", "KeyType": "HASH"},
                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    # Images table
    ddb.create_table(
        TableName="test-images",
        KeySchema=[{"AttributeName": "image_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "image_id", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    # Patches table
    ddb.create_table(
        TableName="test-patches",
        KeySchema=[{"AttributeName": "patch_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "patch_id", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    # Runs table
    ddb.create_table(
        TableName="test-runs",
        KeySchema=[{"AttributeName": "run_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "run_id", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    return ddb


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """Return the FastAPI application instance."""
    from src.apps.backend.main import app
    return app


@pytest.fixture
def client(app, s3, dynamodb):
    """HTTPX-based test client for the FastAPI app with mocked AWS."""
    from httpx import ASGITransport, AsyncClient
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://testserver")


@pytest.fixture
def auth_headers():
    """Return Authorization headers with a valid JWT for user_id='test-user-1'."""
    from src.apps.backend.security.jwt_tokens import create_access_token
    token = create_access_token("test-user-1")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def create_test_user(dynamodb):
    """Factory fixture to create a test user in DynamoDB."""
    def _create(user_id="test-user-1", email="test@example.com", username="testuser"):
        from src.apps.backend.security.passwords import hash_password
        table = dynamodb.Table("test-users")
        item = {
            "user_id": user_id,
            "email": email.lower(),
            "username": username,
            "password_hash": hash_password("password123"),
            "created_at": 1700000000000,
        }
        table.put_item(Item=item)
        return item
    return _create


@pytest.fixture
def sample_image_bytes():
    """Return minimal valid JPEG bytes for testing image uploads."""
    from PIL import Image
    from io import BytesIO
    img = Image.new("RGB", (600, 600), color="red")
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()
