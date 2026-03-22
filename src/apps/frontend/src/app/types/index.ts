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

/** How to interpret `score` for display and filters. */
export type ScoreSemantics = "authenticity" | "legacy_forgery";

/** DynamoDB inference_status (camelCase on the client). */
export type InferenceStatus = "processing" | "completed" | "failed";

export interface AnalysisResult {
  id: string;
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
   * Omitted on legacy/mock analyses that used the old score scale only.
   */
  prediction?: number | null;
  /**
   * `authenticity`: `score` is mean patch probability of authenticity (higher = more authentic).
   * `legacy_forgery`: older saved results where higher `score` meant stronger forgery signal.
   */
  scoreSemantics?: ScoreSemantics;
}

export interface ApiError {
  message: string;
  code?: string;
  status?: number;
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "object" && error !== null && "message" in error) {
    return String((error as { message: unknown }).message);
  }
  return "An unexpected error occurred";
}
