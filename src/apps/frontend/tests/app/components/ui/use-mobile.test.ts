import { renderHook, act } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useIsMobile } from "@/app/components/ui/use-mobile";

// Mock window.matchMedia
const mockMatchMedia = vi.fn();
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: mockMatchMedia,
});

describe("useIsMobile", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns false when window width is above mobile breakpoint", () => {
    // Mock window.innerWidth
    Object.defineProperty(window, "innerWidth", {
      writable: true,
      configurable: true,
      value: 1024,
    });

    // Mock matchMedia to return non-matching media query
    mockMatchMedia.mockReturnValue({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    });

    const { result } = renderHook(() => useIsMobile());

    expect(result.current).toBe(false);
  });

  it("returns true when window width is below mobile breakpoint", () => {
    // Mock window.innerWidth
    Object.defineProperty(window, "innerWidth", {
      writable: true,
      configurable: true,
      value: 600,
    });

    // Mock matchMedia to return matching media query
    mockMatchMedia.mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    });

    const { result } = renderHook(() => useIsMobile());

    expect(result.current).toBe(true);
  });

  it("sets up media query listener on mount", () => {
    const addEventListener = vi.fn();
    mockMatchMedia.mockReturnValue({
      matches: false,
      addEventListener,
      removeEventListener: vi.fn(),
    });

    renderHook(() => useIsMobile());

    expect(mockMatchMedia).toHaveBeenCalledWith(`(max-width: ${768 - 1}px)`);
    expect(addEventListener).toHaveBeenCalledWith("change", expect.any(Function));
  });

  it("cleans up media query listener on unmount", () => {
    const addEventListener = vi.fn();
    const removeEventListener = vi.fn();
    mockMatchMedia.mockReturnValue({
      matches: false,
      addEventListener,
      removeEventListener,
    });

    const { unmount } = renderHook(() => useIsMobile());

    unmount();

    expect(removeEventListener).toHaveBeenCalledWith("change", expect.any(Function));
  });

  it("updates mobile state when media query changes", () => {
    let changeCallback: ((event: MediaQueryListEvent) => void) | null = null;
    const addEventListener = vi.fn((event, callback) => {
      if (event === "change") {
        changeCallback = callback as (event: MediaQueryListEvent) => void;
      }
    });

    mockMatchMedia.mockReturnValue({
      matches: false,
      addEventListener,
      removeEventListener: vi.fn(),
    });

    const { result } = renderHook(() => useIsMobile());

    // Simulate media query change to mobile
    act(() => {
      changeCallback?.({ matches: true } as MediaQueryListEvent);
    });

    expect(result.current).toBe(true);
  });

  it("uses correct mobile breakpoint", () => {
    Object.defineProperty(window, "innerWidth", {
      writable: true,
      configurable: true,
      value: 767,
    });

    const addEventListener = vi.fn();
    mockMatchMedia.mockReturnValue({
      matches: false,
      addEventListener,
      removeEventListener: vi.fn(),
    });

    renderHook(() => useIsMobile());

    expect(mockMatchMedia).toHaveBeenCalledWith("(max-width: 767px)");
  });

  it("handles window width exactly at breakpoint", () => {
    Object.defineProperty(window, "innerWidth", {
      writable: true,
      configurable: true,
      value: 768,
    });

    mockMatchMedia.mockReturnValue({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    });

    const { result } = renderHook(() => useIsMobile());

    expect(result.current).toBe(false);
  });

  it("handles window width below breakpoint", () => {
    Object.defineProperty(window, "innerWidth", {
      writable: true,
      configurable: true,
      value: 767,
    });

    mockMatchMedia.mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    });

    const { result } = renderHook(() => useIsMobile());

    expect(result.current).toBe(true);
  });
});
