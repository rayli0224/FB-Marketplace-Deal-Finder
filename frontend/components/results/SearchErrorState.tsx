"use client";

export interface SearchErrorStateProps {
  error: string | null;
  onReset: () => void;
}

/**
 * Error state component displaying error message and reset button.
 * Shows pirate-themed error message when search fails.
 */
export function SearchErrorState({ error, onReset }: SearchErrorStateProps) {
  return (
    <div className="space-y-6">
      <div className="text-center">
        <div className="mb-4 text-5xl">⚠️</div>
        <h2 className="mb-2 font-mono text-xl font-bold text-destructive">
          HEIST FAILED!
        </h2>
        <p className="font-mono text-sm text-muted-foreground mb-4">
          {error || "An unknown error occurred"}
        </p>
        <button
          type="button"
          onClick={onReset}
          className="border-2 border-accent bg-accent px-4 py-3 font-mono text-sm font-bold text-accent-foreground transition-all hover:bg-transparent hover:text-accent"
        >
          TRY AGAIN
        </button>
      </div>
    </div>
  );
}

