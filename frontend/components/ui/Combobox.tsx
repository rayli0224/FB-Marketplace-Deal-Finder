"use client";

import { useState, useRef, useEffect, type ChangeEvent, type FocusEvent, type KeyboardEvent } from "react";
import { type UseFormRegisterReturn } from "react-hook-form";

const COMBOBOX_INPUT_BASE_CLASS =
  "w-full border-2 bg-secondary px-3 py-2.5 font-mono text-sm text-foreground focus:outline-none border-border focus:border-primary pr-10";
const COMBOBOX_INPUT_ERROR_CLASS = "border-destructive focus:border-destructive";
const INITIALIZATION_DELAY_MS = 10;

/**
 * Chevron icon component for dropdown indicator.
 */
function ChevronIcon({ isOpen }: { isOpen: boolean }) {
  return (
    <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none">
      <svg
        width="16"
        height="16"
        viewBox="0 0 16 16"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={`transition-transform ${isOpen ? "rotate-180" : ""}`}
      >
        <path d="M8 11L3 6h10z" fill="currentColor" className="text-muted-foreground" />
      </svg>
    </div>
  );
}

export interface ComboboxProps<T> {
  id: string;
  register: UseFormRegisterReturn;
  options: readonly T[] | T[];
  getOptionValue: (option: T) => string;
  getOptionLabel: (option: T) => string;
  placeholder?: string;
  error?: string;
  required?: boolean;
}

/**
 * Generic combobox component with substring matching and last valid value restoration.
 * Supports keyboard navigation (Tab, Arrow keys), mouse hover, and typing to filter/highlight options.
 * Updates the selected value in real-time as the user navigates through options.
 */
export function Combobox<T>({ id, register, options, getOptionValue, getOptionLabel, placeholder, error, required }: ComboboxProps<T>) {
  const [selectedValue, setSelectedValue] = useState("");
  const [filterText, setFilterText] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const [lastMatchedValue, setLastMatchedValue] = useState<string>("");
  const [navigationIndex, setNavigationIndex] = useState<number | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const highlightedOptionRef = useRef<HTMLButtonElement | null>(null);
  const { ref: registerRef, ...registerProps } = register;

  // ============================================================================
  // State Management Helpers
  // ============================================================================

  /**
   * Finds an option by its string value.
   */
  function findOptionByValue(value: string): T | undefined {
    return options.find((opt) => getOptionValue(opt) === value);
  }

  /**
   * Updates the form value in react-hook-form when the selected value changes.
   */
  function updateFormValue(value: string): void {
    if (!inputRef.current) return;

    inputRef.current.value = value;
    const syntheticEvent = {
      target: { value, name: registerProps.name },
      currentTarget: { value, name: registerProps.name },
    } as ChangeEvent<HTMLInputElement>;
    registerProps.onChange(syntheticEvent);
  }

  /**
   * Updates the selected value and all related state, including form value.
   */
  function updateSelectedValue(value: string): void {
    setSelectedValue(value);
    setLastMatchedValue(value);
    updateFormValue(value);
  }

  /**
   * Clears filter text and navigation index, typically when starting a new interaction.
   */
  function clearFilterAndNavigation(): void {
    setFilterText("");
    setNavigationIndex(null);
  }

  // ============================================================================
  // Navigation Helpers
  // ============================================================================

  /**
   * Finds the current navigation index based on selected value or navigationIndex state.
   */
  function getCurrentNavigationIndex(): number {
    if (options.length === 0) return -1;

    if (navigationIndex !== null && navigationIndex >= 0 && navigationIndex < options.length) {
      return navigationIndex;
    }
    if (selectedValue) {
      const index = options.findIndex((opt) => getOptionValue(opt) === selectedValue);
      return index >= 0 ? index : -1;
    }
    return -1;
  }

  /**
   * Calculates the next navigation index based on direction and current position.
   */
  function calculateNextIndex(currentIndex: number, direction: "next" | "prev"): number {
    if (direction === "next") {
      return currentIndex < options.length - 1 ? currentIndex + 1 : 0;
    }
    return currentIndex > 0 ? currentIndex - 1 : options.length - 1;
  }

  /**
   * Navigates to the next or previous option and updates the selected value.
   */
  function navigateOptions(direction: "next" | "prev"): void {
    if (options.length === 0) return;

    const currentIndex = getCurrentNavigationIndex();
    const newIndex = calculateNextIndex(currentIndex, direction);

    setNavigationIndex(newIndex);
    clearFilterAndNavigation();
    updateSelectedValue(getOptionValue(options[newIndex]));
  }

  // ============================================================================
  // Filtering Helpers
  // ============================================================================

  /**
   * Finds an option that matches the given filter text (substring match, case-insensitive).
   */
  function findMatchingOption(filter: string): T | undefined {
    if (!filter.trim()) return undefined;
    const searchLower = filter.toLowerCase();
    return options.find((option) => getOptionValue(option).toLowerCase().includes(searchLower));
  }

  /**
   * Finds the option that matches the filter text (substring match).
   * Returns the first option where the option value (as string) contains the filter text as a substring.
   * If no filter text, returns the currently selected option or the option at navigationIndex.
   */
  function getHighlightedOption(): T | null {
    if (navigationIndex !== null && navigationIndex >= 0 && navigationIndex < options.length) {
      return options[navigationIndex];
    }

    if (!filterText.trim()) {
      return selectedValue ? findOptionByValue(selectedValue) ?? null : null;
    }

    const match = findMatchingOption(filterText);
    if (match) {
      return match;
    }

    if (lastMatchedValue) {
      return findOptionByValue(lastMatchedValue) ?? null;
    }

    return selectedValue ? findOptionByValue(selectedValue) ?? null : null;
  }

  // ============================================================================
  // Event Handlers
  // ============================================================================

  /**
   * Handles typing input: updates filter text and selects matching option if found.
   */
  function handleTyping(key: string): void {
    const newFilterText = filterText + key;
    setFilterText(newFilterText);
    setNavigationIndex(null);
    setIsOpen(true);

    const match = findMatchingOption(newFilterText);
    if (match) {
      updateSelectedValue(getOptionValue(match));
    }
  }

  /**
   * Opens dropdown if closed, then navigates in the specified direction.
   */
  function handleArrowNavigation(direction: "next" | "prev"): void {
    if (!isOpen) {
      setIsOpen(true);
    }
    navigateOptions(direction);
  }

  /**
   * Handles keyboard input for filtering: updates filter text and opens dropdown.
   * Input field itself is read-only, so we capture keydown events for filtering.
   */
  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>): void {
    if (e.key === "Backspace" || e.key === "Delete") {
      e.preventDefault();
      return;
    }

    if (e.key === "Enter") {
      e.preventDefault();
      if (!isOpen) {
        setIsOpen(true);
        return;
      }

      const highlighted = getHighlightedOption();
      if (highlighted) {
        handleOptionSelect(highlighted);
      }
      return;
    }

    if (e.key === "Escape") {
      setIsOpen(false);
      clearFilterAndNavigation();
      inputRef.current?.blur();
      return;
    }

    if (e.key === "Tab") {
      if (!isOpen) {
        return;
      }
      e.preventDefault();
      navigateOptions("next");
      return;
    }

    if (e.key === "ArrowDown") {
      e.preventDefault();
      handleArrowNavigation("next");
      return;
    }

    if (e.key === "ArrowUp") {
      e.preventDefault();
      handleArrowNavigation("prev");
      return;
    }

    if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      e.preventDefault();
      handleTyping(e.key);
    }
  }

  /**
   * Handles blur: clears filter text and closes dropdown.
   */
  function handleBlur(e: FocusEvent<HTMLInputElement>): void {
    setIsOpen(false);
    clearFilterAndNavigation();
    setLastMatchedValue("");
    registerProps.onBlur(e);
  }

  /**
   * Handles option selection: updates selected value, closes dropdown, and saves as last valid value.
   */
  function handleOptionSelect(option: T): void {
    updateSelectedValue(getOptionValue(option));
    clearFilterAndNavigation();
    setIsOpen(false);
  }

  /**
   * Handles mouse enter on an option: updates selected value and navigation index.
   */
  function handleOptionMouseEnter(optionValue: string, index: number): void {
    updateSelectedValue(optionValue);
    setNavigationIndex(index);
    setFilterText("");
  }

  // ============================================================================
  // UI Helpers
  // ============================================================================

  /**
   * Gets the CSS classes for the visible input field based on its state.
   */
  function getInputClasses(): string {
    const borderClass = isOpen ? "border-primary" : "";
    const errorClass = error ? COMBOBOX_INPUT_ERROR_CLASS : "";
    return `${COMBOBOX_INPUT_BASE_CLASS} cursor-pointer pr-10 placeholder:text-muted-foreground/50 ${borderClass} ${errorClass}`.trim();
  }

  /**
   * Gets the CSS classes for an option button based on its state.
   */
  function getOptionButtonClasses(isHighlighted: boolean, isSelected: boolean): string {
    const baseClasses =
      "w-full px-3 py-2 text-left transition-colors focus:bg-primary focus:text-primary-foreground focus:outline-none";

    if (isHighlighted) {
      return `${baseClasses} bg-primary text-primary-foreground`;
    }
    if (isSelected) {
      return `${baseClasses} bg-muted text-foreground`;
    }
    return `${baseClasses} text-foreground hover:bg-primary hover:text-primary-foreground`;
  }

  // ============================================================================
  // Initialization
  // ============================================================================

  /**
   * Initializes the selected value from the form's default value.
   */
  function initializeFromFormValue(): void {
    if (!inputRef.current?.value) return;

    const formValue = inputRef.current.value;
    const matchingOption = findOptionByValue(formValue);

    if (matchingOption && selectedValue !== formValue) {
      updateSelectedValue(formValue);
    }
  }

  /**
   * Merges the register ref with our input ref so react-hook-form can control the input.
   * Also initializes the input value from the form's default value when the ref is first set.
   */
  function setInputRef(element: HTMLInputElement | null): void {
    inputRef.current = element;

    if (registerRef) {
      if (typeof registerRef === "function") {
        registerRef(element);
      } else {
        registerRef.current = element;
      }
    }

    if (element?.value && !selectedValue) {
      requestAnimationFrame(() => {
        const formValue = element?.value;
        if (formValue) {
          const matchingOption = findOptionByValue(formValue);
          if (matchingOption) {
            updateSelectedValue(formValue);
          }
        }
      });
    }
  }

  // ============================================================================
  // Effects
  // ============================================================================

  useEffect(() => {
    function handleClickOutside(event: MouseEvent): void {
      const target = event.target as Node;
      const isOutsideDropdown = !dropdownRef.current?.contains(target);
      const isOutsideInput = !inputRef.current?.contains(target);

      if (isOutsideDropdown && isOutsideInput) {
        setIsOpen(false);
        clearFilterAndNavigation();
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    initializeFromFormValue();
    const timeout = setTimeout(initializeFromFormValue, INITIALIZATION_DELAY_MS);
    return () => clearTimeout(timeout);
  }, [options, getOptionValue, selectedValue]);

  // ============================================================================
  // Render
  // ============================================================================

  const highlightedOption = getHighlightedOption();
  const highlightedValue = highlightedOption ? getOptionValue(highlightedOption) : null;
  const displayOption = selectedValue ? findOptionByValue(selectedValue) : null;
  const displayLabel = displayOption ? getOptionLabel(displayOption) : "";

  useEffect(() => {
    if (isOpen && highlightedOptionRef.current) {
      highlightedOptionRef.current.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
    }
  }, [highlightedValue, isOpen]);

  return (
    <div className="relative">
      <input
        type="hidden"
        ref={setInputRef}
        name={registerProps.name}
        value={selectedValue || ""}
        onChange={(e) => {
          const newValue = e.target.value;
          if (newValue !== selectedValue) {
            updateSelectedValue(newValue);
          }
          registerProps.onChange(e);
        }}
        onBlur={handleBlur}
      />
      <div className="relative">
        <input
          id={id}
          type="text"
          value={displayLabel}
          readOnly
          onFocus={clearFilterAndNavigation}
          onKeyDown={handleKeyDown}
          onClick={() => {
            clearFilterAndNavigation();
            setIsOpen(true);
          }}
          placeholder={placeholder}
          required={required}
          className={getInputClasses()}
        />
        <ChevronIcon isOpen={isOpen} />
      </div>
      {isOpen && (
        <div
          ref={dropdownRef}
          className="absolute z-50 mt-1 max-h-48 w-full overflow-auto border-2 border-border bg-secondary font-mono text-sm shadow-lg"
        >
          {options.map((option, index) => {
            const optionValue = getOptionValue(option);
            const isHighlighted = highlightedValue === optionValue;
            const isSelected = selectedValue === optionValue;

            return (
              <button
                key={`${optionValue}-${index}`}
                ref={isHighlighted ? highlightedOptionRef : null}
                type="button"
                onMouseEnter={() => handleOptionMouseEnter(optionValue, index)}
                onClick={() => handleOptionSelect(option)}
                className={getOptionButtonClasses(isHighlighted, isSelected)}
              >
                {getOptionLabel(option)}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
