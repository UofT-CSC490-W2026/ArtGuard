import type { AnalysisResult, PatchData, InferenceApiResponse } from "../types";
import {
  aggregatePatchDataToInferenceGrid,
  chooseGridSize,
  computeGridCells,
} from "../lib/inferenceGrid";
import { hasApiBackend, postFormData } from "./client";

interface AnalyzeInput {
  file: File;
  artistName: string;
  artworkName: string;
  userId: string;
}

function loadImageDimensions(src: string): Promise<{ w: number; h: number }> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () =>
      resolve({ w: img.naturalWidth || 1, h: img.naturalHeight || 1 });
    img.onerror = () => reject(new Error("Failed to read image dimensions"));
    img.src = src;
  });
}

function generateMockPatchData(w: number, h: number, meanScore: number): PatchData[] {
  const gridSize = chooseGridSize(w, h);
  const cells = computeGridCells(w, h, gridSize);
  return cells.map((cell, i) => {
    const jitter = Math.sin(i * 1.7) * 0.12 + (Math.random() - 0.5) * 0.1;
    const prob = Math.max(0, Math.min(1, meanScore + jitter));
    return { ...cell, prob };
  });
}

function mapInferenceToResult(
  raw: InferenceApiResponse,
  input: AnalyzeInput
): AnalysisResult {
  const presigned = raw.image_url?.trim();
  const iw =
    typeof raw.image_width === "number" && raw.image_width > 0
      ? raw.image_width
      : undefined;
  const ih =
    typeof raw.image_height === "number" && raw.image_height > 0
      ? raw.image_height
      : undefined;
  const rawPatches: PatchData[] | undefined = raw.patch_data?.map((p) => ({
    x: p.x,
    y: p.y,
    w: p.w,
    h: p.h,
    prob: p.prob,
  }));
  const patchData =
    rawPatches && iw !== undefined && ih !== undefined
      ? aggregatePatchDataToInferenceGrid(rawPatches, iw, ih)
      : rawPatches;
  return {
    id: raw.inference_id,
    score: raw.score,
    image: presigned ?? "",
    artistName: input.artistName || "Unknown",
    artworkName: input.artworkName || "Untitled",
    timestamp: new Date().toISOString(),
    fileName: input.file.name,
    fileSize: input.file.size,
    explanation: raw.explanation ?? undefined,
    prediction: typeof raw.prediction === "number" ? raw.prediction : undefined,
    imageWidth: iw,
    imageHeight: ih,
    patchData,
  };
}

export async function analyzeArtwork(input: AnalyzeInput): Promise<AnalysisResult> {
  if (hasApiBackend()) {
    const form = new FormData();
    // FastAPI: infer(file: UploadFile = File(...)) → field name "file"
    form.append("file", input.file);
    form.append("artist_name", input.artistName);
    form.append("artwork_name", input.artworkName);
    const raw = await postFormData<InferenceApiResponse>("/inference", form);
    return mapInferenceToResult(raw, input);
  }

  await new Promise((r) => setTimeout(r, 1200));
  const preview = await new Promise<string>((resolve, reject) => {
    const r = new FileReader();
    r.onloadend = () => resolve(r.result as string);
    r.onerror = () => reject(new Error("Failed to read file"));
    r.readAsDataURL(input.file);
  });
  const prediction = Math.random() > 0.5 ? 1 : 0;
  const score =
    prediction === 1 ? 0.55 + Math.random() * 0.45 : Math.random() * 0.45;
  const { w, h } = await loadImageDimensions(preview);
  const patchData = generateMockPatchData(w, h, score);
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    score,
    image: preview,
    artistName: input.artistName || "Unknown",
    artworkName: input.artworkName || "Untitled",
    timestamp: new Date().toISOString(),
    fileName: input.file.name,
    fileSize: input.file.size,
    prediction,
    imageWidth: w,
    imageHeight: h,
    patchData,
  };
}
