"""
evaluate.py — Evaluation script for art authentication models.
Based on: "Art Authentication with Vision Transformers" (Schaerf et al., 2023)

Loads a checkpoint from a Modal Volume, runs inference on the test split,
and reports accuracy, precision, recall, F1, and confusion matrix.
Results are printed to stdout and saved as a JSON file locally.

Usage:
    modal run evaluate.py --variant tiny --checkpoint /checkpoints/tiny/best.pt
    modal run evaluate.py --variant base --checkpoint /checkpoints/base/epoch_042.pt

Output:
    - Printed metrics table to stdout
    - JSON results file saved locally as eval_{variant}_{checkpoint_stem}.json
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import modal

# ---------------------------------------------------------------------------
# Modal primitives (must match train.py)
# ---------------------------------------------------------------------------

app = modal.App("artguard-evaluation")

volume = modal.Volume.from_name("artguard-checkpoints", create_if_missing=False)
CHECKPOINT_DIR = "/checkpoints"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch==2.3.0",
        "torchvision==0.18.0",
        "boto3",
        "pillow",
        "scikit-learn",
        "tqdm",
    )
)

aws_secret = modal.Secret.from_name("artguard-aws")

def _evaluate(variant: str, checkpoint_path: str) -> dict:
    import torch
    from sklearn.metrics import (
        accuracy_score,
        precision_score,
        recall_score,
        f1_score,
        confusion_matrix,
    )
    from torch.utils.data import DataLoader
    from tqdm import tqdm

    from src.apps.training.dataset import PatchDataset, default_val_transforms
    from src.apps.training.model import ArtAuthenticator

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[{variant}] Device: {device}")

    # ---- Load checkpoint -------------------------------------------------
    ckpt_path = Path(checkpoint_path)
    if not ckpt_path.exists():
        raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")

    print(f"[{variant}] Loading checkpoint: {ckpt_path}")
    checkpoint = torch.load(ckpt_path, map_location=device)

    # ---- Build model and load weights ------------------------------------
    model = ArtAuthenticator(variant=variant, pretrained=False).to(device)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()

    trained_epoch  = checkpoint.get("epoch", "unknown")
    ckpt_val_loss  = checkpoint.get("val_loss", None)
    ckpt_val_acc   = checkpoint.get("val_acc", None)
    ckpt_config    = checkpoint.get("config", {})

    print(f"[{variant}] Checkpoint epoch: {trained_epoch}")
    if ckpt_val_loss is not None:
        print(f"[{variant}] Checkpoint val_loss: {ckpt_val_loss:.4f}  val_acc: {ckpt_val_acc:.4f}")

    # ---- Dataset (test split only) ---------------------------------------
    region           = os.environ["AWS_REGION"]
    img_table_name   = os.environ["DDB_IMAGES_TABLE"]
    patch_table_name = os.environ["DDB_PATCHES_TABLE"]
    processed_bucket = os.environ["S3_IMAGES_PROCESSED_BUCKET"]

    test_dataset = PatchDataset(
        img_table_name=img_table_name,
        patch_table_name=patch_table_name,
        processed_bucket=processed_bucket,
        region=region,
        transform=default_val_transforms(),
        imitation_weight=1.0,   # no weighting at eval time
        split="test",
    )

    if len(test_dataset) == 0:
        raise RuntimeError("Test dataset is empty — check your DynamoDB split field.")

    test_loader = DataLoader(
        test_dataset,
        batch_size=32,
        shuffle=False,
        num_workers=4,
        pin_memory=(device == "cuda"),
    )

    print(
        f"[{variant}] Test patches: {len(test_dataset):,} "
        f"({test_dataset.authentic_count:,} authentic, "
        f"{test_dataset.contrast_count:,} contrast)"
    )

    # ---- Inference -------------------------------------------------------
    all_preds  : list[int] = []
    all_labels : list[int] = []
    all_probs  : list[float] = []

    with torch.no_grad():
        for imgs, labels, _ in tqdm(test_loader, desc=f"[{variant}] Evaluating"):
            imgs   = imgs.to(device)
            logits = model(imgs).squeeze(-1)          # (B,)
            probs  = torch.sigmoid(logits).cpu()
            preds  = (probs > 0.5).long()

            all_probs.extend(probs.tolist())
            all_preds.extend(preds.tolist())
            all_labels.extend(labels.tolist())

    # ---- Metrics ---------------------------------------------------------
    # Patch-level metrics
    patch_acc  = accuracy_score(all_labels, all_preds)
    patch_prec = precision_score(all_labels, all_preds, zero_division=0)
    patch_rec  = recall_score(all_labels, all_preds, zero_division=0)
    patch_f1   = f1_score(all_labels, all_preds, zero_division=0)
    patch_cm   = confusion_matrix(all_labels, all_preds).tolist()

    # Painting-level metrics (paper reports these — mean prob across patches per image)
    # Requires patch→image mapping from the dataset index
    from collections import defaultdict
    img_probs : dict[str, list[float]] = defaultdict(list)
    img_label : dict[str, int] = {}

    for idx, (prob, label) in enumerate(zip(all_probs, all_labels)):
        patch_path, lbl, _ = test_dataset._samples[idx]
        # Use patch_path as a proxy key grouped by image folder
        # patch_path format: {prefix}/{image_id}/x{x}_y{y}_{type}.jpg
        image_id = Path(patch_path).parent.name
        img_probs[image_id].append(prob)
        img_label[image_id] = lbl

    painting_labels = []
    painting_preds  = []
    for image_id, probs in img_probs.items():
        mean_prob = sum(probs) / len(probs)
        painting_labels.append(img_label[image_id])
        painting_preds.append(1 if mean_prob > 0.5 else 0)

    paint_acc  = accuracy_score(painting_labels, painting_preds)
    paint_prec = precision_score(painting_labels, painting_preds, zero_division=0)
    paint_rec  = recall_score(painting_labels, painting_preds, zero_division=0)
    paint_f1   = f1_score(painting_labels, painting_preds, zero_division=0)
    paint_cm   = confusion_matrix(painting_labels, painting_preds).tolist()

    # ---- Print results ---------------------------------------------------
    print(f"\n{'='*60}")
    print(f"  Evaluation Results — Swin-{variant.capitalize()}")
    print(f"  Checkpoint : {ckpt_path.name}  (epoch {trained_epoch})")
    print(f"{'='*60}")
    print(f"  PATCH-LEVEL  ({len(all_labels):,} patches)")
    print(f"    Accuracy  : {patch_acc:.4f}")
    print(f"    Precision : {patch_prec:.4f}")
    print(f"    Recall    : {patch_rec:.4f}")
    print(f"    F1        : {patch_f1:.4f}")
    print(f"    Confusion matrix (rows=actual, cols=predicted):")
    print(f"      [TN={patch_cm[0][0]:>5}  FP={patch_cm[0][1]:>5}]")
    print(f"      [FN={patch_cm[1][0]:>5}  TP={patch_cm[1][1]:>5}]")
    print(f"\n  PAINTING-LEVEL  ({len(painting_labels):,} paintings)")
    print(f"    Accuracy  : {paint_acc:.4f}")
    print(f"    Precision : {paint_prec:.4f}")
    print(f"    Recall    : {paint_rec:.4f}")
    print(f"    F1        : {paint_f1:.4f}")
    print(f"    Confusion matrix (rows=actual, cols=predicted):")
    print(f"      [TN={paint_cm[0][0]:>5}  FP={paint_cm[0][1]:>5}]")
    print(f"      [FN={paint_cm[1][0]:>5}  TP={paint_cm[1][1]:>5}]")
    print(f"{'='*60}\n")

    # ---- Assemble results dict -------------------------------------------
    results = {
        "variant":         variant,
        "checkpoint":      str(ckpt_path),
        "checkpoint_name": ckpt_path.name,
        "trained_epoch":   trained_epoch,
        "checkpoint_val_loss": ckpt_val_loss,
        "checkpoint_val_acc":  ckpt_val_acc,
        "train_config":    ckpt_config,
        "patch_level": {
            "n_patches":  len(all_labels),
            "accuracy":   patch_acc,
            "precision":  patch_prec,
            "recall":     patch_rec,
            "f1":         patch_f1,
            "confusion_matrix": patch_cm,
        },
        "painting_level": {
            "n_paintings": len(painting_labels),
            "accuracy":    paint_acc,
            "precision":   paint_prec,
            "recall":      paint_rec,
            "f1":          paint_f1,
            "confusion_matrix": paint_cm,
        },
    }

    return results


# ---------------------------------------------------------------------------
# Modal Function
# ---------------------------------------------------------------------------

@app.function(
    image=image,
    gpu="A10G",
    timeout=60 * 60 * 2,
    volumes={CHECKPOINT_DIR: volume},
    secrets=[aws_secret],
    mounts=[
        modal.Mount.from_local_python_packages(
            "src.apps.training.dataset",
            "src.apps.training.model",
        )
    ],
)
def evaluate(variant: str, checkpoint_path: str) -> dict:
    return _evaluate(variant=variant, checkpoint_path=checkpoint_path)


# ---------------------------------------------------------------------------
# Local entrypoint
# ---------------------------------------------------------------------------

@app.local_entrypoint()
def main(
    variant: str,
    checkpoint: str,
    output_dir: str = ".",
) -> None:
    """
    Args:
        variant    : "tiny" or "base"
        checkpoint : Full path to checkpoint inside the Modal Volume,
                     e.g. /checkpoints/tiny/best.pt
        output_dir : Local directory to write the JSON results file (default: cwd)
    """
    if variant not in ("tiny", "base"):
        raise ValueError(f"variant must be 'tiny' or 'base', got '{variant}'")

    results = evaluate.remote(variant=variant, checkpoint_path=checkpoint)

    # Save JSON locally
    ckpt_stem   = Path(checkpoint).stem
    output_path = Path(output_dir) / f"eval_{variant}_{ckpt_stem}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Results saved to {output_path}")