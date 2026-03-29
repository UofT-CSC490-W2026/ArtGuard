import { describe, expect, it } from "vitest";
import {
  aggregatePatchDataToInferenceGrid,
  chooseGridSize,
  computeGridCells,
} from "@/app/lib/inferenceGrid";

describe("inferenceGrid", () => {
  it("chooseGridSize matches preprocess thresholds", () => {
    expect(chooseGridSize(2048, 1536)).toBe(4);
    expect(chooseGridSize(1024, 1024)).toBe(2);
    expect(chooseGridSize(1025, 1025)).toBe(4);
    expect(chooseGridSize(768, 768)).toBe(2);
  });

  it("computeGridCells uses rounded edges like preprocess", () => {
    const cells = computeGridCells(768, 768, 2);
    expect(cells).toHaveLength(4);
    expect(cells[0]).toEqual({ x: 0, y: 0, w: 384, h: 384 });
    expect(cells[3]).toEqual({ x: 384, y: 384, w: 384, h: 384 });
  });

  it("aggregates duplicate legacy 224 boxes per cell to full cell with mean prob", () => {
    const legacy = [
      { x: 0, y: 0, w: 224, h: 224, prob: 0.1 },
      { x: 0, y: 0, w: 224, h: 224, prob: 0.3 },
      { x: 384, y: 0, w: 224, h: 224, prob: 0.2 },
      { x: 384, y: 0, w: 224, h: 224, prob: 0.4 },
      { x: 0, y: 384, w: 224, h: 224, prob: 0.5 },
      { x: 0, y: 384, w: 224, h: 224, prob: 0.5 },
      { x: 384, y: 384, w: 224, h: 224, prob: 0.6 },
      { x: 384, y: 384, w: 224, h: 224, prob: 0.8 },
    ];
    const out = aggregatePatchDataToInferenceGrid(legacy, 768, 768);
    expect(out).toHaveLength(4);
    expect(out[0]?.prob).toBeCloseTo(0.2, 5);
    expect(out[1]?.prob).toBeCloseTo(0.3, 5);
    expect(out[2]?.prob).toBeCloseTo(0.5, 5);
    expect(out[3]?.prob).toBeCloseTo(0.7, 5);
  });

  it("maps center-cropped 224 regions to the correct cells", () => {
    const patches = [
      { x: 80, y: 80, w: 224, h: 224, prob: 0.9 },
      { x: 0, y: 0, w: 384, h: 384, prob: 0.1 },
    ];
    const out = aggregatePatchDataToInferenceGrid(patches, 768, 768);
    const topLeft = out.find((p) => p.x === 0 && p.y === 0);
    expect(topLeft?.w).toBe(384);
    expect(topLeft?.h).toBe(384);
    expect(topLeft?.prob).toBeCloseTo(0.5, 5);
  });

  it("returns patches unchanged when list is empty or dimensions invalid", () => {
    expect(aggregatePatchDataToInferenceGrid([], 100, 100)).toEqual([]);
    const one = [{ x: 0, y: 0, w: 1, h: 1, prob: 0.5 }];
    expect(aggregatePatchDataToInferenceGrid(one, 0, 100)).toBe(one);
    expect(aggregatePatchDataToInferenceGrid(one, 100, 0)).toBe(one);
  });

  it("uses overall mean when patch center falls outside grid cells", () => {
    const patches = [{ x: 500, y: 500, w: 10, h: 10, prob: 0.25 }];
    const out = aggregatePatchDataToInferenceGrid(patches, 100, 100);
    expect(out.length).toBeGreaterThan(0);
    for (const cell of out) {
      expect(cell.prob).toBe(0.25);
    }
  });
});
