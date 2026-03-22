"""Metropolitan Museum of Art data pipeline for RAG knowledge base.

Downloads the MET's open-access CSV catalogue, filters for records that
have an artist name, and converts each into a structured text document
suitable for ingestion into the Bedrock Knowledge Base.

Output is a JSONL file where each line is ``{"id": "...", "text": "..."}``.

Usage::

    python -m src.apps.data_pipeline.met_pipeline
"""

import csv
import json
import os
import shutil
import tempfile
import urllib.request

OUTPUT_FILE = "src/apps/data_pipeline/output/met_data.jsonl"
MAX_RECORDS = int(os.environ.get("MET_MAX_RECORDS", "50000"))

# Direct CSV URL from the MET's GitHub repo (no HuggingFace dependency).
CSV_URL = "https://github.com/metmuseum/openaccess/raw/master/MetObjects.csv"

ARTIST_COLUMNS = [
    "Artist Display Name",
    "Artist Display Bio",
    "Artist Nationality",
    "Artist Begin Date",
    "Artist End Date",
    "Artist Gender",
]

ARTWORK_COLUMNS = [
    "Object Name",
    "Title",
    "Culture",
    "Period",
    "Object Date",
    "Object Begin Date",
    "Object End Date",
    "Medium",
    "Dimensions",
    "Credit Line",
    "City",
    "Country",
    "Region",
    "Classification",
]

COLUMNS = ARTIST_COLUMNS + ARTWORK_COLUMNS


def build_rag_document(row: dict) -> str:
    """Format a single MET catalogue row as a structured text document for RAG.

    Extracts artist and artwork metadata from the row and formats them
    into a human-readable text block.

    >>> row = {"Title": "Starry Night", "Artist Display Name": "Van Gogh",
    ...        "Classification": "Paintings"}
    >>> "Artwork Title: Starry Night" in build_rag_document(row)
    True

    Args:
        row: A dict from the MET CSV with column names as keys.

    Returns:
        A multi-line string with labelled fields for artist and artwork metadata.
    """
    return f"""
Artwork Title: {row.get('Title') or 'Unknown'}
Object Type: {row.get('Object Name') or 'Unknown'}
Classification: {row.get('Classification') or 'Unknown'}

Artist: {row.get('Artist Display Name') or 'Unknown'}
Nationality: {row.get('Artist Nationality') or 'Unknown'}
Lifespan: {row.get('Artist Begin Date') or 'Unknown'}\u2013{row.get('Artist End Date') or 'Unknown'}

Cultural Context: {row.get('Culture') or 'Unknown'}
Period: {row.get('Period') or 'Unknown'}
Date Range: {row.get('Object Begin Date') or 'Unknown'}\u2013{row.get('Object End Date') or 'Unknown'}

Medium: {row.get('Medium') or 'Unknown'}
Dimensions: {row.get('Dimensions') or 'Unknown'}

Credit Line: {row.get('Credit Line') or 'Unknown'}
""".strip()


def main() -> None:
    """Download the MET CSV, filter for records with artists, and write JSONL output.

    Downloads the ~250 MB CSV to a temp file to avoid buffering in memory,
    then streams through it and writes structured text documents to the
    output JSONL file. Stops after MAX_RECORDS documents.
    """
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    tmp_csv = os.path.join(tempfile.gettempdir(), "MetObjects.csv")
    print("Downloading MET CSV to disk...", flush=True)
    with urllib.request.urlopen(CSV_URL) as response:
        with open(tmp_csv, "wb") as tmp:
            shutil.copyfileobj(response, tmp, length=1024 * 1024)
    print("Download complete. Processing...", flush=True)

    count = 0
    with open(tmp_csv, "r", encoding="utf-8") as csvfile, \
         open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        reader = csv.DictReader(csvfile)
        for i, row in enumerate(reader):
            artist = row.get("Artist Display Name")
            if not artist or not str(artist).strip():
                continue
            filtered = {col: row.get(col) for col in COLUMNS}
            text = build_rag_document(filtered)
            record = {"id": str(i), "text": text}
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
            if count % 10000 == 0:
                print(f"  Processed {count} records...", flush=True)
            if count >= MAX_RECORDS:
                print(f"  Reached limit of {MAX_RECORDS} records.", flush=True)
                break

    os.remove(tmp_csv)
    print(f"Pipeline complete. Wrote {count} records to {OUTPUT_FILE}", flush=True)


if __name__ == "__main__":
    main()
