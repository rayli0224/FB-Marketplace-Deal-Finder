"use client";

import { useRouter } from "next/navigation";

const YOUTUBE_VIDEO_ID = "8UjWwMtrETk";

/**
 * Page shown after the 5th click on the red close button. Displays a YouTube
 * video (enemy ship attack) and message; button navigates back to the app.
 */
export function SunkView() {
  const router = useRouter();

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-8 bg-background p-6">
      <div className="aspect-video w-full max-w-2xl overflow-hidden rounded border-2 border-border">
        <iframe
          src={`https://www.youtube.com/embed/${YOUTUBE_VIDEO_ID}?autoplay=1`}
          title="Sunk by enemy ship"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
          className="h-full w-full"
        />
      </div>
      <div className="max-w-md text-center">
        <p className="mb-4 font-mono text-xl font-bold text-foreground">
          The enemy ship got ye.
        </p>
        <button
          type="button"
          onClick={() => router.push("/")}
          className="rounded border-2 border-primary bg-primary px-4 py-2 font-mono text-sm text-primary-foreground hover:bg-primary/90 cursor-pointer"
        >
          Go back to loot finder
        </button>
      </div>
    </main>
  );
}
