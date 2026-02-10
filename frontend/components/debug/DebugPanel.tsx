"use client";

import { useState } from "react";
import type { DebugSearchParams } from "@/components/debug/DebugSearchParams";

export type DebugFacebookListing = {
  title: string;
  price: number;
  location: string;
  url: string;
  description: string;
};

export type DebugEbayQueryEntry = { fbTitle: string; ebayQuery: string };

export type DebugLogEntry = { level: string; message: string };

export interface DebugPanelProps {
  searchParams: DebugSearchParams | null;
  facebookListings: DebugFacebookListing[];
  ebayQueries: DebugEbayQueryEntry[];
}

/**
 * Expandable panel shown only when the backend runs in debug mode. Displays search
 * request summary, Facebook data retrieved, and the generated eBay search queries.
 * Logs are shown in a separate floating panel. Persists for the duration of one search and resets on a new query.
 */
export function DebugPanel({
  searchParams,
  facebookListings,
  ebayQueries,
}: DebugPanelProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="mt-4 border border-border bg-secondary rounded-md overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((prev: boolean) => !prev)}
        className="w-full flex items-center justify-between gap-2 px-4 py-2 text-left font-mono text-sm text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
        aria-expanded={expanded}
      >
        <span>Debug</span>
        <span className="text-xs" aria-hidden>
          {expanded ? "▼" : "▶"}
        </span>
      </button>
      {expanded && (
        <div className="border-t border-border">
          {searchParams && (
            <div className="px-4 py-2 border-b border-border font-mono text-xs">
              <div className="font-semibold text-foreground mb-1.5">Search request</div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-0.5 text-muted-foreground">
                <div><span>Query: </span><span className="text-foreground">{searchParams.query}</span></div>
                <div><span>Zip: </span><span className="text-foreground">{searchParams.zipCode}</span></div>
                <div><span>Radius: </span><span className="text-foreground">{searchParams.radius} mi</span></div>
                <div><span>Max listings: </span><span className="text-foreground">{searchParams.maxListings}</span></div>
                <div><span>Threshold: </span><span className="text-foreground">{searchParams.threshold}%</span></div>
                <div><span>Extract descriptions: </span><span className="text-foreground">{searchParams.extractDescriptions ? "Yes" : "No"}</span></div>
              </div>
            </div>
          )}
          <div className="grid grid-cols-2 divide-x divide-border">
            <div className="px-4 py-2 border-b border-border bg-muted/50 font-mono text-xs font-semibold text-foreground">
              Facebook query details
            </div>
            <div className="px-4 py-2 border-b border-border bg-muted/50 font-mono text-xs font-semibold text-foreground">
              Generated eBay query
            </div>
          </div>
          <div className="max-h-80 overflow-auto">
            <DebugPairedRows
              facebookListings={facebookListings}
              ebayQueries={ebayQueries}
            />
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Renders paired rows so each Facebook listing and its corresponding eBay query
 * share the same row and scroll together, aligned by index.
 */
function DebugPairedRows({
  facebookListings,
  ebayQueries,
}: {
  facebookListings: DebugFacebookListing[];
  ebayQueries: DebugEbayQueryEntry[];
}) {
  const rowCount = Math.max(facebookListings.length, ebayQueries.length, 1);

  if (rowCount === 1 && facebookListings.length === 0 && ebayQueries.length === 0) {
    return (
      <div className="p-4 font-mono text-xs text-muted-foreground">
        No debug data yet. Data appears after the scrape and as listings are processed.
      </div>
    );
  }

  return (
    <div className="font-mono text-xs">
      {Array.from({ length: rowCount }, (_, i) => (
        <div
          key={i}
          className="grid grid-cols-2 divide-x divide-border border-b border-border items-start"
        >
          <div className="p-4 min-h-[4rem]">
            {facebookListings[i] ? (
              <FacebookListingCell item={facebookListings[i]} />
            ) : (
              <span className="text-muted-foreground">—</span>
            )}
          </div>
          <div className="p-4 min-h-[4rem]">
            {ebayQueries[i] ? (
              <EbayQueryCell entry={ebayQueries[i]} />
            ) : (
              <span className="text-muted-foreground">—</span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

/** Renders one Facebook listing's debug fields (title, price, location, url, description). */
function FacebookListingCell({ item }: { item: DebugFacebookListing }) {
  return (
    <div className="space-y-1">
      <div>
        <span className="text-muted-foreground">Title: </span>
        <span className="font-semibold text-foreground break-words">
          {item.title}
        </span>
      </div>
      <div className="text-muted-foreground">
        <span>Price: </span>
        <span className="text-foreground">${item.price.toFixed(2)}</span>
      </div>
      <div className="text-muted-foreground">
        <span>Location: </span>
        <span className="text-foreground">{item.location}</span>
      </div>
      {item.url && (
        <div>
          <span className="text-muted-foreground">URL: </span>
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary hover:underline break-all"
          >
            {item.url}
          </a>
        </div>
      )}
      {item.description && (
        <div>
          <span className="text-muted-foreground">Description: </span>
          <span className="text-foreground line-clamp-2 block">
            {item.description}
          </span>
        </div>
      )}
    </div>
  );
}

/** Renders one eBay query debug entry (FB title and generated eBay query). */
function EbayQueryCell({ entry }: { entry: DebugEbayQueryEntry }) {
  return (
    <div className="space-y-1">
      <div>
        <span className="text-muted-foreground">FB title: </span>
        <span className="font-semibold text-foreground break-words">
          {entry.fbTitle}
        </span>
      </div>
      <div>
        <span className="text-muted-foreground">eBay query: </span>
        <span className="text-primary break-words">
          &quot;{entry.ebayQuery}&quot;
        </span>
      </div>
    </div>
  );
}
