from fastapi import FastAPI, UploadFile, File, HTTPException, Header, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import boto3
import json
import os, time
import uuid
from typing import Optional, List
from PIL import Image
from io import BytesIO
import base64
import requests
from src.apps.data_pipeline.process import process_inference_image
from src.apps.backend.routes.train_router import router as train_router
from src.apps.backend.routes.auth_router import router as auth_router
from src.apps.backend.routes.inferences_router import router as inferences_router
from src.apps.backend.deps.auth import get_current_user_id
from src.apps.backend.services.s3_presign import presigned_get_url

app = FastAPI(title="ArtGuard API", version="1.0.1")

# CORS: comma-separated origins, or * for any (no cookies; Bearer header is fine).
_cors_raw = os.getenv("CORS_ALLOW_ORIGINS", "*").strip()
if _cors_raw == "*":
    _cors_list = ["*"]
else:
    _cors_list = [o.strip() for o in _cors_raw.split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(inferences_router)
app.include_router(train_router)

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
            "/auth/*": "Signup, login, profile, change-password (JWT)",
            "/inference": "Multipart image + artist/artwork (Bearer required)",
            "/inferences/*": "List, stats, get, delete inference history (Bearer)",
            "/train": "Start a training run (POST)",
            "/evaluate": "Start an evaluation run (POST)",
        }
    }

class ProcessDataResponse(BaseModel):
    run_id: str
    task_arn: str

@app.post("/process_data", response_model=ProcessDataResponse)
async def process_data():
    cluster = os.getenv("ECS_CLUSTER", "artguard-cluster")
    region = os.getenv("AWS_REGION", "ca-central-1")
    account_id = boto3.client("sts").get_caller_identity()["Account"]
    task_def = f"arn:aws:ecs:{region}:{account_id}:task-definition/artguard-backend"
    subnets = os.getenv("ECS_PRIVATE_SUBNETS", "")
    security_groups = os.getenv("ECS_TASK_SECURITY_GROUPS", "")
    container_name = os.getenv("ECS_PROCESS_CONTAINER_NAME", "backend")

    if not task_def:
        raise HTTPException(status_code=500, detail="ECS_PROCESS_TASK_DEF_ARN not configured")
    if not subnets or not security_groups:
        raise HTTPException(status_code=500, detail="ECS_PRIVATE_SUBNETS / ECS_TASK_SECURITY_GROUPS not configured")

    run_id = str(uuid.uuid4())
    command = [
        "python", "-m",
        "src.apps.data_pipeline.driver",
        "--run_id", run_id,
    ]

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
    return ProcessDataResponse(run_id=run_id, task_arn=task_arn)

# This class tells FastAPI the minimum information to receive from an inference request.
class InferenceResponse(BaseModel):
    inference_id: str
    score: float
    explanation: Optional[str] = None
    image_url: Optional[str] = None


@app.post("/inference", response_model=InferenceResponse)
async def infer(
    file: UploadFile = File(...),
    artist_name: str = Form(...),
    artwork_name: str = Form(...),
    user_id: str = Depends(get_current_user_id),
):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty upload")
    artist_name = artist_name.strip()
    artwork_name = artwork_name.strip()
    if not artist_name or not artwork_name:
        raise HTTPException(
            status_code=400,
            detail="artist_name and artwork_name are required",
        )
    
    # TODO: Initialize the S3 buckets.
    region = os.getenv("AWS_REGION")
    raw_bucket = os.getenv("S3_IMAGES_RAW_BUCKET")
    processed_bucket = os.getenv("S3_IMAGES_PROCESSED_BUCKET")

    raw_prefix = os.getenv("S3_RAW_PREFIX", "inference")
    processed_prefix = os.getenv("S3_PROCESSED_PREFIX", "inference")

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
        ServerSideEncryption="AES256",
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
    score = 1.0
    explanation = "This is a sample response."

    ttl_days = int(os.getenv("INFERENCE_TTL_DAYS", "90"))
    ttl_ts = int(time.time()) + ttl_days * 86400

    inference_table.put_item(
        Item={
            "inference_id": inference_id,
            "user_id": user_id,
            "created_at": created_at,
            "image_name": filename,
            "image_path": raw_s3_uri,
            "score": score,
            "explanation": explanation,
            "artist_name": artist_name,
            "artwork_name": artwork_name,
            "file_size": len(content),
            "ttl": ttl_ts,
        }
    )

    presign_expires = int(os.getenv("S3_INFERENCE_PRESIGN_EXPIRES", "86400"))
    image_url: Optional[str] = None
    try:
        image_url = presigned_get_url(s3, raw_s3_uri, presign_expires)
    except Exception:
        image_url = None

    return InferenceResponse(
        inference_id=inference_id,
        score=score,
        explanation=explanation,
        image_url=image_url,
    )

class RAGQueryRequest(BaseModel):
    query: str

class RAGQueryResponse(BaseModel):
    answer: str
    sources: List[dict]

@app.post("/rag-query", response_model=RAGQueryResponse)
async def rag_query(body: RAGQueryRequest):
    """Test endpoint to query the Bedrock Knowledge Base."""
    region = os.getenv("AWS_REGION")
    knowledge_base_id = os.getenv("KNOWLEDGE_BASE_ID")

    if not knowledge_base_id:
        raise HTTPException(status_code=500, detail="KNOWLEDGE_BASE_ID not configured")

    bedrock = boto3.client("bedrock-agent-runtime", region_name=region)

    resp = bedrock.retrieve_and_generate(
        input={"text": body.query},
        retrieveAndGenerateConfiguration={
            "type": "KNOWLEDGE_BASE",
            "knowledgeBaseConfiguration": {
                "knowledgeBaseId": knowledge_base_id,
                "modelArn": f"arn:aws:bedrock:{region}::foundation-model/anthropic.claude-3-haiku-20240307-v1:0",
            },
        },
    )

    answer = resp.get("output", {}).get("text", "")
    citations = resp.get("citations", [])
    sources = []
    for citation in citations:
        for ref in citation.get("retrievedReferences", []):
            loc = ref.get("location", {})
            s3_uri = loc.get("s3Location", {}).get("uri", "")
            snippet = ref.get("content", {}).get("text", "")[:200]
            sources.append({"s3_uri": s3_uri, "snippet": snippet})

    return RAGQueryResponse(answer=answer, sources=sources)
