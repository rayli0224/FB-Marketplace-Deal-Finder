"use client";

import type { DebugSearchParams } from "@/components/debug/DebugSearchParams";

export interface SearchQueryDetailsProps {
  searchParams: DebugSearchParams | null;
}

const SEARCH_PARAM_FIELDS: {
  label: string;
  key: keyof DebugSearchParams;
  format?: (value: string | number | boolean) => string;
}[] = [
  { label: "Query", key: "query" },
  { label: "Zip", key: "zipCode" },
  { label: "Radius", key: "radius", format: (v) => `${v} mi` },
  { label: "Max listings", key: "maxListings" },
  { label: "Threshold", key: "threshold", format: (v) => `${v}%` },
  { label: "Extract descriptions", key: "extractDescriptions", format: (v) => (v ? "Yes" : "No") },
];

/**
 * Displays search request parameters (query, location, radius, etc.).
 * Shown on both the loading and results views.
 */
export function SearchQueryDetails({ searchParams }: SearchQueryDetailsProps) {
  if (!searchParams) return null;

  return (
    <div className="w-full border-2 border-border bg-secondary px-4 py-2 font-mono text-xs text-muted-foreground">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-0.5">
        {SEARCH_PARAM_FIELDS.map(({ label, key, format }) => {
          const value = searchParams[key];
          const display = format ? format(value) : String(value);
          return (
            <div key={key}>
              <span>{label}: </span>
              <span className="text-foreground">{display}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
