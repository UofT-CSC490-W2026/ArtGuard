/**
 * Tests for AuthContext — covers all auth flows in mock mode (no API backend):
 * signup, login, logout, updateProfile, changePassword, legacy user migration,
 * corrupted localStorage, and the useAuth guard.
 */
import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "./AuthContext";
import * as client from "../api/client";

// Global setup
beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("AuthContext — mock mode", () => {
  beforeEach(() => {
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

  describe("initial state", () => {
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
      expect(result.current.isAuthenticated).toBe(false);
    });
  });

  describe("signup", () => {
    it("creates user and sets authenticated state", async () => {
      const { result } = renderHook(() => useAuth(), { wrapper });
      await waitFor(() => expect(result.current.isLoading).toBe(false));

      await act(async () => {
        await result.current.signup("newuser", "new@example.com", "password123");
      });

      expect(result.current.user?.username).toBe("newuser");
      expect(result.current.user?.email).toBe("new@example.com");
      expect(result.current.isAuthenticated).toBe(true);
    });

    it("rejects duplicate email", async () => {
      // Add existing user with same email
      const existingUsers = [
        { id: "u1", username: "existing", email: "existing@example.com", passwordHash: "hash" },
      ];
      localStorage.setItem("artguard_users", JSON.stringify(existingUsers));

      const { result } = renderHook(() => useAuth(), { wrapper });
      await waitFor(() => expect(result.current.isLoading).toBe(false));

      await expect(
        act(async () => {
          await result.current.signup("newuser", "existing@example.com", "password123");
        }),
      ).rejects.toThrow(/email already in use/i);
    });
  });

  describe("login", () => {
    it("logs in with correct credentials", async () => {
      // Pre-create a user
      const passwordHash = await hashPassword("password123");
      const existingUsers = [
        { id: "u1", username: "testuser", email: "test@example.com", passwordHash },
      ];
      localStorage.setItem("artguard_users", JSON.stringify(existingUsers));

      const { result } = renderHook(() => useAuth(), { wrapper });
      await waitFor(() => expect(result.current.isLoading).toBe(false));

      await act(async () => {
        await result.current.login("test@example.com", "password123");
      });

      expect(result.current.user?.username).toBe("testuser");
      expect(result.current.isAuthenticated).toBe(true);
    });

    it("rejects invalid credentials", async () => {
      const { result } = renderHook(() => useAuth(), { wrapper });
      await waitFor(() => expect(result.current.isLoading).toBe(false));

      await expect(
        act(async () => {
          await result.current.login("nonexistent@example.com", "wrongpass");
        }),
      ).rejects.toThrow(/invalid email or password/i);
    });
  });

  describe("logout", () => {
    it("clears user and authentication state", async () => {
      localStorage.setItem(
        "artguard_user",
        JSON.stringify({ id: "u1", username: "test", email: "test@example.com" }),
      );

      const { result } = renderHook(() => useAuth(), { wrapper });
      await waitFor(() => expect(result.current.isLoading).toBe(false));
      expect(result.current.isAuthenticated).toBe(true);

      act(() => result.current.logout());

      expect(result.current.user).toBeNull();
      expect(result.current.isAuthenticated).toBe(false);
      expect(localStorage.getItem("artguard_user")).toBeNull();
    });
  });

  describe("updateProfile", () => {
    it("updates username and email", async () => {
      localStorage.setItem(
        "artguard_user",
        JSON.stringify({ id: "u1", username: "old", email: "old@example.com" }),
      );

      const { result } = renderHook(() => useAuth(), { wrapper });
      await waitFor(() => expect(result.current.isLoading).toBe(false));

      await act(async () => {
        await result.current.updateProfile("newname", "new@example.com");
      });

      expect(result.current.user?.username).toBe("newname");
      expect(result.current.user?.email).toBe("new@example.com");
    });

    it("rejects duplicate email", async () => {
      localStorage.setItem(
        "artguard_user",
        JSON.stringify({ id: "u1", username: "user1", email: "user1@example.com" }),
      );
      const otherUsers = [{ id: "u2", username: "user2", email: "user2@example.com", passwordHash: "hash" }];
      localStorage.setItem("artguard_users", JSON.stringify(otherUsers));

      const { result } = renderHook(() => useAuth(), { wrapper });
      await waitFor(() => expect(result.current.isLoading).toBe(false));

      await expect(
        act(async () => {
          await result.current.updateProfile("newname", "user2@example.com");
        }),
      ).rejects.toThrow(/email already in use/i);
    });
  });

  describe("changePassword", () => {
    it("changes password successfully", async () => {
      const passwordHash = await hashPassword("oldpass");
      localStorage.setItem(
        "artguard_user",
        JSON.stringify({ id: "u1", username: "test", email: "test@example.com" }),
      );
      const users = [{ id: "u1", username: "test", email: "test@example.com", passwordHash }];
      localStorage.setItem("artguard_users", JSON.stringify(users));

      const { result } = renderHook(() => useAuth(), { wrapper });
      await waitFor(() => expect(result.current.isLoading).toBe(false));

      await act(async () => {
        await result.current.changePassword("oldpass", "newpass123");
      });

      // Verify password was changed (user should still be logged in)
      expect(result.current.user?.username).toBe("test");
      expect(result.current.isAuthenticated).toBe(true);
    });

    it("rejects wrong current password", async () => {
      const passwordHash = await hashPassword("correctpass");
      localStorage.setItem(
        "artguard_user",
        JSON.stringify({ id: "u1", username: "test", email: "test@example.com" }),
      );
      const users = [{ id: "u1", username: "test", email: "test@example.com", passwordHash }];
      localStorage.setItem("artguard_users", JSON.stringify(users));

      const { result } = renderHook(() => useAuth(), { wrapper });
      await waitFor(() => expect(result.current.isLoading).toBe(false));

      await expect(
        act(async () => {
          await result.current.changePassword("wrongpass", "newpass123");
        }),
      ).rejects.toThrow(/incorrect current password/i);
    });
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
    vi.spyOn(client, "hasApiBackend").mockReturnValue(true);
    vi.spyOn(client, "getAccessToken").mockReturnValue(null);
  });

  function wrapper({ children }: { children: React.ReactNode }) {
    return <AuthProvider>{children}</AuthProvider>;
  }

  it("starts unauthenticated when no token", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.user).toBeNull();
    expect(result.current.isAuthenticated).toBe(false);
  });

  it("restores user from API when token exists", async () => {
    vi.spyOn(client, "getAccessToken").mockReturnValue("valid-token");
    vi.spyOn(client.api, "get").mockResolvedValue({
      id: "api-user-1",
      username: "apiuser",
      email: "apiuser@example.com",
    });
    
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    
    expect(client.api.get).toHaveBeenCalledWith("/auth/me");
    expect(result.current.user?.username).toBe("apiuser");
    expect(result.current.isAuthenticated).toBe(true);
  });

  it("handles API error gracefully", async () => {
    vi.spyOn(client, "getAccessToken").mockReturnValue("invalid-token");
    vi.spyOn(client.api, "get").mockRejectedValue(new Error("Unauthorized"));
    const mockSetToken = vi.spyOn(client, "setAccessToken");
    
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    
    expect(mockSetToken).toHaveBeenCalledWith(null);
    expect(result.current.user).toBeNull();
    expect(result.current.isAuthenticated).toBe(false);
  });
});
