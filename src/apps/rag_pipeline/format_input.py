"""Input formatting utilities for the RAG generation step.

This module prepares a single, structured text payload for the generation
model. It combines:

- source image reference
- predicted label (authentic/inauthentic)
- confidence derived from mean probability
- top-k patch-level evidence
- retrieved knowledge-base chunks
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional


@dataclass(frozen=True)
class PatchEvidence:
    """Patch-level evidence used in generation input."""

    rank: int
    patch_id: str
    patch_path: str
    patch_type: str
    score: float
    contribution: float
    bbox: str


def prediction_to_label(prediction: int) -> str:
    """Convert numeric prediction to semantic label."""
    return "authentic" if int(prediction) == 1 else "inauthentic"


def confidence_from_mean_prob(mean_prob: float) -> float:
    """Compute confidence percent from mean probability.

    Formula:
      abs(mean_prob - 0.5) / 0.5 * 100
    """
    conf = abs(float(mean_prob) - 0.5) / 0.5 * 100.0
    # Clamp to [0, 100] for numerical safety.
    return max(0.0, min(100.0, conf))


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _bbox_from_patch(patch: dict[str, Any]) -> str:
    x = int(_to_float(patch.get("patch_x", 0)))
    y = int(_to_float(patch.get("patch_y", 0)))
    w = int(_to_float(patch.get("patch_width", 0)))
    h = int(_to_float(patch.get("patch_height", 0)))
    return f"x={x}, y={y}, w={w}, h={h}"


def top_k_patch_evidence(
    patches_info: list[dict[str, Any]],
    patch_probs: list[float],
    *,
    prediction: int,
    top_k: int = 5,
) -> list[PatchEvidence]:
    """Select top-k patches by contribution to the final decision.

    Only patches on the predicted side of the decision boundary are considered:
      - prediction=1 (authentic): patch_prob >= 0.5
      - prediction=0 (inauthentic): patch_prob < 0.5

    Contribution is measured as distance from 0.5 within that side.
    """
    pred = int(prediction)
    same_side_rows: list[tuple[dict[str, Any], float, float]] = []
    all_rows: list[tuple[dict[str, Any], float, float]] = []

    for patch, prob in zip(patches_info, patch_probs):
        p = _to_float(prob)
        contribution = abs(p - 0.5)
        row = (patch, p, contribution)
        all_rows.append(row)

        if pred == 1 and p >= 0.5:
            same_side_rows.append(row)
        elif pred == 0 and p < 0.5:
            same_side_rows.append(row)

    # Prefer patches that support the predicted label.
    rows = same_side_rows if same_side_rows else all_rows

    rows.sort(key=lambda t: t[2], reverse=True)
    selected = rows[: max(1, int(top_k))]

    out: list[PatchEvidence] = []
    for i, (patch, prob, contrib) in enumerate(selected, start=1):
        out.append(
            PatchEvidence(
                rank=i,
                patch_id=str(patch.get("patch_id", "")),
                patch_path=str(patch.get("patch_path", "")),
                patch_type=str(patch.get("patch_type", "")),
                score=prob,
                contribution=contrib,
                bbox=_bbox_from_patch(patch),
            )
        )
    return out


def normalize_kb_chunks(chunks: Iterable[Any], *, max_chars: int = 400) -> list[str]:
    """Normalize retrieved KB chunks into plain snippet strings."""
    out: list[str] = []
    for c in chunks:
        snippet = ""
        if isinstance(c, str):
            snippet = c
        elif isinstance(c, dict):
            snippet = str(c.get("snippet", "") or c.get("text", ""))
        else:
            snippet = str(c)

        snippet = " ".join(snippet.split())
        if max_chars > 0 and len(snippet) > max_chars:
            snippet = snippet[:max_chars].rstrip() + "..."
        if snippet:
            out.append(snippet)
    return out


def build_generation_input(
    *,
    source_image: str,
    prediction: int,
    mean_prob: float,
    patches_info: list[dict[str, Any]],
    patch_probs: list[float],
    retrieved_kb_chunks: Iterable[Any],
    top_k_patches: int = 5,
    max_kb_chars: int = 400,
    artist_name: Optional[str] = None,
    artwork_name: Optional[str] = None,
) -> str:
    """Build one structured prompt text for the RAG generation model."""
    label = prediction_to_label(prediction)
    confidence = confidence_from_mean_prob(mean_prob)
    patches = top_k_patch_evidence(
        patches_info,
        patch_probs,
        prediction=prediction,
        top_k=top_k_patches,
    )
    kb_chunks = normalize_kb_chunks(retrieved_kb_chunks, max_chars=max_kb_chars)

    lines: list[str] = [
        "### Inference Context",
        f"- Source image: {source_image}",
        f"- Predicted label: {label}",
        f"- Mean probability: {float(mean_prob):.4f}",
        f"- Confidence (%): {confidence:.2f}",
    ]
    if artist_name:
        lines.append(f"- Artist (user input): {artist_name}")
    if artwork_name:
        lines.append(f"- Artwork (user input): {artwork_name}")

    lines.extend(["", "### Top Patch Evidence"])
    if not patches:
        lines.append("- None")
    else:
        for p in patches:
            lines.append(
                f"- #{p.rank} patch_id={p.patch_id} type={p.patch_type} "
                f"score={p.score:.4f} contribution={p.contribution:.4f} "
                f"bbox=({p.bbox}) path={p.patch_path}"
            )

    lines.extend(["", "### Retrieved Knowledge Chunks"])
    if not kb_chunks:
        lines.append("- None")
    else:
        for i, c in enumerate(kb_chunks, start=1):
            lines.append(f"- [{i}] {c}")

    lines.extend(
        [
            "",
            "### Task",
            "Use the inference evidence and retrieved knowledge to explain the prediction.",
            "Be explicit about uncertainty and avoid unsupported claims.",
        ]
    )
    return "\n".join(lines)

