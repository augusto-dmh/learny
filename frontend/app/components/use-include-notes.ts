"use client";

/**
 * Device-local "include my notes" preference for the Ask and Teach surfaces (NL-04).
 *
 * Whether an answer may draw on the reader's own notes is a per-surface reader
 * preference, not book or account state, so — like the reading settings (AD-125) —
 * it lives in versioned `localStorage` under `learny.include-notes.v1`. The two
 * surfaces are stored independently because their server defaults differ (AD-147):
 * Q&A includes notes by default, teaching does not.
 *
 * The key distinction this hook draws is *chosen* vs *not chosen*: until the reader
 * flips the toggle there is no stored value, `chosen` is false, and the request
 * MUST omit the flag so the server applies its own default. Once flipped, the
 * choice persists and every request carries it explicitly. `includeNotes` is only
 * for display — the surface's server default when unchosen, the stored value after.
 * When storage is unavailable (private mode) the choice still works for the session,
 * held in memory; only persistence is lost.
 */

import { useCallback, useState } from "react";

/** Versioned key so a future shape change can migrate forward cheaply. */
export const INCLUDE_NOTES_KEY = "learny.include-notes.v1";

export type NotesSurface = "ask" | "teach";

/** Server-owned defaults per surface (AD-147): Q&A on, teaching off. */
const SURFACE_DEFAULTS: Record<NotesSurface, boolean> = { ask: true, teach: false };

/** The stored choices; a surface key is absent until the reader chooses. */
type StoredChoices = { ask?: boolean; teach?: boolean };

/** Read the stored choices, keeping only well-typed booleans (stale/hand-edited
 * keys fall back to "unchosen" rather than being trusted). */
function loadChoices(): StoredChoices {
  try {
    const raw = localStorage.getItem(INCLUDE_NOTES_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const choices: StoredChoices = {};
    if (typeof parsed.ask === "boolean") {
      choices.ask = parsed.ask;
    }
    if (typeof parsed.teach === "boolean") {
      choices.teach = parsed.teach;
    }
    return choices;
  } catch {
    return {};
  }
}

export type UseIncludeNotes = {
  /** The value to display: the surface's server default until chosen, then the stored choice. */
  includeNotes: boolean;
  /** Whether the reader has made an explicit choice (drives whether the flag is sent). */
  chosen: boolean;
  /** Record an explicit choice (persisted); from now on the flag is sent. */
  setIncludeNotes: (value: boolean) => void;
};

export function useIncludeNotes(surface: NotesSurface): UseIncludeNotes {
  // Lazy initializer so a stored choice applies on the first frame; guarded for
  // the SSR pass where `window` is absent.
  const [choices, setChoices] = useState<StoredChoices>(() =>
    typeof window === "undefined" ? {} : loadChoices(),
  );

  const setIncludeNotes = useCallback(
    (value: boolean) => {
      setChoices((prev) => {
        const next = { ...prev, [surface]: value };
        try {
          localStorage.setItem(INCLUDE_NOTES_KEY, JSON.stringify(next));
        } catch {
          // Private mode: keep the choice in memory for the session.
        }
        return next;
      });
    },
    [surface],
  );

  const chosenValue = choices[surface];
  return {
    includeNotes: chosenValue ?? SURFACE_DEFAULTS[surface],
    chosen: chosenValue !== undefined,
    setIncludeNotes,
  };
}
