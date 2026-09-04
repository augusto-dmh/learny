"use client";

import { useEffect, useState } from "react";

/** Tailwind `lg` — first width that is not a phone column (AD-280). */
export const LG_MIN_WIDTH_PX = 1024;

const BELOW_LG_QUERY = `(max-width: ${LG_MIN_WIDTH_PX - 1}px)`;

/**
 * Whether the viewport is below Tailwind `lg` (1024px).
 *
 * Starts `false` so SSR and the first client paint match the overlay side dock
 * (T10 / AD-279). jsdom has no `matchMedia` unless a test stubs it; missing
 * `matchMedia` stays on the side dock so existing tests do not throw.
 */
export function useBelowLg(): boolean {
  const [belowLg, setBelowLg] = useState(false);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") {
      return;
    }
    const mql = window.matchMedia(BELOW_LG_QUERY);
    const onChange = () => {
      setBelowLg(mql.matches);
    };
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  return belowLg;
}
