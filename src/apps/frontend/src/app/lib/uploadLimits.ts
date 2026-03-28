/**
 * Must match `MAX_UPLOAD_SIZE_BYTES` in `src/apps/backend/validation.py`.
 */
export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;

export const MAX_UPLOAD_MB = MAX_UPLOAD_BYTES / (1024 * 1024);

/** Allowed file suffixes (case-insensitive). Align with backend image handling. */
export const IMAGE_EXTENSIONS = new Set([".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"]);

export function hasAllowedImageExtension(fileName: string): boolean {
  const lower = fileName.toLowerCase();
  const dot = lower.lastIndexOf(".");
  if (dot === -1) return false;
  return IMAGE_EXTENSIONS.has(lower.slice(dot));
}
