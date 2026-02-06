"use client";

/**
 * Footer component displaying pirate-themed copyright and attribution text.
 * Simple static footer with no props or state.
 */
export function AppFooter() {
  return (
    <footer className="mt-8 text-center">
      <p className="font-mono text-xs text-muted-foreground">
        {"/* "} frontend only - no actual piracy involved {" */"}
      </p>
      <p className="mt-2 font-mono text-xs text-muted-foreground/50">
        made with {"<3"} by digital pirates
      </p>
    </footer>
  );
}

