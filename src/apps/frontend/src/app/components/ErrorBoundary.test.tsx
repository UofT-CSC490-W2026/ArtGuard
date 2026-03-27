import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Component, type ReactNode } from "react";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "./ErrorBoundary";

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
});
