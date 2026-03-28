import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

describe("client token helpers", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("setAccessToken and getAccessToken round-trip", async () => {
    const { setAccessToken, getAccessToken } = await import("@/app/api/client");
    expect(getAccessToken()).toBeNull();
    setAccessToken("abc");
    expect(getAccessToken()).toBe("abc");
    setAccessToken(null);
    expect(getAccessToken()).toBeNull();
  });

  it("postFormData sends multipart with Bearer token when API URL is set", async () => {
    vi.stubEnv("VITE_API_URL", "http://127.0.0.1/api");
    vi.resetModules();

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ inference_id: "x" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const { postFormData, setAccessToken } = await import("@/app/api/client");
    setAccessToken("jwt-token");
    const form = new FormData();
    form.append("file", new Blob([new Uint8Array([1])]), "a.png");

    await postFormData<{ inference_id: string }>("/inference", form);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1/api/inference");
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({ Authorization: "Bearer jwt-token" });
    expect(init.body).toBe(form);
  });

  it("postFormData omits Authorization when no token is set", async () => {
    vi.stubEnv("VITE_API_URL", "http://127.0.0.1/api");
    vi.resetModules();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", fetchMock);
    const { postFormData } = await import("@/app/api/client");
    await postFormData("/inference", new FormData());
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it("api.get parses JSON on success", async () => {
    vi.stubEnv("VITE_API_URL", "http://127.0.0.1/api");
    vi.resetModules();

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ id: "user-1", username: "a", email: "a@b.c" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const { api, setAccessToken } = await import("@/app/api/client");
    setAccessToken("t");
    const user = await api.get<{ id: string }>("/auth/me");

    expect(user.id).toBe("user-1");
    expect(fetchMock.mock.calls[0][0]).toContain("/auth/me");
  });

  it("api.get throws with message from API error body", async () => {
    vi.stubEnv("VITE_API_URL", "http://127.0.0.1/api");
    vi.resetModules();

    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      statusText: "Bad Request",
      json: async () => ({ detail: [{ msg: "Invalid" }] }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const { api } = await import("@/app/api/client");
    await expect(api.get("/x")).rejects.toThrow("Invalid");
  });

  it("getAccessToken returns null when localStorage throws", async () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    vi.resetModules();
    const { getAccessToken } = await import("@/app/api/client");
    expect(getAccessToken()).toBeNull();
    spy.mockRestore();
  });

  it("api.get throws when VITE_API_URL is unset", async () => {
    vi.stubEnv("VITE_API_URL", "");
    vi.resetModules();
    const { api } = await import("@/app/api/client");
    await expect(api.get("/x")).rejects.toThrow("API client used without VITE_API_URL");
  });

  it("extractErrorMessage uses message and detail string from error JSON", async () => {
    vi.stubEnv("VITE_API_URL", "http://127.0.0.1/api");
    vi.resetModules();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        statusText: "Error",
        json: async () => ({ message: "hello" }),
      })
      .mockResolvedValueOnce({
        ok: false,
        statusText: "Error",
        json: async () => ({ detail: "oops" }),
      });
    vi.stubGlobal("fetch", fetchMock);
    const { api } = await import("@/app/api/client");
    await expect(api.get("/a")).rejects.toThrow("hello");
    await expect(api.get("/b")).rejects.toThrow("oops");
  });

  it("api.post, api.put and api.delete succeed", async () => {
    vi.stubEnv("VITE_API_URL", "http://127.0.0.1/api");
    vi.resetModules();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const { api } = await import("@/app/api/client");
    await api.post("/p", { x: 1 });
    await api.put("/p", { a: 1 });
    await api.delete("/d");
    expect(fetchMock.mock.calls.some((c) => (c[1] as RequestInit).method === "POST")).toBe(true);
    expect(fetchMock.mock.calls.some((c) => (c[1] as RequestInit).method === "PUT")).toBe(true);
    expect(fetchMock.mock.calls.some((c) => (c[1] as RequestInit).method === "DELETE")).toBe(
      true,
    );
  });

  it("postFormData throws on non-ok response", async () => {
    vi.stubEnv("VITE_API_URL", "http://127.0.0.1/api");
    vi.resetModules();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        statusText: "Bad",
        json: async () => ({}),
      }),
    );
    const { postFormData } = await import("@/app/api/client");
    await expect(postFormData("/inference", new FormData())).rejects.toThrow("Bad");
  });

  it("api.get with skipAuth omits Authorization header", async () => {
    vi.stubEnv("VITE_API_URL", "http://127.0.0.1/api");
    vi.resetModules();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", fetchMock);
    const { api, setAccessToken } = await import("@/app/api/client");
    setAccessToken("secret");
    await api.get("/public", { skipAuth: true });
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
  });
});
