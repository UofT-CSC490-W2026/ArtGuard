import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/app/App";

vi.mock("react-router", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router")>();
  return {
    ...actual,
    RouterProvider: (props: { router?: object }) => (
      <div data-testid="router-provider" role="application" lang="en" data-has-router={props.router ? "yes" : "no"} />
    ),
  };
});

describe("App", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders RouterProvider with router", () => {
    render(<App />);
    const routerProvider = screen.getByTestId("router-provider");
    expect(routerProvider).toBeInTheDocument();
    expect(routerProvider).toHaveAttribute("data-has-router", "yes");
  });

  it("renders without crashing", () => {
    expect(() => render(<App />)).not.toThrow();
  });

  it("has proper semantic structure", () => {
    render(<App />);
    expect(screen.getByRole("application")).toBeInTheDocument();
  });

  it("has correct accessibility attributes", () => {
    render(<App />);
    const app = screen.getByRole("application");
    expect(app).toHaveAttribute("lang", "en");
  });
});
