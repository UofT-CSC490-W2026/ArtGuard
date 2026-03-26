import requests
import json
import time

SPARQL_URL = "https://query.wikidata.org/sparql"
HEADERS = {
    "Accept": "application/sparql-results+json",
    "User-Agent": "VanGoghScraper/1.0 (akshayad0301@gmail.com)"
}

def sparql(query):
    r = requests.get(SPARQL_URL, params={"query": query}, headers=HEADERS)
    r.raise_for_status()
    return r.json()["results"]["bindings"]

# ── Phase 1: all paintings in one call ───────────────────────────────────────
print("Fetching all paintings...")

PAINTINGS_QUERY = """
SELECT ?painting ?paintingLabel ?date ?collectionLabel
       ?imageUrl ?height ?width ?materialLabel ?movementLabel WHERE {
  ?painting wdt:P31 wd:Q3305213 ;
            wdt:P170 wd:Q5582 .
  OPTIONAL { ?painting wdt:P571 ?date . }
  OPTIONAL { ?painting wdt:P195 ?collection . }
  OPTIONAL { ?painting wdt:P18  ?imageUrl . }
  OPTIONAL { ?painting wdt:P2048 ?height . }
  OPTIONAL { ?painting wdt:P2049 ?width . }
  OPTIONAL { ?painting wdt:P186 ?material . }
  OPTIONAL { ?painting wdt:P135 ?movement . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
ORDER BY ?date
"""

rows = sparql(PAINTINGS_QUERY)
paintings = {}
for row in rows:
    qid = row["painting"]["value"].split("/")[-1]
    paintings[qid] = {
        "title":      row.get("paintingLabel", {}).get("value", "Unknown"),
        "wikidata_id": qid,
        "date":       row.get("date", {}).get("value", ""),
        "collection": row.get("collectionLabel", {}).get("value", ""),
        "image_url":  row.get("imageUrl", {}).get("value", ""),
        "height_cm":  row.get("height", {}).get("value", ""),
        "width_cm":   row.get("width", {}).get("value", ""),
        "material":   row.get("materialLabel", {}).get("value", ""),
        "movement":   row.get("movementLabel", {}).get("value", ""),
        "provenance": []
    }

print(f"Found {len(paintings)} paintings")

# ── Phase 2: provenance per painting ─────────────────────────────────────────
PROV_TEMPLATE = """
SELECT ?ownerLabel ?startDate ?endDate ?methodLabel WHERE {{
  wd:{qid} p:P127 ?stmt .
  ?stmt ps:P127 ?owner .
  OPTIONAL {{ ?stmt pq:P580 ?startDate . }}
  OPTIONAL {{ ?stmt pq:P582 ?endDate . }}
  OPTIONAL {{ ?stmt pq:P1039 ?method . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
"""

total = len(paintings)
for i, (qid, painting) in enumerate(paintings.items()):
    print(f"  [{i+1}/{total}] {painting['title'][:50]}", end="\r")
    try:
        rows = sparql(PROV_TEMPLATE.format(qid=qid))
        painting["provenance"] = [
            {
                "owner":      row.get("ownerLabel", {}).get("value", ""),
                "start_date": row.get("startDate", {}).get("value", ""),
                "end_date":   row.get("endDate", {}).get("value", ""),
                "method":     row.get("methodLabel", {}).get("value", ""),
            }
            for row in rows
        ]
    except Exception as e:
        print(f"\n  Warning: failed for {qid}: {e}")
    time.sleep(0.5)  # be polite to Wikidata's servers

# ── Save ──────────────────────────────────────────────────────────────────────
output = list(paintings.values())
with open("van_gogh_paintings.json", "w") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"\nDone. Saved {len(output)} paintings.")