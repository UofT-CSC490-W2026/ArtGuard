import { describe, expect, it, vi } from "vitest";
import { artAsset } from "@/app/lib/artAssets";

describe("artAsset", () => {
  it("joins BASE_URL with art path for both trailing slash variants", () => {
    vi.stubEnv("BASE_URL", "/");
    expect(artAsset("a.jpg")).toBe("/art/a.jpg");
    vi.stubEnv("BASE_URL", "/app/");
    expect(artAsset("a.jpg")).toBe("/app/art/a.jpg");
  });

  it("handles BASE_URL without trailing slash", () => {
    vi.stubEnv("BASE_URL", "/app");
    expect(artAsset("b.jpg")).toBe("/app/art/b.jpg");
  });

  it("handles empty BASE_URL", () => {
    vi.stubEnv("BASE_URL", "");
    const result = artAsset("c.jpg");
    expect(result).toContain("art/c.jpg");
  });
});
