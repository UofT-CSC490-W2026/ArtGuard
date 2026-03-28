# Testing

## Overview

ArtGuard uses **pytest** with **moto** (AWS mocks), **httpx** (async API testing), and **Locust** (load testing) to achieve **600+ tests at 100% code coverage** across all Python modules in `src/` — including the ML training pipeline.

Modal GPU modules (training, evaluation, inference, dataset, model) are tested on CPU with mocked datasets, checkpoints, and AWS calls. No PyTorch + CUDA is required in CI. The test files (`test_model.py`, `test_train.py`, `test_evaluate.py`, `test_dataset.py`, `test_inference_modal.py`) cover all logic including error handling branches, early stopping, checkpoint saving, and metric computation.

All tests run in CI via the `test-coverage.yml` GitHub Actions workflow on every push to `main` and every pull request (with `-m "not slow"`; there are currently no tests marked `slow`). Locally, `test_evaluate.py` may skip one collection item if `sklearn` is not installed; CI installs full `requirements.txt`.

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
├── test_routes_auth_extended.py # Extra auth route branches and edge cases
├── test_routes_inference.py # POST /inference (upload, validate, predict)
├── test_routes_inference_extended.py # Extra inference route coverage
├── test_routes_inferences.py# Inference history (list, get, delete, stats)
├── test_routes_inferences_extended.py # Extra inferences route coverage
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
├── test_main_extended.py    # Additional app wiring and startup edge cases
├── test_logging_config.py   # Structured JSON logging, EMF metrics, middleware
├── test_s3_presign.py       # S3 URI parsing, presigned URL generation
├── test_preprocess.py     # Image → 224x224 patch pipeline
├── test_driver.py           # ECS Fargate processing task (unit)
├── test_driver_main.py      # ECS Fargate processing task (integration)
├── test_pipelines.py        # MET Museum + Wikidata data ingestion
├── test_rag_pipeline.py     # RAG formatting, KB queries, response generation (mocked)
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
- **MET Museum pipeline**: CSV download and filtering, JSONL output format, MAX_RECORDS limit, progress logging at 10,000 records
- **Wikidata pipeline**: SPARQL response parsing, multi-value field collection (movements, genres, occupations, influences, notable works), `main()` orchestrator, empty results handling
- **ECS Fargate driver**: end-to-end processing, empty bucket handling, pre-existing image record updates, error recovery (continues to next image on failure, marks run as `completed_with_errors`)

### ML Module Tests
These test the Modal GPU code on CPU without pretrained weights:
- **Model** (`test_model.py`): Swin Transformer construction (tiny/base variants), forward pass output shapes, He-normal weight initialization, dropout configuration, invalid variant rejection, predict() probability range, configure_criterion/optimizer
- **Training** (`test_train.py`): Full training loop with mocked dataset, checkpoint saving verification, early stopping trigger after patience exhaustion, config defaults validation
- **Evaluation** (`test_evaluate.py`): accuracy/precision/recall/F1 computation, confusion matrix structure, per-sublabel metric breakdowns, empty input edge cases, checkpoint-not-found error, empty test dataset error
- **Dataset** (`test_dataset.py`): S3 path parsing, patch streaming from mocked S3, DynamoDB scan pagination, GSI fallback to scan, split filter propagation, sublabel counting, records-without-label skipping
- **Inference** (`test_inference_modal.py`): Patch prediction pipeline, empty patch list, S3 download failures, malformed URIs

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
600+ tests | 100% line coverage | 1781 statements, 0 missed
```

Coverage is measured across all `src/` Python modules **except** the 5 ML modules (`train.py`, `evaluate.py`, `inference.py`, `dataset.py`, `model.py`) which are omitted in `.coveragerc` because they require PyTorch (not in `requirements.txt` — it's installed inside Modal containers). These modules have dedicated test files that achieve 100% coverage locally and are auto-skipped in CI via `pytest.importorskip("torch")`. Modal-specific decorators (`@app.function`, `@app.local_entrypoint`, `.spawn()`, `.remote()`) are also excluded since they require the Modal runtime.

### Coverage by Module

| Module | Coverage |
|--------|----------|
| Backend config, auth, security, validation, prompts | 100% |
| All route handlers (auth, inference, inferences, train, rag, process_data) | 100% |
| Inference service, users service, S3 presign | 100% |
| Data pipeline (preprocess, schemas, split, driver, met, wikidata) | 100% |
| Structured logging and middleware | 100% |
| ML modules (model, dataset, train, evaluate, inference) | 100% |
| **Total (1781 statements)** | **100%** |

### How We Reached 100%

The last few percent came from targeted tests that exercise hard-to-reach error branches:
- **`test_coverage_gaps.py`**: User record vanishing between DynamoDB operations, generic inference exceptions, presigned URL failures, `process_single_image` raising mid-batch, MET pipeline progress logging at 10,000 records
- **`test_pipelines.py`**: MET CSV download failures (`URLError`), Wikidata query exceptions with `continue`, `None` result handling
- **`test_driver.py`**: S3 `download()` raising `IOError`, `move_to_processed()` copy/delete failures
- **`test_preprocess.py`**: S3 `_upload_patch()` raising `IOError` on `put_object` failure
- **`test_evaluate.py`**: Checkpoint not found (`FileNotFoundError`), empty test dataset (`RuntimeError`)
- **`test_dataset.py`**: Split filter propagation (`FilterExpression` passed to DynamoDB scan)

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
