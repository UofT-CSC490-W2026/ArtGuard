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
  artguard-aws:
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION,
    DDB_IMAGES_TABLE, DDB_PATCHES_TABLE, S3_IMAGES_PROCESSED_BUCKET
  artguard-wandb (optional but recommended for logging):
    WANDB_API_KEY

  Create W&B secret once:
    modal secret create artguard-wandb WANDB_API_KEY=<your_key>
"""

from __future__ import annotations

import os
import time
import math
from typing import Optional

import modal

# ---------------------------------------------------------------------------
# Modal primitives
# ---------------------------------------------------------------------------


def _cache_swin_base_weights() -> None:
    import torchvision.models as models
    models.swin_b(weights=models.Swin_B_Weights.IMAGENET1K_V1)


def _cache_swin_tiny_weights() -> None:
    import torchvision.models as models
    models.swin_t(weights=models.Swin_T_Weights.IMAGENET1K_V1)

app = modal.App("artguard-training")

# Persistent volume for model checkpoints
volume = modal.Volume.from_name("artguard-checkpoints", create_if_missing=True)
CHECKPOINT_DIR = "/checkpoints"

# Container image — install all deps and include local python source
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch==2.3.0",
        "torchvision==0.18.0",
        "boto3",
        "pillow",
        "tqdm",
        "wandb",
    )
    .run_function(_cache_swin_base_weights)
    .run_function(_cache_swin_tiny_weights)
    .add_local_python_source(
        "src.apps.train.dataset",
        "src.apps.train.model",
    )
)

# AWS credentials as a Modal secret (set via `modal secret create artguard-aws ...`)
aws_secret = modal.Secret.from_name("artguard-aws")
# Weights & Biases API key (set via `modal secret create artguard-wandb WANDB_API_KEY=...`)
wandb_secret = modal.Secret.from_name("artguard-wandb")

# ---------------------------------------------------------------------------
# Training config dataclass (plain dict passed as JSON-serialisable kwargs)
# Keep this local so Modal containers do not depend on additional mounted files.
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = dict(
    num_epochs=50,
    batch_size=32,         # paper Section 3.3
    lr=1e-4,               # paper Section 3.3
    early_stop_patience=10,
    early_stop_min_delta=1e-3,
    imitation_weight=10.0, # paper Section 3.2
    val_split=0.1,
    num_workers=4,
    wandb_enabled=True,
    wandb_project="artguard-training",
    wandb_entity=None,
    wandb_run_name='akshaya-artguard-training-baseline-v2',
)

# ---------------------------------------------------------------------------
# Core training logic (shared between both variants)
# ---------------------------------------------------------------------------

def _train(variant: str, config: dict) -> None:
    import torch
    from torch.utils.data import DataLoader, random_split
    from tqdm import tqdm

    from src.apps.train.dataset import (
        PatchDataset,
        default_train_transforms,
        default_val_transforms,
    )
    from src.apps.train.model import ArtAuthenticator

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[{variant}] Device: {device}")
    wandb = None
    wandb_run = None
    wandb_enabled = bool(config.get("wandb_enabled", True))
    if wandb_enabled:
        try:
            import wandb as _wandb
            wandb = _wandb
            run_name = config.get("wandb_run_name") or f"swin-{variant}"
            wandb_kwargs = {
                "project": config.get("wandb_project", "artguard-training"),
                "name": run_name,
                "config": config,
                "tags": [variant],
            }
            if config.get("wandb_entity"):
                wandb_kwargs["entity"] = config["wandb_entity"]
            wandb_run = wandb.init(**wandb_kwargs)
            print(f"[{variant}] Weights & Biases logging enabled.")
        except Exception as exc:
            wandb_enabled = False
            print(f"[{variant}] W&B init failed, continuing without W&B: {exc}")

    region = os.environ["AWS_REGION"]
    img_table_name = os.environ["DDB_IMAGES_TABLE"]
    patch_table_name = os.environ["DDB_PATCHES_TABLE"]
    processed_bucket = os.environ["S3_IMAGES_PROCESSED_BUCKET"]

    # Prefer persisted splits from ImageRecords; fallback to random split for legacy data.
    train_ds = PatchDataset(
        img_table_name=img_table_name,
        patch_table_name=patch_table_name,
        processed_bucket=processed_bucket,
        region=region,
        transform=default_train_transforms(),
        imitation_weight=config["imitation_weight"],
        split="train",
    )
    val_ds = PatchDataset(
        img_table_name=img_table_name,
        patch_table_name=patch_table_name,
        processed_bucket=processed_bucket,
        region=region,
        transform=default_val_transforms(),
        imitation_weight=1.0,
        split="val",
    )

    if len(train_ds) == 0 or len(val_ds) == 0:
        print(
            f"[{variant}] WARNING: split-labelled train/val dataset is empty "
            f"(train={len(train_ds)}, val={len(val_ds)}). Falling back to random split."
        )
        full_dataset = PatchDataset(
            img_table_name=img_table_name,
            patch_table_name=patch_table_name,
            processed_bucket=processed_bucket,
            region=region,
            transform=default_train_transforms(),
            imitation_weight=config["imitation_weight"],
        )
        val_size = max(1, int(len(full_dataset) * config["val_split"]))
        train_size = len(full_dataset) - val_size
        train_ds, val_ds = random_split(full_dataset, [train_size, val_size])
        val_ds.dataset.transform = default_val_transforms()
    else:
        train_size = len(train_ds)
        val_size = len(val_ds)

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

    train_auth = train_ds.authentic_count if hasattr(train_ds, "authentic_count") else None
    train_con = train_ds.contrast_count if hasattr(train_ds, "contrast_count") else None
    val_auth = val_ds.authentic_count if hasattr(val_ds, "authentic_count") else None
    val_con = val_ds.contrast_count if hasattr(val_ds, "contrast_count") else None
    if train_auth is not None and val_auth is not None:
        print(
            f"[{variant}] Train patches: {train_size:,}  |  Val patches: {val_size:,}\n"
            f"[{variant}] Train authentic: {train_auth:,}  |  Train contrast: {train_con:,}\n"
            f"[{variant}] Val authentic: {val_auth:,}  |  Val contrast: {val_con:,}"
        )
    else:
        print(f"[{variant}] Train patches: {train_size:,}  |  Val patches: {val_size:,}")

    print(
        f"[{variant}] Training plan: {config['num_epochs']} epochs | "
        f"batch_size={config['batch_size']} | lr={config['lr']} | "
        f"early_stop_patience={config['early_stop_patience']}",
        flush=True,
    )

    print(f"[{variant}] Initializing Swin-{variant} model (pretrained=True)...", flush=True)
    model = ArtAuthenticator(variant=variant, pretrained=True).to(device)
    print(f"[{variant}] Model initialized and moved to {device}.", flush=True)
    optimizer = model.configure_optimizer(lr=config["lr"])
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=0.5, patience=5, min_lr=1e-6
    )
    criterion = torch.nn.BCEWithLogitsLoss(reduction="none")

    best_val_loss = float("inf")
    best_val_bpb = float("inf")
    last_train_loss = float("nan")
    last_train_bpb = float("nan")
    last_val_bpb = float("nan")
    # last_epoch_mfu = 0.0
    # mean_mfu_accum = 0.0
    # mfu_count = 0
    peak_memory_mb = 0.0
    instability_events = 0
    prev_val_bpb = None
    max_train_images_per_sec = 0.0
    epochs_no_improve = 0
    checkpoint_dir = os.path.join(CHECKPOINT_DIR, variant)
    os.makedirs(checkpoint_dir, exist_ok=True)
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()

    run_start = time.perf_counter()
    for epoch in range(1, config["num_epochs"] + 1):
        epoch_wall_start = time.perf_counter()
        train_phase_start = time.perf_counter()
        model.train()
        train_loss = 0.0
        train_correct = 0

        for imgs, labels, weights, _, __ in tqdm(train_loader, desc=f"[{variant}] Epoch {epoch} train"):
            imgs = imgs.to(device)
            labels = labels.float().to(device)
            weights = weights.float().to(device)

            optimizer.zero_grad()
            logits = model(imgs).squeeze(-1)
            losses = criterion(logits, labels)
            loss = (losses * weights).mean()
            loss.backward()
            optimizer.step()

            train_loss += loss.item() * imgs.size(0)
            preds = (torch.sigmoid(logits) > 0.5).long()
            train_correct += (preds == labels.long()).sum().item()

        train_loss /= train_size
        train_acc = train_correct / train_size
        train_phase_sec = time.perf_counter() - train_phase_start

        print(
            f"[{variant}] Epoch {epoch}/{config['num_epochs']} — "
            f"train done: loss={train_loss:.4f} acc={train_acc:.4f} "
            f"({train_phase_sec:.1f}s)",
            flush=True,
        )

        model.eval()
        val_loss = 0.0
        val_correct = 0

        print(
            f"[{variant}] Epoch {epoch}/{config['num_epochs']} — "
            f"running validation on {val_size:,} patches...",
            flush=True,
        )
        with torch.no_grad():
            for imgs, labels, weights, _, __ in val_loader:
                imgs = imgs.to(device)
                labels = labels.float().to(device)
                logits = model(imgs).squeeze(-1)
                losses = criterion(logits, labels)
                loss = losses.mean()

                val_loss += loss.item() * imgs.size(0)
                preds = (torch.sigmoid(logits) > 0.5).long()
                val_correct += (preds == labels.long()).sum().item()

        val_loss /= val_size
        val_acc = val_correct / val_size
        scheduler.step(val_loss)
        val_bpb = val_loss / math.log(2)
        train_bpb = train_loss / math.log(2)
        last_train_loss = train_loss
        last_train_bpb = train_bpb
        last_val_bpb = val_bpb
        best_val_bpb = min(best_val_bpb, val_bpb)

        train_images_per_sec = train_size / max(train_phase_sec, 1e-9)
        max_train_images_per_sec = max(max_train_images_per_sec, train_images_per_sec)
        # epoch_mfu = train_images_per_sec / max(max_train_images_per_sec, 1e-9)  # throughput proxy
        # last_epoch_mfu = epoch_mfu
        # mean_mfu_accum += epoch_mfu
        # mfu_count += 1

        if prev_val_bpb is not None and val_bpb > (prev_val_bpb * 1.05):
            instability_events += 1
        prev_val_bpb = val_bpb

        if device == "cuda":
            peak_memory_mb = max(
                peak_memory_mb,
                float(torch.cuda.max_memory_allocated()) / (1024.0 * 1024.0),
            )
        epoch_wall_sec = time.perf_counter() - epoch_wall_start

        print(
            f"[{variant}] Epoch {epoch}/{config['num_epochs']} — "
            f"VAL loss={val_loss:.4f} acc={val_acc:.4f} | "
            f"train_loss={train_loss:.4f} train_acc={train_acc:.4f} | "
            f"epoch_wall={epoch_wall_sec:.1f}s",
            flush=True,
        )
        if wandb_enabled and wandb is not None and wandb_run is not None:
            wandb.log(
                {
                    "epoch": int(epoch),
                    "train_loss": float(train_loss),
                    "train_acc": float(train_acc),
                    "val_loss": float(val_loss),
                    "val_acc": float(val_acc),
                    "val_bpb": float(val_bpb),
                    "training_bpb": float(train_bpb),
                    "training_time_epoch_sec": float(epoch_wall_sec),
                    "peak_memory_mb": float(peak_memory_mb),
                    # "mfu": float(epoch_mfu),
                }
            )

        epoch_ckpt = os.path.join(checkpoint_dir, f"epoch_{epoch:03d}.pt")
        torch.save(
            {
                "epoch": epoch,
                "variant": variant,
                "state_dict": model.state_dict(),
                "optimizer": optimizer.state_dict(),
                "val_loss": val_loss,
                "val_acc": val_acc,
                "config": config,
            },
            epoch_ckpt,
        )
        volume.commit()

        if val_loss < best_val_loss - config["early_stop_min_delta"]:
            best_val_loss = val_loss
            epochs_no_improve = 0

            best_ckpt = os.path.join(checkpoint_dir, "best.pt")
            torch.save(
                {
                    "epoch": epoch,
                    "variant": variant,
                    "state_dict": model.state_dict(),
                    "val_loss": val_loss,
                    "val_acc": val_acc,
                    "config": config,
                },
                best_ckpt,
            )
            volume.commit()
            print(
                f"[{variant}]   ✓ New best val_loss={best_val_loss:.4f} val_acc={val_acc:.4f} "
                f"— saved to {best_ckpt}",
                flush=True,
            )
        else:
            epochs_no_improve += 1
            print(
                f"[{variant}]   No val improvement ({epochs_no_improve}/{config['early_stop_patience']}) "
                f"— val_loss={val_loss:.4f} val_acc={val_acc:.4f}",
                flush=True,
            )
            if epochs_no_improve >= config["early_stop_patience"]:
                print(f"[{variant}] Early stopping triggered at epoch {epoch}.", flush=True)
                break

    print(
        f"[{variant}] Training complete. Best val_loss={best_val_loss:.4f} "
        f"(last val_loss={val_loss:.4f} val_acc={val_acc:.4f})",
        flush=True,
    )
    print(f"[{variant}] Checkpoints saved to Modal Volume at {checkpoint_dir}/", flush=True)
    if wandb_enabled and wandb is not None and wandb_run is not None:
        total_training_time_sec = time.perf_counter() - run_start
        # mean_mfu = mean_mfu_accum / max(mfu_count, 1)
        # training_stability = 1.0 - (instability_events / max(mfu_count - 1, 1))
        wandb.summary["min_validation_bpb"] = float(best_val_bpb)
        wandb.summary["final_validation_bpb"] = float(last_val_bpb)
        wandb.summary["final_training_bpb"] = float(last_train_bpb)
        wandb.summary["training_loss_final"] = float(last_train_loss)
        # wandb.summary["mfu"] = float(last_epoch_mfu)
        # wandb.summary["mean_mfu"] = float(mean_mfu)
        wandb.summary["training_time_sec"] = float(total_training_time_sec)
        wandb.summary["peak_memory_mb"] = float(peak_memory_mb)
        # wandb.summary["training_stability"] = float(training_stability)
        wandb.summary["validation_bpb_at_checkpoint"] = float(best_val_bpb)
        wandb.finish()

# ---------------------------------------------------------------------------
# Modal Functions — one per variant so they can run in parallel
# ---------------------------------------------------------------------------

@app.function(
    image=image,
    gpu="A10G",
    timeout=60 * 60 * 12,
    volumes={CHECKPOINT_DIR: volume},
    secrets=[aws_secret, wandb_secret],
)
def train_swin_tiny(config: Optional[dict] = None) -> None:
    _train(variant="tiny", config=config or DEFAULT_CONFIG)


@app.function(
    image=image,
    gpu="A10G",
    timeout=60 * 60 * 12,
    volumes={CHECKPOINT_DIR: volume},
    secrets=[aws_secret, wandb_secret],
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