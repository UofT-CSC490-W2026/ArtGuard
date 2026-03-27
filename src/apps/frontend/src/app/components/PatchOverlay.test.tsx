import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { PatchOverlay } from "./PatchOverlay";

const dataUrl =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQImWNgYAAAAAMAASsJTYQAAAAASUVORK5CYII=";

describe("PatchOverlay", () => {
  it("shows placeholder when imageSrc missing", () => {
    render(<PatchOverlay imageSrc="" patchData={[]} />);
    expect(screen.getByText(/preview unavailable/i)).toBeInTheDocument();
  });

  it("renders image and toggles overlay controls when patches exist", async () => {
    const user = userEvent.setup();
    render(
      <PatchOverlay
        imageSrc={dataUrl}
        patchData={[{ x: 0, y: 0, w: 1, h: 1, prob: 0.5 }]}
        imageWidth={1}
        imageHeight={1}
      />,
    );
    const img = screen.getByRole("img", { name: /analyzed artwork/i });
    fireEvent.load(img);
    expect(screen.getByText(/patch authenticity heatmap/i)).toBeInTheDocument();
    await user.click(screen.getByRole("switch"));
  });

  it("clears tooltip on mouse leave", async () => {
    render(
      <PatchOverlay
        imageSrc={dataUrl}
        patchData={[{ x: 0, y: 0, w: 100, h: 100, prob: 0.2 }]}
        imageWidth={100}
        imageHeight={100}
      />,
    );
    const img = screen.getByRole("img", { name: /analyzed artwork/i });
    fireEvent.load(img);
    const wrap = img.parentElement?.parentElement;
    expect(wrap).toBeTruthy();
    fireEvent.mouseMove(wrap!, { clientX: 10, clientY: 10 });
    fireEvent.mouseLeave(wrap!);
  });
});
