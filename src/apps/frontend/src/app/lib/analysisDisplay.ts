/**
 * Display logic aligned with backend Modal inference:
 * - `score` = mean patch probability of **authenticity** (0–1), higher = more authentic.
 * - `prediction` = 1 authentic, 0 forgery, -1 unknown/pending.
 * Legacy localStorage rows may use `scoreSemantics: "legacy_forgery"` (high score = more forged).
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

export function usesAuthenticitySemantics(r: AnalysisResult): boolean {
  return r.scoreSemantics === "authenticity";
}

/** Explicit backend failure or legacy placeholder row (0 / -1 / no explanation) from a failed run. */
export function isInferenceFailed(r: AnalysisResult): boolean {
  if (r.inferenceStatus === "failed") return true;
  if (r.inferenceStatus === "completed" || r.inferenceStatus === "processing") {
    return false;
  }
  // Legacy rows (no inference_status): same placeholders we write before Modal runs
  if (
    usesAuthenticitySemantics(r) &&
    r.prediction === -1 &&
    r.score === 0 &&
    !(r.explanation && String(r.explanation).trim())
  ) {
    return true;
  }
  return false;
}

function verdictFailed(): VerdictDisplay {
  return {
    text: "Inference failed",
    icon: AlertCircle,
    color: "text-red-700",
    bgColor: "bg-red-50",
    borderColor: "border-red-200",
  };
}

function verdictAuthenticity(r: AnalysisResult): VerdictDisplay {
  if (isInferenceFailed(r)) return verdictFailed();
  const p = r.prediction;
  const s = r.score;

  if (p === 1) {
    return {
      text: "Authentic (model)",
      icon: CheckCircle,
      color: "text-green-600",
      bgColor: "bg-green-50",
      borderColor: "border-green-200",
    };
  }
  if (p === 0) {
    return {
      text: "Likely forgery (model)",
      icon: AlertCircle,
      color: "text-red-600",
      bgColor: "bg-red-50",
      borderColor: "border-red-200",
    };
  }

  if (s > 0.7) {
    return {
      text: "Likely authentic",
      icon: CheckCircle,
      color: "text-green-600",
      bgColor: "bg-green-50",
      borderColor: "border-green-200",
    };
  }
  if (s < 0.3) {
    return {
      text: "Likely forgery",
      icon: AlertCircle,
      color: "text-red-600",
      bgColor: "bg-red-50",
      borderColor: "border-red-200",
    };
  }
  return {
    text: "Uncertain / needs review",
    icon: AlertTriangle,
    color: "text-yellow-600",
    bgColor: "bg-yellow-50",
    borderColor: "border-yellow-200",
  };
}

function verdictLegacyForgery(r: AnalysisResult): VerdictDisplay {
  if (isInferenceFailed(r)) return verdictFailed();
  const s = r.score;
  if (s < 0.3) {
    return {
      text: "Likely Authentic",
      icon: CheckCircle,
      color: "text-green-600",
      bgColor: "bg-green-50",
      borderColor: "border-green-200",
    };
  }
  if (s < 0.7) {
    return {
      text: "Uncertain / Needs Review",
      icon: AlertTriangle,
      color: "text-yellow-600",
      bgColor: "bg-yellow-50",
      borderColor: "border-yellow-200",
    };
  }
  return {
    text: "Likely Forged",
    icon: AlertCircle,
    color: "text-red-600",
    bgColor: "bg-red-50",
    borderColor: "border-red-200",
  };
}

export function getAnalysisVerdict(r: AnalysisResult): VerdictDisplay {
  return usesAuthenticitySemantics(r) ? verdictAuthenticity(r) : verdictLegacyForgery(r);
}

export function getAuthenticityBarColor(score: number): string {
  if (score >= 0.7) return "bg-green-600";
  if (score <= 0.3) return "bg-red-600";
  return "bg-yellow-500";
}

export function getLegacyForgeryBarColor(score: number): string {
  if (score < 0.3) return "bg-green-600";
  if (score < 0.7) return "bg-yellow-500";
  return "bg-red-600";
}

export function getAnalysisBarColor(r: AnalysisResult): string {
  if (isInferenceFailed(r)) return "bg-gray-400";
  return usesAuthenticitySemantics(r)
    ? getAuthenticityBarColor(r.score)
    : getLegacyForgeryBarColor(r.score);
}

export function formatAnalysisScorePercent(r: AnalysisResult): string {
  if (isInferenceFailed(r)) return "—";
  return (r.score * 100).toFixed(1);
}

export function primaryScoreTitle(r: AnalysisResult): string {
  if (isInferenceFailed(r)) return "Inference failed";
  return usesAuthenticitySemantics(r) ? "Authenticity confidence" : "Detection score";
}

export function primaryScoreDescription(r: AnalysisResult): string {
  if (isInferenceFailed(r)) {
    return "The model did not return a score for this upload. See below for details or try again later.";
  }
  if (usesAuthenticitySemantics(r)) {
    return "Mean probability across patches that the artwork is authentic (higher = stronger authenticity cues). The model also returns a binary prediction (Authentic / Forgery).";
  }
  return "Older scale: lower values suggest authenticity; higher values suggest greater forgery risk.";
}

export function matchesAuthenticFilter(r: AnalysisResult): boolean {
  if (isInferenceFailed(r)) return false;
  if (usesAuthenticitySemantics(r)) {
    if (r.prediction === 0) return false;
    if (r.prediction === 1) return true;
    return r.score >= 0.7;
  }
  return r.score < 0.3;
}

export function matchesForgedFilter(r: AnalysisResult): boolean {
  if (isInferenceFailed(r)) return false;
  if (usesAuthenticitySemantics(r)) {
    if (r.prediction === 1) return false;
    if (r.prediction === 0) return true;
    return r.score <= 0.3;
  }
  return r.score >= 0.7;
}

export function matchesUncertainFilter(r: AnalysisResult): boolean {
  if (isInferenceFailed(r)) return false;
  if (usesAuthenticitySemantics(r)) {
    if (r.prediction === 1 || r.prediction === 0) return false;
    return r.score > 0.3 && r.score < 0.7;
  }
  return r.score >= 0.3 && r.score < 0.7;
}

export function matchesFailedInferenceFilter(r: AnalysisResult): boolean {
  return isInferenceFailed(r);
}

export function batchIndicatorAuthenticity(score: number): {
  icon: LucideIcon;
  color: string;
  label: string;
} {
  if (score >= 0.7) {
    return { icon: CheckCircle, color: "text-green-600", label: "Authentic" };
  }
  if (score <= 0.3) {
    return { icon: AlertCircle, color: "text-red-600", label: "Forgery" };
  }
  return { icon: AlertTriangle, color: "text-yellow-600", label: "Uncertain" };
}

export function batchIndicatorLegacy(score: number): {
  icon: LucideIcon;
  color: string;
  label: string;
} {
  if (score < 0.3) {
    return { icon: CheckCircle, color: "text-green-600", label: "Authentic" };
  }
  if (score < 0.7) {
    return { icon: AlertTriangle, color: "text-yellow-600", label: "Uncertain" };
  }
  return { icon: AlertCircle, color: "text-red-600", label: "Forged" };
}

export function getBatchIndicator(r: AnalysisResult, score: number) {
  if (isInferenceFailed(r)) {
    return { icon: AlertCircle, color: "text-gray-700", label: "Failed" };
  }
  return usesAuthenticitySemantics(r)
    ? batchIndicatorAuthenticity(score)
    : batchIndicatorLegacy(score);
}

export function generateFallbackExplanation(r: AnalysisResult): string {
  if (isInferenceFailed(r)) {
    const detail = r.inferenceError?.trim();
    return detail
      ? `Inference did not complete. ${detail}`
      : "Inference did not complete (for example the model service was unavailable). This entry does not contain a real authenticity score—try analyzing again later.";
  }
  if (usesAuthenticitySemantics(r)) {
    const s = r.score;
    const p = r.prediction;
    if (p === 1 || s > 0.7) {
      return `Patch-level analysis suggests cues more consistent with authentic work (mean authenticity probability ${(s * 100).toFixed(1)}%). This is not a certificate of authenticity—consult experts for high-value pieces.`;
    }
    if (p === 0 || s < 0.3) {
      return `Patch-level analysis suggests cues more consistent with forgery or reproduction (mean authenticity probability ${(s * 100).toFixed(1)}%). False positives occur; seek professional verification before conclusions.`;
    }
    return `Results are mixed or borderline (mean authenticity probability ${(s * 100).toFixed(1)}%). We recommend further review by qualified conservators or forensic specialists.`;
  }
  if (r.score < 0.3) {
    return `Based on our comprehensive AI analysis, this artwork shows strong characteristics consistent with authentic pieces. The brushstroke patterns, aging indicators, and material composition align well with expected authenticity markers. The pigment distribution and canvas texture demonstrate natural aging processes typical of genuine artworks. However, we recommend consulting with certified art experts for a definitive authentication, especially for high-value pieces.`;
  }
  if (r.score < 0.7) {
    return `Our analysis reveals mixed indicators that make definitive authentication challenging. While some characteristics suggest authenticity, there are certain anomalies in the brushwork consistency and material composition that warrant further investigation. The artwork displays both authentic and questionable features. We strongly recommend professional verification by certified art historians and forensic experts before making any authentication claims or purchase decisions.`;
  }
  return `Our AI analysis has detected several concerning indicators that may suggest this artwork could be a forgery or reproduction. Notable issues include inconsistencies in brushstroke patterns, unusual pigment composition, and aging characteristics that don't align with expected authentic markers. The technical execution shows patterns commonly associated with reproductions or modern forgeries. However, false positives can occur, and we strongly advise seeking multiple expert opinions and conducting forensic laboratory testing before reaching final conclusions.`;
}
