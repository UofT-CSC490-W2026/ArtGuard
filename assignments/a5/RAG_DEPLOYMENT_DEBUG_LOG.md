# RAG Deployment Bugs

**Goal:** Get documents from S3 into a Bedrock Knowledge Base backed by OpenSearch Serverless, so our FastAPI `/rag-query` endpoint can answer questions about artworks using retrieval-augmented generation.

**Architecture:** S3 (.txt documents) -> Bedrock Knowledge Base (chunking + embedding) -> OpenSearch Serverless (vector store) -> FastAPI `/rag-query` endpoint (RetrieveAndGenerate)

**What made this hard:** We ran into a lot of cascading bugs. Changing the embedding model led to a dimension mismatch, fixing the dimension led to a silent ingestion failure, fixing the mapping led to large file timeouts. Debugging relied heavily on AWS CLI logs (`aws logs tail`, `aws bedrock-agent get-ingestion-job`) and direct OpenSearch queries (`awscurl ... /_count`) since the Bedrock API frequently reported success when nothing actually worked.

### Other Minor Bugs Encountered

Beyond the major bugs documented below, we hit a chain of smaller issues getting the `/rag-query` endpoint working after ingestion succeeded:

- **Old boto3 in Docker image:** The container's `boto3==1.28.0` didn't include the `bedrock-agent-runtime` service (added in 1.34.0). Every call to `RetrieveAndGenerate` threw `UnknownServiceError`. Fixed by updating `requirements.txt` to `boto3>=1.34.0`.

- **Anthropic use case form:** AWS requires first-time Anthropic model users to submit a use case details form before any Claude model can be invoked via Bedrock. One-time per-account, ~15 minute approval. No code change needed.

- **Missing AWS Marketplace permissions:** Anthropic models on Bedrock are delivered through AWS Marketplace. The ECS task role needed `aws-marketplace:ViewSubscriptions` and `aws-marketplace:Subscribe` for the first model invocation. Added to `iam.tf`.

---

## Bug 1: AMAZON_BEDROCK_METADATA Mapping Conflict

### What the bug was and how we discovered it

This was the hardest and most time-consuming bug to debug. After converting files to `.txt` and fixing the dimension issue, ingestion jobs repeatedly reported `COMPLETE` with 0 documents indexed and 0 documents failed. The OpenSearch vector count stayed at 0.

The first clue came when one ingestion job actually reported a failure reason:

```bash
aws bedrock-agent get-ingestion-job \
  --knowledge-base-id XI7PYTAYZC \
  --data-source-id TT4YFXAFIE \
  --ingestion-job-id LSRWR0EEQS \
  --region ca-central-1 \
  --query "ingestionJob.failureReasons"
```

```json
[
  "Encountered error: object mapping for [AMAZON_BEDROCK_METADATA] tried to parse field [AMAZON_BEDROCK_METADATA] as object, but found a concrete value. Issue occurred while processing file: s3://artguard-knowledge-base-dev/documents/wikidata_data.txt. Call to Amazon OpenSearch Serverless Vector Database did not succeed."
]
```

But most subsequent ingestion jobs showed no failure reason at all — they just silently indexed 0 documents. This inconsistency made the bug extremely difficult to track down.

### The debugging process

**Step 1: Understood the error** — OpenSearch expected `AMAZON_BEDROCK_METADATA` to be a JSON object (nested key-value pairs), but Bedrock was sending a flat string value. This is a type mismatch in the OpenSearch mapping.

**Step 2: Tried mapping as `"type": "text"`**

```bash
awscurl --service aoss --region ca-central-1 -X DELETE "${ENDPOINT}/bedrock-knowledge-base-index"
awscurl --service aoss --region ca-central-1 -X PUT "${ENDPOINT}/bedrock-knowledge-base-index" \
  -H 'Content-Type: application/json' \
  -d '{"settings":{"index":{"knn":true,"knn.algo_param.ef_search":512}},"mappings":{"properties":{"bedrock-knowledge-base-index-vector":{"type":"knn_vector","dimension":1024,"method":{"engine":"faiss","name":"hnsw"}},"AMAZON_BEDROCK_TEXT_CHUNK":{"type":"text"},"AMAZON_BEDROCK_METADATA":{"type":"text"}}}}'

aws bedrock-agent start-ingestion-job ...
# Result: COMPLETE, 0 indexed, count: 0
```

**Step 3: Tried omitting the field entirely (let Bedrock auto-create)**

```bash
awscurl --service aoss --region ca-central-1 -X DELETE "${ENDPOINT}/bedrock-knowledge-base-index"
awscurl --service aoss --region ca-central-1 -X PUT "${ENDPOINT}/bedrock-knowledge-base-index" \
  -H 'Content-Type: application/json' \
  -d '{"settings":{"index":{"knn":true,"knn.algo_param.ef_search":512}},"mappings":{"properties":{"bedrock-knowledge-base-index-vector":{"type":"knn_vector","dimension":1024,"method":{"engine":"faiss","name":"hnsw"}},"AMAZON_BEDROCK_TEXT_CHUNK":{"type":"text"}}}}'

aws bedrock-agent start-ingestion-job ...
# Result: COMPLETE, 0 indexed, count: 0
```

**Step 4: Verified the index was structurally broken**

```bash
awscurl --service aoss --region ca-central-1 "${ENDPOINT}/bedrock-knowledge-base-index/_count"
# {"count":0,"_shards":{"total":0,"successful":0,"skipped":0,"failed":0}}

awscurl --service aoss --region ca-central-1 "${ENDPOINT}/bedrock-knowledge-base-index/_mapping"
# Showed our mapping was applied correctly — looked identical to what should work

awscurl --service aoss --region ca-central-1 "${ENDPOINT}/bedrock-knowledge-base-index/_search?size=1"
# {"hits":{"total":{"value":0},"hits":[]}}
```

The critical clue was `"_shards":{"total":0}` — the index had **zero shards allocated**. This meant OpenSearch Serverless wasn't treating the manually-created index the same as one created through its internal provisioning. Even though the mapping looked correct, something about the index creation process was different from what Bedrock expected.

**Step 6: Gave up on manual recreation — used Terraform**

We realized that manually recreating the index via `awscurl` was fundamentally unreliable. The only approach that consistently worked was letting Terraform's `null_resource` create the index through its provisioner script, which matched what Bedrock's internal tooling expected.

### How we fixed it

Destroyed and recreated the entire Knowledge Base via Terraform:

```bash
cd infra/terraform
terraform destroy -var-file=dev.tfvars -target=aws_bedrockagent_knowledge_base.main -target=null_resource.opensearch_index
terraform apply -var-file=dev.tfvars
```

Updated `bedrock.tf` to use `"type": "text"` for `AMAZON_BEDROCK_METADATA` in the Terraform-managed index creation script, so future bootstraps create the index with the correct mapping from the start.

After the Terraform recreation, ingestion worked immediately:

```json
{
  "status": "COMPLETE",
  "stats": {
    "numberOfDocumentsScanned": 101,
    "numberOfNewDocumentsIndexed": 90,
    "numberOfModifiedDocumentsIndexed": 11,
    "numberOfDocumentsFailed": 0
  }
}
```

```bash
awscurl --service aoss --region ca-central-1 "${ENDPOINT}/bedrock-knowledge-base-index/_count"
# {"count":4318}
```

### What we learned

- **Don't manually recreate managed infrastructure** — OpenSearch Serverless indexes created via `awscurl PUT` are not identical to those created by Bedrock's internal provisioner or Terraform's provisioner, even with the same JSON mapping. There are likely internal metadata or shard allocation settings that differ.
- **Silent failures with `_shards: {"total": 0}`** — this means the index exists but has no storage allocated. It can accept write requests without error, but nothing persists.

### Test cases to prevent reoccurrence

```bash
pytest tests/test_rag_deployment.py::TestOpenSearchIndexConfig -v
```

- `test_bedrock_tf_uses_text_for_metadata` — reads `bedrock.tf` and asserts `AMAZON_BEDROCK_METADATA` is `"type": "text"`, not `"object"`. If someone changes it, this test fails.
- `test_bedrock_tf_uses_1024_dimensions` — ensures vector dimension matches `titan-embed-text-v2` output (1024, not 1536).
- `test_variables_tf_uses_v2_embedding_model` — ensures we use `titan-embed-text-v2`, not v1 (which doesn't exist in `ca-central-1`).

---

## Bug 2: Large File Ingestion Stuck/Timeout

### What the bug was and how we discovered it

After fixing the metadata mapping by recreating via Terraform, we uploaded a single 20MB `met_data.txt` file containing 50,000 artwork records. The ingestion job started but never progressed past `numberOfNewDocumentsIndexed: 0` for over 30 minutes:

```bash
# Checked repeatedly over 30 minutes:
aws bedrock-agent get-ingestion-job \
  --knowledge-base-id XI7PYTAYZC \
  --data-source-id TT4YFXAFIE \
  --ingestion-job-id 6CB9RZXNMF \
  --region ca-central-1 \
  --query "ingestionJob.{status:status,updatedAt:updatedAt,stats:statistics}"
```

```json
{
  "status": "IN_PROGRESS",
  "updatedAt": "2026-03-15T20:30:20.183446+00:00",
  "stats": {
    "numberOfDocumentsScanned": 2,
    "numberOfNewDocumentsIndexed": 0,
    "numberOfDocumentsFailed": 0
  }
}
```

### The debugging process

**Step 1: Checked if the job was alive by monitoring `updatedAt`**

```bash
# Run 1:
"updatedAt": "2026-03-15T20:28:52.525372+00:00"
# Run 2 (30 seconds later):
"updatedAt": "2026-03-15T20:29:37.790397+00:00"
# Run 3 (30 seconds later):
"updatedAt": "2026-03-15T20:30:20.183446+00:00"
```

The `updatedAt` kept changing, meaning Bedrock was still alive and processing. But `numberOfNewDocumentsIndexed` stayed at 0 for 30+ minutes.

**Step 2: Checked vector count directly in OpenSearch**

```bash
awscurl --service aoss --region ca-central-1 "${ENDPOINT}/bedrock-knowledge-base-index/_count"
# {"count":2301} — some vectors existed, but stopped growing
```

2,301 vectors were indexed but the count stopped growing. Bedrock was processing the file but got stuck partway through. A 20MB text file with 50,000 records generates thousands of 300-token chunks, each requiring an embedding API call. The `ca-central-1` region likely has lower embedding throughput, and the single massive file caused the chunking/embedding pipeline to bottleneck or timeout.

**Step 3: Confirmed file sizes**

```bash
ls -lh src/apps/data_pipeline/output/txt/
# met_data.txt    20M
# wikidata_data.txt  3.5K
```

The 20MB file was the problem. The 3.5K wikidata file would have been fine on its own.

### How we fixed it

Updated `scripts/convert-jsonl-to-txt.py` to split the output into ~100 smaller files of ~500 records each (~200KB per file):

```bash
python3 scripts/convert-jsonl-to-txt.py
ls src/apps/data_pipeline/output/txt/
# met_data_part1.txt ... met_data_part100.txt, wikidata_data.txt
```

After uploading the split files and re-ingesting:

```json
{
  "status": "COMPLETE",
  "stats": {
    "numberOfDocumentsScanned": 101,
    "numberOfNewDocumentsIndexed": 90,
    "numberOfModifiedDocumentsIndexed": 11,
    "numberOfDocumentsFailed": 0
  }
}
```

```bash
awscurl --service aoss --region ca-central-1 "${ENDPOINT}/bedrock-knowledge-base-index/_count"
# {"count":4318} — success!
```

101 documents scanned, 101 indexed, 4318 vectors. The smaller files completed in ~8 minutes vs the 20MB file that was stuck for 30+ minutes.

### What we learned

Bedrock Knowledge Base ingestion has practical limits on file size even though the documented limit is 50MB. A 20MB text file with 50,000 records generates tens of thousands of embedding API calls, which can overwhelm the embedding model's throughput in regions with lower capacity. Splitting into many smaller files allows Bedrock to process them in parallel and recover gracefully if one file has issues.

### Test cases to prevent reoccurrence

```bash
pytest tests/test_rag_deployment.py::TestFileSplitting -v
```

- `test_no_txt_file_exceeds_max_size` — verifies no single `.txt` file exceeds 500KB.
- `test_split_produces_multiple_files_for_large_dataset` — verifies large datasets produce multiple part files.
- `test_convert_script_splits_at_500_records` — verifies the split threshold is set to 500 in the script.

---

## Bug 3: OOM Kill — Pipeline Crashing the ECS Container (Exit Code -9)

### What the bug was and how we discovered it

One of our dataset pipelines (`met_pipeline.py`) was running as a background task inside the FastAPI container on ECS Fargate. We triggered the pipeline via `POST /upload-rag-data` and monitored status via `GET /upload-rag-data/status` (a custom endpoint we built to track background task progress). The status endpoint returned:

```bash
curl ${BACKEND_URL}/upload-rag-data/status
```

```json
{
  "status": "failed",
  "step": "Running met_pipeline.py",
  "error": "src/apps/data_pipeline/met_pipeline.py failed (exit code -9):\nSTDOUT: Loading MET dataset (streaming)...\n  Processed 10000 records...\n\nSTDERR: Warning: You are sending unauthenticated requests to the HF Hub..."
}
```

Exit code `-9` means `SIGKILL` — the Linux kernel's Out-Of-Memory (OOM) killer forcefully terminated the process. The process consistently died at exactly ~10,000 records every time we retried, confirming it was a memory ceiling issue, not a random crash.

The pipeline subprocess consumed so much memory that it didn't just kill itself — it killed the **entire ECS container**, taking down the FastAPI server and returning 503 to all requests:

```bash
curl ${BACKEND_URL}/health
```

```html
<html><head><title>503 Service Temporarily Unavailable</title></head>...</html>
```

### The debugging process

1. **Checked the status endpoint repeatedly** — saw it go from `"running"` to `"failed"` with exit code -9
2. **Identified the pattern** — it always died at ~10,000 records, suggesting memory grew linearly with records processed
3. **Root cause analysis** — we were using the HuggingFace `datasets` library to download the MET museum's 480,000 artwork records. Even in "streaming" mode, the library internally caches and buffers data. Combined with Python's memory overhead for dict objects (~200-400 bytes per dict on top of the data), this exceeded the Fargate task's 2GB memory limit. The 2GB was shared between the FastAPI server, uvicorn, the Python runtime, and the pipeline subprocess — so the pipeline realistically had ~1-1.5GB available.
4. **Realized the blast radius** — when the subprocess OOM'd, the Linux kernel killed the largest memory consumer in the container, which was the subprocess + parent FastAPI process, causing the container to restart and losing all in-flight requests.

### How we fixed it

- Rewrote `met_pipeline.py` to download MetObjects.csv directly via HTTP using `urllib.request` with chunked writing to disk, then processed line-by-line with `csv.DictReader` — keeping memory constant regardless of dataset size
- Added `MAX_RECORDS = 50000` limit and periodic `gc.collect()` calls
- Ultimately decided to **run pipelines locally** rather than inside the memory-constrained ECS container, since the output files are small (~20MB) and only need to be generated once. Our laptops have 8-16GB+ of RAM vs the container's 2GB.

### What we learned

Running heavy data processing inside a web server container is fundamentally risky. The pipeline had no memory isolation from the API server — one bad subprocess could take down the entire service. Data pipelines should run separately (local machine, batch job, or a dedicated container with higher memory limits) and only the final output should be uploaded.

### Test cases to prevent reoccurrence

```bash
pytest tests/test_rag_deployment.py::TestPipelineOutput -v
```

- `test_met_data_jsonl_exists` — verifies the pipeline output file exists (was generated locally).
- `test_jsonl_records_are_valid_json` — every record has a `text` field with content.
- `test_met_data_has_records` — output has at least 1 valid record.

---

## Bug 4: JSONL Format Not Supported by Bedrock Knowledge Base

### What the bug was and how we discovered it

After generating the pipeline output as `.jsonl` files and uploading them to S3, we triggered a Bedrock Knowledge Base ingestion job. The job reported `COMPLETE` with zero failures — but also zero documents indexed:

```bash
aws bedrock-agent get-ingestion-job \
  --knowledge-base-id XI7PYTAYZC \
  --data-source-id TT4YFXAFIE \
  --ingestion-job-id V3PMVVQWCJ \
  --region ca-central-1 \
  --query "ingestionJob.{status:status,stats:statistics}"
```

```json
{
  "status": "COMPLETE",
  "stats": {
    "numberOfDocumentsScanned": 1,
    "numberOfNewDocumentsIndexed": 0,
    "numberOfDocumentsFailed": 0
  }
}
```

We confirmed with a direct vector count query that nothing was actually stored:

```bash
awscurl --service aoss --region ca-central-1 "${ENDPOINT}/bedrock-knowledge-base-index/_count"
```

```json
{"count":0,"_shards":{"total":0,"successful":0,"skipped":0,"failed":0}}
```

This was particularly deceptive because `status: COMPLETE` and `numberOfDocumentsFailed: 0` suggested everything worked. The only way to catch this was independently verifying the vector count.

### The debugging process

1. **Checked ingestion status** — `COMPLETE`, 0 failed. Looked like success
2. **Checked vector count** — 0 vectors in OpenSearch. Something was wrong
3. **Checked S3 files** — files were there: `met_data.jsonl` and `wikidata_data.jsonl`
4. **Researched Bedrock supported formats** — Bedrock Knowledge Base supports `.txt`, `.pdf`, `.csv`, `.md`, `.html`, `.doc`, `.xls` but **not `.jsonl`**. Bedrock scanned the files, couldn't parse the JSONL format, but didn't count them as "failed" — it silently skipped them
5. **Root cause** — JSONL is a machine-readable format (one JSON object per line). Bedrock's text chunker doesn't know how to extract meaningful text from JSON structures. It needs plain text to split into chunks and generate embeddings

### How we fixed it

Created `scripts/convert-jsonl-to-txt.py` which:
- Reads each `.jsonl` file
- Extracts the `text` field from each JSON record (which contains the human-readable artwork description)
- Writes plain `.txt` files with one record per section, separated by `---`
- Splits large files into smaller parts (~500 records per file)

Updated `upload-rag-data.sh` to run the conversion before uploading.

### What we learned

Never trust a `COMPLETE` status without independently verifying the result. Bedrock's ingestion API has a design flaw where unsupported file formats are silently ignored rather than reported as failures. The `numberOfDocumentsFailed` counter only increments for files that Bedrock *attempted* to process and encountered an error — files it can't parse at all are simply skipped.

### Test cases to prevent reoccurrence

```bash
pytest tests/test_rag_deployment.py::TestJsonlToTxtConversion -v
```

- `test_conversion_produces_txt_files` — runs the conversion script and verifies `.txt` files are produced.
- `test_txt_files_contain_plain_text_not_json` — verifies output starts with plain text, not `{`.
- `test_no_jsonl_files_in_txt_directory` — ensures no `.jsonl` files end up in the upload directory.

---

## Bug 5: S3 Buckets Not Empty on terraform destroy

### What the bug was and how we discovered it

When running `terraform destroy` to tear down the environment, Terraform failed on S3 bucket deletion:

```bash
terraform destroy -var-file=dev.tfvars
```

```
Error: deleting S3 Bucket (artguard-images-raw-dev): BucketNotEmpty:
The bucket you tried to delete is not empty.
You must delete all versions in the bucket.

Error: deleting S3 Bucket (artguard-knowledge-base-dev): BucketNotEmpty:
The bucket you tried to delete is not empty.
You must delete all versions in the bucket.
```

### The debugging process

1. **First attempt** — ran `aws s3 rm --recursive` to empty the buckets. Terraform destroy still failed with the same error
2. **Realized versioning was enabled** — S3 versioning (configured in Terraform for data protection) means that `aws s3 rm` only creates "delete markers" — it doesn't actually remove the underlying object versions. The bucket appears empty when you `ls` it, but it still contains version history
3. **Needed to delete all object versions AND delete markers** — the standard `aws s3 rm` command doesn't handle this

### How we fixed it

Used boto3 to delete all object versions (including delete markers):

```bash
python3 -c "
import boto3
s3 = boto3.resource('s3', region_name='ca-central-1')
for bucket_name in ['artguard-images-raw-dev', 'artguard-knowledge-base-dev',
                     'artguard-images-processed-dev', 'artguard-frontend-dev']:
    try:
        bucket = s3.Bucket(bucket_name)
        bucket.object_versions.all().delete()
        print(f'{bucket_name} emptied')
    except Exception as e:
        print(f'{bucket_name} skipped: {e}')
"

terraform destroy -var-file=dev.tfvars
```

This was later automated into `scripts/destroy-all.sh` so teammates don't have to do it manually. We also encountered a related issue where Secrets Manager secrets had a 7-30 day deletion recovery window that blocked recreation — solved by using `--force-delete-without-recovery`.

### What we learned

S3 bucket versioning adds a hidden layer of complexity to cleanup. `aws s3 rm --recursive` is not sufficient for versioned buckets — you must use the S3 API to delete all object versions. Always include bucket emptying logic in destroy/teardown scripts when versioning is enabled.

### Test cases to prevent reoccurrence

```bash
pytest tests/test_rag_deployment.py::TestDestroyScript -v
```

- `test_destroy_script_empties_versioned_buckets` — verifies `destroy-all.sh` handles S3 object versions (not just objects).
- `test_destroy_script_force_deletes_secrets` — verifies `destroy-all.sh` uses `--force-delete-without-recovery` for Secrets Manager.

---

## Key Debug Commands Used

| Purpose | Command |
|---------|---------|
| Check ingestion status | `aws bedrock-agent get-ingestion-job --knowledge-base-id $KB_ID --data-source-id $DS_ID --ingestion-job-id $JOB_ID --region ca-central-1 --query "ingestionJob.{status:status,stats:statistics}"` |
| Check failure reasons | `aws bedrock-agent get-ingestion-job ... --query "ingestionJob.failureReasons"` |
| Check vector count | `awscurl --service aoss --region ca-central-1 "${ENDPOINT}/bedrock-knowledge-base-index/_count"` |
| Check index mapping | `awscurl --service aoss --region ca-central-1 "${ENDPOINT}/bedrock-knowledge-base-index/_mapping"` |
| Search index contents | `awscurl --service aoss --region ca-central-1 "${ENDPOINT}/bedrock-knowledge-base-index/_search?size=1"` |
| Check ECS backend errors | `aws logs tail /ecs/artguard-backend --region ca-central-1 --since 5m` |
| Find specific error | `aws logs tail /ecs/artguard-backend --region ca-central-1 --since 5m \| grep -A 1 "raise error_class"` |
| Check available models | `aws bedrock list-foundation-models --region ca-central-1 --query "modelSummaries[?contains(modelId, 'titan-embed')].modelId"` |
| Stop stuck ingestion | `aws bedrock-agent stop-ingestion-job --knowledge-base-id $KB_ID --data-source-id $DS_ID --ingestion-job-id $JOB_ID --region ca-central-1` |
| List ingestion jobs | `aws bedrock-agent list-ingestion-jobs --knowledge-base-id $KB_ID --data-source-id $DS_ID --region ca-central-1 --query "ingestionJobSummaries[:3]"` |
| Check S3 contents | `aws s3 ls s3://artguard-knowledge-base-dev/documents/ --region ca-central-1` |
| Delete OpenSearch index | `awscurl --service aoss --region ca-central-1 -X DELETE "${ENDPOINT}/bedrock-knowledge-base-index"` |
| Check ECS task count | `./scripts/ecs-control.sh status dev` |
| Check collection status | `aws opensearchserverless list-collections --region ca-central-1` |

---

## Automated Test Suite

All bugs have corresponding pytest test cases in `tests/test_rag_deployment.py`. Run with:

```bash
pytest tests/test_rag_deployment.py -v
```

| Test Class | Bug Covered | What It Verifies |
|------------|-------------|------------------|
| `TestOpenSearchIndexConfig` | Bug 1 (Metadata mapping) | `bedrock.tf` uses `text` type for metadata (not `object`), dimension is 1024, model is v2 |
| `TestFileSplitting` | Bug 2 (Large files) | No file exceeds 500KB, large datasets produce multiple parts, split threshold is 500 records |
| `TestPipelineOutput` | Bug 3 (OOM Kill) | JSONL files exist, have valid records with `text` field, record count is within bounds |
| `TestJsonlToTxtConversion` | Bug 4 (JSONL format) | Conversion produces `.txt` files, output is plain text not JSON, no `.jsonl` in output dir |
| `TestDestroyScript` | Bug 5 (Destroy issues) | `destroy-all.sh` deletes S3 object versions and force-deletes secrets |
| `TestBoto3Compatibility` | Minor (boto3 version) | `bedrock-agent-runtime` service exists in boto3, `requirements.txt` pins >= 1.34 |
| `TestModelConfiguration` | Minor (Model selection) | Uses `claude-3-haiku` (not Sonnet), no hardcoded Sonnet in rag_query endpoint |
| `TestIAMConfiguration` | Minor (Marketplace perms) | `iam.tf` includes `aws-marketplace` permissions and Bedrock permissions |
| `TestConversionPipelineIntegration` | Bugs 2+4 (End-to-end) | Full JSONL->txt pipeline: splitting, size limits, plain text output |

---
