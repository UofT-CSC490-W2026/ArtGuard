import type { ReactNode } from "react";
import { cn } from "./ui/utils";

/** Lines the RAG emits that describe individual patch evidence. */
const PATCH_LINE = /^\s*Patch #\d+/;

export type ExplanationBlock =
  | { type: "prose"; body: string }
  | { type: "patch"; body: string };

export function parseExplanationBlocks(text: string): ExplanationBlock[] {
  const lines = text.split("\n");
  const blocks: ExplanationBlock[] = [];
  let proseLines: string[] = [];

  const flushProse = () => {
    const body = proseLines.join("\n").trim();
    if (body) blocks.push({ type: "prose", body });
    proseLines = [];
  };

  for (const line of lines) {
    const trimmed = line.trim();
    if (PATCH_LINE.test(trimmed)) {
      flushProse();
      blocks.push({ type: "patch", body: trimmed });
    } else {
      proseLines.push(line);
    }
  }
  flushProse();
  return blocks;
}

/** Inline citations like `(source: met_data_part27.txt)` from the RAG contract. */
function InlineWithSources({ text }: { text: string }): ReactNode {
  const segments = text.split(/(\(source:[^)]+\))/g);
  return (
    <>
      {segments.map((seg, i) =>
        /^\(source:[^)]+\)$/.test(seg) ? (
          <span
            key={i}
            className="mx-0.5 inline-block rounded-sm bg-muted/70 px-1.5 py-0.5 align-baseline font-mono text-[0.7rem] leading-snug text-muted-foreground print:border print:border-neutral-400 print:bg-neutral-100 print:text-neutral-800"
          >
            {seg}
          </span>
        ) : (
          <span key={i}>{seg}</span>
        ),
      )}
    </>
  );
}

function ProseParagraphs({ body }: { body: string }) {
  const paras = body
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean);

  return (
    <>
      {paras.map((para, i) => (
        <p
          key={i}
          className={cn(
            "text-sm leading-relaxed text-muted-foreground print:text-neutral-800",
            i < paras.length - 1 && "mb-4",
          )}
        >
          <span className="whitespace-pre-line">
            <InlineWithSources text={para} />
          </span>
        </p>
      ))}
    </>
  );
}

export function ExplanationContent({
  text,
  className,
}: {
  text: string;
  className?: string;
}) {
  const blocks = parseExplanationBlocks(text);

  if (blocks.length === 0) {
    return null;
  }

  return (
    <div className={cn("space-y-4", className)}>
      {blocks.map((block, i) =>
        block.type === "prose" ? (
          <ProseParagraphs key={`prose-${i}`} body={block.body} />
        ) : (
          <div
            key={`patch-${i}`}
            className="border-l-2 border-foreground/15 pl-4 text-sm leading-relaxed text-muted-foreground print:break-inside-avoid print:border-l-2 print:border-neutral-400 print:text-neutral-800"
          >
            <InlineWithSources text={block.body} />
          </div>
        ),
      )}
    </div>
  );
}
