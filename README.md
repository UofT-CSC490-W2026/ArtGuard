# ArtGuard

![Test Coverage](coverage.svg)

Art forgery detection system using Swin Vision Transformers, with a FastAPI backend, React frontend, and AWS cloud infrastructure.

Based on: *"Art Authentication with Vision Transformers"* (Schaerf et al., 2023) — [arXiv:2307.03039](https://arxiv.org/abs/2307.03039)

See the [Documentation Index](#documentation-index) for detailed documentation on every part of the project.

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Access (Already Deployed)](#quick-access-already-deployed)
3. [Architecture](#architecture)
4. [Project Structure](#project-structure)
5. [Getting Started](#getting-started)
6. [Running the App](#running-the-app)
7. [Testing](#testing)
8. [Benchmarking](#benchmarking)
9. [Deployment](#deployment)
10. [Documentation Index](#documentation-index)
11. [Contributors](#contributors)
12. [License](#license)

---

## Overview

ArtGuard analyses artwork images to detect potential forgeries. Users upload an image with artist and artwork metadata, and the system:

1. Splits the image into patches using resolution-dependent grids
2. Runs each patch through a fine-tuned Swin Transformer model on [Modal](https://modal.com)
3. Aggregates patch-level predictions into a painting-level authenticity score
4. Generates a human-readable explanation via AWS Bedrock RAG (Retrieval-Augmented Generation)

### Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 18, TypeScript, Vite, Tailwind CSS, Shadcn/ui |
| **Backend API** | Python 3.11, FastAPI, Uvicorn |
| **Authentication** | JWT (HS256), bcrypt |
| **ML Model** | Swin-Tiny / Swin-Base (PyTorch), trained on Modal GPUs |
| **RAG** | AWS Bedrock (Claude 3 Haiku) + OpenSearch Serverless |
| **Database** | AWS DynamoDB (6 tables) |
| **Storage** | AWS S3 (4 buckets) |
| **Compute** | AWS ECS Fargate, Modal serverless GPUs |
| **CDN** | AWS CloudFront |
| **IaC** | Terraform |
| **CI/CD** | GitHub Actions (10 workflows) |
| **Monitoring** | CloudWatch (dashboards, alarms, structured JSON logs) |

---

## Quick Access (Already Deployed)

If the infrastructure is already running, you can access the system immediately:

```bash
# Get URLs from Terraform
cd infra/terraform && terraform output -json summary | jq .

# Or use the deployed URLs directly:
export API_BASE="https://YOUR_CLOUDFRONT_URL"

# Health check
curl -sS "${API_BASE}/health" | jq .

# Sign up
curl -sS -X POST "${API_BASE}/auth/signup" \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","email":"demo@example.com","password":"demopass1"}' | jq .

# Run inference on an artwork
TOKEN=$(curl -sS -X POST "${API_BASE}/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.com","password":"demopass1"}' | jq -r '.access_token')

curl -sS -X POST "${API_BASE}/inference" \
  -H "Authorization: Bearer ${TOKEN}" \
  -F "file=@path/to/painting.jpg" \
  -F "artist_name=Vincent van Gogh" \
  -F "artwork_name=Starry Night" | jq .
```

For the full list of endpoints see [docs/API_REFERENCE.md](docs/API_REFERENCE.md). For service management (scale up/down, logs, status) see [DEPLOYMENT.md](DEPLOYMENT.md).

---

## Architecture

```
                    CloudFront (CDN)
                   /              \
        S3 (frontend)      ALB (API)
                            |
                     ECS Fargate
                     (FastAPI app)
                    /      |       \
              DynamoDB   S3 raw   Modal (GPU)
              (6 tables) images   Swin model
                    \              /
                     Bedrock RAG
                     (Knowledge Base)
```

For detailed architecture diagrams see [infra/INFRA_README.md](infra/INFRA_README.md).

---

## Project Structure

```
ArtGuard/
├── src/apps/
│   ├── backend/               # FastAPI REST API (runs on ECS Fargate)
│   │   ├── main.py            #   App entry point, middleware, health check
│   │   ├── config.py          #   AWS clients, enums, constants
│   │   ├── validation.py      #   Shared data contracts and field limits
│   │   ├── prompts.py         #   RAG/LLM prompt templates (plug-and-play)
│   │   ├── logging_config.py  #   JSON structured logging, CloudWatch EMF metrics
│   │   ├── routes/            #   Route handlers (auth, inference, train, rag, process_data)
│   │   ├── services/          #   Business logic (inference pipeline, users, S3 presign)
│   │   ├── security/          #   JWT tokens, bcrypt password hashing
│   │   └── deps/              #   FastAPI dependencies (auth middleware)
│   ├── data_pipeline/         # ETL and image preprocessing
│   │   ├── driver.py          #   ECS Fargate processing task entry point
│   │   ├── preprocess.py      #   Image → 224x224 patch pipeline
│   │   ├── schemas.py         #   DynamoDB dataclasses with validation
│   │   ├── split.py           #   Deterministic stratified k-fold splitting
│   │   ├── met_pipeline.py    #   Metropolitan Museum data ingestion
│   │   ├── wikidata_pipeline.py # Wikidata SPARQL ingestion
│   │   └── output/            #   Pipeline output (.jsonl sources, .txt for RAG)
│   ├── train/                 # Modal GPU training and inference
│   │   ├── model.py           #   Swin Transformer (Tiny/Base) with He-normal init
│   │   ├── train.py           #   Training loop with early stopping + checkpointing
│   │   ├── evaluate.py        #   Patch- and painting-level evaluation metrics
│   │   ├── inference.py       #   Modal inference endpoint (called by backend)
│   │   └── dataset.py         #   S3-streaming PyTorch Dataset with DynamoDB labels
│   └── frontend/              # React + TypeScript + Vite
│       └── src/app/
│           ├── pages/         #   9 page components (Upload, Results, History, etc.)
│           ├── api/           #   Typed API client (auth, inference, inferences)
│           ├── components/    #   UI components (Shadcn/Radix)
│           └── contexts/      #   React contexts (auth state)
├── infra/
│   ├── terraform/             # Infrastructure as Code (15 .tf files)
│   │   ├── app.tf            #   ECS, ALB, ECR, CloudWatch logs
│   │   ├── database.tf       #   6 DynamoDB tables with GSIs
│   │   ├── s3.tf             #   4 S3 buckets with lifecycle policies
│   │   ├── bedrock.tf        #   OpenSearch Serverless + Bedrock Knowledge Base
│   │   ├── networking.tf     #   VPC, subnets, NAT gateways, VPC endpoints
│   │   ├── {dev,prod}.tfvars #   Environment-specific configurations
│   │   └── ...               #   IAM, CloudFront, Route53, monitoring, secrets
│   └── disaster_recovery/     # DR video demo and secret recovery script
├── scripts/                   # Deployment and operations (18 scripts)
│   ├── _colors.sh            #   Shared color output helpers (sourced by all scripts)
│   ├── deploy-all.sh         #   Full deployment (infra + secrets + Docker + ECS + RAG)
│   ├── destroy-all.sh        #   Teardown (full wipe or --preserve-data for DR)
│   ├── disaster-recovery.sh  #   One-command DR demo (destroy → prove → recover)
│   ├── recover-prod.sh       #   Recovery script (import orphans → rebuild → verify)
│   └── ...                   #   bootstrap, build-docker, deploy-ecs, upload-rag, etc.
├── tests/                     # pytest test suite (395 tests, 100% coverage)
│   ├── conftest.py           #   Shared fixtures (mocked AWS, FastAPI test client)
│   ├── test_routes_*.py      #   API route tests (auth, inference, rag, train, etc.)
│   ├── test_model.py         #   Swin Transformer model tests (CPU, no pretrained weights)
│   ├── test_train.py         #   Training loop tests (mocked dataset, early stopping)
│   ├── locustfile.py         #   Load testing with Locust
│   └── ...                   #   28 test files covering all src/ modules
├── data/                      # Training dataset
│   ├── metadata.csv          #   Image metadata (labels, splits, creators)
│   ├── train/                #   Training images (class_0=forgery, class_1=authentic)
│   ├── test/                 #   Test images
│   └── val/                  #   Validation images
├── docs/                      # Additional documentation
│   ├── API_REFERENCE.md    #   API reference with curl examples for all endpoints
│   └── architecture_diagram.xml # Architecture diagram source
├── .github/workflows/         # CI/CD pipelines (10 GitHub Actions workflows)
├── DISASTER_RECOVERY.md       # Disaster recovery guide and demo instructions
├── DEPLOYMENT.md              # Step-by-step deployment guide
├── Dockerfile                 # Backend container image (Python 3.11 + FastAPI)
└── requirements.txt           # Python dependencies
```

---

## Getting Started

### Prerequisites

| Tool | Required for | Install |
|------|-------------|---------|
| Python 3.11+ | Backend, tests, data pipeline | `brew install python@3.11` |
| Node.js 18+ | Frontend | `brew install node` |
| Docker Desktop | Containerized deployment | [docker.com](https://docker.com/products/docker-desktop) |
| AWS CLI | Cloud deployment only | `brew install awscli` |
| Terraform 1.10+ | Infrastructure provisioning only | `brew install terraform` |

### Install Dependencies

```bash
# Clone the repository
git clone https://github.com/UofT-CSC490-W2026/ArtGuard.git
cd ArtGuard

# Backend (Python)
pip install -r requirements.txt

# Frontend (Node)
cd src/apps/frontend && npm ci && cd ../../..
```

---

## Running the Code

### Run Tests (no AWS/Docker required)

The fastest way to verify the codebase works. Only requires Python 3.11+ and `pip install -r requirements.txt`.

```bash
# Run full test suite (395 tests, 100% coverage)
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=src --cov-report=term-missing

# Run a specific test file
pytest tests/test_routes_auth.py -v

# Run load tests only
pytest tests/test_load.py -v
```

All AWS services (S3, DynamoDB, STS) are mocked via [moto](https://github.com/getmoto/moto) — no AWS credentials needed to run tests.

### Run Backend Locally

Requires Python 3.11+. The backend starts in dev mode with an insecure JWT secret and no AWS connections (inference/RAG features will return errors without AWS, but auth and health check work):

```bash
export ENVIRONMENT=dev
uvicorn src.apps.backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Then test:
```bash
curl http://localhost:8000/health          # {"status": "ok"}
curl -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"username":"test","email":"test@test.com","password":"password1"}'
```

### Run Frontend Locally

Requires Node.js 18+. Connects to the backend API:

```bash
cd src/apps/frontend
export VITE_API_URL=http://localhost:8000
npm run dev
# Opens at http://localhost:5173
```

### Run via Docker

```bash
docker build -t artguard-backend .
docker run -p 8000:8000 -e ENVIRONMENT=dev artguard-backend
# Health check: curl http://localhost:8000/health
```

### Run Data Pipelines (no AWS required)

Generate RAG knowledge base documents from public APIs:

```bash
# Metropolitan Museum data → JSONL
python -m src.apps.data_pipeline.met_pipeline

# Wikidata artist data → JSONL
python -m src.apps.data_pipeline.wikidata_pipeline

# Convert JSONL to chunked TXT files for Bedrock
python scripts/convert-jsonl-to-txt.py
```

Output is written to `src/apps/data_pipeline/output/`.

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=src --cov-report=term-missing

# Run only load tests
pytest tests/test_load.py -m load -v

# Run Locust load tests against a live API
locust -f tests/locustfile.py --host http://localhost:8000
```

**Test suite:** 395 tests, 100% code coverage. See [tests/README.md](tests/README.md) for full testing methodology.

| Category | Files | Tests |
|----------|-------|-------|
| Unit tests | config, security, validation, schemas, split, preprocess | 100+ |
| Service tests | inference_service, users_service, s3_presign | 30+ |
| Route integration | auth, inference, inferences, train, rag, process_data | 60+ |
| AWS integration | S3 upload/download, DynamoDB CRUD (via moto mocks) | 40+ |
| Load tests | Concurrency, latency, throughput, mixed workload | 14 |
| Edge cases | Error branches, bad data, missing config | 24 |

---

## Benchmarking

For full methodology, data split strategy, and reproducibility instructions, see [BENCHMARKS.md](BENCHMARKS.md).

### Quick Reproduce

```bash
# Train + evaluate both Swin-Tiny and Swin-Base on Modal GPUs
./scripts/run-benchmarks.sh

# Or a single variant
./scripts/run-benchmarks.sh tiny

# Evaluate only (using existing checkpoint)
modal run src/apps/train/evaluate.py --variant tiny --checkpoint /checkpoints/tiny/best.pt --output-dir benchmarks/
```

Results are saved as JSON to `benchmarks/` with patch-level and painting-level metrics (accuracy, precision, recall, F1, confusion matrix) broken down by sublabel.

### Reproducibility

All data splits are deterministic via SHA-256 hashing with fixed seeds (`outer_split_seed=17`, `inner_split_seed=99`). The same dataset with the same seeds always produces identical train/val/test assignments regardless of item ordering or platform. Training hyperparameters follow the paper: Adam optimizer, lr=1e-4, batch_size=32, BCEWithLogitsLoss with imitation weight wim=10.

---

## Deployment

For the complete guide including data upload, model training, RAG setup, and troubleshooting, see [DEPLOYMENT.md](DEPLOYMENT.md).

### Full Deployment From Scratch (all-in-one)

```bash
# Deploys everything: infra, secrets, Docker, ECS, frontend, RAG data
# Takes ~30-45 minutes. You will be prompted for your Modal API key.
./scripts/deploy-all.sh dev
```

### Step-by-Step Deployment

```bash
# 1. Create all AWS infrastructure (~15-20 min)
./scripts/bootstrap.sh dev

# 2. Store Modal API key in Secrets Manager
./scripts/setup-secrets.sh dev

# 3. Build and push Docker image to ECR (~5-10 min)
./scripts/build-and-push-docker.sh dev

# 4. Deploy backend to ECS Fargate (~2-3 min)
./scripts/deploy-ecs.sh dev

# 5. Deploy frontend to S3 + CloudFront
export VITE_API_URL=$(terraform -chdir=infra/terraform output -raw cloudfront_distribution_url)
./scripts/deploy-frontend.sh dev

# 6. Upload RAG knowledge base documents (~10-20 min)
./scripts/upload-rag-data.sh

# 7. Upload training data (optional, if training locally)
./scripts/update-data.sh --data-dir ./data --metadata ./data/metadata.csv

# 8. Train the model on Modal GPUs (if not already trained)
./scripts/run-benchmarks.sh tiny
```

### Common Operations

```bash
./scripts/ecs-control.sh status dev     # Check service health
./scripts/ecs-control.sh logs dev       # View recent logs
./scripts/ecs-control.sh scale dev 0    # Pause (save costs)
./scripts/ecs-control.sh scale dev 1    # Resume
./scripts/destroy-all.sh dev            # Tear down everything
```

---

## Documentation Index

### Setup and Operations

| Document | Description |
|----------|-------------|
| [DEPLOYMENT.md](DEPLOYMENT.md) | Step-by-step deployment guide (prerequisites, first-time setup, ongoing workflow) |
| [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md) | Disaster recovery guide, demo instructions, and manual recovery steps |
| [BENCHMARKS.md](BENCHMARKS.md) | Model evaluation methodology, training config, reproducibility instructions |
| [tests/README.md](tests/README.md) | Testing methodology, what is tested, coverage breakdown, CI integration |
| [scripts/README.md](scripts/README.md) | All deployment and operations scripts with usage examples |

### Architecture and Infrastructure

| Document | Description |
|----------|-------------|
| [infra/INFRA_README.md](infra/INFRA_README.md) | Infrastructure overview, architecture decisions, security, monitoring, costs |
| [infra/COMPONENT_DESCRIPTION.md](infra/COMPONENT_DESCRIPTION.md) | Detailed breakdown of every AWS component (ECS, ALB, DynamoDB, S3, etc.) |

### Data and API

| Document | Description |
|----------|-------------|
| [DATA.md](DATA.md) | DynamoDB schemas (6 tables), S3 storage structure, data workflows, query patterns |
| [docs/API_REFERENCE.md](docs/API_REFERENCE.md) | API reference with curl examples for all 17 endpoints |
| [assignments/a5/RAG_DEPLOYMENT_DEBUG_LOG.md](assignments/a5/RAG_DEPLOYMENT_DEBUG_LOG.md) | RAG pipeline debugging log and fixes |

### Frontend

| Document | Description |
|----------|-------------|
| [src/apps/frontend/README.md](src/apps/frontend/README.md) | Frontend setup and development |
| [src/apps/frontend/ATTRIBUTIONS.md](src/apps/frontend/ATTRIBUTIONS.md) | Third-party component attributions |

---

## Contributors

ArtGuard Development Team — Department of Computer Science, University of Toronto (CSC490 W2026).

---

## License

This project is licensed under the terms specified in [LICENSE](LICENSE).
