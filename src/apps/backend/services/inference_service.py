"""Business logic for the /inference endpoint.

Separates AWS operations, Modal calls, and RAG queries from the HTTP
route handler so each concern can be tested and maintained independently.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from decimal import Decimal
from io import BytesIO
from typing import Optional

import boto3
from PIL import Image

from src.apps.backend.config import (
    DDB_IMAGES_TABLE,
    DDB_INFERENCES_TABLE,
    DDB_PATCHES_TABLE,
    InferenceStatus,
    S3_IMAGES_PROCESSED_BUCKET,
    S3_IMAGES_RAW_BUCKET,
    bedrock_model_arn,
    get_region,
    get_table,
    require_env,
    s3_client,
)
from src.apps.backend.logging_config import emit_metric
from src.apps.backend.prompts import rag_explanation_prompt
from src.apps.backend.services.s3_presign import presigned_get_url
from src.apps.backend.validation import (
    ARTIST_NAME_MAX,
    ARTWORK_NAME_MAX,
    EXPLANATION_MAX,
    IMAGE_NAME_MAX,
    clamp_score,
    truncate,
    validate_prediction,
)
from src.apps.data_pipeline.preprocess import process_image_to_patches

logger = logging.getLogger(__name__)


def upload_raw_image(
    content: bytes,
    image_id: str,
    filename: str,
    content_type: str,
) -> str:
    """Upload the raw user image to S3 and return its s3:// URI.

    Args:
        content:      Raw file bytes.
        image_id:     UUID for this image.
        filename:     Original filename.
        content_type: MIME type of the upload.

    Returns:
        The ``s3://bucket/key`` URI of the uploaded object.

    Raises:
        EnvironmentError: If the S3_IMAGES_RAW_BUCKET env var is not set.
        botocore.exceptions.ClientError: If the S3 upload fails.
    """
    raw_bucket = require_env(S3_IMAGES_RAW_BUCKET)
    raw_prefix = os.getenv("S3_RAW_PREFIX", "inference")
    raw_key = f"{raw_prefix}/{image_id}/{filename}"

    s3 = s3_client()
    s3.put_object(
        Bucket=raw_bucket,
        Key=raw_key,
        Body=content,
        ContentType=content_type,
        ServerSideEncryption="AES256",
    )
    return f"s3://{raw_bucket}/{raw_key}"


def save_image_metadata(
    image_id: str,
    filename: str,
    raw_s3_uri: str,
    width: int,
    height: int,
    artist_name: str,
    artwork_name: str,
) -> None:
    """Write image metadata to the DynamoDB images table.

    Args:
        image_id:     UUID for this image.
        filename:     Original filename.
        raw_s3_uri:   S3 URI of the raw image.
        width:        Image width in pixels.
        height:       Image height in pixels.
        artist_name:  Artist name from the upload form.
        artwork_name: Artwork name from the upload form.

    Raises:
        EnvironmentError: If the DDB_IMAGES_TABLE env var is not set.
    """
    img_table = get_table(DDB_IMAGES_TABLE)
    img_table.put_item(Item={
        "image_id": image_id,
        "created_at": _now_ms(),
        "image_name": truncate(filename, IMAGE_NAME_MAX),
        "image_path": raw_s3_uri,
        "image_width": max(0, width),
        "image_height": max(0, height),
        "artist_name": truncate(artist_name, ARTIST_NAME_MAX),
        "title": truncate(artwork_name, ARTWORK_NAME_MAX),
    })


def create_inference_record(
    inference_id: str,
    image_id: str,
    user_id: str,
    filename: str,
    raw_s3_uri: str,
    artist_name: str,
    artwork_name: str,
    file_size: int,
) -> None:
    """Write an initial inference record to DynamoDB with status=processing.

    Args:
        inference_id: UUID for this inference.
        image_id:     UUID of the associated image.
        user_id:      Authenticated user's ID.
        filename:     Original filename.
        raw_s3_uri:   S3 URI of the raw image.
        artist_name:  Artist name from the upload form.
        artwork_name: Artwork name from the upload form.
        file_size:    Upload file size in bytes.

    Raises:
        EnvironmentError: If the DDB_INFERENCES_TABLE env var is not set.
    """
    inference_table = get_table(DDB_INFERENCES_TABLE)
    ttl_days = int(os.getenv("INFERENCE_TTL_DAYS", "90"))
    ttl_ts = int(time.time()) + ttl_days * 86400
    created_at = _now_ms()

    inference_table.put_item(Item={
        "inference_id": inference_id,
        "image_id": image_id,
        "user_id": user_id,
        "created_at": created_at,
        "image_name": truncate(filename, IMAGE_NAME_MAX),
        "image_path": raw_s3_uri,
        "score": Decimal("0.0"),
        "prediction": -1,
        "inference_status": InferenceStatus.PROCESSING.value,
        "artist_name": truncate(artist_name, ARTIST_NAME_MAX),
        "artwork_name": truncate(artwork_name, ARTWORK_NAME_MAX),
        "title": truncate(artwork_name, ARTWORK_NAME_MAX),
        "file_size": max(0, file_size),
        "ttl": ttl_ts,
    })


def create_and_upload_patches(
    img: Image.Image,
    image_id: str,
) -> list[dict]:
    """Split an image into patches, upload to S3, and write patch metadata to DynamoDB.

    Args:
        img:      PIL Image (already converted to RGB).
        image_id: UUID of the parent image.

    Returns:
        List of patch metadata dicts from ``process_image_to_patches``.

    Raises:
        EnvironmentError: If required env vars are not set.
    """
    processed_bucket = require_env(S3_IMAGES_PROCESSED_BUCKET)
    processed_prefix = os.getenv("S3_PROCESSED_PREFIX", "inference")

    patches_info = process_image_to_patches(
        img=img,
        image_id=image_id,
        processed_bucket=processed_bucket,
        processed_prefix=processed_prefix,
        s3_client=s3_client(),
    )

    patch_table = get_table(DDB_PATCHES_TABLE)
    created_at = _now_ms()
    for p in patches_info:
        patch_table.put_item(Item={
            "patch_id": p["patch_id"],
            "image_id": image_id,
            "patch_type": p["patch_type"],
            "patch_path": p["patch_path"],
            "patch_x": int(p["patch_x"]),
            "patch_y": int(p["patch_y"]),
            "patch_width": int(p["patch_width"]),
            "patch_height": int(p["patch_height"]),
            "created_at": created_at,
        })

    return patches_info


def run_modal_inference(patch_s3_uris: list[str]) -> dict:
    """Send patches to the Modal-hosted Swin model and return the result.

    Args:
        patch_s3_uris: List of ``s3://`` URIs for patch images.

    Returns:
        Dict with ``mean_prob``, ``prediction``, ``patch_probs``, ``patch_preds``.

    Raises:
        RuntimeError: If the Modal call fails for any reason.
    """
    start = time.perf_counter()
    try:
        import modal

        predict_patches = modal.Function.from_name(
            "artguard-inference", "predict_patches"
        )
        result = predict_patches.remote(
            patch_s3_uris=patch_s3_uris,
            variant="tiny",
            checkpoint_name="best.pt",
        )
        duration = time.perf_counter() - start
        logger.info(
            "Modal inference completed in %.2fs: prediction=%s score=%.4f",
            duration, result.get("prediction"), result.get("mean_prob", 0),
        )
        emit_metric("ArtGuard", "InferenceLatency", duration, "Seconds",
                     {"Endpoint": "inference"})
        emit_metric("ArtGuard", "InferenceSuccess", 1, "Count",
                     {"Endpoint": "inference"})
        return result
    except Exception as exc:
        duration = time.perf_counter() - start
        logger.error("Modal inference failed after %.2fs: %s", duration, exc, exc_info=True)
        emit_metric("ArtGuard", "InferenceError", 1, "Count",
                     {"Endpoint": "inference"})
        raise RuntimeError(f"Model inference failed: {exc}") from exc


def save_patch_predictions(
    patches_info: list[dict],
    patch_probs: list[float],
    patch_preds: list[int],
) -> None:
    """Write per-patch prediction scores to DynamoDB.

    Args:
        patches_info: Patch metadata dicts (must contain ``patch_id``).
        patch_probs:  Per-patch probability values.
        patch_preds:  Per-patch 0/1 predictions.
    """
    patch_table = get_table(DDB_PATCHES_TABLE)
    for p_info, prob, pred in zip(patches_info, patch_probs, patch_preds):
        try:
            patch_table.update_item(
                Key={"patch_id": p_info["patch_id"]},
                UpdateExpression="SET score = :s, prediction = :p",
                ExpressionAttributeValues={":s": Decimal(str(prob)), ":p": pred},
            )
        except Exception:
            logger.warning(
                "Failed to save prediction for patch %s", p_info["patch_id"],
                exc_info=True,
            )


def query_rag_explanation(prediction: int, score: float) -> Optional[str]:
    """Query the Bedrock Knowledge Base for an explanation of the inference result.

    Returns None if no Knowledge Base is configured. Returns a fallback
    message if the Bedrock call fails (does not raise).

    Args:
        prediction: 1 = authentic, 0 = forgery.
        score:      Mean patch probability (0-1).

    Returns:
        Explanation text, or None if KB is not configured.
    """
    knowledge_base_id = os.getenv("KNOWLEDGE_BASE_ID")
    if not knowledge_base_id:
        return None

    rag_prompt = rag_explanation_prompt(prediction, score)

    start = time.perf_counter()
    try:
        region = get_region()
        bedrock = boto3.client("bedrock-agent-runtime", region_name=region)
        rag_resp = bedrock.retrieve_and_generate(
            input={"text": rag_prompt},
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": knowledge_base_id,
                    "modelArn": bedrock_model_arn(),
                },
            },
        )
        duration = time.perf_counter() - start
        logger.info("RAG explanation generated in %.2fs", duration)
        emit_metric("ArtGuard", "RAGLatency", duration, "Seconds",
                     {"Endpoint": "rag"})
        return rag_resp.get("output", {}).get("text", "")
    except Exception:
        duration = time.perf_counter() - start
        logger.warning("Bedrock RAG query failed after %.2fs", duration, exc_info=True)
        emit_metric("ArtGuard", "RAGError", 1, "Count", {"Endpoint": "rag"})
        return "Explanation unavailable at this time."


def finalize_inference(
    inference_id: str,
    score: float,
    prediction: int,
    explanation: Optional[str],
) -> None:
    """Update the inference record in DynamoDB with final results.

    Args:
        inference_id: UUID of the inference record.
        score:        Final mean probability score.
        prediction:   Final 0/1 prediction.
        explanation:  RAG explanation text, or None.
    """
    inference_table = get_table(DDB_INFERENCES_TABLE)
    clamped_score = clamp_score(score)
    valid_prediction = validate_prediction(prediction)

    update_expr = "SET score = :s, prediction = :p, inference_status = :ist"
    expr_values: dict = {
        ":s": Decimal(str(clamped_score)),
        ":p": valid_prediction,
        ":ist": InferenceStatus.COMPLETED.value,
    }
    if explanation is not None:
        update_expr += ", explanation = :e"
        expr_values[":e"] = truncate(explanation, EXPLANATION_MAX)

    try:
        inference_table.update_item(
            Key={"inference_id": inference_id},
            UpdateExpression=update_expr + " REMOVE error_message",
            ExpressionAttributeValues=expr_values,
        )
    except Exception:
        logger.error(
            "Failed to finalize inference %s", inference_id, exc_info=True
        )


def mark_inference_failed(inference_id: str, error_message: str) -> None:
    """Mark an inference record as failed in DynamoDB.

    Args:
        inference_id:  UUID of the inference record.
        error_message: Error detail to store (truncated to 3500 chars).
    """
    try:
        inference_table = get_table(DDB_INFERENCES_TABLE)
        inference_table.update_item(
            Key={"inference_id": inference_id},
            UpdateExpression="SET inference_status = :st, error_message = :em",
            ExpressionAttributeValues={
                ":st": InferenceStatus.FAILED.value,
                ":em": error_message[:3500],
            },
        )
    except Exception:
        logger.error(
            "Failed to mark inference %s as failed", inference_id, exc_info=True
        )


def generate_image_url(raw_s3_uri: str) -> Optional[str]:
    """Generate a presigned S3 GET URL for the uploaded image.

    Returns None if presigning fails (logged as a warning).

    Args:
        raw_s3_uri: The ``s3://bucket/key`` URI of the raw image.

    Returns:
        A presigned HTTPS URL, or None.
    """
    presign_expires = int(os.getenv("S3_INFERENCE_PRESIGN_EXPIRES", "86400"))
    try:
        return presigned_get_url(s3_client(), raw_s3_uri, presign_expires)
    except Exception:
        logger.warning("Failed to generate presigned URL for %s", raw_s3_uri, exc_info=True)
        return None


def _now_ms() -> int:
    """Return current time as Unix milliseconds."""
    return int(time.time() * 1000)
