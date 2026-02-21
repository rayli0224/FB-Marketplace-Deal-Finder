"use client";

import { useEffect, useMemo, useState } from "react";
import type { DebugSearchParams } from "@/components/debug/DebugSearchParams";

const DEBUG_PAIRED_GRID_COLS = "grid-cols-[2.5rem_1fr_1fr]";
export type DebugFacebookListing = {
  fbListingId?: string;
  title: string;
  price: number;
  currency?: string;
  location: string;
  url: string;
  description: string;
  filtered?: boolean;
  filterReason?: string;
};

export type DebugEbayQueryEntry = {
  fbListingId: string;
  listingIndex: number;
  fbTitle: string;
  ebayQuery?: string;
  productRecon?: {
    canonical_name?: string;
    brand?: string;
    category?: string;
    model_or_series?: string;
    year_or_generation?: string;
    key_attributes?: Array<{ attribute: string; value: string; price_impact: string }>;
    notes?: string;
    citations?: { url: string; title?: string }[];
  };
  noCompReason?: string;
  startedAtMs: number;
  queryGeneratedAtMs?: number;
  finishedAtMs?: number;
  failed?: boolean;
};

export type DebugLogEntry = { level: string; message: string; timestampMs?: number };

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
          <div className={`grid ${DEBUG_PAIRED_GRID_COLS} divide-x divide-border`}>
            <div className="px-2 py-2 border-b border-border bg-muted/50 font-mono text-xs font-semibold text-foreground text-center">
              #
            </div>
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
 * share the same row and scroll together, aligned by a backend-only listing id.
 */
function DebugPairedRows({
  facebookListings,
  ebayQueries,
}: {
  facebookListings: DebugFacebookListing[];
  ebayQueries: DebugEbayQueryEntry[];
}) {
  const [nowMs, setNowMs] = useState<number>(() => Date.now());

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      setNowMs(Date.now());
    }, 100);
    return () => window.clearInterval(intervalId);
  }, []);

  const ebayQueriesByIndex = useMemo(() => {
    const m = new Map<string, DebugEbayQueryEntry>();
    for (const entry of ebayQueries) {
      m.set(entry.fbListingId, entry);
    }
    return m;
  }, [ebayQueries]);

  const rowCount = Math.max(facebookListings.length, 1);

  if (facebookListings.length === 0 && ebayQueries.length === 0) {
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
          className={`grid ${DEBUG_PAIRED_GRID_COLS} divide-x divide-border border-b border-border items-start`}
        >
          <div className="p-2 min-h-[4rem] flex items-start justify-center font-mono text-xs text-muted-foreground">
            {i + 1}
          </div>
          <div className="p-4 min-h-[4rem]">
            {facebookListings[i] ? (
              <FacebookListingCell item={facebookListings[i]} />
            ) : (
              <span className="text-muted-foreground">—</span>
            )}
          </div>
          <div className="p-4 min-h-[4rem]">
            {facebookListings[i]?.fbListingId && ebayQueriesByIndex.get(facebookListings[i].fbListingId!) ? (
              <EbayQueryCell entry={ebayQueriesByIndex.get(facebookListings[i].fbListingId!)!} nowMs={nowMs} />
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
  const currency = item.currency ?? "$";
  return (
    <div className={`space-y-1${item.filtered ? " opacity-50" : ""}`}>
      {item.filtered && (
        <div className="text-xs font-bold text-yellow-500">⚠️ FILTERED — suspicious price</div>
      )}
      <div>
        <span className="text-muted-foreground">Title: </span>
        <span className="font-semibold text-foreground break-words">
          {item.title}
        </span>
      </div>
      <div className="text-muted-foreground">
        <span>Price: </span>
        <span className="text-foreground">{currency}{item.price.toFixed(2)}</span>
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
function formatElapsedMs(elapsedMs: number): string {
  const clampedMs = Math.max(0, elapsedMs);
  const totalTenths = Math.floor(clampedMs / 100);
  const minutes = Math.floor(totalTenths / 600);
  const seconds = Math.floor((totalTenths % 600) / 10);
  const tenths = totalTenths % 10;
  return `${minutes}:${String(seconds).padStart(2, "0")}.${tenths}`;
}

function EbayQueryCell({ entry, nowMs }: { entry: DebugEbayQueryEntry; nowMs: number }) {
  const endMs = entry.finishedAtMs ?? nowMs;
  const elapsed = formatElapsedMs(endMs - entry.startedAtMs);
  const statusLabel = entry.finishedAtMs
    ? (entry.failed ? "Done (failed)" : "Done")
    : entry.queryGeneratedAtMs
      ? "Matching listings"
      : "Generating eBay query";

  return (
    <div className="space-y-1">
      <div className="text-muted-foreground">
        <span>Timer: </span>
        <span className="text-foreground tabular-nums">{elapsed}</span>
        <span className="ml-2 text-[10px] uppercase tracking-wide">{statusLabel}</span>
      </div>
      <div>
        <span className="text-muted-foreground">FB title: </span>
        <span className="font-semibold text-foreground break-words">
          {entry.fbTitle}
        </span>
      </div>
      <div>
        <span className="text-muted-foreground">eBay query: </span>
        {entry.ebayQuery ? (
          <span className="text-primary break-words">
            &quot;{entry.ebayQuery}&quot;
          </span>
        ) : entry.noCompReason ? (
          <span className="text-muted-foreground">—</span>
        ) : (
          <span className="text-muted-foreground">Waiting for query...</span>
        )}
      </div>
      <div className="pt-1">
        <div className="text-muted-foreground">
          <span className="text-muted-foreground">Details found: </span>
        </div>
        {entry.productRecon ? (
          <div className="text-muted-foreground space-y-0.5 pl-4">
            <div><span>◦ Product name: </span><span className="text-foreground">{entry.productRecon.canonical_name ?? "—"}</span></div>
            <div><span>◦ Brand: </span><span className="text-foreground">{entry.productRecon.brand ?? "—"}</span></div>
            <div><span>◦ Category: </span><span className="text-foreground">{entry.productRecon.category ?? "—"}</span></div>
            <div><span>◦ Model/series: </span><span className="text-foreground">{entry.productRecon.model_or_series ?? "—"}</span></div>
            <div><span>◦ Year/generation: </span><span className="text-foreground">{entry.productRecon.year_or_generation ?? "—"}</span></div>
            <div>
              <span>◦ Price-changing details: </span>
              <span className="text-foreground">
                {(entry.productRecon.key_attributes ?? []).length > 0
                  ? (entry.productRecon.key_attributes ?? [])
                      .map((attr) => `${attr.attribute}: ${attr.value} (${attr.price_impact})`)
                      .join(", ")
                  : "—"}
              </span>
            </div>
            <div><span>◦ Notes: </span><span className="text-foreground">{entry.productRecon.notes ?? "—"}</span></div>
            <div>
              <span>◦ Citations: </span>
              {(entry.productRecon.citations ?? []).length > 0 ? (
                <span className="inline-flex flex-col gap-0.5">
                  {(entry.productRecon.citations ?? []).map((c, idx) => (
                    <a
                      key={`${c.url}-${idx}`}
                      href={c.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary hover:underline break-all"
                    >
                      {c.url}
                    </a>
                  ))}
                </span>
              ) : (
                <span className="text-foreground">—</span>
              )}
            </div>
          </div>
        ) : (
          <div className="text-muted-foreground pl-4">Waiting for research...</div>
        )}
      </div>
      {entry.noCompReason && (
        <div className="text-muted-foreground">
          <span>{entry.noCompReason}</span>
        </div>
      )}
    </div>
  );
}
