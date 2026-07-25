"use client";

/**
 * How far the reader has travelled through the section they are reading.
 *
 * The reader's progress figure is a word count: the words before the current
 * section, out of the book's words. That makes it exact at every section
 * boundary — it agrees with the server's stored percent there — but it also
 * makes it a staircase, sitting still through a long section and then jumping.
 * This hook supplies the missing term: the fraction of the current section the
 * viewport has passed, measured from the section's own rendered extent, so the
 * figure moves while the reader reads.
 *
 * It is presentation only. Nothing here is written anywhere: the position the
 * reader saves is still an anchor, and the percent stored against it is still
 * the server's.
 *
 * `headerOffset` is where the reading line sits below the viewport top (the
 * sticky chrome's height), so the fraction is measured against what the reader
 * can actually see. Section ids carry a `#fragment`, so the element is resolved
 * with `getElementById` — a CSS selector could not match it. Where geometry is
 * unavailable (server render, jsdom, a section not yet laid out) the fraction is
 * zero, which leaves the figure exactly as it behaved before: step by step.
 *
 * Measuring is deferred to the next animation frame, and a burst of scroll
 * events collapses into that one frame. A scroll event fires far more often than
 * the screen redraws, and each measurement reads layout and can re-render the
 * whole reader — work no reader could ever see the result of, on the one surface
 * this app exists to keep smooth. A frame is also the honest granularity: the
 * figure cannot update more often than the screen does. The pending frame is
 * cancelled on cleanup, so nothing measures a section the reader has left.
 */

import { useEffect, useState } from "react";

export function useSectionProgress(
  anchor: string | null,
  headerOffset: number,
): number {
  const [fraction, setFraction] = useState(0);

  useEffect(() => {
    setFraction(0);
    if (!anchor) {
      return;
    }
    let frame: number | null = null;
    function measure() {
      frame = null;
      const rect = document.getElementById(anchor!)?.getBoundingClientRect?.();
      if (!rect || rect.height <= 0) {
        setFraction(0);
        return;
      }
      setFraction(clamp((headerOffset - rect.top) / rect.height));
    }
    function schedule() {
      // Already waiting on a frame: this event's position will be read by that
      // one. Every event in a frame therefore costs a single measurement.
      if (frame !== null) {
        return;
      }
      frame = requestAnimationFrame(measure);
    }
    // The first measurement is immediate: the reader arrives mid-section on a
    // deep link and the figure must be right on the first paint, not a frame later.
    measure();
    // Capture-phase, so a scrolling container is heard as well as the page.
    window.addEventListener("scroll", schedule, true);
    window.addEventListener("resize", schedule);
    return () => {
      if (frame !== null) {
        cancelAnimationFrame(frame);
      }
      window.removeEventListener("scroll", schedule, true);
      window.removeEventListener("resize", schedule);
    };
  }, [anchor, headerOffset]);

  return fraction;
}

/**
 * A fraction of the section, in `[0, 1]` — quantized, so a pixel of scroll never
 * re-renders the reader for a change no one could see.
 */
function clamp(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.min(1, Math.max(0, Math.round(value * 1000) / 1000));
}
