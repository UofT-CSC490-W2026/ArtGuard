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

export function getAuthenticityBarColor(score: number): string {
  if (score >= 0.7) return "bg-bar-positive";
  if (score <= 0.3) return "bg-bar-negative";
  return "bg-bar-caution";
}

export function getAnalysisBarColor(r: AnalysisResult): string {
  if (isInferenceFailed(r)) return "bg-bar-muted";
  return getAuthenticityBarColor(r.score);
}

export function formatAnalysisScorePercent(r: AnalysisResult): string {
  if (isInferenceFailed(r)) return "—";
  return (r.score * 100).toFixed(1);
}

export function primaryScoreTitle(r: AnalysisResult): string {
  if (isInferenceFailed(r)) return "Inference failed";
  return "Authenticity confidence";
}

export function primaryScoreDescription(r: AnalysisResult): string {
  if (isInferenceFailed(r)) {
    return "The model did not return a score for this upload. See below for details or try again later.";
  }
  return "Mean probability across patches that the artwork is authentic (higher = stronger authenticity cues). The model also returns a binary prediction (Authentic or Forgery).";
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

export function generateFallbackExplanation(r: AnalysisResult): string {
  if (isInferenceFailed(r)) {
    const detail = r.inferenceError?.trim();
    return detail
      ? `Inference did not complete. ${detail}`
      : "Inference did not complete (for example the model service was unavailable). This entry does not contain a real authenticity score—try analyzing again later.";
  }

  const s = r.score;
  const p = r.prediction;

  if (p === 1) {
    return `Patch-level analysis suggests cues more consistent with authentic work (mean authenticity probability ${(s * 100).toFixed(1)}%). This is not a certificate of authenticity—consult experts for high-value pieces.`;
  }
  if (p === 0) {
    return `Patch-level analysis suggests cues more consistent with forgery or reproduction (mean authenticity probability ${(s * 100).toFixed(1)}%). False positives occur; seek professional verification before conclusions.`;
  }

  if (s > 0.7) {
    return `Mean patch authenticity probability is ${(s * 100).toFixed(1)}%, but a binary model label was not available. Treat as indicative only and seek expert review.`;
  }
  if (s < 0.3) {
    return `Mean patch authenticity probability is ${(s * 100).toFixed(1)}%, but a binary model label was not available. False positives occur; seek professional verification before conclusions.`;
  }
  return `Results are mixed or borderline (mean authenticity probability ${(s * 100).toFixed(1)}%). A binary model label was not available—we recommend further review by qualified conservators or forensic specialists.`;
}
