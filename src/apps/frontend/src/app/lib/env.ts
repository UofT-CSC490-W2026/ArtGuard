/** Testable wrapper for dev-only UI (e.g. error details). */
export function isDev(): boolean {
  return import.meta.env.DEV;
}
