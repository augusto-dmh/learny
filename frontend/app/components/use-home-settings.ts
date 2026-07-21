"use client";

/**
 * Device-local Home settings (RFC-004 Cycle E — HOME-14, AD-155).
 *
 * Whether the adherence stats block (streak + heatmap) is shown is the viewer's
 * own preference, not account state: RFC-004 keeps it device-local (AD-147
 * precedent — no per-user preferences table), so it lives in versioned
 * `localStorage` under `learny.home.v1`, defaulting to shown. A stored value of
 * the wrong shape falls back to the default rather than being trusted, so a
 * hand-edited or stale key can never wedge the block into an unexpected state.
 * When storage is unavailable (private mode) the toggle still works for the
 * session, held in memory; only persistence is lost.
 *
 * Mirrors `use-reading-settings` (RD-21): a lazy first-render read (no flash of
 * the default), SSR-guarded, and a single setter.
 */

import { useCallback, useState } from "react";

/** Versioned key so a future shape change can migrate forward cheaply. */
export const HOME_SETTINGS_KEY = "learny.home.v1";

export type HomeSettings = { showStats: boolean };

/** Untouched default: the adherence block is visible (AD-155). */
export const HOME_DEFAULTS: HomeSettings = { showStats: true };

/** Coerce arbitrary stored JSON into valid settings, defaulting each field. */
function clampSettings(raw: unknown): HomeSettings {
  if (typeof raw !== "object" || raw === null) {
    return HOME_DEFAULTS;
  }
  const record = raw as Record<string, unknown>;
  return {
    showStats:
      typeof record.showStats === "boolean"
        ? record.showStats
        : HOME_DEFAULTS.showStats,
  };
}

/** Read + clamp the stored settings, falling back to defaults on any failure. */
function loadSettings(): HomeSettings {
  try {
    const raw = localStorage.getItem(HOME_SETTINGS_KEY);
    return raw ? clampSettings(JSON.parse(raw)) : HOME_DEFAULTS;
  } catch {
    return HOME_DEFAULTS;
  }
}

export type UseHomeSettings = HomeSettings & {
  setShowStats: (showStats: boolean) => void;
};

export function useHomeSettings(): UseHomeSettings {
  // Lazy initializer so the stored choice applies on the first painted frame (no
  // flash of the default); guarded for the SSR pass where `window` is absent.
  const [settings, setSettings] = useState<HomeSettings>(() =>
    typeof window === "undefined" ? HOME_DEFAULTS : loadSettings(),
  );

  const setShowStats = useCallback((showStats: boolean) => {
    setSettings(() => {
      const next = { showStats };
      try {
        localStorage.setItem(HOME_SETTINGS_KEY, JSON.stringify(next));
      } catch {
        // Private mode: keep the change in memory for the session.
      }
      return next;
    });
  }, []);

  return { ...settings, setShowStats };
}
