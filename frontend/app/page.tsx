"use client";

import { useState, useEffect, useCallback } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { formSchema, type FormData as ValidationFormData } from "@/lib/validation";
import { AppHeader } from "@/components/layout/AppHeader";
import { AppFooter } from "@/components/layout/AppFooter";
import { MarketplaceSearchForm } from "@/components/search-form/MarketplaceSearchForm";
import { SearchLoadingState, type SearchPhase } from "@/components/loading/SearchLoadingState";
import { SearchErrorState } from "@/components/results/SearchErrorState";
import { SearchResultsTable } from "@/components/results/SearchResultsTable";
import type { Listing } from "@/components/results/SearchResultsTable";

type AppState = "form" | "loading" | "done" | "error";

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
  const [phase, setPhase] = useState<SearchPhase>("scraping");

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
   * Handles SSE phase update events by updating the current search phase state.
   * Called when the server sends a phase change notification (scraping, ebay, calculating).
   */
  const handlePhaseUpdate = useCallback((phase: SearchPhase) => {
    setPhase(phase);
  }, []);

  /**
   * Handles SSE progress update events by updating the scanned count.
   * Called periodically as listings are scanned during the search process.
   */
  const handleProgressUpdate = useCallback((scannedCount: number) => {
    setScannedCount(scannedCount);
  }, []);

  /**
   * Handles SSE completion events by setting final results and transitioning to done state.
   * Processes the final listings data, generates CSV blob, and updates all final counts.
   */
  const handleCompletion = useCallback((data: { scannedCount: number; evaluatedCount: number; listings: Listing[] }) => {
    setScannedCount(data.scannedCount);
    setEvaluatedCount(data.evaluatedCount);
    setListings(data.listings);

    const blob = generateCSV(data.listings);
    setCsvBlob(blob);

    setAppState("done");
  }, [generateCSV]);

  /**
   * Parses Server-Sent Events (SSE) stream data and updates UI state accordingly.
   * Reads chunks from the stream reader, decodes text, and processes each line.
   * Delegates to specific handlers for phase updates, progress updates, and completion events.
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
              handlePhaseUpdate(data.phase);
            } else if (data.type === "progress") {
              handleProgressUpdate(data.scannedCount);
            } else if (data.type === "done") {
              handleCompletion(data);
            }
          }
        }
      }
    },
    [handlePhaseUpdate, handleProgressUpdate, handleCompletion]
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
  }, [formData, parseSSEStream]);

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
      <div className="pointer-events-none fixed inset-0 bg-[repeating-linear-gradient(0deg,transparent,transparent_2px,rgba(0,0,0,0.1)_2px,rgba(0,0,0,0.1)_4px)] opacity-30" />
      
      <div className="relative mx-auto max-w-4xl">
        <AppHeader appState={appState} />

        <div className="border-2 border-border bg-card shadow-[4px_4px_0_0] shadow-primary/20">
          <div className="flex items-center gap-2 border-b border-border bg-secondary px-4 py-2">
            <span className="h-3 w-3 rounded-full bg-destructive" />
            <span className="h-3 w-3 rounded-full bg-accent" />
            <span className="h-3 w-3 rounded-full bg-primary" />
            <span className="ml-2 font-mono text-xs text-muted-foreground">loot_finder.exe</span>
          </div>

          <div className="p-6">
            {appState === "form" && (
              <MarketplaceSearchForm
                register={register}
                errors={errors}
                isValid={isValid}
                handleSubmit={handleSubmit}
              />
            )}

            {appState === "loading" && (
              <SearchLoadingState
                phase={phase}
                scannedCount={scannedCount}
                evaluatedCount={evaluatedCount}
              />
            )}

            {appState === "done" && (
              <SearchResultsTable
                listings={listings}
                scannedCount={scannedCount}
                onDownloadCSV={downloadCSV}
                onReset={handleReset}
              />
            )}

            {appState === "error" && (
              <SearchErrorState error={error} onReset={handleReset} />
            )}
          </div>
        </div>

        <AppFooter />
      </div>
    </main>
  );
}

