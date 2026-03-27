import { render, screen, fireEvent } from "@testing-library/react";
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

  it("has correct header structure", () => {
    mockUnauthenticated();
    render(<MemoryRouter><Header /></MemoryRouter>);
    
    const header = screen.getByRole("banner");
    expect(header).toHaveClass("border-b", "border-border", "bg-background");
    
    const container = header.querySelector(".mx-auto");
    expect(container).toHaveClass("flex", "max-w-6xl", "items-center", "justify-between", "px-6", "py-6");
  });

  it("handles loading state correctly", () => {
    vi.mocked(useAuth).mockReturnValue({
      user: null,
      isAuthenticated: false,
      isLoading: true,
      login: vi.fn(),
      signup: vi.fn(),
      logout: vi.fn(),
      updateProfile: vi.fn(),
      changePassword: vi.fn(),
    });

    render(<MemoryRouter><Header showAuthLinks={true} /></MemoryRouter>);

    // Should still show auth links but not user menu
    expect(screen.getByRole("link", { name: "Sign Up" })).toBeInTheDocument();
    expect(screen.queryByText("testuser")).not.toBeInTheDocument();
  });

  it("handles null user gracefully", () => {
    vi.mocked(useAuth).mockReturnValue({
      user: null,
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      signup: vi.fn(),
      logout: vi.fn(),
      updateProfile: vi.fn(),
      changePassword: vi.fn(),
    });

    render(<MemoryRouter><Header showAuthLinks={true} /></MemoryRouter>);

    // Should not crash when user is null but authenticated
    expect(screen.queryByText("testuser")).not.toBeInTheDocument();
  });

  it("uses custom auth link text", () => {
    mockUnauthenticated();
    render(
      <MemoryRouter>
        <Header showAuthLinks authLinkText="Custom Auth" authLinkTo="/custom-auth" />
      </MemoryRouter>
    );
    
    expect(screen.getByRole("link", { name: "Custom Auth" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Custom Auth" })).toHaveAttribute("href", "/custom-auth");
  });

  it("handles missing authLinkText gracefully", () => {
    mockUnauthenticated();
    render(
      <MemoryRouter>
        <Header showAuthLinks={true} />
      </MemoryRouter>
    );
    
    // Should not crash and should not show auth link
    expect(screen.queryByRole("link", { name: /Sign Up|Sign In/i })).not.toBeInTheDocument();
  });

  it("handles missing authLinkTo gracefully", () => {
    mockUnauthenticated();
    render(
      <MemoryRouter>
        <Header showAuthLinks={true} authLinkText="Sign In" />
      </MemoryRouter>
    );
    
    // Should show auth link without href
    expect(screen.getByRole("link", { name: "Sign In" })).toBeInTheDocument();
  });
});
