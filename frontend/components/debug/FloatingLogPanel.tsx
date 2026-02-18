"use client";

import React, { useRef, useState, useCallback, useEffect } from "react";
import type { DebugLogEntry } from "./DebugPanel";

const DEFAULT_X = 24;
const DEFAULT_Y = 24;
const DEFAULT_WIDTH = 384;
const DEFAULT_HEIGHT = 400;
const RESIZE_RIGHT_MARGIN = 24;
const MIN_WIDTH = 200;
const MIN_HEIGHT = 150;
const MAX_HEIGHT_VH = 85;
const SCROLL_BOTTOM_THRESHOLD = 20;
const VIEWPORT_FALLBACK_HEIGHT = 800;
const VIEWPORT_FALLBACK_WIDTH = 600;
const HEADER_FALLBACK_HEIGHT = 40;
const LOG_CONTENT_PADDING = "px-3 py-2";
const LOG_LINK_CLASS = "underline text-primary hover:text-primary/80";
const LOG_TIMER_CLASS = "shrink-0 text-[10px] text-muted-foreground/80 tabular-nums mr-2";

/** ANSI SGR codes we care about: 0=reset, 1=bold, 31=red, 33=yellow (matches terminal). */
const ANSI_CODE_RE = /\u001b\[[0-9;]*m|\[[0-9;]*m/g;
const URL_SPLIT_RE = /(https?:\/\/[^\s)]+)/g;
const URL_TEST_RE = /^https?:\/\//;

function getViewportSize(): { width: number; height: number } {
  if (typeof window === "undefined") {
    return { width: VIEWPORT_FALLBACK_WIDTH, height: VIEWPORT_FALLBACK_HEIGHT };
  }
  return { width: window.innerWidth, height: window.innerHeight };
}

/** Returns true if the element is scrolled within the bottom threshold (user is viewing the latest content). */
function isScrolledToBottom(el: HTMLElement): boolean {
  return el.scrollHeight - el.scrollTop - el.clientHeight <= SCROLL_BOTTOM_THRESHOLD;
}

/** Splits text on URLs and converts each URL into a clickable anchor; returns plain text or React nodes. */
function linkifyText(text: string, keyPrefix: string): React.ReactNode {
  const parts = text.split(URL_SPLIT_RE);
  if (parts.length === 1) return text;
  return parts.map((part, i) =>
    URL_TEST_RE.test(part) ? (
      <a key={`${keyPrefix}-${i}`} href={part} target="_blank" rel="noopener noreferrer" className={LOG_LINK_CLASS}>
        {part}
      </a>
    ) : (
      <React.Fragment key={`${keyPrefix}-${i}`}>{part}</React.Fragment>
    )
  );
}

/**
 * Parses ANSI SGR escape sequences in text and returns React nodes with bold/color styling.
 * Supports reset, bold, red (31), and yellow (33). URLs in output are linkified.
 */
function parseAnsiToNodes(text: string): React.ReactNode {
  const parts = text.split(ANSI_CODE_RE);
  const codes = text.match(ANSI_CODE_RE) ?? [];
  let bold = false;
  let color: string | null = null;
  const out: React.ReactNode[] = [];
  parts.forEach((segment, i) => {
    if (i > 0 && codes[i - 1]) {
      const raw = codes[i - 1].replace(/\u001b\[/g, "").replace(/^\[/, "").replace(/m$/, "");
      const n = raw.split(";").map((s) => parseInt(s, 10)).filter((x) => !Number.isNaN(x));
      if (n.includes(0)) {
        bold = false;
        color = null;
      }
      if (n.includes(1)) bold = true;
      if (n.includes(31)) color = "var(--warning-red, #dc2626)";
      if (n.includes(33)) color = "var(--warning-yellow, #ca8a04)";
    }
    if (segment === "") return;
    let node: React.ReactNode = linkifyText(segment, `a${i}`);
    if (bold) node = <strong>{node}</strong>;
    if (color) node = <span style={{ color }}>{node}</span>;
    out.push(<React.Fragment key={i}>{node}</React.Fragment>);
  });
  return out.length === 1 ? out[0] : out;
}

/** Returns Tailwind classes for log entry text based on log level (WARNING, ERROR, CRITICAL, default). */
function logEntryClass(level: string): string {
  switch (level) {
    case "WARNING":
      return "text-yellow-600 dark:text-yellow-500";
    case "ERROR":
    case "CRITICAL":
      return "text-red-600 dark:text-red-400 font-medium";
    default:
      return "text-muted-foreground";
  }
}

/** True if the message is a horizontal separator line (only dash/unicode dash/space). */
function isSeparatorLine(message: string): boolean {
  return /^[\s\-─]+$/.test(message) && message.length > 2;
}

/** Format elapsed milliseconds as m:ss.t (e.g. 1:04.3). */
function formatElapsedSinceStart(elapsedMs: number): string {
  const clamped = Math.max(0, elapsedMs);
  const totalTenths = Math.floor(clamped / 100);
  const minutes = Math.floor(totalTenths / 600);
  const seconds = Math.floor((totalTenths % 600) / 10);
  const tenths = totalTenths % 10;
  return `${minutes}:${String(seconds).padStart(2, "0")}.${tenths}`;
}

export interface FloatingLogPanelProps {
  logs: DebugLogEntry[];
  debugEnabled: boolean;
}

/**
 * Free-floating, draggable and resizable panel that shows debug logs.
 * Always visible when debug mode is enabled. Logs persist across searches and page refreshes until the container restarts.
 * Auto-scrolls to the latest logs when the user is at the bottom; pauses when they scroll up and resumes when they scroll back down.
 */
export function FloatingLogPanel({ logs, debugEnabled }: FloatingLogPanelProps) {
  const [position, setPosition] = useState({ x: DEFAULT_X, y: DEFAULT_Y });
  const [size, setSize] = useState({ width: DEFAULT_WIDTH, height: DEFAULT_HEIGHT });
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [isResizing, setIsResizing] = useState(false);
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true);
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const headerRef = useRef<HTMLDivElement | null>(null);
  const dragStartRef = useRef({ x: 0, y: 0, left: 0, top: 0 });
  const resizeStartRef = useRef({ x: 0, y: 0, width: 0, height: 0 });

  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (e.button !== 0) return;
      e.preventDefault();
      dragStartRef.current = {
        x: e.clientX,
        y: e.clientY,
        left: position.x,
        top: position.y,
      };
      setIsDragging(true);
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    },
    [position]
  );

  useEffect(() => {
    if (!isDragging) return;
    const viewport = getViewportSize();
    const headerElement = headerRef.current;
    const headerWidth = headerElement?.offsetWidth ?? size.width;
    const headerHeight = headerElement?.offsetHeight ?? HEADER_FALLBACK_HEIGHT;

    const handlePointerMove = (e: PointerEvent) => {
      const { x, y, left, top } = dragStartRef.current;
      const calculatedX = left + (e.clientX - x);
      const calculatedY = top + (e.clientY - y);
      
      setPosition({
        x: Math.max(0, Math.min(viewport.width - headerWidth, calculatedX)),
        y: Math.max(0, Math.min(viewport.height - headerHeight, calculatedY)),
      });
    };

    const handlePointerUp = () => setIsDragging(false);

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    window.addEventListener("pointercancel", handlePointerUp);
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
      window.removeEventListener("pointercancel", handlePointerUp);
    };
  }, [isDragging, size.width]);

  const handleResizePointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();
      resizeStartRef.current = {
        x: e.clientX,
        y: e.clientY,
        width: size.width,
        height: size.height,
      };
      setIsResizing(true);
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    },
    [size]
  );

  useEffect(() => {
    if (!isResizing) return;
    const viewport = getViewportSize();
    const maxHeightPx = viewport.height * (MAX_HEIGHT_VH / 100);
    const maxWidthPx = viewport.width - position.x - RESIZE_RIGHT_MARGIN;

    const handlePointerMove = (e: PointerEvent) => {
      const { x, y, width, height } = resizeStartRef.current;
      const newWidth = Math.min(maxWidthPx, Math.max(MIN_WIDTH, width + (e.clientX - x)));
      const newHeight = Math.min(maxHeightPx, Math.max(MIN_HEIGHT, height + (e.clientY - y)));
      setSize({ width: newWidth, height: newHeight });
    };

    const handlePointerUp = () => setIsResizing(false);

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    window.addEventListener("pointercancel", handlePointerUp);
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
      window.removeEventListener("pointercancel", handlePointerUp);
    };
  }, [isResizing, position.x]);

  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    setShouldAutoScroll(isScrolledToBottom(el));
  }, []);

  useEffect(() => {
    if (!shouldAutoScroll) return;
    const el = scrollContainerRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [logs, shouldAutoScroll]);

  const handleCollapseClick = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsCollapsed((prev: boolean) => !prev);
  }, []);

  const handleCollapsePointerDown = useCallback((e: React.PointerEvent) => {
    e.stopPropagation();
  }, []);

  const firstTimestampMs = logs.find((entry) => typeof entry.timestampMs === "number")?.timestampMs ?? null;

  return (
    <div
      className="fixed z-50 flex flex-col rounded-md border border-border bg-background shadow-lg overflow-visible"
      style={{
        left: position.x,
        top: position.y,
        width: size.width,
        height: isCollapsed ? undefined : size.height,
        minHeight: isCollapsed ? 0 : undefined,
      }}
    >
      <div
        ref={headerRef}
        onPointerDown={handlePointerDown}
        className={`flex items-center justify-between gap-2 ${LOG_CONTENT_PADDING} border-b border-border bg-muted/50 font-mono text-xs font-semibold text-foreground cursor-grab active:cursor-grabbing select-none`}
        aria-label="Drag to move log panel"
      >
        <span>Logs</span>
        <button
          type="button"
          onClick={handleCollapseClick}
          onPointerDown={handleCollapsePointerDown}
          className="shrink-0 w-4 h-4 flex items-center justify-center rounded border border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground cursor-pointer font-mono text-[10px] leading-none"
          aria-label={isCollapsed ? "Expand logs" : "Minimize logs"}
          title={isCollapsed ? "Expand" : "Minimize"}
        >
          {isCollapsed ? "+" : "−"}
        </button>
      </div>
      {!isCollapsed && (
        <>
          <div
            ref={scrollContainerRef}
            onScroll={handleScroll}
            className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden font-mono text-xs"
          >
            {logs.length === 0 ? (
              <div className={`${LOG_CONTENT_PADDING} text-muted-foreground`}>
                {debugEnabled
                  ? "No logs yet. Logs stream during the search."
                  : "Start a search with the debug server to see logs."}
              </div>
            ) : (
              <ul className={`list-none ${LOG_CONTENT_PADDING} space-y-1 min-w-0`}>
                {logs.map((entry, i) => {
                  const isSeparator = isSeparatorLine(entry.message);
                  const lineClass = isSeparator
                    ? "block overflow-hidden whitespace-nowrap"
                    : "break-all";
                  const elapsedLabel =
                    firstTimestampMs !== null && typeof entry.timestampMs === "number"
                      ? formatElapsedSinceStart(entry.timestampMs - firstTimestampMs)
                      : null;
                  return (
                    <li
                      key={i}
                      className={`min-w-0 overflow-hidden ${logEntryClass(entry.level)} ${lineClass} flex items-start`}
                    >
                      <span className={LOG_TIMER_CLASS}>
                        {elapsedLabel ? elapsedLabel : "--:--.-"}
                      </span>
                      <span className="min-w-0 flex-1">{parseAnsiToNodes(entry.message)}</span>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
          <div
            onPointerDown={handleResizePointerDown}
            className="absolute bottom-0 right-0 w-4 h-4 cursor-nwse-resize select-none border-l border-t border-border bg-muted/30 rounded-br"
            aria-label="Drag to resize log panel"
          />
        </>
      )}
    </div>
  );
}
