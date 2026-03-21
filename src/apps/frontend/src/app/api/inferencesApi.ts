/**
 * User inference history (DynamoDB + presigned S3 URLs).
 */

import { api } from "./client";
import type { AnalysisResult } from "../types";

export interface InferenceListItem {
  inference_id: string;
  created_at: number;
  score: number;
  explanation?: string | null;
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
    explanation: row.explanation ?? undefined,
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
