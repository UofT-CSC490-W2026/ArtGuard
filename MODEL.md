# ArtGuard Benchmarks

Model evaluation results and reproducibility instructions for the art forgery detection system.

Based on: *"Art Authentication with Vision Transformers"* (Schaerf et al., 2023) — [arXiv:2307.03039](https://arxiv.org/abs/2307.03039)

---

## Table of Contents

1. [Model Architecture](#model-architecture)
2. [Training Configuration](#training-configuration)
3. [Data Split Strategy](#data-split-strategy)
4. [How to Reproduce](#how-to-reproduce)
5. [Evaluation Methodology](#evaluation-methodology)

---

## Model Architecture

We implement two variants from the paper:

| Variant | Backbone | Pretrained On | Parameters | Classification Head |
|---------|----------|---------------|------------|-------------------|
| **Swin-Tiny** | Swin-T | ImageNet-1K | 28M | He-normal init, 768 → 1 |
| **Swin-Base** | Swin-B | ImageNet-1K | 88M | He-normal init, 1024 → 1 |

Both variants use **full fine-tuning** (variant iii from the paper) — all layers are unfrozen, with only the classification head randomly initialised using He normal.

### Preprocessing Pipeline

Images are processed following the paper's approach:

1. **Grid splitting**: Images are divided into an N×N grid based on resolution:
   - min side > 1024px: 4×4 grid (16 cells)
   - min side > 512px: 2×2 grid (4 cells)
   - otherwise: 2×2 grid

2. **Patch extraction**: Each grid cell produces two 224×224 patches:
   - **Center crop**: Take the central 224×224 region (if the cell is large enough)
   - **Bicubic downsample**: Resize the full cell to 224×224

3. **Normalisation**: ImageNet mean/std normalisation applied to all patches

4. **Training augmentation**: Random horizontal flip (validation/test: no augmentation)

---

## Training Configuration

Implementation: `src/apps/train/train.py` (Modal app `artguard-training`). Default hyperparameters are defined in `DEFAULT_CONFIG`.

Hyperparameters aligned with the paper (Sections 3.2–3.3) plus training-loop extras:

| Parameter | Default | Notes |
|-----------|---------|--------|
| Optimiser | Adam | Via `ArtAuthenticator.configure_optimizer` |
| Learning rate | 1e-4 | Paper Section 3.3 |
| LR scheduler | `ReduceLROnPlateau` | `mode=min`, `factor=0.5`, `patience=5`, `min_lr=1e-6`, stepped on validation loss |
| Batch size | 32 | Paper Section 3.3 |
| Training loss | Weighted BCE with logits | `BCEWithLogitsLoss(reduction="none")`, then sample-weighted mean (see [Data Split Strategy](#data-split-strategy)) |
| Validation loss | Unweighted mean BCE | Same logits loss, **no** per-sample weights on the val set |
| Imitation / contrast weight (w_im) | 10.0 | Applied to **all** inauthentic (label 0) training samples; authentic = 1.0 |
| Max epochs | 50 | Upper bound before early stop |
| Early stopping | patience 10 epochs | Triggers when validation loss does not beat the best by more than `early_stop_min_delta` (1e-3) |
| Fallback val fraction | 0.1 | Only used when split-based train/val is empty (see below) |

Training runs on **Modal A10G** GPUs. Checkpoint directory on the volume: `/checkpoints/{tiny|base}/`.

- Each epoch writes `epoch_{NNN}.pt` (full state dict + optimizer state + metrics).
- When validation loss improves (by at least `early_stop_min_delta`), `best.pt` is written (state dict + val metrics + config snapshot).

Optional **Weights & Biases** logging uses the `artguard-wandb` secret (`WANDB_API_KEY`); if init fails, training continues without W&B.

---

## Data Split Strategy

### Runtime behaviour (`PatchDataset` + `train.py`)

Training reads **patch rows from DynamoDB** (Images + Patches) and **filters by the ImageRecord `split` field**:

1. **Preferred path**: Build a separate `PatchDataset` for `split="train"` and `split="val"`. Patches inherit their parent image’s split.
2. **Fallback**: If either dataset is empty (e.g. legacy data without `split` set), the code loads all patches into one dataset and uses PyTorch `random_split` with fraction `val_split` from config (default **10%** validation).

Evaluation (`src/apps/train/evaluate.py`) loads `split="test"` only; it errors if that set is empty.

### Schema context (DynamoDB)

`ImageRecord` supports `split` (`train` / `val` / `test` / `unassigned`) and `fold_id` for cross-validation-style metadata (see `DATA.md`). The **Modal training loop** consumes `split` as above; it does not iterate outer folds by `fold_id`.

### Label convention

| Label | Value | Description |
|-------|-------|-------------|
| Authentic | 1 | Original artwork by the attributed artist |
| Inauthentic | 0 | Forgery, imitation, or proxy |

### Sample weights (training)

Weights are **binary** (authentic vs inauthentic), matching the paper’s emphasis on up-weighting the contrast set:

| Condition | Training weight |
|-----------|-----------------|
| Authentic (`label == 1`) | 1.0 |
| Inauthentic (`label == 0`) | `imitation_weight` (default 10.0, paper w_im) |

| Sublabel | Description | Sample Weight |
|----------|-------------|---------------|
| `original` | Genuine artwork | 1.0 |
| `forgery` | Human-made fake | 10.0 (wim) |
| `imitation` | AI-generated imitation | 10.0 (wim) |
| `proxy` | Proxy artwork | 10.0 (wim) |

### Reproducibility

- With **train/val/test** assigned in DynamoDB, splits are stable and ordering-independent for a given dataset.
- If the code falls back to `random_split`, repeatability depends on PyTorch RNG unless you fix seeds separately (not done in `train.py` today).

---

## How to Reproduce

### A note on data

Training images are **not** stored in the Git repo (they are large). They are expected in S3 via the data pipeline, with metadata in DynamoDB. Model weights are stored on the Modal volume (`artguard-checkpoints`, paths under `/checkpoints/{variant}/`). If you would like to use our model weights to reproduce the exact same model, the weights can be downloaded from the following link: https://drive.google.com/file/d/1hoLMyUZWo_eTzAJfs1i6vmw9P87Tg4Gn/view?usp=sharing.

**You do not need the raw images to clone, deploy, or run inference** if your backend only serves inference. Retraining requires AWS access to the Images/Patches tables and processed bucket.

If you want to download or inspect the dataset locally:

```bash
./scripts/download-data.sh
```

See `scripts/README.md` for details.

### Prerequisites

1. **Modal account** with `artguard-aws` secret: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `DDB_IMAGES_TABLE`, `DDB_PATCHES_TABLE`, `S3_IMAGES_PROCESSED_BUCKET`
2. Optional: `artguard-wandb` with `WANDB_API_KEY` for experiment tracking
3. DynamoDB ImageRecords with `split` populated for train/val (and test for evaluation), and Patches rows for each image

### Run Training + Evaluation

```bash
# Both variants (train then evaluate)
./scripts/run-benchmarks.sh

# Or individually
./scripts/run-benchmarks.sh tiny
./scripts/run-benchmarks.sh base

# Evaluate only (checkpoint must exist on the volume)
./scripts/run-benchmarks.sh tiny eval
```

### Run Training Only

```bash
modal run src/apps/train/train.py::train_swin_tiny
modal run src/apps/train/train.py::train_swin_base

# Local entrypoint: both variants in parallel
modal run src/apps/train/train.py
```

The API can also start training via `POST /train` (`src/apps/backend/routes/train_router.py`), merging optional JSON overrides into `train.py`’s `DEFAULT_CONFIG`.

### Run Evaluation Only (existing checkpoint)

```bash
modal run src/apps/train/evaluate.py \
  --variant tiny \
  --checkpoint /checkpoints/tiny/best.pt \
  --output-dir benchmarks/
```

### Output Files

After evaluation, results are saved as JSON (checkpoint filename stem appears in the name, e.g. `best` for `best.pt`):

```
benchmarks/
├── eval_tiny_best_metrics.json   # Aggregated metrics
├── eval_tiny_best_patches.json   # Per-patch prediction log
└── eval_tiny_best_images.json    # Painting-level aggregation log
```

### View Results

```bash
cat benchmarks/eval_tiny_best_metrics.json | python3 -m json.tool
```

---

## Evaluation Methodology

Evaluation (`src/apps/train/evaluate.py`) computes metrics at two levels:

### Patch-Level Metrics

Each 224×224 patch is classified independently. Metrics computed:

- **Accuracy**: Overall correct predictions / total patches
- **Precision**: True positives / (true positives + false positives)
- **Recall**: True positives / (true positives + false negatives)
- **F1 Score**: Harmonic mean of precision and recall
- **Confusion Matrix**: [[TN, FP], [FN, TP]]

### Painting-Level Metrics

Patch predictions are aggregated per painting by averaging probabilities:

- For each painting: `mean_prob = average(patch_probabilities)`
- Painting prediction: `1 (authentic)` if `mean_prob > 0.5`, else `0 (forgery)`
- Same metrics (accuracy, precision, recall, F1, confusion matrix) computed on painting-level predictions

### Sublabel Breakdown

All metrics are computed **overall** and **broken down by sublabel** (original, forgery, imitation, proxy) to identify where the model performs well or struggles — matching the paper's analysis approach.

### Example Metrics Output

```json
{
  "variant": "tiny",
  "checkpoint": "/checkpoints/tiny/best.pt",
  "trained_epoch": 42,
  "patch_level": {
    "overall": {
      "n": 1250,
      "accuracy": 0.89,
      "precision": 0.91,
      "recall": 0.87,
      "f1": 0.89,
      "confusion_matrix": [[540, 55], [82, 573]]
    },
    "by_sublabel": {
      "original": { "n": 600, "accuracy": 0.92, "...": "..." },
      "forgery":  { "n": 400, "accuracy": 0.86, "...": "..." },
      "imitation":{ "n": 250, "accuracy": 0.88, "...": "..." }
    }
  },
  "painting_level": {
    "overall": {
      "n": 50,
      "accuracy": 0.94,
      "...": "..."
    }
  }
}
```

*Note: The metrics above are illustrative. Actual results depend on the dataset used.*
