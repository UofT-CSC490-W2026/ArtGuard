"""Convert JSONL pipeline output to .txt files for Bedrock Knowledge Base ingestion.

Splits large files into parts of MAX_RECORDS_PER_FILE to avoid slow/stuck ingestion.
"""
import json
import os

INPUT_DIR = "src/apps/data_pipeline/output"
OUTPUT_DIR = "src/apps/data_pipeline/output/txt"
MAX_RECORDS_PER_FILE = 500


def convert_jsonl(input_path, base_name):
    """Convert a JSONL file into one or more .txt files."""
    records = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            records.append(record["text"])

    total = len(records)
    file_count = 0

    if total <= MAX_RECORDS_PER_FILE:
        output_path = os.path.join(OUTPUT_DIR, f"{base_name}.txt")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n\n---\n\n".join(records))
        file_count = 1
    else:
        for i in range(0, total, MAX_RECORDS_PER_FILE):
            chunk = records[i:i + MAX_RECORDS_PER_FILE]
            part = i // MAX_RECORDS_PER_FILE + 1
            output_path = os.path.join(OUTPUT_DIR, f"{base_name}_part{part}.txt")
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("\n\n---\n\n".join(chunk))
            file_count += 1

    print(f"  {input_path} -> {file_count} file(s) ({total} records)")
    return file_count


def main():
    # Clean previous output
    if os.path.exists(OUTPUT_DIR):
        for f in os.listdir(OUTPUT_DIR):
            os.remove(os.path.join(OUTPUT_DIR, f))
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    total_files = 0
    for fname in sorted(os.listdir(INPUT_DIR)):
        if not fname.endswith(".jsonl"):
            continue
        input_path = os.path.join(INPUT_DIR, fname)
        base_name = fname.replace(".jsonl", "")
        total_files += convert_jsonl(input_path, base_name)

    print(f"\nConverted to {total_files} file(s) in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
