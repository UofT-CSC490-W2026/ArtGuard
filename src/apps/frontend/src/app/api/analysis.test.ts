import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { analyzeArtwork } from "./analysis";

const hoisted = vi.hoisted(() => ({
  hasBackend: false,
  postFormData: vi.fn(),
}));

vi.mock("./client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./client")>();
  return {
    ...actual,
    hasApiBackend: () => hoisted.hasBackend,
    postFormData: hoisted.postFormData,
  };
});

describe("analyzeArtwork", () => {
  beforeEach(() => {
    hoisted.hasBackend = false;
    hoisted.postFormData.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("maps API inference response to AnalysisResult", async () => {
    hoisted.hasBackend = true;
    hoisted.postFormData.mockResolvedValue({
      inference_id: "inf-1",
      score: 0.7,
      prediction: 1,
      explanation: "ok",
      image_url: "  https://x  ",
      image_width: 400,
      image_height: 300,
      patch_data: [{ x: 0, y: 0, w: 10, h: 10, prob: 0.5 }],
    });
    const file = new File([new Uint8Array([1])], "a.png", { type: "image/png" });
    const r = await analyzeArtwork({
      file,
      artistName: "A",
      artworkName: "B",
      userId: "u",
    });
    expect(r.id).toBe("inf-1");
    expect(r.image).toBe("https://x");
    expect(r.patchData).toHaveLength(1);
    expect(r.prediction).toBe(1);
  });

  it("uses Unknown/Untitled when names missing in API path", async () => {
    hoisted.hasBackend = true;
    hoisted.postFormData.mockResolvedValue({
      inference_id: "i",
      score: 0.5,
      prediction: null,
    });
    const file = new File([new Uint8Array([1])], "f.jpg", { type: "image/jpeg" });
    const r = await analyzeArtwork({
      file,
      artistName: "",
      artworkName: "",
      userId: "",
    });
    expect(r.artistName).toBe("Unknown");
    expect(r.artworkName).toBe("Untitled");
  });

  it(
    "runs mock pipeline with delay and image dimensions",
    async () => {
      class Img {
        naturalWidth = 448;
        naturalHeight = 224;
        onload: (() => void) | null = null;
        set src(_: string) {
          queueMicrotask(() => this.onload?.());
        }
      }
      vi.stubGlobal("Image", Img);

      const file = new File([new Uint8Array([1])], "a.png", { type: "image/png" });
      const r = await analyzeArtwork({
        file,
        artistName: "X",
        artworkName: "Y",
        userId: "z",
      });
      expect(r.patchData?.length).toBeGreaterThan(0);
      expect(r.image.startsWith("data:")).toBe(true);
    },
    15_000,
  );

  it(
    "rejects when FileReader fails in mock mode",
    async () => {
      class BadReader {
        onloadend: ((ev: ProgressEvent<FileReader>) => void) | null = null;
        onerror: ((ev: ProgressEvent<FileReader>) => void) | null = null;
        readAsDataURL() {
          queueMicrotask(() => this.onerror?.({} as ProgressEvent<FileReader>));
        }
      }
      vi.stubGlobal("FileReader", BadReader);

      const file = new File([new Uint8Array([1])], "a.png", { type: "image/png" });
      await expect(
        analyzeArtwork({
          file,
          artistName: "X",
          artworkName: "Y",
          userId: "z",
        }),
      ).rejects.toThrow("Failed to read file");
    },
    15_000,
  );

  it(
    "handles Image onerror in mock mode (loadImageDimensions fallback)",
    async () => {
      // Image that fires onerror — dimensions should fall back to 1x1
      class ErrImg {
        naturalWidth = 0;
        naturalHeight = 0;
        onerror: (() => void) | null = null;
        set src(_: string) {
          queueMicrotask(() => this.onerror?.());
        }
      }
      vi.stubGlobal("Image", ErrImg);

      const file = new File([new Uint8Array([1])], "a.png", { type: "image/png" });
      await expect(
        analyzeArtwork({ file, artistName: "X", artworkName: "Y", userId: "z" }),
      ).rejects.toThrow("Failed to read image dimensions");
    },
    15_000,
  );
});
