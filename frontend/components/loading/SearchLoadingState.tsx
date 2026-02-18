"use client";

import { useEffect, useState } from "react";
import { HeistTimerAnimation } from "@/components/loading/HeistTimerAnimation";
import { LoadingBox } from "@/components/loading/LoadingBox";
import { ProgressBar } from "@/components/loading/ProgressBar";
import { CONTENT_TEXT_CLASS, CONTENT_TEXT_XS_CLASS } from "@/lib/ui-constants";

/** Interval in ms for updating the heist clock display. */
const HEIST_CLOCK_TICK_MS = 1000;

/** Loading section flex layout (wrap, gap). */
const LOADING_LAYOUT_CLASS = "flex flex-wrap items-stretch gap-3";

/** Stack of loading sections (column gap). */
const LOADING_STACK_CLASS = "flex flex-col gap-3 min-w-0 flex-1";

/** Loading cancel button (outline style, primary color). */
const LOADING_CANCEL_BUTTON_CLASS =
  "mt-2 w-full border-2 border-primary bg-transparent px-2 py-1 font-mono text-xs font-bold text-primary transition-all hover:bg-primary hover:text-primary-foreground";

export type SearchPhase = "scraping" | "evaluating";

const PHASE_MESSAGES: Record<SearchPhase, string> = {
  scraping: "Infiltrating the marketplace for treasures...",
  evaluating: "Appraising each piece of loot...",
};

const FALLBACK_PHASE_MESSAGE = "Getting the crew ready...";

export interface SearchLoadingStateProps {
  phase: SearchPhase;
  scannedCount: number;
  evaluatedCount: number;
  maxListings: number;
  onCancel?: () => void;
}

function formatHeistClock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function getPhaseMessage(phase: SearchPhase): string {
  return PHASE_MESSAGES[phase] ?? FALLBACK_PHASE_MESSAGE;
}

/**
 * Loading state component displaying progress during marketplace search.
 * Shows current phase with heist clock (radar + elapsed time), phase description,
 * and progress bars for scanned and evaluated listings. Includes a cancel button.
 */
export function SearchLoadingState({ phase, scannedCount, evaluatedCount, maxListings, onCancel }: SearchLoadingStateProps) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    const startedAt = Date.now();
    const tick = () => setElapsedSeconds(Math.floor((Date.now() - startedAt) / HEIST_CLOCK_TICK_MS));
    const id = setInterval(tick, HEIST_CLOCK_TICK_MS);
    return () => clearInterval(id);
  }, []);

  const phaseMessage = getPhaseMessage(phase);

  return (
    <div className={LOADING_LAYOUT_CLASS}>
      <LoadingBox className="shrink-0 w-fit">
        <div className={CONTENT_TEXT_XS_CLASS}>
          {phaseMessage}
        </div>
        <div className="mt-2 flex flex-col items-center gap-1">
          <HeistTimerAnimation />
          <span className={CONTENT_TEXT_XS_CLASS}>
            Heist clock: <span className={`tabular-nums font-medium ${CONTENT_TEXT_CLASS}`}>{formatHeistClock(elapsedSeconds)}</span>
          </span>
        </div>
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className={LOADING_CANCEL_BUTTON_CLASS}
          >
            CANCEL
          </button>
        )}
      </LoadingBox>

      <div className={LOADING_STACK_CLASS}>
        <LoadingBox>
          <ProgressBar
            label="Infiltrating listings"
            count={scannedCount}
            maxCount={maxListings}
            suffix="scanned"
            icon="~"
          />
        </LoadingBox>
        <LoadingBox>
          <ProgressBar
            label="Evaluating loot value"
            count={evaluatedCount}
            maxCount={scannedCount || maxListings}
            suffix="assessed"
            icon="*"
          />
        </LoadingBox>
      </div>
    </div>
  );
}

