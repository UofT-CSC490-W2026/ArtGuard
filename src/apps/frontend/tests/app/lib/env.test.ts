import { describe, expect, it } from "vitest";
import { isDev } from "@/app/lib/env";

describe("env", () => {
  it("isDev matches import.meta.env.DEV", () => {
    expect(isDev()).toBe(import.meta.env.DEV);
  });
});
