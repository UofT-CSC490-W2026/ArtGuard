import type { ReactNode } from "react";
import { cn } from "./ui/utils";

interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: ReactNode;
  /** Width alignment with main content (e.g. max-w-3xl mx-auto) */
  contentClassName?: string;
}

export function PageHeader({ title, description, actions, contentClassName }: PageHeaderProps) {
  return (
    <header className="border-b border-border bg-card">
      <div className="container mx-auto px-4 py-8">
        <div className={cn("flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between", contentClassName)}>
          <div>
            <h1 className="font-serif text-3xl font-semibold text-foreground tracking-tight mb-2">
              {title}
            </h1>
            {description ? (
              <p className="font-sans text-muted-foreground max-w-2xl">{description}</p>
            ) : null}
          </div>
          {actions ? <div className="flex shrink-0 flex-wrap gap-2 justify-start sm:justify-end">{actions}</div> : null}
        </div>
      </div>
    </header>
  );
}
