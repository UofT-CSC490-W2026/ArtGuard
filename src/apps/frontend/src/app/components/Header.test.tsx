import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Header } from "./Header";
import { useAuth } from "../contexts/AuthContext";

vi.mock("../contexts/AuthContext", () => ({
  useAuth: vi.fn(),
}));

const mockLogout = vi.fn();

function mockUnauthenticated() {
  vi.mocked(useAuth).mockReturnValue({
    user: null,
    isAuthenticated: false,
    isLoading: false,
    login: vi.fn(),
    signup: vi.fn(),
    logout: mockLogout,
    updateProfile: vi.fn(),
    changePassword: vi.fn(),
  });
}

function mockAuthenticated(username = "testuser") {
  vi.mocked(useAuth).mockReturnValue({
    user: { id: "u1", username, email: "test@example.com" },
    isAuthenticated: true,
    isLoading: false,
    login: vi.fn(),
    signup: vi.fn(),
    logout: mockLogout,
    updateProfile: vi.fn(),
    changePassword: vi.fn(),
  });
}

describe("Header", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders ArtGuard logo link", () => {
    mockUnauthenticated();
    render(<MemoryRouter><Header /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "ArtGuard" })).toBeInTheDocument();
  });

  it("shows auth link when showAuthLinks is true", () => {
    mockUnauthenticated();
    render(
      <MemoryRouter>
        <Header showAuthLinks authLinkText="Sign Up" authLinkTo="/signup" />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Sign Up" })).toBeInTheDocument();
  });

  it("does not show auth link when showAuthLinks is false", () => {
    mockUnauthenticated();
    render(
      <MemoryRouter>
        <Header showAuthLinks={false} authLinkText="Sign Up" authLinkTo="/signup" />
      </MemoryRouter>,
    );
    expect(screen.queryByRole("link", { name: "Sign Up" })).not.toBeInTheDocument();
  });

  it("shows Upload and History nav links when authenticated", () => {
    mockAuthenticated();
    render(<MemoryRouter><Header /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "Upload" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "History" })).toBeInTheDocument();
  });

  it("shows username in dropdown trigger when authenticated", () => {
    mockAuthenticated("alice");
    render(<MemoryRouter><Header /></MemoryRouter>);
    expect(screen.getByText("alice")).toBeInTheDocument();
  });

  it("does not show nav links when unauthenticated", () => {
    mockUnauthenticated();
    render(<MemoryRouter><Header /></MemoryRouter>);
    expect(screen.queryByRole("link", { name: "Upload" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "History" })).not.toBeInTheDocument();
  });

  it("calls logout when Log out is clicked", async () => {
    const user = userEvent.setup();
    mockAuthenticated();
    render(<MemoryRouter><Header /></MemoryRouter>);

    // Open dropdown
    await user.click(screen.getByText("testuser"));
    // Click Log out
    await user.click(screen.getByText(/log out/i));
    expect(mockLogout).toHaveBeenCalledOnce();
  });

  it("dropdown contains Profile link", async () => {
    const user = userEvent.setup();
    mockAuthenticated();
    render(<MemoryRouter><Header /></MemoryRouter>);

    await user.click(screen.getByText("testuser"));
    expect(screen.getByRole("link", { name: /profile/i })).toBeInTheDocument();
  });
});
