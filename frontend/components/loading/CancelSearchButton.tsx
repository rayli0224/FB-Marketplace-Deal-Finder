"use client";

/** Cancel button styling (outline, primary). */
const CANCEL_BUTTON_CLASS =
  "border-2 border-primary bg-transparent px-3 py-2 font-mono text-xs font-bold text-primary transition-all hover:bg-primary hover:text-primary-foreground";

export interface CancelSearchButtonProps {
  onCancel: () => void;
}

/**
 * Cancel button for aborting an in-progress search.
 */
export function CancelSearchButton({ onCancel }: CancelSearchButtonProps) {
  return (
    <button type="button" onClick={onCancel} className={CANCEL_BUTTON_CLASS}>
      CANCEL
    </button>
  );
}
