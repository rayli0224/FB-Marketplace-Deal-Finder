"use client";

import { useState, useEffect, useMemo } from "react";
import { HeistClockSection } from "@/components/loading/HeistClockSection";
import { CancelSearchButton } from "@/components/loading/CancelSearchButton";
import { ResultsTable, filteredOutToListing } from "@/components/results/ResultsTable";
import type { Listing, FilteredOutListingRow } from "@/components/results/ResultsTable";
import type { DebugFacebookListing, DebugEbayQueryEntry } from "@/components/debug/DebugPanel";
import type { DebugSearchParams } from "@/components/debug/DebugSearchParams";
import { SearchQueryDetails } from "@/components/results/SearchQueryDetails";

const ELAPSED_TIME_UPDATE_INTERVAL_MS = 100;

export interface SearchLoadingViewProps {
  listings: Listing[];
  threshold: number;
  filteredOutListings: FilteredOutListingRow[];
  currentItem: { listingIndex: number; fbTitle: string; totalListings: number } | null;
  facebookListings: DebugFacebookListing[];
  ebayQueries: DebugEbayQueryEntry[];
  searchParams: DebugSearchParams | null;
  onCancel: () => void;
}

/**
 * Loading-state view: shows live progress (current item), timer, and cancel.
 * Displays pending Facebook listings and filtered-out items alongside evaluated results.
 */
export function SearchLoadingView({
  listings,
  threshold,
  filteredOutListings,
  currentItem,
  facebookListings,
  ebayQueries,
  searchParams,
  onCancel,
}: SearchLoadingViewProps) {
  const [nowMs, setNowMs] = useState<number>(() => Date.now());

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      setNowMs(Date.now());
    }, ELAPSED_TIME_UPDATE_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
  }, []);

  const evaluatedListingUrls = useMemo(() => new Set(listings.map((l) => l.url)), [listings]);
  const filteredOutListingUrls = useMemo(
    () => new Set(filteredOutListings.map((l) => l.url)),
    [filteredOutListings]
  );

  const allFacebookListingsAsListings: Listing[] =
    facebookListings.length > 0
      ? facebookListings
          .filter(
            (fb) =>
              !evaluatedListingUrls.has(fb.url) && !filteredOutListingUrls.has(fb.url)
          )
          .map((fb) => ({
            title: fb.title,
            price: fb.price,
            currency: "$",
            location: fb.location,
            url: fb.url,
            dealScore: null,
          }))
      : [];

  const displayListings: Listing[] = [
    ...listings,
    ...allFacebookListingsAsListings,
    ...filteredOutListings.map(filteredOutToListing),
  ];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3 flex-wrap">
            <h2 className="font-mono text-lg font-bold text-foreground">
              LOOT INCOMING...
            </h2>
            <HeistClockSection />
          </div>
          {currentItem && (
            <div className="mt-2 border-2 border-primary/50 bg-primary/5 px-3 py-2 rounded">
              <div className="font-mono text-xs">
                <span className="text-primary font-bold">Processing:</span>
              </div>
              <div className="font-mono text-xs mt-1">
                <span className="text-primary/80">
                  [{currentItem.listingIndex}/{currentItem.totalListings}]
                </span>
                <span className="ml-2 text-foreground font-medium">
                  {currentItem.fbTitle}
                </span>
              </div>
            </div>
          )}
        </div>
        <CancelSearchButton onCancel={onCancel} />
      </div>

      <SearchQueryDetails searchParams={searchParams} />

      <ResultsTable
        displayListings={displayListings}
        threshold={threshold}
        filteredOutListings={filteredOutListings}
        emptyMessage="Raiding the marketplace..."
        showStatusColumn={true}
        ebayQueries={ebayQueries}
        facebookListings={facebookListings}
        nowMs={nowMs}
      />
    </div>
  );
}
