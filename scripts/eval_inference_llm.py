"""Batch-evaluate /inference explanations on data/test images.

This script runs authenticated inference calls and evaluates explanation quality
with:
1) Deterministic guardrail checks:
   - alignment with model prediction
   - anti-overconfidence / hedging policy
   - robust patch-reference structure checks
   - robust faithfulness checks grounded in retrieved KB snippets
It writes JSON + CSV reports and (optionally) logs traces/scores to Langfuse.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import requests

# Ensure project imports work when running as a script.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.apps.rag_pipeline.knowledge_base import RetrievedChunk, retrieve_top_chunks


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
VISUAL_OBS_TERMS = {
    "contrast",
    "texture",
    "edge",
    "edges",
    "color transition",
    "color transitions",
    "sharp",
    "soft",
    "coarse",
    "smooth",
}
HEDGING_FORBIDDEN = {
    "certain",
    "certainly",
    "guarantee",
    "guaranteed",
    "definitely",
    "undeniably",
    "without doubt",
    "conclusive",
}
ALIGN_POSITIVE_TERMS = {"authentic", "likely authentic", "supports authenticity"}
ALIGN_NEGATIVE_TERMS = {"inauthentic", "non-authentic", "forgery", "likely non-authentic"}
METADATA_CLAIM_HINTS = {
    "museum",
    "provenance",
    "series",
    "title",
    "dated",
    "date",
    "period",
    "ownership",
    "collection",
    "artist",
    "histor",
    "exhibit",
}
STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "to",
    "in",
    "on",
    "for",
    "with",
    "is",
    "are",
    "was",
    "were",
    "be",
    "by",
    "this",
    "that",
    "as",
    "it",
    "its",
    "from",
    "at",
}


@dataclass
class EvalResult:
    image_path: str
    expected_label: int
    api_prediction: int
    score: float
    explanation: str
    inference_id: str
    alignment: bool
    hedging: bool
    patch_references: bool
    faithfulness: bool
    patch_reference_count: int
    patch_reference_unique_ranks: int
    cited_metadata_sentences: int
    uncited_metadata_sentences: int
    unsupported_cited_sentences: int
    notes: list[str]

    @property
    def overall_pass(self) -> bool:
        return self.alignment and self.hedging and self.patch_references and self.faithfulness


LANGFUSE_DEBUG_LOG_PATH: Optional[Path] = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ArtGuard explanation evals.")
    parser.add_argument("--api-base", default="https://d1b5yxlog377uv.cloudfront.net")
    parser.add_argument("--data-dir", default="data/test")
    parser.add_argument("--artist-name", default="Vincent van Gogh")
    parser.add_argument("--artwork-name", default="Untitled")
    parser.add_argument("--username", default="demo")
    parser.add_argument("--email", default="demo@example.com")
    parser.add_argument("--password", default="demopass1")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--output-dir", default="artifacts/llm_evals")
    parser.add_argument("--max-images", type=int, default=0, help="0 means all")
    parser.add_argument("--min-patch-refs", type=int, default=3)
    parser.add_argument("--kb-top-k", type=int, default=7)
    parser.add_argument("--kb-candidate-k", type=int, default=40)
    parser.add_argument("--kb-search-type", default="HYBRID")
    parser.add_argument("--langfuse-trace-name", default="artguard-llm-eval")
    return parser.parse_args()


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def _contains_any(text: str, terms: set[str]) -> bool:
    low = text.lower()
    return any(t in low for t in terms)


def _wordset(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    return {w for w in words if len(w) > 2 and w not in STOPWORDS}


def evaluate_alignment(prediction: int, explanation: str) -> tuple[bool, str]:
    low = explanation.lower()
    pos = _contains_any(low, ALIGN_POSITIVE_TERMS)
    neg = _contains_any(low, ALIGN_NEGATIVE_TERMS)
    if prediction == 1:
        if neg and not pos:
            return False, "Text implies inauthentic while prediction=1."
    else:
        if pos and not neg:
            return False, "Text implies authentic while prediction=0."
    return True, ""


def evaluate_hedging(explanation: str) -> tuple[bool, str]:
    low = explanation.lower()
    hits = [w for w in sorted(HEDGING_FORBIDDEN) if w in low]
    if hits:
        return False, f"Over-certain terms: {', '.join(hits)}."
    return True, ""


def evaluate_patch_references(
    explanation: str,
    patch_count: int,
    min_patch_refs: int,
) -> tuple[bool, int, int, str]:
    """Robust patch-reference check.

    Requires explicit Patch references in this structure:
      Patch #<rank>:
    (optionally wrapped in markdown bold, e.g. **Patch #<rank>**:)
    and requires visual-observation wording in the same sentence.
    """
    sentences = _split_sentences(explanation)
    pattern = re.compile(
        r"(?:\*\*)?\bPatch\s*#(?P<rank>\d+)(?:\*\*)?\s*:",
        flags=re.IGNORECASE,
    )

    total_refs = 0
    valid_refs = 0
    ranks: set[int] = set()
    for s in sentences:
        for m in pattern.finditer(s):
            total_refs += 1
            rank = int(m.group("rank"))
            has_visual_term = _contains_any(s, VISUAL_OBS_TERMS)
            rank_in_range = 1 <= rank <= max(1, patch_count)
            if has_visual_term and rank_in_range:
                valid_refs += 1
                ranks.add(rank)

    unique_ranks = len(ranks)
    if valid_refs < min_patch_refs:
        return (
            False,
            total_refs,
            unique_ranks,
            f"Only {valid_refs} valid structured patch refs (< {min_patch_refs}).",
        )
    if unique_ranks < min_patch_refs:
        return (
            False,
            total_refs,
            unique_ranks,
            f"Only {unique_ranks} unique referenced patch ranks (< {min_patch_refs}).",
        )
    return True, total_refs, unique_ranks, ""


def evaluate_faithfulness(
    explanation: str,
    retrieved_chunks: list[RetrievedChunk],
) -> tuple[bool, int, int, int, str]:
    """Robust faithfulness check.

    Rules:
    1) If a metadata/history claim includes `(source: filename)`,
       that filename must exist in retrieved chunks.
    2) Cited claim should have lexical overlap with at least one cited snippet.
    3) Metadata/history claims without citations are allowed (counted, not failed).
    """
    sentences = _split_sentences(explanation)
    snippet_by_filename: dict[str, list[str]] = {}
    for c in retrieved_chunks:
        fname = (c.s3_uri.split("/")[-1] if c.s3_uri else "").strip().lower()
        if not fname:
            continue
        snippet_by_filename.setdefault(fname, []).append(c.snippet or "")

    cited = 0
    uncited = 0
    unsupported = 0
    for s in sentences:
        sl = s.lower()
        looks_like_metadata = any(h in sl for h in METADATA_CLAIM_HINTS)
        if not looks_like_metadata:
            continue

        citations = re.findall(r"\(source:\s*([^)]+)\)", s, flags=re.IGNORECASE)
        if not citations:
            uncited += 1
            continue

        cited += 1
        # validate citation exists + textual support
        claim_words = _wordset(s)
        has_support = False
        for raw_name in citations:
            fname = raw_name.strip().lower()
            if fname not in snippet_by_filename:
                continue
            for snip in snippet_by_filename[fname]:
                overlap = claim_words.intersection(_wordset(snip))
                if len(overlap) >= 3:
                    has_support = True
                    break
            if has_support:
                break
        if not has_support:
            unsupported += 1

    if unsupported > 0:
        return False, cited, uncited, unsupported, "Some cited metadata claims lack textual support in KB snippets."
    return True, cited, uncited, unsupported, ""


def list_images(data_dir: Path, max_images: int) -> list[Path]:
    images = [
        p
        for p in sorted(data_dir.rglob("*"))
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS and "class_" in str(p.parent)
    ]
    return images[:max_images] if max_images > 0 else images


def expected_label_from_path(path: Path) -> int:
    return 1 if "class_1" in str(path) else 0


def ensure_user_and_login(
    session: requests.Session,
    api_base: str,
    username: str,
    email: str,
    password: str,
    timeout_seconds: int,
) -> str:
    session.post(
        f"{api_base}/auth/signup",
        json={"username": username, "email": email, "password": password},
        timeout=timeout_seconds,
    )
    resp = session.post(
        f"{api_base}/auth/login",
        json={"email": email, "password": password},
        timeout=timeout_seconds,
    )
    resp.raise_for_status()
    payload = resp.json()
    token = payload.get("access_token") or payload.get("token")
    if not token:
        raise RuntimeError(f"No token in login response: {payload}")
    return str(token)


def call_inference(
    session: requests.Session,
    api_base: str,
    token: str,
    image_path: Path,
    artist_name: str,
    artwork_name: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    with image_path.open("rb") as fh:
        files = {"file": (image_path.name, fh, "application/octet-stream")}
        data = {"artist_name": artist_name, "artwork_name": artwork_name}
        headers = {"Authorization": f"Bearer {token}"}
        resp = session.post(
            f"{api_base}/inference",
            headers=headers,
            files=files,
            data=data,
            timeout=timeout_seconds,
        )
    resp.raise_for_status()
    return resp.json()


def get_retrieved_chunks(
    artist_name: str,
    artwork_name: str,
    top_k: int,
    candidate_k: int,
    search_type: str,
) -> tuple[str, list[RetrievedChunk]]:
    query = " ".join([artist_name.strip(), artwork_name.strip()]).strip() or "art authenticity"
    chunks = retrieve_top_chunks(
        query,
        top_k=max(1, int(top_k)),
        candidate_k=max(1, int(candidate_k)),
        snippet_chars=600,
        search_type=search_type.strip(),
    )
    return query, chunks


def maybe_create_langfuse_client() -> Optional[Any]:
    pub = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    sec = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    if not pub or not sec:
        return None
    try:
        from langfuse import Langfuse  # type: ignore
    except Exception:
        return None

    kwargs: dict[str, Any] = {"public_key": pub, "secret_key": sec}
    base = os.getenv("LANGFUSE_BASE_URL", "").strip()
    if base:
        kwargs["host"] = base
    try:
        return Langfuse(**kwargs)
    except Exception:
        return None


def print_langfuse_diagnostics(client: Optional[Any]) -> None:
    pub = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    sec = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    host = os.getenv("LANGFUSE_BASE_URL", "").strip() or "https://cloud.langfuse.com (default)"
    if not pub or not sec:
        print("Langfuse: disabled (missing LANGFUSE_PUBLIC_KEY and/or LANGFUSE_SECRET_KEY).")
        return

    masked_pub = f"{pub[:8]}..." if len(pub) > 8 else pub
    print(f"Langfuse: configured (host={host}, public_key={masked_pub}).")
    if client is None:
        print("Langfuse: client initialization failed; traces will not be uploaded.")
        return

    try:
        ok = bool(client.auth_check())
        if ok:
            print("Langfuse: auth_check passed.")
        else:
            print("Langfuse: auth_check failed; verify keys/host/project.")
    except Exception as exc:
        print(f"Langfuse: auth_check error ({exc}); verify keys/host/project.")


def _set_langfuse_debug_log_path(path: Path) -> None:
    global LANGFUSE_DEBUG_LOG_PATH
    LANGFUSE_DEBUG_LOG_PATH = path


def _langfuse_log(message: str) -> None:
    timestamp = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    line = f"{timestamp} {message}"
    print(line)
    if LANGFUSE_DEBUG_LOG_PATH is None:
        return
    try:
        LANGFUSE_DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LANGFUSE_DEBUG_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        return


def _safe_langfuse_score(observation: Any, name: str, value: float, comment: Optional[str] = None) -> None:
    try:
        if comment:
            observation.score(name=name, value=value, comment=comment)
        else:
            observation.score(name=name, value=value)
    except Exception as exc:
        _langfuse_log(f"Langfuse score logging error ({name}): {exc}")
        return


def log_langfuse_eval(
    client: Any,
    trace_name: str,
    item: EvalResult,
    *,
    run_id: str,
    image_index: int,
    total_images: int,
    artist_name: str,
    artwork_name: str,
    api_base: str,
) -> None:
    if client is None:
        return
    try:
        if hasattr(client, "trace"):
            trace = client.trace(
                name=trace_name,
                session_id=run_id,
                user_id="eval-script",
                tags=["eval", "artguard", "llm-explanation"],
                input={
                    "image_path": item.image_path,
                    "expected_label": item.expected_label,
                    "artist_name": artist_name,
                    "artwork_name": artwork_name,
                },
                output={"prediction": item.api_prediction, "explanation": item.explanation},
                metadata={
                    "inference_id": item.inference_id,
                    "run_id": run_id,
                    "image_index": image_index,
                    "total_images": total_images,
                    "api_base": api_base,
                    "score": item.score,
                    "patch_reference_count": item.patch_reference_count,
                    "patch_reference_unique_ranks": item.patch_reference_unique_ranks,
                    "cited_metadata_sentences": item.cited_metadata_sentences,
                    "uncited_metadata_sentences": item.uncited_metadata_sentences,
                    "unsupported_cited_sentences": item.unsupported_cited_sentences,
                    "notes": item.notes,
                },
            )

            trace.span(
                name="inference-api-call",
                input={"image_path": item.image_path},
                output={"inference_id": item.inference_id, "prediction": item.api_prediction},
            )
            trace.span(
                name="deterministic-eval",
                input={"expected_label": item.expected_label, "prediction": item.api_prediction},
                output={
                    "alignment": item.alignment,
                    "hedging": item.hedging,
                    "patch_references": item.patch_references,
                    "faithfulness": item.faithfulness,
                    "overall_pass": item.overall_pass,
                },
            )
            obs = trace.generation(
                name="explanation-output",
                model="remote-artguard-inference",
                input={"expected_label": item.expected_label},
                output=item.explanation,
                metadata={"explanation_chars": len(item.explanation)},
            )
        else:
            with client.start_as_current_span(
                name=trace_name,
                input={
                    "image_path": item.image_path,
                    "expected_label": item.expected_label,
                    "artist_name": artist_name,
                    "artwork_name": artwork_name,
                },
                output={"prediction": item.api_prediction, "explanation": item.explanation},
                metadata={
                    "inference_id": item.inference_id,
                    "run_id": run_id,
                    "image_index": image_index,
                    "total_images": total_images,
                    "api_base": api_base,
                    "score": item.score,
                    "patch_reference_count": item.patch_reference_count,
                    "patch_reference_unique_ranks": item.patch_reference_unique_ranks,
                    "cited_metadata_sentences": item.cited_metadata_sentences,
                    "uncited_metadata_sentences": item.uncited_metadata_sentences,
                    "unsupported_cited_sentences": item.unsupported_cited_sentences,
                    "notes": item.notes,
                },
            ):
                client.update_current_trace(
                    name=trace_name,
                    session_id=run_id,
                    user_id="eval-script",
                    tags=["eval", "artguard", "llm-explanation"],
                )
                with client.start_as_current_span(
                    name="inference-api-call",
                    input={"image_path": item.image_path},
                    output={"inference_id": item.inference_id, "prediction": item.api_prediction},
                ):
                    pass
                with client.start_as_current_span(
                    name="deterministic-eval",
                    input={"expected_label": item.expected_label, "prediction": item.api_prediction},
                    output={
                        "alignment": item.alignment,
                        "hedging": item.hedging,
                        "patch_references": item.patch_references,
                        "faithfulness": item.faithfulness,
                        "overall_pass": item.overall_pass,
                    },
                ):
                    pass
                with client.start_as_current_generation(
                    name="explanation-output",
                    model="remote-artguard-inference",
                    input={"expected_label": item.expected_label},
                    output=item.explanation,
                    metadata={"explanation_chars": len(item.explanation)},
                ) as obs:
                    _safe_langfuse_score(obs, name="alignment", value=1.0 if item.alignment else 0.0)
                    _safe_langfuse_score(obs, name="hedging", value=1.0 if item.hedging else 0.0)
                    _safe_langfuse_score(
                        obs, name="patch_references", value=1.0 if item.patch_references else 0.0
                    )
                    _safe_langfuse_score(obs, name="faithfulness", value=1.0 if item.faithfulness else 0.0)
                    _safe_langfuse_score(
                        obs, name="overall_pass", value=1.0 if item.overall_pass else 0.0
                    )
            return
        # Keep observations hierarchical so failures and latency are easy to locate.
        _safe_langfuse_score(obs, name="alignment", value=1.0 if item.alignment else 0.0)
        _safe_langfuse_score(obs, name="hedging", value=1.0 if item.hedging else 0.0)
        _safe_langfuse_score(
            obs, name="patch_references", value=1.0 if item.patch_references else 0.0
        )
        _safe_langfuse_score(obs, name="faithfulness", value=1.0 if item.faithfulness else 0.0)
        _safe_langfuse_score(obs, name="overall_pass", value=1.0 if item.overall_pass else 0.0)
    except Exception as exc:
        _langfuse_log(f"Langfuse trace logging error for successful eval item: {exc}")
        return


def log_langfuse_eval_error(
    client: Any,
    trace_name: str,
    *,
    run_id: str,
    image_index: int,
    total_images: int,
    image_path: Path,
    expected_label: int,
    exc: Exception,
) -> None:
    if client is None:
        return
    try:
        if hasattr(client, "trace"):
            trace = client.trace(
                name=trace_name,
                session_id=run_id,
                user_id="eval-script",
                tags=["eval", "artguard", "llm-explanation", "error"],
                input={"image_path": str(image_path), "expected_label": expected_label},
                output={"error": str(exc)},
                metadata={
                    "run_id": run_id,
                    "image_index": image_index,
                    "total_images": total_images,
                    "status": "error",
                },
            )
            obs = trace.span(
                name="inference-eval-error",
                output={"error": str(exc)},
                metadata={"level": "ERROR"},
            )
            _safe_langfuse_score(obs, name="overall_pass", value=0.0, comment="Image evaluation failed.")
        else:
            with client.start_as_current_span(
                name=trace_name,
                input={"image_path": str(image_path), "expected_label": expected_label},
                output={"error": str(exc)},
                metadata={
                    "run_id": run_id,
                    "image_index": image_index,
                    "total_images": total_images,
                    "status": "error",
                },
            ):
                client.update_current_trace(
                    name=trace_name,
                    session_id=run_id,
                    user_id="eval-script",
                    tags=["eval", "artguard", "llm-explanation", "error"],
                )
                with client.start_as_current_span(
                    name="inference-eval-error",
                    output={"error": str(exc)},
                    level="ERROR",
                    status_message=str(exc),
                ) as obs:
                    _safe_langfuse_score(
                        obs, name="overall_pass", value=0.0, comment="Image evaluation failed."
                    )
    except Exception as trace_exc:
        _langfuse_log(f"Langfuse trace logging error for failed eval item: {trace_exc}")
        return


def write_outputs(output_dir: Path, rows: list[EvalResult]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "llm_eval_report.json"
    csv_path = output_dir / "llm_eval_report.csv"

    total = len(rows)
    summary = {
        "total_images": total,
        "alignment_pass_rate": (sum(r.alignment for r in rows) / total) if total else 0.0,
        "hedging_pass_rate": (sum(r.hedging for r in rows) / total) if total else 0.0,
        "patch_references_pass_rate": (sum(r.patch_references for r in rows) / total) if total else 0.0,
        "faithfulness_pass_rate": (sum(r.faithfulness for r in rows) / total) if total else 0.0,
        "overall_pass_rate": (sum(r.overall_pass for r in rows) / total) if total else 0.0,
        "model_prediction_accuracy_vs_dataset_label": (
            sum(int(r.api_prediction == r.expected_label) for r in rows) / total
        ) if total else 0.0,
    }

    payload = {
        "summary": summary,
        "items": [r.__dict__ | {"overall_pass": r.overall_pass} for r in rows],
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    fieldnames = list(rows[0].__dict__.keys()) + ["overall_pass"] if rows else []
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            row = r.__dict__.copy()
            row["overall_pass"] = r.overall_pass
            row["notes"] = " | ".join(r.notes)
            writer.writerow(row)

    return json_path, csv_path


def main() -> None:
    args = parse_args()
    api_base = args.api_base.rstrip("/")
    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)
    if not data_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")
    _set_langfuse_debug_log_path(output_dir / "langfuse_debug.log")

    images = list_images(data_dir, args.max_images)
    if not images:
        raise RuntimeError(f"No images found in {data_dir}")

    session = requests.Session()
    token = ensure_user_and_login(
        session, api_base, args.username, args.email, args.password, args.timeout_seconds
    )
    langfuse_client = maybe_create_langfuse_client()
    print_langfuse_diagnostics(langfuse_client)
    eval_run_id = f"llm-eval-{uuid.uuid4().hex[:12]}"
    print(f"Langfuse run_id: {eval_run_id}")

    results: list[EvalResult] = []
    for idx, image_path in enumerate(images, start=1):
        expected_label = expected_label_from_path(image_path)
        try:
            response = call_inference(
                session=session,
                api_base=api_base,
                token=token,
                image_path=image_path,
                artist_name=args.artist_name,
                artwork_name=args.artwork_name,
                timeout_seconds=args.timeout_seconds,
            )
            explanation = str(response.get("explanation") or "")
            prediction = int(response.get("prediction", -1))
            score = float(response.get("score", 0.0))
            inference_id = str(response.get("inference_id", ""))
            patch_data = response.get("patch_data") or []
            patch_count = len(patch_data)

            # Retrieve KB snippets used for robust faithfulness checks.
            _, retrieved_chunks = get_retrieved_chunks(
                args.artist_name,
                args.artwork_name,
                args.kb_top_k,
                args.kb_candidate_k,
                args.kb_search_type,
            )

            alignment_ok, alignment_note = evaluate_alignment(prediction, explanation)
            hedging_ok, hedging_note = evaluate_hedging(explanation)
            patch_ok, patch_refs, patch_unique, patch_note = evaluate_patch_references(
                explanation, patch_count=max(1, patch_count), min_patch_refs=max(1, args.min_patch_refs)
            )
            faithful_ok, cited, uncited, unsupported, faithful_note = evaluate_faithfulness(
                explanation, retrieved_chunks
            )

            notes = [n for n in [alignment_note, hedging_note, patch_note, faithful_note] if n]
            item = EvalResult(
                image_path=str(image_path),
                expected_label=expected_label,
                api_prediction=prediction,
                score=score,
                explanation=explanation,
                inference_id=inference_id,
                alignment=alignment_ok,
                hedging=hedging_ok,
                patch_references=patch_ok,
                faithfulness=faithful_ok,
                patch_reference_count=patch_refs,
                patch_reference_unique_ranks=patch_unique,
                cited_metadata_sentences=cited,
                uncited_metadata_sentences=uncited,
                unsupported_cited_sentences=unsupported,
                notes=notes,
            )
            results.append(item)
            log_langfuse_eval(
                langfuse_client,
                args.langfuse_trace_name,
                item,
                run_id=eval_run_id,
                image_index=idx,
                total_images=len(images),
                artist_name=args.artist_name,
                artwork_name=args.artwork_name,
                api_base=api_base,
            )
            print(
                f"[{idx}/{len(images)}] {image_path.name}: "
                f"pred={prediction} overall_pass={item.overall_pass}"
            )
        except Exception as exc:
            log_langfuse_eval_error(
                langfuse_client,
                args.langfuse_trace_name,
                run_id=eval_run_id,
                image_index=idx,
                total_images=len(images),
                image_path=image_path,
                expected_label=expected_label,
                exc=exc,
            )
            print(f"[{idx}/{len(images)}] {image_path.name}: ERROR {exc}")

    if langfuse_client is not None:
        try:
            langfuse_client.flush()
        except Exception as exc:
            _langfuse_log(f"Langfuse flush error: {exc}")
            pass

    json_path, csv_path = write_outputs(output_dir, results)
    print(f"\nCompleted {len(results)}/{len(images)} successful inferences.")
    print(f"JSON report: {json_path}")
    print(f"CSV report: {csv_path}")
    print(f"Langfuse debug log: {output_dir / 'langfuse_debug.log'}")


if __name__ == "__main__":
    main()
