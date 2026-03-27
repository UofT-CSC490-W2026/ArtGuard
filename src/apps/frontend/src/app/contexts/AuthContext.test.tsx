/**
 * Tests for AuthContext — covers all auth flows in mock mode (no API backend):
 * signup, login, logout, updateProfile, changePassword, legacy user migration,
 * corrupted localStorage, and the useAuth guard.
 */
import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "./AuthContext";
import * as client from "../api/client";

// Always use mock mode (no API backend)
beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
  vi.spyOn(client, "hasApiBackend").mockReturnValue(false);
  vi.spyOn(client, "getAccessToken").mockReturnValue(null);
});

async function hashPassword(password: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(password);
  const hash = await crypto.subtle.digest("SHA-256", data);
  return btoa(String.fromCharCode(...new Uint8Array(hash)));
}

function wrapper({ children }: { children: React.ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}

describe("AuthContext — initial state", () => {
  it("starts unauthenticated with no user", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.user).toBeNull();
    expect(result.current.isAuthenticated).toBe(false);
  });

  it("restores user from valid localStorage on mount", async () => {
    localStorage.setItem(
      "artguard_user",
      JSON.stringify({ id: "u1", username: "alice", email: "alice@example.com" }),
    );
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.user?.username).toBe("alice");
    expect(result.current.isAuthenticated).toBe(true);
  });

  it("ignores corrupted artguard_user in localStorage", async () => {
    localStorage.setItem("artguard_user", "{bad json{{");
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.user).toBeNull();
  });

  it("ignores user object missing required fields", async () => {
    localStorage.setItem("artguard_user", JSON.stringify({ id: "u1" })); // missing username/email
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.user).toBeNull();
  });
});

describe("AuthContext — signup", () => {
  it("creates user and sets authenticated state", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.signup("newuser", "new@example.com", "password123");
    });

    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.user?.username).toBe("newuser");
    expect(result.current.user?.email).toBe("new@example.com");
  });

  it("throws when username is too short", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await expect(
      act(async () => result.current.signup("ab", "x@x.com", "password123")),
    ).rejects.toThrow(/at least 3 characters/i);
  });

  it("throws when email is invalid", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await expect(
      act(async () => result.current.signup("user", "not-an-email", "password123")),
    ).rejects.toThrow(/invalid email/i);
  });

  it("throws when password is too short", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await expect(
      act(async () => result.current.signup("user", "x@x.com", "12345")),
    ).rejects.toThrow(/at least 6 characters/i);
  });

  it("throws when email is already registered", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.signup("user1", "taken@example.com", "password123");
    });

    await expect(
      act(async () => result.current.signup("user2", "taken@example.com", "password123")),
    ).rejects.toThrow(/already registered/i);
  });

  it("persists user to localStorage after signup", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.signup("persisted", "persist@example.com", "password123");
    });

    const stored = JSON.parse(localStorage.getItem("artguard_user") || "null");
    expect(stored?.username).toBe("persisted");
  });
});

describe("AuthContext — login", () => {
  it("logs in with correct credentials", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.signup("loginuser", "login@example.com", "password123");
      result.current.logout();
    });

    await act(async () => {
      await result.current.login("login@example.com", "password123");
    });

    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.user?.username).toBe("loginuser");
  });

  it("throws on wrong password", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.signup("user", "user@example.com", "correctpass");
      result.current.logout();
    });

    await expect(
      act(async () => result.current.login("user@example.com", "wrongpass")),
    ).rejects.toThrow(/invalid email or password/i);
  });

  it("throws on unknown email", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await expect(
      act(async () => result.current.login("nobody@example.com", "password123")),
    ).rejects.toThrow(/invalid email or password/i);
  });

  it("migrates legacy user (plain password) on login", async () => {
    // Seed a legacy user with plain password (old format)
    localStorage.setItem(
      "artguard_users",
      JSON.stringify([{ id: "legacy-1", username: "legacy", email: "legacy@example.com", password: "plainpass" }]),
    );

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.login("legacy@example.com", "plainpass");
    });

    expect(result.current.isAuthenticated).toBe(true);

    // After migration, the user should have passwordHash instead of password
    const users = JSON.parse(localStorage.getItem("artguard_users") || "[]");
    const migrated = users.find((u: { id: string }) => u.id === "legacy-1");
    expect(migrated).toHaveProperty("passwordHash");
    expect(migrated).not.toHaveProperty("password");
  });
});

describe("AuthContext — logout", () => {
  it("clears user and authentication state", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.signup("logoutuser", "logout@example.com", "password123");
    });
    expect(result.current.isAuthenticated).toBe(true);

    act(() => result.current.logout());
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.user).toBeNull();
    expect(localStorage.getItem("artguard_user")).toBeNull();
  });
});

describe("AuthContext — updateProfile", () => {
  it("updates username and email", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.signup("original", "original@example.com", "password123");
    });

    await act(async () => {
      await result.current.updateProfile("updated", "updated@example.com");
    });

    expect(result.current.user?.username).toBe("updated");
    expect(result.current.user?.email).toBe("updated@example.com");
  });

  it("throws when username is too short", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.signup("user", "user@example.com", "password123");
    });

    await expect(
      act(async () => result.current.updateProfile("ab", "user@example.com")),
    ).rejects.toThrow(/at least 3 characters/i);
  });

  it("throws when email is invalid", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.signup("user", "user@example.com", "password123");
    });

    await expect(
      act(async () => result.current.updateProfile("user", "not-an-email")),
    ).rejects.toThrow(/invalid email/i);
  });

  it("throws when email is taken by another user", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    // Create two users
    await act(async () => {
      await result.current.signup("user1", "user1@example.com", "password123");
      result.current.logout();
      await result.current.signup("user2", "user2@example.com", "password123");
    });

    await expect(
      act(async () => result.current.updateProfile("user2", "user1@example.com")),
    ).rejects.toThrow(/already in use/i);
  });
});

describe("AuthContext — changePassword", () => {
  it("changes password successfully", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.signup("pwuser", "pw@example.com", "oldpass123");
    });

    await act(async () => {
      await result.current.changePassword("oldpass123", "newpass456");
    });

    // Should not throw — verify by logging in with new password
    act(() => result.current.logout());
    await act(async () => {
      await result.current.login("pw@example.com", "newpass456");
    });
    expect(result.current.isAuthenticated).toBe(true);
  });

  it("throws when new password is too short", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.signup("user", "user@example.com", "password123");
    });

    await expect(
      act(async () => result.current.changePassword("password123", "12345")),
    ).rejects.toThrow(/at least 6 characters/i);
  });

  it("throws when current password is wrong", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.signup("user", "user@example.com", "password123");
    });

    await expect(
      act(async () => result.current.changePassword("wrongpass", "newpass456")),
    ).rejects.toThrow(/incorrect/i);
  });

  it("throws when session is expired (no user in storage)", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.signup("user", "user@example.com", "password123");
    });

    // Simulate session expiry by clearing users storage
    localStorage.removeItem("artguard_users");

    await expect(
      act(async () => result.current.changePassword("password123", "newpass456")),
    ).rejects.toThrow(/session expired/i);
  });
});

describe("useAuth guard", () => {
  it("throws when used outside AuthProvider", () => {
    // Suppress console.error for this test
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => renderHook(() => useAuth())).toThrow(/must be used within an AuthProvider/i);
    consoleSpy.mockRestore();
  });
});

describe("AuthContext — API backend mode", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
    // Switch to API backend mode
    vi.spyOn(client, "hasApiBackend").mockReturnValue(true);
    vi.spyOn(client, "getAccessToken").mockReturnValue(null);
  });

  it("signup calls POST /auth/signup and stores token", async () => {
    const mockPost = vi.spyOn(client.api, "post").mockResolvedValue({
      access_token: "jwt-token",
      token_type: "bearer",
      user: { id: "api-u1", username: "apiuser", email: "api@example.com" },
    });
    const mockSetToken = vi.spyOn(client, "setAccessToken");

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.signup("apiuser", "api@example.com", "password123");
    });

    expect(mockPost).toHaveBeenCalledWith(
      "/auth/signup",
      { username: "apiuser", email: "api@example.com", password: "password123" },
      { skipAuth: true },
    );
    expect(mockSetToken).toHaveBeenCalledWith("jwt-token");
    expect(result.current.user?.username).toBe("apiuser");
  });

  it("login calls POST /auth/login and stores token", async () => {
    const mockPost = vi.spyOn(client.api, "post").mockResolvedValue({
      access_token: "login-token",
      token_type: "bearer",
      user: { id: "api-u2", username: "loginuser", email: "login@example.com" },
    });
    const mockSetToken = vi.spyOn(client, "setAccessToken");

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.login("login@example.com", "password123");
    });

    expect(mockPost).toHaveBeenCalledWith(
      "/auth/login",
      { email: "login@example.com", password: "password123" },
      { skipAuth: true },
    );
    expect(mockSetToken).toHaveBeenCalledWith("login-token");
    expect(result.current.isAuthenticated).toBe(true);
  });

  it("init fetches /auth/me when token exists", async () => {
    vi.spyOn(client, "getAccessToken").mockReturnValue("existing-token");
    vi.spyOn(client.api, "get").mockResolvedValue({
      id: "me-u1", username: "meuser", email: "me@example.com",
    });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.user?.username).toBe("meuser");
    expect(result.current.isAuthenticated).toBe(true);
  });

  it("init clears token when /auth/me fails", async () => {
    vi.spyOn(client, "getAccessToken").mockReturnValue("bad-token");
    vi.spyOn(client.api, "get").mockRejectedValue(new Error("401 Unauthorized"));
    const mockSetToken = vi.spyOn(client, "setAccessToken");

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.user).toBeNull();
    expect(mockSetToken).toHaveBeenCalledWith(null);
  });

  it("updateProfile calls PUT /auth/profile", async () => {
    vi.spyOn(client, "getAccessToken").mockReturnValue("token");
    vi.spyOn(client.api, "get").mockResolvedValue({
      id: "u1", username: "user", email: "user@example.com",
    });
    const mockPut = vi.spyOn(client.api, "put").mockResolvedValue({
      access_token: "new-token",
      token_type: "bearer",
      user: { id: "u1", username: "updated", email: "updated@example.com" },
    });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.updateProfile("updated", "updated@example.com");
    });

    expect(mockPut).toHaveBeenCalledWith("/auth/profile", {
      username: "updated", email: "updated@example.com",
    });
    expect(result.current.user?.username).toBe("updated");
  });

  it("changePassword calls POST /auth/change-password", async () => {
    vi.spyOn(client, "getAccessToken").mockReturnValue("token");
    vi.spyOn(client.api, "get").mockResolvedValue({
      id: "u1", username: "user", email: "user@example.com",
    });
    const mockPost = vi.spyOn(client.api, "post").mockResolvedValue({ ok: true });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.changePassword("oldpass", "newpass123");
    });

    expect(mockPost).toHaveBeenCalledWith("/auth/change-password", {
      currentPassword: "oldpass", newPassword: "newpass123",
    });
  });

  it("logout clears token via setAccessToken(null)", async () => {
    vi.spyOn(client, "getAccessToken").mockReturnValue("token");
    vi.spyOn(client.api, "get").mockResolvedValue({
      id: "u1", username: "user", email: "user@example.com",
    });
    const mockSetToken = vi.spyOn(client, "setAccessToken");

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => result.current.logout());

    expect(mockSetToken).toHaveBeenCalledWith(null);
    expect(result.current.user).toBeNull();
  });
});
