/** Paths to JPEGs in `public/art/` (Vite). Source: Wikimedia Commons, public domain. */
export function artAsset(filename: string): string {
  const base = import.meta.env.BASE_URL;
  return base.endsWith("/") ? `${base}art/${filename}` : `${base}/art/${filename}`;
}
