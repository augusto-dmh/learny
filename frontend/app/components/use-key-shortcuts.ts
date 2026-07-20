"use client";

/**
 * Single-key shortcuts (CAP-28..33, AD-141) — one guarded global `keydown`
 * listener, in one place.
 *
 * The app had no shortcut precedent before this cycle, which makes the *guard*
 * the load-bearing part rather than the dispatch. Two rules keep a bare letter
 * key from ever hijacking something the student meant to type:
 *
 * - any of Ctrl / Meta / Alt held → the event is not ours. This is also what
 *   keeps the vendored sidebar's Cmd/Ctrl+B working; `b` is never bound here
 *   either way (`components/ui/sidebar.tsx`).
 * - the event target is an `input`, a `textarea`, or a contenteditable region →
 *   the student is writing, and a letter is a letter. Typing "h" into a note body
 *   must never create a highlight.
 *
 * Callers scope the listener further with `enabled`: the reader binds its keys
 * only while the capture popover is open, so a bare press with nothing selected
 * cannot fire an action the student has no on-screen evidence of.
 *
 * Bindings are read through a ref, so a caller may pass a fresh object every
 * render — closing over current state — without the listener being torn down and
 * re-attached. The listener itself is registered once per `enabled` change and
 * removed on unmount, mirroring the polling hooks' cleanup discipline.
 */

import { useEffect, useRef } from "react";

/** Key (lowercased; `" "` normalized to `"space"`) → the action it performs. */
export type ShortcutBindings = Record<string, () => void>;

export function useKeyShortcuts(
  bindings: ShortcutBindings,
  enabled: boolean,
): void {
  const latest = useRef(bindings);
  useEffect(() => {
    latest.current = bindings;
  });

  useEffect(() => {
    if (!enabled) {
      return;
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.ctrlKey || event.metaKey || event.altKey) {
        return;
      }
      if (isTypingTarget(event.target)) {
        return;
      }
      const handler = latest.current[normalizeKey(event.key)];
      if (!handler) {
        return;
      }
      event.preventDefault();
      handler();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [enabled]);
}

/** `" "` → `"space"`; everything else lowercased so `H` and `h` are one binding. */
function normalizeKey(key: string): string {
  return key === " " ? "space" : key.toLowerCase();
}

/**
 * Whether the event landed somewhere the student is writing. `contenteditable`
 * is matched by attribute rather than by the `isContentEditable` property, which
 * jsdom does not compute — and an explicit `contenteditable="false"` is excluded,
 * since that region is not editable at all.
 */
function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  const tag = target.tagName.toLowerCase();
  if (tag === "input" || tag === "textarea") {
    return true;
  }
  return target.closest('[contenteditable]:not([contenteditable="false"])') !== null;
}
