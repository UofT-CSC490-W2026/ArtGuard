import type { AnalysisResult } from "../types";
import { hasApiBackend, postFormData } from "./client";
import type { InferenceApiResponse } from "./backendApi";

export interface AnalyzeInput {
  file: File;
  artistName: string;
  artworkName: string;
  userId: string;
}

function mapInferenceToResult(
  raw: InferenceApiResponse,
  input: AnalyzeInput
): AnalysisResult {
  const presigned = raw.image_url?.trim();
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

  await new Promise((r) => setTimeout(r, 2000));
  const preview = await new Promise<string>((resolve, reject) => {
    const r = new FileReader();
    r.onloadend = () => resolve(r.result as string);
    r.onerror = () => reject(new Error("Failed to read file"));
    r.readAsDataURL(input.file);
  });
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    score: Math.random() * 0.9,
    image: preview,
    artistName: input.artistName || "Unknown",
    artworkName: input.artworkName || "Untitled",
    timestamp: new Date().toISOString(),
    fileName: input.file.name,
    fileSize: input.file.size,
  };
}
