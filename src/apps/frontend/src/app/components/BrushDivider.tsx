import type { ReactNode } from "react";
import { cn } from "./ui/utils";

/** Subtle horizontal rule — no decorative SVG. */
export function BrushDivider({ className }: { className?: string }): ReactNode {
  return (
    <div
      className={cn("flex justify-center py-3", className)}
      role="separator"
      aria-hidden
    >
      <div className="h-px w-full max-w-xl bg-gradient-to-r from-transparent via-foreground/10 to-transparent" />
    </div>
  );
}
