"""
evaluate.py — Evaluation script for art authentication models.
Based on: "Art Authentication with Vision Transformers" (Schaerf et al., 2023)

Loads a checkpoint from a Modal Volume, runs inference on the test split,
and reports accuracy, precision, recall, F1, and confusion matrix —
overall and broken down by sublabel (original / forgery / imitation / proxy).

Results are printed to stdout and saved locally as two JSON files:
  - eval_{variant}_{checkpoint_stem}_metrics.json  — aggregated metrics
  - eval_{variant}_{checkpoint_stem}_patches.json  — per-patch prediction log

Usage:
    modal run evaluate.py --variant tiny --checkpoint /checkpoints/tiny/best.pt
    modal run evaluate.py --variant base --checkpoint /checkpoints/base/epoch_042.pt --output-dir ./results
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path

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
    .add_local_python_source(
        "src.apps.train.dataset",
        "src.apps.train.model",
    )
)

aws_secret = modal.Secret.from_name("artguard-aws")


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

def _compute_metrics(labels: list[int], preds: list[int]) -> dict:
    """Compute classification metrics for a set of true labels and predictions.

    Returns a dict with ``n``, ``accuracy``, ``precision``, ``recall``,
    ``f1``, and ``confusion_matrix`` (as [[TN, FP], [FN, TP]]). Returns
    None values if labels is empty.

    Args:
        labels: List of ground-truth binary labels (0 or 1).
        preds:  List of predicted binary labels (0 or 1).

    Returns:
        A dict of metric name -> value.
    """
    from sklearn.metrics import (
        accuracy_score,
        confusion_matrix,
        f1_score,
        precision_score,
        recall_score,
    )

    if not labels:
        return {
            "n": 0,
            "accuracy": None,
            "precision": None,
            "recall": None,
            "f1": None,
            "confusion_matrix": None,
        }

    cm = confusion_matrix(labels, preds, labels=[0, 1]).tolist()
    return {
        "n": len(labels),
        "accuracy": accuracy_score(labels, preds),
        "precision": precision_score(labels, preds, zero_division=0),
        "recall": recall_score(labels, preds, zero_division=0),
        "f1": f1_score(labels, preds, zero_division=0),
        "confusion_matrix": cm,  # [[TN, FP], [FN, TP]]
    }


def _print_metrics(title: str, m: dict) -> None:
    """Pretty-print a metrics dict (from ``_compute_metrics``) to stdout.

    Args:
        title: Section title label (e.g. ``"Overall"`` or ``"Forgery"``).
        m:     Metrics dict from ``_compute_metrics``.
    """
    if m["n"] == 0:
        print(f"  {title}: no samples")
        return

    cm = m["confusion_matrix"]
    print(f"  {title}  (n={m['n']:,})")
    print(f"    Accuracy  : {m['accuracy']:.4f}")
    print(f"    Precision : {m['precision']:.4f}")
    print(f"    Recall    : {m['recall']:.4f}")
    print(f"    F1        : {m['f1']:.4f}")
    print("    Confusion matrix (rows=actual, cols=predicted):")
    print(f"      [TN={cm[0][0]:>5}  FP={cm[0][1]:>5}]")
    print(f"      [FN={cm[1][0]:>5}  TP={cm[1][1]:>5}]")


# ---------------------------------------------------------------------------
# Core evaluation logic
# ---------------------------------------------------------------------------

def _evaluate(variant: str, checkpoint_path: str) -> tuple[dict, list[dict]]:
    """Run evaluation on the test split and compute patch- and painting-level metrics.

    Loads a model checkpoint, runs inference on all test patches, computes
    accuracy/precision/recall/F1 both at the patch level and aggregated
    at the painting level (mean probability per image), and breaks down
    metrics by sublabel (original / forgery / imitation / proxy).

    Args:
        variant:         ``"tiny"`` or ``"base"`` Swin model variant.
        checkpoint_path: Full path to a ``.pt`` checkpoint file on the Modal Volume.

    Returns:
        A tuple of (metrics_results, patch_log) where:
        - metrics_results: Aggregated metrics dict (saved as _metrics.json).
        - patch_log: List of per-patch prediction dicts (saved as _patches.json).
    """
    import torch
    from torch.utils.data import DataLoader
    from tqdm import tqdm

    from src.apps.train.dataset import PatchDataset, default_val_transforms
    from src.apps.train.model import ArtAuthenticator

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[{variant}] Device: {device}")

    # ---- Load checkpoint -------------------------------------------------
    ckpt_path = Path(checkpoint_path)
    if not ckpt_path.exists():
        raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")

    print(f"[{variant}] Loading checkpoint: {ckpt_path}")
    checkpoint = torch.load(ckpt_path, map_location=device)
    trained_epoch = checkpoint.get("epoch", "unknown")
    ckpt_val_loss = checkpoint.get("val_loss", None)
    ckpt_val_acc = checkpoint.get("val_acc", None)
    ckpt_config = checkpoint.get("config", {})

    print(f"[{variant}] Checkpoint epoch : {trained_epoch}")
    if ckpt_val_loss is not None and ckpt_val_acc is not None:
        print(f"[{variant}] Checkpoint val   : loss={ckpt_val_loss:.4f}  acc={ckpt_val_acc:.4f}")

    # ---- Model -----------------------------------------------------------
    model = ArtAuthenticator(variant=variant, pretrained=False).to(device)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()

    # ---- Dataset (test split only) --------------------------------------
    region = os.environ["AWS_REGION"]
    img_table_name = os.environ["DDB_IMAGES_TABLE"]
    patch_table_name = os.environ["DDB_PATCHES_TABLE"]
    processed_bucket = os.environ["S3_IMAGES_PROCESSED_BUCKET"]

    test_dataset = PatchDataset(
        img_table_name=img_table_name,
        patch_table_name=patch_table_name,
        processed_bucket=processed_bucket,
        region=region,
        transform=default_val_transforms(),
        imitation_weight=1.0,
        split="test",
    )

    if len(test_dataset) == 0:
        raise RuntimeError("Test dataset is empty — check the split field in DynamoDB.")

    print(
        f"[{variant}] Test patches : {len(test_dataset):,} "
        f"({test_dataset.authentic_count:,} authentic, "
        f"{test_dataset.contrast_count:,} inauthentic)"
    )
    print(f"[{variant}] Sublabel breakdown: {test_dataset.sublabel_counts}")

    test_loader = DataLoader(
        test_dataset,
        batch_size=32,
        shuffle=False,
        num_workers=4,
        pin_memory=(device == "cuda"),
    )

    # ---- Inference -------------------------------------------------------
    all_patch_paths: list[str] = []
    all_labels: list[int] = []
    all_preds: list[int] = []
    all_probs: list[float] = []
    all_sublabels: list[str] = []

    with torch.no_grad():
        for imgs, labels, _, sublabels, patch_paths in tqdm(
            test_loader, desc=f"[{variant}] Evaluating"
        ):
            imgs = imgs.to(device)
            logits = model(imgs).squeeze(-1)
            probs = torch.sigmoid(logits).cpu()
            preds = (probs > 0.5).long()

            all_probs.extend(probs.tolist())
            all_preds.extend(preds.tolist())
            all_labels.extend(labels.tolist())
            all_sublabels.extend(sublabels)
            all_patch_paths.extend(patch_paths)

    # ---- Patch-level metrics --------------------------------------------
    patch_overall = _compute_metrics(all_labels, all_preds)

    sublabel_patch_labels: dict[str, list[int]] = defaultdict(list)
    sublabel_patch_preds: dict[str, list[int]] = defaultdict(list)
    for lbl, pred, sl in zip(all_labels, all_preds, all_sublabels):
        key = sl if sl else "unlabelled"
        sublabel_patch_labels[key].append(lbl)
        sublabel_patch_preds[key].append(pred)

    patch_by_sublabel = {
        sl: _compute_metrics(sublabel_patch_labels[sl], sublabel_patch_preds[sl])
        for sl in sublabel_patch_labels
    }

    # ---- Painting-level metrics -----------------------------------------
    img_probs: dict[str, list[float]] = defaultdict(list)
    img_label: dict[str, int] = {}
    img_sublabel: dict[str, str] = {}

    for prob, lbl, sl, patch_path in zip(all_probs, all_labels, all_sublabels, all_patch_paths):
        image_id = Path(patch_path).parent.name
        img_probs[image_id].append(prob)
        img_label[image_id] = lbl
        img_sublabel[image_id] = sl if sl else "unlabelled"

    painting_labels: list[int] = []
    painting_preds: list[int] = []
    painting_sublabels: list[str] = []

    for image_id, probs in img_probs.items():
        mean_prob = sum(probs) / len(probs)
        painting_labels.append(img_label[image_id])
        painting_preds.append(1 if mean_prob > 0.5 else 0)
        painting_sublabels.append(img_sublabel[image_id])

    painting_overall = _compute_metrics(painting_labels, painting_preds)

    sublabel_paint_labels: dict[str, list[int]] = defaultdict(list)
    sublabel_paint_preds: dict[str, list[int]] = defaultdict(list)
    for lbl, pred, sl in zip(painting_labels, painting_preds, painting_sublabels):
        sublabel_paint_labels[sl].append(lbl)
        sublabel_paint_preds[sl].append(pred)

    painting_by_sublabel = {
        sl: _compute_metrics(sublabel_paint_labels[sl], sublabel_paint_preds[sl])
        for sl in sublabel_paint_labels
    }

    # ---- Print results ---------------------------------------------------
    sep = "=" * 64
    print(f"\n{sep}")
    print(f"  Evaluation Results — Swin-{variant.capitalize()}")
    print(f"  Checkpoint : {ckpt_path.name}  (epoch {trained_epoch})")
    print(sep)

    print("\n  PATCH-LEVEL")
    _print_metrics("Overall", patch_overall)
    for sl, m in sorted(patch_by_sublabel.items()):
        _print_metrics(sl.capitalize(), m)

    print("\n  PAINTING-LEVEL")
    _print_metrics("Overall", painting_overall)
    for sl, m in sorted(painting_by_sublabel.items()):
        _print_metrics(sl.capitalize(), m)

    print(f"{sep}\n")

    # ---- Build output dicts ---------------------------------------------
    metrics_results = {
        "variant": variant,
        "checkpoint": str(ckpt_path),
        "checkpoint_name": ckpt_path.name,
        "trained_epoch": trained_epoch,
        "checkpoint_val_loss": ckpt_val_loss,
        "checkpoint_val_acc": ckpt_val_acc,
        "train_config": ckpt_config,
        "patch_level": {
            "overall": patch_overall,
            "by_sublabel": patch_by_sublabel,
        },
        "painting_level": {
            "overall": painting_overall,
            "by_sublabel": painting_by_sublabel,
        },
    }

    patch_log = [
        {
            "patch_path": patch_path,
            "image_id": Path(patch_path).parent.name,
            "true_label": lbl,
            "pred_label": pred,
            "prob": round(prob, 6),
            "correct": lbl == pred,
            "sublabel": sl if sl else None,
        }
        for patch_path, lbl, pred, prob, sl in zip(
            all_patch_paths, all_labels, all_preds, all_probs, all_sublabels
        )
    ]

    return metrics_results, patch_log


# ---------------------------------------------------------------------------
# Modal Function
# ---------------------------------------------------------------------------

@app.function(
    image=image,
    gpu="A10G",
    timeout=60 * 60 * 2,
    volumes={CHECKPOINT_DIR: volume},
    secrets=[aws_secret],
)
def evaluate(variant: str, checkpoint_path: str) -> tuple[dict, list[dict]]:
    """Modal Function: evaluate a checkpoint on the test split and return metrics."""
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
    """Local entrypoint: run evaluation and save results as JSON files.

    Args:
        variant:    ``"tiny"`` or ``"base"`` Swin model variant.
        checkpoint: Full path to checkpoint inside Modal Volume,
                    e.g. ``/checkpoints/tiny/best.pt``.
        output_dir: Local directory to write JSON output (default: cwd).
    """
    if variant not in ("tiny", "base"):
        raise ValueError(f"variant must be 'tiny' or 'base', got '{variant}'")

    metrics, patch_log = evaluate.remote(variant=variant, checkpoint_path=checkpoint)

    stem = Path(checkpoint).stem
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    metrics_file = output_path / f"eval_{variant}_{stem}_metrics.json"
    patches_file = output_path / f"eval_{variant}_{stem}_patches.json"

    with open(metrics_file, "w") as f:
        json.dump(metrics, f, indent=2)

    with open(patches_file, "w") as f:
        json.dump(patch_log, f, indent=2)

    print(f"Metrics saved to  : {metrics_file}")
    print(f"Patch log saved to: {patches_file}")