import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BrushDivider } from "./BrushDivider";

describe("BrushDivider", () => {
  it("renders separator", () => {
    const { container } = render(<BrushDivider />);
    expect(container.querySelector('[role="separator"]')).toBeTruthy();
  });
});
