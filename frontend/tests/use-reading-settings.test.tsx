// @vitest-environment jsdom

/**
 * C1 (RD-18/21, RD-06) — device-local reading settings. The hook exposes the
 * current size/spacing/appearance with the untouched defaults, persists a change
 * under the versioned key so a reload re-applies it, clamps a stored value
 * outside the allowed steps back to the default, and keeps working in memory when
 * `localStorage` throws (private mode) — losing only persistence.
 */

import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  READING_DEFAULTS,
  READING_SETTINGS_KEY,
  useReadingSettings,
} from "../app/components/use-reading-settings";

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("useReadingSettings defaults (RD-06)", () => {
  it("starts at the untouched defaults when nothing is stored", () => {
    const { result } = renderHook(() => useReadingSettings());
    expect(result.current.size).toBe(19);
    expect(result.current.leading).toBe(1.6);
    expect(result.current.appearance).toBe("default");
    expect(READING_DEFAULTS).toEqual({ size: 19, leading: 1.6, appearance: "default" });
  });
});

describe("useReadingSettings persistence (RD-21)", () => {
  it("persists each changed axis under the versioned key and re-applies it on reload", () => {
    const first = renderHook(() => useReadingSettings());
    act(() => first.result.current.setSize(23));
    act(() => first.result.current.setLeading(1.8));
    act(() => first.result.current.setAppearance("paper"));

    // The change is written under the versioned key as one JSON blob.
    expect(JSON.parse(localStorage.getItem(READING_SETTINGS_KEY)!)).toEqual({
      size: 23,
      leading: 1.8,
      appearance: "paper",
    });

    // A fresh hook instance (a reload) reads the stored settings straight back.
    const reloaded = renderHook(() => useReadingSettings());
    expect(reloaded.result.current.size).toBe(23);
    expect(reloaded.result.current.leading).toBe(1.8);
    expect(reloaded.result.current.appearance).toBe("paper");
  });
});

describe("useReadingSettings clamping", () => {
  it("clamps a stored value outside the allowed steps back to the default", () => {
    localStorage.setItem(
      READING_SETTINGS_KEY,
      JSON.stringify({ size: 99, leading: 3.2, appearance: "neon" }),
    );
    const { result } = renderHook(() => useReadingSettings());
    expect(result.current.size).toBe(19);
    expect(result.current.leading).toBe(1.6);
    expect(result.current.appearance).toBe("default");
  });

  it("falls back to defaults when the stored JSON is corrupt", () => {
    localStorage.setItem(READING_SETTINGS_KEY, "{not json");
    const { result } = renderHook(() => useReadingSettings());
    expect(result.current.size).toBe(19);
    expect(result.current.leading).toBe(1.6);
    expect(result.current.appearance).toBe("default");
  });
});

describe("useReadingSettings storage-unavailable fallback (spec edge)", () => {
  it("keeps a change in memory for the session when persistence throws", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("QuotaExceededError");
    });
    const { result } = renderHook(() => useReadingSettings());

    // The setter must not throw and the value must update in memory...
    act(() => result.current.setSize(21));
    expect(result.current.size).toBe(21);
    // ...but nothing was persisted (the throw was swallowed).
    expect(localStorage.getItem(READING_SETTINGS_KEY)).toBeNull();
  });
});
