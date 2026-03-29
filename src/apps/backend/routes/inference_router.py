"""POST /inference -- upload an artwork image and receive a forgery detection result.

This route handler is a thin orchestrator that delegates business logic
to ``inference_service``. The pipeline:

1. Validate and parse the uploaded image.
2. Upload raw image to S3 and record metadata in DynamoDB.
3. Split image into patches and upload them.
4. Send patches to the Modal Swin model for prediction.
5. Optionally query Bedrock RAG for an explanation.
6. Return the aggregated result.
"""

from __future__ import annotations

import logging
import uuid
from io import BytesIO
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from PIL import Image
from pydantic import BaseModel

from src.apps.backend.deps.auth import get_current_user_id
from src.apps.backend.services import inference_service
from src.apps.backend.validation import (
    ARTIST_NAME_MAX,
    ARTWORK_NAME_MAX,
    MAX_UPLOAD_SIZE_BYTES,
    sanitize_filename,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["inference"])


# ---------------------------------------------------------------------------
# Pydantic response model
# ---------------------------------------------------------------------------

class PatchResult(BaseModel):
    """Per-patch bounding box and authenticity probability (0–1)."""

    x: int
    y: int
    w: int
    h: int
    prob: float


class InferenceResponse(BaseModel):
    """Response from a successful POST /inference call.

    Attributes:
        inference_id: Unique identifier for this inference record.
        prediction:   1 = authentic, 0 = forgery.
        score:        Mean patch probability of authenticity (0-1).
        explanation:  RAG-generated explanation, or None.
        image_url:    Presigned S3 GET URL for the uploaded image, or None.
        image_width:  Original image width in pixels.
        image_height: Original image height in pixels.
        patch_data:   Per-patch boxes and probabilities (aligned with patches_info order).
    """

    inference_id: str
    prediction: int
    score: float
    confidence_percent: float
    explanation: Optional[str] = None
    image_url: Optional[str] = None
    image_width: int = 0
    image_height: int = 0
    patch_data: Optional[List[PatchResult]] = None


# ---------------------------------------------------------------------------
# Route handler
# ---------------------------------------------------------------------------

@router.post("/inference", response_model=InferenceResponse)
async def infer(
    file: UploadFile = File(...),
    artist_name: str = Form(...),
    artwork_name: str = Form(...),
    user_id: str = Depends(get_current_user_id),
) -> InferenceResponse:
    """Accept an artwork image and return a forgery detection result.

    Validates the upload, orchestrates the inference pipeline via
    ``inference_service``, and returns the prediction with an optional
    RAG explanation.

    Raises:
        HTTPException 400: If the file is empty, not a valid image,
                           or required form fields are blank.
        HTTPException 500: If model inference or a critical AWS operation fails.
    """
    # --- Input validation ---
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file upload.")

    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum upload size is {MAX_UPLOAD_SIZE_BYTES // (1024*1024)} MB.",
        )

    artist_name = artist_name.strip()[:ARTIST_NAME_MAX]
    artwork_name = artwork_name.strip()[:ARTWORK_NAME_MAX]
    if not artist_name or not artwork_name:
        raise HTTPException(
            status_code=400,
            detail="Both artist_name and artwork_name are required.",
        )

    try:
        img = Image.open(BytesIO(content)).convert("RGB")
    except Exception:
        raise HTTPException(
            status_code=400, detail="The uploaded file is not a valid image."
        )

    # --- Generate IDs ---
    inference_id = str(uuid.uuid4())
    image_id = str(uuid.uuid4())
    filename = sanitize_filename(file.filename or f"{image_id}.jpg")
    content_type = file.content_type or "application/octet-stream"
    w, h = img.size

    # --- Pipeline ---
    try:
        raw_s3_uri = inference_service.upload_raw_image(
            content, image_id, filename, content_type,
        )

        inference_service.save_image_metadata(
            image_id, filename, raw_s3_uri, w, h, artist_name, artwork_name,
        )

        inference_service.create_inference_record(
            inference_id, image_id, user_id, filename,
            raw_s3_uri, artist_name, artwork_name, len(content),
        )

        patches_info = inference_service.create_and_upload_patches(img, image_id)

    except EnvironmentError as exc:
        logger.error("Missing configuration: %s", exc)
        raise HTTPException(
            status_code=500, detail="Server configuration error. Please contact support."
        )
    except Exception as exc:
        logger.error("Failed to prepare inference: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail="Failed to process the uploaded image."
        )

    # --- Modal inference ---
    patch_s3_uris = [p["patch_path"] for p in patches_info]
    try:
        modal_result = inference_service.run_modal_inference(patch_s3_uris)
    except RuntimeError:
        inference_service.mark_inference_failed(
            inference_id, "Model inference service is temporarily unavailable."
        )
        raise HTTPException(
            status_code=500,
            detail="The forgery detection model is temporarily unavailable. Please try again later.",
        )

    score = modal_result["mean_prob"]
    prediction = modal_result["prediction"]

    # --- Store results and generate explanation ---
    inference_service.save_patch_predictions(
        patches_info, modal_result["patch_probs"], modal_result["patch_preds"],
    )

    explanation = inference_service.query_rag_explanation(
        prediction,
        score,
        raw_s3_uri=raw_s3_uri,
        patches_info=patches_info,
        patch_probs=modal_result["patch_probs"],
        artist_name=artist_name,
        artwork_name=artwork_name,
    )

    patch_data = [
        PatchResult(
            x=int(p["patch_x"]),
            y=int(p["patch_y"]),
            w=int(p["patch_width"]),
            h=int(p["patch_height"]),
            prob=float(prob),
        )
        for p, prob in zip(patches_info, modal_result["patch_probs"])
    ]

    patch_rows_for_ddb = [
        {"x": pr.x, "y": pr.y, "w": pr.w, "h": pr.h, "prob": pr.prob} for pr in patch_data
    ]
    inference_service.finalize_inference(
        inference_id,
        score,
        prediction,
        explanation,
        image_width=w,
        image_height=h,
        patch_data=patch_rows_for_ddb,
    )

    image_url = inference_service.generate_image_url(raw_s3_uri)

    return InferenceResponse(
        inference_id=inference_id,
        prediction=prediction,
        score=score,
        confidence_percent=abs(score - 0.5) / 0.5 * 100.0,
        explanation=explanation,
        image_url=image_url,
        image_width=w,
        image_height=h,
        patch_data=patch_data,
    )
