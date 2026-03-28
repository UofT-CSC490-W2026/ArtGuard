/**
 * Display logic aligned with backend Modal inference:
 * - `score` = mean patch probability of **authenticity** (0–1), higher = more authentic.
 * - `prediction` = 1 authentic, 0 forgery, -1 / missing = no binary label yet.
 */

import type { AnalysisResult } from "../types";
import { AlertCircle, AlertTriangle, CheckCircle, type LucideIcon } from "lucide-react";

export type VerdictDisplay = {
  text: string;
  icon: LucideIcon;
  color: string;
  bgColor: string;
  borderColor: string;
};

/** Explicit backend failure or placeholder row (0 / -1 / no explanation) from a failed run. */
export function isInferenceFailed(r: AnalysisResult): boolean {
  if (r.inferenceStatus === "failed") return true;
  if (r.inferenceStatus === "completed" || r.inferenceStatus === "processing") {
    return false;
  }
  if (
    r.prediction === -1 &&
    r.score === 0 &&
    !(r.explanation && String(r.explanation).trim())
  ) {
    return true;
  }
  return false;
}

function verdictError(): VerdictDisplay {
  return {
    text: "Error",
    icon: AlertCircle,
    color: "text-negative",
    bgColor: "bg-negative-muted",
    borderColor: "border-negative-border",
  };
}

function verdictUnavailable(): VerdictDisplay {
  return {
    text: "Unavailable",
    icon: AlertTriangle,
    color: "text-caution",
    bgColor: "bg-caution-muted",
    borderColor: "border-caution-border",
  };
}

/** Binary model label: Authentic, Forgery, Error (inference failed), or Unavailable (no 0/1 yet). */
export function getAnalysisVerdict(r: AnalysisResult): VerdictDisplay {
  if (isInferenceFailed(r)) return verdictError();

  const p = r.prediction;
  if (p === 1) {
    return {
      text: "Authentic",
      icon: CheckCircle,
      color: "text-positive",
      bgColor: "bg-positive-muted",
      borderColor: "border-positive-border",
    };
  }
  if (p === 0) {
    return {
      text: "Forgery",
      icon: AlertCircle,
      color: "text-negative",
      bgColor: "bg-negative-muted",
      borderColor: "border-negative-border",
    };
  }

  return verdictUnavailable();
}

export function formatAnalysisScorePercent(r: AnalysisResult): string {
  if (isInferenceFailed(r)) return "—";
  return (r.score * 100).toFixed(1);
}

export function matchesAuthenticFilter(r: AnalysisResult): boolean {
  if (isInferenceFailed(r)) return false;
  return r.prediction === 1;
}

export function matchesForgedFilter(r: AnalysisResult): boolean {
  if (isInferenceFailed(r)) return false;
  return r.prediction === 0;
}

export function matchesUncertainFilter(r: AnalysisResult): boolean {
  if (isInferenceFailed(r)) return false;
  return r.prediction !== 1 && r.prediction !== 0;
}

export function matchesFailedInferenceFilter(r: AnalysisResult): boolean {
  return isInferenceFailed(r);
}

export function getBatchIndicator(r: AnalysisResult) {
  if (isInferenceFailed(r)) {
    return { icon: AlertCircle, color: "text-muted-foreground", label: "Error" };
  }
  if (r.prediction === 1) {
    return { icon: CheckCircle, color: "text-positive", label: "Authentic" };
  }
  if (r.prediction === 0) {
    return { icon: AlertCircle, color: "text-negative", label: "Forgery" };
  }
  return { icon: AlertTriangle, color: "text-caution", label: "Unavailable" };
}

/**
 * Text to show in the explanation panel: real `explanation` from the API when present;
 * otherwise a factual inference-failure line, or a fallback — never score-based narrative as a substitute for RAG.
 */
export function resolveDisplayedExplanation(r: AnalysisResult): string {
  const raw = r.explanation != null ? String(r.explanation).trim() : "";
  if (raw) return raw;
  if (isInferenceFailed(r)) {
    const detail = r.inferenceError?.trim();
    return detail ? `Inference did not complete. ${detail}` : "Inference did not complete.";
  }
  return "A retrieval-augmented explanation was not available for this analysis. Refer to the authenticity score and patch heatmap above for the model\u2019s quantitative assessment.";
}
