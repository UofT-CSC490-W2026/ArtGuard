#!/usr/bin/env python3
"""Start the FastAPI backend with mocked AWS services for E2E testing.

Uses moto to mock S3 and DynamoDB so no real AWS credentials are needed.
Creates all required tables and buckets, then starts uvicorn on port 8000.

Usage:
    python scripts/start_e2e_backend.py
"""
import os

# Must be set before any boto3/moto imports
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SECURITY_TOKEN", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("ENVIRONMENT", "dev")
os.environ.setdefault("JWT_SECRET_KEY", "e2e-test-secret-key-do-not-use-in-prod")
os.environ.setdefault("DDB_USERS_TABLE", "e2e-users")
os.environ.setdefault("DDB_INFERENCES_TABLE", "e2e-inferences")
os.environ.setdefault("DDB_IMAGES_TABLE", "e2e-images")
os.environ.setdefault("DDB_PATCHES_TABLE", "e2e-patches")
os.environ.setdefault("DDB_RUNS_TABLE", "e2e-runs")
os.environ.setdefault("S3_IMAGES_RAW_BUCKET", "e2e-raw")
os.environ.setdefault("S3_IMAGES_PROCESSED_BUCKET", "e2e-processed")
os.environ.setdefault("CORS_ALLOW_ORIGINS", "*")

import boto3
from moto import mock_aws

# Start moto mock — must stay active for the lifetime of the process
_mock = mock_aws()
_mock.start()

# Clear lru_cache so boto3 clients pick up moto
from src.apps.backend.config import s3_client, dynamodb_resource
s3_client.cache_clear()
dynamodb_resource.cache_clear()

# Create S3 buckets
s3 = boto3.client("s3", region_name="us-east-1")
for bucket in ["e2e-raw", "e2e-processed"]:
    s3.create_bucket(Bucket=bucket)

# Create DynamoDB tables
ddb = boto3.resource("dynamodb", region_name="us-east-1")

ddb.create_table(
    TableName="e2e-users",
    KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
    AttributeDefinitions=[
        {"AttributeName": "user_id", "AttributeType": "S"},
        {"AttributeName": "email", "AttributeType": "S"},
    ],
    GlobalSecondaryIndexes=[{
        "IndexName": "EmailIndex",
        "KeySchema": [{"AttributeName": "email", "KeyType": "HASH"}],
        "Projection": {"ProjectionType": "ALL"},
    }],
    BillingMode="PAY_PER_REQUEST",
)

ddb.create_table(
    TableName="e2e-inferences",
    KeySchema=[{"AttributeName": "inference_id", "KeyType": "HASH"}],
    AttributeDefinitions=[
        {"AttributeName": "inference_id", "AttributeType": "S"},
        {"AttributeName": "user_id", "AttributeType": "S"},
        {"AttributeName": "created_at", "AttributeType": "N"},
    ],
    GlobalSecondaryIndexes=[{
        "IndexName": "UserInferencesIndex",
        "KeySchema": [
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "created_at", "KeyType": "RANGE"},
        ],
        "Projection": {"ProjectionType": "ALL"},
    }],
    BillingMode="PAY_PER_REQUEST",
)

for table_name in ["e2e-images", "e2e-patches"]:
    pk = "image_id" if "images" in table_name else "patch_id"
    ddb.create_table(
        TableName=table_name,
        KeySchema=[{"AttributeName": pk, "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": pk, "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )

ddb.create_table(
    TableName="e2e-runs",
    KeySchema=[{"AttributeName": "run_id", "KeyType": "HASH"}],
    AttributeDefinitions=[{"AttributeName": "run_id", "AttributeType": "S"}],
    BillingMode="PAY_PER_REQUEST",
)

print("E2E backend: AWS resources created", flush=True)

# Mock Modal inference so full-stack E2E tests don't need real Modal credentials
import random
from src.apps.backend.services import inference_service

def _mock_run_modal_inference(patch_s3_uris: list[str]) -> dict:
    n = len(patch_s3_uris) or 1
    probs = [round(random.uniform(0.6, 0.95), 4) for _ in range(n)]
    mean_prob = sum(probs) / n
    prediction = 1 if mean_prob >= 0.5 else 0
    preds = [1 if p >= 0.5 else 0 for p in probs]
    return {
        "mean_prob": mean_prob,
        "prediction": prediction,
        "patch_probs": probs,
        "patch_preds": preds,
    }

inference_service.run_modal_inference = _mock_run_modal_inference
print("E2E backend: Modal inference mocked", flush=True)

# Start uvicorn
import uvicorn
uvicorn.run(
    "src.apps.backend.main:app",
    host="127.0.0.1",
    port=8000,
    log_level="warning",
)
