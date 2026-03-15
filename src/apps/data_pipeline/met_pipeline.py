import pandas as pd
import json
import os
from datasets import load_dataset

INPUT_FILE = "metmuseum/openaccess"
# INPUT_FILE = "preprocessing/METObjects.csv"
OUTPUT_FILE = "src/apps/data_pipeline/output/met_data.jsonl"

ARTIST_COLUMNS = [
    "Artist Display Name",
    "Artist Display Bio",
    "Artist Nationality",
    "Artist Begin Date",
    "Artist End Date",
    "Artist Gender"
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
    "Classification"
]

def load_and_filter_data(filepath):
    print("Loading MET dataset...")
    ds = load_dataset(filepath, split="train")
    df = ds.to_pandas()
    # df = pd.read_csv(filepath, low_memory=False, dtype=str)
    
    df = df.replace("", pd.NA)

    df = df[ARTIST_COLUMNS + ARTWORK_COLUMNS].copy()

    return df

def build_rag_document(row):
    return f"""
Artwork Title: {row.get('Title') or 'Unknown'}
Object Type: {row.get('Object Name') or 'Unknown'}
Classification: {row.get('Classification') or 'Unknown'}

Artist: {row.get('Artist Display Name') or 'Unknown'}
Nationality: {row.get('Artist Nationality') or 'Unknown'}
Lifespan: {row.get('Artist Begin Date') or 'Unknown'}–{row.get('Artist End Date') or 'Unknown'}

Cultural Context: {row.get('Culture') or 'Unknown'}
Period: {row.get('Period') or 'Unknown'}
Date Range: {row.get('Object Begin Date') or 'Unknown'}–{row.get('Object End Date') or 'Unknown'}

Medium: {row.get('Medium') or 'Unknown'}
Dimensions: {row.get('Dimensions') or 'Unknown'}

Credit Line: {row.get('Credit Line') or 'Unknown'}
""".strip()

def transform_to_rag(df):
    print("Transforming rows into RAG documents...")
    df = df.copy()
    df["rag_text"] = df.apply(build_rag_document, axis=1)

    # Add stable ID for traceability
    df["doc_id"] = df.index.astype(str)

    return df

def export_jsonl(df, output_path):
    print("Exporting JSONL for Bedrock ingestion...")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for _, row in df.iterrows():
            record = {
                "id": row["doc_id"],
                "text": row["rag_text"]
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

def main():
    df = load_and_filter_data(INPUT_FILE)
    df = transform_to_rag(df)
    export_jsonl(df, OUTPUT_FILE)

    print("Pipeline complete.")


if __name__ == "__main__":
    main()
