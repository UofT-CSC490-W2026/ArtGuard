import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../contexts/AuthContext";
import type { AnalysisResult } from "../types";
import { HistoryPage } from "./HistoryPage";
import * as client from "../api/client";
import * as inferencesApi from "../api/inferencesApi";

function makeResult(overrides: Partial<AnalysisResult> = {}): AnalysisResult {
  return {
    id: `id-${Math.random()}`,
    score: 0.75,
    image: "",
    artistName: "Monet",
    artworkName: "Water Lilies",
    timestamp: new Date().toISOString(),
    fileName: "test.jpg",
    fileSize: 1024,
    prediction: 1,
    inferenceStatus: "completed",
    ...overrides,
  };
}

function renderHistory(userId = "u1") {
  localStorage.setItem("artguard_user", JSON.stringify({ id: userId, username: "test", email: "t@t.com" }));
  return render(
    <MemoryRouter initialEntries={["/history"]}>
      <AuthProvider>
        <Routes>
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/results" element={<div data-testid="results-page">Results</div>} />
          <Route path="/upload" element={<div data-testid="upload-page">Upload</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("HistoryPage", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
    vi.spyOn(client, "hasApiBackend").mockReturnValue(false);
  });

  it("shows empty state when no history", async () => {
    renderHistory();
    await waitFor(() => expect(screen.getByText(/no analysis history yet/i)).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /upload artwork/i })).toBeInTheDocument();
  });

  it("shows history items from localStorage", async () => {
    const result = makeResult({ artworkName: "Starry Night", artistName: "Van Gogh" });
    localStorage.setItem("artguard_history_u1", JSON.stringify([result]));
    renderHistory();
    await waitFor(() => expect(screen.getByText("Starry Night")).toBeInTheDocument());
    expect(screen.getByText(/van gogh/i)).toBeInTheDocument();
  });

  it("shows score percentage for completed inference", async () => {
    const result = makeResult({ score: 0.85, prediction: 1, inferenceStatus: "completed" });
    localStorage.setItem("artguard_history_u1", JSON.stringify([result]));
    renderHistory();
    await waitFor(() => expect(screen.getByText(/85\.0%/)).toBeInTheDocument());
  });

  it("view details navigates to results page", async () => {
    const result = makeResult();
    localStorage.setItem("artguard_history_u1", JSON.stringify([result]));
    renderHistory();
    await waitFor(() => expect(screen.getByRole("button", { name: /view details/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /view details/i }));
    await waitFor(() => expect(screen.getByTestId("results-page")).toBeInTheDocument());
  });

  it("delete removes item from history", async () => {
    const result = makeResult({ artworkName: "Mona Lisa" });
    localStorage.setItem("artguard_history_u1", JSON.stringify([result]));
    renderHistory();
    await waitFor(() => expect(screen.getByText("Mona Lisa")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /delete/i }));
    await waitFor(() => expect(screen.queryByText("Mona Lisa")).not.toBeInTheDocument());
    expect(screen.getByText(/no analysis history yet/i)).toBeInTheDocument();
  });

  it("search filters by artist name", async () => {
    const results = [
      makeResult({ artworkName: "Water Lilies", artistName: "Monet" }),
      makeResult({ artworkName: "Guernica", artistName: "Picasso" }),
    ];
    localStorage.setItem("artguard_history_u1", JSON.stringify(results));
    renderHistory();
    await waitFor(() => expect(screen.getByText("Water Lilies")).toBeInTheDocument());

    const searchInput = screen.getByPlaceholderText(/search artist/i);
    fireEvent.change(searchInput, { target: { value: "Monet" } });

    await waitFor(() => expect(screen.getByText("Water Lilies")).toBeInTheDocument());
    expect(screen.queryByText("Guernica")).not.toBeInTheDocument();
  });

  it("search filters by artwork name", async () => {
    const results = [
      makeResult({ artworkName: "Water Lilies", artistName: "Monet" }),
      makeResult({ artworkName: "Guernica", artistName: "Picasso" }),
    ];
    localStorage.setItem("artguard_history_u1", JSON.stringify(results));
    renderHistory();
    await waitFor(() => expect(screen.getByText("Guernica")).toBeInTheDocument());

    const searchInput = screen.getByPlaceholderText(/search artist/i);
    fireEvent.change(searchInput, { target: { value: "Guernica" } });

    await waitFor(() => expect(screen.getByText("Guernica")).toBeInTheDocument());
    expect(screen.queryByText("Water Lilies")).not.toBeInTheDocument();
  });

  it("shows no results found when search has no matches", async () => {
    const result = makeResult({ artworkName: "Water Lilies" });
    localStorage.setItem("artguard_history_u1", JSON.stringify([result]));
    renderHistory();
    await waitFor(() => expect(screen.getByText("Water Lilies")).toBeInTheDocument());

    const searchInput = screen.getByPlaceholderText(/search artist/i);
    fireEvent.change(searchInput, { target: { value: "zzznomatch" } });

    await waitFor(() => expect(screen.getByText(/no results found/i)).toBeInTheDocument());
  });

  it("shows failed inference badge for failed status", async () => {
    const result = makeResult({
      prediction: -1,
      score: 0,
      inferenceStatus: "failed",
      inferenceError: "Model unavailable",
    });
    localStorage.setItem("artguard_history_u1", JSON.stringify([result]));
    renderHistory();
    await waitFor(() => expect(screen.getByText(/error/i)).toBeInTheDocument());
  });

  it("shows result count when items are visible", async () => {
    const results = [makeResult(), makeResult()];
    localStorage.setItem("artguard_history_u1", JSON.stringify(results));
    renderHistory();
    await waitFor(() => expect(screen.getByText(/showing 2 of 2/i)).toBeInTheDocument());
  });

  it("clear all button appears when history has items", async () => {
    const result = makeResult();
    localStorage.setItem("artguard_history_u1", JSON.stringify([result]));
    renderHistory();
    await waitFor(() => expect(screen.getByRole("button", { name: /clear all/i })).toBeInTheDocument());
  });

  it("handles corrupted localStorage gracefully", async () => {
    localStorage.setItem("artguard_history_u1", "not-valid-json{{{");
    renderHistory();
    await waitFor(() => expect(screen.getByText(/no analysis history yet/i)).toBeInTheDocument());
  });

  it("sort by score-high puts highest score first", async () => {
    const user = userEvent.setup();
    const results = [
      makeResult({ artworkName: "Low Score", score: 0.2, prediction: 0 }),
      makeResult({ artworkName: "High Score", score: 0.9, prediction: 1 }),
    ];
    localStorage.setItem("artguard_history_u1", JSON.stringify(results));
    renderHistory();
    await waitFor(() => expect(screen.getByText("Low Score")).toBeInTheDocument());

    const sortTrigger = screen.getAllByRole("combobox")[1];
    await user.click(sortTrigger);
    await user.click(await screen.findByRole("option", { name: /highest score/i }));

    await waitFor(() => {
      const items = screen.getAllByRole("heading", { level: 3 });
      expect(items[0].textContent).toBe("High Score");
    });
  });

  it("filter by authentic shows only authentic results", async () => {
    const user = userEvent.setup();
    const results = [
      makeResult({ artworkName: "Authentic Work", prediction: 1, inferenceStatus: "completed" }),
      makeResult({ artworkName: "Forged Work", prediction: 0, inferenceStatus: "completed" }),
    ];
    localStorage.setItem("artguard_history_u1", JSON.stringify(results));
    renderHistory();
    await waitFor(() => expect(screen.getByText("Authentic Work")).toBeInTheDocument());

    await user.click(screen.getAllByRole("combobox")[0]);
    await user.click(await screen.findByRole("option", { name: /likely authentic/i }));

    await waitFor(() => expect(screen.getByText("Authentic Work")).toBeInTheDocument());
    expect(screen.queryByText("Forged Work")).not.toBeInTheDocument();
  });

  it("filter by forged shows only forged results", async () => {
    const user = userEvent.setup();
    const results = [
      makeResult({ artworkName: "Authentic Work", prediction: 1, inferenceStatus: "completed" }),
      makeResult({ artworkName: "Forged Work", prediction: 0, inferenceStatus: "completed" }),
    ];
    localStorage.setItem("artguard_history_u1", JSON.stringify(results));
    renderHistory();
    await waitFor(() => expect(screen.getByText("Forged Work")).toBeInTheDocument());

    await user.click(screen.getAllByRole("combobox")[0]);
    await user.click(await screen.findByRole("option", { name: /likely forgery/i }));

    await waitFor(() => expect(screen.getByText("Forged Work")).toBeInTheDocument());
    expect(screen.queryByText("Authentic Work")).not.toBeInTheDocument();
  });

  it("filter by uncertain shows only uncertain results", async () => {
    const user = userEvent.setup();
    const results = [
      makeResult({
        artworkName: "Uncertain Work",
        prediction: -1,
        score: 0.5,
        explanation: "x",
        inferenceStatus: "completed",
      }),
      makeResult({ artworkName: "Authentic Work", prediction: 1, inferenceStatus: "completed" }),
    ];
    localStorage.setItem("artguard_history_u1", JSON.stringify(results));
    renderHistory();
    await waitFor(() => expect(screen.getByText("Uncertain Work")).toBeInTheDocument());

    await user.click(screen.getAllByRole("combobox")[0]);
    await user.click(await screen.findByRole("option", { name: /^uncertain$/i }));

    await waitFor(() => expect(screen.getByText("Uncertain Work")).toBeInTheDocument());
    expect(screen.queryByText("Authentic Work")).not.toBeInTheDocument();
  });

  it("filter by failed shows only failed results", async () => {
    const user = userEvent.setup();
    const results = [
      makeResult({ artworkName: "Failed Work", prediction: -1, score: 0, inferenceStatus: "failed" }),
      makeResult({ artworkName: "Good Work", prediction: 1, inferenceStatus: "completed" }),
    ];
    localStorage.setItem("artguard_history_u1", JSON.stringify(results));
    renderHistory();
    await waitFor(() => expect(screen.getByText("Failed Work")).toBeInTheDocument());

    await user.click(screen.getAllByRole("combobox")[0]);
    await user.click(await screen.findByRole("option", { name: /inference failed/i }));

    await waitFor(() => expect(screen.getByText("Failed Work")).toBeInTheDocument());
    expect(screen.queryByText("Good Work")).not.toBeInTheDocument();
  });
});

describe("HistoryPage API backend", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
    vi.spyOn(client, "hasApiBackend").mockReturnValue(true);
    vi.spyOn(client, "getAccessToken").mockReturnValue("tok");
    vi.spyOn(client.api, "get").mockResolvedValue({
      id: "u1",
      username: "test",
      email: "t@t.com",
    });
  });

  it("shows error when list inferences fails", async () => {
    vi.spyOn(inferencesApi, "listInferences").mockRejectedValue(new Error("Service unavailable"));
    renderHistory();
    await waitFor(() => expect(screen.getByText(/service unavailable/i)).toBeInTheDocument());
  });

  it("renders list from API and loads more with cursor", async () => {
    const user = userEvent.setup();
    const baseItem: inferencesApi.InferenceListItem = {
      inference_id: "inf-1",
      created_at: Date.now(),
      score: 0.8,
      prediction: 1,
      artist_name: "API Artist",
      artwork_name: "API Work",
      image_name: "a.png",
      file_size: 100,
      image_url: "",
      inference_status: "completed",
    };
    const listSpy = vi
      .spyOn(inferencesApi, "listInferences")
      .mockResolvedValueOnce({ items: [baseItem], next_cursor: "c2" })
      .mockResolvedValueOnce({
        items: [{ ...baseItem, inference_id: "inf-2", artwork_name: "Second Work" }],
        next_cursor: null,
      });

    renderHistory();
    await waitFor(() => expect(screen.getByText("API Work")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /load more/i }));
    await waitFor(() => expect(screen.getByText("Second Work")).toBeInTheDocument());
    expect(listSpy).toHaveBeenCalledWith(50);
    expect(listSpy).toHaveBeenCalledWith(50, "c2");
  });
});
