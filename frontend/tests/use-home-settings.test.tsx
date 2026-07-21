// @vitest-environment jsdom

/**
 * T6 (HOME-14, AD-155) — device-local Home settings. The hide-stats toggle
 * defaults to shown, persists a change under the versioned key so a reload
 * re-applies it, ignores a stored value of the wrong shape (falling back to the
 * default), and keeps working in memory when `localStorage` throws (private mode)
 * — losing only persistence.
 */

import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  HOME_DEFAULTS,
  HOME_SETTINGS_KEY,
  useHomeSettings,
} from "../app/components/use-home-settings";

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("useHomeSettings default (AD-155)", () => {
  it("starts with the stats block visible when nothing is stored", () => {
    const { result } = renderHook(() => useHomeSettings());
    expect(result.current.showStats).toBe(true);
    expect(HOME_DEFAULTS).toEqual({ showStats: true });
  });
});

describe("useHomeSettings persistence (HOME-14)", () => {
  it("persists the hidden choice under the versioned key and re-applies it on reload", () => {
    const first = renderHook(() => useHomeSettings());
    act(() => first.result.current.setShowStats(false));

    // The change is written under the versioned key as one JSON blob.
    expect(JSON.parse(localStorage.getItem(HOME_SETTINGS_KEY)!)).toEqual({
      showStats: false,
    });

    // A fresh hook instance (a reload) reads the stored choice straight back.
    const reloaded = renderHook(() => useHomeSettings());
    expect(reloaded.result.current.showStats).toBe(false);
  });
});

describe("useHomeSettings clamping", () => {
  it("falls back to the default when the stored value is the wrong shape", () => {
    localStorage.setItem(HOME_SETTINGS_KEY, JSON.stringify({ showStats: "nope" }));
    const { result } = renderHook(() => useHomeSettings());
    expect(result.current.showStats).toBe(true);
  });

  it("falls back to the default when the stored JSON is corrupt", () => {
    localStorage.setItem(HOME_SETTINGS_KEY, "{not json");
    const { result } = renderHook(() => useHomeSettings());
    expect(result.current.showStats).toBe(true);
  });
});

describe("useHomeSettings storage-unavailable fallback (spec edge)", () => {
  it("keeps a change in memory for the session when persistence throws", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("QuotaExceededError");
    });
    const { result } = renderHook(() => useHomeSettings());

    // The setter must not throw and the value must update in memory...
    act(() => result.current.setShowStats(false));
    expect(result.current.showStats).toBe(false);
    // ...but nothing was persisted (the throw was swallowed).
    expect(localStorage.getItem(HOME_SETTINGS_KEY)).toBeNull();
  });
});
