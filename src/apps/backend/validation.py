"""Shared validation constraints and data contracts for the ArtGuard API.

Centralizes field length limits, numeric bounds, file size limits, and
allowed enum values so they are consistent across Pydantic request/response
models, service-layer writes, and DynamoDB records.

Import constants from here rather than hardcoding limits in route handlers.
"""

from __future__ import annotations

from typing import Literal

# ---------------------------------------------------------------------------
# String length limits
# ---------------------------------------------------------------------------

USERNAME_MIN = 3
USERNAME_MAX = 50
PASSWORD_MIN = 6
PASSWORD_MAX = 128
EMAIL_MAX = 254  # RFC 5321 max email length
EMAIL_PATTERN = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"

ARTIST_NAME_MAX = 200
ARTWORK_NAME_MAX = 200
IMAGE_NAME_MAX = 255
EXPLANATION_MAX = 10_000
ERROR_MESSAGE_MAX = 3_500
RAG_QUERY_MAX = 2_000

# ---------------------------------------------------------------------------
# File constraints
# ---------------------------------------------------------------------------

MAX_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB
ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/bmp",
    "image/tiff",
}

# ---------------------------------------------------------------------------
# Numeric bounds
# ---------------------------------------------------------------------------

SCORE_MIN = 0.0
SCORE_MAX = 1.0
PREDICTION_VALUES = {-1, 0, 1}  # -1 = pending, 0 = forgery, 1 = authentic
PATCH_COORD_MIN = 0
PATCH_COORD_MAX = 100_000  # Max pixels in any dimension

# ---------------------------------------------------------------------------
# Enum / Literal types for strict validation
# ---------------------------------------------------------------------------

ModelVariant = Literal["tiny", "base"]

ImageLabel = Literal["authentic", "inauthentic"]
ImageSublabel = Literal["original", "forgery", "imitation", "proxy"]
DataSplit = Literal["train", "val", "test", "unassigned"]

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def clamp_score(value: float) -> float:
    """Clamp a score to the [0.0, 1.0] range.

    >>> clamp_score(0.85)
    0.85
    >>> clamp_score(-0.1)
    0.0
    >>> clamp_score(1.5)
    1.0
    """
    return max(SCORE_MIN, min(SCORE_MAX, value))


def validate_prediction(value: int) -> int:
    """Validate that a prediction value is -1, 0, or 1.

    >>> validate_prediction(1)
    1
    >>> validate_prediction(99)
    -1

    Returns -1 (pending) if the value is not in the allowed set.
    """
    return value if value in PREDICTION_VALUES else -1


def truncate(value: str, max_length: int) -> str:
    """Truncate a string to max_length characters.

    >>> truncate("hello world", 5)
    'hello'
    >>> truncate("hi", 10)
    'hi'
    """
    return value[:max_length] if len(value) > max_length else value


def sanitize_filename(name: str) -> str:
    """Sanitize a filename by removing path traversal and null bytes.

    >>> sanitize_filename("../../etc/passwd")
    'passwd'
    >>> sanitize_filename("normal_file.jpg")
    'normal_file.jpg'
    >>> sanitize_filename("")
    'unnamed'
    """
    import os
    # Remove null bytes
    name = name.replace("\x00", "")
    # Normalize backslashes to forward slashes (Windows paths on Unix)
    name = name.replace("\\", "/")
    # Take only the basename (strips directory traversal)
    name = os.path.basename(name)
    # Remove leading dots (hidden files)
    name = name.lstrip(".")
    return name if name else "unnamed"
