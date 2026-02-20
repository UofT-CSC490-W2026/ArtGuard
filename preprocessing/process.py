from __future__ import annotations
import uuid
from typing import Callable, Dict, List, Optional, Tuple
from PIL import Image
from io import BytesIO


PATCH_SIZE = 256  

def _choose_p(img: Image.Image) -> int:
    """
    The sub-images are created by dividing the whole image into 2^p by 2^p
    equally sized units, with p depending on the resolution of the original 
    image as follows: p = 2, if the smaller side of an image is larger than 
    1024 pixels, and p = 1, if the smaller side is larger than 512 pixels 
    and smaller than 1024.
    """
    w, h = img.size
    m = min(w, h)
    if m > 1024:
        return 2
    if m > 512:
        return 1
    return 1


def _center_crop_square(img: Image.Image) -> Tuple[Image.Image, int, int, int]:
    """
    For all images, regardless of the resolution, we also include the sub-image 
    of the center-cropped square stemming from the full image.
    Returns the center-cropped square image, its top-left corner coordinates and
    side length.
    """
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    cropped = img.crop((left, top, left + side, top + side))
    return cropped, left, top, side


def _encode_jpeg(img: Image.Image, quality: int = 95) -> bytes:
    """
    Encode PIL image to JPEG bytes.
    """
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


# TODO:
def _upload_patch(
    s3_client,
    processed_bucket: str,
    key: str,
    img: Image.Image,
) -> str:
    """
    Upload a patch image to S3 and return its s3:// URI.
    """
    body = _encode_jpeg(img)
    s3_client.put_object(
        Bucket=processed_bucket,
        Key=key,
        Body=body,
        ContentType="image/jpeg",
    )
    return f"s3://{processed_bucket}/{key}"

# TODO
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
    Store patch's metadata, so it can be eventually updated in DynamoDB.
    """
    patch_img = patch_img.resize((PATCH_SIZE, PATCH_SIZE), resample=Image.BICUBIC)

    patch_id = str(uuid.uuid4())
    key = f"{processed_prefix}/{image_id}/{patch_type}/{patch_id}.jpg"
    s3_uri = _upload_patch(s3_client, processed_bucket, key, patch_img)

    metadata: Dict = {
        "patch_id": patch_id,
        "patch_type": patch_type,
        "patch_path": s3_uri,
        "patch_x": int(x),
        "patch_y": int(y),
        "patch_width": int(width),
        "patch_height": int(height),
    }
    patches.append(metadata)

# TODO:
def process_image_to_patches(
    img: Image.Image,
    image_id: str,
    processed_bucket: str,
    processed_prefix: str,
    s3_client,
) -> List[Dict]:
    """
    Produce a center-cropped square from the full image, and (2^p x 2^p) grid patches
    from it. All patches are resized to 256x256 using bicubic resampling.
    Returns a list of patch metadata dicts suitable for writing to DynamoDB.
    """
    if img.mode != "RGB":
        img = img.convert("RGB")

    square, sq_left, sq_top, sq_side = _center_crop_square(img)

    p = _choose_p(img)
    grid_n = 2 ** p  

    cell = sq_side // grid_n
    if cell <= 0:
        raise ValueError("Image too small to create grid patches.")

    patches: List[Dict] = []

    # Center square patch
    _add_patch_record(
        patches=patches,
        patch_img=square,
        patch_type="center_square",
        x=sq_left,
        y=sq_top,
        width=sq_side,
        height=sq_side,
        processed_prefix=processed_prefix,
        image_id=image_id,
        processed_bucket=processed_bucket,
        s3_client=s3_client,
    )

    # Grid patches
    for row in range(grid_n):
        for col in range(grid_n):
            x0 = col * cell
            y0 = row * cell
            x1 = x0 + cell
            y1 = y0 + cell

            patch = square.crop((x0, y0, x1, y1))

            orig_x = sq_left + x0
            orig_y = sq_top + y0

            _add_patch_record(
                patches=patches,
                patch_img=patch,
                patch_type="grid",
                x=orig_x,
                y=orig_y,
                width=cell,
                height=cell,
                processed_prefix=processed_prefix,
                image_id=image_id,
                processed_bucket=processed_bucket,
                s3_client=s3_client,
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