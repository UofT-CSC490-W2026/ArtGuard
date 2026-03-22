"""Image preprocessing pipeline: split images into patches for model training/inference.

Based on the approach from "Art Authentication with Vision Transformers"
(Schaerf et al., 2023). Images are divided into an NxN grid (2x2 or 4x4
depending on resolution), and each grid cell produces two 224x224 patches:
a center crop and a bicubic downsample. Optional augmentations (rotation,
Gaussian blur) can be configured via ``PreprocessConfig``.

All patches are uploaded to S3 as JPEG files and their metadata is returned
as a list of dicts for the caller (driver.py or inference_router.py) to
write to DynamoDB.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from io import BytesIO
from typing import Dict, List, Tuple

from PIL import Image, ImageFilter

TARGET_PATCH_SIZE = 224
"""Side length in pixels for all output patches."""

GRID_4X4_THRESHOLD = 1024
"""Images with min side > this threshold use a 4x4 grid."""

GRID_2X2_THRESHOLD = 512
"""Images with min side > this threshold (but <= GRID_4X4_THRESHOLD) use a 2x2 grid."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class PreprocessConfig:
    """Configuration for image preprocessing augmentations.

    Attributes:
        apply_gaussian_blur:   Whether to apply Gaussian blur to patches.
        gaussian_blur_radius:  Radius for the Gaussian blur filter.
        rotation_angles:       List of rotation angles in degrees to apply.
                               Default ``[0]`` means no rotation (original only).
    """

    def __init__(
        self,
        apply_gaussian_blur: bool = False,
        gaussian_blur_radius: float = 1.0,
        rotation_angles: List[int] | None = None,
    ) -> None:
        """Initialize preprocessing config with optional blur and rotation settings."""
        self.apply_gaussian_blur = apply_gaussian_blur
        self.gaussian_blur_radius = gaussian_blur_radius
        self.rotation_angles = rotation_angles if rotation_angles is not None else [0]


@dataclass
class S3UploadContext:
    """Bundles the S3 parameters needed to upload patch images.

    Passed through the processing pipeline so individual functions
    don't need 3+ separate S3-related parameters.

    Attributes:
        s3_client:        A boto3 S3 client.
        processed_bucket: Destination S3 bucket name.
        processed_prefix: S3 key prefix (e.g. ``"training"`` or ``"inference"``).
        image_id:         Parent image UUID (used in S3 key construction).
    """

    s3_client: object
    processed_bucket: str
    processed_prefix: str
    image_id: str


# ---------------------------------------------------------------------------
# Grid computation
# ---------------------------------------------------------------------------

def choose_grid_size(image_width: int, image_height: int) -> int:
    """Return grid size N based on image resolution (image is split into NxN cells).

    The grid size depends on the smaller side of the image:
    - min side > 1024 pixels -> 4x4 grid
    - min side > 512 pixels  -> 2x2 grid
    - otherwise              -> 2x2 grid

    >>> choose_grid_size(2048, 1536)
    4
    >>> choose_grid_size(800, 600)
    2
    >>> choose_grid_size(400, 300)
    2
    """
    smaller_side = min(image_width, image_height)

    if smaller_side > GRID_4X4_THRESHOLD:
        return 4
    if GRID_2X2_THRESHOLD < smaller_side <= GRID_4X4_THRESHOLD:
        return 2
    return 2


def compute_grid_boxes(
    image_width: int,
    image_height: int,
    grid_size: int,
) -> List[Tuple[int, int, int, int]]:
    """Compute crop boxes that divide an image into a grid_size x grid_size grid.

    Returns a list of (left, upper, right, lower) tuples suitable for
    ``PIL.Image.crop()``. Edges are rounded to ensure full pixel coverage.

    >>> compute_grid_boxes(100, 100, 2)
    [(0, 0, 50, 50), (50, 0, 100, 50), (0, 50, 50, 100), (50, 50, 100, 100)]
    """
    boxes: List[Tuple[int, int, int, int]] = []

    x_edges = [round(i * image_width / grid_size) for i in range(grid_size + 1)]
    y_edges = [round(i * image_height / grid_size) for i in range(grid_size + 1)]

    for row in range(grid_size):
        for col in range(grid_size):
            left = x_edges[col]
            right = x_edges[col + 1]
            upper = y_edges[row]
            lower = y_edges[row + 1]
            boxes.append((left, upper, right, lower))

    return boxes


def extract_grid_patches(
    image: Image.Image,
    grid_size: int,
) -> List[Tuple[Image.Image, int, int, int, int]]:
    """Crop an image into grid_size x grid_size patches.

    Each result tuple contains:
        (patch_image, patch_x, patch_y, patch_width, patch_height)
    where patch_x and patch_y are pixel coordinates in the original image.

    >>> from PIL import Image
    >>> img = Image.new("RGB", (100, 100))
    >>> patches = extract_grid_patches(img, 2)
    >>> len(patches)
    4
    """
    patches: List[Tuple[Image.Image, int, int, int, int]] = []

    for left, upper, right, lower in compute_grid_boxes(image.width, image.height, grid_size):
        patch = image.crop((left, upper, right, lower))
        patches.append((patch, left, upper, right - left, lower - upper))

    return patches


# ---------------------------------------------------------------------------
# Patch transformations
# ---------------------------------------------------------------------------

def center_crop_to_square(image: Image.Image, size: int) -> Image.Image:
    """Return a centered ``size x size`` crop from the image.

    >>> from PIL import Image
    >>> img = Image.new("RGB", (300, 300))
    >>> center_crop_to_square(img, 224).size
    (224, 224)

    Raises:
        ValueError: If the image is smaller than ``size`` in either dimension.
    """
    if image.width < size or image.height < size:
        raise ValueError(
            f"Cannot center crop {size}x{size} from patch of size "
            f"{image.width}x{image.height}."
        )

    left = (image.width - size) // 2
    upper = (image.height - size) // 2
    right = left + size
    lower = upper + size
    return image.crop((left, upper, right, lower))


def downsample_to_square(image: Image.Image, size: int) -> Image.Image:
    """Resize image to ``size x size`` using bicubic interpolation.

    >>> from PIL import Image
    >>> img = Image.new("RGB", (500, 500))
    >>> downsample_to_square(img, 224).size
    (224, 224)
    """
    return image.resize((size, size), resample=Image.Resampling.BICUBIC)


def apply_gaussian_blur(image: Image.Image, radius: float) -> Image.Image:
    """Return a copy of image with Gaussian blur applied.

    >>> from PIL import Image
    >>> img = Image.new("RGB", (100, 100))
    >>> blurred = apply_gaussian_blur(img, 2.0)
    >>> blurred.size
    (100, 100)
    """
    return image.filter(ImageFilter.GaussianBlur(radius=radius))


def rotate_patch(image: Image.Image, angle: int) -> Image.Image:
    """Return image rotated by angle degrees (counter-clockwise).

    Returns a copy of the original if angle is 0. Uses ``expand=True``
    to avoid cropping corners on non-zero rotations.

    >>> from PIL import Image
    >>> img = Image.new("RGB", (100, 100))
    >>> rotate_patch(img, 0).size
    (100, 100)
    """
    if angle == 0:
        return image.copy()
    return image.rotate(angle, expand=True)


def generate_patch_variants(
    patch_image: Image.Image,
    config: PreprocessConfig,
) -> List[Tuple[Image.Image, str]]:
    """Apply configured augmentations to a patch and return all variants.

    Each result is a (variant_image, variant_suffix) tuple where the suffix
    encodes the applied transformations (e.g. ``"orig"``, ``"rot90"``,
    ``"orig_blur"``).

    >>> from PIL import Image
    >>> img = Image.new("RGB", (100, 100))
    >>> variants = generate_patch_variants(img, PreprocessConfig())
    >>> len(variants)
    1
    >>> variants[0][1]
    'orig'
    """
    variants: List[Tuple[Image.Image, str]] = []

    for angle in config.rotation_angles:
        rotated = rotate_patch(patch_image, angle)

        if angle == 0:
            suffix = "orig"
        else:
            suffix = f"rot{angle}"

        if config.apply_gaussian_blur:
            rotated = apply_gaussian_blur(rotated, config.gaussian_blur_radius)
            suffix = f"{suffix}_blur"

        variants.append((rotated, suffix))

    return variants


# ---------------------------------------------------------------------------
# S3 upload helpers
# ---------------------------------------------------------------------------

def _encode_jpeg(img: Image.Image, quality: int = 95) -> bytes:
    """Encode a PIL Image as optimized JPEG bytes.

    >>> from PIL import Image
    >>> img = Image.new("RGB", (10, 10))
    >>> data = _encode_jpeg(img)
    >>> isinstance(data, bytes) and len(data) > 0
    True
    """
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _upload_patch(
    s3_client,
    processed_bucket: str,
    key: str,
    img: Image.Image,
) -> str:
    """Encode img as JPEG, upload it to S3, and return the ``s3://`` URI.

    Args:
        s3_client:        A boto3 S3 client.
        processed_bucket: Destination S3 bucket name.
        key:              S3 object key for the uploaded patch.
        img:              PIL Image to upload.

    Returns:
        The ``s3://bucket/key`` URI of the uploaded object.
    """
    body = _encode_jpeg(img)
    s3_client.put_object(
        Bucket=processed_bucket,
        Key=key,
        Body=body,
        ContentType="image/jpeg",
        ServerSideEncryption="AES256",
    )

    return f"s3://{processed_bucket}/{key}"


def _add_patch_record(
    patches: List[Dict],
    patch_img: Image.Image,
    patch_type: str,
    x: int,
    y: int,
    width: int,
    height: int,
    ctx: S3UploadContext,
) -> None:
    """Upload a patch image to S3 and append its metadata dict to patches.

    The metadata dict contains ``patch_id``, ``patch_type``, ``patch_path``,
    and bounding box fields, matching the schema expected by driver.py and
    DynamoDB PatchRecord.

    Args:
        patches:    Mutable list to append the metadata dict to.
        patch_img:  PIL Image of the patch to upload.
        patch_type: Patch category string (e.g. ``"center_crop_orig"``).
        x:          Patch x-coordinate in the original image.
        y:          Patch y-coordinate in the original image.
        width:      Patch width in pixels.
        height:     Patch height in pixels.
        ctx:        S3 upload context with bucket, prefix, image_id, and client.
    """
    patch_id = str(uuid.uuid4())
    key = f"{ctx.processed_prefix}/{ctx.image_id}/{patch_type}/{patch_id}.jpg"
    s3_uri = _upload_patch(ctx.s3_client, ctx.processed_bucket, key, patch_img)

    patches.append(
        {
            "patch_id": patch_id,
            "patch_type": patch_type,
            "patch_path": s3_uri,
            "patch_x": int(x),
            "patch_y": int(y),
            "patch_width": int(width),
            "patch_height": int(height),
        }
    )


# ---------------------------------------------------------------------------
# Single patch processing
# ---------------------------------------------------------------------------

def _process_single_grid_patch(
    patches: List[Dict],
    patch_image: Image.Image,
    patch_x: int,
    patch_y: int,
    ctx: S3UploadContext,
    config: PreprocessConfig,
) -> None:
    """Process one grid cell into center-cropped and downsampled patches.

    For each configured variant (rotation / blur), produces:
    - A center-cropped 224x224 patch (if the variant is large enough).
    - A bicubic-downsampled 224x224 patch.

    All patches are uploaded to S3 and their metadata appended to patches.

    Args:
        patches:     Mutable list to accumulate patch metadata dicts.
        patch_image: PIL Image of the grid cell.
        patch_x:     Grid cell x-coordinate in the original image.
        patch_y:     Grid cell y-coordinate in the original image.
        ctx:         S3 upload context.
        config:      Augmentation configuration.
    """
    variants = generate_patch_variants(patch_image, config)

    for variant_image, variant_suffix in variants:
        center_type = f"center_crop_{variant_suffix}"
        downsample_type = f"downsample_{variant_suffix}"

        if variant_image.width >= TARGET_PATCH_SIZE and variant_image.height >= TARGET_PATCH_SIZE:
            center_crop = center_crop_to_square(variant_image, TARGET_PATCH_SIZE)
            _add_patch_record(
                patches=patches,
                patch_img=center_crop,
                patch_type=center_type,
                x=patch_x,
                y=patch_y,
                width=TARGET_PATCH_SIZE,
                height=TARGET_PATCH_SIZE,
                ctx=ctx,
            )

        downsample = downsample_to_square(variant_image, TARGET_PATCH_SIZE)
        _add_patch_record(
            patches=patches,
            patch_img=downsample,
            patch_type=downsample_type,
            x=patch_x,
            y=patch_y,
            width=TARGET_PATCH_SIZE,
            height=TARGET_PATCH_SIZE,
            ctx=ctx,
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def process_image_to_patches(
    img: Image.Image,
    image_id: str,
    processed_bucket: str,
    processed_prefix: str,
    s3_client,
) -> List[Dict]:
    """Split an image into patches, upload them to S3, and return their metadata.

    The image is divided into a 2x2 or 4x4 grid (based on resolution).
    Each grid cell produces center-cropped and downsampled 224x224 patches,
    optionally with rotation and blur augmentations.

    Args:
        img:              PIL Image to process (converted to RGB if needed).
        image_id:         UUID identifying the parent image.
        processed_bucket: S3 bucket for processed patch uploads.
        processed_prefix: S3 key prefix (e.g. ``"training"`` or ``"inference"``).
        s3_client:        A boto3 S3 client.

    Returns:
        A list of patch metadata dicts, each containing ``patch_id``,
        ``patch_type``, ``patch_path`` (s3:// URI), and bounding box fields.
    """
    if img.mode != "RGB":
        img = img.convert("RGB")

    config = PreprocessConfig()
    ctx = S3UploadContext(
        s3_client=s3_client,
        processed_bucket=processed_bucket,
        processed_prefix=processed_prefix,
        image_id=image_id,
    )

    grid_size = choose_grid_size(img.width, img.height)
    grid_patches = extract_grid_patches(img, grid_size)

    patches: List[Dict] = []

    for patch_image, patch_x, patch_y, _pw, _ph in grid_patches:
        _process_single_grid_patch(
            patches=patches,
            patch_image=patch_image,
            patch_x=patch_x,
            patch_y=patch_y,
            ctx=ctx,
            config=config,
        )

    return patches
