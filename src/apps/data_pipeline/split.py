"""Deterministic, stratified data splitting for k-fold cross-validation.

Provides functions to assign images to outer folds and produce
train/val/test splits that are:
- **Deterministic**: Same seeds always produce the same splits.
- **Stratified**: Each split preserves the ratio of sublabels
  (original / forgery / imitation).

Uses SHA-256 hashing keyed by (seed, image_id) to avoid any dependency
on item ordering.
"""

from __future__ import annotations

import hashlib
from typing import Dict, List, Tuple


def _stable_int(seed: int, image_id: str, salt: str = "") -> int:
    """Compute a deterministic integer hash from a seed, image_id, and optional salt.

    Uses SHA-256 to produce a stable ordering of items that is reproducible
    across runs, regardless of insertion order.

    >>> _stable_int(42, "img-001")
    70762790482105753
    >>> _stable_int(42, "img-001") == _stable_int(42, "img-001")
    True
    >>> _stable_int(42, "img-001") != _stable_int(99, "img-001")
    True

    Args:
        seed:     Integer seed for reproducibility.
        image_id: The image's unique identifier.
        salt:     Optional additional string to differentiate contexts.

    Returns:
        A deterministic non-negative integer.
    """
    msg = f"{seed}:{salt}:{image_id}".encode("utf-8")
    h = hashlib.sha256(msg).hexdigest()
    return int(h[:16], 16)


def _get_stratum_value(item: dict, stratify_on: str) -> str:
    """Extract the stratification group from an image record.

    Returns ``"UNKNOWN"`` if the stratification field is missing or empty.

    >>> _get_stratum_value({"sublabel": "forgery"}, "sublabel")
    'forgery'
    >>> _get_stratum_value({}, "sublabel")
    'UNKNOWN'

    Args:
        item:         A dict representing an ImageRecord.
        stratify_on:  The field name to stratify on (e.g. ``"sublabel"``).

    Returns:
        The stratum value as a string.
    """
    sublabel = item.get(stratify_on)
    if sublabel is None or sublabel == "":
        return "UNKNOWN"
    return str(sublabel)


def _group_by_stratum(
    items: List[dict], stratify_on: str
) -> Dict[str, List[dict]]:
    """Group image records by their stratification field value.

    >>> items = [{"sublabel": "original"}, {"sublabel": "forgery"}, {"sublabel": "original"}]
    >>> groups = _group_by_stratum(items, "sublabel")
    >>> sorted(groups.keys())
    ['forgery', 'original']
    >>> len(groups["original"])
    2

    Args:
        items:        List of ImageRecord dicts.
        stratify_on:  Field name to group by.

    Returns:
        A dict mapping stratum values to lists of items.
    """
    groups: Dict[str, List[dict]] = {}
    for item in items:
        key = _get_stratum_value(item, stratify_on=stratify_on)
        groups.setdefault(key, []).append(item)
    return groups


def assign_folds(
    items: List[dict],
    k_folds: int,
    outer_seed: int,
    inner_seed: int,
    stratify_on: str = "sublabel",
) -> Dict[str, int]:
    """Assign each image to an outer fold deterministically with stratification.

    Within each stratum (sublabel group), images are sorted by a stable hash
    and assigned to folds in round-robin order, ensuring each fold has an
    approximately equal ratio of each sublabel.

    >>> items = [{"image_id": f"img-{i}", "sublabel": "original"} for i in range(10)]
    >>> folds = assign_folds(items, k_folds=5, outer_seed=17, inner_seed=99)
    >>> all(0 <= f < 5 for f in folds.values())
    True
    >>> len(folds)
    10

    Args:
        items:        List of ImageRecord dicts (must contain ``image_id``).
        k_folds:      Number of outer folds.
        outer_seed:   Seed for deterministic fold assignment.
        inner_seed:   Seed for inner splits (unused here, kept for API symmetry).
        stratify_on:  Field name to stratify on (default ``"sublabel"``).

    Returns:
        A dict mapping image_id to fold index (0 to k_folds - 1).
    """
    groups = _group_by_stratum(items, stratify_on=stratify_on)

    assignment: Dict[str, int] = {}
    for sublabel, group_items in groups.items():
        ordered = sorted(
            group_items,
            key=lambda item: _stable_int(outer_seed, item["image_id"], salt="outer"),
        )
        for i, item in enumerate(ordered):
            assignment[item["image_id"]] = i % k_folds

    return assignment


def train_val_test_splits(
    items: List[dict],
    assignment: Dict[str, int],
    fold_id: int,
    k_folds: int,
    inner_seed: int,
    val_fraction: float = 0.2,
    stratify_on: str = "sublabel",
) -> Tuple[List[str], List[str], List[str]]:
    """Produce deterministic, stratified train/val/test splits for one outer fold.

    - **Test**: All items assigned to ``fold_id`` by ``assign_folds``.
    - **Val**: ~``val_fraction`` of the remaining items, stratified.
    - **Train**: Everything else.

    Uses SHA-256 hashing keyed by (inner_seed, fold_id, image_id) so the
    validation selection is reproducible and differs across folds.

    Args:
        items:         List of ImageRecord dicts.
        assignment:    Fold assignments from ``assign_folds``.
        fold_id:       Which outer fold to use as the test set.
        k_folds:       Total number of outer folds.
        inner_seed:    Seed for deterministic train/val splitting.
        val_fraction:  Fraction of the training pool to hold out for validation.
        stratify_on:   Field name to stratify on.

    Returns:
        A tuple of (train_ids, val_ids, test_ids) where each is a sorted
        list of image_id strings.
    """
    train_pool: List[dict] = []
    test_ids: List[str] = []

    for item in items:
        img_id = item["image_id"]
        fid = assignment.get(img_id)
        if fid == fold_id:
            test_ids.append(img_id)
        else:
            train_pool.append(item)

    groups = _group_by_stratum(train_pool, stratify_on=stratify_on)
    train_ids: List[str] = []
    val_ids: List[str] = []

    fold_salt = f"inner:fold={fold_id}"
    for sublabel, group_items in groups.items():
        ordered = sorted(
            group_items,
            key=lambda image: _stable_int(inner_seed, image["image_id"], salt=fold_salt),
        )
        n = len(ordered)
        n_val = int(round(n * val_fraction))

        val_part = ordered[:n_val]
        train_part = ordered[n_val:]

        val_ids.extend([r["image_id"] for r in val_part])
        train_ids.extend([r["image_id"] for r in train_part])

    train_ids.sort(key=lambda x: _stable_int(inner_seed, x, salt=fold_salt + ":train"))
    val_ids.sort(key=lambda x: _stable_int(inner_seed, x, salt=fold_salt + ":val"))
    test_ids.sort(key=lambda x: _stable_int(inner_seed, x, salt=fold_salt + ":test"))

    return train_ids, val_ids, test_ids


def all_nested_splits(
    items: List[dict],
    assignment: Dict[str, int],
    k_folds: int,
    inner_seed: int,
    val_fraction: float = 0.2,
    stratify_on: str = "sublabel",
) -> Dict[int, Dict[str, List[str]]]:
    """Compute train/val/test splits for every outer fold.

    Calls ``train_val_test_splits`` for each fold_id in ``range(k_folds)``.

    >>> items = [{"image_id": f"img-{i}", "sublabel": "original"} for i in range(20)]
    >>> folds = assign_folds(items, 5, 17, 99)
    >>> splits = all_nested_splits(items, folds, 5, 99)
    >>> sorted(splits.keys())
    [0, 1, 2, 3, 4]
    >>> sorted(splits[0].keys())
    ['test', 'train', 'val']

    Args:
        items:         List of ImageRecord dicts.
        assignment:    Fold assignments from ``assign_folds``.
        k_folds:       Total number of outer folds.
        inner_seed:    Seed for deterministic train/val splitting.
        val_fraction:  Fraction of the training pool to hold out for validation.
        stratify_on:   Field name to stratify on.

    Returns:
        A dict mapping fold_id to ``{"train": [...], "val": [...], "test": [...]}``.
    """
    out: Dict[int, Dict[str, List[str]]] = {}
    for fid in range(k_folds):
        tr, va, te = train_val_test_splits(
            items=items,
            assignment=assignment,
            fold_id=fid,
            k_folds=k_folds,
            inner_seed=inner_seed,
            val_fraction=val_fraction,
            stratify_on=stratify_on,
        )
        out[fid] = {"train": tr, "val": va, "test": te}
    return out
