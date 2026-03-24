"""Tests for src.apps.data_pipeline.schemas — DynamoDB dataclasses.

Validates __post_init__ normalization (dimension clamping, label validation,
sublabel validation, split validation, fold_id clamping), UUID generation,
timestamp generation, and serialization for all six record types.
"""

import uuid
from dataclasses import asdict

from src.apps.data_pipeline.schemas import (
    ConfigRecord,
    ImageRecord,
    InferenceRecord,
    PatchRecord,
    RunRecord,
    User,
)


class TestUser:
    """Tests for the User dataclass."""

    def test_defaults_generate_valid_uuid(self):
        u = User()
        # Must be a valid UUID-4, not just 36 chars
        uuid.UUID(u.user_id)
        assert u.created_at > 0

    def test_two_users_get_distinct_ids(self):
        """Each User() call must produce a unique user_id."""
        a, b = User(), User()
        assert a.user_id != b.user_id

    def test_custom_fields(self):
        u = User(username="alice", email="a@b.com")
        assert u.username == "alice"
        assert u.email == "a@b.com"

    def test_serializable(self):
        d = asdict(User(username="test"))
        assert d["username"] == "test"
        assert "user_id" in d


class TestInferenceRecord:
    """Tests for the InferenceRecord dataclass."""

    def test_defaults(self):
        r = InferenceRecord()
        uuid.UUID(r.inference_id)
        assert r.score == 0.0
        assert r.user_id == ""

    def test_custom_fields(self):
        r = InferenceRecord(user_id="u1", score=0.85)
        assert r.user_id == "u1"
        assert r.score == 0.85


class TestImageRecord:
    """Tests for the ImageRecord dataclass with __post_init__ validation."""

    def test_defaults(self):
        r = ImageRecord()
        assert r.image_width == 0
        assert r.image_height == 0
        assert r.label is None
        assert r.sublabel is None
        assert r.split is None

    def test_all_fields(self):
        r = ImageRecord(
            label="authentic",
            sublabel="original",
            split="train",
            attributed_creator="Vermeer",
            actual_creator="Vermeer",
        )
        assert r.label == "authentic"
        assert r.sublabel == "original"
        assert r.split == "train"

    def test_negative_dimensions_clamped_to_zero(self):
        """__post_init__ clamps width/height to >= 0 to prevent bad DynamoDB data."""
        r = ImageRecord(image_width=-10, image_height=-5)
        assert r.image_width == 0
        assert r.image_height == 0

    def test_invalid_label_set_to_none(self):
        """Labels outside {'authentic', 'inauthentic'} are normalized to None."""
        r = ImageRecord(label="maybe_real")
        assert r.label is None

    def test_valid_labels_preserved(self):
        assert ImageRecord(label="authentic").label == "authentic"
        assert ImageRecord(label="inauthentic").label == "inauthentic"

    def test_invalid_sublabel_set_to_none(self):
        """Sublabels outside {'original', 'forgery', 'imitation', 'proxy'} are normalized."""
        r = ImageRecord(sublabel="unknown_type")
        assert r.sublabel is None

    def test_valid_sublabels_preserved(self):
        for sl in ("original", "forgery", "imitation", "proxy"):
            assert ImageRecord(sublabel=sl).sublabel == sl

    def test_invalid_split_set_to_unassigned(self):
        """Splits outside {'train', 'val', 'test', 'unassigned'} default to 'unassigned'."""
        r = ImageRecord(split="holdout")
        assert r.split == "unassigned"

    def test_valid_splits_preserved(self):
        for sp in ("train", "val", "test", "unassigned"):
            assert ImageRecord(split=sp).split == sp

    def test_negative_fold_id_clamped_to_zero(self):
        """fold_id is clamped to >= 0."""
        r = ImageRecord(fold_id=-3)
        assert r.fold_id == 0

    def test_float_dimensions_converted_to_int(self):
        """Width/height passed as floats are truncated to int."""
        r = ImageRecord(image_width=100.7, image_height=200.9)
        assert r.image_width == 100
        assert r.image_height == 200
        assert isinstance(r.image_width, int)


class TestPatchRecord:
    """Tests for the PatchRecord dataclass."""

    def test_defaults(self):
        r = PatchRecord()
        uuid.UUID(r.patch_id)
        assert r.patch_type == ""
        assert r.patch_x == 0

    def test_serializable(self):
        r = PatchRecord(patch_type="center_crop_orig", patch_x=100, patch_y=200)
        d = asdict(r)
        assert d["patch_type"] == "center_crop_orig"
        assert d["patch_x"] == 100


class TestRunRecord:
    """Tests for the RunRecord dataclass."""

    def test_defaults_match_paper(self):
        """Default seeds and fold count match the Schaerf et al. (2023) paper config."""
        r = RunRecord()
        assert r.status == "running"
        assert r.k_folds == 5
        assert r.stratify_on == "sublabel"
        assert r.outer_split_seed == 17
        assert r.inner_split_seed == 99

    def test_serializable(self):
        r = RunRecord(status="completed", mean_accuracy=0.92)
        d = asdict(r)
        assert d["status"] == "completed"
        assert d["mean_accuracy"] == 0.92


class TestConfigRecord:
    """Tests for the ConfigRecord dataclass."""

    def test_defaults(self):
        r = ConfigRecord()
        assert r.fold_id == 0
        assert r.hyperparameters == {}
        assert r.early_stopped is False
        assert r.is_best_in_fold is False

    def test_with_hyperparameters(self):
        r = ConfigRecord(
            hyperparameters={"lr": 1e-4, "batch_size": 32},
            best_epoch=15,
            is_best_in_fold=True,
        )
        assert r.hyperparameters["lr"] == 1e-4
        assert r.best_epoch == 15

    def test_mutable_default_not_shared(self):
        """Each ConfigRecord must get its own hyperparameters dict (no shared mutable default)."""
        a = ConfigRecord()
        b = ConfigRecord()
        a.hyperparameters["lr"] = 0.01
        assert "lr" not in b.hyperparameters
