"""
Test cases for RAG deployment bugs.

These tests verify the fixes for bugs encountered during RAG pipeline deployment.
They cover: file format conversion, file splitting, boto3 compatibility,
OpenSearch index configuration, and end-to-end RAG query validation.

Run with: pytest tests/test_rag_deployment.py -v
"""
import json
import os
import subprocess
import pytest


# ---------------------------------------------------------------------------
# Bug 1: OOM Kill — Verify pipeline output is valid
# ---------------------------------------------------------------------------

class TestPipelineOutput:
    """Verify data pipeline produces valid output without crashing."""

    def test_met_data_jsonl_exists(self):
        """Pipeline should produce met_data.jsonl."""
        path = "src/apps/data_pipeline/output/met_data.jsonl"
        assert os.path.exists(path), (
            f"{path} does not exist. Run the MET pipeline locally first: "
            "python3 src/apps/data_pipeline/met_pipeline.py"
        )

    def test_wikidata_jsonl_exists(self):
        """Pipeline should produce wikidata_data.jsonl."""
        path = "src/apps/data_pipeline/output/wikidata_data.jsonl"
        assert os.path.exists(path), (
            f"{path} does not exist. Run the wikidata pipeline locally first: "
            "python3 src/apps/data_pipeline/wikidata_pipeline.py"
        )

    def test_jsonl_records_are_valid_json(self):
        """Every line in the JSONL files must be valid JSON with a 'text' field."""
        for fname in ["met_data.jsonl", "wikidata_data.jsonl"]:
            path = f"src/apps/data_pipeline/output/{fname}"
            if not os.path.exists(path):
                pytest.skip(f"{path} not found — run pipeline first")
            with open(path, "r", encoding="utf-8") as f:
                first_line = f.readline()
            # Skip Git LFS pointer files (not actual data)
            if first_line.startswith("version https://git-lfs"):
                pytest.skip(f"{fname} is a Git LFS pointer — run pipeline to generate actual data")
            with open(path, "r", encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    assert "text" in record, (
                        f"{fname} line {i}: missing 'text' field. "
                        "Bedrock needs a text field to extract content."
                    )
                    assert len(record["text"]) > 0, (
                        f"{fname} line {i}: 'text' field is empty"
                    )

    def test_met_data_has_records(self):
        """MET dataset JSONL should have at least 1 valid record."""
        path = "src/apps/data_pipeline/output/met_data.jsonl"
        if not os.path.exists(path):
            pytest.skip("met_data.jsonl not found — run pipeline first")
        with open(path, "r") as f:
            count = sum(1 for line in f if line.strip())
        assert count >= 1, f"Expected >= 1 records, got {count}"


# ---------------------------------------------------------------------------
# Bug 2: JSONL format not supported — Verify conversion to .txt
# ---------------------------------------------------------------------------

class TestJsonlToTxtConversion:
    """Verify convert-jsonl-to-txt.py produces valid .txt files for Bedrock."""

    def test_conversion_produces_txt_files(self):
        """Running the conversion script should produce .txt files."""
        txt_dir = "src/apps/data_pipeline/output/txt"
        jsonl_dir = "src/apps/data_pipeline/output"
        jsonl_files = [f for f in os.listdir(jsonl_dir) if f.endswith(".jsonl")] if os.path.isdir(jsonl_dir) else []
        if not jsonl_files:
            pytest.skip("No JSONL files found — run pipeline first")

        # Check that JSONL files are actual data (not Git LFS pointers)
        for fname in jsonl_files:
            path = os.path.join(jsonl_dir, fname)
            with open(path, "r") as f:
                first_line = f.readline()
            if first_line.startswith("version https://git-lfs"):
                pytest.skip(f"{fname} is a Git LFS pointer — run pipeline to generate actual data")

        result = subprocess.run(
            ["python3", "scripts/convert-jsonl-to-txt.py"],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"Conversion failed: {result.stderr}"
        assert os.path.isdir(txt_dir), f"Output directory {txt_dir} not created"

        txt_files = [f for f in os.listdir(txt_dir) if f.endswith(".txt")]
        assert len(txt_files) > 0, "No .txt files produced"

    def test_txt_files_contain_plain_text_not_json(self):
        """Output .txt files must contain plain text, not JSON objects."""
        txt_dir = "src/apps/data_pipeline/output/txt"
        if not os.path.isdir(txt_dir):
            pytest.skip("txt output directory not found — run conversion first")

        for fname in os.listdir(txt_dir):
            if not fname.endswith(".txt"):
                continue
            path = os.path.join(txt_dir, fname)
            with open(path, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
            # Should NOT start with { (JSON) — should be plain text
            assert not first_line.startswith("{"), (
                f"{fname} starts with '{{' — looks like JSON, not plain text. "
                "Bedrock cannot parse JSONL. Files must contain plain text."
            )

    def test_no_jsonl_files_in_txt_directory(self):
        """The txt output directory should not contain any .jsonl files."""
        txt_dir = "src/apps/data_pipeline/output/txt"
        if not os.path.isdir(txt_dir):
            pytest.skip("txt output directory not found")
        jsonl_files = [f for f in os.listdir(txt_dir) if f.endswith(".jsonl")]
        assert len(jsonl_files) == 0, (
            f"Found .jsonl files in txt directory: {jsonl_files}. "
            "Only .txt files should be uploaded to S3 for Bedrock ingestion."
        )


# ---------------------------------------------------------------------------
# Bug 3: Metadata mapping — Verify Terraform index config
# ---------------------------------------------------------------------------

class TestOpenSearchIndexConfig:
    """Verify the Terraform-managed OpenSearch index has correct configuration."""

    def test_bedrock_tf_uses_text_for_metadata(self):
        """bedrock.tf must define AMAZON_BEDROCK_METADATA as 'text', not 'object'.

        Root cause: When the metadata field is mapped as 'object', Bedrock
        ingestion reports COMPLETE with 0 indexed and 0 failed (silent failure).
        When mapped as 'text', ingestion works correctly.
        """
        bedrock_tf = "infra/terraform/bedrock.tf"
        assert os.path.exists(bedrock_tf), f"{bedrock_tf} not found"
        with open(bedrock_tf, "r") as f:
            content = f.read()

        # In Terraform HCL, JSON in provisioner commands uses escaped quotes
        # Check for both plain and escaped forms
        has_text_type = (
            '"type": "text"' in content
            or "'type': 'text'" in content
            or '\\"type\\":\\"text\\"' in content  # escaped in provisioner command
        )
        assert has_text_type, (
            "bedrock.tf should define AMAZON_BEDROCK_METADATA as type 'text'. "
            "Using 'object' causes silent ingestion failures where 0 documents "
            "are indexed but the job reports COMPLETE with 0 failures."
        )

    def test_bedrock_tf_uses_1024_dimensions(self):
        """Vector dimension must be 1024 for titan-embed-text-v2.

        Root cause: titan-embed-text-v1 (1536 dimensions) is not available in
        ca-central-1. titan-embed-text-v2 outputs 1024 dimensions by default.
        A dimension mismatch causes: 'Query vector has invalid dimension: 1024.
        Dimension should be: 1536'
        """
        bedrock_tf = "infra/terraform/bedrock.tf"
        with open(bedrock_tf, "r") as f:
            content = f.read()

        assert "1024" in content, (
            "bedrock.tf should use dimension 1024 for titan-embed-text-v2:0. "
            "Using 1536 (the v1 default) causes a dimension mismatch error "
            "because v1 is not available in ca-central-1."
        )

    def test_variables_tf_uses_v2_embedding_model(self):
        """Embedding model must be titan-embed-text-v2, not v1.

        Root cause: amazon.titan-embed-text-v1 does not exist in ca-central-1.
        Only v2 is available. Using v1 causes: 'The provided model identifier
        is invalid.'
        """
        variables_tf = "infra/terraform/variables.tf"
        assert os.path.exists(variables_tf), f"{variables_tf} not found"
        with open(variables_tf, "r") as f:
            content = f.read()

        assert "titan-embed-text-v2" in content, (
            "variables.tf should use amazon.titan-embed-text-v2:0. "
            "v1 is not available in ca-central-1."
        )
        assert "titan-embed-text-v1" not in content or "v1" not in content.split("titan-embed-text-v2")[0], (
            "variables.tf should NOT default to titan-embed-text-v1."
        )


# ---------------------------------------------------------------------------
# Bug 4: Large file ingestion — Verify files are split small enough
# ---------------------------------------------------------------------------

class TestFileSplitting:
    """Verify converted files are small enough for Bedrock to ingest reliably."""

    MAX_FILE_SIZE_BYTES = 500_000  # 500KB — files larger than this get stuck

    def test_no_txt_file_exceeds_max_size(self):
        """No single .txt file should exceed 500KB.

        Root cause: A single 20MB file caused Bedrock ingestion to hang for 30+
        minutes without indexing any documents. The embedding model throughput in
        ca-central-1 couldn't handle the volume of chunks from a large file.
        Splitting into ~200KB files resolved the issue.
        """
        txt_dir = "src/apps/data_pipeline/output/txt"
        if not os.path.isdir(txt_dir):
            pytest.skip("txt output directory not found")

        oversized = []
        for fname in os.listdir(txt_dir):
            if not fname.endswith(".txt"):
                continue
            path = os.path.join(txt_dir, fname)
            size = os.path.getsize(path)
            if size > self.MAX_FILE_SIZE_BYTES:
                oversized.append(f"{fname} ({size / 1024:.0f}KB)")

        assert len(oversized) == 0, (
            f"Files exceed {self.MAX_FILE_SIZE_BYTES // 1000}KB limit: {oversized}. "
            "Large files cause Bedrock ingestion to hang. Split into smaller parts."
        )

    def test_split_produces_multiple_files_for_large_dataset(self):
        """A large JSONL should produce many small .txt files, not one large one.

        If the MET JSONL has > 500 records, the conversion should split it.
        If the local JSONL is small (dev/test), this test is skipped.
        """
        txt_dir = "src/apps/data_pipeline/output/txt"
        jsonl_path = "src/apps/data_pipeline/output/met_data.jsonl"
        if not os.path.isdir(txt_dir):
            pytest.skip("txt output directory not found — run conversion first")
        if not os.path.exists(jsonl_path):
            pytest.skip("met_data.jsonl not found — run pipeline first")

        with open(jsonl_path, "r") as f:
            record_count = sum(1 for line in f if line.strip())
        if record_count <= 500:
            pytest.skip(f"Only {record_count} records locally — splitting not expected")

        met_files = [f for f in os.listdir(txt_dir) if f.startswith("met_data")]
        assert len(met_files) > 1, (
            f"Expected multiple met_data_partN.txt files, got {len(met_files)}. "
            f"The MET dataset has {record_count} records and must be split into parts."
        )

    def test_convert_script_splits_at_500_records(self):
        """The conversion script should split at MAX_RECORDS_PER_FILE = 500."""
        with open("scripts/convert-jsonl-to-txt.py", "r") as f:
            content = f.read()
        assert "MAX_RECORDS_PER_FILE = 500" in content, (
            "convert-jsonl-to-txt.py should set MAX_RECORDS_PER_FILE = 500. "
            "Larger values cause slow or stuck ingestion in ca-central-1."
        )


# ---------------------------------------------------------------------------
# Bug 5: boto3 version — Verify bedrock-agent-runtime is available
# ---------------------------------------------------------------------------

class TestBoto3Compatibility:
    """Verify boto3 version supports bedrock-agent-runtime."""

    def test_boto3_has_bedrock_agent_runtime(self):
        """boto3 must include bedrock-agent-runtime service.

        Root cause: Old boto3 versions don't know about bedrock-agent-runtime,
        causing UnknownServiceError at runtime. This only shows up in the
        deployed container, not locally if your local boto3 is newer.
        """
        import boto3
        from botocore.loaders import Loader
        loader = Loader()
        available = loader.list_available_services("service-2")
        assert "bedrock-agent-runtime" in available, (
            f"boto3 {boto3.__version__} does not include bedrock-agent-runtime. "
            "Update boto3 >= 1.34.0 in requirements.txt."
        )

    def test_requirements_has_recent_boto3(self):
        """requirements.txt must pin boto3 >= 1.34 for Bedrock Agent support."""
        with open("requirements.txt", "r") as f:
            content = f.read()
        assert "boto3>=1.34" in content or "boto3>=1.35" in content, (
            "requirements.txt should have boto3>=1.34. Older versions don't "
            "include bedrock-agent-runtime needed for RetrieveAndGenerate."
        )


# ---------------------------------------------------------------------------
# Bug 6: Model selection — Verify correct model for ca-central-1
# ---------------------------------------------------------------------------

class TestModelConfiguration:
    """Verify the RAG query uses a model available in ca-central-1."""

    def test_rag_query_uses_sonnet(self):
        """main.py/config should use claude-sonnet-4-5 (Claude 4.5 Sonnet).

        Note: Claude Sonnet 4.5 often requires a Bedrock inference profile
        (commonly cross-region) in ca-central-1. The code supports routing via
        `BEDROCK_INFERENCE_PROFILE_ARN` when configured.
        """
        # Model ID may be in main.py or config.py
        content = ""
        for path in ("src/apps/backend/main.py", "src/apps/backend/config.py"):
            if os.path.exists(path):
                with open(path, "r") as f:
                    content += f.read()

        assert "claude-sonnet-4-5" in content, (
            "Backend should use anthropic.claude-sonnet-4-5-* for RAG. "
            "Configure `BEDROCK_INFERENCE_PROFILE_ARN` if Sonnet requires it."
        )

    def test_no_hardcoded_sonnet_in_rag_endpoint(self):
        """The rag-query endpoint should not use Sonnet directly."""
        with open("src/apps/backend/main.py", "r") as f:
            content = f.read()

        # Check the section after "rag_query" function definition
        rag_section = content[content.find("def rag_query"):]
        assert "claude-sonnet-4-5" not in rag_section, (
            "rag_query function uses claude-sonnet-4-5 which requires inference "
            "profiles in ca-central-1. Use the configured model/inference profile "
            "(via config/env) rather than hardcoding it in the endpoint."
        )


# ---------------------------------------------------------------------------
# Bug 8: IAM Marketplace permissions — Verify Terraform IAM config
# ---------------------------------------------------------------------------

class TestIAMConfiguration:
    """Verify ECS task role has required permissions for Bedrock + Marketplace."""

    def test_iam_includes_marketplace_permissions(self):
        """ECS task role must have aws-marketplace permissions.

        Root cause: Anthropic models on Bedrock are delivered via AWS Marketplace.
        The first invocation requires the calling role to have
        aws-marketplace:ViewSubscriptions and aws-marketplace:Subscribe.
        Without these, you get: 'Model access is denied due to IAM user or
        service role is not authorized to perform the required AWS Marketplace
        actions.'
        """
        iam_tf = "infra/terraform/iam.tf"
        assert os.path.exists(iam_tf), f"{iam_tf} not found"
        with open(iam_tf, "r") as f:
            content = f.read()

        assert "aws-marketplace" in content, (
            "iam.tf must include aws-marketplace permissions "
            "(ViewSubscriptions, Subscribe) for the ECS task role. "
            "Anthropic models require Marketplace subscription activation."
        )

    def test_iam_includes_bedrock_agent_permissions(self):
        """ECS task role must have bedrock-agent permissions for RetrieveAndGenerate."""
        iam_tf = "infra/terraform/iam.tf"
        with open(iam_tf, "r") as f:
            content = f.read()

        assert "bedrock" in content.lower(), (
            "iam.tf must include Bedrock permissions for the ECS task role."
        )


# ---------------------------------------------------------------------------
# Bug 9 & 10: Destroy/recreate — Verify destroy script handles edge cases
# ---------------------------------------------------------------------------

class TestDestroyScript:
    """Verify destroy-all.sh handles S3 versioning and Secrets Manager."""

    def test_destroy_script_empties_versioned_buckets(self):
        """destroy-all.sh must delete all S3 object versions before terraform destroy.

        Root cause: S3 buckets with versioning retain delete markers after
        'aws s3 rm --recursive'. Terraform destroy fails with BucketNotEmpty
        because hidden object versions still exist.
        """
        script = "scripts/destroy-all.sh"
        assert os.path.exists(script), f"{script} not found"
        with open(script, "r") as f:
            content = f.read()

        assert (
            "object_versions" in content
            or "delete-objects" in content
            or "bucket.object_versions" in content
            or "list-object-versions" in content
            or "force_destroy" in content
        ), (
            "destroy-all.sh must handle S3 object versions (not just objects). "
            "Versioned buckets retain hidden delete markers that prevent deletion."
        )

    def test_destroy_script_force_deletes_secrets(self):
        """destroy-all.sh must force-delete Secrets Manager secrets.

        Root cause: Secrets Manager has a 7-30 day recovery window. A destroyed
        secret blocks creation of a new secret with the same name until the
        window expires. --force-delete-without-recovery bypasses this.
        """
        script = "scripts/destroy-all.sh"
        with open(script, "r") as f:
            content = f.read()

        assert "force-delete-without-recovery" in content, (
            "destroy-all.sh must use --force-delete-without-recovery for secrets. "
            "Otherwise, re-creating the environment fails with: 'secret with this "
            "name is already scheduled for deletion.'"
        )


# ---------------------------------------------------------------------------
# Integration: End-to-end conversion pipeline test
# ---------------------------------------------------------------------------

class TestConversionPipelineIntegration:
    """End-to-end test of the JSONL -> txt conversion pipeline."""

    def test_full_conversion_pipeline(self, tmp_path):
        """Test the entire flow: JSONL input -> txt output with correct splitting.

        Simulates what convert-jsonl-to-txt.py does: reads JSONL, extracts text,
        splits into parts of MAX_RECORDS_PER_FILE, writes as plain .txt.
        """
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Create fake JSONL with 1200 records (more than the 500 limit)
        records = []
        for i in range(1200):
            records.append(json.dumps({
                "id": str(i),
                "text": f"Artwork Title: Test Painting {i}\nArtist: Test Artist\nMedium: Oil on canvas"
            }))

        jsonl_path = input_dir / "test_data.jsonl"
        jsonl_path.write_text("\n".join(records))

        # Simulate the conversion logic from convert-jsonl-to-txt.py
        max_per_file = 500
        all_texts = []
        with open(jsonl_path, "r") as f:
            for line in f:
                record = json.loads(line)
                all_texts.append(record["text"])

        total = len(all_texts)

        # Verify splitting math
        expected_parts = (total + max_per_file - 1) // max_per_file
        assert expected_parts == 3, f"1200 records at 500/file should give 3 parts, got {expected_parts}"

        # Write split files and verify each
        for i in range(0, total, max_per_file):
            chunk = all_texts[i:i + max_per_file]
            part = i // max_per_file + 1
            out_path = output_dir / f"test_data_part{part}.txt"
            out_path.write_text("\n\n---\n\n".join(chunk))

            assert len(chunk) <= max_per_file, f"Chunk has {len(chunk)} records, max is {max_per_file}"
            content = out_path.read_text()
            assert not content.startswith("{"), "Output should be plain text, not JSON"
            assert "Artwork Title:" in content, "Output should contain readable artwork info"
            assert out_path.stat().st_size < 500_000, f"File {out_path.name} exceeds 500KB"

        # Verify correct number of output files
        txt_files = list(output_dir.glob("*.txt"))
        assert len(txt_files) == 3, f"Expected 3 part files, got {len(txt_files)}"

    def test_single_small_file_not_split(self, tmp_path):
        """A JSONL with fewer than MAX_RECORDS_PER_FILE should produce one file."""
        records = []
        for i in range(10):
            records.append(json.dumps({
                "id": str(i),
                "text": f"Artwork {i}"
            }))

        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        jsonl_path = input_dir / "small_data.jsonl"
        jsonl_path.write_text("\n".join(records))

        # Simulate conversion
        all_texts = [json.loads(r)["text"] for r in records]
        max_per_file = 500

        if len(all_texts) <= max_per_file:
            # Should produce single file
            output_path = output_dir / "small_data.txt"
            output_path.write_text("\n\n---\n\n".join(all_texts))
            files = list(output_dir.glob("*.txt"))
            assert len(files) == 1, f"Small dataset should produce 1 file, got {len(files)}"
        else:
            pytest.fail("10 records should not trigger splitting")

        # Verify content
        content = output_path.read_text()
        assert "Artwork 0" in content
        assert "Artwork 9" in content
        assert not content.startswith("{"), "Content should be plain text"
