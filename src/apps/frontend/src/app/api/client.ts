/**
 * Production API client. Uses VITE_API_URL when set; otherwise operations
 * can use mock implementations until backend is available.
 */

const BASE_URL = import.meta.env.VITE_API_URL as string | undefined;

export const hasApiBackend = (): boolean =>
  typeof BASE_URL === "string" && BASE_URL.length > 0;

function getBaseUrl(): string {
  if (hasApiBackend()) return BASE_URL!.replace(/\/$/, "");
  throw new Error("API client used without VITE_API_URL");
}

export interface RequestConfig extends RequestInit {
  params?: Record<string, string>;
}

async function request<T>(
  endpoint: string,
  config: RequestConfig = {}
): Promise<T> {
  const base = getBaseUrl();
  const { params, ...init } = config;
  const url = new URL(endpoint, base);
  if (params) {
    Object.entries(params).forEach(([key, value]) =>
      url.searchParams.set(key, value)
    );
  }
  const response = await fetch(url.toString(), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init.headers,
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message =
      (data as { message?: string })?.message ?? response.statusText;
    throw new Error(message);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, config?: RequestConfig) =>
    request<T>(path, { ...config, method: "GET" }),

  post: <T>(path: string, body?: unknown, config?: RequestConfig) =>
    request<T>(path, { ...config, method: "POST", body: body ? JSON.stringify(body) : undefined }),

  put: <T>(path: string, body?: unknown, config?: RequestConfig) =>
    request<T>(path, { ...config, method: "PUT", body: body ? JSON.stringify(body) : undefined }),

  delete: <T>(path: string, config?: RequestConfig) =>
    request<T>(path, { ...config, method: "DELETE" }),
};
