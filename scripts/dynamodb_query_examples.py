"""
DynamoDB Query Examples for ArtGuard Schema
Demonstrates efficient query patterns and "joins" using application-level logic
"""

import boto3
from boto3.dynamodb.conditions import Key
from typing import List, Dict, Optional
from datetime import datetime

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb', region_name='ca-central-1')

# Table references
users_table = dynamodb.Table('artguard-users-dev')
inferences_table = dynamodb.Table('artguard-inference-records-dev')
images_table = dynamodb.Table('artguard-image-records-dev')
patches_table = dynamodb.Table('artguard-patch-records-dev')


# ========================================
# User Operations
# ========================================

def get_user_by_id(user_id: str) -> Optional[Dict]:
    """Get user by user_id (primary key lookup - fast)"""
    response = users_table.get_item(Key={'user_id': user_id})
    return response.get('Item')


def get_user_by_email(email: str) -> Optional[Dict]:
    """Get user by email (GSI query)"""
    response = users_table.query(
        IndexName='EmailIndex',
        KeyConditionExpression=Key('email').eq(email)
    )
    items = response.get('Items', [])
    return items[0] if items else None


def create_user(user_id: str, username: str, password_hash: str, email: str):
    """Create a new user"""
    users_table.put_item(
        Item={
            'user_id': user_id,
            'username': username,
            'password': password_hash,  # Should be hashed!
            'email': email,
            'created_at': int(datetime.now().timestamp() * 1000)
        }
    )


# ========================================
# Inference Operations
# ========================================

def create_inference(inference_id: str, user_id: str, image_path: str,
                     score: float, explanation: Optional[str] = None,
                     image_name: Optional[str] = None):
    """Create a new inference record"""
    inferences_table.put_item(
        Item={
            'inference_id': inference_id,
            'user_id': user_id,
            'image_name': image_name,
            'image_path': image_path,
            'score': score,
            'explanation': explanation,
            'created_at': int(datetime.now().timestamp() * 1000),
            'ttl': int((datetime.now().timestamp() + 90 * 24 * 3600)) # 90 days
        }
    )


def get_inference_by_id(inference_id: str) -> Optional[Dict]:
    """Get specific inference (primary key lookup)"""
    response = inferences_table.get_item(Key={'inference_id': inference_id})
    return response.get('Item')


def get_user_inferences(user_id: str, limit: int = 20) -> List[Dict]:
    """Get all inferences for a user (sorted by time, most recent first)"""
    response = inferences_table.query(
        IndexName='UserInferencesIndex',
        KeyConditionExpression=Key('user_id').eq(user_id),
        ScanIndexForward=False,  # Descending order (newest first)
        Limit=limit
    )
    return response.get('Items', [])


# ========================================
# "JOIN" Example: Inference with User Details
# ========================================

def get_inference_with_user(inference_id: str) -> Optional[Dict]:
    """
    Application-level join: Get inference AND user details
    This is what would be a SQL JOIN - done in 2 queries
    """
    # Step 1: Get the inference
    inference = get_inference_by_id(inference_id)
    if not inference:
        return None

    # Step 2: Get the user details (using user_id from inference)
    user = get_user_by_id(inference['user_id'])

    # Combine the data
    return {
        **inference,
        'user': user  # Nested user object
    }


def get_user_inferences_with_details(user_id: str, limit: int = 20) -> Dict:
    """
    Get user info + all their inferences in one call
    Efficient: 2 queries total (not 1 per inference)
    """
    # Get user and inferences in parallel
    user = get_user_by_id(user_id)
    inferences = get_user_inferences(user_id, limit)

    return {
        'user': user,
        'inferences': inferences,
        'total_inferences': len(inferences)
    }


# ========================================
# Image Operations
# ========================================

def create_image(image_id: str, image_name: str, image_path: str,
                 width: int, height: int, label: str, split: str,
                 sublabel: Optional[str] = None,
                 attributed_creator: Optional[str] = None,
                 actual_creator: Optional[str] = None):
    """Create a new image record"""
    images_table.put_item(
        Item={
            'image_id': image_id,
            'image_name': image_name,
            'image_path': image_path,
            'image_width': width,
            'image_height': height,
            'label': label,
            'sublabel': sublabel,
            'split': split,
            'attributed_creator': attributed_creator,
            'actual_creator': actual_creator,
            'created_at': int(datetime.now().timestamp() * 1000)
        }
    )


def get_image_by_id(image_id: str) -> Optional[Dict]:
    """Get specific image (primary key lookup)"""
    response = images_table.get_item(Key={'image_id': image_id})
    return response.get('Item')


def get_images_by_label_and_split(label: str, split: str, limit: int = 100) -> List[Dict]:
    """Get all images with specific label in a dataset split (GSI query)"""
    response = images_table.query(
        IndexName='LabelSplitIndex',
        KeyConditionExpression=Key('label').eq(label) & Key('split').eq(split),
        Limit=limit
    )
    return response.get('Items', [])


# ========================================
# Patch Operations
# ========================================

def create_patch(patch_id: str, patch_path: str, image_id: str,
                 patch_type: str, x: int, y: int, width: int, height: int):
    """Create a new patch record"""
    patches_table.put_item(
        Item={
            'patch_id': patch_id,
            'patch_path': patch_path,
            'image_id': image_id,
            'patch_type': patch_type,
            'patch_x': x,
            'patch_y': y,
            'patch_width': width,
            'patch_height': height,
            'created_at': int(datetime.now().timestamp() * 1000)
        }
    )


def get_patch_by_id(patch_id: str) -> Optional[Dict]:
    """Get specific patch (primary key lookup)"""
    response = patches_table.get_item(Key={'patch_id': patch_id})
    return response.get('Item')


def get_image_patches(image_id: str, patch_type: Optional[str] = None) -> List[Dict]:
    """Get all patches for an image (GSI query)"""
    if patch_type:
        # Filter by patch type as well
        response = patches_table.query(
            IndexName='ImagePatchesIndex',
            KeyConditionExpression=Key('image_id').eq(image_id) & Key('patch_type').eq(patch_type)
        )
    else:
        # All patches for this image
        response = patches_table.query(
            IndexName='ImagePatchesIndex',
            KeyConditionExpression=Key('image_id').eq(image_id)
        )
    return response.get('Items', [])


# ========================================
# "JOIN" Example: Image with All Patches
# ========================================

def get_image_with_patches(image_id: str) -> Optional[Dict]:
    """
    Application-level join: Get image AND all its patches
    This is what would be a SQL JOIN - done in 2 queries
    """
    # Step 1: Get the image
    image = get_image_by_id(image_id)
    if not image:
        return None

    # Step 2: Get all patches for this image
    patches = get_image_patches(image_id)

    # Combine the data
    return {
        **image,
        'patches': patches,
        'patch_count': len(patches)
    }


def get_image_with_patches_by_type(image_id: str) -> Optional[Dict]:
    """
    Get image with patches grouped by type
    Useful for analysis: authentic vs forged patches
    """
    image = get_image_by_id(image_id)
    if not image:
        return None

    # Get patches by type
    authentic_patches = get_image_patches(image_id, 'authentic')
    forged_patches = get_image_patches(image_id, 'forged')

    return {
        **image,
        'patches': {
            'authentic': authentic_patches,
            'forged': forged_patches,
            'total': len(authentic_patches) + len(forged_patches)
        }
    }


# ========================================
# Batch Operations (Efficient for Multiple Items)
# ========================================

def get_images_with_patches_batch(image_ids: List[str]) -> List[Dict]:
    """
    Efficiently get multiple images with their patches
    Uses batch operations to minimize round trips
    """
    # Batch get all images
    response = dynamodb.batch_get_item(
        RequestItems={
            images_table.name: {
                'Keys': [{'image_id': img_id} for img_id in image_ids]
            }
        }
    )
    images = response['Responses'][images_table.name]

    # Get patches for each image (could be done in parallel)
    results = []
    for image in images:
        patches = get_image_patches(image['image_id'])
        results.append({
            **image,
            'patches': patches
        })

    return results


# ========================================
# Usage Examples
# ========================================

if __name__ == '__main__':
    # Example 1: Get inference with user details (JOIN)
    inference_with_user = get_inference_with_user('inference-123')
    print(f"Inference by {inference_with_user['user']['username']}")
    print(f"Score: {inference_with_user['score']}")

    # Example 2: Get all inferences for a user
    user_data = get_user_inferences_with_details('user-456')
    print(f"User {user_data['user']['email']} has {user_data['total_inferences']} inferences")

    # Example 3: Get image with all patches (JOIN)
    image_with_patches = get_image_with_patches('image-789')
    print(f"Image has {image_with_patches['patch_count']} patches")

    # Example 4: Get training images labeled as "forged"
    forged_train_images = get_images_by_label_and_split('forged', 'train')
    print(f"Found {len(forged_train_images)} forged training images")

    # Example 5: Batch get multiple images with patches
    images = get_images_with_patches_batch(['image-1', 'image-2', 'image-3'])
    for img in images:
        print(f"{img['image_name']}: {len(img['patches'])} patches")
