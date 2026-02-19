"use client";

import { Fragment, useState, useEffect, useMemo } from "react";
import { FullSizeToggle } from "@/components/ui/FullSizeToggle";
import { HeistClockSection } from "@/components/loading/HeistClockSection";
import { CancelSearchButton } from "@/components/loading/CancelSearchButton";
import type { DebugFacebookListing, DebugEbayQueryEntry } from "@/components/debug/DebugPanel";

export interface CompItem {
  title: string;
  price: number;
  url: string;
  filtered?: boolean;  // True if this item was filtered out as non-comparable (backwards compat)
  filterStatus?: "accept" | "maybe" | "reject";  // Decision status from filtering
  filterReason?: string;  // Short reason explaining why item was accepted, maybe, or rejected
}

export interface Listing {
  title: string;
  price: number;
  currency?: string;  // Currency symbol: $, £, €, etc. Defaults to "$" if not provided
  location: string;
  url: string;
  dealScore: number | null;
  ebaySearchQuery?: string;
  compPrice?: number;
  compPrices?: number[];
  compItems?: CompItem[];
  noCompReason?: string;
}

export interface FilteredOutListingRow {
  title: string;
  price: number;
  location: string;
  url: string;
  fbListingId?: string;
}

export interface SearchResultsTableProps {
  listings: Listing[];
  scannedCount: number;
  threshold: number;
  filteredOutListings?: FilteredOutListingRow[];
  onDownloadCSV: () => void;
  onReset: () => void;
  isLoading?: boolean;
  currentItem?: { listingIndex: number; fbTitle: string; totalListings: number } | null;
  facebookListings?: DebugFacebookListing[];
  ebayQueries?: DebugEbayQueryEntry[];
  onCancel?: () => void;
}

/** Interval in ms for updating elapsed time display during loading. */
const ELAPSED_TIME_UPDATE_INTERVAL_MS = 100;

/** Number of columns in the table (for colSpan). */
const TABLE_COLUMN_COUNT = 7;

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
 * Formats a price with the given currency symbol.
 */
function formatPrice(price: number, currency: string = "$"): string {
  return `${currency}${price.toFixed(2)}`;
}

/**
 * Formats elapsed milliseconds as M:SS.t (minutes:seconds.tenths).
 */
function formatElapsedMs(elapsedMs: number): string {
  const clampedMs = Math.max(0, elapsedMs);
  const totalTenths = Math.floor(clampedMs / 100);
  const minutes = Math.floor(totalTenths / 600);
  const seconds = Math.floor((totalTenths % 600) / 10);
  const tenths = totalTenths % 10;
  return `${minutes}:${String(seconds).padStart(2, "0")}.${tenths}`;
}

/**
 * Renders the reason why no comparisons could be made (query rejected, no eBay results, etc.).
 */
function ListingDetailsPanel({ reason }: { reason: string }) {
  return (
    <div className="font-mono text-xs text-muted-foreground">
      <span className="font-bold text-foreground">Why no comparison: </span>
      {reason}
    </div>
  );
}

/**
 * Renders the comparison transparency block for one result: eBay search query, comp (average) price,
 * and the list of comps. When compItems (title, price, url) exist, shows each as a link; otherwise
 * shows compPrices as plain price list.
 */
function ListingCompsPanel({ listing }: { listing: Listing }) {
  const { ebaySearchQuery, compPrice, compPrices, compItems, currency = "$" } = listing;
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
            <span className="text-primary font-bold">{formatPrice(compPrice, "$")}</span>
          </div>
        )}
      </div>
      {count > 0 && (
        <div>
          <span className="font-bold text-foreground">Compared against {count} listing{count !== 1 ? "s" : ""}:</span>
          <ul className="mt-1 max-h-40 overflow-auto space-y-0.5 pl-2 border-l-2 border-border">
            {compItems && compItems.length > 0
              ? compItems.map((item, i) => {
                  const status = item.filterStatus ?? (item.filtered ? "reject" : "accept");
                  const isRejected = status === "reject";
                  const isMaybe = status === "maybe";
                  
                  // Style classes based on status
                  const opacityClass = isRejected ? 'opacity-60' : '';
                  const linkClass = isRejected 
                    ? 'text-red-500 line-through' 
                    : isMaybe 
                    ? 'text-yellow-500' 
                    : 'text-primary';
                  const priceClass = isRejected 
                    ? 'text-red-500' 
                    : isMaybe 
                    ? 'text-yellow-500' 
                    : 'text-primary';
                  const reasonClass = isRejected 
                    ? 'text-red-500/70' 
                    : isMaybe 
                    ? 'text-yellow-500/70' 
                    : 'text-muted-foreground';
                  const statusLabel = isRejected ? '(filtered)' : isMaybe ? '(maybe)' : null;
                  const titleText = isRejected 
                    ? 'Filtered out as non-comparable' 
                    : isMaybe 
                    ? 'Partial match (0.5x weight in average)' 
                    : undefined;

                  return (
                    <li key={i} className={`flex items-baseline gap-2 flex-wrap ${opacityClass}`} style={{ wordBreak: 'break-word', overflowWrap: 'anywhere' }}>
                      <a
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={`truncate max-w-[280px] hover:underline ${linkClass}`}
                        title={titleText}
                      >
                        {item.title || "eBay listing"}
                      </a>
                      <span className={`font-bold shrink-0 ${priceClass}`}>
                        {formatPrice(item.price, "$")}
                      </span>
                      {statusLabel && (
                        <span className={`text-xs ${reasonClass} shrink-0`}>{statusLabel}</span>
                      )}
                      {item.filterReason && (
                        <span 
                          className={`text-xs ${reasonClass}`}
                          style={{
                            wordBreak: 'break-word',
                            overflowWrap: 'break-word',
                            whiteSpace: 'normal',
                            minWidth: 0,
                            flex: '1 1 0%',
                            maxWidth: '100%'
                          }}
                        >
                          — {item.filterReason}
                        </span>
                      )}
                    </li>
                  );
                })
              : compPrices?.map((p, i) => (
                  <li key={i}>
                    <span className="text-muted-foreground">{formatPrice(p, "$")}</span>
                  </li>
                ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/**
 * Converts a filtered-out listing row to a Listing for display in the table.
 */
function filteredOutToListing(row: FilteredOutListingRow): Listing {
  return {
    title: row.title,
    price: row.price,
    location: row.location,
    url: row.url,
    dealScore: null,
  };
}

/**
 * Scrollable results table with one row per listing (title, price, location, deal %, link).
 * Header shows result counts and actions (CSV export, new search). Filter section toggles
 * visibility of below-threshold deals. Rows are color-coded by deal quality; each row can
 * expand to show eBay comparison details (search query, comp price, comp listings).
 */
export function SearchResultsTable({
  listings,
  scannedCount,
  threshold,
  filteredOutListings = [],
  onDownloadCSV,
  onReset,
  isLoading = false,
  currentItem = null,
  facebookListings = [],
  ebayQueries = [],
  onCancel,
}: SearchResultsTableProps) {
  const [showBadDeals, setShowBadDeals] = useState<boolean>(true);
  const [showFilteredOut, setShowFilteredOut] = useState<boolean>(false);
  const [isFiltersExpanded, setIsFiltersExpanded] = useState<boolean>(false);
  const [expandedListingUrl, setExpandedListingUrl] = useState<string | null>(null);
  const [nowMs, setNowMs] = useState<number>(() => Date.now());

  useEffect(() => {
    if (isLoading) {
      const intervalId = window.setInterval(() => {
        setNowMs(Date.now());
      }, ELAPSED_TIME_UPDATE_INTERVAL_MS);
      return () => window.clearInterval(intervalId);
    } else {
      setNowMs(Date.now());
    }
  }, [isLoading]);

  const ebayQueriesByFbId = useMemo(() => {
    const m = new Map<string, DebugEbayQueryEntry>();
    for (const entry of ebayQueries) {
      m.set(entry.fbListingId, entry);
    }
    return m;
  }, [ebayQueries]);

  const facebookListingsByUrl = useMemo(() => {
    const m = new Map<string, DebugFacebookListing>();
    for (const listing of facebookListings) {
      m.set(listing.url, listing);
    }
    return m;
  }, [facebookListings]);

  const filteredListings = listings.filter((listing) => {
    if (showBadDeals) return true;
    return !isBadDeal(listing.dealScore, threshold);
  });

  const filteredOutUrls = new Set(filteredOutListings.map((item) => item.url));
  const evaluatedListingUrls = new Set(listings.map((l) => l.url));
  const filteredOutListingUrls = new Set(filteredOutListings.map((l) => l.url));
  
  const allFacebookListingsAsListings: Listing[] = isLoading && facebookListings.length > 0
    ? facebookListings
        .filter((fbListing) => !evaluatedListingUrls.has(fbListing.url) && !filteredOutListingUrls.has(fbListing.url))
        .map((fbListing) => ({
          title: fbListing.title,
          price: fbListing.price,
          currency: "$",
          location: fbListing.location,
          url: fbListing.url,
          dealScore: null,
        }))
    : [];
  
  const displayListings: Listing[] = isLoading || showFilteredOut
    ? [...filteredListings, ...allFacebookListingsAsListings, ...filteredOutListings.map(filteredOutToListing)]
    : filteredListings;

  const filteredCount = filteredListings.length;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3 flex-wrap">
            <h2 className="font-mono text-lg font-bold text-foreground">
              {isLoading ? "LOOT INCOMING..." : "HEIST COMPLETE!"}
            </h2>
            {isLoading && <HeistClockSection />}
          </div>
          <p className="font-mono text-xs text-muted-foreground">
            {isLoading 
              ? `${filteredCount} treasure${filteredCount !== 1 ? "s" : ""} found so far...`
              : `Showing ${filteredCount} of ${listings.length} treasures from ${scannedCount} scanned`
            }
          </p>
          {isLoading && currentItem && (
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
        {isLoading && onCancel && (
          <CancelSearchButton onCancel={onCancel} />
        )}
        {!isLoading && (
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
        )}
      </div>

      {/* Filters Section - hidden during loading */}
      {!isLoading && (
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
      )}

      {displayListings.length > 0 ? (
        <div className="max-h-[60vh] overflow-auto border border-border">
          <table className="w-full border-collapse font-mono text-sm">
            <thead className="sticky top-0 bg-secondary">
              <tr className="border-b border-border text-left">
                <th className="px-3 py-2 text-xs text-muted-foreground">TITLE</th>
                <th className="px-3 py-2 text-xs text-muted-foreground">PRICE</th>
                <th className="px-3 py-2 text-xs text-muted-foreground">LOCATION</th>
                {isLoading && (
                  <th className="px-3 py-2 text-xs text-muted-foreground">STATUS</th>
                )}
                <th className="px-3 py-2 text-xs text-muted-foreground">DEAL %</th>
                <th className="px-3 py-2 text-xs text-muted-foreground">LINK</th>
                <th className="px-3 py-2 text-xs text-muted-foreground w-20">DETAILS</th>
              </tr>
            </thead>
            <tbody>
              {displayListings.map((listing) => {
                const isFilteredOut = listing.dealScore === null && filteredOutUrls.has(listing.url);
                const goodDeal = !isFilteredOut && isGoodDeal(listing.dealScore, threshold);
                const badDeal = !isFilteredOut && isBadDeal(listing.dealScore, threshold);
                const rowBgClass = isFilteredOut
                  ? "bg-muted/30 hover:bg-muted/50 opacity-70"
                  : goodDeal
                  ? "bg-green-500/10 hover:bg-green-500/20"
                  : badDeal
                  ? "bg-red-500/10 hover:bg-red-500/20"
                  : "hover:bg-secondary/50";
                const hasComps = listing.ebaySearchQuery != null || listing.compPrice != null;
                const hasDetails = !hasComps && (listing.noCompReason != null && listing.noCompReason !== "");
                const isExpanded = expandedListingUrl === listing.url;
                const fbListing = facebookListingsByUrl.get(listing.url);
                const ebayQuery = fbListing?.fbListingId ? ebayQueriesByFbId.get(fbListing.fbListingId) : undefined;
                
                const isUnprocessed = isLoading && listing.dealScore === null && !ebayQuery && !isFilteredOut;
                
                let itemStatus: "Filtered" | "Completed" | "Evaluating" | "Todo";
                if (isFilteredOut) {
                  itemStatus = "Filtered";
                } else if (ebayQuery) {
                  itemStatus = ebayQuery.finishedAtMs ? "Completed" : "Evaluating";
                } else if (listing.dealScore !== null) {
                  itemStatus = "Completed";
                } else if (isUnprocessed) {
                  itemStatus = "Todo";
                } else {
                  itemStatus = isLoading ? "Evaluating" : "Completed";
                }
                
                const itemElapsedMs = isFilteredOut
                  ? null
                  : ebayQuery && ebayQuery.startedAtMs
                    ? (ebayQuery.finishedAtMs ?? (isLoading ? nowMs : ebayQuery.startedAtMs)) - ebayQuery.startedAtMs
                    : null;
                const itemElapsedFormatted = itemElapsedMs !== null && itemElapsedMs >= 0 ? formatElapsedMs(itemElapsedMs) : null;

                const filteredOutStyle = isFilteredOut ? "text-muted-foreground line-through" : "";
                const titleClasses = `px-3 py-2 max-w-[300px] truncate ${filteredOutStyle}`.trim();
                const priceClasses = isFilteredOut 
                  ? "px-3 py-2 font-bold text-muted-foreground line-through"
                  : "px-3 py-2 font-bold text-primary";
                const locationClasses = isFilteredOut
                  ? "px-3 py-2 max-w-[150px] truncate text-muted-foreground/70 line-through"
                  : "px-3 py-2 max-w-[150px] truncate text-muted-foreground";
                const linkClasses = isFilteredOut
                  ? "text-muted-foreground hover:text-foreground hover:underline line-through"
                  : "text-primary hover:underline";

                return (
                <Fragment key={listing.url}>
                <tr
                  className={`border-b border-border/50 transition-colors ${rowBgClass}`}
                >
                  <td className={titleClasses} title={listing.title}>
                    {listing.title}
                  </td>
                  <td className={priceClasses}>
                    {formatPrice(listing.price, listing.currency)}
                  </td>
                  <td className={locationClasses} title={listing.location}>
                    {listing.location}
                  </td>
                  {isLoading && (
                    <td className="px-3 py-2">
                      <div className="flex flex-col gap-0.5">
                        <span className={`text-xs font-semibold ${
                          itemStatus === "Completed" 
                            ? "text-green-500" 
                            : itemStatus === "Filtered"
                              ? "text-yellow-500"
                              : itemStatus === "Todo"
                                ? "text-muted-foreground/70"
                                : "text-primary"
                        }`}>
                          {itemStatus}
                        </span>
                        {itemElapsedFormatted !== null && (
                          <span className="text-[10px] text-muted-foreground tabular-nums">
                            {itemElapsedFormatted}
                          </span>
                        )}
                      </div>
                    </td>
                  )}
                  <td className="px-3 py-2">
                    {listing.dealScore !== null ? (
                      <span className={`font-bold ${goodDeal ? 'text-green-500' : badDeal ? 'text-red-500' : 'text-muted-foreground'}`}>
                        {listing.dealScore}%
                      </span>
                    ) : isFilteredOut ? (
                      <span className="text-muted-foreground italic">Filtered</span>
                    ) : (
                      <span className="text-muted-foreground/50">--</span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <a 
                      href={listing.url} 
                      target="_blank" 
                      rel="noopener noreferrer"
                      className={linkClasses}
                      onClick={(e: React.MouseEvent) => e.stopPropagation()}
                    >
                      VIEW →
                    </a>
                  </td>
                  <td className="px-3 py-2">
                    {hasComps || hasDetails ? (
                      <button
                        type="button"
                        onClick={() => setExpandedListingUrl(isExpanded ? null : listing.url)}
                        className="font-mono text-xs text-primary hover:underline"
                        aria-expanded={isExpanded}
                      >
                        {isExpanded ? "▲ Hide" : hasComps ? "▼ Comps" : "▼ Details"}
                      </button>
                    ) : (
                      <span className="text-muted-foreground/50 text-xs">--</span>
                    )}
                  </td>
                </tr>
                {isExpanded && hasComps && (
                  <tr className="border-b border-border/50 bg-secondary/80">
                    <td colSpan={TABLE_COLUMN_COUNT} className="px-4 py-3">
                      <ListingCompsPanel listing={listing} />
                    </td>
                  </tr>
                )}
                {isExpanded && hasDetails && (
                  <tr className="border-b border-border/50 bg-secondary/80">
                    <td colSpan={TABLE_COLUMN_COUNT} className="px-4 py-3">
                      <ListingDetailsPanel reason={listing.noCompReason!} />
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

