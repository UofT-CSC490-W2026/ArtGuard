import type { PatchData } from "../types";

/** Matches ``preprocess.choose_grid_size`` (min side in pixels). */
const GRID_4X4_THRESHOLD = 1024;
const GRID_2X2_THRESHOLD = 512;

export function chooseGridSize(imageWidth: number, imageHeight: number): number {
  const smaller = Math.min(imageWidth, imageHeight);
  if (smaller > GRID_4X4_THRESHOLD) return 4;
  if (smaller > GRID_2X2_THRESHOLD) return 2;
  return 2;
}

/** Cell bounding boxes in source-image pixels (row-major). Matches ``compute_grid_boxes`` rounding. */
export function computeGridCells(
  imageWidth: number,
  imageHeight: number,
  gridSize: number,
): Array<{ x: number; y: number; w: number; h: number }> {
  const xEdges: number[] = [];
  const yEdges: number[] = [];
  for (let i = 0; i <= gridSize; i++) {
    xEdges.push(Math.round((i * imageWidth) / gridSize));
    yEdges.push(Math.round((i * imageHeight) / gridSize));
  }
  const cells: Array<{ x: number; y: number; w: number; h: number }> = [];
  for (let row = 0; row < gridSize; row++) {
    for (let col = 0; col < gridSize; col++) {
      const x = xEdges[col]!;
      const y = yEdges[row]!;
      const w = xEdges[col + 1]! - x;
      const h = yEdges[row + 1]! - y;
      cells.push({ x, y, w, h });
    }
  }
  return cells;
}

function cellIndexForPoint(
  cells: Array<{ x: number; y: number; w: number; h: number }>,
  px: number,
  py: number,
): number {
  for (let i = 0; i < cells.length; i++) {
    const c = cells[i]!;
    if (px >= c.x && px < c.x + c.w && py >= c.y && py < c.y + c.h) {
      return i;
    }
  }
  return -1;
}

/**
 * Maps each inference patch (center-crop and/or downsample variants) to the
 * preprocessing grid cell that contains the patch bbox center, then returns
 * one heatmap rect per cell (full cell bounds) with prob = mean of variants
 * assigned to that cell.
 */
export function aggregatePatchDataToInferenceGrid(
  patches: PatchData[],
  imageWidth: number,
  imageHeight: number,
): PatchData[] {
  if (!patches.length || imageWidth < 1 || imageHeight < 1) {
    return patches;
  }

  const gridSize = chooseGridSize(imageWidth, imageHeight);
  const cells = computeGridCells(imageWidth, imageHeight, gridSize);
  const buckets: number[][] = cells.map(() => []);

  const overallMean =
    patches.reduce((s, p) => s + p.prob, 0) / Math.max(1, patches.length);

  for (const p of patches) {
    const cx = p.x + p.w / 2;
    const cy = p.y + p.h / 2;
    const idx = cellIndexForPoint(cells, cx, cy);
    if (idx >= 0) {
      buckets[idx]!.push(p.prob);
    }
  }

  return cells.map((c, i) => {
    const probs = buckets[i]!;
    const prob =
      probs.length > 0
        ? probs.reduce((a, b) => a + b, 0) / probs.length
        : overallMean;
    return { x: c.x, y: c.y, w: c.w, h: c.h, prob };
  });
}
