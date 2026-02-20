"use client";

import React, { useRef, useState, useCallback, useEffect } from "react";
import { CompactInlineToggle } from "@/components/ui/CompactInlineToggle";

const DEFAULT_Y = 24;
const RIGHT_MARGIN = 24;
const PANEL_ESTIMATE_WIDTH = 260;
const PANEL_MIN_WIDTH = 200;
const HEADER_FALLBACK_HEIGHT = 40;
const CONTENT_PADDING = "px-3 py-2";

function getViewportSize(): { width: number; height: number } {
  if (typeof window === "undefined") return { width: 800, height: 600 };
  return { width: window.innerWidth, height: window.innerHeight };
}

export interface FloatingDebugTogglesPanelProps {
  openDevToolsTabs: boolean;
  onOpenDevToolsTabsChange: (checked: boolean) => void;
}

/**
 * Free-floating, draggable panel for debug toggles.
 * Shown when debug mode is enabled. Holds per-run options like "Open DevTools tabs".
 */
export function FloatingDebugTogglesPanel({
  openDevToolsTabs,
  onOpenDevToolsTabsChange,
}: FloatingDebugTogglesPanelProps) {
  const [position, setPosition] = useState(() => {
    if (typeof window === "undefined") return { x: 0, y: DEFAULT_Y };
    const x = Math.max(0, window.innerWidth - PANEL_ESTIMATE_WIDTH - RIGHT_MARGIN);
    return { x, y: DEFAULT_Y };
  });
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const headerRef = useRef<HTMLDivElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const dragStartRef = useRef({ x: 0, y: 0, left: 0, top: 0 });

  const updatePositionForRightEdge = useCallback(() => {
    const panelWidth = panelRef.current?.offsetWidth ?? PANEL_ESTIMATE_WIDTH;
    setPosition((prev: { x: number; y: number }) => ({
      ...prev,
      x: Math.max(0, window.innerWidth - panelWidth - RIGHT_MARGIN),
    }));
  }, []);

  useEffect(() => {
    updatePositionForRightEdge();
    window.addEventListener("resize", updatePositionForRightEdge);
    return () => window.removeEventListener("resize", updatePositionForRightEdge);
  }, [updatePositionForRightEdge]);

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
    const headerWidth = headerElement?.offsetWidth ?? PANEL_MIN_WIDTH;
    const headerHeight = headerElement?.offsetHeight ?? HEADER_FALLBACK_HEIGHT;

    const handlePointerMove = (e: PointerEvent) => {
      const { x, y, left, top } = dragStartRef.current;
      setPosition({
        x: Math.max(0, Math.min(viewport.width - headerWidth, left + (e.clientX - x))),
        y: Math.max(0, Math.min(viewport.height - headerHeight, top + (e.clientY - y))),
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
  }, [isDragging]);

  const stopPropagation = useCallback((e: React.PointerEvent) => {
    e.stopPropagation();
  }, []);

  const handleCollapseClick = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsCollapsed((prev: boolean) => !prev);
  }, []);

  return (
    <div
      ref={panelRef}
      className="fixed z-50 flex flex-col rounded-md border border-border bg-background shadow-lg overflow-visible min-w-[200px]"
      style={{ left: position.x, top: position.y }}
    >
      <div
        ref={headerRef}
        onPointerDown={handlePointerDown}
        className={`flex items-center justify-between gap-2 ${CONTENT_PADDING} border-b border-border bg-muted/50 font-mono text-xs font-semibold text-foreground cursor-grab active:cursor-grabbing select-none`}
        aria-label="Drag to move debug toggles panel"
      >
        <span>Debug toggles</span>
        <button
          type="button"
          onClick={handleCollapseClick}
          onPointerDown={stopPropagation}
          className="shrink-0 w-4 h-4 flex items-center justify-center rounded border border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground cursor-pointer font-mono text-[10px] leading-none"
          aria-label={isCollapsed ? "Expand" : "Minimize"}
          title={isCollapsed ? "Expand" : "Minimize"}
        >
          {isCollapsed ? "+" : "−"}
        </button>
      </div>
      {!isCollapsed && (
        <div className={`${CONTENT_PADDING} space-y-3`} onPointerDown={stopPropagation}>
          <CompactInlineToggle
            id="openDevToolsTabs"
            label="Open DevTools tabs"
            checked={openDevToolsTabs}
            onChange={onOpenDevToolsTabsChange}
            tooltip="When on, browser tabs open automatically so you can inspect the scrapers."
          />
        </div>
      )}
    </div>
  );
}
