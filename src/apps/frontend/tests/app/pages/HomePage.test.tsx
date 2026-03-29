import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HomePage } from "@/app/pages/HomePage";

const { mockUseAuth } = vi.hoisted(() => ({
  mockUseAuth: vi.fn(),
}));

vi.mock("@/app/contexts/AuthContext", () => ({
  useAuth: mockUseAuth,
}));

describe("HomePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  function wrapper({ children }: { children: React.ReactNode }) {
    return (
      <MemoryRouter>
        <div>{children}</div>
      </MemoryRouter>
    );
  }

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

  const anonUser = {
    ...authUser,
    isAuthenticated: false,
    user: null,
  };

  it("renders main heading", () => {
    mockUseAuth.mockReturnValue(anonUser);
    render(<HomePage />, { wrapper });

    expect(
      screen.getByRole("heading", { name: /authenticate art\. understand why\./i }),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/^ArtGuard$/).length).toBeGreaterThan(0);
  });

  it("renders mosaic artwork images", () => {
    mockUseAuth.mockReturnValue(anonUser);
    const { container } = render(<HomePage />, { wrapper });

    const artImages = container.querySelectorAll('img[src^="/art/"]');
    expect(artImages.length).toBe(3);
    expect(screen.getByText("Vincent van Gogh")).toBeInTheDocument();
    expect(screen.getByText("Johannes Vermeer")).toBeInTheDocument();
    expect(screen.getByText("Leonardo da Vinci")).toBeInTheDocument();
  });

  it("renders editorial copy tiles", () => {
    mockUseAuth.mockReturnValue(anonUser);
    render(<HomePage />, { wrapper });

    expect(
      screen.getByRole("heading", {
        name: /grounded explanations, not black-box verdicts/i,
      }),
    ).toBeInTheDocument();
  });

  it("renders hero primary and secondary links for guests", () => {
    mockUseAuth.mockReturnValue(anonUser);
    render(<HomePage />, { wrapper });

    expect(screen.getByRole("link", { name: /get started/i })).toHaveAttribute("href", "/signup");
    expect(screen.getAllByRole("link", { name: /^log in$/i })[0]).toHaveAttribute("href", "/login");
  });

  it("renders hero links for authenticated users", () => {
    mockUseAuth.mockReturnValue(authUser);
    render(<HomePage />, { wrapper });

    expect(screen.getByRole("link", { name: /analyze artwork/i })).toHaveAttribute("href", "/upload");
    const historyToUpload = screen
      .getAllByRole("link", { name: /^history$/i })
      .filter((el) => el.getAttribute("href") === "/history");
    expect(historyToUpload.length).toBeGreaterThan(0);
  });

  it("footer shows auth links when logged out", () => {
    mockUseAuth.mockReturnValue(anonUser);
    render(<HomePage />, { wrapper });

    const footer = screen.getByRole("contentinfo");
    expect(within(footer).getByRole("link", { name: /^log in$/i })).toHaveAttribute("href", "/login");
    expect(within(footer).getByRole("link", { name: /^sign up$/i })).toHaveAttribute("href", "/signup");
  });

  it("footer shows profile when authenticated", () => {
    mockUseAuth.mockReturnValue(authUser);
    render(<HomePage />, { wrapper });

    const footer = screen.getByRole("contentinfo");
    expect(within(footer).getByRole("link", { name: /^profile$/i })).toHaveAttribute("href", "/profile");
  });

  it("ignores loading flag for layout (only isAuthenticated affects copy)", () => {
    mockUseAuth.mockReturnValue({
      ...anonUser,
      isLoading: true,
    });
    render(<HomePage />, { wrapper });

    expect(
      screen.getByRole("heading", { name: /authenticate art\. understand why\./i }),
    ).toBeInTheDocument();
  });

  it("uses min-h-screen root", () => {
    mockUseAuth.mockReturnValue(anonUser);
    render(<HomePage />, { wrapper });
    expect(document.querySelector(".min-h-screen")).toBeInTheDocument();
  });
});
