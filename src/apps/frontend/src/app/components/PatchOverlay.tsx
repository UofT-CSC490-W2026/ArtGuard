import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { PatchData } from "../types";
import { Label } from "./ui/label";
import { Switch } from "./ui/switch";

/** Peak overlay strength (matches previous slider at 100%). */
const OVERLAY_FILL_ALPHA = 0.65;

interface PatchOverlayProps {
  imageSrc: string;
  patchData?: PatchData[];
  imageWidth?: number;
  imageHeight?: number;
  alt?: string;
}

/** Heatmap: per-patch authenticity probability — red = low, green = high. */
function probToRgba(prob: number, alpha: number): string {
  const r = Math.round(255 * (1 - prob));
  const g = Math.round(255 * prob);
  return `rgba(${r},${g},0,${alpha})`;
}

type NumberedPatch = PatchData & { displayNumber: number };

// Stable display ordering: left-to-right within each row, then next row.
function numberPatchesLeftToRight(patches: PatchData[]): NumberedPatch[] {
  const indexed = patches.map((p, idx) => ({ ...p, _idx: idx }));
  indexed.sort((a, b) => {
    if (a.y !== b.y) return a.y - b.y;
    if (a.x !== b.x) return a.x - b.x;
    return a._idx - b._idx;
  });
  return indexed.map((p, i) => ({
    x: p.x,
    y: p.y,
    w: p.w,
    h: p.h,
    prob: p.prob,
    displayNumber: i + 1,
  }));
}

export function PatchOverlay({
  imageSrc,
  patchData,
  imageWidth: propW,
  imageHeight: propH,
  alt = "Analyzed artwork",
}: PatchOverlayProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [showOverlay, setShowOverlay] = useState(true);
  const [tooltip, setTooltip] = useState<{
    x: number;
    y: number;
    prob: number;
    patchNumber: number;
  } | null>(null);
  const displayPatches = patchData;

  const numberedPatches = useMemo<NumberedPatch[] | undefined>(() => {
    if (!displayPatches?.length) return undefined;
    return numberPatchesLeftToRight(displayPatches);
  }, [displayPatches]);

  const hasPatches = Boolean(numberedPatches?.length);

  const draw = useCallback(() => {
    const wrap = wrapRef.current;
    const img = imgRef.current;
    const canvas = canvasRef.current;
    if (!wrap || !img || !canvas || !hasPatches || !numberedPatches) return;

    const cw = img.clientWidth;
    const ch = img.clientHeight;
    if (cw < 1 || ch < 1) return;

    const nw = propW && propW > 0 ? propW : img.naturalWidth;
    const nh = propH && propH > 0 ? propH : img.naturalHeight;
    if (nw < 1 || nh < 1) return;

    const dpr = typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;
    canvas.width = Math.floor(cw * dpr);
    canvas.height = Math.floor(ch * dpr);
    canvas.style.width = `${cw}px`;
    canvas.style.height = `${ch}px`;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cw, ch);

    if (!showOverlay) return;

    const sx = cw / nw;
    const sy = ch / nh;
    const a = OVERLAY_FILL_ALPHA;

    for (const p of numberedPatches) {
      const x = p.x * sx;
      const y = p.y * sy;
      const w = p.w * sx;
      const h = p.h * sy;
      ctx.fillStyle = probToRgba(p.prob, a);
      ctx.fillRect(x, y, w, h);
      ctx.strokeStyle = "rgba(0,0,0,0.12)";
      ctx.lineWidth = 1;
      ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);

      const label = String(p.displayNumber);
      ctx.font = "600 12px ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto";
      const textW =
        typeof ctx.measureText === "function" ? ctx.measureText(label).width : label.length * 8;
      const labelW = Math.ceil(textW + 12);
      const labelH = 18;
      const lx = Math.max(0, Math.min(cw - labelW, x + 2));
      const ly = Math.max(0, Math.min(ch - labelH, y + 2));
      ctx.fillStyle = "rgba(0,0,0,0.62)";
      ctx.fillRect(lx, ly, labelW, labelH);
      ctx.fillStyle = "rgba(255,255,255,0.96)";
      ctx.textBaseline = "middle";
      if (typeof ctx.fillText === "function") {
        ctx.fillText(label, lx + 6, ly + labelH / 2);
      }
    }
  }, [hasPatches, numberedPatches, propW, propH, showOverlay]);

  useEffect(() => {
    draw();
    const wrap = wrapRef.current;
    if (!wrap) return;
    const ro = new ResizeObserver(() => draw());
    ro.observe(wrap);
    return () => ro.disconnect();
  }, [draw, imageSrc]);

  const onMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!hasPatches || !numberedPatches || !showOverlay) {
      setTooltip(null);
      return;
    }
    const img = imgRef.current;
    const wrap = wrapRef.current;
    if (!img || !wrap) return;

    const rect = img.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const cw = img.clientWidth;
    const ch = img.clientHeight;
    const nw = propW && propW > 0 ? propW : img.naturalWidth;
    const nh = propH && propH > 0 ? propH : img.naturalHeight;
    if (cw < 1 || ch < 1 || nw < 1 || nh < 1) return;

    const nx = (mx / cw) * nw;
    const ny = (my / ch) * nh;

    for (let i = numberedPatches.length - 1; i >= 0; i--) {
      const p = numberedPatches[i];
      if (nx >= p.x && nx <= p.x + p.w && ny >= p.y && ny <= p.y + p.h) {
        setTooltip({
          x: e.clientX - wrap.getBoundingClientRect().left,
          y: e.clientY - wrap.getBoundingClientRect().top,
          prob: p.prob,
          patchNumber: p.displayNumber,
        });
        return;
      }
    }
    setTooltip(null);
  };

  const onMouseLeave = () => setTooltip(null);

  if (!imageSrc) {
    return (
      <div className="size-full flex items-center justify-center text-sm text-muted-foreground p-4 text-center">
        Image preview unavailable.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div
        ref={wrapRef}
        className="relative aspect-square w-full overflow-hidden rounded-lg bg-muted"
        onMouseMove={onMouseMove}
        onMouseLeave={onMouseLeave}
      >
        <img
          ref={imgRef}
          src={imageSrc}
          alt={alt}
          className="size-full object-cover"
        />
        {hasPatches ? (
          <canvas
            ref={canvasRef}
            className="pointer-events-none absolute inset-0 size-full touch-none"
            aria-hidden
          />
        ) : null}
        {tooltip && hasPatches && showOverlay ? (
          <div
            className="pointer-events-none absolute z-10 rounded-md border border-border bg-popover px-2 py-1 text-xs font-mono text-popover-foreground shadow-md"
            style={{
              left: Math.min(tooltip.x + 12, (wrapRef.current?.clientWidth ?? 0) - 120),
              top: Math.max(tooltip.y - 36, 8),
            }}
          >
            {`Patch #${tooltip.patchNumber}: ${(tooltip.prob * 100).toFixed(1)}% authenticity`}
          </div>
        ) : null}
      </div>
      {hasPatches ? (
        <div className="flex items-center gap-2">
          <Switch id="patch-overlay" checked={showOverlay} onCheckedChange={setShowOverlay} />
          <Label htmlFor="patch-overlay" className="text-sm font-normal cursor-pointer">
            Per-patch authenticity heatmap
          </Label>
        </div>
      ) : null}
    </div>
  );
}
