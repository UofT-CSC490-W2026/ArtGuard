"""Generate final RAG explanations from model + retrieval evidence.

Pipeline:
1) Retrieve top-k knowledge chunks from Bedrock KB.
2) Build structured generation input from inference context.
3) Call Bedrock Runtime (Claude Sonnet) with top patch images + text context
   to generate the final explanation.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Optional

import boto3

from src.apps.backend.config import bedrock_invoke_model_id, get_region
from src.apps.rag_pipeline.format_input import build_generation_input, top_k_patch_evidence
from src.apps.rag_pipeline.knowledge_base import retrieve_top_chunks


SYSTEM_PROMPT = """\
<role>
You are an expert assistant in computer vision-based art analysis.
</role>

<why_this_task_matters>
The model produces a binary authenticity score (0 or 1), but this output alone is not interpretable to users.
Your explanation must show that the result is supported by concrete visual evidence and relevant artistic context.
By referring to specific regions in the image, help users visually follow along and understand how the decision is grounded in the painting itself.
</why_this_task_matters>

<task>
Explain how the model arrived at its authenticity score using the provided evidence.
</task>

<inputs_you_will_receive>
<input>Top image patches ranked by contribution (typically top 8).</input>
<input>Binary authenticity score (0 = non-authentic, 1 = authentic).</input>
<input>Confidence score computed as abs(image_logit - 0.5) / 0.5 * 100.</input>
<input>Retrieved metadata and context about the artist and artworks.</input>
</inputs_you_will_receive>

<response_requirements>
<requirement>
For each patch you discuss (choose 3-6 of the highest-ranked patches from the provided “Top Patch Evidence”), write one sentence that starts with:
`Patch #<rank> (<region_hint>, <patch_type>)`.
</requirement>
<requirement>
In that same sentence, include at least one concrete visual observation category that is directly visible in the patch image.
Use one or more of: contrast (high/low), texture (smooth/coarse), edges (sharp/soft), color transitions (broad/abrupt).
</requirement>
<requirement>
If the provided `region_hint` is `unknown-position`, determine the patch's rough location by visually matching it against the attached overall image, and report a rough position such as `top-left`, `top-right`, `center`, `bottom-left`, or `bottom-right` (or `position uncertain` if you cannot reliably match).
</requirement>
<requirement>
If `region_hint` is `unknown-position` and the input says `Overall image attached: False`, then you must output `position uncertain` for the location (do not guess `center` / corners).
</requirement>
<requirement>
Use patches and the confidence score together to explain which regions support authenticity and which reduce it.
</requirement>
<requirement>
Write clear, well-structured paragraphs for an end user.
</requirement>
<requirement>
Do not use patch tokens like `P1` / `P2` in the final answer.
Instead, connect each visual claim to the patch region by using the `region_hint` (provided in the “Top Patch Evidence”) and the concrete visual observation from that patch image.
</requirement>
<requirement>
For any metadata/history claim (title, series, date, provenance, museum ownership, artist-period linkage), include the source filename from the retrieved knowledge (e.g., `(source: met_data_part27.txt)`).
</requirement>
</response_requirements>

<style>
<item>Be specific, grounded, and concise.</item>
<item>Do not invent visual details that are not directly visible in the provided patch images or explicitly present in retrieved metadata.</item>
<item>Do not claim certainty when evidence is mixed.</item>
<item>Avoid bullet points in the final answer; produce paragraph-style explanation.</item>
</style>

<allowed_claims>
<claim>Low-level visual observations directly visible in patches (e.g., high/low contrast, smooth vs coarse texture, sharp vs soft edges, broad color transitions).</claim>
<claim>Metadata-grounded statements if explicitly present in retrieved chunks.</claim>
</allowed_claims>

<forbidden_claims>
<claim>Do not claim specific art-historical traits (e.g., "Van Gogh's characteristic brushstroke pattern") unless the claim is explicitly supported by retrieved metadata and linked to visible evidence.</claim>
<claim>Do not describe stroke direction, impasto, or other fine-grained technique unless clearly visible in the provided patches.</claim>
<claim>Do not infer provenance, materials, or history unless explicitly stated in retrieved metadata.</claim>
<claim>Do not assert a specific artwork title, series, or museum ownership unless that exact fact is explicitly present in retrieved chunks and you include the corresponding source filename in the response.</claim>
<claim>Do not use named examples (e.g., "Sunflowers", "The Potato Eaters") unless the retrieved chunks explicitly contain them and they are directly relevant.</claim>
</forbidden_claims>

<evidence_policy>
If evidence is insufficient for a detailed visual claim, explicitly say the signal is inconclusive.
Prefer cautious language over speculative language.
If metadata evidence is missing, weak, or conflicting, explicitly state that metadata is insufficient and avoid specific historical assertions.
</evidence_policy>

<output_contract>
- Every visual claim must use the `Patch #<rank> (<region_hint>, <patch_type>)` format for at least one patch and include at least one visual observation category (contrast/texture/edges/color transitions).
- Every metadata/history claim must include the source filename (e.g., `(source: met_data_part27.txt)`).
- If no retrieved knowledge provides source-file support for a metadata/history claim, omit the metadata/history claim.
</output_contract>

<example_grounded_non_authentic>
<input>
Score: 0
Confidence: 68
Top Patch Evidence (example):
- #1 (region_hint=middle-right, patch_type=center_crop_orig)
- #2 (region_hint=top-center, patch_type=downsample_orig)
- #3 (region_hint=bottom-left, patch_type=center_crop_orig)
Metadata: limited artist context available
</input>
<output>
The model predicts that this painting is likely non-authentic, with a moderate level of confidence.
Patch #1 (middle-right, center_crop_orig): texture appears relatively smooth with low local contrast, which provides evidence against authenticity.
Patch #2 (top-center, downsample_orig): color transitions look broad and gradual rather than abrupt, which also points away from authenticity.
Patch #3 (bottom-left, center_crop_orig): local variation is stronger, partially supporting authenticity, but this signal is outweighed by the other patch observations above.
Overall, the confidence score indicates moderate certainty rather than absolute certainty. The evidence is directionally consistent across multiple patches, but the available metadata is limited, so the conclusion should be treated as model-supported rather than definitive.
</output>
</example_grounded_non_authentic>
"""


def _build_user_prompt(formatted_input: str) -> str:
    """Wrap structured evidence for Claude with XML tags."""
    return (
        "<analysis_input>\n"
        f"{formatted_input}\n"
        "</analysis_input>\n\n"
        "<instruction>\n"
        "Produce the final end-user explanation now.\n"
        "</instruction>"
    )


@dataclass(frozen=True)
class GenerationResult:
    """Result package from end-to-end generation."""

    response_text: str
    formatted_input: str
    retrieved_kb_chunks: list[str]
    used_patch_image_uris: list[str]


def _extract_text_from_invoke_response(resp: dict[str, Any]) -> str:
    """Extract response text from Bedrock invoke_model payload."""
    body = resp.get("body")
    if body is None:
        return ""

    raw = body.read() if hasattr(body, "read") else body
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    payload = json.loads(raw)

    # Claude Messages response format.
    parts = payload.get("content", [])
    texts: list[str] = []
    for p in parts:
        if isinstance(p, dict) and p.get("type") == "text":
            t = p.get("text")
            if t:
                texts.append(str(t))
    if texts:
        return "\n".join(texts).strip()

    # Fallback for unknown payload shapes.
    if isinstance(payload.get("outputText"), str):
        return payload["outputText"].strip()
    return ""


def _s3_uri_to_bucket_key(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise ValueError(f"Not an s3 uri: {uri}")
    rest = uri[5:]
    bucket, _, key = rest.partition("/")
    if not bucket or not key:
        raise ValueError(f"Invalid s3 uri: {uri}")
    return bucket, key


def _infer_media_type_from_uri(uri: str) -> str:
    lower = uri.lower()
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".webp"):
        return "image/webp"
    # Default to jpeg for .jpg/.jpeg and unknown image-like paths.
    return "image/jpeg"


def _load_patch_image_blocks(
    patch_image_uris: list[str],
    *,
    max_images: int = 8,
    max_bytes: int = 3_500_000,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Fetch patch images from S3 and build Claude image content blocks."""
    if not patch_image_uris:
        return [], []

    s3 = boto3.client("s3", region_name=get_region())
    blocks: list[dict[str, Any]] = []
    used: list[str] = []

    for uri in patch_image_uris[: max(1, int(max_images))]:
        try:
            bucket, key = _s3_uri_to_bucket_key(uri)
            obj = s3.get_object(Bucket=bucket, Key=key)
            raw = obj["Body"].read()
            if not raw:
                continue
            # Keep payload sizes bounded for Bedrock invoke.
            if len(raw) > max_bytes:
                continue

            media_type = _infer_media_type_from_uri(uri)
            b64 = base64.b64encode(raw).decode("utf-8")
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": b64,
                    },
                }
            )
            used.append(uri)
        except Exception:
            # Best-effort: skip unreadable patch images and continue.
            continue

    return blocks, used


def _load_single_image_block(uri: str, *, max_bytes: int = 6_000_000) -> tuple[list[dict[str, Any]], bool]:
    """Fetch one S3 image and return a single Claude image block."""
    if not uri or not uri.startswith("s3://"):
        return [], False
    try:
        s3 = boto3.client("s3", region_name=get_region())
        bucket, key = _s3_uri_to_bucket_key(uri)
        obj = s3.get_object(Bucket=bucket, Key=key)
        raw = obj["Body"].read()
        if not raw or len(raw) > max_bytes:
            return [], False
        media_type = _infer_media_type_from_uri(uri)
        b64 = base64.b64encode(raw).decode("utf-8")
        return (
            [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": b64,
                    },
                }
            ],
            True,
        )
    except Exception:
        return [], False


def _generate_with_claude(
    prompt: str,
    *,
    patch_image_blocks: Optional[list[dict[str, Any]]] = None,
    max_tokens: int = 500,
    temperature: float = 0.2,
) -> str:
    """Generate text with Bedrock Runtime Claude model."""
    runtime = boto3.client("bedrock-runtime", region_name=get_region())
    content_blocks: list[dict[str, Any]] = list(patch_image_blocks or [])
    content_blocks.append({"type": "text", "text": _build_user_prompt(prompt)})

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "system": SYSTEM_PROMPT,
        "max_tokens": int(max_tokens),
        "temperature": float(temperature),
        "messages": [
            {"role": "user", "content": content_blocks},
        ],
    }
    resp = runtime.invoke_model(
        # `modelId` supports both foundation model ids and inference profile
        # ARNs. We choose based on env configuration in `backend.config`.
        modelId=bedrock_invoke_model_id(),
        body=json.dumps(body),
        accept="application/json",
        contentType="application/json",
    )
    return _extract_text_from_invoke_response(resp)


def generate_explanation(
    *,
    source_image: str,
    prediction: int,
    mean_prob: float,
    patches_info: list[dict[str, Any]],
    patch_probs: list[float],
    retrieval_query: str,
    top_k_patches: int = 5,
    top_k_kb: int = 7,
    kb_candidate_k: Optional[int] = 30,
    kb_search_type: str = "HYBRID",
    artist_name: Optional[str] = None,
    artwork_name: Optional[str] = None,
    max_generation_tokens: int = 500,
    temperature: float = 0.2,
    include_patch_images: bool = True,
    max_patch_images: int = 8,
    include_overall_image: bool = True,
    strict_patch_images: bool = False,
    min_patch_images: int = 1,
) -> GenerationResult:
    """End-to-end generation helper for the RAG pipeline."""
    kb_chunks = retrieve_top_chunks(
        retrieval_query,
        top_k=top_k_kb,
        candidate_k=kb_candidate_k,
        snippet_chars=500,
        search_type=kb_search_type,
    )
    kb_snippets = [c.snippet for c in kb_chunks]

    overall_image_attached = bool(include_overall_image and source_image.startswith("s3://"))
    formatted_input = build_generation_input(
        source_image=source_image,
        prediction=prediction,
        mean_prob=mean_prob,
        patches_info=patches_info,
        patch_probs=patch_probs,
        retrieved_kb_chunks=kb_chunks,
        top_k_patches=top_k_patches,
        max_kb_chars=500,
        artist_name=artist_name,
        artwork_name=artwork_name,
        overall_image_attached=overall_image_attached,
    )

    selected_evidence = top_k_patch_evidence(
        patches_info,
        patch_probs,
        prediction=prediction,
        top_k=top_k_patches,
    )
    patch_image_uris = [p.patch_path for p in selected_evidence if p.patch_path.startswith("s3://")]

    patch_image_blocks: list[dict[str, Any]] = []
    used_patch_image_uris: list[str] = []
    if include_patch_images and patch_image_uris:
        patch_image_blocks, used_patch_image_uris = _load_patch_image_blocks(
            patch_image_uris,
            max_images=max_patch_images,
        )
    if strict_patch_images:
        required = max(1, int(min_patch_images))
        if len(used_patch_image_uris) < required:
            raise RuntimeError(
                f"Only {len(used_patch_image_uris)} patch images were attached; "
                f"required at least {required}."
            )

    overall_image_blocks: list[dict[str, Any]] = []
    if include_overall_image:
        overall_image_blocks, _ = _load_single_image_block(source_image)

    response_text = _generate_with_claude(
        formatted_input,
        patch_image_blocks=(overall_image_blocks + patch_image_blocks),
        max_tokens=max_generation_tokens,
        temperature=temperature,
    )

    return GenerationResult(
        response_text=response_text,
        formatted_input=formatted_input,
        retrieved_kb_chunks=kb_snippets,
        used_patch_image_uris=used_patch_image_uris,
    )

