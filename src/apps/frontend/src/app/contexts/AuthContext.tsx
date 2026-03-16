import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";
import type { User } from "../types";
import { getErrorMessage } from "../types";
import { hasApiBackend, api } from "../api/client";

const STORAGE_USER = "artguard_user";
const STORAGE_USERS = "artguard_users";

interface StoredUserLegacy {
  id: string;
  username: string;
  email: string;
  password?: string;
}

interface StoredUser {
  id: string;
  username: string;
  email: string;
  passwordHash: string;
}

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (username: string, email: string, password: string) => Promise<void>;
  logout: () => void;
  updateProfile: (username: string, email: string) => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

async function hashPassword(password: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(password);
  const hash = await crypto.subtle.digest("SHA-256", data);
  return btoa(String.fromCharCode(...new Uint8Array(hash)));
}

type StoredUserOrLegacy = StoredUser | StoredUserLegacy;

function getStoredUsers(): StoredUserOrLegacy[] {
  try {
    const raw = localStorage.getItem(STORAGE_USERS);
    if (!raw) return [];
    return JSON.parse(raw) as StoredUserOrLegacy[];
  } catch {
    return [];
  }
}

function isStoredUser(u: StoredUserOrLegacy): u is StoredUser {
  return "passwordHash" in u && typeof (u as StoredUser).passwordHash === "string";
}

function persistStoredUsers(users: StoredUserOrLegacy[]): void {
  localStorage.setItem(STORAGE_USERS, JSON.stringify(users));
}

function persistUser(user: User): void {
  localStorage.setItem(STORAGE_USER, JSON.stringify(user));
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_USER);
      if (stored) {
        const parsed = JSON.parse(stored) as User;
        if (parsed?.id && parsed?.username && parsed?.email) {
          setUser(parsed);
        }
      }
    } catch {
      localStorage.removeItem(STORAGE_USER);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const signup = useCallback(async (username: string, email: string, password: string) => {
    if (username.length < 3) throw new Error("Username must be at least 3 characters");
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new Error("Invalid email format");
    if (password.length < 6) throw new Error("Password must be at least 6 characters");

    if (hasApiBackend()) {
      const res = await api.post<{ user: User }>("/auth/signup", { username, email, password });
      setUser(res.user);
      persistUser(res.user);
      return;
    }

    const existingUsers = getStoredUsers();
    if (existingUsers.some((u) => u.email.toLowerCase() === email.toLowerCase())) {
      throw new Error("Email already registered");
    }

    const passwordHash = await hashPassword(password);
    const newUser: StoredUser = {
      id: crypto.randomUUID?.() ?? Date.now().toString(),
      username,
      email,
      passwordHash,
    };
    existingUsers.push(newUser);
    persistStoredUsers(existingUsers);
    const { id, username: u, email: e } = newUser;
    const userData: User = { id, username: u, email: e };
    setUser(userData);
    persistUser(userData);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    if (hasApiBackend()) {
      const res = await api.post<{ user: User }>("/auth/login", { email, password });
      setUser(res.user);
      persistUser(res.user);
      return;
    }

    const existingUsers = getStoredUsers();
    const emailLower = email.toLowerCase();
    let found: StoredUserOrLegacy | undefined;
    for (const u of existingUsers) {
      if (u.email.toLowerCase() !== emailLower) continue;
      if (isStoredUser(u)) {
        const passwordHash = await hashPassword(password);
        if (u.passwordHash === passwordHash) {
          found = u;
          break;
        }
      } else if ((u as StoredUserLegacy).password === password) {
        found = u;
        const hashed = await hashPassword(password);
        const migrated: StoredUser = { id: u.id, username: u.username, email: u.email, passwordHash: hashed };
        const updated = existingUsers.map((x) => (x === u ? migrated : x));
        persistStoredUsers(updated);
        break;
      }
    }
    if (!found) throw new Error("Invalid email or password");
    const userData: User = { id: found.id, username: found.username, email: found.email };
    setUser(userData);
    persistUser(userData);
  }, []);

  const logout = useCallback(() => {
    setUser(null);
    localStorage.removeItem(STORAGE_USER);
  }, []);

  const updateProfile = useCallback(async (username: string, email: string) => {
    if (username.length < 3) throw new Error("Username must be at least 3 characters");
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new Error("Invalid email format");

    if (hasApiBackend()) {
      const res = await api.put<{ user: User }>("/auth/profile", { username, email });
      setUser(res.user);
      persistUser(res.user);
      return;
    }

    const existingUsers = getStoredUsers();
    const emailTaken = existingUsers.some(
      (u) => u.email.toLowerCase() === email.toLowerCase() && u.id !== user?.id
    );
    if (emailTaken) throw new Error("Email is already in use by another account");

    const updatedUsers = existingUsers.map((u) =>
      u.id === user?.id ? { ...u, username, email } : u
    );
    persistStoredUsers(updatedUsers);
    const updatedUser: User = { id: user!.id, username, email };
    setUser(updatedUser);
    persistUser(updatedUser);
  }, [user?.id]);

  const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
    if (newPassword.length < 6) throw new Error("New password must be at least 6 characters");
    if (hasApiBackend()) {
      await api.post("/auth/change-password", { currentPassword, newPassword });
      return;
    }
    const existingUsers = getStoredUsers();
    const current = existingUsers.find((u) => u.id === user?.id);
    if (!current) throw new Error("Session expired. Please log in again.");
    if (isStoredUser(current)) {
      const currentHash = await hashPassword(currentPassword);
      if (current.passwordHash !== currentHash) throw new Error("Current password is incorrect");
    } else if ((current as StoredUserLegacy).password !== currentPassword) {
      throw new Error("Current password is incorrect");
    }
    const newHash = await hashPassword(newPassword);
    const updated: StoredUserOrLegacy[] = existingUsers.map((u) =>
      u.id === user?.id ? { id: u.id, username: u.username, email: u.email, passwordHash: newHash } : u
    );
    persistStoredUsers(updated);
  }, [user?.id]);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        signup,
        logout,
        updateProfile,
        changePassword,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
