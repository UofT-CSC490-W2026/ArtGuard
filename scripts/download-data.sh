#!/bin/bash
set -e

# Download training/test/val data from Google Drive
# Usage: ./scripts/download-data.sh
#
# Prerequisites: gdown (pip install gdown)
#
# After running, you should have:
#   data/train/class_0/  — forgery images
#   data/train/class_1/  — authentic images
#   data/test/...
#   data/val/...

source "$(dirname "$0")/_colors.sh" 2>/dev/null || true

# ── Configuration ─────────────────────────────────────────────────
GDRIVE_FILE_ID="1-VELhmPI-4uAOl4bY9Bh33UktfWrS-Oo"
ZIP_NAME="data.zip"
DEST_DIR="data"
# ──────────────────────────────────────────────────────────────────

if [ "$GDRIVE_FILE_ID" = "REPLACE_WITH_YOUR_GOOGLE_DRIVE_FILE_ID" ]; then
  echo "ERROR: Edit this script and set GDRIVE_FILE_ID first."
  echo "  1. Zip your data/ folder and upload to Google Drive"
  echo "  2. Share the file (anyone with the link)"
  echo "  3. Copy the file ID from the share URL"
  echo "  4. Paste it into GDRIVE_FILE_ID in this script"
  exit 1
fi

if [ -d "$DEST_DIR/train" ] && [ -d "$DEST_DIR/test" ]; then
  echo "data/ already exists. Delete it first to re-download."
  exit 0
fi

# Check for gdown
if ! command -v gdown &>/dev/null; then
  echo "Installing gdown..."
  pip install gdown
fi

echo "Downloading data from Google Drive..."
gdown "$GDRIVE_FILE_ID" -O "$ZIP_NAME"

echo "Extracting..."
unzip -q "$ZIP_NAME" -d .

# Clean up
rm -f "$ZIP_NAME"

echo "Done. Data available at ./$DEST_DIR/"
ls -d "$DEST_DIR"/*/ 2>/dev/null
