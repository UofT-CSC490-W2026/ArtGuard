"""Inference history routes: list, fetch, and delete inference records.

All endpoints require JWT authentication and scope results to the
authenticated user via the UserInferencesIndex GSI.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from starlette.responses import Response

from src.apps.backend.config import (
    DDB_INFERENCES_TABLE,
    USER_INFERENCES_INDEX,
    get_table,
    paginated_query,
    paginated_query_count,
    s3_client,
)
from src.apps.backend.deps.auth import get_current_user_id
from src.apps.backend.routes.inference_router import PatchResult
from src.apps.backend.services.s3_presign import presigned_get_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inferences", tags=["inferences"])

PRESIGN_EXPIRES = int(os.getenv("S3_INFERENCE_PRESIGN_EXPIRES", "86400"))


# ---------------------------------------------------------------------------
# Cursor-based pagination helpers
# ---------------------------------------------------------------------------

def _normalize_key_for_json(key: dict[str, Any]) -> dict[str, Any]:
    """Convert Decimal values in a DynamoDB key to ints for JSON serialization.

    >>> _normalize_key_for_json({"id": "abc", "ts": Decimal("123")})
    {'id': 'abc', 'ts': 123}
    """
    return {k: int(v) if isinstance(v, Decimal) else v for k, v in key.items()}


def _encode_cursor(key: dict[str, Any]) -> str:
    """Encode a DynamoDB LastEvaluatedKey dict into a URL-safe base64 cursor string.

    >>> _encode_cursor({"inference_id": "abc"})
    'eyJpbmZlcmVuY2VfaWQiOiJhYmMifQ'
    """
    normalized = _normalize_key_for_json(key)
    raw = json.dumps(normalized, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> dict[str, Any]:
    """Decode a URL-safe base64 cursor string back to a DynamoDB ExclusiveStartKey dict.

    >>> _decode_cursor('eyJpbmZlcmVuY2VfaWQiOiJhYmMifQ')
    {'inference_id': 'abc'}
    """
    pad = "=" * (-len(cursor) % 4)
    raw = base64.urlsafe_b64decode(cursor + pad)
    return json.loads(raw.decode())


def _float_score(raw: Any) -> float:
    """Safely convert a DynamoDB score value (Decimal, None, or numeric) to float.

    >>> _float_score(Decimal("0.85"))
    0.85
    >>> _float_score(None)
    0.0
    """
    if isinstance(raw, Decimal):
        return float(raw)
    if raw is None:
        return 0.0
    return float(raw)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class InferenceStatsResponse(BaseModel):
    """Response for GET /inferences/stats."""

    count: int


class InferenceListItem(BaseModel):
    """A single inference record returned to the client.

    Attributes:
        inference_id:     Unique inference identifier.
        created_at:       Unix timestamp in milliseconds.
        score:            Mean patch probability of authenticity (0-1).
        prediction:       1 = authentic, 0 = forgery, -1 = pending.
        explanation:      RAG-generated explanation text, if available.
        inference_status: ``processing``, ``completed``, or ``failed``.
        error_message:    Server error detail when inference_status is failed.
        artist_name:      Artist name provided at upload time.
        artwork_name:     Artwork name provided at upload time.
        image_name:       Original filename of the uploaded image.
        file_size:        Upload file size in bytes.
        image_url:        Presigned S3 GET URL for the raw uploaded image.
        image_width:      Original image width in pixels when patch data was stored.
        image_height:     Original image height in pixels when patch data was stored.
        patch_data:       Per-patch authenticity heatmap data when stored on completion.
    """

    inference_id: str
    created_at: int = Field(..., ge=0)
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    prediction: Optional[int] = Field(default=None, ge=-1, le=1)
    explanation: Optional[str] = None
    inference_status: Optional[str] = None
    error_message: Optional[str] = None
    artist_name: str
    artwork_name: str
    image_name: str
    file_size: int = Field(default=0, ge=0)
    image_url: str
    image_width: int = Field(default=0, ge=0)
    image_height: int = Field(default=0, ge=0)
    patch_data: Optional[list[PatchResult]] = None


class InferenceListResponse(BaseModel):
    """Paginated list of inference records."""

    items: list[InferenceListItem]
    next_cursor: Optional[str] = None


class DeleteAllResponse(BaseModel):
    """Response for DELETE /inferences (bulk delete)."""

    deleted: int


# ---------------------------------------------------------------------------
# DynamoDB → Pydantic mapping
# ---------------------------------------------------------------------------

def _item_to_list_item(item: dict[str, Any], s3) -> InferenceListItem:
    """Convert a raw DynamoDB inference item to an InferenceListItem response model.

    Generates a presigned S3 URL for the image and coerces DynamoDB types
    (Decimal, missing keys) to the expected Python types.
    """
    uri = item.get("image_path") or ""
    url = ""
    if uri:
        try:
            url = presigned_get_url(s3, uri, PRESIGN_EXPIRES)
        except Exception:
            logger.warning("Failed to presign URL for %s", uri, exc_info=True)

    pred_raw = item.get("prediction")
    prediction: Optional[int] = None
    if pred_raw is not None:
        try:
            prediction = int(pred_raw)
        except (TypeError, ValueError):
            prediction = None

    status_raw = item.get("inference_status")
    inference_status: Optional[str] = str(status_raw) if status_raw is not None else None

    iw = int(item.get("image_width") or 0)
    ih = int(item.get("image_height") or 0)
    patch_data: Optional[list[PatchResult]] = None
    raw_patches = item.get("patch_data")
    if isinstance(raw_patches, list) and len(raw_patches) > 0:
        parsed: list[PatchResult] = []
        for p in raw_patches:
            if not isinstance(p, dict):
                continue
            try:
                prob_raw = p.get("prob")
                prob_f = float(prob_raw) if isinstance(prob_raw, Decimal) else float(prob_raw)
                parsed.append(
                    PatchResult(
                        x=int(p["x"]),
                        y=int(p["y"]),
                        w=int(p["w"]),
                        h=int(p["h"]),
                        prob=prob_f,
                    )
                )
            except (TypeError, KeyError, ValueError):
                continue
        if parsed:
            patch_data = parsed

    return InferenceListItem(
        inference_id=item["inference_id"],
        created_at=int(item["created_at"]),
        score=_float_score(item.get("score")),
        confidence_percent=abs(_float_score(item.get("score")) - 0.5) / 0.5 * 100.0,
        prediction=prediction,
        explanation=item.get("explanation"),
        inference_status=inference_status,
        error_message=item.get("error_message"),
        artist_name=str(item.get("artist_name") or ""),
        artwork_name=str(item.get("artwork_name") or ""),
        image_name=str(item.get("image_name") or ""),
        file_size=int(item.get("file_size") or 0),
        image_url=url,
        image_width=iw,
        image_height=ih,
        patch_data=patch_data,
    )


# ---------------------------------------------------------------------------
# Table accessor
# ---------------------------------------------------------------------------

def _inference_table():
    """Return the DynamoDB Table resource for inference records.

    Raises:
        HTTPException 500: If the DDB_INFERENCES_TABLE env var is not set.
    """
    try:
        return get_table(DDB_INFERENCES_TABLE)
    except EnvironmentError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Inference service is not properly configured.",
        )


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

@router.get("/stats", response_model=InferenceStatsResponse)
async def inference_stats(
    user_id: str = Depends(get_current_user_id),
) -> InferenceStatsResponse:
    """Return the total number of inference records for the authenticated user."""
    table = _inference_table()
    total = paginated_query_count(
        table,
        IndexName=USER_INFERENCES_INDEX,
        KeyConditionExpression="user_id = :u",
        ExpressionAttributeValues={":u": user_id},
    )
    return InferenceStatsResponse(count=total)


@router.get("", response_model=InferenceListResponse)
async def list_inferences(
    user_id: str = Depends(get_current_user_id),
    limit: int = Query(50, ge=1, le=100),
    cursor: Optional[str] = Query(None, description="Pagination cursor from previous response"),
) -> InferenceListResponse:
    """Return a paginated list of the user's inference records (newest first).

    Pass the ``next_cursor`` value from a previous response as the ``cursor``
    query parameter to fetch the next page.
    """
    table = _inference_table()
    s3 = s3_client()
    kwargs: dict[str, Any] = {
        "IndexName": USER_INFERENCES_INDEX,
        "KeyConditionExpression": "user_id = :u",
        "ExpressionAttributeValues": {":u": user_id},
        "Limit": limit,
        "ScanIndexForward": False,
    }
    if cursor:
        try:
            kwargs["ExclusiveStartKey"] = _decode_cursor(cursor)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid pagination cursor.",
            )

    resp = table.query(**kwargs)
    items = [_item_to_list_item(it, s3) for it in resp.get("Items", [])]
    next_c: Optional[str] = None
    lek = resp.get("LastEvaluatedKey")
    if lek:
        next_c = _encode_cursor(lek)
    return InferenceListResponse(items=items, next_cursor=next_c)


@router.delete("", response_model=DeleteAllResponse)
async def delete_all_inferences(
    user_id: str = Depends(get_current_user_id),
) -> DeleteAllResponse:
    """Delete all inference records belonging to the authenticated user.

    Returns the total number of records deleted.
    """
    table = _inference_table()
    all_items = paginated_query(
        table,
        IndexName=USER_INFERENCES_INDEX,
        KeyConditionExpression="user_id = :u",
        ExpressionAttributeValues={":u": user_id},
        ProjectionExpression="inference_id",
    )
    with table.batch_writer() as batch:
        for it in all_items:
            batch.delete_item(Key={"inference_id": it["inference_id"]})
    return DeleteAllResponse(deleted=len(all_items))


@router.get("/{inference_id}", response_model=InferenceListItem)
async def get_inference(
    inference_id: str,
    user_id: str = Depends(get_current_user_id),
) -> InferenceListItem:
    """Return a single inference record by ID.

    Raises HTTP 404 if the record does not exist or belongs to a different user.
    """
    table = _inference_table()
    s3 = s3_client()
    resp = table.get_item(Key={"inference_id": inference_id})
    item = resp.get("Item")
    if not item or item.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inference not found.",
        )
    return _item_to_list_item(item, s3)


@router.delete("/{inference_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inference(
    inference_id: str,
    user_id: str = Depends(get_current_user_id),
) -> Response:
    """Delete a single inference record by ID.

    Raises HTTP 404 if the record does not exist or belongs to a different user.
    """
    table = _inference_table()
    resp = table.get_item(Key={"inference_id": inference_id})
    item = resp.get("Item")
    if not item or item.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inference not found.",
        )
    table.delete_item(Key={"inference_id": inference_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
