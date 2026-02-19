"use client";

import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import type { CompItem, Listing } from "./ResultsTable";

const DEFAULT_CURRENCY = "$";
const COMP_TABLE_ROW_HEIGHT = "max-h-[2.5em]";
const COMP_TABLE_BORDER_R = "border-r border-border last:border-r-0";
const COMP_TABLE_CELL_BASE = `px-2 py-1 align-top ${COMP_TABLE_ROW_HEIGHT} overflow-hidden`;
const POPUP_ANCHOR_OFFSET_TOP = 8;

function formatPrice(price: number, currency: string = DEFAULT_CURRENCY): string {
  return `${currency}${price.toFixed(2)}`;
}

function DetailsContentPanel({ reason }: { reason: string }) {
  return (
    <p className="text-muted-foreground">
      {reason}
    </p>
  );
}

function getCompItemStatus(item: CompItem): "accept" | "maybe" | "reject" {
  return (item.filterStatus ?? (item.filtered ? "reject" : "accept")) as "accept" | "maybe" | "reject";
}

function getCompRowStyles(status: "accept" | "maybe" | "reject"): {
  opacityClass: string;
  linkClass: string;
  priceClass: string;
  reasonClass: string;
  statusLabel: string;
  titleText: string | undefined;
} {
  const isRejected = status === "reject";
  const isMaybe = status === "maybe";
  return {
    opacityClass: isRejected ? "opacity-60" : "",
    linkClass: isRejected ? "text-red-500 line-through" : isMaybe ? "text-yellow-500" : "text-primary",
    priceClass: isRejected ? "text-red-500" : isMaybe ? "text-yellow-500" : "text-primary",
    reasonClass: isRejected ? "text-red-500/70" : isMaybe ? "text-yellow-500/70" : "text-muted-foreground",
    statusLabel: isRejected ? "Rejected" : isMaybe ? "Maybe" : "Accepted",
    titleText: isRejected ? "Filtered out as non-comparable" : isMaybe ? "Partial match (0.5x weight in average)" : undefined,
  };
}

function sortCompsValidFirst(items: CompItem[]): CompItem[] {
  const order = { accept: 0, maybe: 1, reject: 2 };
  return [...items].sort(
    (a, b) => order[getCompItemStatus(a)] - order[getCompItemStatus(b)]
  );
}

function CompsContentPanel({ listing }: { listing: Listing }) {
  const { ebaySearchQuery, compPrice, compPrices, compItems, currency = "$" } = listing;
  const prices = compItems?.map((c) => c.price) ?? compPrices ?? [];
  const count = prices.length;
  const sortedItems =
    compItems && compItems.length > 0 ? sortCompsValidFirst(compItems) : null;

  return (
    <div className="space-y-3 text-muted-foreground">
      {(ebaySearchQuery != null || compPrice != null) && (
        <div className="grid gap-x-4 gap-y-0.5 grid-cols-1 sm:grid-cols-2">
          {ebaySearchQuery != null && (
            <div>
              <span>eBay search query: </span>
              <span className="text-foreground break-words">&quot;{ebaySearchQuery}&quot;</span>
            </div>
          )}
          {compPrice != null && (
            <div>
              <span>eBay sold avg: </span>
              <span className="text-primary font-bold">{formatPrice(compPrice, currency)}</span>
            </div>
          )}
        </div>
      )}
      {count > 0 && (
        <div>
          <span className="font-bold text-foreground">Compared against {count} listing{count !== 1 ? "s" : ""}:</span>
          <div className="mt-1 max-h-72 overflow-auto border border-border min-w-0">
            {sortedItems ? (
              <table className="w-full min-w-max table-auto border-collapse border border-border text-xs">
                <thead>
                  <tr className="border-b border-border bg-secondary/50">
                    <th className={`${COMP_TABLE_BORDER_R} px-2 py-1 text-left font-semibold text-foreground`}>Listing</th>
                    <th className={`${COMP_TABLE_BORDER_R} px-2 py-1 text-right font-semibold text-foreground whitespace-nowrap`}>Price</th>
                    <th className={`${COMP_TABLE_BORDER_R} px-2 py-1 text-left font-semibold text-foreground whitespace-nowrap`}>Status</th>
                    <th className="px-2 py-1 text-left font-semibold text-foreground">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedItems.map((item: CompItem, i: number) => {
                    const status = getCompItemStatus(item);
                    const styles = getCompRowStyles(status);
                    return (
                      <tr
                        key={item.url ? `${item.url}-${i}` : i}
                        className={`border-b border-border/50 last:border-b-0 ${styles.opacityClass}`}
                      >
                        <td className={`${COMP_TABLE_CELL_BASE} ${COMP_TABLE_BORDER_R}`}>
                          <a
                            href={item.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className={`hover:underline truncate block max-w-[200px] cursor-pointer ${styles.linkClass}`}
                            title={styles.titleText ?? (item.title || "eBay listing")}
                          >
                            {item.title || "eBay listing"}
                          </a>
                        </td>
                        <td className={`${COMP_TABLE_CELL_BASE} ${COMP_TABLE_BORDER_R} text-right font-bold ${styles.priceClass}`}>
                          <span className="line-clamp-2 block">{formatPrice(item.price, DEFAULT_CURRENCY)}</span>
                        </td>
                        <td className={`${COMP_TABLE_CELL_BASE} ${COMP_TABLE_BORDER_R} ${styles.reasonClass}`}>
                          <span className="line-clamp-2 block">{styles.statusLabel}</span>
                        </td>
                        <td className={`${COMP_TABLE_CELL_BASE} ${styles.reasonClass}`}>
                          <span className="line-clamp-2 block" title={item.filterReason ?? ""}>
                            {item.filterReason ?? "—"}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              <ul className="p-2 space-y-0.5">
                {compPrices?.map((p, i) => (
                  <li key={i}>
                    <span className="text-muted-foreground">{formatPrice(p, DEFAULT_CURRENCY)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export interface DetailsPopupProps {
  listing: Listing;
  anchorRect: DOMRect;
  onClose: () => void;
}

/**
 * Tooltip-style popup showing listing comps/details. Rendered in a portal above
 * the table, positioned from anchorRect. Opaque background so it overlays content.
 */
export function DetailsPopup({ listing, anchorRect, onClose }: DetailsPopupProps) {
  const popupRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const handleClickOutside = (e: MouseEvent) => {
      if (popupRef.current && !popupRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleEscape);
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      window.removeEventListener("keydown", handleEscape);
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [onClose]);

  const hasComps =
    listing.ebaySearchQuery != null || listing.compPrice != null;
  const hasDetails =
    !hasComps &&
    listing.noCompReason != null &&
    listing.noCompReason !== "";

  const popup = (
    <div
      ref={popupRef}
      className="fixed z-50 w-fit max-w-[min(560px,90vw)] max-h-[85vh] overflow-hidden flex flex-col border-2 border-border bg-secondary shadow-[4px_4px_0_0] shadow-primary/20 font-mono text-xs"
      style={{
        left: anchorRect.left + anchorRect.width / 2,
        top: anchorRect.top - POPUP_ANCHOR_OFFSET_TOP,
        transform: "translate(-50%, -100%)",
      }}
      role="dialog"
      aria-modal="true"
    >
      <div className="px-4 py-3 overflow-auto flex-1 min-h-0">
        {hasComps && <CompsContentPanel listing={listing} />}
        {hasDetails && listing.noCompReason && (
          <DetailsContentPanel reason={listing.noCompReason} />
        )}
      </div>
    </div>
  );

  return typeof document !== "undefined" ? createPortal(popup, document.body) : null;
}
