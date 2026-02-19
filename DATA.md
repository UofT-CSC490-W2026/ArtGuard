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

### Table 1: Users (`artguard-users-{env}`)

**Purpose:** User accounts and authentication.

#### Schema

| Attribute | Type | Key | Description |
|-----------|------|-----|-------------|
| `user_id` | String | **PK** | Unique user ID |
| `email` | String | GSI-PK |User email address |
| `username` | String | - | Username for login |
| `password` | String | - | Hashed password |

#### Global Secondary Index

**Email Index**
- **Keys:** `email` (PK)
- **Use Case:** Login by email

---

### Table 2: InferenceRecords (`artguard-inference-records-{env}`)

**Purpose:** Stores forgery detection inference results.

#### Schema

| Attribute | Type | Key | Required | Description |
|-----------|------|-----|----------|-------------|
| `inference_id` | String | **PK** | - | Unique inference ID |
| `user_id` | String | GSI-PK | - | Foreign key to Users table |
| `created_at` | Number | GSI-SK | - | Unix timestamp in milliseconds |
| `image_name` | String | - | Optional | Name of analyzed image |
| `image_path` | String | - | - | S3 path to image |
| `score` | Number | - | - | Forgery confidence score 0.0-1.0 |
| `explanation` | String | - | Optional | AI analysis explanation |
| `ttl` | Number | - | Optional | Auto-delete timestamp (90 days) |

#### Global Secondary Index

**UserInferencesIndex**
- **Keys:** `user_id` (PK), `created_at` (SK)
- **Use Case:** Get all inferences for a user, sorted by time

---

### Table 3: ImageRecords (`artguard-image-records-{env}`)

**Purpose:** Dataset images for training and testing.

#### Schema

| Attribute | Type | Key | Required | Description |
|-----------|------|-----|----------|-------------|
| `image_id` | String | **PK** | - | Unique image ID |
| `image_name` | String | - | - | Image filename |
| `image_path` | String | - | - | S3 path to image |
| `image_width` | Number | - | - | Image width in pixels |
| `image_height` | Number | - | - | Image height in pixels |
| `label` | String | GSI-PK | - | Image label (e.g., "authentic", "forged") |
| `sublabel` | String | - | Optional | Sublabel for classification |
| `split` | String | GSI-SK | - | Dataset split ("train", "val", "test") |
| `attributed_creator` | String | - | Optional | Attributed artist/creator |
| `actual_creator` | String | - | Optional | Actual creator if different |

#### Global Secondary Index

**LabelSplitIndex**
- **Keys:** `label` (PK), `split` (SK)
- **Use Case:** Get all images with specific label in a dataset split

---

### Table 4: PatchRecords (`artguard-patch-records-{env}`)

**Purpose:** Image patches extracted for analysis.

#### Schema

| Attribute | Type | Key | Required | Description |
|-----------|------|-----|----------|-------------|
| `patch_id` | String | **PK** | - | Unique patch ID |
| `patch_path` | String | - | - | S3 path to patch image |
| `image_id` | String | GSI-PK | - | Foreign key to ImageRecords table |
| `patch_type` | String | GSI-SK | - | Patch type ("authentic", "forged") |
| `patch_x` | Number | - | - | X coordinate in source image |
| `patch_y` | Number | - | - | Y coordinate in source image |
| `patch_width` | Number | - | - | Patch width in pixels |
| `patch_height` | Number | - | - | Patch height in pixels |

#### Global Secondary Index

**ImagePatchesIndex**
- **Keys:** `image_id` (PK), `patch_type` (SK)
- **Use Case:** Get all patches for an image, optionally filtered by type

---

### Table 5: RunRecords (`artguard-run-records-{env}`)

**Purpose:** Stores each training run's metadata, data split configuration, and averaged metrics across folds.

#### Schema

| Attribute | Type | Key | Required | Description |
|-----------|------|-----|----------|-------------|
| `run_id` | String | **PK** | - | Unique run ID (UUID) |
| `created_at` | Number | GSI-SK | - | Unix timestamp in milliseconds |
| `status` | String | GSI-PK | - | Run status ("running", "completed", "failed") |
| `dataset_version` | String | GSI-PK | - | Dataset version identifier |
| `modal_volume_path` | String | - | Optional | Path to Modal volume with artifacts |
| `best_config_id` | String | - | Optional | Foreign key to best ConfigRecord |
| `k_folds` | Number | - | - | Number of cross-validation folds (default: 5) |
| `stratify_on` | String | - | - | Stratification attribute (default: "sublabel") |
| `outer_split_seed` | Number | - | - | Seed for outer split reproducibility |
| `inner_split_seed` | Number | - | - | Seed for inner split reproducibility |
| `mean_accuracy` | Number | - | Optional | Mean accuracy across folds |
| `mean_auc` | Number | - | Optional | Mean AUC across folds |
| `mean_f1` | Number | - | Optional | Mean F1 score across folds |
| `mean_precision` | Number | - | Optional | Mean precision across folds |
| `mean_recall` | Number | - | Optional | Mean recall across folds |
| `std_accuracy` | Number | - | Optional | Std dev of accuracy across folds |
| `std_auc` | Number | - | Optional | Std dev of AUC across folds |
| `std_f1` | Number | - | Optional | Std dev of F1 across folds |
| `std_precision` | Number | - | Optional | Std dev of precision across folds |
| `std_recall` | Number | - | Optional | Std dev of recall across folds |

#### Global Secondary Indexes

**StatusIndex**
- **Keys:** `status` (PK), `created_at` (SK)
- **Use Case:** Find all running/completed/failed runs, sorted by time

**DatasetVersionIndex**
- **Keys:** `dataset_version` (PK), `created_at` (SK)
- **Use Case:** Find all runs for a specific dataset version, sorted by time

---

### Table 6: ConfigRecords (`artguard-config-records-{env}`)

**Purpose:** Stores each hyperparameter configuration per fold, including training metrics and whether it was the best config in the fold.

#### Schema

| Attribute | Type | Key | Required | Description |
|-----------|------|-----|----------|-------------|
| `config_id` | String | **PK** | - | Unique config ID (UUID) |
| `created_at` | Number | - | - | Unix timestamp in milliseconds |
| `run_id` | String | GSI-PK | - | Foreign key to RunRecords table |
| `dataset_version` | String | - | - | Dataset version for reproducibility |
| `fold_id` | Number | GSI-SK | - | Fold number (0-indexed) |
| `hyperparameters` | Map | - | - | Hyperparameter key-value pairs |
| `best_epoch` | Number | - | Optional | Epoch with best validation metric |
| `best_val` | Number | - | Optional | Best validation metric value |
| `early_stopped` | Boolean | - | - | Whether training was early-stopped |
| `is_best_in_fold` | Boolean | - | - | Whether this config was best in the fold |
| `modal_volume_path` | String | - | Optional | Path to model weights on Modal volume |

#### Global Secondary Index

**RunConfigsIndex**
- **Keys:** `run_id` (PK), `fold_id` (SK)
- **Use Case:** Get all configs for a run, organized by fold

---

## S3 Storage Structure

### Buckets

| Bucket Name | Purpose | Lifecycle Policy | Access |
|-------------|---------|------------------|--------|
| `artguard-images-raw-{env}` | Original uploaded images  | 30-day auto-delete | Private |
| `artguard-images-processed-{env}` | Processed images | 90-day auto-delete | Private |
| `artguard-frontend-{env}` | React static assets | None | Public via CloudFront |
| `artguard-knowledge-base-{env}` | RAG documentation for Bedrock | Versioning enabled | Private |

### Directory Structure

```
artguard-images-raw-{env}/
├── training/
│   ├── authentic_v1/           (Model training image data)
│   │   ├── img001.jpg
│   │   └── img002.jpg
│   └── forged_v1/              (Forged examples for training)
│       ├── img001.jpg
│       └── img002.jpg
└── inference/                   (User uploaded image)   
|    └── 
└── processed /  (CHANGE W REAL NAME)
artguard-images-processed-{env}/
├── training/
│   ├── authentic_v1/           (Resized, normalized, RGB)
│   └── forged_v1/
│
└── inference/                      
|    └── 
└── processed/ (CHANGE W REAL NAME)
```

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
   - Convert to patches
   ↓
4. Parallel AI analysis
   ├─ Bedrock Claude → Text reasoning
   └─ Modal → Forgery score 0-100
   ↓
5. Update DynamoDB (status=COMPLETED)
   forgery_score: 87
   verdict: "LIKELY_FORGED"
   ai_analysis: "Detailed reasoning..."
   ↓
6. Return results to user
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
3. Lambda triggered automatically (EDIT THIS )
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
- list relevant files here 

---

### Workflow C: Bedrock Upload


---

### User Image Storage

**When user explicitly requests:**
```bash
curl -X POST https://api.artguard.com/detect-forgery \
  -F "file=@artwork.jpg"
```

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
# Users table
terraform output -raw dynamodb_users_table_name

# Inference records table
terraform output -raw dynamodb_inference_records_table_name

# Image records table
terraform output -raw dynamodb_image_records_table_name

# Patch records table
terraform output -raw dynamodb_patch_records_table_name

# Run records table
terraform output -raw dynamodb_run_records_table_name

# Config records table
terraform output -raw dynamodb_config_records_table_name

# Use in application
export USERS_TABLE=$(terraform output -raw dynamodb_users_table_name)
export INFERENCES_TABLE=$(terraform output -raw dynamodb_inference_records_table_name)
export IMAGES_TABLE=$(terraform output -raw dynamodb_image_records_table_name)
export PATCHES_TABLE=$(terraform output -raw dynamodb_patch_records_table_name)
export RUNS_TABLE=$(terraform output -raw dynamodb_run_records_table_name)
export CONFIGS_TABLE=$(terraform output -raw dynamodb_config_records_table_name)
```

### Verify Tables

```bash
# List tables
aws dynamodb list-tables --region ca-central-1

# Describe table
aws dynamodb describe-table \
  --table-name artguard-inference-records-dev \
  --region ca-central-1

# Get item count
aws dynamodb scan \
  --table-name artguard-inference-records-dev \
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
