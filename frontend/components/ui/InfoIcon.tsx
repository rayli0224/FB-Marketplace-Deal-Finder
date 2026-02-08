"use client";

export interface InfoIconProps {
  tooltip: string;
  className?: string;
}

/**
 * Parses tooltip text into main text and optional example section.
 * Splits on "Example:" delimiter if present, otherwise returns the full text as main.
 */
function parseTooltip(tooltip: string): { main: string; example?: string } {
  if (tooltip.includes("Example:")) {
    const [main, example] = tooltip.split("Example:");
    return { main: main.trim(), example: example.trim() };
  }
  return { main: tooltip };
}

/**
 * Reusable info icon with hover popup.
 * Shared across form fields.
 */
export function InfoIcon({ tooltip, className = "" }: InfoIconProps) {
  const { main, example } = parseTooltip(tooltip);

  return (
    <div className={`group relative ml-0.5 inline-flex cursor-help ${className}`}>
      <span className="flex h-2 w-2 items-center justify-center rounded-full border border-accent/40 bg-accent/10 text-[6px] font-bold leading-none text-accent transition-all hover:border-accent hover:bg-accent/20">
        i
      </span>
      <div className="invisible absolute bottom-full left-1/2 mb-2 w-64 -translate-x-1/2 rounded-lg border-2 border-accent/30 bg-gradient-to-br from-card to-secondary/80 px-3 py-2 font-mono text-[11px] text-foreground shadow-[0_4px_12px_rgba(0,0,0,0.15)] backdrop-blur-sm group-hover:visible z-20">
        <div className="absolute -bottom-1 left-1/2 h-2 w-2 -translate-x-1/2 rotate-45 border-r-2 border-b-2 border-accent/30 bg-gradient-to-br from-card to-secondary/80" />
        <div className="relative">
          <span className="block whitespace-pre-line text-foreground">
            {main}{main.endsWith(".") ? "" : "."}
            {example && (
              <> <span className="text-accent font-semibold">Example:</span>{" "}{example}{example.endsWith(".") ? "" : "."}</>
            )}
          </span>
        </div>
      </div>
    </div>
  );
}
