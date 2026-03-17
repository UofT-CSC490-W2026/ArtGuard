from __future__ import annotations

from dataclasses import asdict, dataclass, field
from io import BytesIO
from typing import List, Tuple

import boto3
from PIL import Image, ImageFilter

from schemas import ImageRecord, PatchRecord


TARGET_PATCH_SIZE = 224
GRID_4X4_THRESHOLD = 1024
GRID_2X2_THRESHOLD = 512


@dataclass
class PreprocessConfig:
    """Store preprocessing options for baseline and ablation experiments.

    apply_gaussian_blur controls whether each grid patch is blurred before
    derived 224x224 patches are created.

    gaussian_blur_radius is the radius used by PIL's Gaussian blur filter.

    rotation_angles contains the rotation angles, in degrees, applied to each
    grid patch before derived patches are created. The baseline setting is [0].

    >>> config = PreprocessConfig()
    >>> config.rotation_angles
    [0]
    """
    apply_gaussian_blur: bool = False
    gaussian_blur_radius: float = 1.0
    rotation_angles: List[int] = field(default_factory=lambda: [0])


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

    return ImageRecord(**response["Item"])


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
    """Return the number of rows and columns used to split the image.

    If the smaller side is:
    - greater than 1024: use a 4 x 4 grid
    - greater than 512 and less than or equal to 1024: use a 2 x 2 grid

    >>> choose_grid_size(1600, 1400)
    4
    >>> choose_grid_size(900, 700)
    2
    """
    smaller_side = min(image_width, image_height)

    if smaller_side > GRID_4X4_THRESHOLD:
        return 4
    if GRID_2X2_THRESHOLD < smaller_side <= GRID_4X4_THRESHOLD:
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


def apply_gaussian_blur(image: Image.Image, radius: float) -> Image.Image:
    """Return a blurred copy of image using Gaussian blur.

    >>> image = Image.new("RGB", (300, 300))
    >>> blurred = apply_gaussian_blur(image, 1.5)
    >>> blurred.size
    (300, 300)
    """
    return image.filter(ImageFilter.GaussianBlur(radius=radius))


def rotate_patch(image: Image.Image, angle: int) -> Image.Image:
    """Return image rotated by angle degrees.

    expand=True is used so the full rotated image is preserved.

    >>> image = Image.new("RGB", (300, 200))
    >>> rotate_patch(image, 90).size
    (200, 300)
    """
    if angle == 0:
        return image.copy()

    return image.rotate(angle, expand=True)


def generate_patch_variants(
    patch_image: Image.Image,
    config: PreprocessConfig,
) -> List[Tuple[Image.Image, str]]:
    """Return transformed variants of patch_image for preprocessing.

    Each result is (variant_image, variant_suffix). The suffix is appended
    to the patch_type so ablation outputs can be distinguished.

    >>> patch = Image.new("RGB", (300, 300))
    >>> variants = generate_patch_variants(patch, PreprocessConfig())
    >>> variants[0][1]
    'orig'
    """
    variants = []

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
    patch_type_suffix: str = "",
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
    if patch_type_suffix:
        patch_type = f"{patch_type}_{patch_type_suffix}"

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
    patch_table_name: str,
    patch_type_suffix: str = "",
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
    if patch_type_suffix:
        patch_type = f"{patch_type}_{patch_type_suffix}"

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


def process_single_grid_patch(
    patch_image: Image.Image,
    image_id: str,
    patch_x: int,
    patch_y: int,
    patch_bucket: str,
    patch_prefix: str,
    patch_table_name: str,
    config: PreprocessConfig,
) -> List[PatchRecord]:
    """Return PatchRecords created from one grid patch.

    For each transformed patch variant:
    - create a center crop when possible
    - create a bicubic-downsampled patch

    >>> patch = Image.new("RGB", (300, 300))
    >>> records = process_single_grid_patch(  # doctest: +SKIP
    ...     patch, "img123", 0, 0,
    ...     "patch-bucket", "patches",
    ...     "PatchTable",
    ...     PreprocessConfig()
    ... )
    >>> len(records)  # doctest: +SKIP
    2
    """
    records = []

    for variant_image, variant_suffix in generate_patch_variants(patch_image, config):
        if variant_image.width >= TARGET_PATCH_SIZE and variant_image.height >= TARGET_PATCH_SIZE:
            records.append(
                create_center_crop_patch(
                    source_patch=variant_image,
                    image_id=image_id,
                    patch_x=patch_x,
                    patch_y=patch_y,
                    patch_bucket=patch_bucket,
                    patch_prefix=patch_prefix,
                    patch_table_name=patch_table_name,
                    patch_type_suffix=variant_suffix,
                )
            )

        records.append(
            create_downsample_patch(
                source_patch=variant_image,
                image_id=image_id,
                patch_x=patch_x,
                patch_y=patch_y,
                patch_bucket=patch_bucket,
                patch_prefix=patch_prefix,
                patch_table_name=patch_table_name,
                patch_type_suffix=variant_suffix,
            )
        )

    return records


def preprocess_image_record(
    image_record: ImageRecord,
    image_bucket: str,
    patch_bucket: str,
    patch_prefix: str,
    patch_table_name: str,
    config: PreprocessConfig,
) -> List[PatchRecord]:
    """Preprocess the image referenced by image_record and return PatchRecords.

    The image is retrieved from S3 using image_record.image_path.
    Then:
    - choose 2x2, or 4x4 grid based on the smaller side
    - optionally rotate each grid patch
    - optionally blur each grid patch
    - derive center-cropped 224x224 patches
    - derive bicubic-downsampled 224x224 patches
    - save patch images to S3
    - save PatchRecord metadata to DynamoDB

    >>> image_record = ImageRecord(image_id="img123", image_path="images/sample.jpg")
    >>> preprocess_image_record(  # doctest: +SKIP
    ...     image_record=image_record,
    ...     image_bucket="image-bucket",
    ...     patch_bucket="patch-bucket",
    ...     patch_prefix="patches",
    ...     patch_table_name="PatchTable",
    ...     config=PreprocessConfig(),
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
                config=config,
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
    config: PreprocessConfig,
) -> List[PatchRecord]:
    """Load an ImageRecord from DynamoDB, preprocess its image, and return PatchRecords.

    >>> preprocess_image_record_from_dynamodb(  # doctest: +SKIP
    ...     image_table_name="ImageTable",
    ...     image_id="img123",
    ...     image_bucket="image-bucket",
    ...     patch_bucket="patch-bucket",
    ...     patch_prefix="patches",
    ...     patch_table_name="PatchTable",
    ...     config=PreprocessConfig(),
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
        config=config,
    )
