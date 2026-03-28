import { useCallback, useEffect, useRef, useState } from "react";
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

/** Heatmap overlay: red = low authenticity, green = high. */
function probToRgba(prob: number, alpha: number): string {
  const r = Math.round(255 * (1 - prob));
  const g = Math.round(255 * prob);
  return `rgba(${r},${g},0,${alpha})`;
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
  const [tooltip, setTooltip] = useState<{ x: number; y: number; prob: number } | null>(null);

  const hasPatches = Boolean(patchData?.length);

  const draw = useCallback(() => {
    const wrap = wrapRef.current;
    const img = imgRef.current;
    const canvas = canvasRef.current;
    if (!wrap || !img || !canvas || !hasPatches || !patchData) return;

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

    for (const p of patchData) {
      const x = p.x * sx;
      const y = p.y * sy;
      const w = p.w * sx;
      const h = p.h * sy;
      ctx.fillStyle = probToRgba(p.prob, a);
      ctx.fillRect(x, y, w, h);
      ctx.strokeStyle = "rgba(0,0,0,0.12)";
      ctx.lineWidth = 1;
      ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
    }
  }, [hasPatches, patchData, propW, propH, showOverlay]);

  useEffect(() => {
    draw();
    const wrap = wrapRef.current;
    if (!wrap) return;
    const ro = new ResizeObserver(() => draw());
    ro.observe(wrap);
    return () => ro.disconnect();
  }, [draw, imageSrc]);

  const onMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!hasPatches || !patchData || !showOverlay) {
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

    for (let i = patchData.length - 1; i >= 0; i--) {
      const p = patchData[i];
      if (nx >= p.x && nx <= p.x + p.w && ny >= p.y && ny <= p.y + p.h) {
        setTooltip({
          x: e.clientX - wrap.getBoundingClientRect().left,
          y: e.clientY - wrap.getBoundingClientRect().top,
          prob: p.prob,
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
          onLoad={draw}
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
            {(tooltip.prob * 100).toFixed(1)}% authenticity
          </div>
        ) : null}
      </div>
      {hasPatches ? (
        <div className="flex items-center gap-2">
          <Switch id="patch-overlay" checked={showOverlay} onCheckedChange={setShowOverlay} />
          <Label htmlFor="patch-overlay" className="text-sm font-normal cursor-pointer">
            Patch authenticity heatmap
          </Label>
        </div>
      ) : null}
    </div>
  );
}
