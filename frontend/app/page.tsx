"use client";

import React from "react"

import { useState, useEffect, useCallback, useRef } from "react";

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

type JobInfo = {
  id: string;
  query: string;
  zipCode: string;
  status: string;
  queuePosition?: number;
  results?: Listing[];
  dismissed?: boolean;
};

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
  const [phase, setPhase] = useState<string>("scraping");
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);
  const currentJobIdRef = useRef<string | null>(null);
  const [queueStatus, setQueueStatus] = useState<{queueSize: number; maxQueueSize: number; activeJobs: number} | null>(null);
  const [jobs, setJobs] = useState<Map<string, JobInfo>>(new Map());

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

  const fetchQueueStatus = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/queue/status`);
      if (!response.ok) {
        console.error(`Failed to fetch queue status: ${response.status} ${response.statusText}`);
        return;
      }
      const data = await response.json();
      if (data && typeof data === 'object' && 'queueSize' in data) {
        setQueueStatus(data);
      } else {
        console.error("Invalid queue status response:", data);
      }
    } catch (err) {
      console.error("Failed to fetch queue status:", err);
    }
  }, []);

  const loadJobs = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/jobs?include_dismissed=false`);
      if (response.ok) {
        const data = await response.json();
        const jobsMap = new Map();
        data.jobs.forEach((job: any) => {
          jobsMap.set(job.jobId, {
            id: job.jobId,
            query: job.query,
            zipCode: job.zipCode,
            status: job.status,
            results: job.results || [],
            dismissed: job.dismissed
          });
        });
        setJobs(jobsMap);
      }
    } catch (err) {
      console.error("Failed to load jobs:", err);
    }
  }, []);

  const dismissJob = useCallback(async (jobId: string) => {
    try {
      const response = await fetch(`${API_URL}/api/jobs/${jobId}/dismiss`, {
        method: "POST"
      });
      if (response.ok) {
        setJobs((prev: Map<string, JobInfo>) => {
          const newJobs = new Map(prev);
          const job = newJobs.get(jobId);
          if (job) {
            newJobs.set(jobId, { ...job, dismissed: true });
          }
          return newJobs;
        });
        // Reload jobs to get updated list
        loadJobs();
      }
    } catch (err) {
      console.error("Failed to dismiss job:", err);
    }
  }, [loadJobs]);

  const deleteJob = useCallback(async (jobId: string) => {
    try {
      const response = await fetch(`${API_URL}/api/jobs/${jobId}`, {
        method: "DELETE"
      });
      if (response.ok) {
        setJobs((prev: Map<string, JobInfo>) => {
          const newJobs = new Map(prev);
          newJobs.delete(jobId);
          return newJobs;
        });
        // Reload jobs to get updated list
        loadJobs();
      }
    } catch (err) {
      console.error("Failed to delete job:", err);
    }
  }, [loadJobs]);

  useEffect(() => {
    if (appState !== "loading") return;

    const searchAPI = async () => {
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

        // Read the SSE stream
        const reader = response.body?.getReader();
        const decoder = new TextDecoder();

        if (!reader) {
          throw new Error("No response body");
        }

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const text = decoder.decode(value);
          const lines = text.split("\n");

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const data = JSON.parse(line.slice(6));

              if (data.type === "queued") {
                const jobId = data.jobId;
                setCurrentJobId(jobId);
                currentJobIdRef.current = jobId;
                setJobs((prev: Map<string, JobInfo>) => {
                  const newJobs = new Map(prev);
                  newJobs.set(jobId, {
                    id: jobId,
                    query: formData.query,
                    zipCode: formData.zipCode,
                    status: "pending",
                    queuePosition: data.queuePosition
                  });
                  return newJobs;
                });
                fetchQueueStatus();
              } else if (data.type === "waiting") {
                const jobId = currentJobIdRef.current;
                if (jobId) {
                  setJobs((prev: Map<string, JobInfo>) => {
                    const newJobs = new Map(prev);
                    const job = newJobs.get(jobId);
                    if (job) {
                      newJobs.set(jobId, { ...job, queuePosition: data.queuePosition });
                    }
                    return newJobs;
                  });
                }
                fetchQueueStatus();
              } else if (data.type === "phase") {
                setPhase(data.phase);
                const jobId = currentJobIdRef.current;
                if (jobId) {
                  setJobs((prev: Map<string, JobInfo>) => {
                    const newJobs = new Map(prev);
                    const job = newJobs.get(jobId);
                    if (job) {
                      newJobs.set(jobId, { ...job, status: "processing" });
                    }
                    return newJobs;
                  });
                }
              } else if (data.type === "progress") {
                setScannedCount(data.scannedCount);
              } else if (data.type === "done") {
                setScannedCount(data.scannedCount);
                setEvaluatedCount(data.evaluatedCount);
                setListings(data.listings);

                const blob = generateCSV(data.listings);
                setCsvBlob(blob);

                const jobId = currentJobIdRef.current;
                if (jobId) {
                  setJobs((prev: Map<string, JobInfo>) => {
                    const newJobs = new Map(prev);
                    const job = newJobs.get(jobId);
                    if (job) {
                      newJobs.set(jobId, {
                        ...job,
                        status: "completed",
                        results: data.listings
                      });
                    }
                    return newJobs;
                  });
                }

                setAppState("done");
                fetchQueueStatus();
              } else if (data.type === "error") {
                setError(data.message);
                const jobId = currentJobIdRef.current;
                if (jobId) {
                  setJobs((prev: Map<string, JobInfo>) => {
                    const newJobs = new Map(prev);
                    const job = newJobs.get(jobId);
                    if (job) {
                      newJobs.set(jobId, { ...job, status: "failed" });
                    }
                    return newJobs;
                  });
                }
                setAppState("error");
                fetchQueueStatus();
              }
            }
          }
        }
      } catch (err) {
        console.error("Search error:", err);
        setError(err instanceof Error ? err.message : "Failed to search marketplace");
        setAppState("error");
      }
    };

    searchAPI();
  }, [appState, formData, generateCSV, fetchQueueStatus]);

  // Load jobs from database on mount
  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  // Poll queue status periodically when there are active jobs
  useEffect(() => {
    if (jobs.size > 0 || (queueStatus && queueStatus.queueSize > 0)) {
      const interval = setInterval(() => {
        fetchQueueStatus();
        loadJobs(); // Also refresh jobs list
      }, 2000); // Poll every 2 seconds
      return () => clearInterval(interval);
    }
  }, [jobs.size, queueStatus, fetchQueueStatus, loadJobs]);

  // Removed auto-download - now showing results in UI instead

  const handleBeginHeist = async (e: React.FormEvent) => {
    e.preventDefault();
    setScannedCount(0);
    setEvaluatedCount(0);
    setCsvBlob(null);
    setListings([]);
    setError(null);
    setPhase("scraping");
    setAppState("loading");
    // The streaming logic in useEffect will handle the rest
  };

  const handleAddToQueue = async (e: React.FormEvent) => {
    e.preventDefault();
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

      // Read just the initial queued event to get job ID
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error("No response body");
      }

      // Read first event to get job ID, then close the stream
      const { done, value } = await reader.read();
      if (!done && value) {
        const text = decoder.decode(value);
        const lines = text.split("\n");
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = JSON.parse(line.slice(6));
            if (data.type === "queued") {
              const jobId = data.jobId;
              setJobs((prev: Map<string, JobInfo>) => {
                const newJobs = new Map(prev);
                newJobs.set(jobId, {
                  id: jobId,
                  query: formData.query,
                  zipCode: formData.zipCode,
                  status: "pending",
                  queuePosition: data.queuePosition
                });
                return newJobs;
              });
              fetchQueueStatus();
              // Close the reader - we don't need to stream for queue mode
              reader.cancel();
              break;
            }
          }
        }
      }
    } catch (err) {
      console.error("Failed to add job to queue:", err);
      setError(err instanceof Error ? err.message : "Failed to add job to queue");
    }
  };

  const handleReset = () => {
    setAppState("form");
    setScannedCount(0);
    setEvaluatedCount(0);
    setCsvBlob(null);
    setListings([]);
    setError(null);
    setCurrentJobId(null);
    setPhase("scraping");
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

        {/* Queue Display */}
        {Array.from(jobs.values()).some(job => !job.dismissed) || (queueStatus && queueStatus.queueSize > 0) ? (
          <div className="mb-6 border-2 border-border bg-card p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="font-mono text-sm font-bold text-foreground">
                <span className="text-primary">{">"}</span> HEIST QUEUE
              </h2>
              {queueStatus && (
                <span className="font-mono text-xs text-muted-foreground">
                  {queueStatus.queueSize}/{queueStatus.maxQueueSize} queued
                </span>
              )}
            </div>
            <div className="space-y-4">
              {Array.from(jobs.values())
                .filter((job): job is JobInfo => !job.dismissed)
                .map((job: JobInfo) => (
                <div key={job.id} className="space-y-2">
                  <div
                    className={`flex items-center justify-between border px-3 py-2 font-mono text-xs ${
                      job.status === "processing"
                        ? "border-primary bg-primary/10"
                        : job.status === "completed"
                        ? "border-green-500/50 bg-green-500/5"
                        : job.status === "failed"
                        ? "border-destructive/50 bg-destructive/5"
                        : "border-border bg-secondary"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-muted-foreground">
                        {job.status === "processing" && "⚡"}
                        {job.status === "pending" && "⏳"}
                        {job.status === "completed" && "✓"}
                        {job.status === "failed" && "✗"}
                      </span>
                      <span className="text-foreground">
                        {job.query} @ {job.zipCode}
                        {job.status === "completed" && job.results && (
                          <span className="ml-2 text-muted-foreground">
                            ({job.results.length} results)
                          </span>
                        )}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      {job.queuePosition && job.status === "pending" && (
                        <span className="text-muted-foreground">#{job.queuePosition}</span>
                      )}
                      {job.status === "completed" && (
                        <button
                          onClick={() => deleteJob(job.id)}
                          className="border border-border bg-secondary px-2 py-1 text-xs uppercase text-muted-foreground transition-all hover:bg-destructive/10 hover:text-destructive"
                        >
                          Delete
                        </button>
                      )}
                      <span
                        className={`uppercase ${
                          job.status === "processing"
                            ? "text-primary font-bold"
                            : job.status === "completed"
                            ? "text-green-500"
                            : job.status === "failed"
                            ? "text-destructive"
                            : "text-muted-foreground"
                        }`}
                      >
                        {job.status}
                      </span>
                    </div>
                  </div>
                  {/* Show results for completed jobs */}
                  {job.status === "completed" && job.results && job.results.length > 0 && (
                    <div className="ml-4 border-l-2 border-green-500/30 pl-4">
                      <div className="max-h-[40vh] overflow-auto border border-border bg-secondary">
                        <table className="w-full border-collapse font-mono text-xs">
                          <thead className="sticky top-0 bg-secondary">
                            <tr className="border-b border-border text-left">
                              <th className="px-2 py-1 text-muted-foreground">TITLE</th>
                              <th className="px-2 py-1 text-muted-foreground">PRICE</th>
                              <th className="px-2 py-1 text-muted-foreground">LOCATION</th>
                              <th className="px-2 py-1 text-muted-foreground">DEAL %</th>
                              <th className="px-2 py-1 text-muted-foreground">LINK</th>
                            </tr>
                          </thead>
                          <tbody>
                            {job.results.map((listing: Listing, index: number) => (
                              <tr 
                                key={index} 
                                className="border-b border-border/50 hover:bg-secondary/50 transition-colors"
                              >
                                <td className="px-2 py-1 max-w-[200px] truncate" title={listing.title}>
                                  {listing.title}
                                </td>
                                <td className="px-2 py-1 text-primary font-bold">
                                  ${listing.price.toFixed(2)}
                                </td>
                                <td className="px-2 py-1 text-muted-foreground max-w-[100px] truncate" title={listing.location}>
                                  {listing.location}
                                </td>
                                <td className="px-2 py-1">
                                  {listing.dealScore > 0 ? (
                                    <span className={`font-bold ${listing.dealScore >= 20 ? 'text-green-500' : listing.dealScore >= 10 ? 'text-accent' : 'text-muted-foreground'}`}>
                                      {listing.dealScore}%
                                    </span>
                                  ) : (
                                    <span className="text-muted-foreground/50">--</span>
                                  )}
                                </td>
                                <td className="px-2 py-1">
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
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        ) : null}

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
            {appState !== "done" && (
              <form className="space-y-5">
                <div className="mb-4 font-mono text-xs text-muted-foreground">
                  <span className="text-primary">{">"}</span> Enter target parameters, matey...
                </div>

                <FormField
                  label="TARGET_QUERY"
                  id="query"
                  type="text"
                  placeholder="e.g. iPhone 13 Pro"
                  value={formData.query}
                  onChange={(v) => setFormData((p: FormData) => ({ ...p, query: v }))}
                  required
                  icon={<TreasureIcon className="text-accent" />}
                />

                <FormField
                  label="PORT_CODE"
                  id="zipCode"
                  type="text"
                  placeholder="e.g. 10001"
                  value={formData.zipCode}
                  onChange={(v) => setFormData((p: FormData) => ({ ...p, zipCode: v }))}
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
                    onChange={(v) => setFormData((p: FormData) => ({ ...p, radius: Number(v) }))}
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
                    onChange={(v) => setFormData((p: FormData) => ({ ...p, threshold: Number(v) }))}
                    min={1}
                    max={90}
                    required
                    suffix="%"
                  />
                </div>

                <div className="mt-2 grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={handleBeginHeist}
                    className="group border-2 border-primary bg-primary px-4 py-3 font-mono text-sm font-bold uppercase tracking-wide text-primary-foreground transition-all hover:bg-transparent hover:text-primary"
                  >
                    <span className="inline-block transition-transform group-hover:translate-x-1">
                      {">>>"} BEGIN HEIST {"<<<"}
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={handleAddToQueue}
                    className="group border-2 border-accent bg-accent px-4 py-3 font-mono text-sm font-bold uppercase tracking-wide text-accent-foreground transition-all hover:bg-transparent hover:text-accent"
                  >
                    <span className="inline-block transition-transform group-hover:translate-x-1">
                      {"+++"} ADD TO QUEUE {"+++"}
                    </span>
                  </button>
                </div>
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
                        {listings.map((listing: Listing, index: number) => (
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
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
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
      setCurrentIndex((prev: number) => (prev + 1) % texts.length);
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
