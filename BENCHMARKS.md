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
| **Swin-Tiny** | Swin-T | ImageNet-1K | 28M | He-normal init, 768 -> 1 |
| **Swin-Base** | Swin-B | ImageNet-1K | 88M | He-normal init, 1024 -> 1 |

Both variants use **full fine-tuning** (variant iii from the paper) — all layers are unfrozen, with only the classification head randomly initialised using He normal.

### Preprocessing Pipeline

Images are processed following the paper's approach:

1. **Grid splitting**: Images are divided into an NxN grid based on resolution:
   - min side > 1024px: 4x4 grid (16 cells)
   - min side > 512px: 2x2 grid (4 cells)
   - otherwise: 2x2 grid

2. **Patch extraction**: Each grid cell produces two 224x224 patches:
   - **Center crop**: Take the central 224x224 region (if cell is large enough)
   - **Bicubic downsample**: Resize the full cell to 224x224

3. **Normalisation**: ImageNet mean/std normalisation applied to all patches

4. **Training augmentation**: Random horizontal flip (validation/test: no augmentation)

---

## Training Configuration

Hyperparameters follow the paper (Section 3.3):

| Parameter | Value | Source |
|-----------|-------|--------|
| Optimiser | Adam | Paper Section 3.3 |
| Learning rate | 1e-4 | Paper Section 3.3 |
| Batch size | 32 | Paper Section 3.3 |
| Loss function | BCEWithLogitsLoss | Paper Section 3.3 |
| Imitation weight (wim) | 10.0 | Paper Section 3.2 |
| Max epochs | 100 | |
| Early stopping patience | 20 epochs | |
| Early stopping min delta | 1e-3 | |
| Validation split | 10% | |

Training runs on **Modal A10G GPUs** with checkpoints saved to a persistent Modal Volume after each epoch. The best checkpoint (lowest validation loss) is saved as `best.pt`.

---

## Data Split Strategy

Data splitting is **deterministic and stratified**, implemented in `src/apps/data_pipeline/split.py`:

### Outer Split (K-Fold Cross-Validation)

- **K = 5** outer folds
- **Stratified by sublabel**: Each fold preserves the ratio of `original` / `forgery` / `imitation` samples
- **Deterministic**: Uses SHA-256 hashing keyed by `(outer_split_seed=17, image_id)` — no dependency on item ordering

### Inner Split (Train/Validation)

- Within each outer fold's training pool, **20% is held out for validation**
- Also stratified by sublabel
- Deterministic via `(inner_split_seed=99, fold_id, image_id)` hashing

### Label Convention

| Label | Value | Description |
|-------|-------|-------------|
| Authentic | 1 | Original artwork by the attributed artist |
| Inauthentic | 0 | Forgery, imitation, or proxy |

| Sublabel | Description | Sample Weight |
|----------|-------------|---------------|
| `original` | Genuine artwork | 1.0 |
| `forgery` | Human-made fake | 10.0 (wim) |
| `imitation` | AI-generated imitation | 10.0 (wim) |
| `proxy` | Proxy artwork | 10.0 (wim) |

### Reproducibility Guarantee

```python
# Same seeds + same dataset = identical splits every time
assignment = assign_folds(items, k_folds=5, outer_seed=17, inner_seed=99)
train_ids, val_ids, test_ids = train_val_test_splits(
    items, assignment, fold_id=0, k_folds=5, inner_seed=99,
)
```

The splitting algorithm uses SHA-256 hashing (not random shuffling), so:
- Order of items in the database does not affect the split
- Adding new items does not change existing assignments
- Results are reproducible across machines and Python versions

---

## How to Reproduce

### A note on data

Training images are **not** stored in the Git repo (they are ~2.1 GB). They are already uploaded to S3 via the data pipeline, and model weights are stored on a Modal volume (`artguard-checkpoints/tiny/best.pt`).

**You do not need the raw images to clone, deploy, or run inference.** The deployed app works end-to-end without them.

If you want to retrain or inspect the dataset locally, run:

```bash
./scripts/download-data.sh
```

This downloads the dataset zip from Google Drive and extracts it to `data/`. See `scripts/README.md` for details.

### Prerequisites

1. **Modal account** with `artguard-aws` secret configured (AWS credentials for S3/DynamoDB access)
2. **Training data** uploaded to S3 via `scripts/update-data.sh` (already done — only needed if re-uploading)
3. **DynamoDB tables** populated with image metadata (label, sublabel, split fields set)

### Run Training + Evaluation

```bash
# Both variants
./scripts/run-benchmarks.sh

# Or individually
./scripts/run-benchmarks.sh tiny
./scripts/run-benchmarks.sh base
```

### Run Evaluation Only (existing checkpoint)

```bash
# Evaluate Swin-Tiny against the test split
modal run src/apps/train/evaluate.py \
  --variant tiny \
  --checkpoint /checkpoints/tiny/best.pt \
  --output-dir benchmarks/
```

### Run Training Only

```bash
# Train Swin-Tiny
modal run src/apps/train/train.py::train_swin_tiny

# Train Swin-Base
modal run src/apps/train/train.py::train_swin_base

# Both in parallel
modal run src/apps/train/train.py
```

### Output Files

After evaluation, results are saved as JSON:

```
benchmarks/
├── eval_tiny_best_metrics.json   # Aggregated metrics
└── eval_tiny_best_patches.json   # Per-patch prediction log
```

### View Results

```bash
cat benchmarks/eval_tiny_best_metrics.json | python3 -m json.tool
```

---

## Evaluation Methodology

Evaluation (`src/apps/train/evaluate.py`) computes metrics at two levels:

### Patch-Level Metrics

Each 224x224 patch is classified independently. Metrics computed:
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
