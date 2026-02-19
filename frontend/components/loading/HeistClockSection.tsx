"use client";

import { useEffect, useState } from "react";
import { HeistTimerAnimation } from "@/components/loading/HeistTimerAnimation";
import { CONTENT_TEXT_CLASS, CONTENT_TEXT_XS_CLASS } from "@/lib/ui-constants";

/** Interval in ms for updating the heist clock display. */
const HEIST_CLOCK_TICK_MS = 1000;

function formatHeistClock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/**
 * Compact heist clock (radar + elapsed time).
 * Self-contained; manages its own timer from mount.
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
    <div className="flex flex-wrap items-center gap-2">
      <HeistTimerAnimation compact />
      <span className={CONTENT_TEXT_XS_CLASS}>
        Heist clock: <span className={`tabular-nums font-medium ${CONTENT_TEXT_CLASS}`}>{formatHeistClock(elapsedSeconds)}</span>
      </span>
    </div>
  );
}
