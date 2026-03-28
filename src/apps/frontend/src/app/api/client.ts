/**
 * Production API client. Uses VITE_API_URL when set; otherwise operations
 * can use mock implementations until backend is available.
 */

const BASE_URL = import.meta.env.VITE_API_URL as string | undefined;

const STORAGE_ACCESS_TOKEN = "artguard_access_token";

export const hasApiBackend = (): boolean =>
  typeof BASE_URL === "string" && BASE_URL.length > 0;

function getBaseUrl(): string {
  if (hasApiBackend()) return BASE_URL!.replace(/\/$/, "");
  throw new Error("API client used without VITE_API_URL");
}

/**
 * Join `VITE_API_URL` with a route path. Strips a leading slash from `path` and resolves relative to
 * the base so `https://host/api` + `/inference` → `https://host/api/inference` (plain `new URL` would drop `/api`).
 */
function resolveApiUrl(base: string, path: string): URL {
  const root = `${base.replace(/\/?$/, "/")}`;
  const segment = path.replace(/^\/+/, "");
  return new URL(segment, root);
}

/** Persist JWT from /auth/login | /auth/signup | /auth/profile */
export function setAccessToken(token: string | null): void {
  if (token) {
    localStorage.setItem(STORAGE_ACCESS_TOKEN, token);
  } else {
    localStorage.removeItem(STORAGE_ACCESS_TOKEN);
  }
}

export function getAccessToken(): string | null {
  try {
    return localStorage.getItem(STORAGE_ACCESS_TOKEN);
  } catch {
    return null;
  }
}

interface RequestConfig extends RequestInit {
  params?: Record<string, string>;
  /** Skip attaching Bearer token (for public auth routes if needed) */
  skipAuth?: boolean;
}

function extractErrorMessage(data: unknown, fallback: string): string {
  if (typeof data === "object" && data !== null) {
    const d = data as Record<string, unknown>;
    if (typeof d.message === "string") return d.message;
    if (typeof d.detail === "string") return d.detail;
    if (Array.isArray(d.detail) && d.detail.length > 0) {
      const first = d.detail[0] as Record<string, unknown>;
      if (typeof first?.msg === "string") return first.msg;
    }
  }
  return fallback;
}

async function request<T>(
  endpoint: string,
  config: RequestConfig = {}
): Promise<T> {
  const base = getBaseUrl();
  const { params, skipAuth, ...init } = config;
  const url = new URL(endpoint, base);
  if (params) {
    Object.entries(params).forEach(([key, value]) =>
      url.searchParams.set(key, value)
    );
  }

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  if (!skipAuth) {
    const token = getAccessToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
  }

  const response = await fetch(url.toString(), {
    ...init,
    headers,
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = extractErrorMessage(data, response.statusText);
    throw new Error(message);
  }
  return data as T;
}

/**
 * Multipart POST (e.g. /inference). Do not set Content-Type — the browser sets the boundary.
 * Sends Bearer token when present (same as JSON requests).
 */
export async function postFormData<T>(
  path: string,
  form: FormData,
  config?: { skipAuth?: boolean }
): Promise<T> {
  const base = getBaseUrl();
  const url = resolveApiUrl(base, path).toString();
  const headers: Record<string, string> = {};
  if (!config?.skipAuth) {
    const token = getAccessToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
  }

  const response = await fetch(url, { method: "POST", body: form, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = extractErrorMessage(data, response.statusText);
    throw new Error(message);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, config?: RequestConfig) =>
    request<T>(path, { ...config, method: "GET" }),

  post: <T>(path: string, body?: unknown, config?: RequestConfig) =>
    request<T>(path, {
      ...config,
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    }),

  put: <T>(path: string, body?: unknown, config?: RequestConfig) =>
    request<T>(path, {
      ...config,
      method: "PUT",
      body: body ? JSON.stringify(body) : undefined,
    }),

  delete: <T>(path: string, config?: RequestConfig) =>
    request<T>(path, { ...config, method: "DELETE" }),
};
