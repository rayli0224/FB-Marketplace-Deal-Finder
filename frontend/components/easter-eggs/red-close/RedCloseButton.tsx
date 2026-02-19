"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";

const PROMPTS: [string, string, string, string] = [
  "Ye dare abandon the loot hunt? Why would ye close this tab?",
  "Again? What treasure calls ye away from these shores?",
  "Third strike, scallywag. State yer reason for leavin'.",
  "Ye've tried my patience. One more click and ye'll be sunk.",
];

const SUNK_PATH = "/sunk";

/**
 * Red traffic-light button that intercepts close attempts. Prompts the user
 * with pirate-themed messages on clicks 1–4, then navigates to the sunk page
 * on the 5th click. Shows an X on hover.
 */
export function RedCloseButton() {
  const [clickCount, setClickCount] = useState(0);
  const [isHovered, setIsHovered] = useState(false);
  const [showPrompt, setShowPrompt] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  const handleClick = useCallback(() => {
    if (clickCount < 4) {
      setShowPrompt(true);
      setClickCount((c: number) => c + 1);
    } else {
      router.push(SUNK_PATH);
    }
  }, [clickCount, router]);

  const dismissPrompt = useCallback(() => setShowPrompt(false), []);

  useEffect(() => {
    if (!showPrompt) return;
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (containerRef.current && !containerRef.current.contains(target)) {
        dismissPrompt();
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showPrompt, dismissPrompt]);

  return (
    <div ref={containerRef} className="relative">
      {showPrompt && (
        <div className="absolute bottom-full left-0 z-50 mb-1 w-64 -translate-x-12 rounded border-2 border-border bg-card p-3 shadow-lg">
          <p className="font-mono text-xs text-foreground">
            {PROMPTS[clickCount - 1]}
          </p>
        </div>
      )}
      <button
        type="button"
        onClick={handleClick}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        className="relative flex h-3 w-3 shrink-0 items-center justify-center rounded-full bg-destructive transition-colors hover:bg-destructive/90 cursor-pointer"
        aria-label="Close"
      >
        {isHovered && (
          <span className="font-mono text-[6px] font-bold text-destructive-foreground leading-none">
            ×
          </span>
        )}
      </button>
    </div>
  );
}
