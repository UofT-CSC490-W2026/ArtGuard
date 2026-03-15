from src.libs.dynamo import ImageRecord, PatchRecord
import cv2
from urllib.parse import urlparse
import boto3
import numpy as np
import dataclasses

s3 = boto3.client("s3")
PATCH_SIZE = 256
CENTER_SIZE = 224
DOWN_SIZE = 244


def parse_s3_url(url: str) -> tuple[str, str]:
    """Return the (bucket, key) parsed from an s3:// URI.
    """
    parsed = urlparse(url)

    if parsed.scheme != "s3":
        raise ValueError(f"Expected an s3:// URI, got: {url}")

    return parsed.netloc, parsed.path.lstrip("/")


def read_image_from_s3(bucket: str, key: str) -> np.ndarray:
    """Return the decoded BGR image stored at key in bucket.

    Reads the raw bytes from S3 and decodes them into a numpy array
    using OpenCV.
    """
    response = s3.get_object(Bucket=bucket, Key=key)
    img_bytes = response["Body"].read()

    np_arr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    if img is None:
        raise ValueError(f"Failed to decode image from S3: s3://{bucket}/{key}")

    return img


def upload_image_to_s3(bucket: str, key: str, img: np.ndarray) -> str:
    """Upload img to bucket at key as a JPEG and return its s3:// URI.

    Encodes the numpy BGR image as JPEG bytes and uploads them to S3
    with the appropriate content type.
    """
    _, buffer = cv2.imencode(".jpg", img)

    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=buffer.tobytes(),
        ContentType="image/jpeg"
    )

    return f"s3://{bucket}/{key}"


def remove_background(image_record: ImageRecord) -> ImageRecord:
    """Return a new ImageRecord whose image has been cropped to its largest contour.

    Reads the image at image_record.image_path, detects edges with Canny,
    finds the largest external contour, crops the image to its bounding box,
    and uploads the result to processed/<image_id>/clean.jpg in the same bucket.
    The returned record has updated image_path, image_width, and image_height;
    the original record is not modified.

    If no contours are found (e.g. the image has no background to remove),
    the original image_record is returned unchanged.
    """
    bucket, key = parse_s3_url(image_record.image_path)
    img = read_image_from_s3(bucket, key)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return image_record

    largest = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(largest)
    cropped = img[y:y+h, x:x+w]

    new_key = f"processed/{image_record.image_id}/clean.jpg"
    upload_image_to_s3(bucket, new_key, cropped)

    updated = dataclasses.replace(image_record, image_path=new_key, image_width=w, image_height=h)

    return updated


def split_into_patches(image_record: ImageRecord, image_bucket: str, patch_bucket: str) -> list[PatchRecord]:
    """Return PatchRecords for all patches and center crops tiled from the image.

    Divides the image into an approximately PATCH_SIZE x PATCH_SIZE grid.
    For each tile, two PatchRecords are produced and uploaded to patch_bucket:
      - "centered": a CENTER_SIZE x CENTER_SIZE crop from the center of the
        original resolution tile
      - "down-sized": the tile resized to DOWN_SIZE x DOWN_SIZE, uploaded after
        the center crop has been taken from the full resolution

    Pixel columns/rows that don't divide evenly are dropped from the right/bottom
    edges, which is acceptable for ML patch workflows.
    """
    img = read_image_from_s3(image_bucket, image_record.image_path)

    h, w = img.shape[:2]

    patches_x = max(1, round(w / PATCH_SIZE))
    patches_y = max(1, round(h / PATCH_SIZE))

    patch_w = w // patches_x
    patch_h = h // patches_y

    patch_records = []

    for j in range(patches_y):
        for i in range(patches_x):

            x = i * patch_w
            y = j * patch_h

            patch_img = img[y:y+patch_h, x:x+patch_w]

            # Take the CENTER_SIZE x CENTER_SIZE crop from the original resolution
            # tile first. Tiles are always >= PATCH_SIZE (256) px so a CENTER_SIZE
            # (224) crop is always valid without resizing.
            ph, pw = patch_img.shape[:2]
            cx = (pw - CENTER_SIZE) // 2
            cy = (ph - CENTER_SIZE) // 2
            center_img = patch_img[cy:cy + CENTER_SIZE, cx:cx + CENTER_SIZE]

            center_key = f"{image_record.image_id}/{i}_{j}_centered.jpg"
            center_path = upload_image_to_s3(patch_bucket, center_key, center_img)

            patch_records.append(PatchRecord(
                patch_path=center_path,
                image_id=image_record.image_id,
                patch_type="centered",
                patch_x=x + cx,
                patch_y=y + cy,
                patch_width=CENTER_SIZE,
                patch_height=CENTER_SIZE,
            ))

            # Resize the tile to DOWN_SIZE x DOWN_SIZE and upload after the center
            # crop has been taken from the original resolution.
            down_img = cv2.resize(patch_img, (DOWN_SIZE, DOWN_SIZE), interpolation=cv2.INTER_AREA)

            key = f"{image_record.image_id}/{i}_{j}.jpg"
            patch_path = upload_image_to_s3(patch_bucket, key, down_img)

            patch_records.append(PatchRecord(
                patch_path=patch_path,
                image_id=image_record.image_id,
                patch_type="down-sized",
                patch_x=x,
                patch_y=y,
                patch_width=DOWN_SIZE,
                patch_height=DOWN_SIZE,
            ))

    return patch_records