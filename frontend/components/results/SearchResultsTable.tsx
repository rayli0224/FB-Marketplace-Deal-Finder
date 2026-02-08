"use client";

import { useState } from "react";
import { ToggleSwitch } from "@/components/ui/ToggleSwitch";

export interface Listing {
  title: string;
  price: number;
  location: string;
  url: string;
  dealScore: number | null;
}

export interface SearchResultsTableProps {
  listings: Listing[];
  scannedCount: number;
  threshold: number;
  onDownloadCSV: () => void;
  onReset: () => void;
}

/**
 * Determines if a listing is a good deal based on threshold comparison.
 * A good deal has a known deal score (not null) and meets or exceeds the threshold.
 */
function isGoodDeal(dealScore: number | null, threshold: number): boolean {
  return dealScore !== null && dealScore >= threshold;
}

/**
 * Determines if a listing is a bad deal based on threshold comparison.
 * A bad deal has a known deal score (not null) and is below the threshold.
 */
function isBadDeal(dealScore: number | null, threshold: number): boolean {
  return dealScore !== null && dealScore < threshold;
}

/**
 * Results table component displaying search results in a scrollable table.
 * Shows listing details including title, price, location, deal score, and link.
 * Includes header with result counts, filter toggle, and action buttons for CSV export and new search.
 * Color-codes listings based on threshold: green for good deals, red for bad deals.
 */
export function SearchResultsTable({ listings, scannedCount, threshold, onDownloadCSV, onReset }: SearchResultsTableProps) {
  const [showBadDeals, setShowBadDeals] = useState<boolean>(true);
  const [isFiltersExpanded, setIsFiltersExpanded] = useState<boolean>(false);

  const filteredListings = listings.filter((listing) => {
    if (showBadDeals) return true;
    return !isBadDeal(listing.dealScore, threshold);
  });

  const filteredCount = filteredListings.length;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-mono text-lg font-bold text-foreground">
            HEIST COMPLETE!
          </h2>
          <p className="font-mono text-xs text-muted-foreground">
            Showing {filteredCount} of {listings.length} treasures from {scannedCount} scanned
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

      {/* Filters Section */}
      <div className="border-2 border-border bg-secondary">
        <button
          type="button"
          onClick={() => setIsFiltersExpanded(!isFiltersExpanded)}
          className="w-full flex items-center justify-between px-4 py-2 border-b border-border hover:bg-secondary/80 transition-colors"
        >
          <h3 className="font-mono text-xs font-bold text-muted-foreground">
            <span className="text-primary">{"$"}</span> FILTERS
          </h3>
          <span className="font-mono text-xs text-primary transition-transform" style={{ transform: isFiltersExpanded ? 'rotate(180deg)' : 'rotate(0deg)' }}>
            ▼
          </span>
        </button>
        {isFiltersExpanded && (
          <div className="p-4">
            <ToggleSwitch
              checked={showBadDeals}
              onChange={setShowBadDeals}
              label="Show bad deals"
            />
          </div>
        )}
      </div>

      {listings.length > 0 ? (
        <div className="max-h-[60vh] overflow-auto border border-border">
          <table className="w-full border-collapse font-mono text-sm">
            <thead className="sticky top-0 bg-secondary">
              <tr className="border-b border-border text-left">
                <th className="px-3 py-2 text-xs text-muted-foreground">TITLE</th>
                <th className="px-3 py-2 text-xs text-muted-foreground">PRICE</th>
                <th className="px-3 py-2 text-xs text-muted-foreground">LOCATION</th>
                <th className="px-3 py-2 text-xs text-muted-foreground">DEAL %</th>
                <th className="px-3 py-2 text-xs text-muted-foreground">LINK</th>
              </tr>
            </thead>
            <tbody>
              {filteredListings.map((listing, index) => {
                const goodDeal = isGoodDeal(listing.dealScore, threshold);
                const badDeal = isBadDeal(listing.dealScore, threshold);
                const rowBgClass = goodDeal 
                  ? "bg-green-500/10 hover:bg-green-500/20" 
                  : badDeal 
                  ? "bg-red-500/10 hover:bg-red-500/20"
                  : "hover:bg-secondary/50";
                
                return (
                <tr 
                  key={index} 
                  className={`border-b border-border/50 transition-colors ${rowBgClass}`}
                >
                  <td className="px-3 py-2 max-w-[300px] truncate" title={listing.title}>
                    {listing.title}
                  </td>
                  <td className="px-3 py-2 text-primary font-bold">
                    ${listing.price.toFixed(2)}
                  </td>
                  <td className="px-3 py-2 text-muted-foreground max-w-[150px] truncate" title={listing.location}>
                    {listing.location}
                  </td>
                  <td className="px-3 py-2">
                    {listing.dealScore !== null ? (
                      <span className={`font-bold ${goodDeal ? 'text-green-500' : badDeal ? 'text-red-500' : 'text-muted-foreground'}`}>
                        {listing.dealScore}%
                      </span>
                    ) : (
                      <span className="text-muted-foreground/50">--</span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <a 
                      href={listing.url} 
                      target="_blank" 
                      rel="noopener noreferrer"
                      className="text-primary hover:underline"
                    >
                      VIEW →
                    </a>
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="border border-border bg-secondary p-8 text-center">
          <p className="font-mono text-muted-foreground">No listings found matching your criteria.</p>
        </div>
      )}
    </div>
  );
}

