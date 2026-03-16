import type { AnalysisResult } from "../types";
import { hasApiBackend, api } from "./client";

export interface AnalyzeInput {
  file: File;
  artistName: string;
  artworkName: string;
  userId: string;
}

export async function analyzeArtwork(input: AnalyzeInput): Promise<AnalysisResult> {
  if (hasApiBackend()) {
    const form = new FormData();
    form.append("image", input.file);
    form.append("artistName", input.artistName);
    form.append("artworkName", input.artworkName);
    form.append("userId", input.userId);
    const base = import.meta.env.VITE_API_URL as string;
    const url = `${base.replace(/\/$/, "")}/analyze`;
    const res = await fetch(url, { method: "POST", body: form });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error((data as { message?: string })?.message ?? res.statusText);
    return data as AnalysisResult;
  }

  await new Promise((r) => setTimeout(r, 2000));
  const preview = await new Promise<string>((resolve, reject) => {
    const r = new FileReader();
    r.onloadend = () => resolve(r.result as string);
    r.onerror = () => reject(new Error("Failed to read file"));
    r.readAsDataURL(input.file);
  });
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    score: Math.random() * 0.9,
    image: preview,
    artistName: input.artistName || "Unknown",
    artworkName: input.artworkName || "Untitled",
    timestamp: new Date().toISOString(),
    fileName: input.file.name,
    fileSize: input.file.size,
  };
}
