"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { formSchema, type FormData as ValidationFormData, DEFAULT_RADIUS } from "@/lib/validation";
import { AppHeader } from "@/components/layout/AppHeader";
import { RedCloseButton } from "@/components/easter-eggs/red-close/RedCloseButton";
import { AppFooter } from "@/components/layout/AppFooter";
import { MarketplaceSearchForm } from "@/components/search-form/MarketplaceSearchForm";
import type { SearchPhase } from "@/components/loading/SearchLoadingState";
import { SearchErrorState } from "@/components/results/SearchErrorState";
import { SearchLoadingView } from "@/components/results/SearchLoadingView";
import { SearchResultsView } from "@/components/results/SearchResultsView";
import { CookieSetupGuide } from "@/components/auth/CookieSetupGuide";
import type { Listing } from "@/components/results/ResultsTable";
import { FloatingLogPanel } from "@/components/debug/FloatingLogPanel";
import type { DebugFacebookListing, DebugEbayQueryEntry, DebugLogEntry } from "@/components/debug/DebugPanel";
import type { DebugSearchParams } from "@/components/debug/DebugSearchParams";

type AppState = "setup" | "form" | "loading" | "done" | "error";

const DEFAULT_THRESHOLD = 20;
const DEFAULT_MAX_LISTINGS = 20;

function buildSearchParamsFromFormData(data: ValidationFormData): DebugSearchParams {
  return {
    query: data.query,
    zipCode: data.zipCode,
    radius: Number(data.radius),
    maxListings: Number(data.maxListings) || DEFAULT_MAX_LISTINGS,
    threshold: Number(data.threshold) || DEFAULT_THRESHOLD,
    extractDescriptions: data.extractDescriptions ?? false,
  };
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const DEBUG_LOGS_STORAGE_KEY = "fb_marketplace_debug_logs";
const DEBUG_MODE_ENABLED_KEY = "fb_marketplace_debug_mode_enabled";
/** Length of the horizontal separator (dash) line between log steps. Must match backend (SEP_LINE_LEN) for consistent display. */
const STEP_LOG_SEP_LEN = 76;

function loadDebugLogsFromStorage(): DebugLogEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const stored = localStorage.getItem(DEBUG_LOGS_STORAGE_KEY);
    if (!stored) return [];
    return JSON.parse(stored) as DebugLogEntry[];
  } catch {
    return [];
  }
}

function saveDebugLogsToStorage(logs: DebugLogEntry[]): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(DEBUG_LOGS_STORAGE_KEY, JSON.stringify(logs));
  } catch {
    // Storage may be disabled or quota exceeded; continue without persistence
  }
}

function setDebugModeEnabledInStorage(enabled: boolean): void {
  if (typeof window === "undefined") return;
  try {
    if (enabled) {
      localStorage.setItem(DEBUG_MODE_ENABLED_KEY, "true");
    } else {
      localStorage.removeItem(DEBUG_MODE_ENABLED_KEY);
    }
  } catch {
    // Storage may be disabled or quota exceeded; continue without persistence
  }
}

function isDebugModeEnabledInStorage(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return localStorage.getItem(DEBUG_MODE_ENABLED_KEY) === "true";
  } catch {
    return false;
  }
}

/**
 * Opens a URL in a new background tab without stealing focus from the current tab.
 * Simulates a Cmd+Click (macOS) / Ctrl+Click (Windows/Linux) which browsers
 * handle by opening the link in the background.
 */
function openBackgroundTab(url: string): void {
  const a = document.createElement("a");
  a.href = url;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  document.body.appendChild(a);
  a.dispatchEvent(
    new MouseEvent("click", {
      bubbles: true,
      cancelable: true,
      view: window,
      metaKey: true,
      ctrlKey: true,
    })
  );
  document.body.removeChild(a);
}

type CancelSearchOptions = {
  cancelBackend?: boolean;
  clearError?: boolean;
  addCancelLog?: boolean;
};

type SSEDispatchHandlers = {
  handlePhaseUpdate: (phase: SearchPhase) => void;
  handleProgressUpdate: (scannedCount: number) => void;
  handleCompletion: (data: { scannedCount: number; filteredCount?: number; filteredOutListings?: DebugFacebookListing[]; evaluatedCount: number; listings: Listing[]; threshold?: number; averageConfidence?: number | null }) => void;
  handleAuthError: () => void;
  handleLocationError: (message: string) => void;
  setEvaluatedCount: (n: number) => void;
  onCurrentItem?: (entry: { listingIndex: number; fbTitle: string; totalListings: number }) => void;
  onListingResult?: (listing: Listing, evaluatedCount: number, fbListingId?: string) => void;
  onFilteredFacebookListing?: (listing: DebugFacebookListing) => void;
  onDebugMode?: (logsEnabled?: boolean) => void;
  onDebugFacebook?: (listings: DebugFacebookListing[]) => void;
  onDebugFacebookListing?: (listing: DebugFacebookListing) => void;
  onDebugEbayQueryStart?: (entry: { fbListingId: string; listingIndex: number; fbTitle: string }) => void;
  onDebugEbayQueryGenerated?: (entry: DebugEbayQueryEntry) => void;
  onDebugEbayQueryFinished?: (entry: { fbListingId: string; listingIndex: number; failed?: boolean }) => void;
  onDebugProductRecon?: (entry: {
    fbListingId: string;
    listingIndex: number;
    recon: NonNullable<DebugEbayQueryEntry["productRecon"]>;
  }) => void;
  onDebugLog?: (entry: DebugLogEntry) => void;
  onInspectorUrl?: (url: string, source?: string) => void;
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
    filteredOutListings?: DebugFacebookListing[];
    evaluatedCount?: number;
    listing?: Listing;
    fbListingId?: string;
    listingIndex?: number;
    listings?: Listing[] | DebugFacebookListing[];
    threshold?: number;
    averageConfidence?: number | null;
    debug?: boolean;
    logsEnabled?: boolean;
    query?: string;
    zipCode?: string;
    radius?: number;
    maxListings?: number;
    extractDescriptions?: boolean;
    fbTitle?: string;
    totalListings?: number;
    ebayQuery?: string;
    failed?: boolean;
    level?: string;
    message?: string;
    url?: string;
    source?: string;
    recon?: Record<string, unknown>;
    citations?: { url: string; title?: string }[];
  };
  if (data.type === "auth_error") {
    handlers.handleAuthError();
  } else if (data.type === "location_error") {
    handlers.handleLocationError(data.message || "Location not found");
  } else if (data.type === "phase" && data.phase != null) {
    handlers.handlePhaseUpdate(data.phase);
  } else if (data.type === "filtered_facebook_listing" && data.listing) {
    handlers.onFilteredFacebookListing?.(data.listing as DebugFacebookListing);
  } else if (data.type === "progress" && typeof data.scannedCount === "number") {
    handlers.handleProgressUpdate(data.scannedCount);
  } else if (
    data.type === "current_item"
    && typeof data.listingIndex === "number"
    && typeof data.fbTitle === "string"
    && typeof data.totalListings === "number"
  ) {
    handlers.onCurrentItem?.({
      listingIndex: data.listingIndex,
      fbTitle: data.fbTitle,
      totalListings: data.totalListings,
    });
  } else if (data.type === "listing_result" && data.listing != null && typeof data.evaluatedCount === "number") {
    handlers.onListingResult?.(data.listing, data.evaluatedCount, data.fbListingId);
  } else if (data.type === "listing_processed" && typeof data.evaluatedCount === "number") {
    handlers.setEvaluatedCount(data.evaluatedCount);
  } else if (data.type === "done" && data.listings != null && Array.isArray(data.listings)) {
    handlers.handleCompletion({
      scannedCount: data.scannedCount ?? 0,
      filteredCount: data.filteredCount ?? 0,
      filteredOutListings: (data.filteredOutListings ?? []) as DebugFacebookListing[],
      evaluatedCount: data.evaluatedCount ?? 0,
      listings: data.listings as Listing[],
      threshold: data.threshold,
    });
  } else if (data.type === "debug_mode" && data.debug) {
    handlers.onDebugMode?.(data.logsEnabled);
  } else if (data.type === "debug_facebook" && Array.isArray(data.listings)) {
    handlers.onDebugFacebook?.(data.listings as DebugFacebookListing[]);
  } else if (data.type === "debug_facebook_listing" && data.listing) {
    handlers.onDebugFacebookListing?.(data.listing as DebugFacebookListing);
  } else if (
    data.type === "debug_ebay_query_start"
    && data.fbTitle != null
    && typeof data.listingIndex === "number"
    && typeof data.fbListingId === "string"
  ) {
    handlers.onDebugEbayQueryStart?.({
      fbListingId: data.fbListingId,
      listingIndex: data.listingIndex,
      fbTitle: data.fbTitle,
    });
  } else if (
    (data.type === "debug_ebay_query_generated" || data.type === "debug_ebay_query")
    && data.fbTitle != null
    && data.ebayQuery != null
  ) {
    if (typeof data.listingIndex === "number" && typeof data.fbListingId === "string") {
      handlers.onDebugEbayQueryGenerated?.({
        fbListingId: data.fbListingId,
        listingIndex: data.listingIndex,
        fbTitle: data.fbTitle,
        ebayQuery: data.ebayQuery,
        startedAtMs: Date.now(),
      });
    }
  } else if (
    data.type === "debug_ebay_query_finished"
    && typeof data.listingIndex === "number"
    && typeof data.fbListingId === "string"
  ) {
    handlers.onDebugEbayQueryFinished?.({
      fbListingId: data.fbListingId,
      listingIndex: data.listingIndex,
      failed: data.failed,
    });
  } else if (
    data.type === "debug_product_recon"
    && typeof data.listingIndex === "number"
    && typeof data.fbListingId === "string"
    && data.recon != null
  ) {
    handlers.onDebugProductRecon?.({
      fbListingId: data.fbListingId,
      listingIndex: data.listingIndex,
      recon: {
        canonical_name: String((data.recon as any).canonical_name ?? ""),
        brand: String((data.recon as any).brand ?? ""),
        category: String((data.recon as any).category ?? ""),
        model_or_series: String((data.recon as any).model_or_series ?? ""),
        year_or_generation: String((data.recon as any).year_or_generation ?? ""),
        variant_dimensions: Array.isArray((data.recon as any).variant_dimensions)
          ? ((data.recon as any).variant_dimensions as any[]).map((v) => String(v))
          : [],
        notes: String((data.recon as any).notes ?? ""),
        citations: Array.isArray(data.citations) ? data.citations : [],
      },
    });
  } else if (data.type === "debug_log" && data.level != null && data.message != null) {
    handlers.onDebugLog?.({ level: data.level, message: data.message, timestampMs: Date.now() });
  } else if (data.type === "inspector_url" && typeof data.url === "string") {
    handlers.onInspectorUrl?.(data.url, data.source as string | undefined);
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
  const [currentItem, setCurrentItem] = useState<{ listingIndex: number; fbTitle: string; totalListings: number } | null>(null);
  const [csvBlob, setCsvBlob] = useState<Blob | null>(null);
  const [listings, setListings] = useState<Listing[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [phase, setPhase] = useState<SearchPhase>("scraping");
  const [threshold, setThreshold] = useState<number>(0);
  const [debugFacebookListings, setDebugFacebookListings] = useState<DebugFacebookListing[]>([]);
  const [filteredOutListings, setFilteredOutListings] = useState<DebugFacebookListing[]>([]);
  const [debugEbayQueries, setDebugEbayQueries] = useState<DebugEbayQueryEntry[]>([]);
  const [debugLogs, setDebugLogs] = useState<DebugLogEntry[]>(() => loadDebugLogsFromStorage());
  const [debugModeEnabled, setDebugModeEnabledState] = useState<boolean>(() => isDebugModeEnabledInStorage());
  const [isSearching, setIsSearching] = useState<boolean>(false);
  const isSearchingRef = useRef<boolean>(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const readerRef = useRef<ReadableStreamDefaultReader<Uint8Array> | null>(null);

  /**
   * Persists debug logs to localStorage whenever they change.
   */
  useEffect(() => {
    saveDebugLogsToStorage(debugLogs);
  }, [debugLogs]);

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
   * Updates the currently processing item from an SSE current_item event.
   */
  const handleCurrentItem = useCallback((entry: { listingIndex: number; fbTitle: string; totalListings: number }) => {
    setCurrentItem(entry);
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
    setFilteredOutListings([]);
    setEvaluatedCount(0);
    setPhase("scraping");
    setCurrentItem(null);
    setError("Your Facebook session has expired. Please re-connect your account to keep searching.");
    setAppState("setup");
  }, []);

  /**
   * Cancels the current search by canceling the stream reader and aborting the fetch request.
   * Resets state and returns the app to the form view.
   */
  const cancelSearch = useCallback(async (options: CancelSearchOptions = {}) => {
    const { cancelBackend = true, clearError = true, addCancelLog = true } = options;

    // Tell the backend to cancel immediately (kills Chrome, stops scraping)
    // Await so cleanup starts before we allow a new search.
    if (cancelBackend) {
      try {
        await fetch(`${API_URL}/api/search/cancel`, { method: "POST" });
      } catch {
        // Backend may already be down, continue with local cleanup
      }
    }

    // Add log entry for cancellation if requested
    if (addCancelLog && debugModeEnabled) {
      setDebugLogs((prev: DebugLogEntry[]) => [
        ...prev,
        { level: "WARNING", message: "Search cancelled by user", timestampMs: Date.now() },
      ]);
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
    
    
    isSearchingRef.current = false;
    setIsSearching(false);
    setAppState("form");
    setScannedCount(0);
    setFilteredCount(0);
    setFilteredOutListings([]);
    setEvaluatedCount(0);
    setPhase("scraping");
    setCurrentItem(null);
    if (clearError) {
      setError(null);
    }
  }, [debugModeEnabled]);

  const handleLocationError = useCallback((message: string) => {
    // Reset search state immediately
    isSearchingRef.current = false;
    setIsSearching(false);
    setScannedCount(0);
    setFilteredCount(0);
    setEvaluatedCount(0);
    setPhase("scraping");
    setCurrentItem(null);
    setAppState("form");
    setError(message);
    // The backend already reported a terminal location error, so only cancel local stream.
    void cancelSearch({ cancelBackend: false, clearError: false, addCancelLog: false });
  }, [cancelSearch]);

  /**
   * Applies the final search result: sets listings, counts, threshold, generates CSV blob,
   * and switches the app to the done state so the results table is shown.
   */
  const handleCompletion = useCallback((data: { scannedCount: number; filteredCount?: number; filteredOutListings?: DebugFacebookListing[]; evaluatedCount: number; listings: Listing[]; threshold?: number }) => {
    setScannedCount(data.scannedCount);
    setFilteredCount(data.filteredCount ?? 0);
    setFilteredOutListings(data.filteredOutListings ?? []);
    setEvaluatedCount(data.evaluatedCount);
    setListings(data.listings);
    setThreshold(data.threshold || 0);

    const blob = generateCSV(data.listings);
    setCsvBlob(blob);

    setAppState("done");
  }, [generateCSV]);

  const onDebugEbayQueryStart = useCallback((entry: { fbListingId: string; listingIndex: number; fbTitle: string }) => {
    setDebugEbayQueries((prev: DebugEbayQueryEntry[]) => {
      const existing = prev.find((item) => item.fbListingId === entry.fbListingId);
      if (existing) return prev;
      return [
        ...prev,
        {
          fbListingId: entry.fbListingId,
          listingIndex: entry.listingIndex,
          fbTitle: entry.fbTitle,
          startedAtMs: Date.now(),
        },
      ];
    });
  }, []);

  const onDebugEbayQueryGenerated = useCallback((entry: DebugEbayQueryEntry) => {
    setDebugEbayQueries((prev: DebugEbayQueryEntry[]) => {
      const existing = prev.find((item) => item.fbListingId === entry.fbListingId);
      if (!existing) {
        return [
          ...prev,
          {
            fbListingId: entry.fbListingId,
            listingIndex: entry.listingIndex,
            fbTitle: entry.fbTitle,
            startedAtMs: Date.now(),
            ebayQuery: entry.ebayQuery,
            queryGeneratedAtMs: Date.now(),
            failed: false,
          },
        ];
      }
      return prev.map((item) =>
        item.fbListingId === entry.fbListingId
          ? {
              ...item,
              ebayQuery: entry.ebayQuery,
              queryGeneratedAtMs: item.queryGeneratedAtMs ?? Date.now(),
              failed: false,
            }
          : item
      );
    });
  }, []);

  const onDebugEbayQueryFinished = useCallback((entry: { fbListingId: string; listingIndex: number; failed?: boolean }) => {
    setDebugEbayQueries((prev: DebugEbayQueryEntry[]) =>
      prev.map((item) =>
        item.fbListingId === entry.fbListingId
          ? {
              ...item,
              finishedAtMs: item.finishedAtMs ?? Date.now(),
              failed: entry.failed ?? false,
            }
          : item
      )
    );
  }, []);

  const onDebugProductRecon = useCallback((entry: { fbListingId: string; listingIndex: number; recon: NonNullable<DebugEbayQueryEntry["productRecon"]> }) => {
    setDebugEbayQueries((prev: DebugEbayQueryEntry[]) => {
      const existing = prev.find((item) => item.fbListingId === entry.fbListingId);
      if (!existing) {
        return [
          ...prev,
          {
            fbListingId: entry.fbListingId,
            listingIndex: entry.listingIndex,
            fbTitle: "",
            startedAtMs: Date.now(),
            productRecon: entry.recon,
            failed: false,
          },
        ];
      }
      return prev.map((item) =>
        item.fbListingId === entry.fbListingId
          ? {
              ...item,
              productRecon: entry.recon,
            }
          : item
      );
    });
  }, []);

  /**
   * Handles a single listing result from the backend as it's processed.
   * Appends the listing to the results array for incremental display.
   */
  const onListingResult = useCallback((listing: Listing, evaluatedCount: number, fbListingId?: string) => {
    setListings((prev: Listing[]) => [...prev, listing]);
    setEvaluatedCount(evaluatedCount);
    if (fbListingId != null && listing.noCompReason) {
      setDebugEbayQueries((prev: DebugEbayQueryEntry[]) =>
        prev.map((item) =>
          item.fbListingId === fbListingId
            ? {
                ...item,
                noCompReason: listing.noCompReason,
                finishedAtMs: item.finishedAtMs ?? Date.now(),
              }
            : item
        )
      );
    }
  }, []);

  const onFilteredFacebookListing = useCallback((listing: DebugFacebookListing) => {
    setFilteredOutListings((prev: DebugFacebookListing[]) => [...prev, listing]);
  }, []);

  /**
   * Parses an SSE stream from the reader and updates UI from each event.
   * Reads in chunks and accumulates text in a buffer so only complete lines (ending with \n)
   * are parsed. This avoids "Unterminated string" when the large "done" payload is split across
   * TCP chunks. Uses stream: true for decode so multi-byte UTF-8 spanning chunks is handled.
   * Event types: "phase", "progress", "listing_processed", "done", and when backend runs with
   * --debug: "debug_mode", "debug_facebook", "debug_ebay_query_start",
   * "debug_ebay_query_generated", and "debug_ebay_query_finished". Handles cancellation
   * gracefully.
   */
  const parseSSEStream = useCallback(
    async (reader: ReadableStreamDefaultReader<Uint8Array>) => {
      const decoder = new TextDecoder();
      let buffer = "";

      const sseHandlers: SSEDispatchHandlers = {
        handlePhaseUpdate,
        handleProgressUpdate,
        handleCompletion,
        handleAuthError,
        handleLocationError,
        setEvaluatedCount,
        onCurrentItem: handleCurrentItem,
        onListingResult,
        onFilteredFacebookListing,
        onDebugMode: (logsEnabled) => {
          const showLogs = Boolean(logsEnabled);
          setDebugModeEnabledInStorage(showLogs);
          setDebugModeEnabledState(showLogs);
        },
        onDebugFacebook: setDebugFacebookListings,
        onDebugFacebookListing: (listing: DebugFacebookListing) =>
          setDebugFacebookListings((prev: DebugFacebookListing[]) => [...prev, listing]),
        onDebugEbayQueryStart: onDebugEbayQueryStart,
        onDebugEbayQueryGenerated: onDebugEbayQueryGenerated,
        onDebugEbayQueryFinished: onDebugEbayQueryFinished,
        onDebugProductRecon: onDebugProductRecon,
        onDebugLog: (entry) => setDebugLogs((prev: DebugLogEntry[]) => [...prev, entry]),
        onInspectorUrl: openBackgroundTab,
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
    [handlePhaseUpdate, handleProgressUpdate, handleCompletion, handleAuthError, handleLocationError, handleCurrentItem, onListingResult, onFilteredFacebookListing, onDebugEbayQueryStart, onDebugEbayQueryGenerated, onDebugEbayQueryFinished, onDebugProductRecon]
  );

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
      return;
    }
    
    // Reset all state — clean slate for the new search
    setScannedCount(0);
    setFilteredCount(0);
    setFilteredOutListings([]);
    setEvaluatedCount(0);
    setMaxListings(Number(data.maxListings) || 20);
    setCsvBlob(null);
    setListings([]);
    setError(null);
    setPhase("scraping");
    setCurrentItem(null);
    setThreshold(Number(data.threshold) || 0);
    setDebugFacebookListings([]);
    setDebugEbayQueries([]);
    const timestampMs = Date.now();
    const step1Msg = `🔍 Step 1: Starting search — query='${data.query}', location=${data.zipCode}, radius=${data.radius}mi`;
    const sep = "─".repeat(STEP_LOG_SEP_LEN);
    setDebugLogs([
      { level: "INFO", message: sep, timestampMs },
      { level: "INFO", message: step1Msg, timestampMs },
      { level: "INFO", message: sep, timestampMs },
    ]);
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
    setFilteredOutListings([]);
    setEvaluatedCount(0);
    setCsvBlob(null);
    setListings([]);
    setError(null);
    setCurrentItem(null);
    setDebugFacebookListings([]);
    setDebugEbayQueries([]);
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
            <RedCloseButton />
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
                {error && (
                  <div className="mb-4 rounded border-2 border-destructive bg-destructive/10 px-4 py-3">
                    <p className="font-mono text-sm text-destructive">{error}</p>
                  </div>
                )}
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
              <SearchLoadingView
                listings={listings}
                threshold={threshold}
                filteredOutListings={filteredOutListings}
                currentItem={currentItem}
                facebookListings={debugFacebookListings}
                ebayQueries={debugEbayQueries}
                searchParams={buildSearchParamsFromFormData(formData)}
                onCancel={cancelSearch}
              />
            )}

            {appState === "done" && (
              <SearchResultsView
                listings={listings}
                scannedCount={scannedCount}
                threshold={threshold}
                filteredOutListings={filteredOutListings}
                searchParams={buildSearchParamsFromFormData(formData)}
                onDownloadCSV={downloadCSV}
                onReset={handleReset}
              />
            )}

            {appState === "error" && (
              <SearchErrorState error={error} onReset={handleReset} />
            )}
          </div>
        </div>

        {debugModeEnabled && (
          <FloatingLogPanel logs={debugLogs} debugEnabled={true} />
        )}

        <AppFooter />
      </div>
    </main>
  );
}

