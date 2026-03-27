import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HomePage } from "./HomePage";
import { useAuth } from "../contexts/AuthContext";

// Mock useAuth
const mockUseAuth = vi.fn();
vi.mock("../contexts/AuthContext", () => ({
  useAuth: mockUseAuth,
}));

describe("HomePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  function wrapper({ children }: { children: React.ReactNode }) {
    return <MemoryRouter><div>{children}</div></MemoryRouter>;
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

    expect(screen.getByRole("heading", { name: /shaping tomorrow's art authentication with ai/i })).toBeInTheDocument();
    expect(screen.getByText(/ArtGuard/i)).toBeInTheDocument();
  });

  it("renders artwork showcase", () => {
    mockUseAuth.mockReturnValue(anonUser);
    render(<HomePage />, { wrapper });

    // Check for artwork cards
    const artworkCards = screen.getAllByTestId(/artwork-/);
    expect(artworkCards).toHaveLength(4);
    
    // Check first artwork details
    expect(screen.getByTestId("artwork-0")).toBeInTheDocument();
    expect(screen.getByText("Vincent van Gogh")).toBeInTheDocument();
    expect(screen.getByText("The Starry Night")).toBeInTheDocument();
    expect(screen.getByText("1889")).toBeInTheDocument();
  });

  it("renders pipeline information", () => {
    mockUseAuth.mockReturnValue(anonUser);
    render(<HomePage />, { wrapper });

    // Check pipeline steps
    expect(screen.getByText("Upload — image with artist name and title for retrieval.")).toBeInTheDocument();
    expect(screen.getByText("Patches — 224 × 224 px grid per Schaerf et al. (2023).")).toBeInTheDocument();
    expect(screen.getByText("Swin Transformer — per-patch scores, mean-pooled to a painting-level signal.")).toBeInTheDocument();
    expect(screen.getByText("Explanation — RAG-grounded narrative where enabled (Claude, Bedrock, OpenSearch).")).toBeInTheDocument();
  });

  it("renders call to action", () => {
    mockUseAuth.mockReturnValue(anonUser);
    render(<HomePage />, { wrapper });

    const uploadLink = screen.getByRole("link", { name: /upload/i });
    expect(uploadLink).toBeInTheDocument();
    expect(uploadLink).toHaveAttribute("href", "/upload");
  });

  it("shows get started section when not authenticated", () => {
    mockUseAuth.mockReturnValue(anonUser);
    render(<HomePage />, { wrapper });

    expect(screen.getByText(/Get Started/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /login/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /signup/i })).toBeInTheDocument();
  });

  it("shows authenticated user section when authenticated", () => {
    mockUseAuth.mockReturnValue(authUser);
    render(<HomePage />, { wrapper });

    expect(screen.getByText(/Welcome back/i)).toBeInTheDocument();
    expect(screen.getByText("alice")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /history/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /profile/i })).toBeInTheDocument();
  });

  it("renders MosaicImage components correctly", () => {
    mockUseAuth.mockReturnValue(anonUser);
    render(<HomePage />, { wrapper });

    const mosaicImages = screen.getAllByTestId(/artwork-/);
    expect(mosaicImages).toHaveLength(4);
    
    // Check that each mosaic has correct structure
    mosaicImages.forEach((img, index) => {
      expect(img).toBeInTheDocument();
      expect(img).toHaveClass("relative", "overflow-hidden", "rounded-lg");
      
      const artwork = {
        src: "starry-night.jpg",
        artist: "Vincent van Gogh",
        title: "The Starry Night",
        year: "1889",
      };
      expect(img).toHaveAttribute("alt", `${artwork.title} by ${artwork.artist}`);
      expect(img).toHaveAttribute("title", artwork.title);
    });
  });

  it("has correct page structure and styling", () => {
    mockUseAuth.mockReturnValue(anonUser);
    render(<HomePage />, { wrapper });

    // Check main container
    const main = screen.getByRole("main");
    expect(main).toHaveClass("flex-1", "overflow-y-auto");

    // Check sections
    const sections = screen.getAllByRole("region");
    expect(sections.length).toBeGreaterThan(0);
  });

  it("shows analyze/history links when authenticated", () => {
    mockUseAuth.mockReturnValue(authUser);
    render(<HomePage />, { wrapper });

    expect(screen.getByRole("link", { name: /analyze artwork/i })).toHaveAttribute("href", "/upload");
    expect(screen.getAllByRole("link", { name: /^history$/i }).length).toBeGreaterThanOrEqual(1);
  });

  it("shows footer with correct links", () => {
    mockUseAuth.mockReturnValue(authUser);
    render(<HomePage />, { wrapper });

    const footer = screen.getByRole("contentinfo");
    expect(within(footer).getByRole("link", { name: /^profile$/i })).toHaveAttribute("href", "/profile");
  });

  it("handles loading state", () => {
    mockUseAuth.mockReturnValue({
      ...anonUser,
      isLoading: true,
    });

    render(<HomePage />, { wrapper });

    // Should still show main content but with loading indicators
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /shaping tomorrow's art authentication with ai/i })).toBeInTheDocument();
  });

  it("renders responsive layout", () => {
    mockUseAuth.mockReturnValue(anonUser);
    render(<HomePage />, { wrapper });

    // Check responsive containers
    const container = screen.getByRole("main").parentElement;
    expect(container).toHaveClass("min-h-screen");
  });

  it("has proper semantic markup", () => {
    mockUseAuth.mockReturnValue(anonUser);
    render(<HomePage />, { wrapper });

    // Check for proper heading hierarchy
    const heading = screen.getByRole("heading");
    expect(heading).toBeInTheDocument();
    
    // Check for landmark regions
    const regions = screen.getAllByRole("region");
    expect(regions.length).toBeGreaterThan(0);
    
    // Check for proper navigation
    const nav = screen.getByRole("navigation");
    expect(nav).toBeInTheDocument();
  });
});
