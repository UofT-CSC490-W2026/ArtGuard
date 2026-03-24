#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/_colors.sh"

# Run ArtGuard Benchmarks
#
# Reproduces the full training + evaluation pipeline and records results.
# Based on: "Art Authentication with Vision Transformers" (Schaerf et al., 2023)
#
# Prerequisites:
#   - Modal account with `artguard-aws` secret configured
#   - Training data uploaded to S3 (via scripts/update-data.sh)
#   - DynamoDB tables populated with image metadata
#
# Usage:
#   ./scripts/run-benchmarks.sh [variant]
#
# Examples:
#   ./scripts/run-benchmarks.sh tiny           # Train + evaluate Swin-Tiny
#   ./scripts/run-benchmarks.sh base           # Train + evaluate Swin-Base
#   ./scripts/run-benchmarks.sh                # Both variants (default)
#   ./scripts/run-benchmarks.sh tiny eval      # Evaluate only (checkpoint must exist)
#   ./scripts/run-benchmarks.sh tiny train     # Train only (skip evaluation)
#
# Modes:
#   both  (default) — train then evaluate
#   train           — train only, skip evaluation
#   eval            — evaluate only, requires existing checkpoint on Modal Volume
#
# Output:
#   Results saved to benchmarks/ directory as JSON files

VARIANT=${1:-all}
MODE=${2:-both}
OUTPUT_DIR="benchmarks"
mkdir -p "$OUTPUT_DIR"

if [[ "$MODE" != "both" && "$MODE" != "train" && "$MODE" != "eval" ]]; then
  error "Invalid mode: $MODE (must be 'both', 'train', or 'eval')"
  echo -e "  Usage: ${GREEN}./scripts/run-benchmarks.sh [tiny|base|all] [both|train|eval]${NC}"
  exit 1
fi

header "ArtGuard Benchmark Suite"
echo -e "  Variant:    ${CYAN}$VARIANT${NC}"
echo -e "  Mode:       ${CYAN}$MODE${NC}"
echo -e "  Output dir: ${CYAN}$OUTPUT_DIR${NC}"
echo ""
if [ "$MODE" = "both" ]; then
  echo -e "This will:"
  echo -e "  ${DIM}1. Train the Swin model(s) on Modal GPUs${NC}"
  echo -e "  ${DIM}2. Evaluate on the held-out test set${NC}"
  echo -e "  ${DIM}3. Save metrics (accuracy, F1, AUC, confusion matrix)${NC}"
elif [ "$MODE" = "train" ]; then
  echo -e "This will train the model(s) only (no evaluation)."
elif [ "$MODE" = "eval" ]; then
  echo -e "This will evaluate existing checkpoint(s) only (no training)."
fi
echo ""

# Step 1: Train
train_variant() {
  local v=$1
  step "Training Swin-${v^}..."
  echo -e "  ${DIM}This runs on Modal A10G GPUs with early stopping.${NC}"
  echo -e "  ${DIM}Config: lr=1e-4, batch_size=32, patience=20, k_folds=5${NC}"
  echo ""

  modal run src/apps/train/train.py::train_swin_${v}

  echo ""
  success "Training complete for Swin-${v^}."
  info "Checkpoints saved to Modal Volume: /checkpoints/${v}/"
  echo ""
}

# Step 2: Evaluate
eval_variant() {
  local v=$1
  step "Evaluating Swin-${v^} on test split..."
  echo -e "  Checkpoint: ${CYAN}/checkpoints/${v}/best.pt${NC}"
  echo ""

  modal run src/apps/train/evaluate.py \
    --variant "$v" \
    --checkpoint "/checkpoints/${v}/best.pt" \
    --output-dir "$OUTPUT_DIR"

  echo ""
  success "Evaluation complete. Results:"
  echo -e "  Metrics: ${GREEN}${OUTPUT_DIR}/eval_${v}_best_metrics.json${NC}"
  echo -e "  Patches: ${GREEN}${OUTPUT_DIR}/eval_${v}_best_patches.json${NC}"
  echo ""
}

run_variant() {
  local v=$1
  if [ "$MODE" = "both" ] || [ "$MODE" = "train" ]; then
    train_variant "$v"
  fi
  if [ "$MODE" = "both" ] || [ "$MODE" = "eval" ]; then
    eval_variant "$v"
  fi
}

if [ "$VARIANT" = "tiny" ] || [ "$VARIANT" = "all" ]; then
  run_variant "tiny"
fi

if [ "$VARIANT" = "base" ] || [ "$VARIANT" = "all" ]; then
  run_variant "base"
fi

# Step 3: Summary
header "Benchmark Complete"
echo ""
success "Results saved to: $OUTPUT_DIR/"
ls -la "$OUTPUT_DIR"/*.json 2>/dev/null || warn "(no JSON files found — check Modal logs)"
echo ""
echo -e "To view metrics:"
echo -e "  ${GREEN}cat ${OUTPUT_DIR}/eval_tiny_best_metrics.json | python3 -m json.tool${NC}"
echo ""
info "Reproducibility:"
echo -e "  ${DIM}- Seeds: outer_split_seed=17, inner_split_seed=99${NC}"
echo -e "  ${DIM}- Config: lr=1e-4, batch_size=32, early_stop_patience=20${NC}"
echo -e "  ${DIM}- Data splits are deterministic via SHA-256 hashing (split.py)${NC}"
echo -e "  ${DIM}- Same seeds + same data = identical train/val/test assignments${NC}"
