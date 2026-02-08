"use client";

export interface FullSizeToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
}

/**
 * Full-size toggle switch for filter sections and standalone use.
 * Contrasts with CompactInlineToggle, which is used inline in form label rows.
 */
export function FullSizeToggle({ checked, onChange, label }: FullSizeToggleProps) {
  return (
    <label className="flex cursor-pointer items-center gap-3 group">
      <div className="relative">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          className="sr-only"
        />
        <div
          className={`h-6 w-11 rounded-full border-2 transition-all ${
            checked
              ? "border-primary bg-primary"
              : "border-border bg-secondary"
          }`}
        >
          <div
            className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full border-2 bg-background transition-all ${
              checked
                ? "translate-x-5 border-primary"
                : "translate-x-0 border-border"
            }`}
          />
        </div>
      </div>
      {label && (
        <span className="font-mono text-sm text-foreground transition-colors group-hover:text-primary">
          {label}
        </span>
      )}
    </label>
  );
}
