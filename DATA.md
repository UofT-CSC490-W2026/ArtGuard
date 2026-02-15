# ArtGuard Data Architecture

Complete documentation of DynamoDB schemas, S3 storage structure, and data workflows.

---

## Table of Contents

1. [DynamoDB Tables](#dynamodb-tables)
2. [S3 Storage Structure](#s3-storage-structure)
3. [Data Workflows](#data-workflows)
4. [Query Patterns](#query-patterns)
5. [Cost Analysis](#cost-analysis)
6. [Privacy & Compliance](#privacy--compliance)
7. [Deployment](#deployment)

---

## DynamoDB Tables

### Table 1: Image Analysis (`artguard-image-analysis-{env}`)

**Purpose:** Stores all forgery detection analysis results, including metadata, AI reasoning, and analysis status.

#### Schema

| Attribute | Type | Key | Required | Description |
|-----------|------|-----|----------|-------------|
| `request_id` | String | **PK** | ✅ | Unique UUID for each analysis request |
| `created_at` | Number | **SK** | ✅ | Unix timestamp in milliseconds |
| `user_id` | String | GSI-PK | ✅ | User ID from Cognito or "anonymous" |
| `status` | String | GSI-PK | ✅ | `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED` |
| `filename` | String | - | ✅ | Original filename uploaded by user |
| `content_type` | String | - | ✅ | MIME type (e.g., `image/jpeg`) |
| `size_bytes` | Number | - | ✅ | File size in bytes |
| `forgery_score` | Number | - | Optional | Confidence score 0-100 (from Modal) |
| `verdict` | String | - | Optional | `AUTHENTIC`, `SUSPICIOUS`, `LIKELY_FORGED` |
| `ai_analysis` | String | - | Optional | Detailed reasoning from Bedrock Claude |
| `model` | String | - | Optional | Model used: `bedrock`, `modal`, `bedrock+modal` |
| `raw_image_url` | String | - | Optional | S3 URI if image saved (opt-in only) |
| `processed_image_url` | String | - | Optional | S3 URI of processed image |
| `image_saved` | Boolean | - | Optional | Whether image was saved to S3 |
| `timestamp_iso` | String | - | Optional | ISO 8601 timestamp |
| `auto_delete_date` | Number | - | Optional | Unix timestamp for auto-deletion (30 days) |
| `error_message` | String | - | Optional | Error details if status=FAILED |

#### Global Secondary Indexes (GSI)

**1. user-index**
- **Purpose:** Query all analyses for a specific user
- **Keys:** `user_id` (PK), `created_at` (SK)
- **Projection:** ALL
- **Use Case:** User dashboard, history, pagination

**2. status-index**
- **Purpose:** Query all analyses with a specific status
- **Keys:** `status` (PK), `created_at` (SK)
- **Projection:** ALL
- **Use Case:** Admin monitoring, background job processing

#### Example Item

```json
{
  "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "created_at": 1707504000000,
  "user_id": "user_abc123",
  "status": "COMPLETED",
  "filename": "artwork_2024.jpg",
  "content_type": "image/jpeg",
  "size_bytes": 2458624,
  "forgery_score": 87,
  "verdict": "LIKELY_FORGED",
  "ai_analysis": "Analysis reveals inconsistent lighting patterns in the upper left quadrant. The shadow angles don't match the primary light source direction. Confidence: 87/100. Recommendation: LIKELY_FORGED",
  "model": "bedrock+modal",
  "image_saved": true,
  "raw_image_url": "s3://artguard-images-raw-dev/audit/20240209_180000_a1b2c3.jpg",
  "processed_image_url": "s3://artguard-images-processed-dev/20240209_180000_a1b2c3.jpg",
  "timestamp_iso": "2024-02-09T18:00:00.000Z",
  "auto_delete_date": 1710096000
}
```

---

### Table 2: Users (`artguard-users-{env}`)

**Purpose:** Stores user account information, subscription tiers, and usage statistics.

#### Schema

| Attribute | Type | Key | Required | Description |
|-----------|------|-----|----------|-------------|
| `user_id` | String | **PK** | ✅ | Unique user ID (Cognito sub) |
| `email` | String | GSI-PK | ✅ | User email address |
| `account_tier` | String | - | ✅ | `Free`, `Standard`, `Premium`, `Enterprise` |
| `total_uploads` | Number | - | ✅ | Total images analyzed |
| `created_at` | Number | - | ✅ | Account creation timestamp |
| `last_login` | Number | - | ✅ | Last login timestamp |
| `first_name` | String | - | Optional | User first name |
| `last_name` | String | - | Optional | User last name |
| `company` | String | - | Optional | Company/organization name |
| `api_key_hash` | String | - | Optional | Hashed API key for programmatic access |
| `monthly_quota` | Number | - | Optional | Monthly analysis limit |
| `quota_used` | Number | - | Optional | Analyses used this month |

#### Global Secondary Index

**email-index**
- **Purpose:** Query user by email (for login/lookup)
- **Keys:** `email` (PK)
- **Projection:** ALL
- **Use Case:** Authentication, forgot password, admin lookup

#### Example Item

```json
{
  "user_id": "cognito-sub-abc123xyz",
  "email": "john.doe@example.com",
  "first_name": "John",
  "last_name": "Doe",
  "account_tier": "Premium",
  "total_uploads": 247,
  "monthly_quota": 1000,
  "quota_used": 42,
  "created_at": 1704067200000,
  "last_login": 1707504000000,
  "company": "Acme Art Gallery"
}
```

---

## S3 Storage Structure

### Buckets

| Bucket Name | Purpose | Lifecycle Policy | Access |
|-------------|---------|------------------|--------|
| `artguard-images-raw-{env}` | Original uploaded images (opt-in only) | 30-day auto-delete | Private |
| `artguard-images-processed-{env}` | Preprocessed images for training | 90-day auto-delete | Private |
| `artguard-frontend-{env}` | React static assets | None | Public via CloudFront |
| `artguard-knowledge-base-{env}` | RAG documentation for Bedrock | Versioning enabled | Private |

### Directory Structure

```
artguard-images-raw-{env}/
├── training/                    ← Lambda preprocessing ENABLED
│   ├── authentic_v1/           (Model training data)
│   │   ├── img001.jpg
│   │   └── img002.jpg
│   └── forged_v1/              (Forged examples for training)
│       ├── img001.jpg
│       └── img002.jpg
└── inference/                      
    └── 
artguard-images-processed-{env}/
├── training/                    ← Preprocessed by Lambda
│   ├── authentic_v1/           (Resized, normalized, RGB)
│   └── forged_v1/
│
└── inference/                      
    └── 
```

### S3 Path Behaviors

| Path | Lambda Triggered? | Auto-Delete | Use Case |
|------|-------------------|-------------|----------|
| `training/*` | ✅ YES | ❌ Never | Training data preprocessing |
| `inference/*` | | | |

**Terraform:** [infra/terraform/s3.tf](infra/terraform/s3.tf)

---

## Data Workflows

### Workflow A: Real-Time Forgery Detection (Current)

**Use Case:** Interactive user uploads, immediate results

```
1. User uploads image → POST /detect-forgery
   ↓
2. Create DynamoDB entry (status=PENDING)
   request_id: UUID
   user_id: from auth token
   filename, size, content_type
   ↓
3. Preprocess image in-memory (main.py)
   - Resize to 2048px max
   - Convert to RGB
   - Normalize
   ↓
4. Parallel AI analysis
   ├─ Bedrock Claude → Text reasoning
   └─ Modal (optional) → Forgery score 0-100
   ↓
5. Update DynamoDB (status=COMPLETED)
   forgery_score: 87
   verdict: "LIKELY_FORGED"
   ai_analysis: "Detailed reasoning..."
   ↓
6. Return results to user
   Total time: 2-5 seconds
```

**Implementation:** [src/apps/main.py](src/apps/main.py)

---

### Workflow B: Training Data Upload

**Use Case:** Building training datasets for Modal fine-tuning

```
1. Run upload script
   python scripts/upload_training_data.py \
     --dataset-path ./data/authentic \
     --dataset-name authentic_v1
   ↓
2. Upload to S3 training/ prefix
   s3://artguard-images-raw-dev/training/authentic_v1/
   ↓
3. Lambda triggered automatically
   EventBridge → S3 event → Lambda function
   ↓
4. Preprocess images (Lambda)
   - Resize to 2048px max
   - Convert to RGB
   - Normalize pixel values
   - Add metadata tags
   ↓
5. Save to processed bucket
   s3://artguard-images-processed-dev/training/authentic_v1/
   ↓
6. Use for Modal model training
```

**Implementation:**
- Upload: [scripts/upload_training_data.py](scripts/upload_training_data.py)
- Lambda: [infra/lambda/image_processor/lambda_function.py](infra/lambda/image_processor/lambda_function.py)
- S3 trigger: [infra/terraform/s3.tf:417](infra/terraform/s3.tf#L417)

---

### Workflow C: Bedrock Upload


---

## Query Patterns

### 1. Get Specific Analysis Result

```python
import boto3

dynamodb = boto3.resource('dynamodb', region_name='ca-central-1')
table = dynamodb.Table('artguard-image-analysis-dev')

response = table.get_item(
    Key={
        'request_id': 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
        'created_at': 1707504000000
    }
)

item = response.get('Item')
print(f"Verdict: {item['verdict']}")
print(f"Score: {item['forgery_score']}")
```

---

### 2. Get User's Analysis History

```python
from boto3.dynamodb.conditions import Key

# Get last 20 analyses for user, newest first
response = table.query(
    IndexName='user-index',
    KeyConditionExpression=Key('user_id').eq('user_abc123'),
    ScanIndexForward=False,  # Descending order
    Limit=20
)

for item in response['Items']:
    print(f"{item['filename']}: {item['verdict']} ({item['forgery_score']}%)")
```

---

### 3. Get User by Email

```python
users_table = dynamodb.Table('artguard-users-dev')

response = users_table.query(
    IndexName='email-index',
    KeyConditionExpression=Key('email').eq('john.doe@example.com')
)

user = response['Items'][0] if response['Items'] else None
if user:
    print(f"User ID: {user['user_id']}")
    print(f"Tier: {user['account_tier']}")
    print(f"Total uploads: {user['total_uploads']}")
```

---

### 4. Update User Upload Count

```python
from datetime import datetime

users_table.update_item(
    Key={'user_id': 'user_abc123'},
    UpdateExpression='SET total_uploads = total_uploads + :inc, '
                     'last_login = :now, '
                     'quota_used = quota_used + :inc',
    ExpressionAttributeValues={
        ':inc': 1,
        ':now': int(datetime.now().timestamp() * 1000)
    }
)
```

---

### 5. Get Pending Analyses (Background Jobs)

```python
# For async batch processing
response = table.query(
    IndexName='status-index',
    KeyConditionExpression=Key('status').eq('PENDING')
)

pending_items = response['Items']
print(f"Found {len(pending_items)} pending analyses")
```

---

### 6. Update Analysis Status

```python
# When analysis completes
table.update_item(
    Key={
        'request_id': 'a1b2c3d4-e5f6-7890',
        'created_at': 1707504000000
    },
    UpdateExpression='SET #status = :completed, '
                     'forgery_score = :score, '
                     'verdict = :verdict, '
                     'ai_analysis = :analysis',
    ExpressionAttributeNames={
        '#status': 'status'  # 'status' is reserved keyword
    },
    ExpressionAttributeValues={
        ':completed': 'COMPLETED',
        ':score': 87,
        ':verdict': 'LIKELY_FORGED',
        ':analysis': 'Detailed AI reasoning text...'
    }
)
```

---

### 7. Monitoring Queries

```python
# Count analyses by status
for status in ['PENDING', 'PROCESSING', 'COMPLETED', 'FAILED']:
    response = table.query(
        IndexName='status-index',
        KeyConditionExpression=Key('status').eq(status),
        Select='COUNT'
    )
    print(f"{status}: {response['Count']}")

# Get average forgery score
response = table.scan(
    ProjectionExpression='forgery_score',
    FilterExpression='attribute_exists(forgery_score)'
)
scores = [item['forgery_score'] for item in response['Items']]
avg_score = sum(scores) / len(scores) if scores else 0
print(f"Average forgery score: {avg_score:.2f}")
```

---

### User Image Storage

**When user explicitly requests:**
```bash
curl -X POST https://api.artguard.com/detect-forgery?save_image=true \
  -F "file=@artwork.jpg"
```

**Benefits:**
- ✅ Audit trail for disputes
- ✅ Can reprocess with updated models
- ✅ User controls their data
- ✅ Automatic deletion after 30 days
- ✅ Still GDPR compliant (purpose limitation + retention limit)

**Responsibilities:**
- ❌ Must handle GDPR deletion requests
- ❌ Storage costs increase
- ❌ Legal responsibility for data

**Implementation (DynamoDB):**
```json
{
  "image_saved": true,
  "raw_image_url": "s3://artguard-images-raw-dev/audit/...",
  "auto_delete_date": 1710096000
}
```

**Implementation (S3):**
- Lifecycle policy auto-deletes after 30 days
- User can request early deletion via API
- Bucket versioning disabled (no history)

---

### GDPR Compliance Checklist

- ✅ **Data Minimization:** Only save what's necessary
- ✅ **Purpose Limitation:** Clear purpose for each attribute
- ✅ **Storage Limitation:** Auto-delete after 30 days
- ✅ **Transparency:** User knows what's saved
- ✅ **User Control:** Opt-in for image storage
- ✅ **Right to Deletion:** API endpoint for data deletion
- ✅ **Encryption:** At rest (AWS-managed) + in transit (TLS)
- ✅ **Access Control:** IAM roles, least privilege

**Right to Deletion endpoint:**
```python
@app.delete("/api/user/{user_id}/data")
async def delete_user_data(user_id: str):
    # Delete all DynamoDB items
    # Delete all S3 objects
    # Anonymize or delete user account
    pass
```

---

### Get Table Names

```bash
# Image analysis table
terraform output -raw dynamodb_image_analysis_table_name

# Users table
terraform output -raw dynamodb_users_table_name

# Use in application
export DYNAMODB_IMAGE_ANALYSIS_TABLE=$(terraform output -raw dynamodb_image_analysis_table_name)
export DYNAMODB_USERS_TABLE=$(terraform output -raw dynamodb_users_table_name)
```

### Verify Tables

```bash
# List tables
aws dynamodb list-tables --region ca-central-1

# Describe table
aws dynamodb describe-table \
  --table-name artguard-image-analysis-dev \
  --region ca-central-1

# Get item count
aws dynamodb scan \
  --table-name artguard-image-analysis-dev \
  --select COUNT \
  --region ca-central-1
```

---

## Monitoring

### CloudWatch Metrics

**Available metrics:**
- `ConsumedReadCapacityUnits` - Read throughput
- `ConsumedWriteCapacityUnits` - Write throughput
- `UserErrors` - Client-side errors
- `SystemErrors` - Server-side errors

**View in CloudWatch Dashboard:**
```bash
# Dashboard URL
echo "https://console.aws.amazon.com/cloudwatch/home?region=ca-central-1#dashboards:name=artguard-dashboard"
```

### View Logs

```bash
# DynamoDB API calls (CloudTrail)
aws logs tail /aws/cloudtrail --follow --region ca-central-1 | grep DynamoDB

# Application logs (ECS)
aws logs tail /ecs/artguard-backend-dev --follow --region ca-central-1
```

---

## Best Practices

### 1. Always Use Batch Operations

```python
# Bad: Individual writes (slow)
for item in items:
    table.put_item(Item=item)

# Good: Batch write (fast)
with table.batch_writer() as batch:
    for item in items:
        batch.put_item(Item=item)
```

### 2. Use Conditional Writes

```python
# Prevent overwriting existing items
table.put_item(
    Item=new_item,
    ConditionExpression='attribute_not_exists(request_id)'
)
```

### 3. Implement Pagination

```python
response = table.query(
    IndexName='user-index',
    KeyConditionExpression=Key('user_id').eq('user123'),
    Limit=20
)

# Get next page
if 'LastEvaluatedKey' in response:
    next_response = table.query(
        IndexName='user-index',
        KeyConditionExpression=Key('user_id').eq('user123'),
        ExclusiveStartKey=response['LastEvaluatedKey'],
        Limit=20
    )
```

### 4. Use Projection Expressions

```python
# Don't fetch unnecessary data
response = table.get_item(
    Key={'request_id': 'abc-123', 'created_at': 1707504000000},
    ProjectionExpression='forgery_score, verdict, ai_analysis'
)
```

### 5. Handle Errors Gracefully

```python
from botocore.exceptions import ClientError

try:
    response = table.put_item(Item=item)
except ClientError as e:
    if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
        print("Item already exists")
    else:
        raise
```

---
