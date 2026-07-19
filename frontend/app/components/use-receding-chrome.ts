"use client";

/**
 * Receding reader chrome (RD-31).
 *
 * Returns whether the reader's top bar should be hidden: scrolling down past a
 * small threshold recedes it, scrolling back up restores it. The listener is
 * capture-phase on `window` so it catches the reader's inner scroll container
 * (the page's scrollable `<main>`) as well as plain document scroll — scroll
 * events do not bubble, but a capturing listener still sees a descendant's.
 *
 * Motion is left entirely to CSS: the bar carries a transform transition guarded
 * by `motion-reduce:transition-none`, so a reduced-motion reader gets the same
 * show/hide with no animation (RD-31). This hook only decides the boolean.
 */

import { useEffect, useRef, useState } from "react";

export function useRecedingChrome(threshold = 8): boolean {
  const [hidden, setHidden] = useState(false);
  const lastY = useRef(0);

  useEffect(() => {
    function onScroll(event: Event) {
      const target = event.target;
      const y = target instanceof HTMLElement ? target.scrollTop : window.scrollY;
      const delta = y - lastY.current;
      // Ignore sub-threshold jitter so a resting reader never flickers the bar.
      if (Math.abs(delta) < threshold) {
        return;
      }
      // Hide only while moving down and clear of the very top, so the bar is
      // always present at the head of the chapter.
      setHidden(delta > 0 && y > threshold);
      lastY.current = y;
    }
    window.addEventListener("scroll", onScroll, true);
    return () => window.removeEventListener("scroll", onScroll, true);
  }, [threshold]);

  return hidden;
}
