"""DynamoDB user persistence for auth."""

from __future__ import annotations

import os
import time
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError

EMAIL_INDEX = "EmailIndex"


def _table():
    name = os.getenv("DDB_USERS_TABLE")
    if not name:
        raise RuntimeError("DDB_USERS_TABLE is not configured")
    region = os.getenv("AWS_REGION", "ca-central-1")
    return boto3.resource("dynamodb", region_name=region).Table(name)


def get_user_by_email(email: str) -> Optional[dict[str, Any]]:
    email_lower = email.strip().lower()
    table = _table()
    resp = table.query(
        IndexName=EMAIL_INDEX,
        KeyConditionExpression="email = :e",
        ExpressionAttributeValues={":e": email_lower},
        Limit=1,
    )
    items = resp.get("Items") or []
    return items[0] if items else None


def get_user_by_id(user_id: str) -> Optional[dict[str, Any]]:
    table = _table()
    resp = table.get_item(Key={"user_id": user_id})
    return resp.get("Item")


def create_user(
    user_id: str,
    email: str,
    username: str,
    password_hash: str,
) -> dict[str, Any]:
    email_lower = email.strip().lower()
    now = int(time.time() * 1000)
    item = {
        "user_id": user_id,
        "email": email_lower,
        "username": username.strip(),
        "password_hash": password_hash,
        "created_at": now,
    }
    table = _table()
    try:
        table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(user_id)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise ValueError("User already exists") from e
        raise
    return item


def update_user_profile(user_id: str, username: str, email: str) -> dict[str, Any]:
    email_lower = email.strip().lower()
    table = _table()
    table.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET #u = :username, #e = :email, #ua = :updated",
        ExpressionAttributeNames={"#u": "username", "#e": "email", "#ua": "updated_at"},
        ExpressionAttributeValues={
            ":username": username.strip(),
            ":email": email_lower,
            ":updated": int(time.time() * 1000),
        },
    )
    updated = get_user_by_id(user_id)
    if not updated:
        raise ValueError("User not found after update")
    return updated


def update_password_hash(user_id: str, password_hash: str) -> None:
    table = _table()
    table.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET password_hash = :ph, #ua = :updated",
        ExpressionAttributeNames={"#ua": "updated_at"},
        ExpressionAttributeValues={
            ":ph": password_hash,
            ":updated": int(time.time() * 1000),
        },
    )
