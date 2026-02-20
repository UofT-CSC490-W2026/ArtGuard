import requests
import json
import os
import time

OUTPUT_FILE = "output/wikidata_data.jsonl"

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

# QIDs for your artists
ARTISTS = {
  "Vincent van Gogh": "Q5582",
  "Johannes Vermeer": "Q41264",
  "Frans Hals": "Q167654",
  "Gerard ter Borch": "Q346808",
  "Otto Wacker": "Q115015",
  "Han van Meegeren": "Q436161"
}

def build_query(qid):
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

def query_wikidata(query, retries=3):
  headers = {
    "Accept": "application/sparql-results+json",
    "User-Agent": "ArtGuardBot/1.0 (your_email@example.com)"
  }

  for attempt in range(retries):
    try:
      response = requests.get(
        SPARQL_ENDPOINT,
        params={"query": query},
        headers=headers,
        timeout=60
      )

      response.raise_for_status()

      # Ensure we actually received JSON
      if "application/sparql-results+json" not in response.headers.get("Content-Type", ""):
        print("Unexpected response type:")
        print(response.text[:500])
        return None

      return response.json()

    except Exception as e:
      print(f"Error querying Wikidata (attempt {attempt+1}): {e}")
      time.sleep(2)

  print("Failed after retries.")
  return None


def build_rag_document(result):
  bindings = result["results"]["bindings"]

  if not bindings:
    return None

  # Helper to safely extract value
  def get_value(binding, field):
    return binding[field]["value"] if field in binding else None

  # Single-value fields (same across rows)
  first = bindings[0]

  artist = get_value(first, "artistLabel") or "Unknown"
  description = get_value(first, "description") or "Unknown"
  birth = get_value(first, "birth") or "Unknown"
  death = get_value(first, "death") or "Unknown"
  citizenship = get_value(first, "citizenshipLabel") or "Unknown"

  # Multi-value fields (collect across rows)
  movements = set()
  genres = set()
  occupations = set()
  fields = set()
  influenced_by = set()
  notable_works = set()

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


def export_jsonl(records, output_path):
  os.makedirs(os.path.dirname(output_path), exist_ok=True)

  with open(output_path, "w", encoding="utf-8") as f:
    for record in records:
      f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main():
  documents = []

  for name, qid in ARTISTS.items():
    print(f"Querying {name}...")

    query = build_query(qid)
    result = query_wikidata(query)
    rag_text = build_rag_document(result)

    if rag_text:
      documents.append({
        "id": qid,
        "text": rag_text
      })

  export_jsonl(documents, OUTPUT_FILE)
  print("Wikidata pipeline complete.")


if __name__ == "__main__":
  main()
