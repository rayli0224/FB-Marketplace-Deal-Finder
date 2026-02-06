"use client";

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
        <span className="font-mono text-xs text-muted-foreground">
          <span className="text-accent">{icon}</span> {label}
        </span>
        <span className="font-mono text-sm font-bold tabular-nums text-foreground">
          {count.toLocaleString()}
          <span className="ml-1 text-xs font-normal text-muted-foreground">{suffix}</span>
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden bg-secondary">
        <div 
          className="h-full bg-primary transition-all duration-100"
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}

