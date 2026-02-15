"""
Lambda Function: Image Preprocessing
Triggered by S3 uploads to training/ prefix
Processes 1 image at a time (S3 event triggers per upload)
"""
import json
import boto3
import os
from PIL import Image, ImageOps
from io import BytesIO

s3_client = boto3.client('s3')
PROCESSED_BUCKET = os.environ['PROCESSED_BUCKET']
RAW_BUCKET = os.environ['RAW_BUCKET']


def handler(event, context):
    """
    Triggered when an image is uploaded to the raw images bucket (training/ prefix)
    Performs preprocessing: rotation correction, resizing, normalization
    Saves processed image to processed bucket
    """
    try:
        # Parse S3 event to get bucket and key
        for record in event['Records']:
            bucket = record['s3']['bucket']['name']
            key = record['s3']['object']['key']

            print(f"Processing image: s3://{bucket}/{key}")

            # Download image from S3
            response = s3_client.get_object(Bucket=bucket, Key=key)
            image_data = response['Body'].read()

            # Open image with PIL
            image = Image.open(BytesIO(image_data))
            print(f"Image size: {image.size}, mode: {image.mode}")

            # Perform image preprocessing
            processed_image = preprocess_image(image)

            # Upload processed image to processed bucket
            output_key = key.replace('training/', 'processed/')
            save_to_s3(processed_image, output_key)

            print(f"Processed image saved: s3://{PROCESSED_BUCKET}/{output_key}")

            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Image processed successfully',
                    'input': f's3://{bucket}/{key}',
                    'output': f's3://{PROCESSED_BUCKET}/{output_key}'
                })
            }

    except Exception as e:
        error_msg = f"Error processing image: {str(e)}"
        print(error_msg)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': error_msg})
        }


def preprocess_image(image):
    """
    Image preprocessing pipeline:
    1. Auto-rotate based on EXIF orientation
    2. Resize to standard dimensions (max 2048px)
    3. Normalize to RGB
    4. Optional: Apply slight sharpening for forensics
    """
    # 1. Auto-rotate based on EXIF
    try:
        image = ImageOps.exif_transpose(image)
        print("Applied EXIF rotation")
    except Exception:
        print("No EXIF rotation needed")

    # 2. Resize if too large (preserve aspect ratio)
    max_dimension = 2048
    if max(image.size) > max_dimension:
        ratio = max_dimension / max(image.size)
        new_size = tuple(int(dim * ratio) for dim in image.size)
        image = image.resize(new_size, Image.Resampling.LANCZOS)
        print(f"Resized to: {new_size}")

    # 3. Convert to RGB (handle PNG with alpha channel)
    if image.mode in ('RGBA', 'LA', 'P'):
        # Create white background for transparent images
        background = Image.new('RGB', image.size, (255, 255, 255))
        if image.mode == 'P':
            image = image.convert('RGBA')
        # Paste image on white background
        if image.mode in ('RGBA', 'LA'):
            background.paste(image, mask=image.split()[-1])
        else:
            background.paste(image)
        image = background
        print(f"Converted {image.mode} to RGB")
    elif image.mode != 'RGB':
        image = image.convert('RGB')
        print(f"Converted to RGB")

    return image


def save_to_s3(image, output_key):
    """
    Save processed image to S3 processed bucket
    Uses JPEG format with high quality for forensic analysis
    """
    buffer = BytesIO()
    image.save(buffer, format='JPEG', quality=95, optimize=True)
    buffer.seek(0)

    s3_client.put_object(
        Bucket=PROCESSED_BUCKET,
        Key=output_key,
        Body=buffer.getvalue(),
        ContentType='image/jpeg',
        ServerSideEncryption='AES256'
    )
    print(f"Uploaded to S3: {output_key} ({len(buffer.getvalue())} bytes)")
