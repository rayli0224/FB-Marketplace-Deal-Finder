"use client";

import { useState, useEffect, type Ref, type ChangeEvent, type FocusEvent } from "react";
import { type FormData as ValidationFormData } from "@/lib/validation";
import { InfoIcon } from "@/components/ui/InfoIcon";
import { QUERY_SUGGESTIONS } from "@/components/search-form/querySuggestions";

const SUGGESTION_INTERVAL_MS = 2500;

export interface QueryInputWithSuggestionsProps {
  register: (name: keyof ValidationFormData) => {
    name: string;
    onChange: (e: ChangeEvent<HTMLInputElement>) => void;
    onBlur: (e: FocusEvent<HTMLInputElement>) => void;
    ref: Ref<HTMLInputElement>;
  };
  queryValue: string;
  error?: string;
  afterLabel?: React.ReactNode;
}

/**
 * TARGET_QUERY field with an overlay that cycles through example search terms when the
 * field is empty and not focused. Each suggestion fades in. Mix of deal hunts and pirate-themed.
 */
export function QueryInputWithSuggestions({ register, queryValue, error, afterLabel }: QueryInputWithSuggestionsProps) {
  const [focused, setFocused] = useState(false);
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setIndex((i) => (i + 1) % QUERY_SUGGESTIONS.length), SUGGESTION_INTERVAL_MS);
    return () => clearInterval(id);
  }, []);

  const showOverlay = !queryValue.trim() && !focused;
  const suggestion = QUERY_SUGGESTIONS[index];

  return (
    <div>
      <label htmlFor="query" className="mb-2 flex items-center gap-2 font-mono text-xs text-muted-foreground">
        <span className="text-primary">$</span>
        TARGET_QUERY
        <InfoIcon tooltip="The search term for Facebook Marketplace—what you're looking for." />
        {afterLabel}
      </label>
      <div className="relative">
        <input
          id="query"
          type="text"
          placeholder=" "
          autoComplete="off"
          {...register("query")}
          required
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          className={`w-full border-2 bg-secondary px-3 py-2.5 font-mono text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none ${
            error ? "border-destructive focus:border-destructive" : "border-border focus:border-primary"
          }`}
        />
        {showOverlay && (
          <div
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 font-mono text-sm text-muted-foreground/50"
            aria-hidden
          >
            <span
              key={index}
              className="inline-block font-mono text-sm text-muted-foreground/50"
              style={{
                animation: "query-suggestion-fade 0.5s ease-out forwards",
                opacity: 0,
              }}
            >
              {suggestion}
            </span>
          </div>
        )}
      </div>
      {error && <p className="mt-1 font-mono text-xs text-destructive">{error}</p>}
    </div>
  );
}
