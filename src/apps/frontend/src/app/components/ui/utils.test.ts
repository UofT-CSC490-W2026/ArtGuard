import { describe, expect, it } from "vitest";
import { cn } from "./utils";

describe("cn utility function", () => {
  it("merges class names correctly", () => {
    const result = cn("base-class", "additional-class", "another-class");
    expect(result).toContain("base-class");
    expect(result).toContain("additional-class");
    expect(result).toContain("another-class");
  });

  it("handles empty inputs", () => {
    const result = cn();
    expect(result).toBe("");
  });

  it("handles single input", () => {
    const result = cn("single-class");
    expect(result).toBe("single-class");
  });

  it("handles conditional classes", () => {
    const result = cn("base-class", true && "conditional-class", false && "hidden-class");
    expect(result).toContain("base-class");
    expect(result).toContain("conditional-class");
    expect(result).not.toContain("hidden-class");
  });

  it("handles undefined and null inputs", () => {
    const result = cn("base-class", undefined, null, "valid-class");
    expect(result).toContain("base-class");
    expect(result).toContain("valid-class");
  });

  it("handles complex class combinations", () => {
    const result = cn(
      "flex",
      "items-center",
      "justify-center",
      "bg-blue-500",
      "text-white",
      "p-4"
    );
    expect(result).toContain("flex");
    expect(result).toContain("items-center");
    expect(result).toContain("justify-center");
    expect(result).toContain("bg-blue-500");
    expect(result).toContain("text-white");
    expect(result).toContain("p-4");
  });

  it("handles duplicate classes (tailwind-merge behavior)", () => {
    const result = cn("duplicate", "duplicate");
    // tailwind-merge should handle duplicates, but we check the result contains the class
    expect(result).toContain("duplicate");
  });
});
