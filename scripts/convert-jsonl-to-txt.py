"""Convert JSONL pipeline output to .txt files for Bedrock Knowledge Base ingestion.

Splits large files into parts of MAX_RECORDS_PER_FILE to avoid slow/stuck ingestion.

NOTE: This script only needs to be run if the .txt files in
src/apps/data_pipeline/output/txt/ are missing or out of date.
If the .txt files already exist and match the current .jsonl data, you can skip this step.
"""

import json
import os

INPUT_DIR = "src/apps/data_pipeline/output"
OUTPUT_DIR = "src/apps/data_pipeline/output/txt"
MAX_RECORDS_PER_FILE = 500


def convert_jsonl(input_path: str, base_name: str) -> int:
    """Convert a single JSONL file into one or more .txt files.

    Each record's "text" field is extracted and joined with '---' separators.
    If the record count exceeds MAX_RECORDS_PER_FILE, the output is split
    into numbered parts (e.g. base_name_part1.txt, base_name_part2.txt).

    Args:
        input_path: Path to the source .jsonl file.
        base_name: Stem name used for the output .txt file(s).

    Returns:
        The number of .txt files written.
    """
    records = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
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
            chunk = records[i : i + MAX_RECORDS_PER_FILE]
            part = i // MAX_RECORDS_PER_FILE + 1
            output_path = os.path.join(OUTPUT_DIR, f"{base_name}_part{part}.txt")
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("\n\n---\n\n".join(chunk))
            file_count += 1

    print(f"  {input_path} -> {file_count} file(s) ({total} records)")
    return file_count


def main() -> None:
    """Convert all .jsonl files in INPUT_DIR to .txt files in OUTPUT_DIR.

    Clears any existing .txt files in OUTPUT_DIR before converting to ensure
    a clean output directory.
    """
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
