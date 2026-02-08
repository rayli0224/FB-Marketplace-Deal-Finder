"use client";

import { InfoIcon } from "@/components/ui/InfoIcon";

export interface CompactInlineToggleProps {
  id?: string;
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  tooltip: string;
}

/**
 * Compact inline toggle for use in form label rows.
 * Renders a small switch with label and optional info icon.
 */
export function CompactInlineToggle({ id, label, checked, onChange, tooltip }: CompactInlineToggleProps) {
  return (
    <span className="ml-2 inline-flex items-center gap-1.5">
      <label className="flex cursor-pointer items-center gap-1.5">
        <input
          id={id}
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          className="sr-only"
        />
        <div
          className={`relative h-5 w-9 shrink-0 rounded-full border-2 transition-all ${
            checked ? "border-primary bg-primary" : "border-border bg-secondary"
          }`}
        >
          <div
            className={`absolute top-1/2 left-0.5 h-3.5 w-3.5 -translate-y-1/2 rounded-full border-2 bg-background transition-all ${
              checked
                ? "translate-x-[18px] border-primary"
                : "translate-x-0 border-border"
            }`}
          />
        </div>
        <span className="font-mono text-[10px] text-muted-foreground">{label}</span>
      </label>
      <InfoIcon tooltip={tooltip} />
    </span>
  );
}
