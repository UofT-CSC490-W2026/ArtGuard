"""Training and evaluation routes.

Endpoints:
    POST /train     -- spawn a Modal training run, return run_id immediately.
    POST /evaluate  -- spawn a Modal evaluation run, return immediately.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.apps.backend.config import (
    DDB_RUNS_TABLE,
    RunStatus,
    get_table,
)
from src.apps.data_pipeline.schemas import RunRecord

logger = logging.getLogger(__name__)

router = APIRouter(tags=["training"])


# ---------------------------------------------------------------------------
# /train
# ---------------------------------------------------------------------------

from src.apps.backend.validation import ModelVariant


class TrainRequest(BaseModel):
    """Request body for POST /train.

    Attributes:
        variant: Swin model variant -- ``"tiny"`` (28M params) or ``"base"``
                 (88M params).
        config:  Optional dict of hyperparameter overrides merged on top of
                 ``DEFAULT_CONFIG`` in ``train.py``.
    """

    variant: ModelVariant
    config: Optional[dict] = None


class TrainResponse(BaseModel):
    """Response from a successful POST /train call.

    Attributes:
        run_id:  UUID to track this run (stored in DynamoDB RunRecord).
        variant: Echoed back from the request.
        status:  Always ``"started"`` on success.
    """

    run_id: str
    variant: str
    status: str


@router.post("/train", response_model=TrainResponse)
async def start_training(body: TrainRequest) -> TrainResponse:
    """Kick off a Modal training run for the specified Swin variant.

    Writes a RunRecord to DynamoDB with status="running", then spawns the
    Modal Function asynchronously and returns immediately.

    Raises:
        HTTPException 400: If variant is not ``"tiny"`` or ``"base"``.
        HTTPException 500: If required config is missing or Modal spawn fails.
    """
    from src.apps.train.train import DEFAULT_CONFIG, train_swin_base, train_swin_tiny

    try:
        runs_table = get_table(DDB_RUNS_TABLE)
    except EnvironmentError:
        raise HTTPException(
            status_code=500,
            detail="Training service is not properly configured.",
        )

    config = {**DEFAULT_CONFIG, **(body.config or {})}

    run = RunRecord()
    run.status = RunStatus.RUNNING.value
    run.modal_volume_path = f"/checkpoints/{body.variant}"

    runs_table.put_item(Item=asdict(run))

    try:
        if body.variant == "tiny":
            train_swin_tiny.spawn(config)
        else:
            train_swin_base.spawn(config)
    except Exception as exc:
        logger.error("Failed to spawn Modal training run: %s", exc, exc_info=True)
        runs_table.update_item(
            Key={"run_id": run.run_id},
            UpdateExpression="SET #s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": RunStatus.FAILED.value},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to start the training run. Please try again later.",
        )

    return TrainResponse(run_id=run.run_id, variant=body.variant, status="started")


# ---------------------------------------------------------------------------
# /evaluate
# ---------------------------------------------------------------------------

class EvaluateRequest(BaseModel):
    """Request body for POST /evaluate.

    Attributes:
        variant:    Swin model variant -- ``"tiny"`` or ``"base"``.
        checkpoint: Full path inside the Modal Volume, e.g.
                    ``/checkpoints/tiny/best.pt``.
    """

    variant: ModelVariant
    checkpoint: str = Field(..., pattern=r"^/checkpoints/.+\.pt$", max_length=200)


class EvaluateResponse(BaseModel):
    """Response from a successful POST /evaluate call.

    Attributes:
        variant:    Echoed back from the request.
        checkpoint: Echoed back from the request.
        status:     Always ``"started"`` on success.
    """

    variant: str
    checkpoint: str
    status: str


@router.post("/evaluate", response_model=EvaluateResponse)
async def start_evaluation(body: EvaluateRequest) -> EvaluateResponse:
    """Kick off a Modal evaluation run for the specified checkpoint.

    Spawns the Modal evaluate Function asynchronously and returns immediately.

    Raises:
        HTTPException 400: If variant is invalid or checkpoint path is malformed.
        HTTPException 500: If the Modal spawn fails.
    """
    from src.apps.train.evaluate import evaluate

    try:
        evaluate.spawn(variant=body.variant, checkpoint_path=body.checkpoint)
    except Exception as exc:
        logger.error("Failed to spawn Modal evaluation: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to start the evaluation run. Please try again later.",
        )

    return EvaluateResponse(
        variant=body.variant,
        checkpoint=body.checkpoint,
        status="started",
    )
