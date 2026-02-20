from __future__ import annotations
from typing import Dict, List, Tuple, Optional
import hashlib


def _stable_int(seed: int, image_id: str, salt: str = "") -> int:
    """
    This provides a deterministic approach to reproduce splits.
    """
    msg = f"{seed}:{salt}:{image_id}".encode("utf-8")
    h = hashlib.sha256(msg).hexdigest()
    return int(h[:16], 16)  


def _get_stratum_value(item: dict, stratify_on: str) -> str:
    """
    This method ensures that each ImageRecord has a sublabel (original vs. forgery vs.
    AI-imitation).
    """
    sublabel = item.get(stratify_on)
    if sublabel is None or sublabel == "":
        return "UNKNOWN"
    return str(sublabel)


def _group_by_stratum(items: List[dict], stratify_on: str) -> Dict[str, List[dict]]:
    """
    This method groups images based on their sublabels.
    groups["original"] = original images
    groups["forgery"] = forged images
    groups["imitations"] = AI-imitations
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
    """
    This method assigns an outer fold to each image deterministically, while maintaining stratification
    (i.e., equal ratio of original/forgery/imitation in train and test set).
    """
    groups = _group_by_stratum(items, stratify_on=stratify_on)

    assignment: Dict[str, int] = {}
    for sublabel, group_items in groups.items():
        ordered = sorted(group_items, key=lambda item: _stable_int(outer_seed, item["image_id"], salt="outer"))
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
    """
    For a given outer fold, produce train, validation and test splits.

    For a given outer fold_id, produce deterministic, stratified:
      train_ids, val_ids, test_ids

    Outer split:
      - test_ids: all items with assignment == fold_id
      - train_pool: all other items

    Inner split (within train_pool):
      - val_ids: ~val_fraction of train_pool, selected STRATIFIED by `stratify_on`
      - train_ids: remaining

    Determinism:
      - Uses SHA-256 stable hashing keyed by (inner_seed, fold_id, image_id)
        so the validation selection is reproducible AND can differ across folds.
    """
    # Partition into train + test using fold_id.
    train_pool: List[dict] = []
    test_ids: List[str] = []

    for item in items:
        img_id = item["image_id"]
        fid = assignment.get(img_id)
        if fid == fold_id:
            test_ids.append(img_id)
        else:
            train_pool.append(item)

    # Training and validation should have an equal ratio of original/forgery/imitation;
    # stratification
    groups = _group_by_stratum(train_pool, stratify_on=stratify_on)
    train_ids: List[str] = []
    val_ids: List[str] = []

    # Make training + validation set deterministic.
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
    """
    Compute splits for every outer fold.
    Returns:
      {
        fold_id: {
          "train": [...],
          "val":   [...],
          "test":  [...]
        },
        ...
      }
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