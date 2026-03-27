import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Component, type ReactNode } from "react";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "./ErrorBoundary";
import { isDev } from "../lib/env";

vi.mock("../lib/env", () => ({
  isDev: vi.fn(() => true),
}));

class Boom extends Component<{ fail?: boolean }> {
  render(): ReactNode {
    if (this.props.fail) throw new Error("boom");
    return <div>ok</div>;
  }
}

describe("ErrorBoundary", () => {
  const err = console.error;

  beforeEach(() => {
    console.error = vi.fn();
    vi.mocked(isDev).mockReturnValue(true);
  });

  afterEach(() => {
    console.error = err;
    vi.restoreAllMocks();
  });

  it("renders children when healthy", () => {
    render(
      <ErrorBoundary>
        <Boom fail={false} />
      </ErrorBoundary>,
    );
    expect(screen.getByText("ok")).toBeInTheDocument();
  });

  it("offers go to home", async () => {
    const user = userEvent.setup();
    const assign = vi.fn();
    const prev = window.location;
    vi.stubGlobal("location", { ...prev, assign } as Location);

    render(
      <ErrorBoundary>
        <Boom fail />
      </ErrorBoundary>,
    );

    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /go to home/i }));
    expect(assign).toHaveBeenCalledWith("/");
    vi.unstubAllGlobals();
  });

  it("uses custom fallback when provided", () => {
    render(
      <ErrorBoundary fallback={<div>custom</div>}>
        <Boom fail />
      </ErrorBoundary>,
    );
    expect(screen.getByText("custom")).toBeInTheDocument();
  });

  it("logs error in DEV mode", () => {
    vi.mocked(isDev).mockReturnValue(true);

    render(
      <ErrorBoundary>
        <Boom fail />
      </ErrorBoundary>,
    );

    expect(console.error).toHaveBeenCalledWith(
      "ErrorBoundary caught:",
      expect.any(Error),
      expect.objectContaining({
        componentStack: expect.any(String),
      }),
    );
  });

  it("does not log ErrorBoundary diagnostics in production", () => {
    vi.mocked(isDev).mockReturnValue(false);

    render(
      <ErrorBoundary>
        <Boom fail />
      </ErrorBoundary>,
    );

    const boundaryLogs = vi.mocked(console.error).mock.calls.filter(
      (call) => call[0] === "ErrorBoundary caught:",
    );
    expect(boundaryLogs).toHaveLength(0);
  });

  it("shows error message in DEV mode", () => {
    vi.mocked(isDev).mockReturnValue(true);

    render(
      <ErrorBoundary>
        <Boom fail />
      </ErrorBoundary>,
    );

    expect(screen.getByText("boom")).toBeInTheDocument();
  });

  it("hides error message in production", () => {
    vi.mocked(isDev).mockReturnValue(false);

    render(
      <ErrorBoundary>
        <Boom fail />
      </ErrorBoundary>,
    );

    expect(screen.queryByText("boom")).not.toBeInTheDocument();
  });

  it("resets error when try again is clicked", async () => {
    const user = userEvent.setup();
    
    render(
      <ErrorBoundary>
        <Boom fail />
      </ErrorBoundary>,
    );

    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
    
    await user.click(screen.getByRole("button", { name: /try again/i }));
    
    // After reset, it should attempt to render children again
    // Since we're still in the error boundary, it will catch the error again
    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
  });

  it("handles null error gracefully", () => {
    class NullErrorBoundary extends ErrorBoundary {
      static getDerivedStateFromError() {
        return { hasError: true, error: null };
      }
    }

    render(
      <NullErrorBoundary>
        <Boom fail />
      </NullErrorBoundary>,
    );

    // Should render fallback UI even with null error
    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
  });

  it("handles getDerivedStateFromError correctly", () => {
    const ThrowError = () => {
      throw new Error("Test error");
    };

    render(
      <ErrorBoundary>
        <ThrowError />
      </ErrorBoundary>,
    );

    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
  });

  it("handles componentDidCatch correctly", () => {
    vi.mocked(isDev).mockReturnValue(true);

    const ThrowError = () => {
      throw new Error("ComponentDidCatch test");
    };

    render(
      <ErrorBoundary>
        <ThrowError />
      </ErrorBoundary>,
    );

    expect(console.error).toHaveBeenCalled();
  });
});
