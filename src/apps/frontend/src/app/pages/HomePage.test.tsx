import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { HomePage } from "./HomePage";

vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({
    isAuthenticated: true,
    user: { id: "1", username: "alice", email: "a@b.c" },
    isLoading: false,
    login: vi.fn(),
    signup: vi.fn(),
    logout: vi.fn(),
    updateProfile: vi.fn(),
    changePassword: vi.fn(),
  }),
}));

describe("HomePage authenticated", () => {
  it("shows analyze/history links and profile in footer", () => {
    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: /analyze artwork/i })).toHaveAttribute("href", "/upload");
    expect(screen.getAllByRole("link", { name: /^history$/i }).length).toBeGreaterThanOrEqual(1);
    const footer = screen.getByRole("contentinfo");
    expect(within(footer).getByRole("link", { name: /^profile$/i })).toHaveAttribute("href", "/profile");
  });
});
