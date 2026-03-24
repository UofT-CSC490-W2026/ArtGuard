"""POST /rag-query -- TEST endpoint to query the Bedrock Knowledge Base.

Sends a free-text query to the configured AWS Bedrock Knowledge Base
(RAG) and returns the generated answer along with source citations.
"""

from __future__ import annotations

import logging
import os
from typing import List

import boto3
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.apps.backend.config import bedrock_model_arn, get_region
from src.apps.backend.validation import RAG_QUERY_MAX

logger = logging.getLogger(__name__)

router = APIRouter(tags=["rag"])


class RAGQueryRequest(BaseModel):
    """Request body for POST /rag-query.

    Attributes:
        query: Free-text question to send to the Knowledge Base.
    """

    query: str = Field(..., min_length=1, max_length=RAG_QUERY_MAX)


class RAGSource(BaseModel):
    """A single citation source from the Knowledge Base."""

    s3_uri: str = ""
    snippet: str = ""


class RAGQueryResponse(BaseModel):
    """Response from a POST /rag-query call.

    Attributes:
        answer:  Generated text answer from the Knowledge Base.
        sources: List of citation sources with S3 URI and text snippet.
    """

    answer: str
    sources: List[RAGSource]


@router.post("/rag-query", response_model=RAGQueryResponse)
async def rag_query(body: RAGQueryRequest) -> RAGQueryResponse:
    """Query the Bedrock Knowledge Base and return the generated answer with sources.

    Uses the Bedrock ``retrieve_and_generate`` API with the Claude 3 Haiku
    foundation model. Extracts source citations from the response and returns
    truncated snippets (up to 200 characters each).

    Raises:
        HTTPException 500: If the KNOWLEDGE_BASE_ID env var is not set or
                           the Bedrock call fails.
    """
    knowledge_base_id = os.getenv("KNOWLEDGE_BASE_ID")
    if not knowledge_base_id:
        raise HTTPException(
            status_code=500,
            detail="Knowledge Base is not configured. Please contact support.",
        )

    region = get_region()

    try:
        bedrock = boto3.client("bedrock-agent-runtime", region_name=region)
        resp = bedrock.retrieve_and_generate(
            input={"text": body.query},
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": knowledge_base_id,
                    "modelArn": bedrock_model_arn(),
                },
            },
        )
    except Exception as exc:
        logger.error("Bedrock RAG query failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="The knowledge base query failed. Please try again later.",
        )

    answer = resp.get("output", {}).get("text", "")
    citations = resp.get("citations", [])
    sources: List[RAGSource] = []
    for citation in citations:
        for ref in citation.get("retrievedReferences", []):
            loc = ref.get("location", {})
            s3_uri = loc.get("s3Location", {}).get("uri", "")
            snippet = ref.get("content", {}).get("text", "")[:200]
            sources.append(RAGSource(s3_uri=s3_uri, snippet=snippet))

    return RAGQueryResponse(answer=answer, sources=sources)
