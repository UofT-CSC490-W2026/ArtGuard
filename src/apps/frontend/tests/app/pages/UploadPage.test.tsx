import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "@/app/contexts/AuthContext";
import type { AnalysisResult } from "@/app/types";
import { UploadPage } from "@/app/pages/UploadPage";
import * as client from "@/app/api/client";

const analyzeArtwork = vi.fn();

vi.mock("@/app/api/analysis", () => ({
  analyzeArtwork: (...a: unknown[]) => analyzeArtwork(...a),
}));

function pngFile(name = "x.png") {
  return new File(
    [Uint8Array.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])],
    name,
    { type: "image/png" },
  );
}

function artistInput(container: HTMLElement) {
  const el = container.querySelector('input[placeholder="Rembrandt van Rijn"]');
  if (!el) throw new Error("artist input");
  return el as HTMLInputElement;
}

function titleInput(container: HTMLElement) {
  const el = container.querySelector('input[placeholder="The Night Watch"]');
  if (!el) throw new Error("title input");
  return el as HTMLInputElement;
}

function renderUpload() {
  return render(
    <MemoryRouter initialEntries={["/upload"]}>
      <AuthProvider>
        <Routes>
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/results" element={<div data-testid="results-dest">r</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("UploadPage", () => {
  beforeEach(() => {
    localStorage.clear();
    analyzeArtwork.mockReset();
    vi.spyOn(client, "hasApiBackend").mockReturnValue(false);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows extension error for bad file type", async () => {
    renderUpload();
    await waitFor(() => expect(screen.getByText(/upload artwork/i)).toBeInTheDocument());
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File([""], "x.gif", { type: "image/gif" });
    fireEvent.change(input, { target: { files: [file] } });
    expect(
      await screen.findByText(/invalid file extension/i),
    ).toBeInTheDocument();
  });

  it("shows error for non-image mime", async () => {
    renderUpload();
    await waitFor(() => expect(screen.getByText(/upload artwork/i)).toBeInTheDocument());
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File([""], "x.png", { type: "application/octet-stream" });
    fireEvent.change(input, { target: { files: [file] } });
    expect(
      await screen.findByText(/invalid image format/i),
    ).toBeInTheDocument();
  });

  it("validates form on submit", async () => {
    const user = userEvent.setup();
    const { container } = renderUpload();
    await waitFor(() => expect(screen.getByText(/upload artwork/i)).toBeInTheDocument());
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [pngFile()] } });
    await user.type(artistInput(container), "A");
    const form = container.querySelector("form");
    expect(form).toBeTruthy();
    fireEvent.submit(form!);
    expect(await screen.findByText(/both artist name and artwork name/i)).toBeInTheDocument();
  });

  it("submits successfully in mock mode and navigates to results", async () => {
    const user = userEvent.setup();
    const out: AnalysisResult = {
      id: "z",
      score: 0.5,
      image: "",
      artistName: "A",
      artworkName: "B",
      timestamp: new Date().toISOString(),
      fileName: "x.png",
      fileSize: 8,
      prediction: 1,
    };
    analyzeArtwork.mockResolvedValue(out);

    const { container } = renderUpload();
    await waitFor(() => expect(screen.getByText(/upload artwork/i)).toBeInTheDocument());
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [pngFile()] } });
    await user.type(artistInput(container), "Artist");
    await user.type(titleInput(container), "Title");
    await user.click(screen.getByRole("button", { name: /analyze artwork/i }));

    await waitFor(() => expect(screen.getByTestId("results-dest")).toBeInTheDocument());
    expect(JSON.parse(localStorage.getItem("artguard_latest_result") || "{}").id).toBe("z");
  });

  it("persists history only when API backend is off", async () => {
    vi.spyOn(client, "hasApiBackend").mockReturnValue(true);
    const user = userEvent.setup();
    analyzeArtwork.mockResolvedValue({
      id: "z",
      score: 0.5,
      image: "u",
      artistName: "A",
      artworkName: "B",
      timestamp: new Date().toISOString(),
      fileName: "x.png",
      fileSize: 8,
    });

    localStorage.setItem(
      "artguard_user",
      JSON.stringify({ id: "u1", username: "a", email: "a@b.c" }),
    );
    localStorage.setItem("artguard_users", "[]");

    const { container } = renderUpload();
    await waitFor(() => expect(screen.getByText(/upload artwork/i)).toBeInTheDocument());
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [pngFile()] } });
    await user.type(artistInput(container), "Artist");
    await user.type(titleInput(container), "Title");
    await user.click(screen.getByRole("button", { name: /analyze artwork/i }));
    await waitFor(() => expect(screen.getByTestId("results-dest")).toBeInTheDocument());
    expect(localStorage.getItem("artguard_history_u1")).toBeNull();
  });

  it("shows error when file exceeds size limit", async () => {
    renderUpload();
    await waitFor(() => expect(screen.getByText(/upload artwork/i)).toBeInTheDocument());
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const big = new File([new Uint8Array(21 * 1024 * 1024)], "big.png", { type: "image/png" });
    fireEvent.change(input, { target: { files: [big] } });
    expect(await screen.findByText(/file too large/i)).toBeInTheDocument();
  });

  it("accepts file via drop", async () => {
    const user = userEvent.setup();
    analyzeArtwork.mockResolvedValue({
      id: "z",
      score: 0.5,
      image: "",
      artistName: "A",
      artworkName: "B",
      timestamp: new Date().toISOString(),
      fileName: "x.png",
      fileSize: 8,
    });
    const { container } = renderUpload();
    await waitFor(() => expect(screen.getByText(/upload artwork/i)).toBeInTheDocument());
    const dropZone = container.querySelector(".group.cursor-pointer");
    expect(dropZone).toBeTruthy();
    const file = pngFile();
    fireEvent.dragOver(dropZone!, { dataTransfer: { files: [] } });
    fireEvent.drop(dropZone!, { dataTransfer: { files: [file] } });
    await user.type(artistInput(container), "A");
    await user.type(titleInput(container), "B");
    await user.click(screen.getByRole("button", { name: /analyze artwork/i }));
    await waitFor(() => expect(screen.getByTestId("results-dest")).toBeInTheDocument());
  });

  it("shows analyze error message when analyzeArtwork rejects", async () => {
    const user = userEvent.setup();
    analyzeArtwork.mockRejectedValue(new Error("Inference failed"));
    const { container } = renderUpload();
    await waitFor(() => expect(screen.getByText(/upload artwork/i)).toBeInTheDocument());
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [pngFile()] } });
    await user.type(artistInput(container), "Artist");
    await user.type(titleInput(container), "Title");
    await user.click(screen.getByRole("button", { name: /analyze artwork/i }));
    expect(await screen.findByText(/inference failed/i)).toBeInTheDocument();
  });

  it("resets dragging state on drag leave", async () => {
    renderUpload();
    await waitFor(() => expect(screen.getByText(/upload artwork/i)).toBeInTheDocument());
    const dropZone = document.querySelector(".group.cursor-pointer");
    expect(dropZone).toBeTruthy();
    fireEvent.dragOver(dropZone!, { dataTransfer: { files: [] } });
    fireEvent.dragLeave(dropZone!);
  });

  it("shows error when submitting without selecting a file", async () => {
    const { container } = renderUpload();
    await waitFor(() => expect(screen.getByText(/upload artwork/i)).toBeInTheDocument());
    // Submit form without selecting any file
    const form = container.querySelector("form");
    fireEvent.submit(form!);
    expect(await screen.findByText(/please select an image file/i)).toBeInTheDocument();
  });

  it("clears selected file when Remove is clicked", async () => {
    const user = userEvent.setup();
    const { container } = renderUpload();
    await waitFor(() => expect(screen.getByText(/upload artwork/i)).toBeInTheDocument());
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [pngFile()] } });
    expect(screen.getByText(/x\.png/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^remove$/i }));
    expect(screen.queryByText(/x\.png/i)).not.toBeInTheDocument();
  });
});
