import type { AnalysisResult, PatchData, InferenceApiResponse } from "../types";
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
  const cols = Math.max(2, Math.min(8, Math.ceil(w / 224)));
  const rows = Math.max(2, Math.min(8, Math.ceil(h / 224)));
  const patches: PatchData[] = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const x = Math.floor((c * w) / cols);
      const y = Math.floor((r * h) / rows);
      const pw = Math.min(w - x, Math.ceil(w / cols));
      const ph = Math.min(h - y, Math.ceil(h / rows));
      const jitter = (Math.random() - 0.5) * 0.25;
      const prob = Math.max(0, Math.min(1, meanScore + jitter));
      patches.push({ x, y, w: pw, h: ph, prob });
    }
  }
  return patches;
}

function mapInferenceToResult(
  raw: InferenceApiResponse,
  input: AnalyzeInput
): AnalysisResult {
  const presigned = raw.image_url?.trim();
  const patchData = raw.patch_data?.map((p) => ({
    x: p.x,
    y: p.y,
    w: p.w,
    h: p.h,
    prob: p.prob,
  }));
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
    imageWidth: typeof raw.image_width === "number" ? raw.image_width : undefined,
    imageHeight: typeof raw.image_height === "number" ? raw.image_height : undefined,
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
