import { afterEach, describe, expect, it, vi } from "vitest";

describe("backendApi wrappers", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("calls expected POST routes", async () => {
    vi.stubEnv("VITE_API_URL", "http://127.0.0.1/api");
    vi.resetModules();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        run_id: "r",
        task_arn: "t",
        answer: "a",
        sources: [],
        variant: "tiny",
        status: "ok",
        checkpoint: "c",
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const { ragQuery, startEvaluation, startProcessDataPipeline, startTraining } = await import(
      "./backendApi"
    );
    await startProcessDataPipeline();
    await ragQuery("q");
    await startTraining({ variant: "tiny" });
    await startEvaluation({ variant: "base", checkpoint: "ckpt" });

    const urls = fetchMock.mock.calls.map((c) => c[0] as string);
    expect(urls.some((u) => u.includes("/process_data"))).toBe(true);
    expect(urls.some((u) => u.includes("/rag-query"))).toBe(true);
    expect(urls.some((u) => u.includes("/train"))).toBe(true);
    expect(urls.some((u) => u.includes("/evaluate"))).toBe(true);
  });
});
