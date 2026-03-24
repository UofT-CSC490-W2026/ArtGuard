"""
routes/train.py — Training and evaluation endpoints.

Registered in main.py via:
    from src.apps.backend.routes.train import router as train_router
    app.include_router(train_router)

Endpoints:
    POST /train     — spawn a Modal training run, returns run_id immediately
    POST /evaluate  — spawn a Modal evaluation run, returns results path immediately
"""

from __future__ import annotations

import json
import os
from typing import Optional

import boto3
import modal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.apps.data_pipeline.schemas import RunRecord
from src.apps.train.config import DEFAULT_CONFIG, MODAL_EVAL_APP, MODAL_TRAINING_APP

router = APIRouter()


def _ensure_modal_credentials() -> bool:
    """
    Modal's client uses MODAL_TOKEN_ID + MODAL_TOKEN_SECRET (see Modal docs).
    ECS injects MODAL_API_KEY from Secrets Manager — accept JSON or two-line text.
    """
    if os.environ.get("MODAL_TOKEN_ID") and os.environ.get("MODAL_TOKEN_SECRET"):
        return True
    raw = (os.environ.get("MODAL_API_KEY") or "").strip()
    if not raw:
        return False
    if raw.startswith("{"):
        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            return False
        tid = d.get("token_id")
        sec = d.get("token_secret")
        if tid and sec:
            os.environ["MODAL_TOKEN_ID"] = str(tid)
            os.environ["MODAL_TOKEN_SECRET"] = str(sec)
            return True
        # Legacy doc shape: {"api_key": "..."} — not usable without id/secret split
        return False
    if "\n" in raw:
        first, rest = raw.split("\n", 1)
        if first.strip() and rest.strip():
            os.environ["MODAL_TOKEN_ID"] = first.strip()
            os.environ["MODAL_TOKEN_SECRET"] = rest.strip()
            return True
    return bool(os.environ.get("MODAL_TOKEN_ID") and os.environ.get("MODAL_TOKEN_SECRET"))


# ---------------------------------------------------------------------------
# /train
# ---------------------------------------------------------------------------

class TrainRequest(BaseModel):
    variant: str                    # "tiny" | "base"
    config: Optional[dict] = None   # overrides DEFAULT_CONFIG; omit to use defaults


class TrainResponse(BaseModel):
    run_id: str
    variant: str
    status: str                     # always "started" on success


@router.post("/train", response_model=TrainResponse)
async def start_training(body: TrainRequest):
    """
    Kick off a Modal training run for the specified Swin variant.

    - Writes a RunRecord to DynamoDB with status="running".
    - Spawns the Modal Function asynchronously and returns immediately.
    - The Modal run writes checkpoints to the artguard-checkpoints Volume.

    Request body:
        variant : "tiny" or "base"
        config  : optional dict of hyperparameter overrides (see DEFAULT_CONFIG
                  in train.py for available keys)

    Response:
        run_id  : UUID to track this run (stored in DynamoDB RunRecord)
        variant : echoed back
        status  : "started"
    """
    if body.variant not in ("tiny", "base"):
        raise HTTPException(
            status_code=400,
            detail=f"variant must be 'tiny' or 'base', got '{body.variant}'",
        )

    region          = os.getenv("AWS_REGION")
    runs_table_name = os.getenv("DDB_RUNS_TABLE")

    if not runs_table_name:
        raise HTTPException(status_code=500, detail="DDB_RUNS_TABLE not configured")

    # Merge caller config with defaults
    config = {**DEFAULT_CONFIG, **(body.config or {})}

    run = RunRecord(
        status="running",
        modal_volume_path=f"/checkpoints/{body.variant}",
    )

    ddb        = boto3.resource("dynamodb", region_name=region)
    runs_table = ddb.Table(runs_table_name)
    runs_table.put_item(Item=run.to_dynamo_item())

    # Spawn deployed Modal function by name (matches modal deploy of train.py)
    fn_name = "train_swin_tiny" if body.variant == "tiny" else "train_swin_base"
    try:
        if not _ensure_modal_credentials():
            raise RuntimeError(
                "Modal credentials missing. Set MODAL_TOKEN_ID and MODAL_TOKEN_SECRET, "
                "or set MODAL_API_KEY as JSON with token_id/token_secret."
            )
        train_fn = modal.Function.from_name(MODAL_TRAINING_APP, fn_name)
        await train_fn.spawn.aio(config)
    except Exception as exc:
        runs_table.update_item(
            Key={"run_id": run.run_id},
            UpdateExpression="SET #s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": "failed"},
        )
        raise HTTPException(status_code=500, detail=f"Failed to spawn Modal run: {exc}")

    return TrainResponse(run_id=run.run_id, variant=body.variant, status="started")


# ---------------------------------------------------------------------------
# /evaluate
# ---------------------------------------------------------------------------

class EvaluateRequest(BaseModel):
    variant: str        # "tiny" | "base"
    checkpoint: str     # full path inside Modal Volume, e.g. /checkpoints/tiny/best.pt


class EvaluateResponse(BaseModel):
    variant: str
    checkpoint: str
    status: str         # always "started" on success


@router.post("/evaluate", response_model=EvaluateResponse)
async def start_evaluation(body: EvaluateRequest):
    """
    Kick off a Modal evaluation run for the specified checkpoint.

    - Spawns the Modal evaluate Function asynchronously and returns immediately.
    - Results (metrics JSON + patch log JSON) are written to the Modal Volume
      at /checkpoints/{variant}/eval_{checkpoint_stem}_metrics.json and
      /checkpoints/{variant}/eval_{checkpoint_stem}_patches.json.

    Request body:
        variant    : "tiny" or "base"
        checkpoint : path to checkpoint inside Modal Volume,
                     e.g. "/checkpoints/tiny/best.pt"

    Response:
        variant    : echoed back
        checkpoint : echoed back
        status     : "started"
    """
    if body.variant not in ("tiny", "base"):
        raise HTTPException(
            status_code=400,
            detail=f"variant must be 'tiny' or 'base', got '{body.variant}'",
        )

    if not body.checkpoint.startswith("/checkpoints/"):
        raise HTTPException(
            status_code=400,
            detail="checkpoint must be a full Modal Volume path, e.g. /checkpoints/tiny/best.pt",
        )

    try:
        if not _ensure_modal_credentials():
            raise RuntimeError(
                "Modal credentials missing. Set MODAL_TOKEN_ID and MODAL_TOKEN_SECRET, "
                "or set MODAL_API_KEY as JSON with token_id/token_secret."
            )
        eval_fn = modal.Function.from_name(MODAL_EVAL_APP, "evaluate")
        await eval_fn.spawn.aio(variant=body.variant, checkpoint_path=body.checkpoint)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to spawn Modal evaluation: {exc}")

    return EvaluateResponse(
        variant=body.variant,
        checkpoint=body.checkpoint,
        status="started",
    )