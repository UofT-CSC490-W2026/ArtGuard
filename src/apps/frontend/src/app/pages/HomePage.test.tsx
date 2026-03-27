import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { HomePage } from "./HomePage";

const mockUseAuth = vi.fn();
vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}));

const authUser = {
  isAuthenticated: true,
  user: { id: "1", username: "alice", email: "a@b.c" },
  isLoading: false,
  login: vi.fn(),
  signup: vi.fn(),
  logout: vi.fn(),
  updateProfile: vi.fn(),
  changePassword: vi.fn(),
};

const anonUser = { ...authUser, isAuthenticated: false, user: null };

describe("HomePage authenticated", () => {
  it("shows analyze/history links and profile in footer", () => {
    mockUseAuth.mockReturnValue(authUser);
    render(<MemoryRouter><HomePage /></MemoryRouter>);
    expect(screen.getByRole("link", { name: /analyze artwork/i })).toHaveAttribute("href", "/upload");
    expect(screen.getAllByRole("link", { name: /^history$/i }).length).toBeGreaterThanOrEqual(1);
    const footer = screen.getByRole("contentinfo");
    expect(within(footer).getByRole("link", { name: /^profile$/i })).toHaveAttribute("href", "/profile");
  });
});

describe("HomePage unauthenticated", () => {
  it("shows Get started and Log in links", () => {
    mockUseAuth.mockReturnValue(anonUser);
    render(<MemoryRouter><HomePage /></MemoryRouter>);
    expect(screen.getByRole("link", { name: /get started/i })).toHaveAttribute("href", "/signup");
    expect(screen.getByRole("link", { name: /^log in$/i })).toHaveAttribute("href", "/login");
  });

  it("shows Log In and Sign Up in footer for anon users", () => {
    mockUseAuth.mockReturnValue(anonUser);
    render(<MemoryRouter><HomePage /></MemoryRouter>);
    const footer = screen.getByRole("contentinfo");
    expect(within(footer).getByRole("link", { name: /^log in$/i })).toBeInTheDocument();
    expect(within(footer).getByRole("link", { name: /^sign up$/i })).toBeInTheDocument();
  });

  it("shows hero heading", () => {
    mockUseAuth.mockReturnValue(anonUser);
    render(<MemoryRouter><HomePage /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: /shaping tomorrow/i })).toBeInTheDocument();
  });
});
