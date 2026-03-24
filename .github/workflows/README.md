# CI/CD Workflows

ArtGuard uses 9 GitHub Actions workflows for automated testing, deployment, and infrastructure management. Workflows are split into **automatic** (triggered by code changes) and **manual** (triggered from the GitHub Actions UI).

---

## Automatic Workflows

These run automatically when code is pushed or a pull request is opened. No manual intervention needed.

### Build and Deploy Backend (`app-docker.yml`)

**Trigger:** Push to `main` when files in `src/apps/backend/`, `src/apps/data_pipeline/`, `Dockerfile`, or `requirements.txt` change.

**What it does:**
1. Builds the Docker image with `./scripts/build-and-push-docker.sh`
2. Pushes to ECR with a versioned tag (`vYYYY.MM.DD-SHA-BUILD`) and `:latest`
3. Forces a rolling ECS deployment with `./scripts/deploy-ecs.sh`

**Result:** New backend code is live in ~15 minutes after push.

---

### Deploy Frontend (`frontend-deploy.yml`)

**Trigger:** Push to `main` when files in `src/apps/frontend/` change.

**What it does:**
1. Installs Node.js dependencies (`npm ci`)
2. Builds the Vite production bundle (`npm run build`)
3. Syncs static assets to S3 with long cache headers (1 year for hashed JS/CSS)
4. Syncs HTML/JSON with short cache (must-revalidate)
5. Invalidates CloudFront cache

**Result:** Frontend updates are live in ~5-10 minutes.

---

### Terraform Deploy (`terraform-deploy.yml`)

**Trigger:** Push to `main` when files in `infra/terraform/` change.

**What it does:**
1. Initializes Terraform with the environment backend config
2. Runs `terraform apply -auto-approve` with the appropriate `.tfvars`

**Result:** Infrastructure changes (new resources, config updates) are applied automatically.

---

### Terraform PR Check (`terraform-pr.yml`)

**Trigger:** Pull request targeting `main` when files in `infra/terraform/` change.

**What it does:**
1. Runs `terraform fmt -check` (formatting validation)
2. Runs `terraform validate` (syntax/config validation)
3. Runs `terraform plan` (preview of changes, no apply)

**Result:** PR reviewers can see exactly what infrastructure changes would be made before merging.

---

### Test Coverage (`test-coverage.yml`)

**Trigger:** Push to `main` and all pull requests.

**What it does:**
1. Installs Python 3.11 and all dependencies
2. Runs the full test suite with `pytest --cov=src --cov-report=xml`
3. On `main` pushes: generates `coverage.svg` badge and commits it to the repo
4. On PRs: posts a coverage summary comment via `orgoro/coverage`
5. Uploads HTML coverage report as a downloadable artifact

**Result:** Coverage badge on README stays up to date. PR reviewers see coverage impact of their changes.

---

## Manual Workflows

These are triggered from the GitHub Actions UI (**Actions tab → select workflow → Run workflow**). Used for one-time operations, emergency actions, and service management.

### Terraform Bootstrap (`terraform-bootstrap.yml`)

**When to use:** First-time infrastructure setup for a new environment.

**What it does:**
1. Creates the S3 state bucket and DynamoDB lock table
2. Initializes Terraform backend
3. Runs `./scripts/bootstrap.sh` which creates all ~60 AWS resources

**Input:** Environment name (dev/prod), confirmation text "BOOTSTRAP".

---

### ECS Service Control (`ecs-manage.yml`)

**When to use:** Manual ECS operations without SSH or CLI access.

**What it does:** Runs `./scripts/ecs-control.sh` with the selected action.

**Inputs:**
- **Action:** `deploy` (force redeploy), `scale` (change task count), `status` (health check), `logs` (recent CloudWatch logs)
- **Environment:** dev or prod
- **Count:** desired task count (for scale action; use 0 to pause, 1 to resume)

---

### Terraform Destroy (`terraform-destroy.yml`)

**When to use:** Tear down all infrastructure (emergency cost control or environment cleanup).

**What it does:**
1. Requires typing "DESTROY" as confirmation
2. Runs `./scripts/destroy-all.sh` which handles secret cleanup, S3 force-destroy, and `terraform destroy`

**Input:** Environment name, confirmation text "DESTROY".

---

### Disaster Recovery - Secret Injection (`secret.yml`)

**When to use:** After disaster recovery when secrets need to be re-injected into a fresh Secrets Manager.

**What it does:** Writes the Modal API key from the GitHub Secret `MODAL_API_KEY` into AWS Secrets Manager using `aws secretsmanager put-secret-value`.

**Input:** Environment name.

---

## Required GitHub Secrets

Configure these in **Settings → Secrets and variables → Actions**:

| Secret | Required by | Purpose |
|--------|------------|---------|
| `AWS_ACCESS_KEY_ID` | All deployment workflows | AWS authentication |
| `AWS_SECRET_ACCESS_KEY` | All deployment workflows | AWS authentication |
| `MODAL_API_KEY` | `secret.yml` | Modal credentials for DR secret recovery |
| `VITE_API_URL` | `frontend-deploy.yml` | API base URL baked into the frontend JS bundle (e.g. `https://dxxxx.cloudfront.net`) |

---

## Workflow Trigger Summary

| Workflow | Push to main | Pull Request | Manual | Scripts Used |
|----------|:---:|:---:|:---:|---|
| `app-docker.yml` | Backend changes | - | Yes | `build-and-push-docker.sh`, `deploy-ecs.sh` |
| `frontend-deploy.yml` | Frontend changes | - | Yes | inline npm + aws s3 sync |
| `terraform-deploy.yml` | Terraform changes | - | Yes | `terraform-deploy.sh` |
| `terraform-pr.yml` | - | Terraform changes | - | inline terraform validate + tflint |
| `test-coverage.yml` | Yes | Yes | - | pytest |
| `terraform-bootstrap.yml` | - | - | Yes | `bootstrap.sh` |
| `ecs-manage.yml` | - | - | Yes | `ecs-control.sh` |
| `terraform-destroy.yml` | - | - | Yes | `destroy-all.sh` |
| `secret.yml` | - | - | Yes | inline aws secretsmanager |
