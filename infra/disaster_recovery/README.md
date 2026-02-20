# Disaster Recovery Scripts

This directory contains scripts for disaster recovery demonstrations and operations.

## Scripts

### `backup-state.sh`

Backs up Terraform state files from S3 to local storage.

**Usage:**
```bash
./backup-state.sh [dev|prod]
```

**What it does:**
- Downloads state file from S3
- Saves to `./state-backups/terraform.tfstate.<env>.<timestamp>.json`
- Creates a `latest` copy for easy access

**Example:**
```bash
./backup-state.sh dev
# Creates: state-backups/terraform.tfstate.dev.20260218_143022.json
# And:     state-backups/terraform.tfstate.dev.latest.json
```

---

### `disaster-recovery-demo.sh`

Complete disaster recovery demonstration: destroys and restores all infrastructure.
**Verifies all 5 requirements:**
1. Data processing services / deployed applications
2. Database systems and their data
3. Configuration settings
4. Access controls and security settings
5. System functionality verification

**Usage:**
```bash
./disaster-recovery-demo.sh [dev|prod]
```

**What it does:**
1. **Phase 1 - Pre-Disaster**: Shows working system (all 5 components verified)
2. **Phase 2 - Disaster**: Destroys all infrastructure (`terraform destroy`)
3. **Phase 3 - Verify Deletion**: Confirms all resources are deleted
4. **Phase 4 - Recovery**: Restores from Infrastructure as Code (`terraform apply`)
5. **Phase 5 - Post-Recovery**: Verifies all 5 components are restored and functional

**Example:**
```bash
# With secret restoration
export MODAL_API_KEY='your-key-here'
./disaster-recovery-demo.sh prod

# Without secret restoration (will prompt to restore manually)
./disaster-recovery-demo.sh prod
```

**⚠️ Warning:** This will destroy all infrastructure! Make sure you have backups.

---

### `secret_recovery.sh`

Restores Modal API key to AWS Secrets Manager.

**Usage:**
```bash
MODAL_API_KEY='your-key' ./secret_recovery.sh [dev|prod]
```

**What it does:**
- Validates the API key
- Uploads to AWS Secrets Manager
- Verifies the secret was created

**Example:**
```bash
export MODAL_API_KEY='your-modal-api-key'
./secret_recovery.sh dev
```

---

### `verify-all-components.sh`

**Comprehensive verification script** that verifies all 5 requirements for disaster recovery demo.

**Usage:**
```bash
./verify-all-components.sh [dev|prod]
```

**What it verifies:**
1. **Data Processing Services / Deployed Applications**
   - ECS cluster status and configuration
   - ECS service status and running tasks
   - Application Load Balancer and target health

2. **Database Systems and Their Data**
   - DynamoDB tables existence
   - Table structure (key schema, GSIs)
   - Table status and item counts

3. **Configuration Settings**
   - Terraform configuration summary
   - Key configuration values (URLs, table names, etc.)
   - Terraform state resource count

4. **Access Controls and Security Settings**
   - IAM roles and their details
   - IAM policies (custom and managed)
   - Security groups configuration
   - Secrets Manager secrets

5. **System Functionality Verification**
   - Backend health endpoint testing
   - HTTP response codes and body
   - Service availability

**Example:**
```bash
./verify-all-components.sh prod
```

---

### `verify-infrastructure.sh`

Basic infrastructure verification (legacy script, use `verify-all-components.sh` for comprehensive checks).

**Usage:**
```bash
./verify-infrastructure.sh [dev|prod]
```

**What it checks:**
- S3 buckets exist
- ECS cluster is running
- DynamoDB tables exist
- Lambda functions exist
- Application Load Balancer exists
- Backend health endpoint responds
- Frontend is accessible

**Example:**
```bash
./verify-infrastructure.sh dev
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Backup state | `./backup-state.sh dev` |
| Full disaster recovery demo | `./disaster-recovery-demo.sh prod` |
| Comprehensive verification (all 5 components) | `./verify-all-components.sh prod` |
| Basic infrastructure verification | `./verify-infrastructure.sh dev` |
| Restore secrets | `MODAL_API_KEY='xxx' ./secret_recovery.sh dev` |

---

## Directory Structure

```
disaster_recovery/
├── README.md                    # This file
├── backup-state.sh             # State file backup
├── disaster-recovery-demo.sh   # Full destroy/restore demo (5 phases)
├── verify-all-components.sh    # Comprehensive verification (all 5 requirements)
├── verify-infrastructure.sh    # Basic infrastructure verification (legacy)
├── secret_recovery.sh          # Secret restoration
└── state-backups/              # Local state file backups (gitignored)
    ├── terraform.tfstate.dev.20260218_143022.json
    └── terraform.tfstate.dev.latest.json
```

---

## For Video Demonstration

When recording your disaster recovery video, follow these phases:

### Phase 1: Pre-Disaster (2-3 minutes)
1. **Show working system**: Run `./verify-all-components.sh prod`
   - Clearly show all 5 components working:
     - Data processing services (ECS cluster, services, tasks)
     - Database systems (DynamoDB tables with structure)
     - Configuration settings (Terraform outputs)
     - Access controls (IAM roles, security groups, secrets)
     - System functionality (health endpoint responding)
2. **Optional**: Show AWS Console briefly to visualize resources

### Phase 2: Disaster (1-2 minutes)
1. **Destroy infrastructure**: Run `./disaster-recovery-demo.sh prod`
   - Show terraform destroy output
   - Emphasize that ALL infrastructure is being deleted

### Phase 3: Verify Deletion (1 minute)
1. **Confirm deletion**: Script automatically verifies
   - Show that resources are gone
   - Optional: Show empty AWS Console

### Phase 4: Recovery (2-3 minutes)
1. **Restore from IaC**: Script automatically runs terraform apply
   - Show Terraform code files briefly
   - Emphasize that everything is restored from code
   - Show resources being created

### Phase 5: Post-Recovery Verification (2-3 minutes)
1. **Verify all components restored**: Script automatically verifies
   - Show all 5 components are restored
   - Test health endpoint
   - Show system is fully functional

**Total time: ~8-12 minutes**

### Tips for Recording:
- Use large terminal font (18-20pt) for visibility
- Pause at each phase to explain what's happening
- Show Terraform code files briefly to emphasize IaC
- Use `terraform show` to display resource details
- Optional: Show AWS Console before/after for visual confirmation

---

## Notes

- All scripts require AWS CLI to be configured
- Scripts assume Terraform is initialized and backend is configured
- State backups are stored locally in `state-backups/` directory
- Secrets must be restored separately after infrastructure restoration



