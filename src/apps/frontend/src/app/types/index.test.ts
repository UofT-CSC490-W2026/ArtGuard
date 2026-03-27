import { describe, expect, it } from "vitest";
import { getErrorMessage } from "./index";

describe("getErrorMessage", () => {
  it("handles Error instances", () => {
    expect(getErrorMessage(new Error("x"))).toBe("x");
  });

  it("handles object with message", () => {
    expect(getErrorMessage({ message: "m" })).toBe("m");
  });

  it("falls back for unknown values", () => {
    expect(getErrorMessage(null)).toBe("An unexpected error occurred");
    expect(getErrorMessage("x")).toBe("An unexpected error occurred");
  });
});
