"use client";

/** Base Tailwind classes for the loading bordered box (border, background, padding). */
const LOADING_BOX_BASE_CLASSES = "border border-border bg-secondary p-3";

export interface LoadingBoxProps {
  children: React.ReactNode;
  className?: string;
}

/**
 * Reusable bordered container for loading-state content (heist clock, progress bars, etc.).
 */
export function LoadingBox({ children, className = "" }: LoadingBoxProps) {
  return (
    <div className={`${LOADING_BOX_BASE_CLASSES} ${className}`.trim()}>
      {children}
    </div>
  );
}
