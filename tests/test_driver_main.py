"""Tests for driver.main() and met_pipeline.main() — full pipeline runs."""

import json
import os
from io import BytesIO
from unittest.mock import patch

from PIL import Image


class TestDriverMain:
    """Tests for the driver.main() entry point."""

    def test_processes_images_end_to_end(self, s3, dynamodb, monkeypatch):
        """Integration: upload an image to unprocessed, run main(), verify patches."""
        monkeypatch.setenv("S3_IMAGES_RAW_BUCKET", "test-raw-bucket")
        monkeypatch.setenv("S3_IMAGES_PROCESSED_BUCKET", "test-processed-bucket")
        monkeypatch.setenv("DDB_IMAGES_TABLE", "test-images")
        monkeypatch.setenv("DDB_PATCHES_TABLE", "test-patches")
        monkeypatch.setenv("DDB_RUNS_TABLE", "test-runs")

        # Upload a test image
        img = Image.new("RGB", (600, 600), color="green")
        buf = BytesIO()
        img.save(buf, format="JPEG")
        s3.put_object(
            Bucket="test-raw-bucket",
            Key="training/unprocessed/img-001/test.jpg",
            Body=buf.getvalue(),
        )

        with patch("sys.argv", ["driver", "--run_id", "test-run-1"]):
            from src.apps.data_pipeline.driver import main
            main()

        # Verify run record was created
        runs_table = dynamodb.Table("test-runs")
        resp = runs_table.get_item(Key={"run_id": "test-run-1"})
        assert resp["Item"]["status"] in ("completed", "completed_with_errors")

    def test_handles_empty_bucket(self, s3, dynamodb, monkeypatch):
        """Main should complete with 0 images and 0 errors."""
        monkeypatch.setenv("S3_IMAGES_RAW_BUCKET", "test-raw-bucket")
        monkeypatch.setenv("S3_IMAGES_PROCESSED_BUCKET", "test-processed-bucket")
        monkeypatch.setenv("DDB_IMAGES_TABLE", "test-images")
        monkeypatch.setenv("DDB_PATCHES_TABLE", "test-patches")
        monkeypatch.setenv("DDB_RUNS_TABLE", "test-runs")

        with patch("sys.argv", ["driver", "--run_id", "empty-run"]):
            from src.apps.data_pipeline.driver import main
            main()

        runs_table = dynamodb.Table("test-runs")
        resp = runs_table.get_item(Key={"run_id": "empty-run"})
        assert resp["Item"]["status"] == "completed"


class TestMetPipelineMain:
    """Tests for met_pipeline.main() with mocked download."""

    def test_processes_csv_data(self, tmp_path, monkeypatch):
        """Test the pipeline with a minimal CSV fixture."""
        import csv
        from contextlib import contextmanager

        # Use separate subdirs for source CSV and temp download target to
        # avoid copyfileobj overwriting the source file with itself.
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()

        csv_path = str(src_dir / "MetObjects.csv")
        fieldnames = [
            "Artist Display Name", "Artist Display Bio", "Artist Nationality",
            "Artist Begin Date", "Artist End Date", "Artist Gender",
            "Object Name", "Title", "Culture", "Period",
            "Object Date", "Object Begin Date", "Object End Date",
            "Medium", "Dimensions", "Credit Line", "City", "Country",
            "Region", "Classification",
        ]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow({
                "Artist Display Name": "Claude Monet",
                "Title": "Water Lilies",
                "Classification": "Paintings",
                "Medium": "Oil on canvas",
                "Artist Nationality": "French",
            })
            writer.writerow({
                "Artist Display Name": "",  # Should be skipped (no artist)
                "Title": "Unknown Object",
            })
            writer.writerow({
                "Artist Display Name": "Vincent van Gogh",
                "Title": "Starry Night",
                "Classification": "Paintings",
            })

        output_file = str(tmp_path / "output.jsonl")
        monkeypatch.setattr(
            "src.apps.data_pipeline.met_pipeline.OUTPUT_FILE",
            output_file,
        )

        # Mock urllib.request.urlopen to return a context manager over our local CSV
        @contextmanager
        def mock_urlopen(url):
            yield open(csv_path, "rb")

        monkeypatch.setattr(
            "src.apps.data_pipeline.met_pipeline.urllib.request.urlopen",
            mock_urlopen,
        )
        # Point tempfile to a DIFFERENT dir so copyfileobj doesn't clobber the source
        monkeypatch.setattr(
            "tempfile.gettempdir",
            lambda: str(temp_dir),
        )

        from src.apps.data_pipeline.met_pipeline import main
        main()

        # Verify output
        assert os.path.exists(output_file)
        with open(output_file, "r") as f:
            lines = f.readlines()
        assert len(lines) == 2  # Monet + Van Gogh (empty artist skipped)

        record = json.loads(lines[0])
        assert "text" in record
        assert "Monet" in record["text"] or "Water Lilies" in record["text"]
