/**
 * User inference history (DynamoDB + presigned S3 URLs).
 */

import { api } from "./client";
import type { AnalysisResult, InferenceStatus, PatchData } from "../types";
import { aggregatePatchDataToInferenceGrid } from "../lib/inferenceGrid";

export interface InferenceListItem {
  inference_id: string;
  created_at: number;
  score: number;
  confidence_percent?: number;
  prediction?: number | null;
  explanation?: string | null;
  inference_status?: string | null;
  error_message?: string | null;
  artist_name: string;
  artwork_name: string;
  image_name: string;
  file_size: number;
  image_url: string;
  image_width?: number;
  image_height?: number;
  patch_data?: PatchData[] | null;
}

interface InferenceListResponse {
  items: InferenceListItem[];
  next_cursor?: string | null;
}

interface DeleteAllInferencesResponse {
  deleted: number;
}

function coerceInferenceStatus(raw: string | null | undefined): InferenceStatus | undefined {
  if (raw === "processing" || raw === "completed" || raw === "failed") return raw;
  return undefined;
}

export function inferenceToAnalysisResult(row: InferenceListItem): AnalysisResult {
  const rawPatchData =
    Array.isArray(row.patch_data) && row.patch_data.length > 0 ? row.patch_data : undefined;
  const iw = row.image_width;
  const ih = row.image_height;
  const patchData =
    rawPatchData && typeof iw === "number" && iw > 0 && typeof ih === "number" && ih > 0
      ? aggregatePatchDataToInferenceGrid(rawPatchData, iw, ih)
      : rawPatchData;
  return {
    id: row.inference_id,
    score: row.score,
    confidencePercent:
      typeof row.confidence_percent === "number" ? row.confidence_percent : undefined,
    image: row.image_url,
    artistName: row.artist_name,
    artworkName: row.artwork_name,
    timestamp: new Date(row.created_at).toISOString(),
    fileName: row.image_name,
    fileSize: row.file_size,
    inferenceStatus: coerceInferenceStatus(row.inference_status ?? undefined),
    inferenceError:
      typeof row.error_message === "string" && row.error_message.trim().length > 0
        ? row.error_message.trim()
        : undefined,
    explanation: row.explanation ?? undefined,
    prediction: typeof row.prediction === "number" ? row.prediction : undefined,
    ...(typeof iw === "number" && iw > 0 ? { imageWidth: iw } : {}),
    ...(typeof ih === "number" && ih > 0 ? { imageHeight: ih } : {}),
    ...(patchData ? { patchData } : {}),
  };
}

export async function listInferences(
  limit = 50,
  cursor?: string
): Promise<InferenceListResponse> {
  return api.get<InferenceListResponse>("/inferences", {
    params: {
      limit: String(limit),
      ...(cursor ? { cursor } : {}),
    },
  });
}

export async function deleteInference(inferenceId: string): Promise<void> {
  await api.delete(`/inferences/${inferenceId}`);
}

export async function deleteAllInferences(): Promise<DeleteAllInferencesResponse> {
  return api.delete<DeleteAllInferencesResponse>("/inferences");
}
