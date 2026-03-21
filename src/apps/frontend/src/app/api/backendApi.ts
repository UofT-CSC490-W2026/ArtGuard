/**
 * Typed wrappers for non-auth backend routes (FastAPI main + train router).
 * Requires VITE_API_URL; uses Bearer token when logged in.
 */

import { api } from "./client";

export interface ProcessDataResponse {
  run_id: string;
  task_arn: string;
}

export interface RAGQueryResponse {
  answer: string;
  sources: { s3_uri?: string; snippet?: string }[];
}

export interface TrainRequestBody {
  variant: "tiny" | "base";
  config?: Record<string, unknown>;
}

export interface TrainResponse {
  run_id: string;
  variant: string;
  status: string;
}

export interface EvaluateRequestBody {
  variant: "tiny" | "base";
  checkpoint: string;
}

export interface EvaluateResponse {
  variant: string;
  checkpoint: string;
  status: string;
}

export interface InferenceApiResponse {
  inference_id: string;
  /** 1 = authentic, 0 = forgery, -1 = pending (from Modal / DynamoDB). */
  prediction?: number | null;
  score: number;
  explanation?: string | null;
  /** Presigned GET for the raw upload (short-lived). */
  image_url?: string | null;
}

export async function startProcessDataPipeline(): Promise<ProcessDataResponse> {
  return api.post<ProcessDataResponse>("/process_data");
}

export async function ragQuery(query: string): Promise<RAGQueryResponse> {
  return api.post<RAGQueryResponse>("/rag-query", { query });
}

export async function startTraining(body: TrainRequestBody): Promise<TrainResponse> {
  return api.post<TrainResponse>("/train", body);
}

export async function startEvaluation(body: EvaluateRequestBody): Promise<EvaluateResponse> {
  return api.post<EvaluateResponse>("/evaluate", body);
}
