"use client";

import { useEffect, useState } from "react";
import { HeistTimerAnimation } from "@/components/loading/HeistTimerAnimation";
import { CONTENT_TEXT_CLASS, CONTENT_TEXT_SM_CLASS } from "@/lib/ui-constants";

/** Interval in ms for updating the heist clock display. */
const HEIST_CLOCK_TICK_MS = 1000;

function formatHeistClock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/**
 * Standalone section showing elapsed time for the current heist/loading run.
 * Renders a bordered block with the treasure-finder animation and Heist clock readout.
 */
export function HeistClockSection() {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    const startedAt = Date.now();
    const tick = () => setElapsedSeconds(Math.floor((Date.now() - startedAt) / HEIST_CLOCK_TICK_MS));
    const id = setInterval(tick, HEIST_CLOCK_TICK_MS);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="border border-border bg-secondary px-6 py-5">
      <div className={`flex items-center gap-5 ${CONTENT_TEXT_SM_CLASS}`}>
        <HeistTimerAnimation />
        <span>
          Heist clock: <span className={`tabular-nums font-medium ${CONTENT_TEXT_CLASS}`}>{formatHeistClock(elapsedSeconds)}</span>
        </span>
      </div>
    </div>
  );
}
