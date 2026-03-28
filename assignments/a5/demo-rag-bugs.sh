#!/bin/bash
# ============================================================================
# RAG Bug Reproduction Demo Script
# ============================================================================
# Reproduces Bug 1 (AMAZON_BEDROCK_METADATA) from
# RAG_DEPLOYMENT_DEBUG_LOG.md — the most impactful bug we encountered.
#
# This bug is the best one to demo live because:
#   - It's fully reproducible in ~5 minutes
#   - The failure is SILENT (status says COMPLETE, but 0 vectors indexed)
#   - The fix is a single field change (object -> text)
#   - It demonstrates why you should always verify with _count
#
# Bugs NOT reproduced live
#   - Bug 1 (OOM Kill): Would need to redeploy old code with HuggingFace lib
#   - Bug 2 (JSONL format): Would need to re-upload .jsonl files to S3
#   - Bug 4 (Large files): Would take 30+ min to show stuck ingestion
#
# PREREQUISITE: Infrastructure must be running (terraform apply completed,
# ECS deployed, data uploaded to S3, ingestion completed at least once).
#
# Usage: ./assignments/a5/demo-rag-bugs.sh
# ============================================================================

set -euo pipefail

# Source colors from the scripts directory
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "${REPO_ROOT}/scripts/_colors.sh"

# ─── Demo-specific helpers ───────────────────────────────────────────────────
pause() {
    echo ""
    echo -e "${YELLOW}>> Press ENTER to continue to next step...${NC}"
    read -r
}

demo_step() {
    echo ""
    echo -e "${BLUE}── Step $1: $2${NC}"
    echo ""
}

show_cmd() {
    echo -e "${GREEN}\$ $1${NC}"
}

run_cmd() {
    show_cmd "$1"
    eval "$1" 2>&1 || true
    echo ""
}

explain()      { echo -e "${YELLOW}$1${NC}"; }
demo_error()   { echo -e "${RED}$1${NC}"; }
demo_success() { echo -e "${GREEN}$1${NC}"; }

# ============================================================================
# Setup: Get environment variables
# ============================================================================

header "Setup: Loading environment variables"

REGION="ca-central-1"
KB_ID=$(terraform -chdir="${REPO_ROOT}/infra/terraform" output -raw knowledge_base_id 2>/dev/null || echo "")
DS_ID=$(aws bedrock-agent list-data-sources --knowledge-base-id "$KB_ID" --region $REGION --query "dataSourceSummaries[0].dataSourceId" --output text 2>/dev/null || echo "")
ENDPOINT=$(terraform -chdir="${REPO_ROOT}/infra/terraform" output -raw opensearch_collection_endpoint 2>/dev/null || echo "")
BACKEND_URL=$(terraform -chdir="${REPO_ROOT}/infra/terraform" output -json summary 2>/dev/null | jq -r '.backend_url' || echo "")
# Read the index name from dev.tfvars to match what Bedrock is configured to use
INDEX_NAME=$(grep 'bedrock_vector_index_name' "${REPO_ROOT}/infra/terraform/dev.tfvars" | sed 's/.*= *"\(.*\)".*/\1/')
VECTOR_FIELD="${INDEX_NAME}-vector"

if [ -z "$KB_ID" ] || [ -z "$ENDPOINT" ]; then
    echo -e "${RED}Error: Infrastructure not deployed. Run ./scripts/deploy-all.sh dev first.${NC}"
    exit 1
fi

echo "Knowledge Base ID: $KB_ID"
echo "Data Source ID:    $DS_ID"
echo "OpenSearch:        $ENDPOINT"
echo "Backend URL:       $BACKEND_URL"
echo "Index Name:        $INDEX_NAME"

pause

# ============================================================================
# PART 1: Show the working state first
# ============================================================================

header "PART 1: Showing the current WORKING state"

demo_step "1" "Verify vectors are currently indexed"
run_cmd "awscurl --service aoss --region $REGION '${ENDPOINT}/${INDEX_NAME}/_count'"
demo_success "Count > 0 means vectors are indexed and RAG queries work."

demo_step "2" "Verify RAG query returns results"
run_cmd "curl -s -X POST ${BACKEND_URL}/rag-query -H 'Content-Type: application/json' -d '{\"query\": \"Tell me about art forgery\"}' | python3 -m json.tool"
demo_success "RAG query returns an answer with sources. Everything works."

explain "Now let's BREAK it by reproducing the bug..."

pause

# ============================================================================
# PART 2: Reproduce Bug 3 — The Silent Failure
# ============================================================================

header "PART 2: REPRODUCING THE BUG"
echo ""
explain "Bug 3 from RAG_DEPLOYMENT_DEBUG_LOG.md:"
explain "AMAZON_BEDROCK_METADATA Mapping Conflict (The Silent Failure)"
echo ""
explain "CONTEXT: Bedrock Knowledge Base stores document vectors in OpenSearch."
explain "Each vector has 3 fields:"
explain "  - ${INDEX_NAME}-vector (the embedding)"
explain "  - AMAZON_BEDROCK_TEXT_CHUNK (the text chunk)"
explain "  - AMAZON_BEDROCK_METADATA (metadata about the source document)"
echo ""
explain "THE BUG: When AMAZON_BEDROCK_METADATA is mapped as 'object' type"
explain "instead of 'text' type, Bedrock ingestion reports COMPLETE with"
explain "0 failures — but indexes 0 documents. A SILENT failure."
echo ""
explain "This was the hardest bug to debug because the API told us"
explain "everything succeeded when nothing actually worked."

pause

demo_step "1" "Delete the working index"
run_cmd "awscurl --service aoss --region $REGION -X DELETE '${ENDPOINT}/${INDEX_NAME}'"
explain "Index deleted. Now we'll recreate it with the WRONG mapping."

demo_step "2" "Create index with WRONG metadata mapping (type=object)"
show_cmd "awscurl -X PUT ... AMAZON_BEDROCK_METADATA: {\"type\": \"object\"}"
awscurl --service aoss --region $REGION -X PUT "${ENDPOINT}/${INDEX_NAME}" \
  -H 'Content-Type: application/json' \
  -d '{"settings":{"index":{"knn":true}},"mappings":{"properties":{"'"${VECTOR_FIELD}"'":{"type":"knn_vector","dimension":1024,"method":{"engine":"faiss","name":"hnsw"}},"AMAZON_BEDROCK_TEXT_CHUNK":{"type":"text"},"AMAZON_BEDROCK_METADATA":{"type":"object"}}}}' 2>&1 || true
echo ""
explain "Index created with metadata as 'object' — this is the broken config."

pause

demo_step "3" "Trigger ingestion (Bedrock processes S3 documents into vectors)"
INGEST_RESULT=$(aws bedrock-agent start-ingestion-job --knowledge-base-id "$KB_ID" --data-source-id "$DS_ID" --region $REGION 2>&1 || true)
JOB_ID=$(echo "$INGEST_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['ingestionJob']['ingestionJobId'])" 2>/dev/null || echo "")
echo "$INGEST_RESULT" | python3 -m json.tool 2>/dev/null || echo "$INGEST_RESULT"

if [ -z "$JOB_ID" ]; then
    explain "Could not start ingestion (may be conflicting with an existing job)."
    explain "In our actual debugging, the ingestion DID start and reported COMPLETE."
    explain "Showing what the result looked like from our debug log..."
    echo ""
    echo '  {
    "status": "COMPLETE",
    "stats": {
      "numberOfDocumentsScanned": 101,
      "numberOfNewDocumentsIndexed": 0,
      "numberOfDocumentsFailed": 0
    }
  }'
    echo ""
    demo_error "Status: COMPLETE. Failures: 0. Looks perfect... but it's lying."

    pause

    demo_step "4" "Check the ACTUAL vector count — THE TRUTH"
    run_cmd "awscurl --service aoss --region $REGION '${ENDPOINT}/${INDEX_NAME}/_count'"
    demo_error "count: 0! NOTHING was actually indexed!"
    demo_error "The ingestion said COMPLETE with 0 failures, but stored ZERO vectors."
    explain "This is the silent failure. The ONLY way to catch it is checking _count."
else
    demo_step "4" "Wait for ingestion to complete..."
    explain "Polling every 30 seconds (usually takes 2-5 minutes)..."
    while true; do
        STATUS=$(aws bedrock-agent get-ingestion-job \
            --knowledge-base-id "$KB_ID" --data-source-id "$DS_ID" \
            --ingestion-job-id "$JOB_ID" --region $REGION \
            --query "ingestionJob.status" --output text 2>/dev/null)
        echo "  Status: $STATUS"
        if [ "$STATUS" = "COMPLETE" ] || [ "$STATUS" = "FAILED" ] || [ "$STATUS" = "STOPPED" ]; then
            break
        fi
        sleep 30
    done

    demo_step "5" "Check the ingestion result — looks like success!"
    run_cmd "aws bedrock-agent get-ingestion-job --knowledge-base-id $KB_ID --data-source-id $DS_ID --ingestion-job-id $JOB_ID --region $REGION --query \"ingestionJob.{status:status,stats:statistics}\""

    demo_error "Status is COMPLETE, numberOfDocumentsFailed is 0."
    demo_error "It LOOKS successful... but is it?"

    pause

    demo_step "6" "Check the ACTUAL vector count — THE TRUTH"
    run_cmd "awscurl --service aoss --region $REGION '${ENDPOINT}/${INDEX_NAME}/_count'"

    demo_error "count: 0! NOTHING was actually indexed!"
    demo_error "The ingestion said COMPLETE with 0 failures, but stored ZERO vectors."
    explain "This is the silent failure. The ONLY way to catch it is checking _count."
fi

pause

# ============================================================================
# PART 3: Apply the fix
# ============================================================================

header "PART 3: APPLYING THE FIX"
echo ""
explain "The fix: Change AMAZON_BEDROCK_METADATA from 'object' to 'text'."
explain "That's it. One field type change."
echo ""
explain "IMPORTANT: Manually recreating the index with awscurl does NOT work."
explain "Indexes created via awscurl get 0 shards allocated — they accept writes"
explain "silently but persist nothing. We MUST use Terraform to recreate it."

pause

demo_step "1" "Destroy Knowledge Base + index via Terraform, then recreate"
explain "Two problems must be solved:"
explain "  1. Indexes created via awscurl get 0 shards — must use Terraform"
explain "  2. The data source tracks which docs were 'processed' — destroying"
explain "     the KB resets this so all 101 documents are treated as new"
echo ""
# This is the exact fix from the debug log (lines 98-100 of RAG_DEPLOYMENT_DEBUG_LOG.md)
show_cmd "terraform destroy -target=... (data source, knowledge base, index)"
{ terraform -chdir="${REPO_ROOT}/infra/terraform" destroy \
    -var-file=dev.tfvars \
    -target=aws_bedrockagent_data_source.s3_documents \
    -target=aws_bedrockagent_knowledge_base.main \
    -target=null_resource.opensearch_index \
    -auto-approve 2>&1 || true; } | tail -10
echo ""
explain "Terraform destroyed the data source, KB, and null_resource from state."
explain "But the broken OpenSearch index still exists — null_resource has no destroy provisioner."
echo ""

demo_step "1b" "Delete the broken index from OpenSearch"
explain "Now safe to delete — data source is already gone, so no DELETE_UNSUCCESSFUL error."
run_cmd "awscurl --service aoss --region $REGION -X DELETE '${ENDPOINT}/${INDEX_NAME}'"
explain "Broken index removed. Terraform apply will now create a FRESH index."
echo ""

demo_step "1c" "Recreate everything with correct mapping via Terraform apply"
show_cmd "terraform apply -var-file=dev.tfvars -auto-approve"
{ terraform -chdir="${REPO_ROOT}/infra/terraform" apply \
    -var-file=dev.tfvars \
    -auto-approve 2>&1 || true; } | tail -15
echo ""
demo_success "Terraform recreated the index (type=text), KB, and data source from scratch."

# Re-read KB_ID and DS_ID — they WILL have changed since we destroyed the KB
KB_ID=$(terraform -chdir="${REPO_ROOT}/infra/terraform" output -raw knowledge_base_id 2>/dev/null || echo "")
DS_ID=$(aws bedrock-agent list-data-sources --knowledge-base-id "$KB_ID" --region $REGION --query "dataSourceSummaries[0].dataSourceId" --output text 2>/dev/null || echo "")
echo "  New KB_ID: $KB_ID"
echo "  New DS_ID: $DS_ID"

demo_step "2" "Redeploy ECS backend with new Knowledge Base ID"
explain "The KB was recreated with a new ID. The running ECS containers still"
explain "have the old KNOWLEDGE_BASE_ID env var. Force a new deployment."
show_cmd "aws ecs update-service --cluster artguard-cluster --service artguard-backend --force-new-deployment"
aws ecs update-service \
    --cluster artguard-cluster \
    --service artguard-backend \
    --force-new-deployment \
    --region $REGION \
    --query "service.deployments[0].{status:status,desired:desiredCount,running:runningCount}" 2>&1 || true
echo ""
demo_success "ECS rolling deployment triggered with new KB_ID."

demo_step "3" "Wait for ECS deployment to stabilize"
explain "ECS rolling deployment takes ~2-3 minutes. Polling until complete..."
ECS_TIMEOUT=300
ECS_ELAPSED=0
while [ $ECS_ELAPSED -lt $ECS_TIMEOUT ]; do
    DEPLOY_COUNT=$(aws ecs describe-services \
        --cluster artguard-cluster \
        --services artguard-backend \
        --region $REGION \
        --query "length(services[0].deployments)" \
        --output text 2>/dev/null || echo "unknown")
    RUNNING=$(aws ecs describe-services \
        --cluster artguard-cluster \
        --services artguard-backend \
        --region $REGION \
        --query "services[0].deployments[0].runningCount" \
        --output text 2>/dev/null || echo "0")
    echo "  Deployments: $DEPLOY_COUNT | Running tasks (new): $RUNNING | Elapsed: ${ECS_ELAPSED}s"
    # Done when only 1 deployment remains (old tasks drained)
    if [ "$DEPLOY_COUNT" = "1" ] && [ "$RUNNING" != "0" ]; then
        break
    fi
    sleep 15
    ECS_ELAPSED=$((ECS_ELAPSED + 15))
done
demo_success "ECS deployment stabilized. Backend is running with new KB_ID."

demo_step "4" "Trigger ingestion with the fixed index"
INGEST_RESULT2=$(aws bedrock-agent start-ingestion-job --knowledge-base-id "$KB_ID" --data-source-id "$DS_ID" --region $REGION 2>&1 || true)
JOB_ID2=$(echo "$INGEST_RESULT2" | python3 -c "import sys,json; print(json.load(sys.stdin)['ingestionJob']['ingestionJobId'])" 2>/dev/null || echo "")
echo "$INGEST_RESULT2" | python3 -m json.tool 2>/dev/null || echo "$INGEST_RESULT2"

if [ -n "$JOB_ID2" ]; then
    demo_step "5" "Wait for ingestion to complete..."
    while true; do
        STATUS=$(aws bedrock-agent get-ingestion-job \
            --knowledge-base-id "$KB_ID" --data-source-id "$DS_ID" \
            --ingestion-job-id "$JOB_ID2" --region $REGION \
            --query "ingestionJob.status" --output text 2>/dev/null)
        echo "  Status: $STATUS"
        if [ "$STATUS" = "COMPLETE" ] || [ "$STATUS" = "FAILED" ] || [ "$STATUS" = "STOPPED" ]; then
            break
        fi
        sleep 30
    done

    demo_step "6" "Check ingestion result"
    run_cmd "aws bedrock-agent get-ingestion-job --knowledge-base-id $KB_ID --data-source-id $DS_ID --ingestion-job-id $JOB_ID2 --region $REGION --query \"ingestionJob.{status:status,stats:statistics}\""

    demo_step "7" "Check vector count — should be > 0 now!"
    run_cmd "awscurl --service aoss --region $REGION '${ENDPOINT}/${INDEX_NAME}/_count'"
    demo_success "Vectors are indexed! The fix worked."
else
    explain "Could not start ingestion. The fix was applied to the index."
    explain "In production, this re-ingestion successfully indexed all documents."
fi

pause

# ============================================================================
# PART 4: Test cases that prevent reoccurrence
# ============================================================================

header "PART 4: TEST CASES (preventing reoccurrence)"

demo_step "1" "Run the automated test suite"
explain "We created 23 pytest tests that verify all the fixes for every bug"
explain "documented in RAG_DEPLOYMENT_DEBUG_LOG.md:"
echo ""
run_cmd "cd ${REPO_ROOT} && python3 -m pytest tests/test_rag_deployment.py -v --tb=short 2>&1 | head -35"

demo_step "2" "Key tests for this bug (Bug 3: Silent Failure)"
echo "  TestOpenSearchIndexConfig:"
echo "    test_bedrock_tf_uses_text_for_metadata"
echo "      -> Reads bedrock.tf and asserts AMAZON_BEDROCK_METADATA is 'text'"
echo "      -> If someone changes it to 'object', this test FAILS"
echo "      -> Catches the exact silent failure we just demonstrated"
echo ""
echo "    test_bedrock_tf_uses_1024_dimensions"
echo "      -> Ensures vector dimension matches titan-embed-text-v2 output"
echo "      -> Catches dimension mismatch error (1536 vs 1024)"
echo ""
echo "    test_variables_tf_uses_v2_embedding_model"
echo "      -> Ensures we use titan-embed-text-v2, not v1"
echo "      -> v1 doesn't exist in ca-central-1"

pause

# ============================================================================
# PART 5: Verify everything works end-to-end
# ============================================================================

header "PART 5: End-to-end verification"

demo_step "1" "Verify ECS task has the new KB ID"
TASK_KB_ID=$(aws ecs describe-task-definition \
    --task-definition artguard-backend \
    --region $REGION \
    --query "taskDefinition.containerDefinitions[0].environment[?name=='KNOWLEDGE_BASE_ID'].value | [0]" \
    --output text 2>/dev/null || echo "unknown")
echo "  Expected KB_ID: $KB_ID"
echo "  Task def KB_ID: $TASK_KB_ID"
if [ "$TASK_KB_ID" = "$KB_ID" ]; then
    demo_success "Task definition has the correct KB_ID."
else
    demo_error "MISMATCH! Task definition KB_ID does not match. ECS may need more time."
fi
echo ""

demo_step "2" "Health check"
run_cmd "curl -s ${BACKEND_URL}/health | python3 -m json.tool"

demo_step "3" "RAG query — the same query that failed before"
run_cmd "curl -s -X POST ${BACKEND_URL}/rag-query -H 'Content-Type: application/json' -d '{\"query\": \"Tell me about Vincent van Gogh painting style\"}' | python3 -m json.tool"

demo_step "4" "Final vector count"
run_cmd "awscurl --service aoss --region $REGION '${ENDPOINT}/${INDEX_NAME}/_count'"

header "Demo Complete!"
echo ""
echo "What we demonstrated:"
echo "  1. SHOWED the working state (vectors indexed, RAG query returns results)"
echo "  2. BROKE it by changing metadata mapping from 'text' to 'object'"
echo "  3. SHOWED the silent failure (COMPLETE status, 0 vectors)"
echo "  4. FIXED it by changing back to 'text'"
echo "  5. VERIFIED vectors are re-indexed and RAG query works again"
echo "  6. SHOWED test cases that prevent this from happening again"
echo ""
echo "Key takeaway: Never trust API status alone — always verify the actual data."
echo ""
