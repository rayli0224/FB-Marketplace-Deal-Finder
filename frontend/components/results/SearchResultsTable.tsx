"use client";

import { Fragment, useState } from "react";
import { FullSizeToggle } from "@/components/ui/FullSizeToggle";

export interface CompItem {
  title: string;
  price: number;
  url: string;
  filtered?: boolean;  // True if this item was filtered out as non-comparable
  filterReason?: string;  // Short reason explaining why item was accepted or rejected
}

export interface Listing {
  title: string;
  price: number;
  location: string;
  url: string;
  dealScore: number | null;
  ebaySearchQuery?: string;
  compPrice?: number;
  compPrices?: number[];
  compItems?: CompItem[];
}

export interface SearchResultsTableProps {
  listings: Listing[];
  scannedCount: number;
  threshold: number;
  onDownloadCSV: () => void;
  onReset: () => void;
}

/**
 * Returns true when the listing is a good deal: dealScore is not null and at or above the threshold.
 */
function isGoodDeal(dealScore: number | null, threshold: number): boolean {
  return dealScore !== null && dealScore >= threshold;
}

/**
 * Returns true when the listing is a bad deal: dealScore is not null and below the threshold.
 */
function isBadDeal(dealScore: number | null, threshold: number): boolean {
  return dealScore !== null && dealScore < threshold;
}

/**
 * Renders the comparison transparency block for one result: eBay search query, comp (average) price,
 * and the list of comps. When compItems (title, price, url) exist, shows each as a link; otherwise
 * shows compPrices as plain price list.
 */
function ListingCompsPanel({ listing }: { listing: Listing }) {
  const { ebaySearchQuery, compPrice, compPrices, compItems } = listing;
  const prices = compItems?.map((c) => c.price) ?? compPrices ?? [];
  const count = prices.length;

  return (
    <div className="font-mono text-xs space-y-2">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-muted-foreground">
        {ebaySearchQuery != null && (
          <div>
            <span className="font-bold text-foreground">eBay search query: </span>
            <span className="break-all">&quot;{ebaySearchQuery}&quot;</span>
          </div>
        )}
        {compPrice != null && (
          <div>
            <span className="font-bold text-foreground">Comp price (eBay avg): </span>
            <span className="text-primary font-bold">${compPrice.toFixed(2)}</span>
          </div>
        )}
      </div>
      {count > 0 && (
        <div>
          <span className="font-bold text-foreground">Compared against {count} listing{count !== 1 ? "s" : ""}:</span>
          <ul className="mt-1 max-h-40 overflow-auto space-y-0.5 pl-2 border-l-2 border-border">
            {compItems && compItems.length > 0
              ? compItems.map((item, i) => {
                  const isFiltered = item.filtered === true;
                  return (
                    <li key={i} className={`flex items-baseline gap-2 flex-wrap ${isFiltered ? 'opacity-60' : ''}`}>
                      <a
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={`truncate max-w-[280px] hover:underline ${isFiltered ? 'text-red-500 line-through' : 'text-primary'}`}
                        title={isFiltered ? 'Filtered out as non-comparable' : undefined}
                      >
                        {item.title || "eBay listing"}
                      </a>
                      <span className={`font-bold shrink-0 ${isFiltered ? 'text-red-500' : 'text-primary'}`}>
                        ${item.price.toFixed(2)}
                      </span>
                      {isFiltered && (
                        <span className="text-xs text-red-500/70 shrink-0">(filtered)</span>
                      )}
                      {item.filterReason && (
                        <span className={`text-xs break-words pl-4 -ml-4 min-w-0 ${isFiltered ? 'text-red-500/70' : 'text-muted-foreground'}`}>
                          — {item.filterReason}
                        </span>
                      )}
                    </li>
                  );
                })
              : compPrices?.map((p, i) => (
                  <li key={i}>
                    <span className="text-muted-foreground">${p.toFixed(2)}</span>
                  </li>
                ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/**
 * Scrollable results table with one row per listing (title, price, location, deal %, link).
 * Header shows result counts and actions (CSV export, new search). Filter section toggles
 * visibility of below-threshold deals. Rows are color-coded by deal quality; each row can
 * expand to show eBay comparison details (search query, comp price, comp listings).
 */
export function SearchResultsTable({ listings, scannedCount, threshold, onDownloadCSV, onReset }: SearchResultsTableProps) {
  const [showBadDeals, setShowBadDeals] = useState<boolean>(true);
  const [isFiltersExpanded, setIsFiltersExpanded] = useState<boolean>(false);
  const [expandedListingUrl, setExpandedListingUrl] = useState<string | null>(null);

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
            <FullSizeToggle
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
                <th className="px-3 py-2 text-xs text-muted-foreground w-20">DETAILS</th>
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
                const hasComps = listing.ebaySearchQuery != null || listing.compPrice != null;
                const isExpanded = expandedListingUrl === listing.url;

                return (
                <Fragment key={listing.url}>
                <tr 
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
                      onClick={(e: React.MouseEvent) => e.stopPropagation()}
                    >
                      VIEW →
                    </a>
                  </td>
                  <td className="px-3 py-2">
                    {hasComps ? (
                      <button
                        type="button"
                        onClick={() => setExpandedListingUrl(isExpanded ? null : listing.url)}
                        className="font-mono text-xs text-primary hover:underline"
                        aria-expanded={isExpanded}
                      >
                        {isExpanded ? "▲ Hide" : "▼ Comps"}
                      </button>
                    ) : (
                      <span className="text-muted-foreground/50 text-xs">--</span>
                    )}
                  </td>
                </tr>
                {isExpanded && hasComps && (
                  <tr className="border-b border-border/50 bg-secondary/80">
                    <td colSpan={7} className="px-4 py-3">
                      <ListingCompsPanel listing={listing} />
                    </td>
                  </tr>
                )}
                </Fragment>
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

