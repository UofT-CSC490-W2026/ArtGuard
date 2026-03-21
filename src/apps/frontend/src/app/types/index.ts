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

export interface AnalysisResult {
  id: string;
  score: number;
  image: string;
  artistName: string;
  artworkName: string;
  timestamp: string;
  fileName: string;
  fileSize: number;
  /** When present, from POST /inference (backend explanation text). */
  explanation?: string | null;
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
