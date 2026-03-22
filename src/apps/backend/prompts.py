"""Prompt templates for RAG and LLM interactions.

Centralizes all prompt text so templates can be tuned in one place
without modifying service logic. Each function returns a fully
formatted prompt string ready to send to the model.

To add a new prompt:
  1. Define a new function here that returns a formatted string.
  2. Import and call it from inference_service.py (or any other service).
  This keeps prompt engineering separate from business logic.
"""

from __future__ import annotations


def rag_explanation_prompt(prediction: int, score: float) -> str:
    """Build the RAG prompt for explaining an inference result.

    Args:
        prediction: 1 = authentic, 0 = forgery.
        score:      Mean patch probability (0.0 - 1.0).

    Returns:
        A formatted prompt string for the Bedrock Knowledge Base.

    >>> rag_explanation_prompt(1, 0.92)
    'The forgery detection model analyzed an artwork and predicted it is authentic with a confidence score of 0.92. Provide context about art forgery detection techniques and what this result might mean.'
    >>> rag_explanation_prompt(0, 0.35)
    'The forgery detection model analyzed an artwork and predicted it is a potential forgery with a confidence score of 0.35. Provide context about art forgery detection techniques and what this result might mean.'
    """
    label = "authentic" if prediction == 1 else "a potential forgery"
    return (
        f"The forgery detection model analyzed an artwork and predicted it is "
        f"{label} with a confidence score of {score:.2f}. "
        f"Provide context about art forgery detection techniques and what this "
        f"result might mean."
    )
