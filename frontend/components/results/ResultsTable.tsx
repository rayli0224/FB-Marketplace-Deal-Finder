"use client";

import { Fragment, useState, useMemo, useCallback, useRef, useEffect } from "react";
import type { DebugFacebookListing, DebugEbayQueryEntry } from "@/components/debug/DebugPanel";
import { DetailsPopup } from "./DetailsPopup";

export interface CompItem {
  title: string;
  price: number;
  url: string;
  filtered?: boolean;
  filterStatus?: "accept" | "maybe" | "reject";
  filterReason?: string;
}

export interface Listing {
  title: string;
  price: number;
  currency?: string;
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
  filterReason?: string;
}

export interface ResultsTableProps {
  displayListings: Listing[];
  threshold: number;
  filteredOutListings: FilteredOutListingRow[];
  emptyMessage: string;
  showStatusColumn?: boolean;
  ebayQueries?: DebugEbayQueryEntry[];
  facebookListings?: DebugFacebookListing[];
  nowMs?: number;
}

/** Offset used to sort post-eval filtered (newer) above pre-eval filtered (older). */
const FILTERED_RECENCY_OFFSET = 1_000_000;

type ListingFilterInfo = { isFiltered: true; isPostEval: boolean } | { isFiltered: false };

/** Returns filter status for a listing. Used for sorting and row styling. */
function getListingFilterInfo(
  listing: Listing,
  filteredOutUrls: Set<string>
): ListingFilterInfo {
  const inFilteredOut = filteredOutUrls.has(listing.url);
  const hasNoCompReason = listing.noCompReason != null && listing.noCompReason !== "";
  const ranEbayQuery =
    listing.ebaySearchQuery != null && String(listing.ebaySearchQuery).trim() !== "";
  const isFiltered =
    listing.dealScore === null &&
    (inFilteredOut || (hasNoCompReason && !ranEbayQuery));
  if (!isFiltered) return { isFiltered: false };
  return { isFiltered: true, isPostEval: hasNoCompReason && !inFilteredOut };
}

/** Returns true when the listing meets or exceeds the deal threshold. */
function isGoodDeal(dealScore: number | null, threshold: number): boolean {
  return dealScore !== null && dealScore >= threshold;
}

/** Returns true when the listing is below the deal threshold. */
export function isBadDeal(dealScore: number | null, threshold: number): boolean {
  return dealScore !== null && dealScore < threshold;
}

/** Converts a filtered-out row to a Listing for table display. */
export function filteredOutToListing(row: FilteredOutListingRow): Listing {
  return {
    title: row.title,
    price: row.price,
    location: row.location,
    url: row.url,
    dealScore: null,
    noCompReason: row.filterReason ?? "Filtered before evaluation",
  };
}

function formatPrice(price: number, currency: string = "$"): string {
  return `${currency}${price.toFixed(2)}`;
}

function formatElapsedMs(elapsedMs: number): string {
  const clampedMs = Math.max(0, elapsedMs);
  const totalTenths = Math.floor(clampedMs / 100);
  const minutes = Math.floor(totalTenths / 600);
  const seconds = Math.floor((totalTenths % 600) / 10);
  const tenths = totalTenths % 10;
  return `${minutes}:${String(seconds).padStart(2, "0")}.${tenths}`;
}

function getItemStatusClass(status: "Filtered" | "Completed" | "Evaluating" | "Todo"): string {
  switch (status) {
    case "Completed":
      return "text-green-500";
    case "Filtered":
      return "text-yellow-500";
    case "Todo":
      return "text-muted-foreground/70";
    default:
      return "text-primary";
  }
}

/**
 * Shared results table: renders rows for displayListings with expandable comps/details.
 * Used by both SearchLoadingView and SearchResultsView.
 */
export function ResultsTable({
  displayListings,
  threshold,
  filteredOutListings,
  emptyMessage,
  showStatusColumn = false,
  ebayQueries = [],
  facebookListings = [],
  nowMs = 0,
}: ResultsTableProps) {
  const [expandedListingUrl, setExpandedListingUrl] = useState<string | null>(null);
  const [anchorRect, setAnchorRect] = useState<DOMRect | null>(null);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);

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

  const filteredOutUrls = new Set(filteredOutListings.map((item) => item.url));

  const sortedDisplayListings = useMemo(() => {
    const filtered: { listing: Listing; idx: number; isPostEval: boolean }[] = [];
    const nonFiltered: Listing[] = [];
    displayListings.forEach((listing, idx) => {
      const filterInfo = getListingFilterInfo(listing, filteredOutUrls);
      if (filterInfo.isFiltered) {
        filtered.push({ listing, idx, isPostEval: filterInfo.isPostEval });
      } else {
        nonFiltered.push(listing);
      }
    });
    filtered.sort((a, b) => {
      const recencyA = a.isPostEval ? a.idx + FILTERED_RECENCY_OFFSET : a.idx;
      const recencyB = b.isPostEval ? b.idx + FILTERED_RECENCY_OFFSET : b.idx;
      return recencyB - recencyA;
    });
    return [...nonFiltered, ...filtered.map((f) => f.listing)];
  }, [displayListings, filteredOutListings]);

  const handleCloseDetails = useCallback(() => {
    setExpandedListingUrl(null);
    setAnchorRect(null);
    buttonRef.current = null;
  }, []);

  const handleOpenDetails = useCallback(
    (e: React.MouseEvent<HTMLButtonElement>, url: string) => {
      if (expandedListingUrl === url) {
        handleCloseDetails();
      } else {
        buttonRef.current = e.currentTarget;
        setAnchorRect(e.currentTarget.getBoundingClientRect());
        setExpandedListingUrl(url);
      }
    },
    [expandedListingUrl, handleCloseDetails]
  );

  const expandedListing = useMemo(
    () =>
      expandedListingUrl
        ? sortedDisplayListings.find((l) => l.url === expandedListingUrl) ?? null
        : null,
    [expandedListingUrl, sortedDisplayListings]
  );

  useEffect(() => {
    if (!expandedListingUrl) return;
    const onScrollOrResize = () => {
      if (buttonRef.current) {
        setAnchorRect(buttonRef.current.getBoundingClientRect());
      }
    };
    const scrollEl = scrollContainerRef.current;
    if (scrollEl) scrollEl.addEventListener("scroll", onScrollOrResize);
    window.addEventListener("scroll", onScrollOrResize, true);
    window.addEventListener("resize", onScrollOrResize);
    return () => {
      if (scrollEl) scrollEl.removeEventListener("scroll", onScrollOrResize);
      window.removeEventListener("scroll", onScrollOrResize, true);
      window.removeEventListener("resize", onScrollOrResize);
    };
  }, [expandedListingUrl]);

  if (displayListings.length === 0) {
    return (
      <div className="border border-border bg-secondary p-8 text-center">
        <p className="font-mono text-muted-foreground">{emptyMessage}</p>
      </div>
    );
  }

  return (
    <Fragment>
      <div ref={scrollContainerRef} className="max-h-[60vh] overflow-auto border border-border">
        <table className="w-full border-collapse font-mono text-sm">
          <thead className="sticky top-0 bg-secondary">
            <tr className="border-b border-border text-left">
              <th className="px-3 py-2 text-xs text-muted-foreground">LISTING</th>
              <th className="px-3 py-2 text-xs text-muted-foreground">PRICE</th>
              <th className="px-3 py-2 text-xs text-muted-foreground">LOCATION</th>
              {showStatusColumn && (
                <th className="px-3 py-2 text-xs text-muted-foreground">STATUS</th>
              )}
              <th className="px-3 py-2 text-xs text-muted-foreground">DEAL %</th>
              <th className="px-3 py-2 text-xs text-muted-foreground w-20">DETAILS</th>
            </tr>
          </thead>
          <tbody>
            {sortedDisplayListings.map((listing) => {
              const filterInfo = getListingFilterInfo(listing, filteredOutUrls);
              const isFilteredOut = filterInfo.isFiltered;
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

              const isUnprocessed = showStatusColumn && listing.dealScore === null && !ebayQuery && !isFilteredOut;

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
                itemStatus = showStatusColumn ? "Evaluating" : "Completed";
              }

              const itemElapsedMs = isFilteredOut
                ? null
                : ebayQuery && ebayQuery.startedAtMs
                  ? (ebayQuery.finishedAtMs ?? nowMs) - ebayQuery.startedAtMs
                  : null;
              const itemElapsedFormatted =
                itemElapsedMs !== null && itemElapsedMs >= 0 ? formatElapsedMs(itemElapsedMs) : null;

              const filteredOutStyle = isFilteredOut ? "text-muted-foreground line-through" : "";
              const titleClasses = `px-3 py-2 max-w-[300px] truncate ${filteredOutStyle}`.trim();
              const priceClasses = isFilteredOut
                ? "px-3 py-2 font-bold text-muted-foreground line-through"
                : "px-3 py-2 font-bold text-primary";
              const locationClasses = isFilteredOut
                ? "px-3 py-2 max-w-[150px] truncate text-muted-foreground/70 line-through"
                : "px-3 py-2 max-w-[150px] truncate text-muted-foreground";
              return (
                <Fragment key={listing.url}>
                  <tr className={`border-b border-border/50 transition-colors ${rowBgClass}`}>
                    <td className={titleClasses} title={listing.title}>
                      <a
                        href={listing.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={`block truncate cursor-pointer ${isFilteredOut ? "text-muted-foreground hover:text-foreground hover:underline" : "text-primary hover:underline"}`}
                        onClick={(e: React.MouseEvent) => e.stopPropagation()}
                      >
                        {listing.title}
                      </a>
                    </td>
                    <td className={priceClasses}>
                      {formatPrice(listing.price, listing.currency)}
                    </td>
                    <td className={locationClasses} title={listing.location}>
                      {listing.location}
                    </td>
                    {showStatusColumn && (
                      <td className="px-3 py-2">
                        <div className="flex flex-col gap-0.5">
                          <span
                            className={`text-xs font-semibold ${getItemStatusClass(itemStatus)}`}
                          >
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
                        <span
                          className={`font-bold ${goodDeal ? "text-green-500" : badDeal ? "text-red-500" : "text-muted-foreground"}`}
                        >
                          {listing.dealScore}%
                        </span>
                      ) : (
                        <span className="text-muted-foreground/50">--</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {hasComps || hasDetails ? (
                        <button
                          type="button"
                          onClick={(e) => handleOpenDetails(e, listing.url)}
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
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {expandedListing && anchorRect && (
        <DetailsPopup
          listing={expandedListing}
          anchorRect={anchorRect}
          onClose={handleCloseDetails}
        />
      )}
    </Fragment>
  );
}
