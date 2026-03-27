/**
 * Tests for routes.tsx — verifies the router is configured with all expected paths
 * and that protected routes wrap the correct pages.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

// Mock all pages so we don't need full rendering context
vi.mock("./pages/HomePage", () => ({ HomePage: () => <div data-testid="home-page" /> }));
vi.mock("./pages/SignUpPage", () => ({ SignUpPage: () => <div data-testid="signup-page" /> }));
vi.mock("./pages/LoginPage", () => ({ LoginPage: () => <div data-testid="login-page" /> }));
vi.mock("./pages/UploadPage", () => ({ UploadPage: () => <div data-testid="upload-page" /> }));
vi.mock("./pages/ResultsPage", () => ({ ResultsPage: () => <div data-testid="results-page" /> }));
vi.mock("./pages/HistoryPage", () => ({ HistoryPage: () => <div data-testid="history-page" /> }));
vi.mock("./pages/ProfilePage", () => ({ ProfilePage: () => <div data-testid="profile-page" /> }));
vi.mock("./components/RootLayout", () => ({
  RootLayout: () => {
    const { Outlet } = require("react-router");
    return <div data-testid="root-layout"><Outlet /></div>;
  },
}));
vi.mock("./components/ProtectedRoute", () => ({
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="protected">{children}</div>
  ),
}));

// Import after mocks
import { router } from "./routes";

function renderAt(path: string) {
  // Create a memory router with the same routes but starting at `path`
  const routes = router.routes;
  const memRouter = createMemoryRouter(routes, { initialEntries: [path] });
  return render(<RouterProvider router={memRouter} />);
}

describe("routes", () => {
  it("/ renders HomePage inside RootLayout", async () => {
    renderAt("/");
    await waitFor(() => expect(screen.getByTestId("home-page")).toBeInTheDocument());
    expect(screen.getByTestId("root-layout")).toBeInTheDocument();
  });

  it("/signup renders SignUpPage", async () => {
    renderAt("/signup");
    await waitFor(() => expect(screen.getByTestId("signup-page")).toBeInTheDocument());
  });

  it("/login renders LoginPage", async () => {
    renderAt("/login");
    await waitFor(() => expect(screen.getByTestId("login-page")).toBeInTheDocument());
  });

  it("/upload renders UploadPage inside ProtectedRoute", async () => {
    renderAt("/upload");
    await waitFor(() => expect(screen.getByTestId("upload-page")).toBeInTheDocument());
    expect(screen.getByTestId("protected")).toBeInTheDocument();
  });

  it("/results renders ResultsPage inside ProtectedRoute", async () => {
    renderAt("/results");
    await waitFor(() => expect(screen.getByTestId("results-page")).toBeInTheDocument());
    expect(screen.getByTestId("protected")).toBeInTheDocument();
  });

  it("/history renders HistoryPage inside ProtectedRoute", async () => {
    renderAt("/history");
    await waitFor(() => expect(screen.getByTestId("history-page")).toBeInTheDocument());
    expect(screen.getByTestId("protected")).toBeInTheDocument();
  });

  it("/profile renders ProfilePage inside ProtectedRoute", async () => {
    renderAt("/profile");
    await waitFor(() => expect(screen.getByTestId("profile-page")).toBeInTheDocument());
    expect(screen.getByTestId("protected")).toBeInTheDocument();
  });
});
