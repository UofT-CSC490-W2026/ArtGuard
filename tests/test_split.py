"""Tests for src.apps.data_pipeline.split — deterministic stratified splitting."""

import pytest

from src.apps.data_pipeline.split import (
    _get_stratum_value,
    _group_by_stratum,
    _stable_int,
    all_nested_splits,
    assign_folds,
    train_val_test_splits,
)


def _make_items(n, sublabel="original"):
    """Helper: create n image record dicts with sequential IDs."""
    return [{"image_id": f"img-{i}", "sublabel": sublabel} for i in range(n)]


class TestStableInt:
    """Tests for _stable_int hash function."""

    def test_deterministic(self):
        assert _stable_int(42, "img-001") == _stable_int(42, "img-001")

    def test_different_seeds(self):
        assert _stable_int(1, "img-001") != _stable_int(2, "img-001")

    def test_different_ids(self):
        assert _stable_int(42, "img-001") != _stable_int(42, "img-002")

    def test_salt_changes_result(self):
        assert _stable_int(42, "img-001", "a") != _stable_int(42, "img-001", "b")

    def test_returns_non_negative_int(self):
        result = _stable_int(0, "test")
        assert isinstance(result, int)
        assert result >= 0


class TestGetStratumValue:
    """Tests for _get_stratum_value."""

    def test_present_field(self):
        assert _get_stratum_value({"sublabel": "forgery"}, "sublabel") == "forgery"

    def test_missing_field(self):
        assert _get_stratum_value({}, "sublabel") == "UNKNOWN"

    def test_empty_field(self):
        assert _get_stratum_value({"sublabel": ""}, "sublabel") == "UNKNOWN"

    def test_none_field(self):
        assert _get_stratum_value({"sublabel": None}, "sublabel") == "UNKNOWN"


class TestGroupByStratum:
    """Tests for _group_by_stratum."""

    def test_groups_correctly(self):
        items = [
            {"sublabel": "original"},
            {"sublabel": "forgery"},
            {"sublabel": "original"},
        ]
        groups = _group_by_stratum(items, "sublabel")
        assert len(groups["original"]) == 2
        assert len(groups["forgery"]) == 1

    def test_missing_labels_grouped_as_unknown(self):
        items = [{"sublabel": "original"}, {"other": "field"}]
        groups = _group_by_stratum(items, "sublabel")
        assert "UNKNOWN" in groups
        assert len(groups["UNKNOWN"]) == 1

    def test_empty_input(self):
        groups = _group_by_stratum([], "sublabel")
        assert groups == {}


class TestAssignFolds:
    """Tests for assign_folds."""

    def test_assigns_all_items(self):
        items = _make_items(20)
        assignment = assign_folds(items, k_folds=5, outer_seed=17, inner_seed=99)
        assert len(assignment) == 20

    def test_all_folds_used(self):
        items = _make_items(100)
        assignment = assign_folds(items, k_folds=5, outer_seed=17, inner_seed=99)
        fold_values = set(assignment.values())
        assert fold_values == {0, 1, 2, 3, 4}

    def test_deterministic(self):
        items = _make_items(50)
        a1 = assign_folds(items, k_folds=5, outer_seed=17, inner_seed=99)
        a2 = assign_folds(items, k_folds=5, outer_seed=17, inner_seed=99)
        assert a1 == a2

    def test_different_seed_different_assignment(self):
        items = _make_items(50)
        a1 = assign_folds(items, k_folds=5, outer_seed=17, inner_seed=99)
        a2 = assign_folds(items, k_folds=5, outer_seed=42, inner_seed=99)
        assert a1 != a2

    def test_roughly_balanced(self):
        items = _make_items(100)
        assignment = assign_folds(items, k_folds=5, outer_seed=17, inner_seed=99)
        counts = [0] * 5
        for fold in assignment.values():
            counts[fold] += 1
        assert all(15 <= c <= 25 for c in counts)

    def test_stratified_across_sublabels(self):
        items = _make_items(50, "original") + _make_items(50, "forgery")
        # Give forgery items unique IDs
        for i, it in enumerate(items[50:]):
            it["image_id"] = f"forg-{i}"
        assignment = assign_folds(items, k_folds=5, outer_seed=17, inner_seed=99)
        assert len(assignment) == 100


class TestTrainValTestSplits:
    """Tests for train_val_test_splits."""

    def test_no_overlap(self):
        items = _make_items(50)
        assignment = assign_folds(items, k_folds=5, outer_seed=17, inner_seed=99)
        train, val, test = train_val_test_splits(
            items, assignment, fold_id=0, k_folds=5, inner_seed=99,
        )
        all_ids = set(train) | set(val) | set(test)
        assert len(all_ids) == len(train) + len(val) + len(test)

    def test_covers_all_items(self):
        items = _make_items(50)
        assignment = assign_folds(items, k_folds=5, outer_seed=17, inner_seed=99)
        train, val, test = train_val_test_splits(
            items, assignment, fold_id=0, k_folds=5, inner_seed=99,
        )
        assert len(train) + len(val) + len(test) == 50

    def test_deterministic(self):
        items = _make_items(50)
        assignment = assign_folds(items, k_folds=5, outer_seed=17, inner_seed=99)
        s1 = train_val_test_splits(items, assignment, 0, 5, 99)
        s2 = train_val_test_splits(items, assignment, 0, 5, 99)
        assert s1 == s2


class TestAllNestedSplits:
    """Tests for all_nested_splits."""

    def test_produces_all_folds(self):
        items = _make_items(50)
        assignment = assign_folds(items, k_folds=5, outer_seed=17, inner_seed=99)
        splits = all_nested_splits(items, assignment, k_folds=5, inner_seed=99)
        assert set(splits.keys()) == {0, 1, 2, 3, 4}
        for fold_data in splits.values():
            assert "train" in fold_data
            assert "val" in fold_data
            assert "test" in fold_data

    def test_each_item_tested_exactly_once(self):
        items = _make_items(50)
        assignment = assign_folds(items, k_folds=5, outer_seed=17, inner_seed=99)
        splits = all_nested_splits(items, assignment, k_folds=5, inner_seed=99)
        all_test_ids = []
        for fold_data in splits.values():
            all_test_ids.extend(fold_data["test"])
        assert len(all_test_ids) == 50
        assert len(set(all_test_ids)) == 50
