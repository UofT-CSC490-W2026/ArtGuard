from fastapi import FastAPI, UploadFile, File, HTTPException, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import subprocess
import boto3
import json
import os, time
import uuid
from typing import Optional, List
from PIL import Image
from io import BytesIO
import base64
import requests
from preprocessing.process import process_inference_image

app = FastAPI(title="ArtGuard API", version="1.0.0")

PIPELINE_SCRIPTS = [
    "preprocessing/met_pipeline.py",
    "preprocessing/wikidata_pipeline.py"
]
UPDATE_KB_SCRIPT = "./update-knowledge-base.sh"

DOCS_DIR = "preprocessing/output"
ENVIRONMENT = "dev"

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok"}


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Welcome to ArtGuard API",
        "version": "1.0.0",
        "endpoints": {
            "/health": "Health check",
        }
    }

# This class tells FastAPI the minimum information to send in a training request.
class TrainRequest(BaseModel):
    dataset_version: str
    k_folds: int = 5
    outer_split_seed: int = 17
    inner_split_seed: int = 99


# This class tells FastAPI the minimum information to receive from a training request.
class TrainRunResponse(BaseModel):
    run_id: str
    task_arn: str # unique identifier for running job

@app.post("/train", response_model=TrainRunResponse)
async def train(body: TrainRequest):
    # TODO: This will configure the environment to carry out the training job.
    # You should provide these via environment variables in your ECS service/task.
    # You can wire them from Terraform outputs.
    cluster = os.getenv("ECS_CLUSTER", "artguard-cluster")         # matches script defaults :contentReference[oaicite:2]{index=2}
    task_def = os.getenv("ECS_TRAIN_TASK_DEF_ARN")                # a task definition that contains your training code
    subnets = os.getenv("ECS_PRIVATE_SUBNETS", "")                # comma-separated subnet IDs
    security_groups = os.getenv("ECS_TASK_SECURITY_GROUPS", "")   # comma-separated security group IDs
    container_name = os.getenv("ECS_TRAIN_CONTAINER_NAME", "backend")

    if not task_def:
        raise HTTPException(status_code=500, detail="ECS_TRAIN_TASK_DEF_ARN not configured")
    if not subnets or not security_groups:
        raise HTTPException(status_code=500, detail="ECS_PRIVATE_SUBNETS / ECS_TASK_SECURITY_GROUPS not configured")

    run_id = str(uuid.uuid4())
    command = [
        "python",
        "model/driver.py",
        "--run_id", run_id,
        "--dataset_version", body.dataset_version,
        "--k_folds", str(body.k_folds),
        "--outer_split_seed", str(body.outer_split_seed),
        "--inner_split_seed", str(body.inner_split_seed),
    ]

    # TODO:
    # Launch and run a Fargate training job.
    ecs = boto3.client("ecs", region_name=os.getenv("AWS_REGION"))
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
                    "environment": [
                        {"name": "RUN_ID", "value": run_id},
                        {"name": "DATASET_VERSION", "value": body.dataset_version},
                    ],
                }
            ]
        },
    )

    failures = resp.get("failures") or []
    if failures:
        raise HTTPException(status_code=500, detail={"ecs_failures": failures})

    tasks = resp.get("tasks") or []
    if not tasks:
        raise HTTPException(status_code=500, detail="No ECS task started")

    task_arn = tasks[0]["taskArn"]
    return TrainRunResponse(run_id=run_id, task_arn=task_arn)

# This class tells FastAPI the minimum information to receive from an inference request.
class InferenceResponse(BaseModel):
    inference_id: str
    score: float
    explanation: Optional[str] = None

@app.post("/inference", response_model=InferenceResponse)
async def infer(file: UploadFile = File(...)):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty upload")
    
    # TODO: Initialize the S3 buckets.
    region = os.getenv("AWS_REGION")
    raw_bucket = os.getenv("S3_IMAGES_RAW_BUCKET")
    processed_bucket = os.getenv("S3_IMAGES_PROCESSED_BUCKET")

    raw_prefix = os.getenv("S3_RAW_PREFIX", "inference/raw")
    processed_prefix = os.getenv("S3_PROCESSED_PREFIX", "inference/processed")

    inference_table_name = os.getenv("DDB_INFERENCES_TABLE")
    img_table_name = os.getenv("DDB_IMAGES_TABLE")
    patch_table_name = os.getenv("DDB_PATCHES_TABLE")

    # Read the image.
    try:
        img = Image.open(BytesIO(content)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="The uploaded file is not an image.")
    w, h = img.size

    s3 = boto3.client("s3", region_name=region)
    ddb = boto3.resource("dynamodb", region_name=region)
    inference_table = ddb.Table(inference_table_name)
    img_table = ddb.Table(img_table_name)
    patch_table = ddb.Table(patch_table_name)

    inference_id = str(uuid.uuid4())
    image_id = str(uuid.uuid4())
    created_at = int(time.time() * 1000)
    filename = file.filename or f"{image_id}.jpg"

    # TODO: Upload the user uploaded image to S3 bucket
    raw_key = f"{raw_prefix}/{image_id}/{filename}"
    s3.put_object(
        Bucket=raw_bucket,
        Key=raw_key,
        Body=content,
        ContentType=file.content_type or "application/octet-stream",
    )
    raw_s3_uri = f"s3://{raw_bucket}/{raw_key}"

    # TODO: Write the image's metadata to DynamoDB
    img_table.put_item(Item={
        "image_id": image_id,
        "created_at": created_at,
        "image_name": filename,
        "image_path": raw_s3_uri,
        "image_width": w,
        "image_height": h,
    })

    # TODO: Write the inference's metadata to DynamoDB
    inference_table.put_item(Item={
        "inference_id": inference_id,
        "user_id": "anonymous", 
        "created_at": created_at,
        "image_name": filename,
        "image_path": raw_s3_uri,
        "score": 0.0,
        "explanation": None,
    })
   
    patches_info = process_inference_image(
        img=img,
        image_id=image_id,
        processed_bucket=processed_bucket,
        processed_prefix=processed_prefix,
        s3_client=s3,
    )

    # TODO: Write the patches' metadata to DynamoDB
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

    # TODO: Load the model from Modal volume with hyperparameter configs from DynamoDB
    # TODO: Make prediction
    # TODO: Update InferenceRecord in DynamoDB
    score = 1.0
    explanation = "This is a sample response."

    return InferenceResponse(inference_id=inference_id, score=score, explanation=explanation)
def run_pipeline(script_path: str):
    """Run a Python preprocessing pipeline."""
    if not os.path.exists(script_path):
        raise FileNotFoundError(f"Pipeline script not found: {script_path}")
    subprocess.run(["python", script_path], check=True)

def run_update_knowledge_base():
    """Call the existing Bash script to upload docs to S3 and trigger ingestion."""
    if not os.path.exists(UPDATE_KB_SCRIPT):
        raise FileNotFoundError(f"Update script not found: {UPDATE_KB_SCRIPT}")
    subprocess.run([UPDATE_KB_SCRIPT, ENVIRONMENT, DOCS_DIR], check=True)

@app.post("/upload-rag-data")
async def upload_rag_data(background_tasks: BackgroundTasks):
    # Create endpoint to trigger RAG pipeline (both met_pipeline.py and wikidata_pipeline.py) and upload data to S3 via the update_knowledge_base.py script
    for script in PIPELINE_SCRIPTS:
        background_tasks.add_task(run_pipeline, script)
    background_tasks.add_task(run_update_knowledge_base)
    return {"status": "RAG data upload initiated. Pipelines are running in the background."}
