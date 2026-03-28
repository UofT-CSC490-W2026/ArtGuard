import { afterEach, describe, expect, it, vi } from "vitest";
import { inferenceToAnalysisResult } from "@/app/api/inferencesApi";

describe("inferenceToAnalysisResult", () => {
  it("maps list item fields and coerces status", () => {
    const row = {
      inference_id: "id1",
      created_at: 1_700_000_000_000,
      score: 0.5,
      prediction: 1,
      explanation: "e",
      inference_status: "processing",
      error_message: "  err  ",
      artist_name: "Art",
      artwork_name: "Work",
      image_name: "i.png",
      file_size: 12,
      image_url: "https://x",
    };
    const r = inferenceToAnalysisResult(row);
    expect(r.id).toBe("id1");
    expect(r.inferenceStatus).toBe("processing");
    expect(r.inferenceError).toBe("err");
  });

  it("omits prediction when not a number and clears empty error", () => {
    const r = inferenceToAnalysisResult({
      inference_id: "x",
      created_at: 0,
      score: 0,
      artist_name: "a",
      artwork_name: "b",
      image_name: "c",
      file_size: 0,
      image_url: "",
      prediction: null,
      error_message: "   ",
    });
    expect(r.prediction).toBeUndefined();
    expect(r.inferenceError).toBeUndefined();
  });

  it("coerces unknown inference_status to undefined", () => {
    const r = inferenceToAnalysisResult({
      inference_id: "x",
      created_at: 0,
      score: 0,
      artist_name: "a",
      artwork_name: "b",
      image_name: "c",
      file_size: 0,
      image_url: "",
      inference_status: "unknown_status",
    });
    expect(r.inferenceStatus).toBeUndefined();
  });

  it("maps all valid inference_status values", () => {
    for (const status of ["processing", "completed", "failed"] as const) {
      const r = inferenceToAnalysisResult({
        inference_id: "x",
        created_at: 0,
        score: 0,
        artist_name: "a",
        artwork_name: "b",
        image_name: "c",
        file_size: 0,
        image_url: "",
        inference_status: status,
      });
      expect(r.inferenceStatus).toBe(status);
    }
  });
});

describe("inferences API functions", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("listInferences builds query params", async () => {
    vi.stubEnv("VITE_API_URL", "http://127.0.0.1/api");
    vi.resetModules();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [], next_cursor: null }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const { listInferences } = await import("@/app/api/inferencesApi");
    await listInferences(10, "cur");
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain("limit=10");
    expect(url).toContain("cursor=cur");
  });

  it("listInferences omits cursor param when not provided", async () => {
    vi.stubEnv("VITE_API_URL", "http://127.0.0.1/api");
    vi.resetModules();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [], next_cursor: null }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const { listInferences } = await import("@/app/api/inferencesApi");
    await listInferences(25);
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain("limit=25");
    expect(url).not.toContain("cursor=");
  });

  it("deleteInference and deleteAllInferences hit routes", async () => {
    vi.stubEnv("VITE_API_URL", "http://127.0.0.1/api");
    vi.resetModules();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ deleted: 2 }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const {
      deleteAllInferences,
      deleteInference,
    } = await import("@/app/api/inferencesApi");
    await deleteInference("abc");
    await deleteAllInferences();

    const urls = fetchMock.mock.calls.map((c) => c[0] as string);
    expect(urls.some((u) => u.includes("/inferences/abc"))).toBe(true);
    expect(urls.some((u) => u.includes("/inferences"))).toBe(true);
  });
});
