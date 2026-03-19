"""
routes/train.py — Training endpoints.

Registered in main.py via:
    from src.apps.backend.routes.train import router as train_router
    app.include_router(train_router)
"""

from __future__ import annotations

import os
from dataclasses import asdict
from typing import Optional

import boto3
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.schemas import RunRecord
from src.apps.training.train import DEFAULT_CONFIG, train_swin_base, train_swin_tiny

router = APIRouter()


class TrainRequest(BaseModel):
    variant: str            # "tiny" | "base"
    config: Optional[dict] = None   # overrides DEFAULT_CONFIG; omit to use defaults


class TrainResponse(BaseModel):
    run_id: str
    variant: str
    status: str             # always "started" on success


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

    # Write RunRecord to DynamoDB
    run = RunRecord()
    run.status            = "running"
    run.modal_volume_path = f"/checkpoints/{body.variant}"

    ddb        = boto3.resource("dynamodb", region_name=region)
    runs_table = ddb.Table(runs_table_name)
    runs_table.put_item(Item=asdict(run))

    # Spawn Modal Function (non-blocking)
    try:
        if body.variant == "tiny":
            train_swin_tiny.spawn(config)
        else:
            train_swin_base.spawn(config)
    except Exception as exc:
        runs_table.update_item(
            Key={"run_id": run.run_id},
            UpdateExpression="SET #s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": "failed"},
        )
        raise HTTPException(status_code=500, detail=f"Failed to spawn Modal run: {exc}")

    return TrainResponse(run_id=run.run_id, variant=body.variant, status="started")