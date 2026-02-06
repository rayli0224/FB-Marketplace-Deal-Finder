"use client";

import { type ReactNode, type Ref, type ChangeEvent, type FocusEvent } from "react";
import { type FormData as ValidationFormData } from "@/lib/validation";

export interface FormInputFieldProps {
  label: string;
  id: string;
  type: string;
  placeholder: string;
  value?: string | number;
  onChange?: (value: string) => void;
  required?: boolean;
  pattern?: string;
  min?: number;
  max?: number;
  icon?: ReactNode;
  suffix?: string;
  error?: string;
  tooltip?: string;
  register?: (name: keyof ValidationFormData) => {
    name: string;
    onChange: (e: ChangeEvent<HTMLInputElement>) => void;
    onBlur: (e: FocusEvent<HTMLInputElement>) => void;
    ref: Ref<HTMLInputElement>;
  };
}

/**
 * Reusable form field component with pirate-themed styling.
 * Supports both controlled (value/onChange) and uncontrolled (react-hook-form register) modes.
 * When register is provided, uses react-hook-form for form state management. Otherwise uses controlled mode.
 * Displays validation errors below the input with red border styling when invalid.
 */
export function FormInputField({
  label,
  id,
  type,
  placeholder,
  value,
  onChange,
  required,
  pattern,
  min,
  max,
  icon,
  suffix,
  error,
  tooltip,
  register,
}: FormInputFieldProps) {
  return (
    <div>
      <label htmlFor={id} className="mb-2 flex items-center gap-2 font-mono text-xs text-muted-foreground">
        <span className="text-primary">$</span>
        {label}
        {tooltip && (
          <div className="group relative ml-1 inline-flex cursor-help">
            <span className="flex h-4 w-4 items-center justify-center rounded-full border border-accent/40 bg-accent/10 text-[10px] font-bold text-accent transition-all hover:border-accent hover:bg-accent/20 hover:scale-110">
              i
            </span>
            <div className="invisible absolute bottom-full left-1/2 mb-3 w-72 -translate-x-1/2 rounded-lg border-2 border-accent/30 bg-gradient-to-br from-card to-secondary/80 px-4 py-3 font-mono text-xs text-foreground shadow-[0_4px_12px_rgba(0,0,0,0.15)] backdrop-blur-sm group-hover:visible z-20">
              <div className="absolute -bottom-1 left-1/2 h-2 w-2 -translate-x-1/2 rotate-45 border-r-2 border-b-2 border-accent/30 bg-gradient-to-br from-card to-secondary/80"></div>
              <div className="relative">
                <span className="text-primary font-bold">{"//"}</span>{" "}
                <span className="text-foreground">{tooltip.split(". Example:")[0]}.</span>
                {tooltip.includes("Example:") && (
                  <>
                    {" "}
                    <span className="text-accent font-semibold">Example:</span>{" "}
                    <span className="text-foreground">{tooltip.split("Example:")[1]}</span>
                  </>
                )}
              </div>
            </div>
          </div>
        )}
        {icon && <span className="ml-auto">{icon}</span>}
      </label>
      <div className="relative">
        <input
          id={id}
          type={type}
          placeholder={placeholder}
          autoComplete="off"
          {...(register
            ? register(id as keyof ValidationFormData)
            : {
                value,
                onChange: (e) => onChange?.(e.target.value),
              })}
          required={required}
          pattern={pattern}
          min={min}
          max={max}
          className={`w-full border-2 bg-secondary px-3 py-2.5 font-mono text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none ${
            type === "number" ? "[appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none" : ""
          } ${
            error
              ? "border-destructive focus:border-destructive"
              : "border-border focus:border-primary"
          }`}
        />
        {suffix && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 font-mono text-xs text-muted-foreground">
            {suffix}
          </span>
        )}
      </div>
      {error && (
        <p className="mt-1 font-mono text-xs text-destructive">{error}</p>
      )}
    </div>
  );
}

