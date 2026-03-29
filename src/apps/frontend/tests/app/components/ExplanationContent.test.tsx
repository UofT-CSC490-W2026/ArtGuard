import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  ExplanationContent,
  parseExplanationBlocks,
} from "@/app/components/ExplanationContent";

describe("parseExplanationBlocks", () => {
  it("splits patch lines from surrounding prose", () => {
    const text = `Intro paragraph here.

Patch #1 (top-left, center_crop_orig): observation one.
Patch #2 (center, downsample_orig): observation two.

Closing thoughts.`;
    const blocks = parseExplanationBlocks(text);
    expect(blocks).toHaveLength(4);
    expect(blocks[0]).toEqual({ type: "prose", body: "Intro paragraph here." });
    expect(blocks[1]).toMatchObject({ type: "patch" });
    expect((blocks[1] as { body: string }).body).toContain("Patch #1");
    expect(blocks[2]).toMatchObject({ type: "patch" });
    expect(blocks[3]).toEqual({ type: "prose", body: "Closing thoughts." });
  });
});

describe("ExplanationContent", () => {
  it("renders prose and patch regions", () => {
    const text = `Summary line.

Patch #1 (middle-right, center_crop_orig): texture appears smooth.`;
    render(<ExplanationContent text={text} />);
    expect(screen.getByText(/Summary line/)).toBeInTheDocument();
    expect(
      screen.getByText(/Patch #1 \(middle-right, center_crop_orig\)/),
    ).toBeInTheDocument();
  });

  it("renders (source: …) citations with styled spans", () => {
    const text = "Claim text (source: met_data_part27.txt) continues.";
    render(<ExplanationContent text={text} />);
    expect(screen.getByText("(source: met_data_part27.txt)")).toBeInTheDocument();
  });

  it("renders markdown bold fragments as strong text", () => {
    const text = "This is **important** evidence.";
    render(<ExplanationContent text={text} />);
    expect(screen.getByText("important").tagName.toLowerCase()).toBe("strong");
  });

  it("returns null when there is no prose or patch content", () => {
    const { container } = render(<ExplanationContent text="   " />);
    expect(container.firstChild).toBeNull();
  });
});
