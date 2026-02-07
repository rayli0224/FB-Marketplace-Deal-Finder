"use client";

import { ProgressBar } from "@/components/loading/ProgressBar";

export type SearchPhase = "scraping" | "ebay" | "calculating";

export interface SearchLoadingStateProps {
  phase: SearchPhase;
  scannedCount: number;
  evaluatedCount: number;
}

/**
 * Returns the main message and description for a given search phase.
 * Provides pirate-themed messaging that matches the current phase of the search process.
 */
function getPhaseMessages(phase: SearchPhase): { main: string; description: string } {
  const messages = {
    scraping: {
      main: "🔍 Searching Facebook Marketplace...",
      description: "Infiltrating the marketplace for treasures...",
    },
    ebay: {
      main: "📊 Fetching eBay prices...",
      description: "Checking market values on eBay...",
    },
    calculating: {
      main: "🧮 Calculating deals...",
      description: "Crunching numbers to find the best deals...",
    },
  };
  return messages[phase];
}

/**
 * Loading state component displaying progress during marketplace search.
 * Shows current phase with animated dots, phase description, and progress bars
 * for scanned and evaluated listings.
 */
export function SearchLoadingState({ phase, scannedCount, evaluatedCount }: SearchLoadingStateProps) {
  const phaseMessages = getPhaseMessages(phase);

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
            {phaseMessages.main}
          </span>
        </div>
        <div className="mt-3 font-mono text-xs text-muted-foreground/60">
          {phaseMessages.description}
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

