"use client";

import { useState } from "react";
import { FullSizeToggle } from "@/components/ui/FullSizeToggle";
import { ResultsTable, filteredOutToListing, isBadDeal } from "@/components/results/ResultsTable";
import type { Listing, FilteredOutListingRow } from "@/components/results/ResultsTable";

export interface SearchResultsViewProps {
  listings: Listing[];
  scannedCount: number;
  threshold: number;
  filteredOutListings: FilteredOutListingRow[];
  onDownloadCSV: () => void;
  onReset: () => void;
}

/**
 * Results view: shows completed search with filters (show bad deals, filtered-out listings),
 * CSV export, and new search button.
 */
export function SearchResultsView({
  listings,
  scannedCount,
  threshold,
  filteredOutListings,
  onDownloadCSV,
  onReset,
}: SearchResultsViewProps) {
  const [showBadDeals, setShowBadDeals] = useState<boolean>(true);
  const [showFilteredOut, setShowFilteredOut] = useState<boolean>(false);
  const [isFiltersExpanded, setIsFiltersExpanded] = useState<boolean>(false);

  const filteredListings = listings.filter((listing) => {
    if (showBadDeals) return true;
    return !isBadDeal(listing.dealScore, threshold);
  });

  const displayListings: Listing[] = showFilteredOut
    ? [...filteredListings, ...filteredOutListings.map(filteredOutToListing)]
    : filteredListings;

  const filteredCount = filteredListings.length;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-mono text-lg font-bold text-foreground">
            HEIST COMPLETE!
          </h2>
          <p className="font-mono text-xs text-muted-foreground">
            Showing {filteredCount} of {listings.length} treasures from {scannedCount}{" "}
            scanned
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onDownloadCSV}
            className="border-2 border-primary bg-transparent px-3 py-2 font-mono text-xs font-bold text-primary transition-all hover:bg-primary hover:text-primary-foreground"
          >
            EXPORT CSV
          </button>
          <button
            type="button"
            onClick={onReset}
            className="border-2 border-accent bg-accent px-3 py-2 font-mono text-xs font-bold text-accent-foreground transition-all hover:bg-transparent hover:text-accent"
          >
            NEW SEARCH
          </button>
        </div>
      </div>

      <div className="border-2 border-border bg-secondary">
        <button
          type="button"
          onClick={() => setIsFiltersExpanded(!isFiltersExpanded)}
          className="w-full flex items-center justify-between px-4 py-2 border-b border-border hover:bg-secondary/80 transition-colors"
        >
          <h3 className="font-mono text-xs font-bold text-muted-foreground">
            <span className="text-primary">{"$"}</span> FILTERS
          </h3>
          <span
            className="font-mono text-xs text-primary transition-transform"
            style={{ transform: `rotate(${isFiltersExpanded ? 180 : 0}deg)` }}
          >
            ▼
          </span>
        </button>
        {isFiltersExpanded && (
          <div className="p-4 space-y-3">
            <FullSizeToggle
              checked={showBadDeals}
              onChange={setShowBadDeals}
              label="Show bad deals"
            />
            {filteredOutListings.length > 0 && (
              <FullSizeToggle
                checked={showFilteredOut}
                onChange={setShowFilteredOut}
                label="Show filtered-out listings"
              />
            )}
          </div>
        )}
      </div>

      <ResultsTable
        displayListings={displayListings}
        threshold={threshold}
        filteredOutListings={showFilteredOut ? filteredOutListings : []}
        emptyMessage="No listings found matching your criteria."
      />
    </div>
  );
}
