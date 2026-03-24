"""DynamoDB record dataclasses for the ArtGuard data pipeline.

Each dataclass maps to one DynamoDB table and is used for serialisation
(via ``dataclasses.asdict``) when writing items. Primary keys and timestamps
are auto-generated with sensible defaults.

All dataclasses include ``__post_init__`` validation to enforce data
contracts (type coercion, range clamping, enum checking) before DynamoDB
writes.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import time
import uuid

# Allowed enum values (kept as sets for fast membership checks without
# importing the full backend validation module — this module is also used
# inside Modal containers that don't have the backend installed).
_VALID_LABELS = {"authentic", "inauthentic"}
_VALID_SUBLABELS = {"original", "forgery", "imitation", "proxy"}
_VALID_SPLITS = {"train", "val", "test", "unassigned"}
_VALID_RUN_STATUSES = {"running", "completed", "completed_with_errors", "failed"}


def _clamp(value: float, lo: float, hi: float) -> float:
    """Clamp a float to [lo, hi].

    >>> _clamp(0.5, 0.0, 1.0)
    0.5
    >>> _clamp(-0.1, 0.0, 1.0)
    0.0
    """
    return max(lo, min(hi, value))


@dataclass
class User:
    """A registered user account.

    Attributes:
        user_id:    Unique identifier (UUID, auto-generated).
        created_at: Account creation timestamp (Unix ms, auto-generated).
        username:   Display name (max 50 chars).
        password:   Password hash (bcrypt).
        email:      Email address (stored lowercase, max 254 chars).
    """

    user_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    username: str = ""
    password: str = ""
    email: str = ""

    def __post_init__(self) -> None:
        """Validate and normalize fields after construction."""
        self.username = str(self.username).strip()[:50]
        self.email = str(self.email).strip().lower()[:254]


@dataclass
class InferenceRecord:
    """A single forgery detection inference result.

    Attributes:
        inference_id: Unique identifier (UUID, auto-generated).
        created_at:   Timestamp (Unix ms, auto-generated).
        user_id:      ID of the user who submitted the inference.
        image_name:   Original filename of the uploaded image.
        image_path:   S3 URI of the raw uploaded image.
        score:        Mean patch probability of authenticity (0-1).
        explanation:  RAG-generated explanation text, if available.
    """

    inference_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    user_id: str = ""
    image_name: Optional[str] = None
    image_path: str = ""
    score: float = 0.0
    explanation: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate and normalize fields after construction."""
        self.score = _clamp(float(self.score), 0.0, 1.0)
        if self.explanation is not None:
            self.explanation = str(self.explanation)[:10_000]


@dataclass
class ImageRecord:
    """Metadata for a training or inference image.

    Attributes:
        image_id:           Unique identifier (UUID, auto-generated).
        created_at:         Timestamp (Unix ms, auto-generated).
        image_name:         Original filename.
        image_path:         S3 URI of the image.
        image_width:        Width in pixels (>= 0).
        image_height:       Height in pixels (>= 0).
        label:              ``"authentic"`` or ``"inauthentic"``.
        sublabel:           ``"original"``, ``"forgery"``, ``"imitation"``, or ``"proxy"``.
        run_id:             Processing run UUID that created this record.
        fold_id:            Outer cross-validation fold assignment (>= 0).
        split:              ``"train"``, ``"val"``, ``"test"``, or ``"unassigned"``.
        attributed_creator: The artist the artwork is attributed to.
        actual_creator:     The true creator of the artwork.
    """

    image_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    image_name: str = ""
    image_path: str = ""
    image_width: int = 0
    image_height: int = 0
    label: Optional[str] = None
    sublabel: Optional[str] = None
    run_id: Optional[str] = None
    fold_id: Optional[int] = None
    split: Optional[str] = None
    attributed_creator: Optional[str] = None
    actual_creator: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate and normalize fields after construction."""
        self.image_width = max(0, int(self.image_width))
        self.image_height = max(0, int(self.image_height))
        if self.label is not None and self.label not in _VALID_LABELS:
            self.label = None
        if self.sublabel is not None and self.sublabel not in _VALID_SUBLABELS:
            self.sublabel = None
        if self.split is not None and self.split not in _VALID_SPLITS:
            self.split = "unassigned"
        if self.fold_id is not None:
            self.fold_id = max(0, int(self.fold_id))


@dataclass
class PatchRecord:
    """Metadata for a single image patch (grid cell or center crop).

    Attributes:
        patch_id:     Unique identifier (UUID, auto-generated).
        created_at:   Timestamp (Unix ms, auto-generated).
        patch_path:   S3 URI of the patch JPEG.
        image_id:     Parent image UUID.
        patch_type:   Category string (e.g. ``"center_crop_orig"``).
        patch_x:      Patch x-coordinate in the original image (>= 0).
        patch_y:      Patch y-coordinate in the original image (>= 0).
        patch_width:  Patch width in pixels (>= 0).
        patch_height: Patch height in pixels (>= 0).
    """

    patch_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    patch_path: str = ""
    image_id: str = ""
    patch_type: str = ""
    patch_x: int = 0
    patch_y: int = 0
    patch_width: int = 0
    patch_height: int = 0

    def __post_init__(self) -> None:
        """Validate and normalize coordinate fields after construction."""
        self.patch_x = max(0, int(self.patch_x))
        self.patch_y = max(0, int(self.patch_y))
        self.patch_width = max(0, int(self.patch_width))
        self.patch_height = max(0, int(self.patch_height))


@dataclass
class RunRecord:
    """Metadata for a training or data processing run.

    Attributes:
        run_id:            Unique identifier (UUID, auto-generated).
        created_at:        Timestamp (Unix ms, auto-generated).
        status:            ``"running"``, ``"completed"``, ``"completed_with_errors"``,
                           or ``"failed"``.
        modal_volume_path: Path inside the Modal Volume for checkpoints.
        best_config_id:    Config UUID of the best hyperparameter combination.
        k_folds:           Number of outer cross-validation folds (>= 2).
        stratify_on:       Field used for stratified splitting.
        outer_split_seed:  Seed for deterministic outer fold assignment.
        inner_split_seed:  Seed for deterministic train/val splitting.
        mean_accuracy:     Average accuracy across folds (0-1).
        mean_auc:          Average AUC across folds (0-1).
        mean_f1:           Average F1 score across folds (0-1).
        mean_precision:    Average precision across folds (0-1).
        mean_recall:       Average recall across folds (0-1).
        std_accuracy:      Standard deviation of accuracy across folds.
        std_auc:           Standard deviation of AUC across folds.
        std_f1:            Standard deviation of F1 across folds.
        std_precision:     Standard deviation of precision across folds.
        std_recall:        Standard deviation of recall across folds.
    """

    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    status: str = "running"
    modal_volume_path: Optional[str] = None
    best_config_id: Optional[str] = None
    k_folds: int = 5
    stratify_on: str = "sublabel"
    outer_split_seed: int = 17
    inner_split_seed: int = 99
    mean_accuracy: Optional[float] = None
    mean_auc: Optional[float] = None
    mean_f1: Optional[float] = None
    mean_precision: Optional[float] = None
    mean_recall: Optional[float] = None
    std_accuracy: Optional[float] = None
    std_auc: Optional[float] = None
    std_f1: Optional[float] = None
    std_precision: Optional[float] = None
    std_recall: Optional[float] = None

    def __post_init__(self) -> None:
        """Validate and normalize fields after construction."""
        if self.status not in _VALID_RUN_STATUSES:
            self.status = "running"
        self.k_folds = max(2, int(self.k_folds))
        # Clamp metric values to [0, 1] if set
        for attr in ("mean_accuracy", "mean_auc", "mean_f1", "mean_precision",
                      "mean_recall"):
            val = getattr(self, attr)
            if val is not None:
                setattr(self, attr, _clamp(float(val), 0.0, 1.0))


@dataclass
class ConfigRecord:
    """Hyperparameter configuration for one fold of a training run.

    Attributes:
        config_id:         Unique identifier (UUID, auto-generated).
        created_at:        Timestamp (Unix ms, auto-generated).
        run_id:            Parent run UUID.
        fold_id:           Outer fold index (0-based, >= 0).
        hyperparameters:   Dict of hyperparameter key-value pairs.
        best_epoch:        Epoch number with the best validation metric (>= 0).
        best_val:          Best validation metric value.
        early_stopped:     Whether training was stopped early.
        is_best_in_fold:   Whether this config achieved the best result in its fold.
        modal_volume_path: Path to model weights in the Modal Volume (if best).
    """

    config_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    run_id: str = ""
    fold_id: int = 0
    hyperparameters: Dict[str, Any] = field(default_factory=dict)
    best_epoch: Optional[int] = None
    best_val: Optional[float] = None
    early_stopped: bool = False
    is_best_in_fold: bool = False
    modal_volume_path: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate and normalize fields after construction."""
        self.fold_id = max(0, int(self.fold_id))
        if self.best_epoch is not None:
            self.best_epoch = max(0, int(self.best_epoch))
