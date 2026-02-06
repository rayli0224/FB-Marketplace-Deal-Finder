"use client";

import { ProgressBar } from "@/components/loading/ProgressBar";

export type SearchPhase = "scraping" | "ebay" | "calculating";

export interface SearchLoadingStateProps {
  phase: SearchPhase;
  scannedCount: number;
  evaluatedCount: number;
}

/**
 * Loading state component displaying progress during marketplace search.
 * Shows current phase with animated dots, phase description, and progress bars
 * for scanned and evaluated listings.
 */
export function SearchLoadingState({ phase, scannedCount, evaluatedCount }: SearchLoadingStateProps) {
  return (
    <div className="space-y-6">
      <div className="border border-border bg-secondary p-4">
        <div className="flex items-center gap-3">
          <div className="flex gap-1">
            <span className="inline-block h-2 w-2 animate-bounce bg-primary" style={{ animationDelay: "0ms" }} />
            <span className="inline-block h-2 w-2 animate-bounce bg-primary" style={{ animationDelay: "150ms" }} />
            <span className="inline-block h-2 w-2 animate-bounce bg-primary" style={{ animationDelay: "300ms" }} />
          </div>
          <span className="font-mono text-sm text-muted-foreground">
            {phase === "scraping" && "🔍 Searching Facebook Marketplace..."}
            {phase === "ebay" && "📊 Fetching eBay prices..."}
            {phase === "calculating" && "🧮 Calculating deals..."}
          </span>
        </div>
        <div className="mt-3 font-mono text-xs text-muted-foreground/60">
          {phase === "scraping" && "Infiltrating the marketplace for treasures..."}
          {phase === "ebay" && "Checking market values on eBay..."}
          {phase === "calculating" && "Crunching numbers to find the best deals..."}
        </div>
      </div>

      <div className="space-y-4">
        <ProgressBar 
          label="Infiltrating listings" 
          count={scannedCount}
          maxCount={scannedCount || 100}
          suffix="scanned" 
          icon="~"
        />
        <ProgressBar 
          label="Evaluating loot value" 
          count={evaluatedCount}
          maxCount={scannedCount || 100}
          suffix="assessed" 
          icon="*"
        />
      </div>
    </div>
  );
}

