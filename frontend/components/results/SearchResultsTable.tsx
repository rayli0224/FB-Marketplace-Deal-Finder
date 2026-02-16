"use client";

import { Fragment, useState } from "react";
import { FullSizeToggle } from "@/components/ui/FullSizeToggle";

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

export interface SearchResultsTableProps {
  listings: Listing[];
  scannedCount: number;
  threshold: number;
  onDownloadCSV: () => void;
  onReset: () => void;
  isLoading?: boolean;
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
 * Formats a price with the given currency symbol.
 */
function formatPrice(price: number, currency: string = "$"): string {
  return `${currency}${price.toFixed(2)}`;
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
 * Scrollable results table with one row per listing (title, price, location, deal %, link).
 * Header shows result counts and actions (CSV export, new search). Filter section toggles
 * visibility of below-threshold deals. Rows are color-coded by deal quality; each row can
 * expand to show eBay comparison details (search query, comp price, comp listings).
 */
export function SearchResultsTable({
  listings,
  scannedCount,
  threshold,
  onDownloadCSV,
  onReset,
  isLoading = false,
}: SearchResultsTableProps) {
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
            {isLoading ? "LOOT INCOMING..." : "HEIST COMPLETE!"}
          </h2>
          <p className="font-mono text-xs text-muted-foreground">
            {isLoading 
              ? `${filteredCount} treasure${filteredCount !== 1 ? "s" : ""} found so far...`
              : `Showing ${filteredCount} of ${listings.length} treasures from ${scannedCount} scanned`
            }
          </p>
        </div>
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
                const hasDetails = !hasComps && (listing.noCompReason != null && listing.noCompReason !== "");
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
                    {formatPrice(listing.price, listing.currency)}
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
                    ) : hasDetails ? (
                      <button
                        type="button"
                        onClick={() => setExpandedListingUrl(isExpanded ? null : listing.url)}
                        className="font-mono text-xs text-primary hover:underline"
                        aria-expanded={isExpanded}
                      >
                        {isExpanded ? "▲ Hide" : "▼ Details"}
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
                {isExpanded && hasDetails && (
                  <tr className="border-b border-border/50 bg-secondary/80">
                    <td colSpan={7} className="px-4 py-3">
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

