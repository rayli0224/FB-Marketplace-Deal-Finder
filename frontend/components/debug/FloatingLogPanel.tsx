"use client";

import React, { useRef, useState, useCallback, useEffect } from "react";
import type { DebugLogEntry } from "./DebugPanel";

const DEFAULT_X = 24;

/** ANSI SGR codes we care about: 0=reset, 1=bold, 31=red, 33=yellow (matches terminal). */
const ANSI_CODE_RE = /\u001b\[[0-9;]*m|\[[0-9;]*m/g;

/** Split on http/https URLs. Separate non-global regex for testing to avoid lastIndex issues. */
const URL_SPLIT_RE = /(https?:\/\/[^\s)]+)/g;
const URL_TEST_RE = /^https?:\/\//;

/** Turn plain text into React nodes, converting URLs into clickable links. */
function linkifyText(text: string, keyPrefix: string): React.ReactNode {
  const parts = text.split(URL_SPLIT_RE);
  if (parts.length === 1) return text;
  return parts.map((part, i) =>
    URL_TEST_RE.test(part) ? (
      <a key={`${keyPrefix}-${i}`} href={part} target="_blank" rel="noopener noreferrer" className="underline text-primary hover:text-primary/80">{part}</a>
    ) : (
      <React.Fragment key={`${keyPrefix}-${i}`}>{part}</React.Fragment>
    )
  );
}

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
const DEFAULT_Y = 24;
const DEFAULT_WIDTH = 384;
const EDGE_MARGIN = 8;
const DEFAULT_HEIGHT = 400;
const MIN_WIDTH = 200;
const MIN_HEIGHT = 150;
const MAX_HEIGHT_VH = 85;

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

export interface FloatingLogPanelProps {
  logs: DebugLogEntry[];
  debugEnabled: boolean;
}

/**
 * Free-floating, draggable and resizable panel that shows debug logs for the current query.
 * Only visible when debug mode is on. Persists for the duration of one search and resets when a new query starts.
 */
export function FloatingLogPanel({ logs, debugEnabled }: FloatingLogPanelProps) {
  const [position, setPosition] = useState({ x: DEFAULT_X, y: DEFAULT_Y });
  const [size, setSize] = useState({ width: DEFAULT_WIDTH, height: DEFAULT_HEIGHT });
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [isResizing, setIsResizing] = useState(false);
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

    const handlePointerMove = (e: PointerEvent) => {
      const { x, y, left, top } = dragStartRef.current;
      const maxX = typeof window !== "undefined" ? window.innerWidth - size.width - EDGE_MARGIN : left + 9999;
      const maxY = typeof window !== "undefined" ? window.innerHeight - size.height - EDGE_MARGIN : top + 9999;
      setPosition({
        x: Math.max(EDGE_MARGIN, Math.min(maxX, left + (e.clientX - x))),
        y: Math.max(EDGE_MARGIN, Math.min(maxY, top + (e.clientY - y))),
      });
    };

    const handlePointerUp = () => {
      setIsDragging(false);
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    window.addEventListener("pointercancel", handlePointerUp);
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
      window.removeEventListener("pointercancel", handlePointerUp);
    };
  }, [isDragging, size.width, size.height]);

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

    const maxHeightPx = (typeof window !== "undefined" ? window.innerHeight : 800) * (MAX_HEIGHT_VH / 100);
    const maxWidthPx = typeof window !== "undefined" ? window.innerWidth - position.x - 24 : 600;

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

  if (!debugEnabled) return null;

  return (
    <div
      className="fixed z-50 flex flex-col rounded-md border border-border bg-background shadow-lg"
      style={{
        left: position.x,
        top: position.y,
        width: size.width,
        height: isCollapsed ? undefined : size.height,
        minHeight: isCollapsed ? 0 : undefined,
      }}
    >
      <div
        onPointerDown={handlePointerDown}
        className="flex items-center justify-between gap-2 px-3 py-2 border-b border-border bg-muted/50 font-mono text-xs font-semibold text-foreground cursor-grab active:cursor-grabbing select-none"
        aria-label="Drag to move log panel"
      >
        <span>Logs</span>
        <button
          type="button"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            setIsCollapsed((prev) => !prev);
          }}
          onPointerDown={(e) => e.stopPropagation()}
          className="shrink-0 w-4 h-4 flex items-center justify-center rounded border border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground cursor-pointer font-mono text-[10px] leading-none"
          aria-label={isCollapsed ? "Expand logs" : "Minimize logs"}
          title={isCollapsed ? "Expand" : "Minimize"}
        >
          {isCollapsed ? "+" : "−"}
        </button>
      </div>
      {!isCollapsed && (
        <>
          <div className="flex-1 min-h-0 overflow-auto font-mono text-xs overflow-x-hidden">
            {logs.length === 0 ? (
              <div className="px-3 py-2 text-muted-foreground">
                No logs yet. Logs stream during the search.
              </div>
            ) : (
              <ul className="list-none px-3 py-2 space-y-1 min-w-0">
                {logs.map((entry, i) => {
                  const isSeparator = isSeparatorLine(entry.message);
                  const lineClass = isSeparator
                    ? "block overflow-hidden whitespace-nowrap"
                    : "break-all";
                  return (
                    <li
                      key={i}
                      className={`min-w-0 overflow-hidden ${logEntryClass(entry.level)} ${lineClass}`}
                    >
                      {parseAnsiToNodes(entry.message)}
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
