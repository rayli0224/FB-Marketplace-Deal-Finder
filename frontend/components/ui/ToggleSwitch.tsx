"use client";

export interface ToggleSwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
}

/**
 * Reusable toggle switch component matching the app's pirate-themed design.
 * Provides a styled toggle switch with smooth transitions and hover effects.
 */
export function ToggleSwitch({ checked, onChange, label }: ToggleSwitchProps) {
  return (
    <label className="flex items-center gap-3 cursor-pointer group">
      <div className="relative">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          className="sr-only"
        />
        <div
          className={`w-11 h-6 rounded-full border-2 transition-all ${
            checked
              ? "bg-primary border-primary"
              : "bg-secondary border-border"
          }`}
        >
          <div
            className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-background border-2 transition-all ${
              checked
                ? "translate-x-5 border-primary"
                : "translate-x-0 border-border"
            }`}
          />
        </div>
      </div>
      {label && (
        <span className="font-mono text-sm text-foreground group-hover:text-primary transition-colors">
          {label}
        </span>
      )}
    </label>
  );
}

