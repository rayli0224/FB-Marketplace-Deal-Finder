"use client";

import { SkullIcon } from "@/lib/icons";

type AppState = "setup" | "form" | "loading" | "done" | "error";

export interface AppHeaderProps {
  appState: AppState;
}

/**
 * Returns the status message text for a given app state.
 * Provides pirate-themed status messages that match the current application state.
 */
function getStatusMessage(appState: AppState): string {
  const messages: Record<AppState, string> = {
    setup: "SETTING SAIL",
    form: "AWAITING ORDERS",
    loading: "RAIDING...",
    done: "TREASURE ACQUIRED",
    error: "MISSION FAILED",
  };
  return messages[appState];
}

/**
 * Header component displaying the application title, icon, and current status.
 * Shows pirate-themed branding with a status badge that reflects the current app state.
 */
export function AppHeader({ appState }: AppHeaderProps) {
  return (
    <header className="mb-8 text-center">
      <div className="mb-4 text-4xl">
        <SkullIcon className="text-accent" />
      </div>
      <h1 className="mb-2 font-mono text-2xl font-bold tracking-tight text-foreground md:text-3xl">
        <span className="text-primary">{">"}</span> LOOT FINDER <span className="text-primary">{"<"}</span>
      </h1>
      <p className="font-mono text-sm text-muted-foreground">
        {"// hack the marketplace, steal the deals ~"}
      </p>
      <div className="mt-4 inline-block border border-border bg-card px-3 py-1">
        <span className="font-mono text-xs text-accent">STATUS: </span>
        <span className="font-mono text-xs text-primary">
          {getStatusMessage(appState)}
        </span>
      </div>
    </header>
  );
}

