"""
train.py — Modal training app for art authentication.
Based on: "Art Authentication with Vision Transformers" (Schaerf et al., 2023)

Runs two separate Modal Functions:
  - train_swin_tiny  (Swin-Tiny,  ImageNet-1K,  28M params)
  - train_swin_base  (Swin-Base,  ImageNet-1K,  88M params)

Weights are checkpointed to a Modal Volume after each epoch and at the end of
training. The volume is mounted at /checkpoints inside the container.

Usage:
  # Deploy and run both variants:
  modal run train.py::train_swin_tiny
  modal run train.py::train_swin_base

  # Or trigger both in parallel:
  modal run train.py

Environment variables expected (set as Modal Secrets):
  AWS_ACCESS_KEY_ID
  AWS_SECRET_ACCESS_KEY
  AWS_REGION
  DDB_IMAGES_TABLE
  DDB_PATCHES_TABLE
"""

from __future__ import annotations

import os
import time
from typing import Optional

import modal

# ---------------------------------------------------------------------------
# Modal primitives
# ---------------------------------------------------------------------------

app = modal.App("artguard-training")

# Persistent volume for model checkpoints
volume = modal.Volume.from_name("artguard-checkpoints", create_if_missing=True)
CHECKPOINT_DIR = "/checkpoints"

# Container image — install all deps
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch==2.3.0",
        "torchvision==0.18.0",
        "boto3",
        "pillow",
        "tqdm",
    )
)

# AWS credentials as a Modal secret (set via `modal secret create artguard-aws ...`)
aws_secret = modal.Secret.from_name("artguard-aws")

# ---------------------------------------------------------------------------
# Training config dataclass (plain dict passed as JSON-serialisable kwargs)
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = dict(
    num_epochs       = 100,
    batch_size       = 32,
    lr               = 1e-4,     
    early_stop_patience = 20,    
    early_stop_min_delta = 1e-3, 
    imitation_weight = 10.0,  
    val_split        = 0.1,     
    num_workers      = 4,
)


# ---------------------------------------------------------------------------
# Core training logic (shared between both variants)
# ---------------------------------------------------------------------------

def _train(variant: str, config: dict) -> None:
    import torch
    from torch.utils.data import DataLoader, random_split
    from tqdm import tqdm

    # Local imports — these files are mounted into the Modal container
    from src.apps.training.dataset import PatchDataset, default_train_transforms, default_val_transforms
    from src.apps.training.model import ArtAuthenticator

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[{variant}] Device: {device}")

    region           = os.environ["AWS_REGION"]
    img_table_name   = os.environ["DDB_IMAGES_TABLE"]
    patch_table_name = os.environ["DDB_PATCHES_TABLE"]
    processed_bucket = os.environ["S3_IMAGES_PROCESSED_BUCKET"]

    # ---- Dataset ---------------------------------------------------------
    full_dataset = PatchDataset(
        img_table_name=img_table_name,
        patch_table_name=patch_table_name,
        processed_bucket=processed_bucket,
        region=region,
        transform=default_train_transforms(),
        imitation_weight=config["imitation_weight"],
    )

    val_size   = max(1, int(len(full_dataset) * config["val_split"]))
    train_size = len(full_dataset) - val_size
    train_ds, val_ds = random_split(full_dataset, [train_size, val_size])

    # Apply val transforms to val split
    val_ds.dataset.transform = default_val_transforms()

    train_loader = DataLoader(
        train_ds,
        batch_size=config["batch_size"],
        shuffle=True,
        num_workers=config["num_workers"],
        pin_memory=(device == "cuda"),
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=config["batch_size"],
        shuffle=False,
        num_workers=config["num_workers"],
        pin_memory=(device == "cuda"),
    )

    print(
        f"[{variant}] Train patches: {train_size:,}  |  Val patches: {val_size:,}\n"
        f"[{variant}] Authentic: {full_dataset.authentic_count:,}  |  Contrast: {full_dataset.contrast_count:,}"
    )

    # ---- Model -----------------------------------------------------------
    model = ArtAuthenticator(variant=variant, pretrained=True).to(device)
    optimizer = model.configure_optimizer(lr=config["lr"])
    # Use reduction="none" so we can apply per-sample imitation weights
    criterion = torch.nn.BCEWithLogitsLoss(reduction="none")

    # ---- Training loop ---------------------------------------------------
    best_val_loss   = float("inf")
    epochs_no_improve = 0
    checkpoint_dir  = os.path.join(CHECKPOINT_DIR, variant)
    os.makedirs(checkpoint_dir, exist_ok=True)

    for epoch in range(1, config["num_epochs"] + 1):
        # -- Train --
        model.train()
        train_loss = 0.0
        train_correct = 0

        for imgs, labels, weights in tqdm(train_loader, desc=f"[{variant}] Epoch {epoch} train"):
            imgs    = imgs.to(device)
            labels  = labels.float().to(device)
            weights = weights.float().to(device)

            optimizer.zero_grad()
            logits = model(imgs).squeeze(-1)          # (B,)
            losses = criterion(logits, labels)        # (B,) unreduced
            loss   = (losses * weights).mean()        # apply imitation weighting
            loss.backward()
            optimizer.step()

            train_loss    += loss.item() * imgs.size(0)
            preds          = (torch.sigmoid(logits) > 0.5).long()
            train_correct += (preds == labels.long()).sum().item()

        train_loss /= train_size
        train_acc   = train_correct / train_size

        # -- Validate --
        model.eval()
        val_loss    = 0.0
        val_correct = 0

        with torch.no_grad():
            for imgs, labels, weights in val_loader:
                imgs   = imgs.to(device)
                labels = labels.float().to(device)
                logits = model(imgs).squeeze(-1)
                losses = criterion(logits, labels)
                loss   = losses.mean()               # no weighting at val time

                val_loss    += loss.item() * imgs.size(0)
                preds        = (torch.sigmoid(logits) > 0.5).long()
                val_correct += (preds == labels.long()).sum().item()

        val_loss /= val_size
        val_acc   = val_correct / val_size

        print(
            f"[{variant}] Epoch {epoch:03d} | "
            f"train_loss={train_loss:.4f}  train_acc={train_acc:.4f} | "
            f"val_loss={val_loss:.4f}  val_acc={val_acc:.4f}"
        )

        # -- Checkpoint every epoch --
        epoch_ckpt = os.path.join(checkpoint_dir, f"epoch_{epoch:03d}.pt")
        torch.save({
            "epoch":      epoch,
            "variant":    variant,
            "state_dict": model.state_dict(),
            "optimizer":  optimizer.state_dict(),
            "val_loss":   val_loss,
            "val_acc":    val_acc,
            "config":     config,
        }, epoch_ckpt)
        volume.commit()  # flush to Modal Volume

        # -- Early stopping --
        if val_loss < best_val_loss - config["early_stop_min_delta"]:
            best_val_loss = val_loss
            epochs_no_improve = 0
            # Save best separately for easy loading
            best_ckpt = os.path.join(checkpoint_dir, "best.pt")
            torch.save({
                "epoch":      epoch,
                "variant":    variant,
                "state_dict": model.state_dict(),
                "val_loss":   val_loss,
                "val_acc":    val_acc,
                "config":     config,
            }, best_ckpt)
            volume.commit()
            print(f"[{variant}]   ✓ New best val_loss={best_val_loss:.4f} — saved to {best_ckpt}")
        else:
            epochs_no_improve += 1
            print(f"[{variant}]   No improvement ({epochs_no_improve}/{config['early_stop_patience']})")
            if epochs_no_improve >= config["early_stop_patience"]:
                print(f"[{variant}] Early stopping triggered at epoch {epoch}.")
                break

    print(f"[{variant}] Training complete. Best val_loss={best_val_loss:.4f}")
    print(f"[{variant}] Checkpoints saved to Modal Volume at {checkpoint_dir}/")


# ---------------------------------------------------------------------------
# Modal Functions — one per variant so they can run in parallel
# ---------------------------------------------------------------------------

@app.function(
    image=image,
    gpu="A10G",
    timeout=60 * 60 * 12,          # 12 hours max
    volumes={CHECKPOINT_DIR: volume},
    secrets=[aws_secret],
    mounts=[
        modal.Mount.from_local_python_packages(
            "src.apps.training.dataset",
            "src.apps.training.model",
        )
    ],
)
def train_swin_tiny(config: Optional[dict] = None) -> None:
    _train(variant="tiny", config=config or DEFAULT_CONFIG)


@app.function(
    image=image,
    gpu="A10G",
    timeout=60 * 60 * 12,
    volumes={CHECKPOINT_DIR: volume},
    secrets=[aws_secret],
    mounts=[
        modal.Mount.from_local_python_packages(
            "src.apps.training.dataset",
            "src.apps.training.model",
        )
    ],
)
def train_swin_base(config: Optional[dict] = None) -> None:
    _train(variant="base", config=config or DEFAULT_CONFIG)


# ---------------------------------------------------------------------------
# Local entrypoint — triggers both variants in parallel
# ---------------------------------------------------------------------------

@app.local_entrypoint()
def main() -> None:
    print("Spawning Swin-Tiny and Swin-Base training runs in parallel...")
    tiny_call = train_swin_tiny.spawn(DEFAULT_CONFIG)
    base_call = train_swin_base.spawn(DEFAULT_CONFIG)
    tiny_call.get()
    base_call.get()
    print("Both runs complete.")