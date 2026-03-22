# ArtGuard Disaster Recovery

## Prerequisites

- AWS CLI v2 configured with admin credentials (`aws sts get-caller-identity`)
- Terraform >= 1.10.0
- Docker Desktop running
- Python 3.9+
- Git LFS installed (`brew install git-lfs && git lfs install`)
- Modal account with Token ID and Token Secret

> **Git LFS note:** This repo uses Git LFS for large files (images, JSONL data). If the
> org's LFS budget is exceeded, `git lfs pull` will fail. This does **not** block the DR demo:
>
> - The RAG `.txt` files are already committed as real files — `deploy-all.sh` works without LFS.
> - Training images are already uploaded to S3 from a prior deploy. The DR demo preserves
>   them in S3, so no local image files are needed.
> - `deploy-all.sh` step 6 automatically detects LFS pointers and skips image upload gracefully.
>
> **For the DR demo, the TA does not need working Git LFS.** Just ensure prod has been
> deployed at least once (by the team) with real images before running `disaster-recovery.sh`.
>
> If a fresh deploy with training images is needed and LFS is unavailable, download the
> dataset from Google Drive: **[ArtGuard Training Data](https://drive.google.com/file/d/1-VELhmPI-4uAOl4bY9Bh33UktfWrS-Oo/view?usp=sharing)**
> Extract into the repo root so the `data/` folder contains the images, then run `deploy-all.sh`.
> Or run `./scripts/download-data.sh` to download and extract automatically.

---

## Quick Reference

| Goal | Command |
|------|---------|
| Deploy from scratch | `./scripts/deploy-all.sh prod` |
| Run DR demo (destroy + prove + recover) | `./scripts/disaster-recovery.sh prod` |
| Clean up after demo | `./scripts/destroy-all.sh prod` |
| Dev teardown (destroys everything) | `./scripts/destroy-all.sh dev` |
| Dev redeploy | `./scripts/deploy-all.sh dev` |

---

## How Disaster Recovery Works

ArtGuard's Disaster Recovery mechanism is script-driven using Terraform's `state rm` and `import` commands.

**Destroying (with data preservation):**
`destroy-all.sh --preserve-data` (ran in `./scripts/disaster-recovery.sh prod`) runs `terraform state rm` on all data-bearing resources
before destroying infrastructure. This detaches them from Terraform's knowledge while
leaving them untouched in AWS — they become **orphans**. All stateless infra (ECS, ALB,
VPC, CloudFront, OpenSearch, Bedrock KB) is then destroyed normally.

**Recovering:**
`recover-prod.sh` re-imports those orphaned resources into Terraform state with
`terraform import`, then runs `terraform apply` to recreate all stateless infrastructure
alongside the recovered data. It then rebuilds the Docker image, deploys to ECS, restores
secrets, and re-syncs the Bedrock Knowledge Base from the surviving S3 documents.

**Normal dev usage** (`destroy-all.sh dev` / `deploy-all.sh dev`) is unchanged —
it destroys and recreates everything including data.

---

## 1. What Survives Destruction

### Retained (data intact after `--preserve-data` destroy)

| Resource | AWS Name | How it survives |
|----------|----------|-----------------|
| DynamoDB: users | `artguard-users-{env}` | `terraform state rm` before destroy |
| DynamoDB: inference_records | `artguard-inference-records-{env}` | `terraform state rm` before destroy |
| DynamoDB: image_records | `artguard-image-records-{env}` | `terraform state rm` before destroy |
| DynamoDB: patch_records | `artguard-patch-records-{env}` | `terraform state rm` before destroy |
| DynamoDB: run_records | `artguard-run-records-{env}` | `terraform state rm` before destroy |
| DynamoDB: config_records | `artguard-config-records-{env}` | `terraform state rm` before destroy |
| S3: images-raw | `artguard-images-raw-{env}` | `terraform state rm` before destroy |
| S3: knowledge-base | `artguard-knowledge-base-{env}` | `terraform state rm` before destroy |

### Destroyed and recreated on recovery

| Resource | Impact |
|----------|--------|
| VPC, subnets, NAT gateways | Recreated by `terraform apply` |
| ALB, target groups, listeners | Recreated. DNS name changes (CloudFront absorbs this). |
| ECS cluster, service, task definition | Code redeployed from source |
| ECR repository | Recreated; Docker image rebuilt and pushed |
| CloudFront distribution | Recreated. URL changes (printed at end of recovery). |
| OpenSearch Serverless collection | Recreated; vector index rebuilt, vectors re-indexed from surviving S3 docs |
| Bedrock Knowledge Base + data source | Recreated; re-synced from surviving knowledge-base S3 bucket |
| IAM roles and policies | Recreated by `terraform apply` |
| Security groups | Recreated by `terraform apply` |
| CloudWatch log groups, dashboard, alarms | Recreated by `terraform apply` |
| Secrets Manager secrets | Recreated; Modal API key carried across by the script |
| S3: frontend | Recreated; frontend redeployed |
| S3: images-processed | Recreated empty; repopulated by data pipeline |

### What data is permanently lost

- **Nothing permanent** — all user records (DynamoDB), uploaded images (S3 images-raw),
  and RAG source documents (S3 knowledge-base) survive.
- **Vector embeddings** (OpenSearch) are rebuilt from source documents on recovery.
- **Processed images** (images-processed bucket) can be regenerated by re-running
  the data pipeline.

---

## 2. Disaster Recovery Demo (single command)

```bash
# Make sure prod is deployed first (team has already run it)
./scripts/deploy-all.sh prod

# Run the full DR demo
./scripts/disaster-recovery.sh prod
# Type: DEMO
```

The script runs three phases automatically:

1. **Phase 1 — Disaster Simulation**
   - Reads Modal API key from Secrets Manager (saves it for later)
   - Runs `destroy-all.sh --preserve-data` to tear down all stateless infra
   - DynamoDB tables and data S3 buckets survive as AWS orphans

2. **Phase 2 — Proof**
   - Queries AWS directly to confirm all 8 data resources (6 tables + 2 buckets)
     still exist with no Terraform owner
   - Prints SURVIVED/MISSING for each resource

3. **Phase 3 — Recovery**
   - Calls `recover-prod.sh` which:
     - Re-imports orphaned resources into Terraform state
     - Runs `terraform apply` to recreate all stateless infra (~15–20 min)
     - Restores the Modal API key to Secrets Manager
     - Builds and pushes a fresh Docker image to ECR
     - Deploys to ECS and waits for `/health` to respond
     - Triggers Bedrock KB ingestion from surviving S3 documents
     - Runs 10 post-recovery verification checks
   - Prints Frontend URL, Backend URL, and ALB URL

**After recovery, the full system is back to normal** — frontend, backend API, database,
image storage, and RAG all work exactly as before the disaster, with all user data intact.

### Full clean up after the demo (will destroy everything)

```bash
./scripts/destroy-all.sh prod
# Type: DESTROY
```

---

## 3. Manual Recovery (if the script fails)

### Step 1: Init Terraform

```bash
cd infra/terraform
terraform init -reconfigure -backend-config=backend-prod.hcl
```

### Step 2: Import surviving resources

```bash
# DynamoDB tables
for tbl in users inference-records image-records patch-records run-records config-records; do
  terraform import -var-file=prod.tfvars "aws_dynamodb_table.${tbl//-/_}" "artguard-${tbl}-prod"
done

# S3 buckets
terraform import -var-file=prod.tfvars aws_s3_bucket.images_raw artguard-images-raw-prod
terraform import -var-file=prod.tfvars aws_s3_bucket.knowledge_base artguard-knowledge-base-prod
```

### Step 3: Recreate stateless infra

```bash
terraform taint null_resource.opensearch_index  # Force index recreation
terraform apply -var-file=prod.tfvars -auto-approve
```

### Step 4: Restore secrets, build, and deploy

```bash
cd ../..
./scripts/setup-secrets.sh prod
./scripts/build-and-push-docker.sh prod
./scripts/deploy-ecs.sh prod
```

### Step 5: Trigger RAG ingestion

```bash
KB_ID=$(terraform -chdir=infra/terraform output -raw knowledge_base_id)
DS_ID=$(aws bedrock-agent list-data-sources --knowledge-base-id "$KB_ID" \
  --region ca-central-1 --query "dataSourceSummaries[0].dataSourceId" --output text)
aws bedrock-agent start-ingestion-job --knowledge-base-id "$KB_ID" \
  --data-source-id "$DS_ID" --region ca-central-1
```

---

## 4. Post-Recovery Verification

```bash
BACKEND_URL=$(terraform -chdir=infra/terraform output -json summary | jq -r '.backend_url')

# DynamoDB tables operational
for tbl in users inference-records image-records patch-records run-records config-records; do
  echo -n "artguard-${tbl}-prod: "
  aws dynamodb describe-table --table-name "artguard-${tbl}-prod" \
    --region ca-central-1 --query Table.TableStatus --output text
done

# S3 buckets accessible
aws s3api head-bucket --bucket artguard-images-raw-prod && echo "images-raw OK"
aws s3api head-bucket --bucket artguard-knowledge-base-prod && echo "knowledge-base OK"

# Backend healthy
curl -sf "$BACKEND_URL/health"

# RAG working
curl -sf -X POST "$BACKEND_URL/rag-query" \
  -H "Content-Type: application/json" \
  -d '{"query": "Vincent van Gogh painting style"}'
```

---

## 5. Terraform Configuration for DR

The following settings in `.tf` files enable scripts to tear down and rebuild cleanly.
In a real production environment, these would be set to their protective values
and the destroy scripts would need manual intervention.

| Setting | Current (DR-enabled) | Real Production |
|---------|---------------------|-----------------|
| `s3.tf: force_destroy` | `true` | `false` |
| `app.tf: force_delete` (ECR) | `true` | `false` |
| `app.tf: enable_deletion_protection` (ALB) | `false` | `true` |

See comments in `infra/terraform/prod.tfvars` for details.
