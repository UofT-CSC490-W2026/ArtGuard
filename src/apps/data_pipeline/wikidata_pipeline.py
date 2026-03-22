"""Wikidata SPARQL pipeline for RAG knowledge base.

Queries Wikidata for biographical and artistic metadata about known artists
relevant to the ArtGuard forgery detection system, and writes the results
as structured text documents to a JSONL file for Bedrock Knowledge Base
ingestion.

Usage::

    python -m src.apps.data_pipeline.wikidata_pipeline
"""

import json
import os
import time
from typing import Optional

import requests

OUTPUT_FILE = "src/apps/data_pipeline/output/wikidata_data.jsonl"

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

# QIDs for artists relevant to art authentication research.
ARTISTS = {
    "Vincent van Gogh": "Q5582",
    "Johannes Vermeer": "Q41264",
    "Frans Hals": "Q167654",
    "Gerard ter Borch": "Q346808",
    "Otto Wacker": "Q115015",
    "Han van Meegeren": "Q436161",
}


def build_query(qid: str) -> str:
    """Build a SPARQL query to fetch artist metadata from Wikidata.

    Queries biographical data (birth, death, citizenship), artistic
    attributes (movements, genres, occupations, fields), influences,
    and notable works for the given Wikidata QID.

    >>> query = build_query("Q5582")
    >>> "wd:Q5582" in query
    True

    Args:
        qid: A Wikidata entity QID (e.g. ``"Q5582"`` for Van Gogh).

    Returns:
        A SPARQL query string.
    """
    return f"""
    SELECT ?artistLabel ?description ?birth ?death ?citizenshipLabel
            ?movementLabel ?genreLabel ?occupationLabel
            ?influencedByLabel ?notableWorkLabel ?fieldLabel
    WHERE {{
        VALUES ?artist {{ wd:{qid} }}

        OPTIONAL {{ ?artist wdt:P569 ?birth. }}
        OPTIONAL {{ ?artist wdt:P570 ?death. }}
        OPTIONAL {{ ?artist wdt:P27 ?citizenship. }}
        OPTIONAL {{ ?artist schema:description ?description.
                    FILTER (LANG(?description) = "en") }}

        OPTIONAL {{ ?artist wdt:P135 ?movement. }}
        OPTIONAL {{ ?artist wdt:P136 ?genre. }}
        OPTIONAL {{ ?artist wdt:P106 ?occupation. }}
        OPTIONAL {{ ?artist wdt:P737 ?influencedBy. }}
        OPTIONAL {{ ?artist wdt:P800 ?notableWork. }}
        OPTIONAL {{ ?artist wdt:P101 ?field. }}

        SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    LIMIT 500
    """


def query_wikidata(query: str, retries: int = 3) -> Optional[dict]:
    """Execute a SPARQL query against the Wikidata endpoint with retries.

    Sends a GET request with the query as a parameter and expects a
    JSON SPARQL results response. Retries up to ``retries`` times on
    failure with a 2-second delay between attempts.

    Args:
        query:   A SPARQL query string.
        retries: Maximum number of attempts (default 3).

    Returns:
        The parsed JSON response dict, or None if all attempts fail.
    """
    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": "ArtGuardBot/1.0 (your_email@example.com)",
    }

    for attempt in range(retries):
        try:
            response = requests.get(
                SPARQL_ENDPOINT,
                params={"query": query},
                headers=headers,
                timeout=60,
            )
            response.raise_for_status()

            if "application/sparql-results+json" not in response.headers.get("Content-Type", ""):
                print("Unexpected response type:")
                print(response.text[:500])
                return None

            return response.json()

        except Exception as e:
            print(f"Error querying Wikidata (attempt {attempt + 1}): {e}")
            time.sleep(2)

    print("Failed after retries.")
    return None


def build_rag_document(result: dict) -> Optional[str]:
    """Convert a Wikidata SPARQL result into a structured text document for RAG.

    Extracts single-value fields (name, description, birth/death dates,
    citizenship) and multi-value fields (movements, genres, occupations,
    influences, notable works) across all result bindings.

    >>> result = {"results": {"bindings": [{"artistLabel": {"value": "Van Gogh"}}]}}
    >>> doc = build_rag_document(result)
    >>> "Artist: Van Gogh" in doc
    True

    Args:
        result: Parsed JSON response from a Wikidata SPARQL query.

    Returns:
        A multi-line structured text string, or None if no bindings are present.
    """
    bindings = result["results"]["bindings"]

    if not bindings:
        return None

    def get_value(binding: dict, field: str) -> Optional[str]:
        """Safely extract a value from a SPARQL binding."""
        return binding[field]["value"] if field in binding else None

    first = bindings[0]

    artist = get_value(first, "artistLabel") or "Unknown"
    description = get_value(first, "description") or "Unknown"
    birth = get_value(first, "birth") or "Unknown"
    death = get_value(first, "death") or "Unknown"
    citizenship = get_value(first, "citizenshipLabel") or "Unknown"

    # Collect multi-value fields across all result rows.
    movements: set[str] = set()
    genres: set[str] = set()
    occupations: set[str] = set()
    fields: set[str] = set()
    influenced_by: set[str] = set()
    notable_works: set[str] = set()

    for b in bindings:
        if get_value(b, "movementLabel"):
            movements.add(get_value(b, "movementLabel"))
        if get_value(b, "genreLabel"):
            genres.add(get_value(b, "genreLabel"))
        if get_value(b, "occupationLabel"):
            occupations.add(get_value(b, "occupationLabel"))
        if get_value(b, "fieldLabel"):
            fields.add(get_value(b, "fieldLabel"))
        if get_value(b, "influencedByLabel"):
            influenced_by.add(get_value(b, "influencedByLabel"))
        if get_value(b, "notableWorkLabel"):
            notable_works.add(get_value(b, "notableWorkLabel"))

    return f"""
Artist: {artist}
Description: {description}

Born: {birth}
Died: {death}
Citizenship: {citizenship}

Movements: {", ".join(movements) or "Unknown"}
Genres: {", ".join(genres) or "Unknown"}
Occupations: {", ".join(occupations) or "Unknown"}
Fields: {", ".join(fields) or "Unknown"}

Influenced By: {", ".join(influenced_by) or "Unknown"}
Notable Works: {", ".join(notable_works) or "Unknown"}
""".strip()


def export_jsonl(records: list[dict], output_path: str) -> None:
    """Write a list of dicts as a JSONL file (one JSON object per line).

    Args:
        records:     List of dicts to serialise.
        output_path: File path to write to (parent dirs created if needed).
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    """Query Wikidata for each artist and write RAG documents to JSONL output."""
    documents: list[dict] = []

    for name, qid in ARTISTS.items():
        print(f"Querying {name}...")

        query = build_query(qid)
        result = query_wikidata(query)
        rag_text = build_rag_document(result)

        if rag_text:
            documents.append({"id": qid, "text": rag_text})

    export_jsonl(documents, OUTPUT_FILE)
    print("Wikidata pipeline complete.")


if __name__ == "__main__":
    main()
