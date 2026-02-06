"use client";

import { useState, useEffect, useCallback, type FormEvent, type ReactNode, type Ref, type ChangeEvent, type FocusEvent } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { formSchema, type FormData as ValidationFormData } from "@/lib/validation";
import { SkullIcon, TreasureIcon } from "@/lib/icons";

type AppState = "form" | "loading" | "done" | "error";

interface Listing {
  title: string;
  price: number;
  location: string;
  url: string;
  dealScore: number;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [appState, setAppState] = useState<AppState>("form");
  const {
    register,
    handleSubmit: handleFormSubmit,
    watch,
    formState: { errors, isValid },
  } = useForm<ValidationFormData>({
    resolver: zodResolver(formSchema),
    defaultValues: { query: "", zipCode: "", radius: "", threshold: "" },
    mode: "onChange",
  });
  const formData = watch();
  const [scannedCount, setScannedCount] = useState(0);
  const [evaluatedCount, setEvaluatedCount] = useState(0);
  const [csvBlob, setCsvBlob] = useState<Blob | null>(null);
  const [listings, setListings] = useState<Listing[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [phase, setPhase] = useState<string>("scraping");

  /**
   * Generates a CSV blob from listings data with pirate-themed column headers.
   * Formats each listing row with quoted strings for text fields and formatted numbers.
   * Returns a Blob object with CSV MIME type for download.
   */
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

  /**
   * Triggers browser download of the CSV file using a temporary anchor element.
   * Creates object URL from blob, creates anchor with download attribute, programmatically clicks it,
   * then cleans up by removing anchor and revoking object URL.
   */
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

  /**
   * Parses Server-Sent Events (SSE) stream data and updates UI state accordingly.
   * Reads chunks from the stream reader, decodes text, and processes each line.
   * Handles three event types: phase updates (sets phase state), progress updates (sets scanned count),
   * and completion (sets all final counts, listings, CSV blob, and transitions to done state).
   */
  const parseSSEStream = useCallback(
    async (reader: ReadableStreamDefaultReader<Uint8Array>) => {
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const text = decoder.decode(value);
        const lines = text.split("\n");

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = JSON.parse(line.slice(6));

            if (data.type === "phase") {
              setPhase(data.phase);
            } else if (data.type === "progress") {
              setScannedCount(data.scannedCount);
            } else if (data.type === "done") {
              setScannedCount(data.scannedCount);
              setEvaluatedCount(data.evaluatedCount);
              setListings(data.listings);

              const blob = generateCSV(data.listings);
              setCsvBlob(blob);

              setAppState("done");
            }
          }
        }
      }
    },
    [generateCSV, setPhase, setScannedCount, setEvaluatedCount, setListings, setCsvBlob, setAppState]
  );

  /**
   * Performs the marketplace search API call and processes the SSE response stream.
   * Sends form data as JSON POST request, reads the streaming response using ReadableStream,
   * and delegates stream parsing to parseSSEStream. Handles errors by logging and setting error state.
   */
  const performSearch = useCallback(async () => {
    try {
      setError(null);
      const response = await fetch(`${API_URL}/api/search/stream`, {
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
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("No response body");
      }

      await parseSSEStream(reader);
    } catch (err) {
      console.error("Search error:", err);
      setError(err instanceof Error ? err.message : "Failed to search marketplace");
      setAppState("error");
    }
  }, [formData, parseSSEStream, setError, setAppState]);

  useEffect(() => {
    if (appState !== "loading") return;
    performSearch();
  }, [appState, performSearch]);

  /**
   * Handles form submission by resetting all state to initial values and transitioning to loading state.
   * Called by react-hook-form after validation passes. Clears previous results and starts new search.
   */
  const onSubmit = (data: ValidationFormData) => {
    setScannedCount(0);
    setEvaluatedCount(0);
    setCsvBlob(null);
    setListings([]);
    setError(null);
    setPhase("scraping");
    setAppState("loading");
  };

  const handleSubmit = handleFormSubmit(onSubmit);

  /**
   * Resets the application state back to the form view.
   * Clears all search results, counts, and error state to allow a new search.
   */
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
                  register={register}
                  required
                  error={errors.query?.message}
                  icon={<TreasureIcon className="text-accent" />}
                />

                <FormField
                  label="PORT_CODE"
                  id="zipCode"
                  type="text"
                  placeholder="e.g. 10001"
                  register={register}
                  pattern="[0-9]{5}"
                  required
                  error={errors.zipCode?.message}
                  icon={<span className="text-accent">@</span>}
                />

                <div className="grid grid-cols-2 gap-4">
                  <FormField
                    label="RAID_RADIUS"
                    id="radius"
                    type="number"
                    placeholder="25"
                    register={register}
                    min={1}
                    max={500}
                    required
                    error={errors.radius?.message}
                    suffix="mi"
                  />

                  <FormField
                    label="STEAL_THRESHOLD"
                    id="threshold"
                    type="number"
                    placeholder="80"
                    register={register}
                    min={0}
                    max={100}
                    required
                    error={errors.threshold?.message}
                    suffix="%"
                    tooltip="Max % of eBay average price. Example: 80% = only show listings priced at 80% of eBay market value or less"
                  />
                </div>

                <button
                  type="submit"
                  disabled={!isValid}
                  className={`group mt-2 w-full border-2 px-4 py-3 font-mono text-sm font-bold uppercase tracking-wide transition-all ${
                    isValid
                      ? "border-primary bg-primary text-primary-foreground hover:bg-transparent hover:text-primary cursor-pointer"
                      : "border-muted bg-muted text-muted-foreground cursor-not-allowed opacity-50"
                  }`}
                >
                  <span className={`inline-block transition-transform ${isValid ? "group-hover:translate-x-1" : ""}`}>
                    {">>>"} BEGIN HEIST {"<<<"}
                  </span>
                </button>
              </form>
            )}

            {/* Loading State */}
            {appState === "loading" && (
              <div className="space-y-6">
                <div className="border border-border bg-secondary p-4">
                  <div className="flex items-center gap-3">
                    <div className="flex gap-1">
                      <span className="inline-block h-2 w-2 animate-bounce bg-primary" style={{ animationDelay: "0ms" }} />
                      <span className="inline-block h-2 w-2 animate-bounce bg-primary" style={{ animationDelay: "150ms" }} />
                      <span className="inline-block h-2 w-2 animate-bounce bg-primary" style={{ animationDelay: "300ms" }} />
                    </div>
                    <span className="font-mono text-sm text-muted-foreground">
                      {phase === "scraping" && "🔍 Searching Facebook Marketplace..."}
                      {phase === "ebay" && "📊 Fetching eBay prices..."}
                      {phase === "calculating" && "🧮 Calculating deals..."}
                    </span>
                  </div>
                  <div className="mt-3 font-mono text-xs text-muted-foreground/60">
                    {phase === "scraping" && "Infiltrating the marketplace for treasures..."}
                    {phase === "ebay" && "Checking market values on eBay..."}
                    {phase === "calculating" && "Crunching numbers to find the best deals..."}
                  </div>
                </div>

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

interface FormFieldProps {
  label: string;
  id: string;
  type: string;
  placeholder: string;
  value?: string | number;
  onChange?: (value: string) => void;
  required?: boolean;
  pattern?: string;
  min?: number;
  max?: number;
  icon?: ReactNode;
  suffix?: string;
  error?: string;
  tooltip?: string;
  register?: (name: keyof ValidationFormData) => {
    name: string;
    onChange: (e: ChangeEvent<HTMLInputElement>) => void;
    onBlur: (e: FocusEvent<HTMLInputElement>) => void;
    ref: Ref<HTMLInputElement>;
  };
}

/**
 * Reusable form field component with pirate-themed styling.
 * Supports both controlled (value/onChange) and uncontrolled (react-hook-form register) modes.
 * When register is provided, uses react-hook-form for form state management. Otherwise uses controlled mode.
 * Displays validation errors below the input with red border styling when invalid.
 */
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
  error,
  tooltip,
  register,
}: FormFieldProps) {
  return (
    <div>
      <label htmlFor={id} className="mb-2 flex items-center gap-2 font-mono text-xs text-muted-foreground">
        <span className="text-primary">$</span>
        {label}
        {tooltip && (
          <div className="group relative ml-1 inline-flex cursor-help">
            <span className="flex h-4 w-4 items-center justify-center rounded-full border border-accent/40 bg-accent/10 text-[10px] font-bold text-accent transition-all hover:border-accent hover:bg-accent/20 hover:scale-110">
              i
            </span>
            <div className="invisible absolute bottom-full left-1/2 mb-3 w-72 -translate-x-1/2 rounded-lg border-2 border-accent/30 bg-gradient-to-br from-card to-secondary/80 px-4 py-3 font-mono text-xs text-foreground shadow-[0_4px_12px_rgba(0,0,0,0.15)] backdrop-blur-sm group-hover:visible z-20">
              <div className="absolute -bottom-1 left-1/2 h-2 w-2 -translate-x-1/2 rotate-45 border-r-2 border-b-2 border-accent/30 bg-gradient-to-br from-card to-secondary/80"></div>
              <div className="relative">
                <span className="text-primary font-bold">{"//"}</span>{" "}
                <span className="text-foreground">{tooltip.split(". Example:")[0]}.</span>
                {tooltip.includes("Example:") && (
                  <>
                    {" "}
                    <span className="text-accent font-semibold">Example:</span>{" "}
                    <span className="text-foreground">{tooltip.split("Example:")[1]}</span>
                  </>
                )}
              </div>
            </div>
          </div>
        )}
        {icon && <span className="ml-auto">{icon}</span>}
      </label>
      <div className="relative">
        <input
          id={id}
          type={type}
          placeholder={placeholder}
          {...(register
            ? register(id as keyof ValidationFormData)
            : {
                value,
                onChange: (e) => onChange?.(e.target.value),
              })}
          required={required}
          pattern={pattern}
          min={min}
          max={max}
          className={`w-full border-2 bg-secondary px-3 py-2.5 font-mono text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none ${
            type === "number" ? "[appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none" : ""
          } ${
            error
              ? "border-destructive focus:border-destructive"
              : "border-border focus:border-primary"
          }`}
        />
        {suffix && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 font-mono text-xs text-muted-foreground">
            {suffix}
          </span>
        )}
      </div>
      {error && (
        <p className="mt-1 font-mono text-xs text-destructive">{error}</p>
      )}
    </div>
  );
}

interface LoadingBarProps {
  label: string;
  count: number;
  maxCount: number;
  suffix: string;
  icon: string;
}

/**
 * Progress bar component displaying loading progress with pirate-themed styling.
 * Calculates percentage from count and maxCount, then renders a visual progress bar.
 * Shows label with icon prefix, current count with suffix, and animated progress bar.
 */
function LoadingBar({ 
  label, 
  count, 
  maxCount,
  suffix,
  icon 
}: LoadingBarProps) {
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
