import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "@/app/contexts/AuthContext";
import type { AnalysisResult } from "@/app/types";
import { ResultsPage } from "@/app/pages/ResultsPage";

function renderAtResults() {
  return render(
    <MemoryRouter initialEntries={["/results"]}>
      <AuthProvider>
        <Routes>
          <Route path="/results" element={<ResultsPage />} />
          <Route path="/upload" element={<div data-testid="upload-dest">up</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("ResultsPage", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("redirects to upload when no stored result", async () => {
    renderAtResults();
    await waitFor(() => expect(screen.getByTestId("upload-dest")).toBeInTheDocument());
  });

  it("redirects when stored JSON is invalid", async () => {
    localStorage.setItem("artguard_latest_result", "{");
    renderAtResults();
    await waitFor(() => expect(screen.getByTestId("upload-dest")).toBeInTheDocument());
  });

  it("renders stored analysis with explanation and patch overlay when patch data exists", async () => {
    const result: AnalysisResult = {
      id: "1",
      score: 0.72,
      image: "data:image/png;base64,AAAA",
      artistName: "A",
      artworkName: "B",
      timestamp: new Date().toISOString(),
      fileName: "f.png",
      fileSize: 10,
      explanation: "From API",
      prediction: 1,
      patchData: [{ x: 0, y: 0, w: 10, h: 10, prob: 0.5 }],
    };
    localStorage.setItem("artguard_latest_result", JSON.stringify(result));
    renderAtResults();
    await waitFor(() => expect(screen.getByText("AUTHENTICITY CONFIDENCE")).toBeInTheDocument());
    expect(screen.getByText("From API")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText(/patch authenticity heatmap/i)).toBeInTheDocument(),
    );
  });

  it("shows fallback explanation when RAG text is missing", async () => {
    const result: AnalysisResult = {
      id: "1",
      score: 0.5,
      image: "",
      artistName: "A",
      artworkName: "B",
      timestamp: new Date().toISOString(),
      fileName: "f.png",
      fileSize: 10,
      prediction: 1,
      inferenceStatus: "completed",
    };
    localStorage.setItem("artguard_latest_result", JSON.stringify(result));
    renderAtResults();
    await waitFor(() => expect(screen.getByText(/retrieval-augmented explanation was not available/)).toBeInTheDocument());
  });

  it("shows dash for failed inference score", async () => {
    const result: AnalysisResult = {
      id: "1",
      score: 0,
      image: "",
      artistName: "A",
      artworkName: "B",
      timestamp: new Date().toISOString(),
      fileName: "f.png",
      fileSize: 10,
      prediction: -1,
      inferenceStatus: "failed",
      inferenceError: "Model unavailable",
    };
    localStorage.setItem("artguard_latest_result", JSON.stringify(result));
    renderAtResults();
    await waitFor(() => expect(screen.getByText("-")).toBeInTheDocument());
  });

  it("download calls print", async () => {
    const print = vi.fn();
    vi.stubGlobal("print", print);

    const result: AnalysisResult = {
      id: "1",
      score: 0.5,
      image: "data:image/png;base64,AAAA",
      artistName: "A",
      artworkName: "B",
      timestamp: new Date().toISOString(),
      fileName: "f.png",
      fileSize: 10,
      prediction: 0,
    };
    localStorage.setItem("artguard_latest_result", JSON.stringify(result));
    renderAtResults();
    await waitFor(() => expect(screen.getByRole("button", { name: /^download$/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /^download$/i }));
    expect(print).toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
