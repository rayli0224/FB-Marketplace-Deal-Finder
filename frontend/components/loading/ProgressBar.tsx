"use client";

import { CONTENT_TEXT_XS_CLASS } from "@/lib/ui-constants";

/** Progress bar track (height, border, background). */
const PROGRESS_BAR_TRACK_CLASS =
  "h-3 w-full overflow-hidden border border-border bg-secondary";

/** Progress bar fill (color, transition). */
const PROGRESS_BAR_FILL_CLASS = "h-full bg-primary transition-all duration-100";

/** Progress bar count (bold, tabular numbers). */
const PROGRESS_BAR_COUNT_CLASS = "font-mono text-sm font-bold tabular-nums text-foreground";

/** Progress bar suffix (smaller, normal weight). */
const PROGRESS_BAR_SUFFIX_CLASS = "ml-1 text-xs font-normal text-foreground";

export interface ProgressBarProps {
  label: string;
  count: number;
  maxCount: number;
  suffix: string;
  icon: string;
}

/**
 * Progress bar component displaying loading progress with pirate-themed styling.
 * Calculates percentage from count and maxCount, then renders a visual progress bar.
 * Shows label with icon prefix, current count with suffix, and animated progress bar.
 */
export function ProgressBar({ 
  label, 
  count, 
  maxCount,
  suffix,
  icon 
}: ProgressBarProps) {
  const percentage = maxCount > 0 ? Math.min((count / maxCount) * 100, 100) : 0;
  
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between">
        <span className={CONTENT_TEXT_XS_CLASS}>
          <span className="text-accent">{icon}</span> {label}
        </span>
        <span className={PROGRESS_BAR_COUNT_CLASS}>
          {count.toLocaleString()}
          <span className={PROGRESS_BAR_SUFFIX_CLASS}>{suffix}</span>
        </span>
      </div>
      <div className={PROGRESS_BAR_TRACK_CLASS}>
        <div
          className={PROGRESS_BAR_FILL_CLASS}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}

