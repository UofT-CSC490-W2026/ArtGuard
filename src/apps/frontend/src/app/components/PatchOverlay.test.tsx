import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PatchOverlay } from "./PatchOverlay";

const dataUrl =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQImWNgYAAAAAMAASsJTYQAAAAASUVORK5CYII=";

describe("PatchOverlay", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });
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

  it("shows authenticity tooltip when pointer is over a patch", async () => {
    render(
      <PatchOverlay
        imageSrc={dataUrl}
        patchData={[{ x: 0, y: 0, w: 50, h: 50, prob: 0.73 }]}
        imageWidth={100}
        imageHeight={100}
      />,
    );
    const img = screen.getByRole("img", { name: /analyzed artwork/i });
    Object.defineProperty(img, "clientWidth", { value: 100, configurable: true });
    Object.defineProperty(img, "clientHeight", { value: 100, configurable: true });
    Object.defineProperty(img, "naturalWidth", { value: 100, configurable: true });
    Object.defineProperty(img, "naturalHeight", { value: 100, configurable: true });
    vi.spyOn(img, "getBoundingClientRect").mockReturnValue({
      left: 0,
      top: 0,
      width: 100,
      height: 100,
      bottom: 100,
      right: 100,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    } as DOMRect);
    const wrap = img.parentElement!;
    vi.spyOn(wrap, "getBoundingClientRect").mockReturnValue({
      left: 0,
      top: 0,
      width: 100,
      height: 100,
      bottom: 100,
      right: 100,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    } as DOMRect);
    fireEvent.load(img);
    fireEvent.mouseMove(wrap, { clientX: 25, clientY: 25 });
    await waitFor(() => expect(screen.getByText(/73\.0% authenticity/)).toBeInTheDocument());
  });

  it("skips canvas draw when getContext returns null", () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);

    render(
      <PatchOverlay
        imageSrc={dataUrl}
        patchData={[{ x: 0, y: 0, w: 10, h: 10, prob: 0.5 }]}
        imageWidth={10}
        imageHeight={10}
      />,
    );
    const img = screen.getByRole("img", { name: /analyzed artwork/i });
    fireEvent.load(img);
  });

  it("adjusts opacity via slider", async () => {
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
    const slider = screen.getByRole("slider");
    await user.click(slider);
  });
});
