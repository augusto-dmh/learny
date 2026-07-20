// @vitest-environment jsdom

/**
 * T6 (NL-04) — the include-my-notes preference. The hook exposes each surface's
 * server default until the reader chooses (Ask on, Teach off), reports whether a
 * choice has been made (which gates whether the request sends the flag at all),
 * persists a choice under the versioned key so a reload re-applies it, and keeps
 * the two surfaces independent.
 */

import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  INCLUDE_NOTES_KEY,
  useIncludeNotes,
} from "../app/components/use-include-notes";

afterEach(() => {
  localStorage.clear();
});

describe("useIncludeNotes defaults (NL-04)", () => {
  it("defaults Ask on and Teach off, unchosen, before any choice", () => {
    const ask = renderHook(() => useIncludeNotes("ask"));
    const teach = renderHook(() => useIncludeNotes("teach"));

    // The displayed value mirrors each surface's server default…
    expect(ask.result.current.includeNotes).toBe(true);
    expect(teach.result.current.includeNotes).toBe(false);
    // …and neither is "chosen" yet, so the request omits the flag entirely.
    expect(ask.result.current.chosen).toBe(false);
    expect(teach.result.current.chosen).toBe(false);
    // Nothing is written until the reader chooses.
    expect(localStorage.getItem(INCLUDE_NOTES_KEY)).toBeNull();
  });
});

describe("useIncludeNotes persistence (NL-04)", () => {
  it("persists a choice under the versioned key and re-applies it on reload", () => {
    const first = renderHook(() => useIncludeNotes("ask"));
    act(() => first.result.current.setIncludeNotes(false));

    // The choice takes effect and is now marked chosen (so the flag is sent).
    expect(first.result.current.includeNotes).toBe(false);
    expect(first.result.current.chosen).toBe(true);
    expect(localStorage.getItem(INCLUDE_NOTES_KEY)).toBe(
      JSON.stringify({ ask: false }),
    );

    // A fresh mount reads the persisted choice.
    const reloaded = renderHook(() => useIncludeNotes("ask"));
    expect(reloaded.result.current.includeNotes).toBe(false);
    expect(reloaded.result.current.chosen).toBe(true);
  });

  it("keeps the two surfaces independent", () => {
    const ask = renderHook(() => useIncludeNotes("ask"));
    act(() => ask.result.current.setIncludeNotes(false));

    // Choosing on Ask leaves Teach at its own default, still unchosen.
    const teach = renderHook(() => useIncludeNotes("teach"));
    expect(teach.result.current.includeNotes).toBe(false);
    expect(teach.result.current.chosen).toBe(false);
  });
});
