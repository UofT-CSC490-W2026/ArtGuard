import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PatchOverlay } from "@/app/components/PatchOverlay";

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
    expect(screen.getByText(/per-patch authenticity heatmap/i)).toBeInTheDocument();
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

  it("shows patch authenticity tooltip when pointer is over a patch", async () => {
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
    await waitFor(() => expect(screen.getByText(/Patch #1: 73\.0% authenticity/)).toBeInTheDocument());
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

  it("hides canvas and controls when no patches provided", () => {
    render(
      <PatchOverlay imageSrc={dataUrl} patchData={[]} imageWidth={1} imageHeight={1} />,
    );
    expect(screen.getByRole("img", { name: /analyzed artwork/i })).toBeInTheDocument();
    // No canvas or heatmap controls when patchData is empty
    expect(screen.queryByText(/per-patch authenticity heatmap/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
  });

  it("sets tooltip to null on mousemove when overlay is off", async () => {
    const user = userEvent.setup();
    render(
      <PatchOverlay
        imageSrc={dataUrl}
        patchData={[{ x: 0, y: 0, w: 100, h: 100, prob: 0.5 }]}
        imageWidth={100}
        imageHeight={100}
      />,
    );
    const img = screen.getByRole("img", { name: /analyzed artwork/i });
    fireEvent.load(img);
    // Turn off overlay via switch
    await user.click(screen.getByRole("switch"));
    const wrap = img.parentElement!;
    // Mousemove should now trigger the early return with setTooltip(null)
    fireEvent.mouseMove(wrap, { clientX: 50, clientY: 50 });
    // No tooltip should appear (tooltip format includes "Patch #N")
    expect(screen.queryByText(/Patch #\d+:\s*\d+\.\d+% authenticity/)).not.toBeInTheDocument();
  });

  it("draws overlay rects when canvas 2d context is available", async () => {
    const user = userEvent.setup();
    const fillRect = vi.fn();
    const strokeRect = vi.fn();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      setTransform: vi.fn(),
      clearRect: vi.fn(),
      fillStyle: "",
      fillRect,
      strokeStyle: "",
      lineWidth: 1,
      strokeRect,
      measureText: vi.fn().mockReturnValue({ width: 8 }),
      fillText: vi.fn(),
    } as unknown as CanvasRenderingContext2D);

    render(
      <PatchOverlay
        imageSrc={dataUrl}
        patchData={[{ x: 0, y: 0, w: 10, h: 10, prob: 0.25 }]}
        imageWidth={100}
        imageHeight={100}
      />,
    );
    const img = screen.getByRole("img", { name: /analyzed artwork/i });
    Object.defineProperty(img, "clientWidth", { value: 100, configurable: true });
    Object.defineProperty(img, "clientHeight", { value: 100, configurable: true });
    Object.defineProperty(img, "naturalWidth", { value: 100, configurable: true });
    Object.defineProperty(img, "naturalHeight", { value: 100, configurable: true });
    fireEvent.load(img);
    // First draw may run before layout width is visible; toggling overlay forces a redraw with dimensions set.
    await user.click(screen.getByRole("switch"));
    await user.click(screen.getByRole("switch"));
    expect(fillRect.mock.calls.length).toBeGreaterThan(0);
    expect(strokeRect.mock.calls.length).toBeGreaterThan(0);
  });

  it("uses stable patch numbering order for same row and position", async () => {
    render(
      <PatchOverlay
        imageSrc={dataUrl}
        patchData={[
          { x: 70, y: 70, w: 20, h: 20, prob: 0.3 },
          { x: 10, y: 10, w: 20, h: 20, prob: 0.8 },
          { x: 10, y: 10, w: 20, h: 20, prob: 0.6 },
        ]}
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
      left: 0, top: 0, width: 100, height: 100, bottom: 100, right: 100, x: 0, y: 0, toJSON: () => ({}),
    } as DOMRect);
    const wrap = img.parentElement!;
    vi.spyOn(wrap, "getBoundingClientRect").mockReturnValue({
      left: 0, top: 0, width: 100, height: 100, bottom: 100, right: 100, x: 0, y: 0, toJSON: () => ({}),
    } as DOMRect);
    fireEvent.load(img);
    fireEvent.mouseMove(wrap, { clientX: 15, clientY: 15 });
    await waitFor(() => {
      expect(screen.getByText(/Patch #2:\s*60\.0% authenticity/)).toBeInTheDocument();
    });
  });

  it("clears tooltip when pointer maps outside image patch coordinates", async () => {
    render(
      <PatchOverlay
        imageSrc={dataUrl}
        patchData={[{ x: 0, y: 0, w: 10, h: 10, prob: 0.5 }]}
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
      left: 0, top: 0, width: 100, height: 100, bottom: 100, right: 100, x: 0, y: 0, toJSON: () => ({}),
    } as DOMRect);
    const wrap = img.parentElement!;
    vi.spyOn(wrap, "getBoundingClientRect").mockReturnValue({
      left: 0, top: 0, width: 100, height: 100, bottom: 100, right: 100, x: 0, y: 0, toJSON: () => ({}),
    } as DOMRect);
    fireEvent.load(img);
    // After grid aggregation the overlay covers the full image; use coords left of the image so nx < 0
    fireEvent.mouseMove(wrap, { clientX: -5, clientY: 50 });
    expect(screen.queryByText(/Patch #\d+:\s*\d+\.\d+% authenticity/)).not.toBeInTheDocument();
  });
});
