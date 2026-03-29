import { describe, expect, it } from "vitest";
import type { AnalysisResult } from "@/app/types";
import {
  formatAnalysisScorePercent,
  getAnalysisVerdict,
  getBatchIndicator,
  isInferenceFailed,
  matchesAuthenticFilter,
  matchesForgedFilter,
  matchesUncertainFilter,
  matchesFailedInferenceFilter,
  resolveDisplayedExplanation,
} from "@/app/lib/analysisDisplay";

function baseResult(overrides: Partial<AnalysisResult> = {}): AnalysisResult {
  return {
    id: "1",
    score: 0.75,
    image: "",
    artistName: "A",
    artworkName: "B",
    timestamp: "",
    fileName: "f.jpg",
    fileSize: 1,
    ...overrides,
  };
}

describe("isInferenceFailed", () => {
  it("returns true for explicit failed status", () => {
    expect(isInferenceFailed(baseResult({ inferenceStatus: "failed" }))).toBe(true);
  });

  it("returns false for completed or processing", () => {
    expect(isInferenceFailed(baseResult({ inferenceStatus: "completed" }))).toBe(false);
    expect(isInferenceFailed(baseResult({ inferenceStatus: "processing" }))).toBe(false);
  });

  it("returns true for placeholder failed row", () => {
    expect(
      isInferenceFailed(
        baseResult({
          prediction: -1,
          score: 0,
          explanation: "",
        }),
      ),
    ).toBe(true);
  });
});

describe("getAnalysisVerdict", () => {
  it("returns Authentic for prediction 1 when not failed", () => {
    const v = getAnalysisVerdict(baseResult({ prediction: 1, score: 0.8 }));
    expect(v.text).toBe("Authentic");
  });

  it("returns Forgery for prediction 0", () => {
    const v = getAnalysisVerdict(baseResult({ prediction: 0, score: 0.2 }));
    expect(v.text).toBe("Forgery");
  });

  it("returns Unavailable when prediction is not 0 or 1", () => {
    const v = getAnalysisVerdict(baseResult({ prediction: -1, score: 0.5, explanation: "x" }));
    expect(v.text).toBe("Unavailable");
  });

  it("returns Error when inference failed", () => {
    const v = getAnalysisVerdict(baseResult({ inferenceStatus: "failed", score: 0 }));
    expect(v.text).toBe("Error");
  });
});

describe("score helpers", () => {
  it("formatAnalysisScorePercent shows dash when failed", () => {
    expect(formatAnalysisScorePercent(baseResult({ inferenceStatus: "failed" }))).toBe("-");
    expect(formatAnalysisScorePercent(baseResult({ score: 0.333 }))).toBe("33.3");
  });
});

describe("filters", () => {
  it("matchesAuthenticFilter and matchesForgedFilter", () => {
    expect(matchesAuthenticFilter(baseResult({ prediction: 1 }))).toBe(true);
    expect(matchesForgedFilter(baseResult({ prediction: 0 }))).toBe(true);
    expect(matchesAuthenticFilter(baseResult({ inferenceStatus: "failed" }))).toBe(false);
  });

  it("matchesUncertainFilter returns true when prediction is not 0 or 1", () => {
    expect(matchesUncertainFilter(baseResult({ prediction: -1, score: 0.5, explanation: "x" }))).toBe(true);
    expect(matchesUncertainFilter(baseResult({ prediction: 1 }))).toBe(false);
    expect(matchesUncertainFilter(baseResult({ prediction: 0 }))).toBe(false);
    expect(matchesUncertainFilter(baseResult({ inferenceStatus: "failed" }))).toBe(false);
  });

  it("matchesFailedInferenceFilter returns true only for failed runs", () => {
    expect(matchesFailedInferenceFilter(baseResult({ inferenceStatus: "failed" }))).toBe(true);
    expect(matchesFailedInferenceFilter(baseResult({ inferenceStatus: "completed", prediction: 1 }))).toBe(false);
  });
});

describe("resolveDisplayedExplanation", () => {
  it("returns API explanation when present", () => {
    expect(resolveDisplayedExplanation(baseResult({ explanation: "  RAG text  " }))).toBe("RAG text");
  });

  it("returns fallback when completed run has no explanation text", () => {
    expect(
      resolveDisplayedExplanation(
        baseResult({ inferenceStatus: "completed", prediction: 1, score: 0.9 }),
      ),
    ).toContain("retrieval-augmented explanation was not available");
  });

  it("treats whitespace-only explanation as missing", () => {
    expect(resolveDisplayedExplanation(baseResult({ explanation: "   " }))).toContain("retrieval-augmented explanation was not available");
  });

  it("includes inference error when failed with detail", () => {
    const text = resolveDisplayedExplanation(
      baseResult({ inferenceStatus: "failed", inferenceError: "timeout" }),
    );
    expect(text).toContain("timeout");
  });

  it("returns short message when failed without detail", () => {
    expect(resolveDisplayedExplanation(baseResult({ inferenceStatus: "failed" }))).toBe(
      "Inference did not complete.",
    );
  });
});

describe("getBatchIndicator", () => {
  it("returns Unavailable when prediction is neither 0 nor 1", () => {
    const b = getBatchIndicator(baseResult({ prediction: -1, score: 0.5, explanation: "x" }));
    expect(b.label).toBe("Unavailable");
  });

  it("returns Authentic for prediction 1", () => {
    const b = getBatchIndicator(baseResult({ prediction: 1, score: 0.9 }));
    expect(b.label).toBe("Authentic");
  });

  it("returns Forgery for prediction 0", () => {
    const b = getBatchIndicator(baseResult({ prediction: 0, score: 0.1 }));
    expect(b.label).toBe("Forgery");
  });

  it("returns Error for failed inference", () => {
    const b = getBatchIndicator(baseResult({ inferenceStatus: "failed" }));
    expect(b.label).toBe("Error");
  });
});
