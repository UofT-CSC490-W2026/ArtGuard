/**
 * User inference history (DynamoDB + presigned S3 URLs).
 */

import { api } from "./client";
import type { AnalysisResult, InferenceStatus } from "../types";

export interface InferenceListItem {
  inference_id: string;
  created_at: number;
  score: number;
  prediction?: number | null;
  explanation?: string | null;
  inference_status?: string | null;
  error_message?: string | null;
  artist_name: string;
  artwork_name: string;
  image_name: string;
  file_size: number;
  image_url: string;
}

export interface InferenceListResponse {
  items: InferenceListItem[];
  next_cursor?: string | null;
}

export interface DeleteAllInferencesResponse {
  deleted: number;
}

function coerceInferenceStatus(raw: string | null | undefined): InferenceStatus | undefined {
  if (raw === "processing" || raw === "completed" || raw === "failed") return raw;
  return undefined;
}

export function inferenceToAnalysisResult(row: InferenceListItem): AnalysisResult {
  return {
    id: row.inference_id,
    score: row.score,
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
    /** All rows from GET /inferences share backend Modal semantics (score = authenticity). */
    scoreSemantics: "authenticity",
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

export async function getInference(inferenceId: string): Promise<InferenceListItem> {
  return api.get<InferenceListItem>(`/inferences/${inferenceId}`);
}

export async function deleteInference(inferenceId: string): Promise<void> {
  await api.delete(`/inferences/${inferenceId}`);
}

export async function deleteAllInferences(): Promise<DeleteAllInferencesResponse> {
  return api.delete<DeleteAllInferencesResponse>("/inferences");
}

export async function getInferenceStats(): Promise<{ count: number }> {
  return api.get<{ count: number }>("/inferences/stats");
}
