import { describe, expect, it, vi } from "vitest";
import { artAsset } from "./artAssets";

describe("artAsset", () => {
  it("joins BASE_URL with art path for both trailing slash variants", () => {
    vi.stubEnv("BASE_URL", "/");
    expect(artAsset("a.jpg")).toBe("/art/a.jpg");
    vi.stubEnv("BASE_URL", "/app/");
    expect(artAsset("a.jpg")).toBe("/app/art/a.jpg");
  });
});
