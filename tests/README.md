# Testing

## Overview

ArtGuard uses **pytest** with **moto** (AWS mocks), **httpx** (async API testing), and **Locust** (load testing) to achieve **395 tests at 100% code coverage** across the backend, data pipeline, and structured logging modules.

Modal GPU modules (training, evaluation, inference, dataset, model) are excluded from coverage measurement since they require PyTorch + CUDA which are not installed in the CI environment. These modules have their own dedicated test files (`test_model.py`, `test_train.py`, `test_evaluate.py`, `test_dataset.py`, `test_inference_modal.py`) that test the logic on CPU with mocked data. Every other line of Python in `src/` is covered.

All tests run in CI via the `test-coverage.yml` GitHub Actions workflow on every push to `main` and every pull request.

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=term-missing

# Run a specific file
pytest tests/test_routes_auth.py -v
```

---

## Test Architecture

```
tests/
├── conftest.py              # Shared fixtures (mocked AWS, test client, factories)
├── test_routes_auth.py      # Auth endpoints (signup, login, profile, password)
├── test_routes_inference.py # POST /inference (upload, validate, predict)
├── test_routes_inferences.py# Inference history (list, get, delete, stats)
├── test_routes_rag.py       # POST /rag-query (Bedrock Knowledge Base)
├── test_routes_train.py     # POST /train and /evaluate (Modal dispatch)
├── test_routes_process_data.py # POST /process_data (ECS task launch)
├── test_inference_service.py# Inference pipeline business logic
├── test_users_service.py    # User CRUD (DynamoDB)
├── test_security.py         # JWT tokens, bcrypt passwords, auth dependency
├── test_config.py           # Env vars, enums, pagination helpers
├── test_validation.py       # Data contracts, sanitization, field limits
├── test_schemas.py          # DynamoDB dataclass __post_init__ validation
├── test_main.py             # App setup, CORS, health endpoint, router registration
├── test_logging_config.py   # Structured JSON logging, EMF metrics, middleware
├── test_s3_presign.py       # S3 URI parsing, presigned URL generation
├── test_split.py            # Deterministic stratified k-fold splitting
├── test_preprocess.py       # Image → 224x224 patch pipeline
├── test_driver.py           # ECS Fargate processing task (unit)
├── test_driver_main.py      # ECS Fargate processing task (integration)
├── test_pipelines.py        # MET Museum + Wikidata data ingestion
├── test_coverage_gaps.py    # Targeted tests for hard-to-reach error branches
├── test_model.py            # Swin Transformer model (CPU, no pretrained weights)
├── test_train.py            # Training loop (mocked dataset, early stopping)
├── test_evaluate.py         # Evaluation metrics (accuracy, F1, confusion matrix)
├── test_inference_modal.py  # Modal inference endpoint (patch prediction)
├── test_dataset.py          # S3/DynamoDB patch streaming PyTorch Dataset
├── test_load.py             # Concurrency and throughput stress tests
├── locustfile.py            # Production load testing (4 user classes)
└── test_rag_deployment.py   # RAG infrastructure verification (live infra)
```

---

## What We Test

### API Route Integration Tests
Full HTTP request/response testing through the FastAPI middleware stack (CORS, JWT auth, request logging) using httpx's `AsyncClient` with `ASGITransport`. Every route is tested for:
- **Success paths** with valid input and mocked downstream services (Modal, Bedrock, S3)
- **Authentication** — 401 for missing, expired, and invalid JWT tokens
- **Input validation** — 400/422 for empty files, oversized uploads (>20 MB), blank fields, invalid types, whitespace-only strings
- **Error handling** — 500 with user-friendly messages when Modal/Bedrock/S3/DynamoDB fail; no stack traces leak
- **User isolation** — users cannot list, view, or delete another user's inference records
- **Security edge cases** — XSS/SQL injection strings in metadata fields are stored as plain text, not interpreted

Covers: `/auth/*`, `/inference`, `/inferences/*`, `/train`, `/evaluate`, `/rag-query`, `/process_data`, `/health`

### Service Layer Tests
Test business logic independently from HTTP routing:
- S3 objects are uploaded with correct content, content-type, key structure, and custom prefix support
- DynamoDB records contain **all** expected fields with correct types and defaults (not just primary keys)
- Inference records initialize with `prediction=-1` (pending), `score=0.0`, `status=processing`, and a future TTL
- Presigned URLs are generated from `s3://` URIs; failures return `None` instead of crashing
- Negative image dimensions are clamped to zero
- RAG explanation queries handle missing Knowledge Base config, Bedrock failures, and successful responses

### Security Tests
- Password hashing with bcrypt (correct verification, wrong password rejection, empty hash edge case)
- JWT token creation, decoding, expiration, and signature validation
- Auth dependency (valid tokens, expired tokens, malformed tokens, missing Authorization header)
- Edge cases: unicode passwords, tampered token payloads

### Data Contract and Validation Tests
- Field length limits and truncation behavior for all string fields
- Score clamping to 0.0–1.0 range
- Prediction validation (only -1, 0, 1 accepted)
- Filename sanitization: path traversal (`../../../etc/passwd`), null byte injection, Unicode characters
- Schema `__post_init__` normalization: negative dimensions clamped, invalid labels/sublabels set to None, invalid splits default to `"unassigned"`, float dimensions converted to int, negative fold_id clamped to 0
- UUID validity (not just length checks), distinct IDs on separate instantiation, mutable default isolation

### Data Pipeline Tests
- **Image patching**: grid computation for various resolutions, RGBA-to-RGB conversion, S3 upload verification, patch metadata structure
- **Deterministic splitting**: SHA-256 hash stability across runs, stratification preserves sublabel ratios, k-fold reproducibility
- **MET Museum pipeline**: CSV download and filtering, JSONL output format, MAX_RECORDS limit, progress logging at 10,000 records
- **Wikidata pipeline**: SPARQL response parsing, multi-value field collection (movements, genres, occupations, influences, notable works), `main()` orchestrator, empty results handling
- **ECS Fargate driver**: end-to-end processing, empty bucket handling, pre-existing image record updates, error recovery (continues to next image on failure, marks run as `completed_with_errors`)

### ML Module Tests
These test the Modal GPU code on CPU without pretrained weights:
- Swin Transformer: model construction (tiny/base variants), forward pass output shapes, He-normal weight initialization
- Training loop: checkpoint saving, early stopping trigger, config propagation
- Evaluation: accuracy/precision/recall/F1 computation, confusion matrix, per-sublabel metric breakdowns, empty input edge cases

### Load and Stress Tests
- 100 concurrent health check requests (all must return 200)
- 50 concurrent authenticated profile reads
- 30 concurrent user signups
- Burst invalid login attempts (all return 401, never 500)
- Mixed read/write workloads under concurrency
- Throughput benchmark confirming >100 requests/second

### Production Load Testing (Locust)
`locustfile.py` defines 4 weighted user classes for testing against a live deployment:
- **ArtGuardReadUser** (weight=3): health checks, profile reads, inference history pagination
- **ArtGuardWriteUser** (weight=1): signups, profile updates
- **ArtGuardInferenceUser** (weight=1): image upload + full inference pipeline
- **ArtGuardUnauthenticatedUser** (weight=1): public endpoints, rejected auth attempts

```bash
# Run Locust against a live API
locust -f tests/locustfile.py --host https://your-api-url
```

---

## How AWS is Mocked

We use [moto](https://github.com/getmoto/moto) to create real in-memory AWS resources:
- **S3**: Two buckets (`test-raw-bucket`, `test-processed-bucket`) with real `put_object`/`get_object`/`generate_presigned_url` calls
- **DynamoDB**: Five tables with Global Secondary Indexes matching the production Terraform schema
- **STS**: Mocked `get_caller_identity` for ECS task launching

Tests actually create DynamoDB items, query GSIs, upload files to S3, and generate presigned URLs — not just mocked return values. If the production schema changes, the tests break immediately because the moto tables mirror the Terraform definitions.

The `conftest.py` fixtures also provide:
- `client` — httpx `AsyncClient` wired to the FastAPI app with mocked AWS
- `auth_headers` — valid JWT Authorization header for `test-user-1`
- `create_test_user()` — factory that inserts a user with hashed password into moto DynamoDB
- `sample_image_bytes` — minimal valid JPEG for upload tests

---

## Coverage

```
395 tests | 100% line coverage
```

Coverage is measured across all `src/` Python modules **except** the 5 Modal GPU modules (`train.py`, `evaluate.py`, `inference.py`, `dataset.py`, `model.py`) which are omitted in `.coveragerc` because they require PyTorch + CUDA (not installed in CI). These modules have dedicated test files that verify their logic on CPU with mocked datasets and checkpoints.

### Coverage by Module

| Module | Coverage |
|--------|----------|
| Backend config, auth, security, validation, prompts | 100% |
| All route handlers (auth, inference, inferences, train, rag, process_data) | 100% |
| Inference service, users service, S3 presign | 100% |
| Data pipeline (preprocess, schemas, split, driver, met, wikidata) | 100% |
| Structured logging and middleware | 100% |
| **Total** | **100%** |

### How We Reached 100%

The last few percent came from targeted tests in `test_coverage_gaps.py` that exercise hard-to-reach error branches:
- User record vanishing between DynamoDB `update_item` and subsequent `get_item` (concurrent delete / eventual consistency)
- Generic exceptions during the inference pipeline prep phase (not just `EnvironmentError`)
- Presigned URL failures when listing inference history (one bad image doesn't crash the list)
- `process_single_image` raising mid-batch in the data pipeline driver (error counter increments, loop continues)
- MET pipeline progress logging triggered at 10,000 records
- Wikidata pipeline `main()` orchestrator with both successful and empty query results

---

## CI/CD Integration

The `test-coverage.yml` GitHub Actions workflow:
1. Runs the full test suite on every push to `main` and every pull request
2. Generates a coverage badge committed to the repo
3. Posts a coverage summary comment on pull requests
4. Uploads the HTML coverage report as a downloadable GitHub Actions artifact

```yaml
# .github/workflows/test-coverage.yml
pytest tests/ --cov=src --cov-report=xml --cov-report=html
```
