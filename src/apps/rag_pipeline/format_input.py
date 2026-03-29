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
    region_hint: str


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


def _region_hint_from_patch_coords(
    *,
    patch_x: int,
    patch_y: int,
    x_min: int,
    x_max: int,
    y_min: int,
    y_max: int,
) -> str:
    """Coarse spatial hint (left/center/right + top/center/bottom)."""
    if x_max <= x_min:
        x_mid = x_min
    else:
        x_mid = (x_min + x_max) / 2.0
    if y_max <= y_min:
        y_mid = y_min
    else:
        y_mid = (y_min + y_max) / 2.0

    x_range = max(1.0, float(x_max - x_min))
    y_range = max(1.0, float(y_max - y_min))

    x_tol = 0.2 * x_range
    y_tol = 0.2 * y_range

    if abs(float(patch_x) - x_mid) <= x_tol:
        horiz = "center"
    elif float(patch_x) < x_mid:
        horiz = "left"
    else:
        horiz = "right"

    if abs(float(patch_y) - y_mid) <= y_tol:
        vert = "center"
    elif float(patch_y) < y_mid:
        vert = "top"
    else:
        vert = "bottom"

    if vert == "center" and horiz == "center":
        return "center"
    if vert == "center":
        return f"middle-{horiz}"
    if horiz == "center":
        return f"{vert}-center"
    return f"{vert}-{horiz}"


def top_k_patch_evidence(
    patches_info: list[dict[str, Any]],
    patch_probs: list[float],
    *,
    prediction: int,
    top_k: int = 5,
    x_min: int = 0,
    x_max: int = 0,
    y_min: int = 0,
    y_max: int = 0,
) -> list[PatchEvidence]:
    """Select top-k patches by contribution to the final decision.

    Only patches on the predicted side of the decision boundary are considered:
      - prediction=1 (authentic): patch_prob >= 0.5
      - prediction=0 (inauthentic): patch_prob < 0.5

    Contribution is measured as distance from 0.5 within that side.
    """
    pred = int(prediction)
    same_side_rows: list[tuple[int, dict[str, Any], float, float]] = []
    all_rows: list[tuple[int, dict[str, Any], float, float]] = []

    # Global display numbering used by both RAG text and frontend cells:
    # row-major over unique grid cells (patch variants in same cell share rank).
    unique_cell_keys = {
        (
            int(_to_float(p.get("patch_x", 0))),
            int(_to_float(p.get("patch_y", 0))),
            int(_to_float(p.get("patch_width", 0))),
            int(_to_float(p.get("patch_height", 0))),
        )
        for p in patches_info
    }
    sorted_cells = sorted(unique_cell_keys, key=lambda c: (c[1], c[0], c[2], c[3]))
    cell_rank_by_key = {cell: rank for rank, cell in enumerate(sorted_cells, start=1)}

    for idx, (patch, prob) in enumerate(zip(patches_info, patch_probs)):
        p = _to_float(prob)
        contribution = abs(p - 0.5)
        row = (idx, patch, p, contribution)
        all_rows.append(row)

        if pred == 1 and p >= 0.5:
            same_side_rows.append(row)
        elif pred == 0 and p < 0.5:
            same_side_rows.append(row)

    # Prefer patches that support the predicted label.
    rows = same_side_rows if same_side_rows else all_rows

    rows.sort(key=lambda t: t[3], reverse=True)
    selected = rows[: max(1, int(top_k))]

    out: list[PatchEvidence] = []
    for orig_idx, patch, prob, contrib in selected:
        patch_x = int(_to_float(patch.get("patch_x", 0)))
        patch_y = int(_to_float(patch.get("patch_y", 0)))
        region_hint = _region_hint_from_patch_coords(
            patch_x=patch_x,
            patch_y=patch_y,
            x_min=x_min,
            x_max=x_max,
            y_min=y_min,
            y_max=y_max,
        )
        out.append(
            PatchEvidence(
                rank=int(
                    cell_rank_by_key.get(
                        (
                            int(_to_float(patch.get("patch_x", 0))),
                            int(_to_float(patch.get("patch_y", 0))),
                            int(_to_float(patch.get("patch_width", 0))),
                            int(_to_float(patch.get("patch_height", 0))),
                        ),
                        orig_idx + 1,
                    )
                ),
                patch_id=str(patch.get("patch_id", "")),
                patch_path=str(patch.get("patch_path", "")),
                patch_type=str(patch.get("patch_type", "")),
                score=prob,
                contribution=contrib,
                bbox=_bbox_from_patch(patch),
                region_hint=region_hint,
            )
        )
    return out


def normalize_kb_chunks(chunks: Iterable[Any], *, max_chars: int = 400) -> list[str]:
    """Normalize retrieved KB chunks into snippet strings with source filename.

    The generation system prompt expects metadata/history claims to include
    the source filename (derived from the KB retrieved `s3_uri`).
    """

    def _s3_uri_to_filename(uri: str) -> str:
        if not uri:
            return ""
        # Expected s3 uri shape: s3://<bucket>/<key>...
        if uri.startswith("s3://"):
            rest = uri[5:]
            _, _, key = rest.partition("/")
        else:
            key = uri
        filename = key.split("/")[-1].strip()
        return filename

    out: list[str] = []
    for c in chunks:
        source_file = ""
        snippet = ""

        if isinstance(c, str):
            snippet = c
        elif isinstance(c, dict):
            source_file = _s3_uri_to_filename(
                str(c.get("s3_uri", "") or c.get("s3Uri", "") or c.get("uri", "") or "")
            )
            snippet = str(c.get("snippet", "") or c.get("text", ""))
        else:
            # Bedrock retrieval returns dataclass-like objects with fields.
            source_uri = str(getattr(c, "s3_uri", "") or "")
            source_file = _s3_uri_to_filename(source_uri)
            snippet = str(getattr(c, "snippet", "") or getattr(c, "text", "") or "")

        snippet = " ".join(snippet.split())
        if max_chars > 0 and len(snippet) > max_chars:
            snippet = snippet[:max_chars].rstrip() + "..."

        snippet = snippet.strip()
        if snippet:
            if source_file:
                out.append(f"source_file={source_file}; snippet={snippet}")
            else:
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
    overall_image_attached: bool = True,
) -> str:
    """Build one structured prompt text for the RAG generation model."""
    label = prediction_to_label(prediction)
    confidence = confidence_from_mean_prob(mean_prob)

    # Coarse spatial bounds used to derive `region_hint` (left/center/right, top/center/bottom).
    x_min = 0
    x_max = 0
    y_min = 0
    y_max = 0
    if patches_info:
        x_starts: list[int] = []
        y_starts: list[int] = []
        x_ends: list[int] = []
        y_ends: list[int] = []
        for patch in patches_info:
            x = int(_to_float(patch.get("patch_x", 0)))
            y = int(_to_float(patch.get("patch_y", 0)))
            w = int(_to_float(patch.get("patch_width", 0)))
            h = int(_to_float(patch.get("patch_height", 0)))

            x_end = x + w if w > 0 else x
            y_end = y + h if h > 0 else y

            x_starts.append(x)
            y_starts.append(y)
            x_ends.append(x_end)
            y_ends.append(y_end)

        x_min = min(x_starts) if x_starts else 0
        x_max = max(x_ends) if x_ends else 0
        y_min = min(y_starts) if y_starts else 0
        y_max = max(y_ends) if y_ends else 0

    patches = top_k_patch_evidence(
        patches_info,
        patch_probs,
        prediction=prediction,
        top_k=top_k_patches,
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max,
    )
    kb_chunks = normalize_kb_chunks(retrieved_kb_chunks, max_chars=max_kb_chars)

    lines: list[str] = [
        "### Inference Context",
        f"- Source image: {source_image}",
        f"- Overall image attached: {overall_image_attached}",
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
                f"region_hint={p.region_hint} bbox=({p.bbox}) path={p.patch_path}"
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

