"use client";

import React from "react"

import { useState, useEffect, useCallback } from "react";

type AppState = "form" | "loading" | "done" | "error";

interface Listing {
  title: string;
  price: number;
  location: string;
  url: string;
  dealScore: number;
}

interface FormData {
  query: string;
  zipCode: string;
  radius: number;
  threshold: number;
}

// Cute skull ASCII art
function SkullIcon({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-block ${className}`} aria-hidden="true">
      {"(^.^)"}
    </span>
  );
}

// Treasure chest ASCII
function TreasureIcon({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-block ${className}`} aria-hidden="true">
      {"[*]"}
    </span>
  );
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [appState, setAppState] = useState<AppState>("form");
  const [formData, setFormData] = useState<FormData>({
    query: "",
    zipCode: "",
    radius: 25,
    threshold: 20,
  });
  const [scannedCount, setScannedCount] = useState(0);
  const [evaluatedCount, setEvaluatedCount] = useState(0);
  const [csvBlob, setCsvBlob] = useState<Blob | null>(null);
  const [listings, setListings] = useState<Listing[]>([]);
  const [error, setError] = useState<string | null>(null);

  const generateCSV = useCallback((listingsData: Listing[]) => {
    const headers = ["Treasure", "Doubloons", "Location", "Steal Score (%)", "Loot URL"];
    const rows = listingsData.map((item) => [
      `"${item.title}"`,
      `$${item.price}`,
      `"${item.location}"`,
      `${item.dealScore}%`,
      item.url,
    ]);

    const csvContent = [headers.join(","), ...rows.map((row) => row.join(","))].join("\n");
    return new Blob([csvContent], { type: "text/csv" });
  }, []);

  const downloadCSV = useCallback(() => {
    if (!csvBlob) return;

    const url = URL.createObjectURL(csvBlob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `loot-map-${formData.query.replace(/\s+/g, "-").toLowerCase()}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [csvBlob, formData.query]);

  useEffect(() => {
    if (appState !== "loading") return;

    const searchAPI = async () => {
      try {
        setError(null);
        const response = await fetch(`${API_URL}/api/search`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            query: formData.query,
            zipCode: formData.zipCode,
            radius: formData.radius,
            threshold: formData.threshold,
          }),
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({ detail: "Unknown error" }));
          throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        setScannedCount(data.scannedCount);
        setEvaluatedCount(data.evaluatedCount);
        setListings(data.listings);

        const blob = generateCSV(data.listings);
        setCsvBlob(blob);

        setAppState("done");
      } catch (err) {
        console.error("Search error:", err);
        setError(err instanceof Error ? err.message : "Failed to search marketplace");
        setAppState("error");
      }
    };

    searchAPI();
  }, [appState, formData, generateCSV]);

  // Removed auto-download - now showing results in UI instead

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setScannedCount(0);
    setEvaluatedCount(0);
    setCsvBlob(null);
    setListings([]);
    setError(null);
    setAppState("loading");
  };

  const handleReset = () => {
    setAppState("form");
    setScannedCount(0);
    setEvaluatedCount(0);
    setCsvBlob(null);
    setListings([]);
    setError(null);
  };

  return (
    <main className="min-h-screen bg-background p-4 md:p-8">
      {/* Scanlines overlay */}
      <div className="pointer-events-none fixed inset-0 bg-[repeating-linear-gradient(0deg,transparent,transparent_2px,rgba(0,0,0,0.1)_2px,rgba(0,0,0,0.1)_4px)] opacity-30" />
      
      <div className="relative mx-auto max-w-4xl">
        {/* Header */}
        <header className="mb-8 text-center">
          <div className="mb-4 text-4xl">
            <SkullIcon className="text-accent" />
          </div>
          <h1 className="mb-2 font-mono text-2xl font-bold tracking-tight text-foreground md:text-3xl">
            <span className="text-primary">{">"}</span> LOOT FINDER <span className="text-primary">{"<"}</span>
          </h1>
          <p className="font-mono text-sm text-muted-foreground">
            {"// hack the marketplace, steal the deals ~"}
          </p>
          <div className="mt-4 inline-block border border-border bg-card px-3 py-1">
            <span className="font-mono text-xs text-accent">STATUS: </span>
            <span className="font-mono text-xs text-primary">
              {appState === "form" && "AWAITING ORDERS"}
              {appState === "loading" && "RAIDING..."}
              {appState === "done" && "TREASURE ACQUIRED"}
              {appState === "error" && "MISSION FAILED"}
            </span>
          </div>
        </header>

        {/* Main Card */}
        <div className="border-2 border-border bg-card shadow-[4px_4px_0_0] shadow-primary/20">
          {/* Terminal Header */}
          <div className="flex items-center gap-2 border-b border-border bg-secondary px-4 py-2">
            <span className="h-3 w-3 rounded-full bg-destructive" />
            <span className="h-3 w-3 rounded-full bg-accent" />
            <span className="h-3 w-3 rounded-full bg-primary" />
            <span className="ml-2 font-mono text-xs text-muted-foreground">loot_finder.exe</span>
          </div>

          <div className="p-6">
            {/* Search Form */}
            {appState === "form" && (
              <form onSubmit={handleSubmit} className="space-y-5">
                <div className="mb-4 font-mono text-xs text-muted-foreground">
                  <span className="text-primary">{">"}</span> Enter target parameters, matey...
                </div>

                <FormField
                  label="TARGET_QUERY"
                  id="query"
                  type="text"
                  placeholder="e.g. iPhone 13 Pro"
                  value={formData.query}
                  onChange={(v) => setFormData((p) => ({ ...p, query: v }))}
                  required
                  icon={<TreasureIcon className="text-accent" />}
                />

                <FormField
                  label="PORT_CODE"
                  id="zipCode"
                  type="text"
                  placeholder="e.g. 10001"
                  value={formData.zipCode}
                  onChange={(v) => setFormData((p) => ({ ...p, zipCode: v }))}
                  pattern="[0-9]{5}"
                  required
                  icon={<span className="text-accent">@</span>}
                />

                <div className="grid grid-cols-2 gap-4">
                  <FormField
                    label="RAID_RADIUS"
                    id="radius"
                    type="number"
                    placeholder="25"
                    value={formData.radius}
                    onChange={(v) => setFormData((p) => ({ ...p, radius: Number(v) }))}
                    min={1}
                    max={500}
                    required
                    suffix="mi"
                  />

                  <FormField
                    label="STEAL_THRESHOLD"
                    id="threshold"
                    type="number"
                    placeholder="20"
                    value={formData.threshold}
                    onChange={(v) => setFormData((p) => ({ ...p, threshold: Number(v) }))}
                    min={1}
                    max={90}
                    required
                    suffix="%"
                  />
                </div>

                <button
                  type="submit"
                  className="group mt-2 w-full border-2 border-primary bg-primary px-4 py-3 font-mono text-sm font-bold uppercase tracking-wide text-primary-foreground transition-all hover:bg-transparent hover:text-primary"
                >
                  <span className="inline-block transition-transform group-hover:translate-x-1">
                    {">>>"} BEGIN HEIST {"<<<"}
                  </span>
                </button>
              </form>
            )}

            {/* Loading State */}
            {appState === "loading" && (
              <div className="space-y-6">
                <div className="space-y-4">
                  <LoadingBar 
                    label="Infiltrating listings" 
                    count={scannedCount}
                    maxCount={scannedCount || 100}
                    suffix="scanned" 
                    icon="~"
                  />
                  <LoadingBar 
                    label="Evaluating loot value" 
                    count={evaluatedCount}
                    maxCount={scannedCount || 100}
                    suffix="assessed" 
                    icon="*"
                  />
                </div>

                <div className="border border-border bg-secondary p-4">
                  <div className="flex items-center gap-3">
                    <div className="flex gap-1">
                      <span className="inline-block h-2 w-2 animate-bounce bg-primary" style={{ animationDelay: "0ms" }} />
                      <span className="inline-block h-2 w-2 animate-bounce bg-primary" style={{ animationDelay: "150ms" }} />
                      <span className="inline-block h-2 w-2 animate-bounce bg-primary" style={{ animationDelay: "300ms" }} />
                    </div>
                    <span className="font-mono text-sm text-muted-foreground">
                      Sneaking through the marketplace...
                    </span>
                  </div>
                  <div className="mt-3 font-mono text-xs text-muted-foreground/60">
                    <TypewriterText texts={[
                      "bypassing security...",
                      "cracking price databases...",
                      "comparing market values...",
                      "finding hidden treasures...",
                      "preparing loot manifest...",
                    ]} />
                  </div>
                </div>
              </div>
            )}

            {/* Done State - Results List */}
            {appState === "done" && (
              <div className="space-y-6">
                {/* Header */}
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="font-mono text-lg font-bold text-foreground">
                      HEIST COMPLETE!
                    </h2>
                    <p className="font-mono text-xs text-muted-foreground">
                      Found {listings.length} treasures from {scannedCount} scanned
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={downloadCSV}
                      className="border-2 border-primary bg-transparent px-3 py-2 font-mono text-xs font-bold text-primary transition-all hover:bg-primary hover:text-primary-foreground"
                    >
                      EXPORT CSV
                    </button>
                    <button
                      type="button"
                      onClick={handleReset}
                      className="border-2 border-accent bg-accent px-3 py-2 font-mono text-xs font-bold text-accent-foreground transition-all hover:bg-transparent hover:text-accent"
                    >
                      NEW SEARCH
                    </button>
                  </div>
                </div>

                {/* Results Table */}
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
                        {listings.map((listing, index) => (
                          <tr 
                            key={index} 
                            className="border-b border-border/50 hover:bg-secondary/50 transition-colors"
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
                              {listing.dealScore > 0 ? (
                                <span className={`font-bold ${listing.dealScore >= 20 ? 'text-green-500' : listing.dealScore >= 10 ? 'text-accent' : 'text-muted-foreground'}`}>
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
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="border border-border bg-secondary p-8 text-center">
                    <p className="font-mono text-muted-foreground">No listings found matching your criteria.</p>
                  </div>
                )}
              </div>
            )}

            {/* Error State */}
            {appState === "error" && (
              <div className="space-y-6">
                <div className="text-center">
                  <div className="mb-4 text-5xl">⚠️</div>
                  <h2 className="mb-2 font-mono text-xl font-bold text-destructive">
                    HEIST FAILED!
                  </h2>
                  <p className="font-mono text-sm text-muted-foreground mb-4">
                    {error || "An unknown error occurred"}
                  </p>
                  <button
                    type="button"
                    onClick={handleReset}
                    className="border-2 border-accent bg-accent px-4 py-3 font-mono text-sm font-bold text-accent-foreground transition-all hover:bg-transparent hover:text-accent"
                  >
                    TRY AGAIN
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <footer className="mt-8 text-center">
          <p className="font-mono text-xs text-muted-foreground">
            {"/* "} frontend only - no actual piracy involved {" */"}
          </p>
          <p className="mt-2 font-mono text-xs text-muted-foreground/50">
            made with {"<3"} by digital pirates
          </p>
        </footer>
      </div>
    </main>
  );
}

// Form field component with pirate styling
function FormField({
  label,
  id,
  type,
  placeholder,
  value,
  onChange,
  required,
  pattern,
  min,
  max,
  icon,
  suffix,
}: {
  label: string;
  id: string;
  type: string;
  placeholder: string;
  value: string | number;
  onChange: (value: string) => void;
  required?: boolean;
  pattern?: string;
  min?: number;
  max?: number;
  icon?: React.ReactNode;
  suffix?: string;
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-2 flex items-center gap-2 font-mono text-xs text-muted-foreground">
        <span className="text-primary">$</span>
        {label}
        {icon && <span className="ml-auto">{icon}</span>}
      </label>
      <div className="relative">
        <input
          id={id}
          type={type}
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          required={required}
          pattern={pattern}
          min={min}
          max={max}
          className="w-full border-2 border-border bg-secondary px-3 py-2.5 font-mono text-sm text-foreground placeholder:text-muted-foreground/50 focus:border-primary focus:outline-none"
        />
        {suffix && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 font-mono text-xs text-muted-foreground">
            {suffix}
          </span>
        )}
      </div>
    </div>
  );
}

// Loading bar component
function LoadingBar({ 
  label, 
  count, 
  maxCount,
  suffix,
  icon 
}: { 
  label: string; 
  count: number;
  maxCount: number;
  suffix: string;
  icon: string;
}) {
  const percentage = maxCount > 0 ? Math.min((count / maxCount) * 100, 100) : 0;
  
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between">
        <span className="font-mono text-xs text-muted-foreground">
          <span className="text-accent">{icon}</span> {label}
        </span>
        <span className="font-mono text-sm font-bold tabular-nums text-foreground">
          {count.toLocaleString()}
          <span className="ml-1 text-xs font-normal text-muted-foreground">{suffix}</span>
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden bg-secondary">
        <div 
          className="h-full bg-primary transition-all duration-100"
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}

// Typewriter effect component
function TypewriterText({ texts }: { texts: string[] }) {
  const [currentIndex, setCurrentIndex] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentIndex((prev) => (prev + 1) % texts.length);
    }, 1500);
    return () => clearInterval(interval);
  }, [texts.length]);

  return (
    <span className="inline-block">
      <span className="text-primary">{">"}</span> {texts[currentIndex]}
      <span className="animate-pulse">_</span>
    </span>
  );
}
