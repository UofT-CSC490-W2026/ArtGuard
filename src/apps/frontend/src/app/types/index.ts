/** Shared domain and API types for production use */

export interface User {
  id: string;
  username: string;
  email: string;
}

/** Backend POST /auth/login and /auth/signup */
export interface AuthApiResponse {
  access_token: string;
  token_type: string;
  user: User;
}

/** DynamoDB inference_status (camelCase on the client). */
export type InferenceStatus = "processing" | "completed" | "failed";

/** Per-patch box and authenticity probability (0–1) from POST /inference. */
export interface PatchData {
  x: number;
  y: number;
  w: number;
  h: number;
  prob: number;
}

export interface AnalysisResult {
  id: string;
  /** Mean per-patch probability of authenticity (0–1), aligned with the backend Modal pipeline. */
  score: number;
  image: string;
  artistName: string;
  artworkName: string;
  timestamp: string;
  fileName: string;
  fileSize: number;
  /**
   * From API: processing → completed | failed. Older rows may omit (treated as completed).
   */
  inferenceStatus?: InferenceStatus | null;
  /** Server error detail when inferenceStatus === "failed". */
  inferenceError?: string | null;
  /** When present, from POST /inference (backend explanation text). */
  explanation?: string | null;
  /**
   * Backend Modal: 1 = authentic, 0 = forgery, -1 = unknown/pending.
   */
  prediction?: number | null;
  /** Original image dimensions (pixels), from API when available. */
  imageWidth?: number;
  imageHeight?: number;
  /** Per-patch authenticity probabilities aligned with backend patch grid. */
  patchData?: PatchData[];
}

/** Raw JSON shape returned by POST /inference. */
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
  patch_data?: PatchData[] | null;
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "object" && error !== null && "message" in error) {
    return String((error as { message: unknown }).message);
  }
  return "An unexpected error occurred";
}
