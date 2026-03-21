"""List, fetch, and delete inference records for the authenticated user."""

from __future__ import annotations

import base64
import json
import os
from decimal import Decimal
from typing import Any, Optional

import boto3
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from starlette.responses import Response

from src.apps.backend.deps.auth import get_current_user_id
from src.apps.backend.services.s3_presign import presigned_get_url

router = APIRouter(prefix="/inferences", tags=["inferences"])

PRESIGN_EXPIRES = int(os.getenv("S3_INFERENCE_PRESIGN_EXPIRES", "86400"))


def _inference_table():
    name = os.getenv("DDB_INFERENCES_TABLE")
    if not name:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DDB_INFERENCES_TABLE not configured",
        )
    region = os.getenv("AWS_REGION", "ca-central-1")
    return boto3.resource("dynamodb", region_name=region).Table(name)


def _s3_client():
    return boto3.client("s3", region_name=os.getenv("AWS_REGION", "ca-central-1"))


def _normalize_key_for_json(key: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in key.items():
        if isinstance(v, Decimal):
            out[k] = int(v)
        else:
            out[k] = v
    return out


def _encode_cursor(key: dict[str, Any]) -> str:
    normalized = _normalize_key_for_json(key)
    raw = json.dumps(normalized, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> dict[str, Any]:
    pad = "=" * (-len(cursor) % 4)
    raw = base64.urlsafe_b64decode(cursor + pad)
    return json.loads(raw.decode())


def _float_score(raw: Any) -> float:
    if isinstance(raw, Decimal):
        return float(raw)
    if raw is None:
        return 0.0
    return float(raw)


class InferenceStatsResponse(BaseModel):
    count: int


@router.get("/stats", response_model=InferenceStatsResponse)
async def inference_stats(user_id: str = Depends(get_current_user_id)):
    table = _inference_table()
    total = 0
    eks: Optional[dict[str, Any]] = None
    while True:
        kwargs: dict[str, Any] = {
            "IndexName": "UserInferencesIndex",
            "KeyConditionExpression": "user_id = :u",
            "ExpressionAttributeValues": {":u": user_id},
            "Select": "COUNT",
        }
        if eks:
            kwargs["ExclusiveStartKey"] = eks
        resp = table.query(**kwargs)
        total += int(resp.get("Count", 0))
        eks = resp.get("LastEvaluatedKey")
        if not eks:
            break
    return InferenceStatsResponse(count=total)


class InferenceListItem(BaseModel):
    inference_id: str
    created_at: int
    score: float
    explanation: Optional[str] = None
    artist_name: str
    artwork_name: str
    image_name: str
    file_size: int = 0
    image_url: str


class InferenceListResponse(BaseModel):
    items: list[InferenceListItem]
    next_cursor: Optional[str] = None


def _item_to_list_item(item: dict[str, Any], s3) -> InferenceListItem:
    uri = item.get("image_path") or ""
    url = ""
    if uri:
        try:
            url = presigned_get_url(s3, uri, PRESIGN_EXPIRES)
        except Exception:
            url = ""
    return InferenceListItem(
        inference_id=item["inference_id"],
        created_at=int(item["created_at"]),
        score=_float_score(item.get("score")),
        explanation=item.get("explanation"),
        artist_name=str(item.get("artist_name") or ""),
        artwork_name=str(item.get("artwork_name") or ""),
        image_name=str(item.get("image_name") or ""),
        file_size=int(item.get("file_size") or 0),
        image_url=url,
    )


@router.get("", response_model=InferenceListResponse)
async def list_inferences(
    user_id: str = Depends(get_current_user_id),
    limit: int = Query(50, ge=1, le=100),
    cursor: Optional[str] = Query(None, description="Pagination cursor from previous response"),
):
    table = _inference_table()
    s3 = _s3_client()
    kwargs: dict[str, Any] = {
        "IndexName": "UserInferencesIndex",
        "KeyConditionExpression": "user_id = :u",
        "ExpressionAttributeValues": {":u": user_id},
        "Limit": limit,
        "ScanIndexForward": False,
    }
    if cursor:
        try:
            kwargs["ExclusiveStartKey"] = _decode_cursor(cursor)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid cursor",
            ) from exc
    resp = table.query(**kwargs)
    items = [_item_to_list_item(it, s3) for it in resp.get("Items", [])]
    next_c: Optional[str] = None
    lek = resp.get("LastEvaluatedKey")
    if lek:
        next_c = _encode_cursor(lek)
    return InferenceListResponse(items=items, next_cursor=next_c)


class DeleteAllResponse(BaseModel):
    deleted: int


@router.delete("", response_model=DeleteAllResponse)
async def delete_all_inferences(user_id: str = Depends(get_current_user_id)):
    table = _inference_table()
    ids: list[str] = []
    eks: Optional[dict[str, Any]] = None
    while True:
        kwargs: dict[str, Any] = {
            "IndexName": "UserInferencesIndex",
            "KeyConditionExpression": "user_id = :u",
            "ExpressionAttributeValues": {":u": user_id},
            "ProjectionExpression": "inference_id",
        }
        if eks:
            kwargs["ExclusiveStartKey"] = eks
        resp = table.query(**kwargs)
        for it in resp.get("Items", []):
            ids.append(it["inference_id"])
        eks = resp.get("LastEvaluatedKey")
        if not eks:
            break
    with table.batch_writer() as batch:
        for iid in ids:
            batch.delete_item(Key={"inference_id": iid})
    return DeleteAllResponse(deleted=len(ids))


@router.get("/{inference_id}", response_model=InferenceListItem)
async def get_inference(inference_id: str, user_id: str = Depends(get_current_user_id)):
    table = _inference_table()
    s3 = _s3_client()
    resp = table.get_item(Key={"inference_id": inference_id})
    item = resp.get("Item")
    if not item or item.get("user_id") != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inference not found")
    return _item_to_list_item(item, s3)


@router.delete("/{inference_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inference(inference_id: str, user_id: str = Depends(get_current_user_id)):
    table = _inference_table()
    resp = table.get_item(Key={"inference_id": inference_id})
    item = resp.get("Item")
    if not item or item.get("user_id") != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inference not found")
    table.delete_item(Key={"inference_id": inference_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
