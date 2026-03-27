import { describe, expect, it } from "vitest";
import { buildAnalysisPdf } from "./pdfReport";

describe("buildAnalysisPdf", () => {
  it("builds a minimal PDF blob", async () => {
    const blob = await buildAnalysisPdf({
      artworkName: "W",
      artistName: "A",
      fileName: "f.png",
      analyzedAt: "2024-01-01",
      scoreLine: "Score: 50%",
      predLine: "Pred: x",
      verdict: "Uncertain",
      explanation: "Short",
    });
    expect(blob.type).toBe("application/pdf");
    expect(blob.size).toBeGreaterThan(100);
  });

  it("embeds PNG data URL and survives addImage failure", async () => {
    const png =
      "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQImWNgYAAAAAMAASsJTYQAAAAASUVORK5CYII=";
    const blob = await buildAnalysisPdf({
      artworkName: "W",
      artistName: "A",
      fileName: "f.png",
      analyzedAt: "2024-01-01",
      scoreLine: "S",
      predLine: "",
      verdict: "V",
      explanation: "E",
      imageDataUrl: png,
    });
    expect(blob.size).toBeGreaterThan(100);
  });

  it("uses JPEG format hint for non-png data URLs", async () => {
    const blob = await buildAnalysisPdf({
      artworkName: "W",
      artistName: "A",
      fileName: "f.jpg",
      analyzedAt: "2024-01-01",
      scoreLine: "S",
      predLine: "",
      verdict: "V",
      explanation: "E",
      imageDataUrl: "data:image/jpeg;base64,AAAA",
    });
    expect(blob.size).toBeGreaterThan(100);
  });

  it("paginates very long explanations across pages", async () => {
    const long = "word ".repeat(2000);
    const blob = await buildAnalysisPdf({
      artworkName: "W",
      artistName: "A",
      fileName: "f.png",
      analyzedAt: "2024-01-01",
      scoreLine: "S",
      predLine: "P",
      verdict: "V",
      explanation: long,
    });
    expect(blob.size).toBeGreaterThan(5000);
  });
});
