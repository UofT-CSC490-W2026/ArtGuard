"""POST /process_data -- kick off an ECS Fargate data processing task.

Launches a one-off ECS task that runs the ``src.apps.data_pipeline.driver``
module to process raw training images from S3 into patches.
"""

from __future__ import annotations

import logging
import os
import uuid

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.apps.backend.config import get_region

logger = logging.getLogger(__name__)

router = APIRouter(tags=["data"])


class ProcessDataResponse(BaseModel):
    """Response from a successful POST /process_data call.

    Attributes:
        run_id:   UUID identifying this processing run.
        task_arn: ARN of the ECS Fargate task that was started.
    """

    run_id: str
    task_arn: str


@router.post("/process_data", response_model=ProcessDataResponse)
async def process_data() -> ProcessDataResponse:
    """Launch an ECS Fargate task to process unprocessed training images.

    Reads cluster, networking, and container configuration from environment
    variables.

    Raises:
        HTTPException 500: If required env vars are missing, the STS call fails,
                           or the ECS RunTask call fails.
    """
    cluster = os.getenv("ECS_CLUSTER", "artguard-cluster")
    region = get_region()
    subnets = os.getenv("ECS_PRIVATE_SUBNETS", "")
    security_groups = os.getenv("ECS_TASK_SECURITY_GROUPS", "")
    container_name = os.getenv("ECS_PROCESS_CONTAINER_NAME", "backend")

    if not subnets or not security_groups:
        raise HTTPException(
            status_code=500,
            detail="Data processing service is not properly configured.",
        )

    task_def = os.getenv("ECS_PROCESS_TASK_FAMILY", "artguard-backend").strip()
    if not task_def:
        raise HTTPException(
            status_code=500,
            detail="Data processing service is not properly configured.",
        )
    run_id = str(uuid.uuid4())
    command = ["python", "-m", "src.apps.data_pipeline.driver", "--run_id", run_id]

    try:
        ecs = boto3.client("ecs", region_name=region)
        resp = ecs.run_task(
            cluster=cluster,
            taskDefinition=task_def,
            launchType="FARGATE",
            networkConfiguration={
                "awsvpcConfiguration": {
                    "subnets": [s.strip() for s in subnets.split(",") if s.strip()],
                    "securityGroups": [sg.strip() for sg in security_groups.split(",") if sg.strip()],
                    "assignPublicIp": "DISABLED",
                }
            },
            overrides={
                "containerOverrides": [
                    {
                        "name": container_name,
                        "command": command,
                        "environment": [{"name": "RUN_ID", "value": run_id}],
                    }
                ]
            },
        )
    except ClientError as exc:
        logger.error("ECS RunTask client error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=400,
            detail="Data processing task configuration is invalid or inactive.",
        )
    except Exception as exc:
        logger.error("ECS RunTask failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to launch the data processing task. Please try again later.",
        )

    failures = resp.get("failures") or []
    if failures:
        logger.error("ECS RunTask returned failures: %s", failures)
        raise HTTPException(
            status_code=500,
            detail="The data processing task could not be started.",
        )

    tasks = resp.get("tasks") or []
    if not tasks:
        raise HTTPException(
            status_code=500,
            detail="No ECS task was started. Please try again later.",
        )

    return ProcessDataResponse(run_id=run_id, task_arn=tasks[0]["taskArn"])
