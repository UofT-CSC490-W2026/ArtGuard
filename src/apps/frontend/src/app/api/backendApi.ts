/**
 * Typed response shapes for backend inference routes (FastAPI).
 */

export interface InferencePatchApi {
  x: number;
  y: number;
  w: number;
  h: number;
  prob: number;
}

export interface InferenceApiResponse {
  inference_id: string;
  /** 1 = authentic, 0 = forgery, -1 = pending (from Modal / DynamoDB). */
  prediction?: number | null;
  score: number;
  explanation?: string | null;
  /** Presigned GET for the raw upload (short-lived). */
  image_url?: string | null;
  image_width?: number;
  image_height?: number;
  patch_data?: InferencePatchApi[] | null;
}
