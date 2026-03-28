# ArtGuard Backend

Python FastAPI backend serving the ArtGuard art forgery detection API. Handles authentication, image upload, inference orchestration (Modal GPU + Bedrock RAG), inference history, and training/evaluation job management.

## Table of Contents

1. [Architecture](#architecture)
2. [Authentication & Security](#authentication--security)
3. [Structured Logging](#structured-logging)
4. [API Reference](#api-reference)
5. [Environment Variables](#environment-variables)
6. [Troubleshooting](#troubleshooting)

---

## Architecture

```
src/apps/backend/
├── main.py              # FastAPI app, CORS, middleware, route registration
├── config.py            # Environment variable loading and validation
├── validation.py        # Shared input validation (field limits, filename sanitization)
├── logging_config.py    # Structured JSON logging + CloudWatch EMF metrics
├── prompts.py           # RAG prompt templates for Bedrock
├── security/
│   ├── auth.py          # JWT creation/validation, bcrypt password hashing
│   └── ...
├── services/
│   ├── inference_service.py  # Inference pipeline (S3 upload → Modal → Bedrock RAG)
│   ├── user_service.py       # User CRUD (DynamoDB)
│   └── ...
├── routes/
│   ├── auth.py          # /auth/* endpoints (signup, login, profile, password)
│   ├── inference.py     # /inference, /inferences/* endpoints
│   ├── rag.py           # /rag-query endpoint
│   └── ...
└── deps/                # FastAPI dependency injection (auth, AWS clients)
```

---

## Authentication & Security

User authentication uses **stateless JWT tokens** (HS256 algorithm) with **bcrypt-hashed passwords**. The JWT secret is stored in AWS Secrets Manager and loaded at container startup; a development-only fallback secret is provided for local testing, while production strictly requires the Secrets Manager value.

### How It Works

1. **Signup/Login**: User provides credentials → password verified against bcrypt hash → JWT issued with `user_id` and expiry
2. **Protected routes**: FastAPI dependency (`get_current_user_id`) extracts the Bearer token, validates signature and expiry, injects the authenticated `user_id` into the request context
3. **Failure**: Missing, expired, or invalid tokens return HTTP 401

### Input Validation

Input validation is centralized in `validation.py`, enforcing:
- Field length limits (username, email, artwork/artist names)
- Score clamping to [0.0, 1.0]
- Prediction value validation ({-1, 0, 1})
- Filename sanitization (path-traversal prevention, null-byte removal)

### Encryption

- **At rest**: AES-256 (S3), AWS-managed KMS keys (DynamoDB, Secrets Manager, OpenSearch)
- **In transit**: TLS 1.2+ (CloudFront enforces HTTPS; ECS communicates with AWS services via SDK default HTTPS)

---

## Structured Logging

All application logs are emitted as single-line JSON objects to stdout, forwarded by the ECS Fargate logging driver to CloudWatch Logs. This enables CloudWatch Logs Insights queries (filter by `request_id`, aggregate error rates, compute latency percentiles).

### Log Entry Fields

| Field | Description |
|-------|-------------|
| `timestamp` | ISO 8601 with millisecond precision |
| `level` | DEBUG, INFO, WARNING, ERROR |
| `logger` | Python logger name |
| `message` | Human-readable log message |
| `request_id` | 8-char UUID prefix, per-request (from `X-Request-ID` header or generated) |
| `user_id` | Authenticated user's ID (empty for unauthenticated) |
| `source` | File path and line number (WARNING+ only) |
| `exc_info` | Full traceback (only when handling exceptions) |

`request_id` and `user_id` use Python `ContextVar` instances (async-safe, request-scoped). The `RequestLoggingMiddleware` sets these at request start and resets after response.

### CloudWatch Embedded Metrics (EMF)

Custom metrics emitted inline in log entries — CloudWatch automatically extracts them without `PutMetricData` API calls:

- **`InferenceLatency`** (Seconds): End-to-end Modal inference duration
- **`RAGLatency`** (Seconds): Bedrock RetrieveAndGenerate call duration
- **`InferenceSuccess`** / **`InferenceError`** (Count): Success/failure counters
- **`RAGError`** (Count): Bedrock call failure counter

### Log Metric Filters

- **`ApplicationErrors`**: `$.level = "ERROR"`
- **`ApplicationWarnings`**: `$.level = "WARNING"`
- **`AuthFailures`**: `$.status = 401`

These drive CloudWatch alarms for error volume spikes.

---

## API Reference

### Setup

```bash
# Set your API base URL (no trailing slash)
export API_BASE="https://https://d1b5yxlog377uv.cloudfront.net"
```

All **authenticated** routes require a JWT token:

```http
Authorization: Bearer <access_token>
```

Get a token from `POST /auth/signup` or `POST /auth/login`.

---

### Public Endpoints (no auth required)

### Health Check

```bash
curl -sS "${API_BASE}/health" | jq .
# {"status": "ok"}
```

### API Info

```bash
curl -sS "${API_BASE}/" | jq .
```

### RAG Query

Query the Bedrock Knowledge Base for art-related information.

```bash
curl -sS -X POST "${API_BASE}/rag-query" \
  -H "Content-Type: application/json" \
  -d '{"query": "Tell me about Vincent van Gogh painting style"}' | jq .
# {"answer": "...", "sources": [{"s3_uri": "s3://...", "snippet": "..."}]}
```

---

## Authentication

### Sign Up

```bash
curl -sS -X POST "${API_BASE}/auth/signup" \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"test@example.com","password":"secret12"}' | jq .
# {"access_token": "eyJ...", "user_id": "...", "email": "..."}
```

### Log In (save token for subsequent requests)

```bash
export TOKEN=$(
  curl -sS -X POST "${API_BASE}/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"email":"test@example.com","password":"secret12"}' \
  | jq -r '.access_token'
)
echo "$TOKEN"
```

### Get Current User

```bash
curl -sS "${API_BASE}/auth/me" \
  -H "Authorization: Bearer ${TOKEN}" | jq .
# {"user_id": "...", "email": "...", "username": "..."}
```

### Update Profile

```bash
curl -sS -X PUT "${API_BASE}/auth/profile" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"username":"newname","email":"new@example.com"}' | jq .
```

### Change Password

```bash
curl -sS -X POST "${API_BASE}/auth/change-password" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"currentPassword":"secret12","newPassword":"newsecret34"}' | jq .
# {"message": "Password changed successfully"}
```

---

## Inference

### Submit Inference (multipart form upload)

Upload an artwork image for forgery detection. Returns a prediction (1=authentic, 0=forgery), confidence score, and RAG-generated explanation.

| Field | Type | Notes |
|---|---|---|
| `file` | file | Image upload (JPEG/PNG, max 20 MB) |
| `artist_name` | string | Required, non-empty |
| `artwork_name` | string | Required, non-empty |

```bash
curl -sS -X POST "${API_BASE}/inference" \
  -H "Authorization: Bearer ${TOKEN}" \
  -F "file=@/path/to/painting.jpg" \
  -F "artist_name=Vincent van Gogh" \
  -F "artwork_name=Starry Night" | jq .
# {
#   "inference_id": "...",
#   "prediction": 1,
#   "score": 0.87,
#   "explanation": "The forgery detection model...",
#   "image_url": "https://..."
# }
```

---

## Inference History

### Get Stats (count of user's inferences)

```bash
curl -sS "${API_BASE}/inferences/stats" \
  -H "Authorization: Bearer ${TOKEN}" | jq .
# {"count": 5}
```

### List Inferences (paginated)

```bash
# First page
curl -sS "${API_BASE}/inferences?limit=10" \
  -H "Authorization: Bearer ${TOKEN}" | jq .
# {"items": [...], "next_cursor": "eyJ..."}

# Next page (use the cursor from previous response)
curl -sS "${API_BASE}/inferences?limit=10&cursor=eyJ..." \
  -H "Authorization: Bearer ${TOKEN}" | jq .
```

### Get Single Inference

```bash
curl -sS "${API_BASE}/inferences/INFERENCE_ID" \
  -H "Authorization: Bearer ${TOKEN}" | jq .
```

### Delete Single Inference

```bash
curl -sS -X DELETE "${API_BASE}/inferences/INFERENCE_ID" \
  -H "Authorization: Bearer ${TOKEN}" \
  -w "\nHTTP %{http_code}\n"
# HTTP 204 (no content)
```

### Delete All Inferences

```bash
curl -sS -X DELETE "${API_BASE}/inferences" \
  -H "Authorization: Bearer ${TOKEN}" | jq .
# {"deleted": 5}
```

---

## Training and Evaluation (admin)

### Start Training

Spawns a Modal GPU training job for the specified Swin variant.

```bash
curl -sS -X POST "${API_BASE}/train" \
  -H "Content-Type: application/json" \
  -d '{"variant": "tiny"}' | jq .
# {"run_id": "...", "variant": "tiny", "status": "started"}

# With custom config
curl -sS -X POST "${API_BASE}/train" \
  -H "Content-Type: application/json" \
  -d '{"variant": "base", "config": {"lr": 0.001, "batch_size": 16}}' | jq .
```

### Start Evaluation

Spawns a Modal GPU evaluation job against a saved checkpoint.

```bash
curl -sS -X POST "${API_BASE}/evaluate" \
  -H "Content-Type: application/json" \
  -d '{"variant": "tiny", "checkpoint": "/checkpoints/tiny/best.pt"}' | jq .
# {"run_id": "...", "variant": "tiny", "checkpoint": "...", "status": "started"}
```

---

## Data Processing (admin)

### Launch ECS Processing Task

Triggers the data pipeline Fargate task to process unprocessed images in S3.

```bash
curl -sS -X POST "${API_BASE}/process_data" | jq .
# {"run_id": "...", "task_arn": "arn:aws:ecs:..."}
```

---

## Quick Start: end-to-end test

```bash
API_BASE="https://dxxxx.cloudfront.net"   # edit

# 1. Health check
curl -sS "${API_BASE}/health" | jq .

# 2. Sign up + get token
TOKEN=$(curl -sS -X POST "${API_BASE}/auth/signup" \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","email":"demo@example.com","password":"demopass1"}' \
  | jq -r '.access_token')

# 3. Verify auth
curl -sS "${API_BASE}/auth/me" -H "Authorization: Bearer ${TOKEN}" | jq .

# 4. Run inference
curl -sS -X POST "${API_BASE}/inference" \
  -H "Authorization: Bearer ${TOKEN}" \
  -F "file=@painting.jpg" \
  -F "artist_name=Test Artist" \
  -F "artwork_name=Test Painting" | jq .

# 5. Check history
curl -sS "${API_BASE}/inferences?limit=5" -H "Authorization: Bearer ${TOKEN}" | jq .

# 6. RAG query
curl -sS -X POST "${API_BASE}/rag-query" \
  -H "Content-Type: application/json" \
  -d '{"query": "How are art forgeries detected?"}' | jq .
```

---

## Endpoint Summary

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | No | Health check (ALB target) |
| GET | `/` | No | API info |
| POST | `/auth/signup` | No | Create account |
| POST | `/auth/login` | No | Get JWT token |
| GET | `/auth/me` | Yes | Current user profile |
| PUT | `/auth/profile` | Yes | Update username/email |
| POST | `/auth/change-password` | Yes | Change password |
| POST | `/inference` | Yes | Submit image for forgery detection |
| GET | `/inferences/stats` | Yes | Inference count |
| GET | `/inferences` | Yes | List inferences (paginated) |
| GET | `/inferences/{id}` | Yes | Get single inference |
| DELETE | `/inferences/{id}` | Yes | Delete single inference |
| DELETE | `/inferences` | Yes | Delete all inferences |
| POST | `/rag-query` | No | Query Knowledge Base |
| POST | `/train` | No | Start training job |
| POST | `/evaluate` | No | Start evaluation job |
| POST | `/process_data` | No | Launch data processing task |

## Environment Variables

Backend environment variables relevant to the API (set automatically by Terraform/ECS in production):

| Variable | Description | Default |
|---|---|---|
| `DDB_USERS_TABLE` | DynamoDB users table name | Set by Terraform |
| `DDB_INFERENCES_TABLE` | DynamoDB inferences table name | Set by Terraform |
| `DDB_IMAGES_TABLE` | DynamoDB images table name | Set by Terraform |
| `DDB_PATCHES_TABLE` | DynamoDB patches table name | Set by Terraform |
| `DDB_RUNS_TABLE` | DynamoDB runs table name | Set by Terraform |
| `S3_IMAGES_RAW_BUCKET` | S3 bucket for raw uploads | Set by Terraform |
| `S3_IMAGES_PROCESSED_BUCKET` | S3 bucket for processed patches | Set by Terraform |
| `JWT_SECRET_KEY` | HS256 JWT signing secret. Injected from Secrets Manager in AWS; falls back to insecure default when `ENVIRONMENT=dev` | (required in prod) |
| `JWT_ACCESS_TOKEN_EXPIRE_SECONDS` | Token expiry | `3600` (1 hour) |
| `CORS_ALLOW_ORIGINS` | Comma-separated origins or `*` | `*` |
| `S3_INFERENCE_PRESIGN_EXPIRES` | Presigned URL TTL (seconds) | `86400` (24 hours) |
| `INFERENCE_TTL_DAYS` | DynamoDB TTL for inference records | `90` |
| `KNOWLEDGE_BASE_ID` | Bedrock Knowledge Base ID for RAG | Set by Terraform |
| `MODAL_API_KEY` | Modal credentials JSON (`{"token_id":"...","token_secret":"..."}`) | Set via Secrets Manager |

---

## Troubleshooting

- **401**: Missing/expired token or wrong `Authorization` header
- **400**: Invalid input (empty file, blank fields, file too large)
- **404**: Resource not found or belongs to another user
- **422**: Request body doesn't match expected schema
- **500**: Server error (check CloudWatch logs)
- **301/302**: Trailing slash mismatch — ensure `API_BASE` has no trailing slash, or use `curl -L`
- **403 from CloudFront**: You hit a path routed to S3 instead of the ALB — API paths must be configured in CloudFront behaviors
