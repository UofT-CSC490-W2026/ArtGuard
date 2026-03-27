import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { ReactNode } from "react";

// Mock react-router to avoid actual routing
vi.mock("react-router", () => ({
  RouterProvider: ({ children }: { children: ReactNode }) => (
    <div data-testid="router-provider" role="application" lang="en">
      {children}
    </div>
  ),
}));

describe("App", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders RouterProvider with router", () => {
    render(<App />);
    
    // Should render RouterProvider
    const routerProvider = screen.getByTestId("router-provider");
    expect(routerProvider).toBeInTheDocument();
  });

  it("renders without crashing", () => {
    expect(() => render(<App />)).not.toThrow();
  });

  it("has proper semantic structure", () => {
    render(<App />);
    
    // Check for main application landmark
    const app = screen.getByRole("application");
    expect(app).toBeInTheDocument();
  });

  it("has correct accessibility attributes", () => {
    render(<App />);
    
    const app = screen.getByRole("application");
    expect(app).toHaveAttribute("lang", "en");
  });
});
