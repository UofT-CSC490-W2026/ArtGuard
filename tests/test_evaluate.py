"""Tests for src.apps.train.evaluate — evaluation metrics and logic.

Tests the metric computation helpers directly (no GPU/Modal needed).
Requires scikit-learn and torch — skipped entirely if not installed (e.g. GitHub Actions CI).
"""
import os

import pytest
from unittest.mock import patch

pytest.importorskip("sklearn")
pytest.importorskip("torch")


class TestComputeMetrics:
    def test_empty_labels(self):
        from src.apps.train.evaluate import _compute_metrics
        result = _compute_metrics([], [])
        assert result["n"] == 0
        assert result["accuracy"] is None
        assert result["precision"] is None
        assert result["recall"] is None
        assert result["f1"] is None
        assert result["confusion_matrix"] is None

    def test_perfect_predictions(self):
        from src.apps.train.evaluate import _compute_metrics
        labels = [0, 0, 1, 1]
        preds = [0, 0, 1, 1]
        result = _compute_metrics(labels, preds)
        assert result["n"] == 4
        assert result["accuracy"] == 1.0
        assert result["precision"] == 1.0
        assert result["recall"] == 1.0
        assert result["f1"] == 1.0
        # [[TN, FP], [FN, TP]]
        assert result["confusion_matrix"] == [[2, 0], [0, 2]]

    def test_all_wrong(self):
        from src.apps.train.evaluate import _compute_metrics
        labels = [0, 0, 1, 1]
        preds = [1, 1, 0, 0]
        result = _compute_metrics(labels, preds)
        assert result["accuracy"] == 0.0
        assert result["confusion_matrix"] == [[0, 2], [2, 0]]

    def test_mixed_predictions(self):
        from src.apps.train.evaluate import _compute_metrics
        labels = [0, 0, 1, 1, 1]
        preds = [0, 1, 1, 1, 0]
        result = _compute_metrics(labels, preds)
        assert result["n"] == 5
        assert 0 < result["accuracy"] < 1
        assert result["confusion_matrix"] is not None

    def test_all_same_class(self):
        from src.apps.train.evaluate import _compute_metrics
        labels = [1, 1, 1]
        preds = [1, 1, 0]
        result = _compute_metrics(labels, preds)
        assert result["n"] == 3
        assert result["recall"] == pytest.approx(2 / 3)


class TestPrintMetrics:
    def test_empty_metrics(self, capsys):
        from src.apps.train.evaluate import _print_metrics
        _print_metrics("Test", {"n": 0})
        output = capsys.readouterr().out
        assert "no samples" in output

    def test_normal_metrics(self, capsys):
        from src.apps.train.evaluate import _print_metrics
        m = {
            "n": 10,
            "accuracy": 0.9,
            "precision": 0.85,
            "recall": 0.95,
            "f1": 0.8974,
            "confusion_matrix": [[4, 1], [0, 5]],
        }
        _print_metrics("Overall", m)
        output = capsys.readouterr().out
        assert "Overall" in output
        assert "0.9000" in output
        assert "TN=" in output
        assert "TP=" in output


class TestEvaluateErrorPaths:
    """Test _evaluate error handling."""

    @pytest.fixture(autouse=True)
    def _skip_no_torch(self):
        pytest.importorskip("torch")

    def test_checkpoint_not_found(self):
        from src.apps.train.evaluate import _evaluate
        with pytest.raises(FileNotFoundError, match="Checkpoint not found"):
            _evaluate(variant="tiny", checkpoint_path="/nonexistent/best.pt")

    @patch.dict(os.environ, {
        "AWS_REGION": "us-east-1",
        "DDB_IMAGES_TABLE": "images",
        "DDB_PATCHES_TABLE": "patches",
        "S3_IMAGES_PROCESSED_BUCKET": "proc",
    })
    def test_empty_test_dataset(self, tmp_path):
        import torch
        from unittest.mock import MagicMock
        from src.apps.train.evaluate import _evaluate
        from src.apps.train.model import ArtAuthenticator

        model = ArtAuthenticator(variant="tiny", pretrained=False)
        ckpt_file = tmp_path / "best.pt"
        torch.save({
            "epoch": 1,
            "state_dict": model.state_dict(),
            "val_loss": 0.5,
            "val_acc": 0.8,
            "config": {},
        }, ckpt_file)

        mock_ds = MagicMock()
        mock_ds.__len__ = MagicMock(return_value=0)
        mock_ds.authentic_count = 0
        mock_ds.contrast_count = 0
        mock_ds.sublabel_counts = {}

        with patch("src.apps.train.dataset.PatchDataset", return_value=mock_ds):
            with pytest.raises(RuntimeError, match="Test dataset is empty"):
                _evaluate(variant="tiny", checkpoint_path=str(ckpt_file))


class TestEvaluateFunction:
    """Test _evaluate with real torch but mocked AWS/dataset.

    Requires torch — skipped if not installed.
    """

    @pytest.fixture(autouse=True)
    def _skip_no_torch(self):
        pytest.importorskip("torch")

    @patch.dict(os.environ, {
        "AWS_REGION": "us-east-1",
        "DDB_IMAGES_TABLE": "images",
        "DDB_PATCHES_TABLE": "patches",
        "S3_IMAGES_PROCESSED_BUCKET": "proc",
    })
    def test_evaluate_returns_metrics(self, tmp_path):
        import torch
        from unittest.mock import MagicMock

        from src.apps.train.evaluate import _evaluate
        from src.apps.train.model import ArtAuthenticator

        # Create a real model and save a checkpoint
        model = ArtAuthenticator(variant="tiny", pretrained=False)
        ckpt_file = tmp_path / "best.pt"
        torch.save({
            "epoch": 1,
            "state_dict": model.state_dict(),
            "val_loss": 0.5,
            "val_acc": 0.8,
            "config": {},
        }, ckpt_file)

        # Mock PatchDataset to return fake data
        fake_imgs = torch.randn(4, 3, 224, 224)
        fake_labels = torch.tensor([0, 0, 1, 1])
        fake_weights = torch.tensor([10.0, 10.0, 1.0, 1.0])
        fake_sublabels = ["forgery", "forgery", "original", "original"]
        fake_paths = [
            "s3://b/img1/p1.jpg", "s3://b/img1/p2.jpg",
            "s3://b/img2/p3.jpg", "s3://b/img2/p4.jpg",
        ]

        mock_ds = MagicMock()
        mock_ds.__len__ = MagicMock(return_value=4)
        mock_ds.__getitem__ = MagicMock(
            side_effect=lambda i: (
                fake_imgs[i], fake_labels[i], fake_weights[i],
                fake_sublabels[i], fake_paths[i],
            )
        )
        mock_ds.authentic_count = 2
        mock_ds.contrast_count = 2
        mock_ds.sublabel_counts = {"original": 2, "forgery": 2}

        # Patch DataLoader to use num_workers=0 (MagicMock can't be pickled)
        from torch.utils.data import DataLoader as RealDataLoader

        def patched_dataloader(*args, **kwargs):
            kwargs["num_workers"] = 0
            return RealDataLoader(*args, **kwargs)

        with patch("src.apps.train.dataset.PatchDataset", return_value=mock_ds), \
             patch("torch.utils.data.DataLoader", side_effect=patched_dataloader):
            metrics, patch_log = _evaluate(
                variant="tiny", checkpoint_path=str(ckpt_file),
            )

        assert metrics["variant"] == "tiny"
        assert "patch_level" in metrics
        assert "painting_level" in metrics
        assert isinstance(patch_log, list)
        assert len(patch_log) == 4
