"use client";

/** Radar container (circle, border, background). */
const RADAR_CONTAINER_CLASS =
  "relative h-24 w-24 shrink-0 overflow-hidden rounded-full border-2 border-primary/80 bg-secondary";

/** Radar sweep line (hand). */
const RADAR_SWEEP_LINE_CLASS =
  "absolute left-1/2 top-1/2 h-0.5 w-1/2 origin-left -translate-y-1/2 bg-accent";

/** Radar center dot. */
const RADAR_CENTER_DOT_CLASS =
  "absolute left-1/2 top-1/2 h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent";

const SWEEP_ROTATION_DURATION_S = 3;
const TRANSFORM_ORIGIN_CENTER = "50% 50%";
const ROTATE_KEYFRAME_NAME = "heist-radar-rotate";

/**
 * Pirate radar animation for the loading timer.
 * Sweep hand and center dot.
 */
export function HeistTimerAnimation() {
  const keyframesCss = `@keyframes ${ROTATE_KEYFRAME_NAME} { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`;
  const animationValue = `${ROTATE_KEYFRAME_NAME} ${SWEEP_ROTATION_DURATION_S}s linear infinite`;

  return (
    <div className={RADAR_CONTAINER_CLASS} aria-hidden>
      <style dangerouslySetInnerHTML={{ __html: keyframesCss }} />
      <div
        className="absolute inset-0"
        style={{
          transformOrigin: TRANSFORM_ORIGIN_CENTER,
          animation: animationValue,
        }}
      >
        <div className={RADAR_SWEEP_LINE_CLASS} />
      </div>
      <div className={RADAR_CENTER_DOT_CLASS} aria-hidden />
    </div>
  );
}
