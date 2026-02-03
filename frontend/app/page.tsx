"use client";

import React from "react"

import { useState, useEffect, useCallback } from "react";

// Mock data for generating CSV results
const MOCK_LISTINGS = [
  {
    title: "iPhone 13 Pro Max 256GB",
    price: 650,
    location: "Brooklyn, NY",
    dealScore: 28,
    url: "https://facebook.com/marketplace/item/123456",
  },
  {
    title: "Sony PlayStation 5 Disc Edition",
    price: 380,
    location: "Queens, NY",
    dealScore: 24,
    url: "https://facebook.com/marketplace/item/234567",
  },
  {
    title: "MacBook Pro 14\" M1 Pro",
    price: 1200,
    location: "Manhattan, NY",
    dealScore: 31,
    url: "https://facebook.com/marketplace/item/345678",
  },
  {
    title: "Nintendo Switch OLED",
    price: 220,
    location: "Bronx, NY",
    dealScore: 18,
    url: "https://facebook.com/marketplace/item/456789",
  },
  {
    title: "Herman Miller Aeron Chair",
    price: 450,
    location: "Jersey City, NJ",
    dealScore: 42,
    url: "https://facebook.com/marketplace/item/567890",
  },
  {
    title: "Samsung 65\" QLED TV",
    price: 580,
    location: "Newark, NJ",
    dealScore: 35,
    url: "https://facebook.com/marketplace/item/678901",
  },
  {
    title: "Dyson V15 Vacuum",
    price: 320,
    location: "Hoboken, NJ",
    dealScore: 22,
    url: "https://facebook.com/marketplace/item/789012",
  },
  {
    title: "Canon EOS R6 Camera Body",
    price: 1100,
    location: "Staten Island, NY",
    dealScore: 27,
    url: "https://facebook.com/marketplace/item/890123",
  },
];

type AppState = "form" | "loading" | "done";

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

  const generateCSV = useCallback(() => {
    const headers = ["Treasure", "Doubloons", "Location", "Steal Score (%)", "Loot URL"];
    const rows = MOCK_LISTINGS.map((item) => [
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

    const targetScanned = 847;
    const targetEvaluated = 156;
    const duration = 4000;

    const scanInterval = setInterval(() => {
      setScannedCount((prev) => {
        const increment = Math.floor(Math.random() * 30) + 10;
        return Math.min(prev + increment, targetScanned);
      });
    }, 50);

    const evalInterval = setInterval(() => {
      setEvaluatedCount((prev) => {
        const increment = Math.floor(Math.random() * 8) + 2;
        return Math.min(prev + increment, targetEvaluated);
      });
    }, 100);

    const timeout = setTimeout(() => {
      clearInterval(scanInterval);
      clearInterval(evalInterval);
      setScannedCount(targetScanned);
      setEvaluatedCount(targetEvaluated);

      const blob = generateCSV();
      setCsvBlob(blob);

      setTimeout(() => {
        setAppState("done");
      }, 500);
    }, duration);

    return () => {
      clearInterval(scanInterval);
      clearInterval(evalInterval);
      clearTimeout(timeout);
    };
  }, [appState, generateCSV]);

  useEffect(() => {
    if (appState === "done" && csvBlob) {
      const timeout = setTimeout(() => {
        downloadCSV();
      }, 100);
      return () => clearTimeout(timeout);
    }
  }, [appState, csvBlob, downloadCSV]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setScannedCount(0);
    setEvaluatedCount(0);
    setCsvBlob(null);
    setAppState("loading");
  };

  const handleReset = () => {
    setAppState("form");
    setScannedCount(0);
    setEvaluatedCount(0);
    setCsvBlob(null);
  };

  return (
    <main className="min-h-screen bg-background p-4 md:p-8">
      {/* Scanlines overlay */}
      <div className="pointer-events-none fixed inset-0 bg-[repeating-linear-gradient(0deg,transparent,transparent_2px,rgba(0,0,0,0.1)_2px,rgba(0,0,0,0.1)_4px)] opacity-30" />
      
      <div className="relative mx-auto max-w-lg">
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
                    suffix="scanned" 
                    icon="~"
                  />
                  <LoadingBar 
                    label="Evaluating loot value" 
                    count={evaluatedCount} 
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

            {/* Done State */}
            {appState === "done" && (
              <div className="space-y-6">
                <div className="text-center">
                  <div className="mb-4 text-5xl">
                    <TreasureIcon className="text-accent" />
                  </div>
                  <h2 className="mb-2 font-mono text-xl font-bold text-foreground">
                    HEIST COMPLETE!
                  </h2>
                  <p className="font-mono text-sm text-muted-foreground">
                    Plundered {MOCK_LISTINGS.length} treasures above {formData.threshold}% steal score
                  </p>
                </div>

                <div className="border border-primary bg-primary/10 p-4">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs text-muted-foreground">LOOT_MAP.CSV</span>
                    <span className="font-mono text-xs text-primary">DOWNLOADED</span>
                  </div>
                  <div className="mt-2 h-1 w-full bg-primary" />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={downloadCSV}
                    className="border-2 border-primary bg-transparent px-4 py-3 font-mono text-sm font-bold text-primary transition-all hover:bg-primary hover:text-primary-foreground"
                  >
                    RE-DOWNLOAD
                  </button>

                  <button
                    type="button"
                    onClick={handleReset}
                    className="border-2 border-accent bg-accent px-4 py-3 font-mono text-sm font-bold text-accent-foreground transition-all hover:bg-transparent hover:text-accent"
                  >
                    NEW HEIST
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
  suffix,
  icon 
}: { 
  label: string; 
  count: number; 
  suffix: string;
  icon: string;
}) {
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
          style={{ width: `${Math.min((count / 847) * 100, 100)}%` }}
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
