from __future__ import annotations

from dataclasses import asdict
from io import BytesIO
from typing import List, Tuple

import boto3
from PIL import Image

from schemas import ImageRecord, PatchRecord


TARGET_PATCH_SIZE = 224

def load_image_record_from_dynamodb(table_name: str, image_id: str) -> ImageRecord:
    """Return the ImageRecord stored in DynamoDB.

    The record is retrieved using the image_id primary key and converted
    into an ImageRecord dataclass.

    >>> load_image_record_from_dynamodb("ImageTable", "abc123")  # doctest: +SKIP
    ImageRecord(...)
    """
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)

    response = table.get_item(Key={"image_id": image_id})

    if "Item" not in response:
        raise ValueError(f"ImageRecord with id {image_id} not found.")

    item = response["Item"]

    return ImageRecord(**item)


def load_image_from_s3(bucket_name: str, key: str) -> Image.Image:
    """Return the image stored in S3 at bucket_name/key.

    The image is converted to RGB so downstream processing is consistent.

    >>> image = load_image_from_s3("my-bucket", "images/example.jpg")  # doctest: +SKIP
    >>> image.mode  # doctest: +SKIP
    'RGB'
    """
    s3_client = boto3.client("s3")
    response = s3_client.get_object(Bucket=bucket_name, Key=key)
    image_bytes = response["Body"].read()
    return Image.open(BytesIO(image_bytes)).convert("RGB")


def choose_grid_size(image_width: int, image_height: int) -> int:
    """Return the number of rows and columns for patching the image.

    If the smaller side is:
    - greater than 1024: use a 4 x 4 grid
    - greater than 512 and smaller than 1024: use a 2 x 2 grid
    - otherwise: use a 1 x 1 grid

    >>> choose_grid_size(1600, 1400)
    4
    >>> choose_grid_size(900, 700)
    2
    """
    smaller_side = min(image_width, image_height)

    if smaller_side > 1024:
        return 4
    if 512 < smaller_side < 1024:
        return 2


def compute_grid_boxes(
    image_width: int, image_height: int, grid_size: int
) -> List[Tuple[int, int, int, int]]:
    """Return crop boxes that divide an image into a grid.

    Each returned tuple is (left, upper, right, lower).

    >>> compute_grid_boxes(400, 400, 2)
    [(0, 0, 200, 200), (200, 0, 400, 200), (0, 200, 200, 400), (200, 200, 400, 400)]
    """
    boxes = []
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


def extract_grid_patches(image: Image.Image, grid_size: int) -> List[Tuple[Image.Image, int, int]]:
    """Return grid patches from image with each patch's top-left coordinates.

    Each result is (patch_image, patch_x, patch_y), where patch_x and patch_y
    are the patch's top-left coordinates in the original image.

    >>> image = Image.new("RGB", (400, 400))
    >>> patches = extract_grid_patches(image, 2)
    >>> len(patches)
    4
    >>> patches[0][1], patches[0][2]
    (0, 0)
    """
    patches = []

    for left, upper, right, lower in compute_grid_boxes(image.width, image.height, grid_size):
        patch = image.crop((left, upper, right, lower))
        patches.append((patch, left, upper))

    return patches


def center_crop_to_square(image: Image.Image, size: int) -> Image.Image:
    """Return a center-cropped size-by-size sub-image from image.

    Raise ValueError if image is smaller than size in either dimension.

    >>> image = Image.new("RGB", (300, 280))
    >>> cropped = center_crop_to_square(image, 224)
    >>> cropped.size
    (224, 224)
    """
    if image.width < size or image.height < size:
        raise ValueError(
            f"Cannot center crop {size}x{size} from patch of size {image.width}x{image.height}."
        )

    left = (image.width - size) // 2
    upper = (image.height - size) // 2
    right = left + size
    lower = upper + size
    return image.crop((left, upper, right, lower))


def downsample_to_square(image: Image.Image, size: int) -> Image.Image:
    """Return image resized to size-by-size using bicubic resampling.

    >>> image = Image.new("RGB", (500, 300))
    >>> resized = downsample_to_square(image, 224)
    >>> resized.size
    (224, 224)
    """
    return image.resize((size, size), resample=Image.Resampling.BICUBIC)


def build_patch_s3_key(
    prefix: str,
    image_id: str,
    patch_x: int,
    patch_y: int,
    patch_type: str,
) -> str:
    """Return the S3 key to use for a saved patch.

    >>> build_patch_s3_key("patches", "img123", 0, 224, "center_crop")
    'patches/img123/x0_y224_center_crop.jpg'
    """
    safe_prefix = prefix.rstrip("/")
    return f"{safe_prefix}/{image_id}/x{patch_x}_y{patch_y}_{patch_type}.jpg"


def upload_image_to_s3(image: Image.Image, bucket_name: str, key: str) -> None:
    """Upload image as a JPEG to S3 at bucket_name/key.

    >>> image = Image.new("RGB", (224, 224))
    >>> upload_image_to_s3(image, "my-bucket", "patches/sample.jpg")  # doctest: +SKIP
    """
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=95)
    buffer.seek(0)

    s3_client = boto3.client("s3")
    s3_client.put_object(
        Bucket=bucket_name,
        Key=key,
        Body=buffer.getvalue(),
        ContentType="image/jpeg",
    )


def upload_patch_record_to_dynamodb(record: PatchRecord, table_name: str) -> None:
    """Store a PatchRecord in DynamoDB.

    The PatchRecord is converted into a dictionary and inserted
    into the DynamoDB table.

    >>> record = PatchRecord(
    ...     patch_path="patches/a.jpg",
    ...     image_id="img123",
    ...     patch_type="center_crop"
    ... )
    >>> upload_patch_record_to_dynamodb(record, "PatchTable")  # doctest: +SKIP
    """
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)

    table.put_item(Item=asdict(record))


def make_patch_record(
    image_id: str,
    patch_path: str,
    patch_type: str,
    patch_x: int,
    patch_y: int,
    patch_width: int,
    patch_height: int,
) -> PatchRecord:
    """Return a PatchRecord describing a saved patch.

    >>> record = make_patch_record("img123", "patches/a.jpg", "downsample", 0, 0, 224, 224)
    >>> record.image_id
    'img123'
    >>> record.patch_width, record.patch_height
    (224, 224)
    """
    return PatchRecord(
        patch_path=patch_path,
        image_id=image_id,
        patch_type=patch_type,
        patch_x=patch_x,
        patch_y=patch_y,
        patch_width=patch_width,
        patch_height=patch_height,
    )


def create_center_crop_patch(
    source_patch: Image.Image,
    image_id: str,
    patch_x: int,
    patch_y: int,
    patch_bucket: str,
    patch_prefix: str,
    patch_table_name: str,
) -> PatchRecord:
    """Create, save, and return a center-cropped 224x224 PatchRecord.

    The cropped patch image is saved to S3, and the PatchRecord metadata
    is saved to DynamoDB.

    >>> patch = Image.new("RGB", (300, 300))
    >>> create_center_crop_patch(  # doctest: +SKIP
    ...     patch, "img123", 0, 0,
    ...     "patch-bucket", "patches",
    ...     "PatchTable"
    ... )
    PatchRecord(...)
    """
    cropped = center_crop_to_square(source_patch, TARGET_PATCH_SIZE)
    patch_type = "center_crop"

    patch_key = build_patch_s3_key(
        patch_prefix,
        image_id,
        patch_x,
        patch_y,
        patch_type,
    )
    upload_image_to_s3(cropped, patch_bucket, patch_key)

    record = make_patch_record(
        image_id=image_id,
        patch_path=patch_key,
        patch_type=patch_type,
        patch_x=patch_x,
        patch_y=patch_y,
        patch_width=TARGET_PATCH_SIZE,
        patch_height=TARGET_PATCH_SIZE,
    )

    upload_patch_record_to_dynamodb(record, patch_table_name)
    return record


def create_downsample_patch(
    source_patch: Image.Image,
    image_id: str,
    patch_x: int,
    patch_y: int,
    patch_bucket: str,
    patch_prefix: str,
    record_bucket: str,
    record_prefix: str,
) -> PatchRecord:
    """Create, save, and return a bicubic-downsampled 224x224 PatchRecord.

    >>> patch = Image.new("RGB", (300, 500))
    >>> create_downsample_patch(  # doctest: +SKIP
    ...     patch, "img123", 0, 0,
    ...     "patch-bucket", "patches",
    ...     "record-bucket", "records"
    ... )
    PatchRecord(...)
    """
    resized = downsample_to_square(source_patch, TARGET_PATCH_SIZE)
    patch_type = "downsample"
    patch_key = build_patch_s3_key(patch_prefix, image_id, patch_x, patch_y, patch_type)
    upload_image_to_s3(resized, patch_bucket, patch_key)

    record = make_patch_record(
        image_id=image_id,
        patch_path=patch_key,
        patch_type=patch_type,
        patch_x=patch_x,
        patch_y=patch_y,
        patch_width=TARGET_PATCH_SIZE,
        patch_height=TARGET_PATCH_SIZE,
    )
    record_key = f"{record_prefix.rstrip('/')}/{record.patch_id}.json"
    upload_patch_record_to_s3(record, record_bucket, record_key)
    return record


def create_downsample_patch(
    source_patch: Image.Image,
    image_id: str,
    patch_x: int,
    patch_y: int,
    patch_bucket: str,
    patch_prefix: str,
    patch_table_name: str,
) -> PatchRecord:
    """Create, save, and return a bicubic-downsampled 224x224 PatchRecord.

    The resized patch image is saved to S3, and the PatchRecord metadata
    is saved to DynamoDB.

    >>> patch = Image.new("RGB", (300, 500))
    >>> create_downsample_patch(  # doctest: +SKIP
    ...     patch, "img123", 0, 0,
    ...     "patch-bucket", "patches",
    ...     "PatchTable"
    ... )
    PatchRecord(...)
    """
    resized = downsample_to_square(source_patch, TARGET_PATCH_SIZE)
    patch_type = "downsample"

    patch_key = build_patch_s3_key(
        patch_prefix,
        image_id,
        patch_x,
        patch_y,
        patch_type,
    )
    upload_image_to_s3(resized, patch_bucket, patch_key)

    record = make_patch_record(
        image_id=image_id,
        patch_path=patch_key,
        patch_type=patch_type,
        patch_x=patch_x,
        patch_y=patch_y,
        patch_width=TARGET_PATCH_SIZE,
        patch_height=TARGET_PATCH_SIZE,
    )

    upload_patch_record_to_dynamodb(record, patch_table_name)
    return record


 def preprocess_image_record(
    image_record: ImageRecord,
    image_bucket: str,
    patch_bucket: str,
    patch_prefix: str,
    patch_table_name: str,
) -> List[PatchRecord]:
    """Preprocess the image referenced by image_record and return PatchRecords.

    The image is retrieved from S3 using image_record.image_path.
    Then:
    - choose 1x1, 2x2, or 4x4 grid based on the smaller side
    - derive center-cropped 224x224 patches
    - derive bicubic-downsampled 224x224 patches
    - save patch images to S3
    - save PatchRecord metadata to DynamoDB

    >>> image_record = ImageRecord(image_id="img123", image_path="images/sample.jpg")
    >>> preprocess_image_record(  # doctest: +SKIP
    ...     image_record,
    ...     image_bucket="image-bucket",
    ...     patch_bucket="patch-bucket",
    ...     patch_prefix="patches",
    ...     patch_table_name="PatchTable",
    ... )
    [PatchRecord(...)]
    """
    image = load_image_from_s3(image_bucket, image_record.image_path)
    grid_size = choose_grid_size(image.width, image.height)

    patch_records = []
    grid_patches = extract_grid_patches(image, grid_size)

    for patch_image, patch_x, patch_y in grid_patches:
        patch_records.extend(
            process_single_grid_patch(
                patch_image=patch_image,
                image_id=image_record.image_id,
                patch_x=patch_x,
                patch_y=patch_y,
                patch_bucket=patch_bucket,
                patch_prefix=patch_prefix,
                patch_table_name=patch_table_name,
            )
        )

    return patch_records

def preprocess_image_record_from_dynamodb(
    image_table_name: str,
    image_id: str,
    image_bucket: str,
    patch_bucket: str,
    patch_prefix: str,
    patch_table_name: str,
) -> List[PatchRecord]:
    """Load an ImageRecord from DynamoDB, preprocess its image, and return PatchRecords.

    >>> preprocess_image_record_from_dynamodb(  # doctest: +SKIP
    ...     image_table_name="ImageTable",
    ...     image_id="img123",
    ...     image_bucket="image-bucket",
    ...     patch_bucket="patch-bucket",
    ...     patch_prefix="patches",
    ...     patch_table_name="PatchTable",
    ... )
    [PatchRecord(...)]
    """
    image_record = load_image_record_from_dynamodb(image_table_name, image_id)
    return preprocess_image_record(
        image_record=image_record,
        image_bucket=image_bucket,
        patch_bucket=patch_bucket,
        patch_prefix=patch_prefix,
        patch_table_name=patch_table_name,
    )
