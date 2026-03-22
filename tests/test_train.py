"""Tests for src.apps.train.train — Modal training logic.

Tests the core _train function and config defaults. Modal decorators
are mocked since we don't have a Modal environment in CI.
"""
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
import torch

from src.apps.train.train import DEFAULT_CONFIG, _train


class TestDefaultConfig:
    def test_has_required_keys(self):
        required = [
            "num_epochs", "batch_size", "lr",
            "early_stop_patience", "early_stop_min_delta",
            "imitation_weight", "val_split", "num_workers",
        ]
        for key in required:
            assert key in DEFAULT_CONFIG

    def test_batch_size(self):
        assert DEFAULT_CONFIG["batch_size"] == 32

    def test_learning_rate(self):
        assert DEFAULT_CONFIG["lr"] == 1e-4

    def test_imitation_weight(self):
        assert DEFAULT_CONFIG["imitation_weight"] == 10.0


class TestTrain:
    @patch("src.apps.train.train.volume")
    @patch("src.apps.train.dataset.PatchDataset")
    def test_train_one_epoch(self, MockDataset, mock_volume):
        """Test that _train runs one epoch with a tiny mock dataset."""
        # Create a small fake dataset
        fake_samples = []
        for i in range(8):
            img = torch.randn(3, 224, 224)
            label = i % 2
            weight = 1.0 if label == 1 else 10.0
            fake_samples.append((img, label, weight, "original", f"s3://b/p{i}.jpg"))

        mock_ds = MagicMock()
        mock_ds.__len__ = MagicMock(return_value=len(fake_samples))
        mock_ds.__getitem__ = MagicMock(side_effect=lambda i: fake_samples[i])
        mock_ds.authentic_count = 4
        mock_ds.contrast_count = 4
        MockDataset.return_value = mock_ds

        with tempfile.TemporaryDirectory() as tmpdir:
            env = {
                "AWS_REGION": "us-east-1",
                "DDB_IMAGES_TABLE": "images",
                "DDB_PATCHES_TABLE": "patches",
                "S3_IMAGES_PROCESSED_BUCKET": "proc",
            }
            with patch.dict(os.environ, env):
                with patch("src.apps.train.train.CHECKPOINT_DIR", tmpdir):
                    config = {
                        **DEFAULT_CONFIG,
                        "num_epochs": 1,
                        "batch_size": 4,
                        "num_workers": 0,
                        "val_split": 0.5,
                        "early_stop_patience": 5,
                    }
                    _train(variant="tiny", config=config)

            # Check checkpoint was saved
            ckpt_dir = os.path.join(tmpdir, "tiny")
            assert os.path.exists(os.path.join(ckpt_dir, "epoch_001.pt"))

    @patch("src.apps.train.train.volume")
    @patch("src.apps.train.dataset.PatchDataset")
    def test_early_stopping(self, MockDataset, mock_volume):
        """Test that early stopping triggers after patience is exhausted."""
        fake_samples = [(torch.randn(3, 224, 224), 1, 1.0, "", "p") for _ in range(4)]

        mock_ds = MagicMock()
        mock_ds.__len__ = MagicMock(return_value=4)
        mock_ds.__getitem__ = MagicMock(side_effect=lambda i: fake_samples[i])
        mock_ds.authentic_count = 4
        mock_ds.contrast_count = 0
        MockDataset.return_value = mock_ds

        with tempfile.TemporaryDirectory() as tmpdir:
            env = {
                "AWS_REGION": "us-east-1",
                "DDB_IMAGES_TABLE": "images",
                "DDB_PATCHES_TABLE": "patches",
                "S3_IMAGES_PROCESSED_BUCKET": "proc",
            }
            with patch.dict(os.environ, env):
                with patch("src.apps.train.train.CHECKPOINT_DIR", tmpdir):
                    config = {
                        **DEFAULT_CONFIG,
                        "num_epochs": 100,
                        "batch_size": 4,
                        "num_workers": 0,
                        "val_split": 0.5,
                        "early_stop_patience": 2,
                        "early_stop_min_delta": 1e10,  # impossible to improve
                    }
                    _train(variant="tiny", config=config)

            # Should stop well before 100 epochs
            ckpt_dir = os.path.join(tmpdir, "tiny")
            checkpoints = [f for f in os.listdir(ckpt_dir) if f.startswith("epoch_")]
            assert len(checkpoints) <= 4  # 1 initial + 2 patience + 1 extra
