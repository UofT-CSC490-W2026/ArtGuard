from __future__ import annotations

import uuid
from io import BytesIO
from typing import Dict, List, Tuple

from PIL import Image, ImageFilter


TARGET_PATCH_SIZE = 224
GRID_4X4_THRESHOLD = 1024
GRID_2X2_THRESHOLD = 512


class PreprocessConfig:
    """
    Lightweight config object for preprocessing behavior.

    Defaults preserve a simple baseline:
    - no blur
    - no rotation beyond 0 degrees
    """

    def __init__(
        self,
        apply_gaussian_blur: bool = False,
        gaussian_blur_radius: float = 1.0,
        rotation_angles: List[int] | None = None,
    ) -> None:
        self.apply_gaussian_blur = apply_gaussian_blur
        self.gaussian_blur_radius = gaussian_blur_radius
        self.rotation_angles = rotation_angles if rotation_angles is not None else [0]


def choose_grid_size(image_width: int, image_height: int) -> int:
    """
    Return grid size N, where the image is split into an N x N grid.

    - min side > 1024 -> 4 x 4
    - 512 < min side <= 1024 -> 2 x 2
    - otherwise -> 2 x 2
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
    """
    Return crop boxes dividing the full image into a grid.

    Each box is (left, upper, right, lower).
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
    """
    Return grid patches from the image.

    Each result is:
        (patch_image, patch_x, patch_y, patch_width, patch_height)
    where patch_x and patch_y are coordinates in the original image.
    """
    patches: List[Tuple[Image.Image, int, int, int, int]] = []

    for left, upper, right, lower in compute_grid_boxes(image.width, image.height, grid_size):
        patch = image.crop((left, upper, right, lower))
        patches.append((patch, left, upper, right - left, lower - upper))

    return patches


def center_crop_to_square(image: Image.Image, size: int) -> Image.Image:
    """
    Return a centered size x size crop.

    Raises ValueError if image is too small.
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
    """Return image resized to size x size using bicubic resampling."""
    return image.resize((size, size), resample=Image.Resampling.BICUBIC)


def apply_gaussian_blur(image: Image.Image, radius: float) -> Image.Image:
    """Return a blurred copy of image."""
    return image.filter(ImageFilter.GaussianBlur(radius=radius))


def rotate_patch(image: Image.Image, angle: int) -> Image.Image:
    """Return image rotated by angle degrees."""
    if angle == 0:
        return image.copy()
    return image.rotate(angle, expand=True)


def generate_patch_variants(
    patch_image: Image.Image,
    config: PreprocessConfig,
) -> List[Tuple[Image.Image, str]]:
    """
    Return transformed variants of a patch.

    Each result is:
        (variant_image, variant_suffix)
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


def _encode_jpeg(img: Image.Image, quality: int = 95) -> bytes:
    """Encode PIL image to JPEG bytes."""
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _upload_patch(
    s3_client,
    processed_bucket: str,
    key: str,
    img: Image.Image,
) -> str:
    """
    Upload patch image to S3 and return s3:// URI.
    """
    body = _encode_jpeg(img)
    s3_client.put_object(
        Bucket=processed_bucket,
        Key=key,
        Body=body,
        ContentType="image/jpeg",
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
    processed_prefix: str,
    image_id: str,
    processed_bucket: str,
    s3_client,
) -> None:
    """
    Upload a patch image to S3 and append its metadata to `patches`.

    The metadata shape matches what driver.py expects to later write to DynamoDB.
    """
    patch_id = str(uuid.uuid4())
    key = f"{processed_prefix}/{image_id}/{patch_type}/{patch_id}.jpg"
    s3_uri = _upload_patch(s3_client, processed_bucket, key, patch_img)

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


def _process_single_grid_patch(
    patches: List[Dict],
    patch_image: Image.Image,
    image_id: str,
    patch_x: int,
    patch_y: int,
    patch_width: int,
    patch_height: int,
    processed_bucket: str,
    processed_prefix: str,
    s3_client,
    config: PreprocessConfig,
) -> None:
    """
    From one grid patch, create:
    - center-cropped 224x224 patch when possible
    - bicubic-downsampled 224x224 patch
    for each configured variant.
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
                processed_prefix=processed_prefix,
                image_id=image_id,
                processed_bucket=processed_bucket,
                s3_client=s3_client,
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
            processed_prefix=processed_prefix,
            image_id=image_id,
            processed_bucket=processed_bucket,
            s3_client=s3_client,
        )


def process_image_to_patches(
    img: Image.Image,
    image_id: str,
    processed_bucket: str,
    processed_prefix: str,
    s3_client,
) -> List[Dict]:
    """
    Produce richer preprocessing outputs while remaining compatible with driver.py.

    Behavior:
    - split full image into 2x2 or 4x4 grid based on image size
    - for each grid patch, optionally rotate / blur
    - derive:
        - center-cropped 224x224 patch when possible
        - bicubic-downsampled 224x224 patch
    - upload all generated patches to S3
    - return metadata dicts for driver.py to write to DynamoDB
    """
    if img.mode != "RGB":
        img = img.convert("RGB")

    # TODO: Modify this to run different ablations.
    config = PreprocessConfig()

    grid_size = choose_grid_size(img.width, img.height)
    grid_patches = extract_grid_patches(img, grid_size)

    patches: List[Dict] = []

    for patch_image, patch_x, patch_y, patch_width, patch_height in grid_patches:
        _process_single_grid_patch(
            patches=patches,
            patch_image=patch_image,
            image_id=image_id,
            patch_x=patch_x,
            patch_y=patch_y,
            patch_width=patch_width,
            patch_height=patch_height,
            processed_bucket=processed_bucket,
            processed_prefix=processed_prefix,
            s3_client=s3_client,
            config=config,
        )

    return patches


def process_training_image(
    img: Image.Image,
    image_id: str,
    processed_bucket: str,
    processed_prefix: str,
    s3_client,
) -> List[Dict]:
    return process_image_to_patches(
        img=img,
        image_id=image_id,
        processed_bucket=processed_bucket,
        processed_prefix=processed_prefix,
        s3_client=s3_client,
    )


def process_inference_image(
    img: Image.Image,
    image_id: str,
    processed_bucket: str,
    processed_prefix: str,
    s3_client,
) -> List[Dict]:
    return process_image_to_patches(
        img=img,
        image_id=image_id,
        processed_bucket=processed_bucket,
        processed_prefix=processed_prefix,
        s3_client=s3_client,
    )
