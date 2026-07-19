"use client";

/**
 * Device-local reading settings (RD-18/21).
 *
 * The reader's type size, line spacing, and appearance (Default / Paper) are the
 * reader's own preference, not book or account state: RFC-004 keeps them
 * device-local, so they live in versioned `localStorage` under
 * `learny.reading.v1` (theme lives in next-themes, not here). A stored value
 * outside the allowed steps is clamped back to the default rather than trusted,
 * so a hand-edited or stale key can never render the book at an absurd size. When
 * storage is unavailable (private mode) the settings still work for the session,
 * held in memory; only persistence is lost (spec edge).
 *
 * The hook returns the current values plus a setter per axis; the reader
 * container consumes them as the `--reading-size` / `--reading-leading` custom
 * properties and the `data-appearance` attribute. Values are read once, lazily,
 * on first render (client-only — the reader mounts after a client fetch), so the
 * stored settings apply on the first painted frame without a flash of defaults.
 */

import { useCallback, useState } from "react";

/** Versioned key so a future shape change can migrate forward cheaply. */
export const READING_SETTINGS_KEY = "learny.reading.v1";

export type ReadingSize = 17 | 19 | 21 | 23;
export type ReadingLeading = 1.5 | 1.6 | 1.8;
export type ReadingAppearance = "default" | "paper";

/** The type-size steps offered by the Aa popover (px), smallest first. */
export const READING_SIZES: readonly ReadingSize[] = [17, 19, 21, 23];
/** The line-spacing steps offered by the Aa popover, tightest first. */
export const READING_LEADINGS: readonly ReadingLeading[] = [1.5, 1.6, 1.8];

export type ReadingSettings = {
  size: ReadingSize;
  leading: ReadingLeading;
  appearance: ReadingAppearance;
};

/** Untouched defaults: the current `.prose-reading` values (RD-06). */
export const READING_DEFAULTS: ReadingSettings = {
  size: 19,
  leading: 1.6,
  appearance: "default",
};

/** Coerce arbitrary stored JSON into valid settings, clamping each axis. */
function clampSettings(raw: unknown): ReadingSettings {
  if (typeof raw !== "object" || raw === null) {
    return READING_DEFAULTS;
  }
  const record = raw as Record<string, unknown>;
  return {
    size: (READING_SIZES as readonly unknown[]).includes(record.size)
      ? (record.size as ReadingSize)
      : READING_DEFAULTS.size,
    leading: (READING_LEADINGS as readonly unknown[]).includes(record.leading)
      ? (record.leading as ReadingLeading)
      : READING_DEFAULTS.leading,
    appearance: record.appearance === "paper" ? "paper" : "default",
  };
}

/** Read + clamp the stored settings, falling back to defaults on any failure. */
function loadSettings(): ReadingSettings {
  try {
    const raw = localStorage.getItem(READING_SETTINGS_KEY);
    return raw ? clampSettings(JSON.parse(raw)) : READING_DEFAULTS;
  } catch {
    return READING_DEFAULTS;
  }
}

export type UseReadingSettings = ReadingSettings & {
  setSize: (size: ReadingSize) => void;
  setLeading: (leading: ReadingLeading) => void;
  setAppearance: (appearance: ReadingAppearance) => void;
};

export function useReadingSettings(): UseReadingSettings {
  // Lazy initializer so the stored settings apply on the first painted frame (no
  // flash of defaults); guarded for the SSR pass where `window` is absent.
  const [settings, setSettings] = useState<ReadingSettings>(() =>
    typeof window === "undefined" ? READING_DEFAULTS : loadSettings(),
  );

  const update = useCallback((patch: Partial<ReadingSettings>) => {
    setSettings((prev) => {
      const next = { ...prev, ...patch };
      try {
        localStorage.setItem(READING_SETTINGS_KEY, JSON.stringify(next));
      } catch {
        // Private mode: keep the change in memory for the session (spec edge).
      }
      return next;
    });
  }, []);

  return {
    ...settings,
    setSize: useCallback((size: ReadingSize) => update({ size }), [update]),
    setLeading: useCallback(
      (leading: ReadingLeading) => update({ leading }),
      [update],
    ),
    setAppearance: useCallback(
      (appearance: ReadingAppearance) => update({ appearance }),
      [update],
    ),
  };
}
