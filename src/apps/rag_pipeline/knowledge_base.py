"""
Bedrock Knowledge Base helper.

This script connects to your configured Bedrock Knowledge Base (set
`KNOWLEDGE_BASE_ID`) and prints the top N most relevant retrieved chunks.

It intentionally focuses on *retrievedReferences* from the Bedrock response,
rather than the generated answer text.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from typing import Any, Optional

import boto3

from src.apps.backend.config import get_region


@dataclass(frozen=True)
class RetrievedChunk:
    rank: int
    s3_uri: str
    snippet: str


def _require_knowledge_base_id() -> str:
    kb_id = os.getenv("KNOWLEDGE_BASE_ID", "").strip()
    if not kb_id:
        raise EnvironmentError(
            "KNOWLEDGE_BASE_ID is not set. Export it before running, e.g.:\n"
            "  export KNOWLEDGE_BASE_ID=$(terraform -chdir=infra/terraform output -raw knowledge_base_id)"
        )
    return kb_id


def _clip(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return text
    return text if len(text) <= max_chars else text[:max_chars].rstrip() + "..."


def retrieve_top_chunks(
    query: str,
    *,
    top_k: int = 7,
    candidate_k: Optional[int] = None,
    snippet_chars: int = 400,
    search_type: str = "",
    prefer_s3_uri_substring: str = "",
) -> list[RetrievedChunk]:
    """Retrieve top chunks for the given query.

    Bedrock's `retrieve_and_generate` can sometimes return empty
    `citations[*].retrievedReferences` (boto3/SDK behavior). To make this tool
    reliable, we call the dedicated `bedrock-agent-runtime.retrieve` API,
    which directly returns `retrievalResults`.
    """
    kb_id = _require_knowledge_base_id()
    region = get_region()

    # Pull more than top_k so we can dedupe and (optionally) prefer a document.
    fetch_k = max(1, int(candidate_k or max(top_k, 30)))

    bedrock = boto3.client("bedrock-agent-runtime", region_name=region)
    vector_cfg: dict[str, Any] = {"numberOfResults": fetch_k}
    if search_type:
        # Valid values are set by Bedrock; we keep this as a passthrough string.
        vector_cfg["overrideSearchType"] = search_type

    resp: dict[str, Any] = bedrock.retrieve(
        knowledgeBaseId=kb_id,
        retrievalQuery={"text": query},
        retrievalConfiguration={
            "vectorSearchConfiguration": {
                **vector_cfg,
            }
        },
    )

    references: list[dict[str, Any]] = resp.get("retrievalResults", []) or []

    # Deduplicate while preserving order (Bedrock can sometimes return duplicates).
    seen: set[str] = set()
    chunks: list[RetrievedChunk] = []
    rank = 1
    for ref in references:
        loc = ref.get("location", {}) or {}
        s3_uri = ((loc.get("s3Location") or {}).get("uri")) or ""

        content = ref.get("content", {}) or {}
        snippet = content.get("text", "") or ""
        snippet = _clip(snippet.strip(), snippet_chars)

        dedupe_key = f"{s3_uri}|{snippet}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        chunks.append(RetrievedChunk(rank=rank, s3_uri=s3_uri, snippet=snippet))
        rank += 1
        if len(chunks) >= top_k:
            break

    if prefer_s3_uri_substring:
        needle = prefer_s3_uri_substring.strip()
        if needle:
            chunks = sorted(
                chunks,
                key=lambda c: (needle not in (c.s3_uri or "")),
            )
            # Re-rank numbers after reordering.
            chunks = [
                RetrievedChunk(rank=i + 1, s3_uri=c.s3_uri, snippet=c.snippet)
                for i, c in enumerate(chunks[:top_k])
            ]

    return chunks[:top_k]


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Query Bedrock Knowledge Base and print top retrieved chunks."
    )
    parser.add_argument("query", help="Free-text query")
    parser.add_argument("--top-k", type=int, default=7, help="Number of chunks to show")
    parser.add_argument(
        "--candidate-k",
        type=int,
        default=0,
        help="Fetch this many candidates before trimming to top-k (helps when preferring a doc).",
    )
    parser.add_argument(
        "--search-type",
        default="",
        help='Optional Bedrock overrideSearchType (e.g. "HYBRID").',
    )
    parser.add_argument(
        "--prefer-s3",
        default="",
        help="If set, prefer results whose s3 uri contains this substring (e.g. wikidata_data.txt).",
    )
    parser.add_argument(
        "--snippet-chars",
        type=int,
        default=400,
        help="Max characters per snippet (for display)",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="If set, also write the retrieved chunks JSON to this path.",
    )
    args = parser.parse_args(argv)

    chunks = retrieve_top_chunks(
        args.query,
        top_k=max(1, args.top_k),
        candidate_k=(args.candidate_k or None),
        snippet_chars=max(0, args.snippet_chars),
        search_type=args.search_type.strip(),
        prefer_s3_uri_substring=args.prefer_s3,
    )

    if not chunks:
        print("No retrieved chunks found for the query.")
        return

    for c in chunks:
        print(f"\n[{c.rank}] {c.s3_uri}")
        print(c.snippet)

    if args.output_json:
        out = [c.__dict__ for c in chunks]
        os.makedirs(os.path.dirname(args.output_json) or ".", exist_ok=True)
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"\nWrote JSON: {args.output_json}")


if __name__ == "__main__":
    main()
