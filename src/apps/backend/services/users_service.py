"""DynamoDB user persistence for authentication.

Provides CRUD operations for user records in the DynamoDB users table.
The table name is read from the ``DDB_USERS_TABLE`` environment variable
and must have an ``EmailIndex`` GSI on the ``email`` attribute.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from botocore.exceptions import ClientError

from src.apps.backend.config import (
    DDB_USERS_TABLE,
    EMAIL_INDEX,
    get_table,
)

logger = logging.getLogger(__name__)


def _table():
    """Return the DynamoDB Table resource for user records.

    Raises:
        EnvironmentError: If DDB_USERS_TABLE is not set.
    """
    return get_table(DDB_USERS_TABLE)


def get_user_by_email(email: str) -> Optional[dict[str, Any]]:
    """Look up a user by email address (case-insensitive).

    Queries the EmailIndex GSI. Returns the first matching DynamoDB item
    dict, or None if no user has this email.

    >>> get_user_by_email("ALICE@example.com")  # queries with "alice@example.com"
    """
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
    """Fetch a user record by primary key (user_id).

    Returns the full DynamoDB item dict, or None if no user exists
    with this user_id.
    """
    table = _table()
    resp = table.get_item(Key={"user_id": user_id})
    return resp.get("Item")


def create_user(
    user_id: str,
    email: str,
    username: str,
    password_hash: str,
) -> dict[str, Any]:
    """Create a new user record in DynamoDB.

    Uses a conditional put to prevent overwriting an existing user_id.
    The email is stored in lowercase for case-insensitive lookups.

    Returns:
        The created item dict.

    Raises:
        ValueError: If a user with this user_id already exists.
    """
    email_lower = email.strip().lower()
    now = int(time.time() * 1000)
    item: dict[str, Any] = {
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


def update_user_profile(
    user_id: str, username: str, email: str
) -> dict[str, Any]:
    """Update a user's username and email in DynamoDB.

    Returns the full updated item dict after re-fetching from the table.

    Raises:
        ValueError: If the user is not found after the update.
    """
    email_lower = email.strip().lower()
    table = _table()
    try:
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
    except ClientError:
        logger.error("Failed to update profile for user %s", user_id, exc_info=True)
        raise

    updated = get_user_by_id(user_id)
    if not updated:
        raise ValueError("User not found after update")
    return updated


def update_password_hash(user_id: str, password_hash: str) -> None:
    """Replace a user's password hash in DynamoDB.

    Also updates the ``updated_at`` timestamp.
    """
    table = _table()
    try:
        table.update_item(
            Key={"user_id": user_id},
            UpdateExpression="SET password_hash = :ph, #ua = :updated",
            ExpressionAttributeNames={"#ua": "updated_at"},
            ExpressionAttributeValues={
                ":ph": password_hash,
                ":updated": int(time.time() * 1000),
            },
        )
    except ClientError:
        logger.error("Failed to update password for user %s", user_id, exc_info=True)
        raise
