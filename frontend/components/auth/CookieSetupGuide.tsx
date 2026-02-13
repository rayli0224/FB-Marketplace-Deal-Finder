"use client";

import { useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const FACEBOOK_URL = "https://www.facebook.com";

export interface CookieSetupGuideProps {
  onSuccess: () => void;
  /** Optional message to show at the top, e.g. when redirected here after a session expiry. */
  sessionExpiredMessage?: string | null;
}

/**
 * Guides the user through connecting their Facebook account by pasting exported cookies.
 * Shows step-by-step instructions for installing a browser extension, logging into Facebook,
 * exporting login data, and pasting it into the app. Submits to the backend for validation
 * and saving. Calls onSuccess when cookies are saved successfully.
 * If sessionExpiredMessage is provided, shows a warning banner at the top explaining why
 * the user was sent back here.
 */
export function CookieSetupGuide({ onSuccess, sessionExpiredMessage }: CookieSetupGuideProps) {
  const [cookieText, setCookieText] = useState("");
  const [status, setStatus] = useState<"idle" | "saving" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState("");

  async function handleSave() {
    if (!cookieText.trim()) return;

    setStatus("saving");
    setErrorMessage("");

    try {
      const response = await fetch(`${API_URL}/api/cookies`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cookies: cookieText.trim() }),
      });

      const data = await response.json();

      if (data.success) {
        onSuccess();
      } else {
        setStatus("error");
        setErrorMessage(data.error || "Something went wrong. Try again.");
      }
    } catch {
      setStatus("error");
      setErrorMessage("Can't reach the app. Make sure it's running and try again.");
    }
  }

  return (
    <div className="space-y-6">
      <div className="text-center mb-2">
        <div className="mb-3 text-4xl">🔐</div>
        <h2 className="mb-1 font-mono text-lg font-bold text-primary">
          CONNECT YER FACEBOOK
        </h2>
        <p className="font-mono text-xs text-muted-foreground">
          {"// one-time setup to access the marketplace"}
        </p>
      </div>

      {/* Session expired banner */}
      {sessionExpiredMessage && (
        <div className="border border-accent/50 bg-accent/10 p-3 text-center">
          <p className="font-mono text-xs text-accent font-bold">{sessionExpiredMessage}</p>
        </div>
      )}

      {/* Steps */}
      <div className="space-y-4 font-mono text-sm">
        <div className="border border-border bg-secondary/50 p-4">
          <div className="flex items-start gap-3">
            <span className="text-accent font-bold shrink-0">01.</span>
            <div>
              <p className="text-foreground font-bold mb-1">Install a browser add-on</p>
              <p className="text-muted-foreground text-xs leading-relaxed">
                Install{" "}
                <a
                  href="https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary underline hover:text-accent transition-colors"
                >
                  Cookie-Editor
                </a>{" "}
                (Chrome/Edge) or{" "}
                <a
                  href="https://addons.mozilla.org/en-US/firefox/addon/cookie-editor/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary underline hover:text-accent transition-colors"
                >
                  Cookie-Editor for Firefox
                </a>
                .
              </p>
            </div>
          </div>
        </div>

        <div className="border border-border bg-secondary/50 p-4">
          <div className="flex items-start gap-3">
            <span className="text-accent font-bold shrink-0">02.</span>
            <div>
              <p className="text-foreground font-bold mb-1">Log into Facebook</p>
              <p className="text-muted-foreground text-xs leading-relaxed mb-3">
                Click the button below to open Facebook and sign in with your account.
              </p>
              <button
                type="button"
                onClick={() => window.open(FACEBOOK_URL, "_blank", "noopener,noreferrer")}
                className="border border-primary bg-primary/10 text-primary hover:bg-primary hover:text-primary-foreground px-3 py-1.5 font-mono text-xs font-bold uppercase transition-colors"
              >
                Open Facebook →
              </button>
            </div>
          </div>
        </div>

        <div className="border border-border bg-secondary/50 p-4">
          <div className="flex items-start gap-3">
            <span className="text-accent font-bold shrink-0">03.</span>
            <div>
              <p className="text-foreground font-bold mb-1">Export your login data as JSON</p>
              <p className="text-muted-foreground text-xs leading-relaxed">
                While on facebook.com, click the Cookie-Editor icon in your browser toolbar,
                then click <span className="text-foreground font-bold">Export</span> (the download arrow at the bottom)
                and choose <span className="text-foreground font-bold">JSON</span>. That copies the data to your clipboard.
              </p>
            </div>
          </div>
        </div>

        <div className="border border-border bg-secondary/50 p-4">
          <div className="flex items-start gap-3">
            <span className="text-accent font-bold shrink-0">04.</span>
            <div>
              <p className="text-foreground font-bold mb-1">Paste it below</p>
              <p className="text-muted-foreground text-xs leading-relaxed">
                Paste what you just copied into the box below and hit Save.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Paste area */}
      <div>
        <textarea
          className="w-full h-32 border-2 border-border bg-input p-3 font-mono text-xs text-foreground placeholder:text-muted-foreground/50 focus:border-primary focus:outline-none resize-none"
          placeholder='Paste your exported data here...'
          value={cookieText}
          onChange={(e) => {
            setCookieText(e.target.value);
            if (status === "error") {
              setStatus("idle");
              setErrorMessage("");
            }
          }}
        />
      </div>

      {/* Error message */}
      {status === "error" && errorMessage && (
        <div className="border border-destructive/50 bg-destructive/10 p-3">
          <p className="font-mono text-xs text-destructive">{errorMessage}</p>
        </div>
      )}

      {/* Save button */}
      <button
        type="button"
        onClick={handleSave}
        disabled={!cookieText.trim() || status === "saving"}
        className={`group w-full border-2 px-4 py-3 font-mono text-sm font-bold uppercase tracking-wide transition-all ${
          cookieText.trim() && status !== "saving"
            ? "border-primary bg-primary text-primary-foreground hover:bg-transparent hover:text-primary cursor-pointer"
            : "border-muted bg-muted text-muted-foreground cursor-not-allowed opacity-50"
        }`}
      >
        <span className={`inline-block transition-transform ${cookieText.trim() && status !== "saving" ? "group-hover:translate-x-1" : ""}`}>
          {status === "saving" ? "SAVING..." : ">>> SAVE & CONTINUE <<<"}
        </span>
      </button>

      {/* Security note */}
      <p className="font-mono text-[10px] text-muted-foreground/60 text-center leading-relaxed">
        Your login data stays on this device and is never sent anywhere except to search Facebook Marketplace on your behalf.
      </p>
    </div>
  );
}
