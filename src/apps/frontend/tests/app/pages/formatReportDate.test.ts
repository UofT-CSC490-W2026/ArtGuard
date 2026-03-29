import { describe, expect, it, vi } from "vitest";
import { formatReportDate } from "@/app/pages/ResultsPage";

describe("formatReportDate", () => {
  it("formats valid ISO timestamps", () => {
    const s = formatReportDate("2020-06-15T12:00:00.000Z");
    expect(s.length).toBeGreaterThan(4);
    expect(s).toContain("2020");
  });

  it("returns original string when date is invalid", () => {
    expect(formatReportDate("not-a-date")).toBe("not-a-date");
  });

  it("returns original string when toLocaleString throws", () => {
    const spy = vi.spyOn(Date.prototype, "toLocaleString").mockImplementation(() => {
      throw new Error("locale");
    });
    const iso = "2020-01-01T00:00:00.000Z";
    expect(formatReportDate(iso)).toBe(iso);
    spy.mockRestore();
  });
});
