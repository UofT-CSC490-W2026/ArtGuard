/** Shared domain and API types for production use */

export interface User {
  id: string;
  username: string;
  email: string;
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
