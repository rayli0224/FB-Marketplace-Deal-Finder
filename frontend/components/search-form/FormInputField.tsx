"use client";

import { type ReactNode, type Ref, type ChangeEvent, type FocusEvent, type KeyboardEvent, type ClipboardEvent } from "react";
import { type FormData as ValidationFormData } from "@/lib/validation";
import { InfoIcon } from "@/components/ui/InfoIcon";

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
  afterLabel?: ReactNode;
  digitsOnly?: boolean;
  inputMode?: "numeric" | "text";
  register?: (name: keyof ValidationFormData) => {
    name: string;
    onChange: (e: ChangeEvent<HTMLInputElement>) => void;
    onBlur: (e: FocusEvent<HTMLInputElement>) => void;
    ref: Ref<HTMLInputElement>;
  };
}

/**
 * Reusable form field component with themed styling.
 * Supports controlled (value/onChange) and uncontrolled (react-hook-form register) modes.
 * When register is provided, uses react-hook-form; otherwise controlled mode.
 * Displays validation errors below the input when invalid.
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
  afterLabel,
  digitsOnly,
  inputMode,
  register,
}: FormInputFieldProps) {
  /**
   * Blocks non-digit keypresses when digitsOnly is enabled.
   * Allows control keys (Backspace, Delete, Tab, Arrow keys, Home, End) and
   * clipboard shortcuts (Ctrl/Cmd + A/C/V/X) so the input remains usable.
   */
  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (!digitsOnly) return;

    const allowedKeys = ["Backspace", "Delete", "Tab", "ArrowLeft", "ArrowRight", "Home", "End"];
    if (allowedKeys.includes(e.key)) return;
    if ((e.metaKey || e.ctrlKey) && ["a", "c", "v", "x"].includes(e.key)) return;
    if (!/^\d$/.test(e.key)) {
      e.preventDefault();
    }
  }

  /**
   * Intercepts paste events when digitsOnly is enabled.
   * Strips all non-digit characters from the pasted text and inserts only the digits
   * at the current cursor position, preserving any existing selection behavior.
   */
  function handlePaste(e: ClipboardEvent<HTMLInputElement>) {
    if (!digitsOnly) return;

    e.preventDefault();
    const digitsOnlyText = e.clipboardData.getData("text").replace(/\D/g, "");
    const input = e.currentTarget;
    const start = input.selectionStart ?? 0;
    const end = input.selectionEnd ?? 0;
    const currentValue = input.value;
    const newValue = currentValue.slice(0, start) + digitsOnlyText + currentValue.slice(end);

    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
    nativeInputValueSetter?.call(input, newValue);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.setSelectionRange(start + digitsOnlyText.length, start + digitsOnlyText.length);
  }

  return (
    <div>
      <label htmlFor={id} className="mb-2 flex items-center gap-2 font-mono text-xs text-muted-foreground">
        <span className="text-primary">$</span>
        {label}
        {tooltip && <InfoIcon tooltip={tooltip} />}
        {afterLabel}
        {icon && <span className="ml-auto">{icon}</span>}
      </label>
      <div className="relative">
        <input
          id={id}
          type={type}
          placeholder={placeholder}
          autoComplete="off"
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          inputMode={inputMode}
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

