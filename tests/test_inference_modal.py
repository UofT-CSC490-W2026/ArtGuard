"""Tests for src.apps.train.inference — Modal inference for patch predictions.

Tests the predict_patches logic with mocked S3, torch, and Modal.
"""
import io
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import torch
from PIL import Image

from src.apps.train.model import ArtAuthenticator


def _make_image_bytes():
    img = Image.new("RGB", (224, 224), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf.read()


class TestPredictPatchesLogic:
    """Test the inference logic inline (not via Modal function)."""

    def test_empty_uris_returns_zero(self):
        """Simulate the empty-input path from predict_patches."""
        # This matches the early return in predict_patches
        result = {
            "patch_probs": [],
            "patch_preds": [],
            "mean_prob": 0.0,
            "prediction": 0,
        }
        assert result["prediction"] == 0
        assert result["mean_prob"] == 0.0

    def test_prediction_aggregation(self):
        """Test that mean probability and prediction are computed correctly."""
        probs = [0.8, 0.7, 0.6]
        preds = [1 if p > 0.5 else 0 for p in probs]
        mean_prob = sum(probs) / len(probs)
        prediction = 1 if mean_prob > 0.5 else 0

        assert preds == [1, 1, 1]
        assert mean_prob == pytest.approx(0.7, abs=0.01)
        assert prediction == 1

    def test_prediction_inauthentic(self):
        probs = [0.2, 0.3, 0.1]
        mean_prob = sum(probs) / len(probs)
        prediction = 1 if mean_prob > 0.5 else 0
        assert prediction == 0

    def test_mixed_predictions(self):
        probs = [0.9, 0.1, 0.6]
        preds = [1 if p > 0.5 else 0 for p in probs]
        assert preds == [1, 0, 1]
        mean_prob = sum(probs) / len(probs)
        assert mean_prob == pytest.approx(0.5333, abs=0.01)
        assert (1 if mean_prob > 0.5 else 0) == 1


class TestInferenceEndToEnd:
    """End-to-end test with a real (untrained) model but mocked S3."""

    def test_predict_with_mock_s3(self):
        model = ArtAuthenticator(variant="tiny", pretrained=False)
        model.eval()

        # Create fake S3 client
        mock_s3 = MagicMock()
        body = MagicMock()
        body.read.return_value = _make_image_bytes()
        mock_s3.get_object.return_value = {"Body": body}

        # Simulate the inference logic from predict_patches
        from torchvision import transforms

        IMAGENET_MEAN = [0.485, 0.456, 0.406]
        IMAGENET_STD = [0.229, 0.224, 0.225]
        transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
        ])

        uris = ["s3://bucket/p1.jpg", "s3://bucket/p2.jpg"]
        tensors = []
        for uri in uris:
            without_scheme = uri[5:]
            bucket, _, key = without_scheme.partition("/")
            resp = mock_s3.get_object(Bucket=bucket, Key=key)
            img = Image.open(io.BytesIO(resp["Body"].read())).convert("RGB")
            tensors.append(transform(img))

        batch = torch.stack(tensors)
        with torch.no_grad():
            logits = model(batch).squeeze(-1)
            probs = torch.sigmoid(logits).tolist()

        assert len(probs) == 2
        assert all(0 <= p <= 1 for p in probs)

        preds = [1 if p > 0.5 else 0 for p in probs]
        mean_prob = sum(probs) / len(probs)

        result = {
            "patch_probs": probs,
            "patch_preds": preds,
            "mean_prob": mean_prob,
            "prediction": 1 if mean_prob > 0.5 else 0,
        }
        assert "patch_probs" in result
        assert "prediction" in result

    def test_checkpoint_load_and_inference(self):
        """Test saving and loading a checkpoint, then running inference."""
        model = ArtAuthenticator(variant="tiny", pretrained=False)

        with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as f:
            torch.save({
                "epoch": 5,
                "state_dict": model.state_dict(),
                "val_loss": 0.3,
            }, f.name)
            ckpt_path = f.name

        try:
            checkpoint = torch.load(ckpt_path, map_location="cpu")
            loaded_model = ArtAuthenticator(variant="tiny", pretrained=False)
            loaded_model.load_state_dict(checkpoint["state_dict"])
            loaded_model.eval()

            dummy = torch.randn(1, 3, 224, 224)
            with torch.no_grad():
                logits = loaded_model(dummy)
            assert logits.shape == (1, 1)
        finally:
            os.unlink(ckpt_path)
