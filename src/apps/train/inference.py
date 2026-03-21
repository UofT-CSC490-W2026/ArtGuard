"""
inference.py -- Modal inference app for art authentication.

Loads a checkpoint from the artguard-checkpoints volume and runs
patch-level predictions. Called by the backend /inference endpoint.

Usage (from backend):
    from src.apps.train.inference import predict_patches
    result = predict_patches.remote(patch_s3_uris=["s3://..."], variant="tiny")
"""

from __future__ import annotations

import os
from typing import Optional

import modal

# ---------------------------------------------------------------------------
# Modal primitives (must match train.py)
# ---------------------------------------------------------------------------

app = modal.App("artguard-inference")

volume = modal.Volume.from_name("artguard-checkpoints", create_if_missing=True)
CHECKPOINT_DIR = "/checkpoints"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch==2.3.0",
        "torchvision==0.18.0",
        "boto3",
        "pillow",
    )
    .add_local_python_source(
        "src.apps.train.model",
    )
)

aws_secret = modal.Secret.from_name("artguard-aws")


# ---------------------------------------------------------------------------
# Modal Function
# ---------------------------------------------------------------------------

@app.function(
    image=image,
    gpu="T4",
    timeout=60 * 5,
    volumes={CHECKPOINT_DIR: volume},
    secrets=[aws_secret],
)
def predict_patches(
    patch_s3_uris: list[str],
    variant: str = "tiny",
    checkpoint_name: str = "best.pt",
) -> dict:
    """
    Load the model from the volume, download patches from S3, run inference.

    Args:
        patch_s3_uris  : list of s3:// URIs pointing to patch images
        variant        : "tiny" or "base"
        checkpoint_name: filename inside /checkpoints/{variant}/

    Returns:
        {
            "patch_probs": [float, ...],   # per-patch probability (>0.5 = authentic)
            "patch_preds": [int, ...],     # per-patch 0/1 prediction
            "mean_prob": float,            # average probability across patches
            "prediction": int,             # 1=authentic, 0=forgery (from mean_prob)
        }
    """
    import torch
    from io import BytesIO
    from pathlib import Path

    import boto3
    from PIL import Image
    from torchvision import transforms

    from src.apps.train.model import ArtAuthenticator

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[inference] Device: {device}, variant: {variant}")

    # ---- Load checkpoint -------------------------------------------------
    ckpt_path = Path(CHECKPOINT_DIR) / variant / checkpoint_name
    if not ckpt_path.exists():
        raise FileNotFoundError(f"Checkpoint not found: {ckpt_path}")

    checkpoint = torch.load(ckpt_path, map_location=device)
    model = ArtAuthenticator(variant=variant, pretrained=False).to(device)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    print(f"[inference] Loaded checkpoint: {ckpt_path} (epoch {checkpoint.get('epoch', '?')})")

    # ---- Transforms (match training val transforms) ----------------------
    IMAGENET_MEAN = [0.485, 0.456, 0.406]
    IMAGENET_STD = [0.229, 0.224, 0.225]

    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ])

    # ---- Download patches from S3 and build batch ------------------------
    region = os.environ.get("AWS_REGION", "ca-central-1")
    s3 = boto3.client("s3", region_name=region)

    tensors = []
    for uri in patch_s3_uris:
        # parse s3://bucket/key
        without_scheme = uri[5:]
        bucket, _, key = without_scheme.partition("/")
        resp = s3.get_object(Bucket=bucket, Key=key)
        img = Image.open(BytesIO(resp["Body"].read())).convert("RGB")
        tensors.append(transform(img))

    if not tensors:
        return {
            "patch_probs": [],
            "patch_preds": [],
            "mean_prob": 0.0,
            "prediction": 0,
        }

    batch = torch.stack(tensors).to(device)

    # ---- Run inference ---------------------------------------------------
    with torch.no_grad():
        logits = model(batch).squeeze(-1)
        probs = torch.sigmoid(logits).cpu().tolist()

    preds = [1 if p > 0.5 else 0 for p in probs]
    mean_prob = sum(probs) / len(probs)
    prediction = 1 if mean_prob > 0.5 else 0

    print(f"[inference] {len(probs)} patches, mean_prob={mean_prob:.4f}, prediction={prediction}")

    return {
        "patch_probs": probs,
        "patch_preds": preds,
        "mean_prob": mean_prob,
        "prediction": prediction,
    }
