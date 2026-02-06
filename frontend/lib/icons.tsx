/**
 * Skull icon component displaying ASCII art "(^.^)" for the pirate-themed UI.
 * Renders as an inline span with optional className for styling.
 */
export function SkullIcon({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-block ${className}`} aria-hidden="true">
      {"(^.^)"}
    </span>
  );
}

/**
 * Treasure chest icon component displaying ASCII art "[*]" for the pirate-themed UI.
 * Renders as an inline span with optional className for styling.
 */
export function TreasureIcon({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-block ${className}`} aria-hidden="true">
      {"[*]"}
    </span>
  );
}
