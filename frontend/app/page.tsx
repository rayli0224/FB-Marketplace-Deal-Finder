"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { formSchema, type FormData as ValidationFormData, DEFAULT_RADIUS } from "@/lib/validation";
import { AppHeader } from "@/components/layout/AppHeader";
import { AppFooter } from "@/components/layout/AppFooter";
import { MarketplaceSearchForm } from "@/components/search-form/MarketplaceSearchForm";
import { SearchLoadingState, type SearchPhase } from "@/components/loading/SearchLoadingState";
import { SearchErrorState } from "@/components/results/SearchErrorState";
import { SearchResultsTable } from "@/components/results/SearchResultsTable";
import { CookieSetupGuide } from "@/components/auth/CookieSetupGuide";
import type { Listing } from "@/components/results/SearchResultsTable";
import { DebugPanel } from "@/components/debug/DebugPanel";
import { FloatingLogPanel } from "@/components/debug/FloatingLogPanel";
import type { DebugFacebookListing, DebugEbayQueryEntry } from "@/components/debug/DebugPanel";
import type { DebugSearchParams } from "@/components/debug/DebugSearchParams";

type AppState = "setup" | "form" | "loading" | "done" | "error";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Defaults when backend omits debug_mode params (fallback for older or partial payloads). */
const DEFAULT_DEBUG_RADIUS = DEFAULT_RADIUS;
const DEFAULT_DEBUG_MAX_LISTINGS = 20;
const DEFAULT_DEBUG_THRESHOLD = 20;

type SSEDispatchHandlers = {
  handlePhaseUpdate: (phase: SearchPhase) => void;
  handleProgressUpdate: (scannedCount: number) => void;
  handleFilteredUpdate?: (filteredCount: number) => void;
  handleCompletion: (data: { scannedCount: number; filteredCount?: number; evaluatedCount: number; listings: Listing[]; threshold?: number; averageConfidence?: number | null }) => void;
  handleAuthError: () => void;
  setEvaluatedCount: (n: number) => void;
  onListingResult?: (listing: Listing, evaluatedCount: number) => void;
  onDebugMode?: (params?: DebugSearchParams) => void;
  onDebugFacebook?: (listings: DebugFacebookListing[]) => void;
  onDebugFacebookListing?: (listing: DebugFacebookListing) => void;
  onDebugEbayQuery?: (entry: DebugEbayQueryEntry) => void;
  onDebugLog?: (entry: { level: string; message: string }) => void;
};

/**
 * Parses a single SSE "data:" payload (JSON string) and invokes the appropriate handler by event type.
 * Throws if JSON is invalid so the stream parser can surface the error.
 */
function dispatchSSEEvent(payloadString: string, handlers: SSEDispatchHandlers): void {
  const data = JSON.parse(payloadString) as {
    type: string;
    phase?: SearchPhase;
    scannedCount?: number;
    filteredCount?: number;
    evaluatedCount?: number;
    listing?: Listing;
    listings?: Listing[] | DebugFacebookListing[];
    threshold?: number;
    averageConfidence?: number | null;
    debug?: boolean;
    query?: string;
    zipCode?: string;
    radius?: number;
    maxListings?: number;
    extractDescriptions?: boolean;
    fbTitle?: string;
    ebayQuery?: string;
    level?: string;
    message?: string;
    url?: string;
  };
  if (data.type === "auth_error") {
    handlers.handleAuthError();
  } else if (data.type === "phase" && data.phase != null) {
    handlers.handlePhaseUpdate(data.phase);
  } else if (data.type === "filtered" && typeof data.filteredCount === "number") {
    handlers.handleFilteredUpdate?.(data.filteredCount);
  } else if (data.type === "progress" && typeof data.scannedCount === "number") {
    handlers.handleProgressUpdate(data.scannedCount);
  } else if (data.type === "listing_result" && data.listing != null && typeof data.evaluatedCount === "number") {
    handlers.onListingResult?.(data.listing, data.evaluatedCount);
  } else if (data.type === "listing_processed" && typeof data.evaluatedCount === "number") {
    handlers.setEvaluatedCount(data.evaluatedCount);
  } else if (data.type === "done" && data.listings != null && Array.isArray(data.listings)) {
    handlers.handleCompletion({
      scannedCount: data.scannedCount ?? 0,
      filteredCount: data.filteredCount ?? 0,
      evaluatedCount: data.evaluatedCount ?? 0,
      listings: data.listings as Listing[],
      threshold: data.threshold,
    });
  } else if (data.type === "debug_mode" && data.debug) {
    const params: DebugSearchParams | undefined =
      data.query != null && data.zipCode != null
        ? {
            query: data.query,
            zipCode: data.zipCode,
            radius: data.radius ?? DEFAULT_DEBUG_RADIUS,
            maxListings: data.maxListings ?? DEFAULT_DEBUG_MAX_LISTINGS,
            threshold: data.threshold ?? DEFAULT_DEBUG_THRESHOLD,
            extractDescriptions: data.extractDescriptions ?? false,
          }
        : undefined;
    handlers.onDebugMode?.(params);
  } else if (data.type === "debug_facebook" && Array.isArray(data.listings)) {
    handlers.onDebugFacebook?.(data.listings as DebugFacebookListing[]);
  } else if (data.type === "debug_facebook_listing" && data.listing) {
    handlers.onDebugFacebookListing?.(data.listing as DebugFacebookListing);
  } else if (data.type === "debug_ebay_query" && data.fbTitle != null && data.ebayQuery != null) {
    handlers.onDebugEbayQuery?.({ fbTitle: data.fbTitle, ebayQuery: data.ebayQuery });
  } else if (data.type === "debug_log" && data.level != null && data.message != null) {
    handlers.onDebugLog?.({ level: data.level, message: data.message });
  } else if (data.type === "inspector_url" && typeof data.url === "string") {
    window.open(data.url, "_blank");
  }
}

export default function Home() {
  const [appState, setAppState] = useState<AppState>("setup");
  const [cookiesChecked, setCookiesChecked] = useState(false);
  const {
    register,
    handleSubmit: handleFormSubmit,
    watch,
    setValue,
    formState: { errors, isValid },
  } = useForm<ValidationFormData>({
    resolver: zodResolver(formSchema),
    defaultValues: { query: "", zipCode: "", radius: String(DEFAULT_RADIUS), threshold: "", maxListings: "", extractDescriptions: false },
    mode: "onTouched",
  });
  const formData = watch();

  /**
   * Checks whether Facebook login data is already configured by hitting the
   * cookies status endpoint. If configured, skips straight to the search form.
   * If not (or if the check fails), shows the setup guide.
   */
  useEffect(() => {
    async function checkCookies() {
      try {
        const res = await fetch(`${API_URL}/api/cookies/status`);
        const data = await res.json();
        if (data.configured) {
          setAppState("form");
        } else {
          setAppState("setup");
        }
      } catch {
        // Can't reach the backend — show setup so user can try again
        setAppState("setup");
      } finally {
        setCookiesChecked(true);
      }
    }
    checkCookies();
  }, []);
  const [scannedCount, setScannedCount] = useState(0);
  const [filteredCount, setFilteredCount] = useState(0);
  const [evaluatedCount, setEvaluatedCount] = useState(0);
  const [maxListings, setMaxListings] = useState<number>(20);
  const [csvBlob, setCsvBlob] = useState<Blob | null>(null);
  const [listings, setListings] = useState<Listing[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [phase, setPhase] = useState<SearchPhase>("scraping");
  const [threshold, setThreshold] = useState<number>(0);
  const [debugEnabled, setDebugEnabled] = useState(false);
  const [debugSearchParams, setDebugSearchParams] = useState<DebugSearchParams | null>(null);
  const [debugFacebookListings, setDebugFacebookListings] = useState<DebugFacebookListing[]>([]);
  const [debugEbayQueries, setDebugEbayQueries] = useState<DebugEbayQueryEntry[]>([]);
  const [debugLogs, setDebugLogs] = useState<Array<{ level: string; message: string }>>([]);
  const [isSearching, setIsSearching] = useState<boolean>(false);
  const isSearchingRef = useRef<boolean>(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const readerRef = useRef<ReadableStreamDefaultReader<Uint8Array> | null>(null);

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
      item.dealScore !== null ? `${item.dealScore}%` : "--",
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
   * Updates the current search phase (e.g. scraping, evaluating) from an SSE event.
   */
  const handlePhaseUpdate = useCallback((phase: SearchPhase) => {
    setPhase(phase);
  }, []);

  /**
   * Updates the scanned listing count from an SSE progress event.
   */
  const handleProgressUpdate = useCallback((scannedCount: number) => {
    setScannedCount(scannedCount);
  }, []);

  /**
   * Updates the filtered count when listings are filtered for suspicious prices.
   */
  const handleFilteredUpdate = useCallback((filteredCount: number) => {
    setFilteredCount(filteredCount);
  }, []);

  /**
   * Handles an auth_error event from the backend, indicating the Facebook session has expired.
   * Resets the search state and sends the user back to the cookie setup guide so they can
   * re-connect their Facebook account.
   */
  const handleAuthError = useCallback(() => {
    isSearchingRef.current = false;
    setIsSearching(false);
    setScannedCount(0);
    setFilteredCount(0);
    setEvaluatedCount(0);
    setPhase("scraping");
    setError("Your Facebook session has expired. Please re-connect your account to keep searching.");
    setAppState("setup");
  }, []);

  /**
   * Applies the final search result: sets listings, counts, threshold, generates CSV blob,
   * and switches the app to the done state so the results table is shown.
   */
  const handleCompletion = useCallback((data: { scannedCount: number; filteredCount?: number; evaluatedCount: number; listings: Listing[]; threshold?: number }) => {
    setScannedCount(data.scannedCount);
    setFilteredCount(data.filteredCount ?? 0);
    setEvaluatedCount(data.evaluatedCount);
    setListings(data.listings);
    setThreshold(data.threshold || 0);

    const blob = generateCSV(data.listings);
    setCsvBlob(blob);

    setAppState("done");
  }, [generateCSV]);

  const onDebugEbayQuery = useCallback((entry: DebugEbayQueryEntry) => {
    setDebugEbayQueries((prev: DebugEbayQueryEntry[]) => [...prev, entry]);
  }, []);

  /**
   * Handles a single listing result from the backend as it's processed.
   * Appends the listing to the results array for incremental display.
   */
  const onListingResult = useCallback((listing: Listing, evaluatedCount: number) => {
    setListings((prev) => [...prev, listing]);
    setEvaluatedCount(evaluatedCount);
  }, []);

  /**
   * Parses an SSE stream from the reader and updates UI from each event.
   * Reads in chunks and accumulates text in a buffer so only complete lines (ending with \n)
   * are parsed. This avoids "Unterminated string" when the large "done" payload is split across
   * TCP chunks. Uses stream: true for decode so multi-byte UTF-8 spanning chunks is handled.
   * Event types: "phase", "progress", "listing_processed", "done", and when backend runs with
   * --debug: "debug_mode", "debug_facebook", "debug_ebay_query". Handles cancellation gracefully.
   */
  const parseSSEStream = useCallback(
    async (reader: ReadableStreamDefaultReader<Uint8Array>) => {
      const decoder = new TextDecoder();
      let buffer = "";

      const sseHandlers: SSEDispatchHandlers = {
        handlePhaseUpdate,
        handleProgressUpdate,
        handleFilteredUpdate,
        handleCompletion,
        handleAuthError,
        setEvaluatedCount,
        onListingResult,
        onDebugMode: (params) => {
          setDebugEnabled(true);
          if (params) setDebugSearchParams(params);
        },
        onDebugFacebook: setDebugFacebookListings,
        onDebugFacebookListing: (listing: DebugFacebookListing) =>
          setDebugFacebookListings((prev: DebugFacebookListing[]) => [...prev, listing]),
        onDebugEbayQuery: onDebugEbayQuery,
        onDebugLog: (entry) => setDebugLogs((prev: Array<{ level: string; message: string }>) => [...prev, entry]),
      };

      try {
        while (true) {
          const { done, value } = await reader.read();
          buffer += decoder.decode(value, { stream: !done });

          const hasNewline = buffer.includes("\n");
          if (!hasNewline && !done) continue;

          const lines = buffer.split("\n");
          buffer = done ? "" : (lines.pop() ?? "");

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              try {
                dispatchSSEEvent(line.slice(6), sseHandlers);
              } catch (parseErr) {
                console.error("SSE parse error for line length:", line.length, parseErr);
                throw parseErr;
              }
            }
          }

          if (done) {
            if (buffer.startsWith("data: ")) {
              try {
                dispatchSSEEvent(buffer.slice(6), sseHandlers);
              } catch {
                // Trailing partial line when stream ends without newline; ignore.
              }
            }
            break;
          }
        }
      } catch (err) {
        // If cancelled, release the reader and re-throw to be handled by performSearch
        if (err instanceof Error && err.name === "AbortError") {
          reader.cancel();
          throw err;
        }
        // For other errors, try to cancel the reader and re-throw
        try {
          reader.cancel();
        } catch {
          // Reader may already be cancelled, ignore
        }
        throw err;
      } finally {
        reader.releaseLock();
      }
    },
    [handlePhaseUpdate, handleProgressUpdate, handleFilteredUpdate, handleCompletion, handleAuthError, onListingResult, onDebugEbayQuery]
  );

  /**
   * Cancels the current search by canceling the stream reader and aborting the fetch request.
   * Resets state and returns the app to the form view.
   */
  const cancelSearch = useCallback(async () => {
    // Tell the backend to cancel immediately (kills Chrome, stops scraping)
    // Await so cleanup starts before we allow a new search
    try {
      await fetch(`${API_URL}/api/search/cancel`, { method: "POST" });
    } catch {
      // Backend may already be down, continue with local cleanup
    }

    // Cancel the reader first to stop reading from the stream
    if (readerRef.current) {
      try {
        readerRef.current.cancel();
      } catch {
        // Reader may already be cancelled or released, ignore
      }
      try {
        readerRef.current.releaseLock();
      } catch {
        // Lock may already be released, ignore
      }
      readerRef.current = null;
    }
    
    // Then abort the fetch request
    if (abortControllerRef.current) {
      try {
        abortControllerRef.current.abort();
      } catch {
        // AbortController may already be aborted, ignore
      }
      abortControllerRef.current = null;
    }
    
    // Keep logs from this run and append a cancellation message
    setDebugLogs((prev) => [
      ...prev,
      { level: "WARNING", message: "Search cancelled by user" },
    ]);
    
    isSearchingRef.current = false;
    setIsSearching(false);
    setAppState("form");
    setScannedCount(0);
    setFilteredCount(0);
    setEvaluatedCount(0);
    setPhase("scraping");
    setError(null);
  }, []);

  /**
   * Runs the marketplace search: POSTs form data to the stream endpoint, reads the SSE response,
   * and updates state from events. Uses a ref to block duplicate submissions while a search is in progress.
   * Form data is passed in as an argument to avoid the callback depending on form state and recreating on every keystroke.
   */
  const performSearch = useCallback(async (formData: ValidationFormData) => {
    if (isSearchingRef.current) {
      return;
    }

    isSearchingRef.current = true;
    setIsSearching(true);
    
    // Create new AbortController for this search
    abortControllerRef.current = new AbortController();
    const abortSignal = abortControllerRef.current.signal;
    
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
          radius: Number(formData.radius),
          threshold: formData.threshold,
          maxListings: formData.maxListings,
          extractDescriptions: formData.extractDescriptions,
        }),
        signal: abortSignal,
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("No response body");
      }

      // Store reader reference for cancellation
      readerRef.current = reader;

      await parseSSEStream(reader);
    } catch (err) {
      // Don't show error if search was cancelled
      if (err instanceof Error && err.name === "AbortError") {
        console.log("Search cancelled by user");
        return;
      }
      
      console.error("Search error:", err);
      
      // Provide more helpful error messages
      let errorMessage = "Failed to search marketplace";
      if (err instanceof TypeError && err.message === "Failed to fetch") {
        errorMessage = `Cannot connect to API server at ${API_URL}. Please ensure the backend server is running on port 8000.`;
      } else if (err instanceof Error) {
        errorMessage = err.message;
      }
      
      setError(errorMessage);
      setAppState("error");
    } finally {
      isSearchingRef.current = false;
      setIsSearching(false);
      abortControllerRef.current = null;
      readerRef.current = null;
    }
  }, [parseSSEStream]);

  /**
   * Handles form submission by resetting all state to initial values and starting the search.
   * Called by react-hook-form after validation passes. Clears previous results and immediately
   * starts the search by calling performSearch directly, avoiding the useEffect dependency chain
   * that was causing duplicate requests.
   */
  const onSubmit = (data: ValidationFormData) => {
    if (isSearchingRef.current) {
      console.log("⚠️ onSubmit: Search already in progress, preventing duplicate submission");
      return;
    }
    
    console.log("✅ onSubmit: Form submitted, starting search");
    
    // Reset all state — clean slate for the new search
    setScannedCount(0);
    setFilteredCount(0);
    setEvaluatedCount(0);
    setMaxListings(Number(data.maxListings) || 20);
    setCsvBlob(null);
    setListings([]);
    setError(null);
    setPhase("scraping");
    setThreshold(Number(data.threshold) || 0);
    setDebugSearchParams(null);
    setDebugFacebookListings([]);
    setDebugEbayQueries([]);
    setDebugLogs([]);
    setAppState("loading");
    
    // Start search directly — backend handles killing any previous search before starting
    performSearch(data);
  };

  const handleSubmit = handleFormSubmit(onSubmit);

  /**
   * Resets the application state back to the form view.
   * Clears all search results, counts, and error state to allow a new search.
   */
  const handleReset = () => {
    setAppState("form");
    setScannedCount(0);
    setFilteredCount(0);
    setEvaluatedCount(0);
    setCsvBlob(null);
    setListings([]);
    setError(null);
    setDebugEnabled(false);
    setDebugSearchParams(null);
    setDebugFacebookListings([]);
    setDebugEbayQueries([]);
    setDebugLogs([]);
    isSearchingRef.current = false;
    setIsSearching(false);
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
            {appState === "setup" && cookiesChecked && (
              <CookieSetupGuide
                onSuccess={() => { setError(null); setAppState("form"); }}
                sessionExpiredMessage={error}
              />
            )}

            {appState === "form" && (
              <>
                <MarketplaceSearchForm
                  register={register}
                  errors={errors}
                  isValid={isValid}
                  handleSubmit={handleSubmit}
                  watch={watch}
                  setValue={setValue}
                />
                <div className="mt-4 flex justify-center">
                  <button
                    type="button"
                    onClick={() => setAppState("setup")}
                    className="border border-muted-foreground/30 px-2 py-1 font-mono text-[10px] text-muted-foreground transition-colors hover:border-muted-foreground/50 hover:text-foreground cursor-pointer"
                  >
                    Reconnect Facebook account
                  </button>
                </div>
              </>
            )}

            {appState === "loading" && (
              <div className="space-y-6">
                <SearchLoadingState
                  phase={phase}
                  scannedCount={scannedCount}
                  filteredCount={filteredCount}
                  evaluatedCount={evaluatedCount}
                  maxListings={maxListings}
                  onCancel={cancelSearch}
                />
                {phase === "evaluating" && listings.length > 0 && (
                  <SearchResultsTable
                    listings={listings}
                    scannedCount={scannedCount}
                    suspiciousFilteredCount={filteredCount}
                    threshold={threshold}
                    onDownloadCSV={downloadCSV}
                    onReset={handleReset}
                    isLoading={true}
                  />
                )}
              </div>
            )}

            {appState === "done" && (
              <SearchResultsTable
                listings={listings}
                scannedCount={scannedCount}
                suspiciousFilteredCount={filteredCount}
                threshold={threshold}
                onDownloadCSV={downloadCSV}
                onReset={handleReset}
              />
            )}

            {appState === "error" && (
              <SearchErrorState error={error} onReset={handleReset} />
            )}
          </div>
        </div>

        {debugEnabled && (appState === "loading" || appState === "done") && (
          <DebugPanel
            searchParams={debugSearchParams}
            facebookListings={debugFacebookListings}
            ebayQueries={debugEbayQueries}
          />
        )}

        <FloatingLogPanel logs={debugLogs} debugEnabled={debugEnabled} />

        <AppFooter />
      </div>
    </main>
  );
}

