import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

globalThis.ResizeObserver = ResizeObserverStub;

// Mock crypto.subtle for password hashing in tests
if (!globalThis.crypto?.subtle) {
  const mockSubtleCrypto = {
    digest: vi.fn().mockResolvedValue(new ArrayBuffer(32)),
    decrypt: vi.fn(),
    deriveBits: vi.fn(),
    deriveKey: vi.fn(),
    encrypt: vi.fn(),
    exportKey: vi.fn(),
    generateKey: vi.fn(),
    importKey: vi.fn(),
    sign: vi.fn(),
    unwrapKey: vi.fn(),
    verify: vi.fn(),
    wrapKey: vi.fn(),
  };
  
  globalThis.crypto = {
    ...globalThis.crypto,
    subtle: mockSubtleCrypto,
  };
}

if (typeof Element !== "undefined") {
  if (!Element.prototype.setPointerCapture) {
    Element.prototype.setPointerCapture = vi.fn() as typeof Element.prototype.setPointerCapture;
  }
  if (!Element.prototype.releasePointerCapture) {
    Element.prototype.releasePointerCapture = vi.fn() as typeof Element.prototype.releasePointerCapture;
  }
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = vi.fn(() => false) as typeof Element.prototype.hasPointerCapture;
  }
  // Radix Select calls scrollIntoView; jsdom may omit or stub it incompletely.
  Element.prototype.scrollIntoView = vi.fn() as typeof Element.prototype.scrollIntoView;
}

afterEach(() => {
  cleanup();
});

HTMLCanvasElement.prototype.getContext = vi.fn(() => ({
  setTransform: vi.fn(),
  clearRect: vi.fn(),
  fillRect: vi.fn(),
  strokeRect: vi.fn(),
  fillStyle: "",
  strokeStyle: "",
  lineWidth: 1,
})) as unknown as typeof HTMLCanvasElement.prototype.getContext;
