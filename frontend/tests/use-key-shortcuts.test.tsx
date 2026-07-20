// @vitest-environment jsdom

/**
 * E3 gate (hook) — the single guarded `keydown` listener behind the capture and
 * grading shortcuts (CAP-28..33, AD-141).
 *
 * The guard is what is really under test: a bare letter must reach its binding,
 * but the same letter must be inert while any of Ctrl/Meta/Alt is held (CAP-33)
 * or while the student is typing into an input, a textarea, or a contenteditable
 * region (CAP-32). `b` is never a binding, so the vendored sidebar keeps
 * Cmd/Ctrl+B to itself. The listener is registered only while the caller enables
 * it and is removed on unmount, mirroring the polling hooks' cleanup tests.
 */

import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useKeyShortcuts } from "../app/components/use-key-shortcuts";

/** Dispatch a bubbling keydown, optionally from a specific target element. */
function press(
  key: string,
  init: KeyboardEventInit = {},
  target: EventTarget = window,
) {
  const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...init });
  target.dispatchEvent(event);
  return event;
}

/** Mount `el` in the document so events dispatched on it bubble to window. */
function mount(el: HTMLElement): HTMLElement {
  document.body.appendChild(el);
  return el;
}

afterEach(() => {
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

describe("useKeyShortcuts dispatch", () => {
  it("runs the bound action for a bare key press", () => {
    const highlight = vi.fn();
    renderHook(() => useKeyShortcuts({ h: highlight }, true));

    press("h");

    expect(highlight).toHaveBeenCalledTimes(1);
  });

  it("treats an uppercase key as the same binding", () => {
    const card = vi.fn();
    renderHook(() => useKeyShortcuts({ c: card }, true));

    press("C");

    expect(card).toHaveBeenCalledTimes(1);
  });

  it("maps the space bar to the space binding", () => {
    const reveal = vi.fn();
    renderHook(() => useKeyShortcuts({ space: reveal }, true));

    press(" ");

    expect(reveal).toHaveBeenCalledTimes(1);
  });

  it("prevents the browser default only for a key it handles", () => {
    renderHook(() => useKeyShortcuts({ space: vi.fn() }, true));

    // Space would scroll the page; the handled press must claim it.
    expect(press(" ").defaultPrevented).toBe(true);
    // An unbound key is left entirely alone.
    expect(press("x").defaultPrevented).toBe(false);
  });

  it("does nothing for a key that is not bound", () => {
    const highlight = vi.fn();
    renderHook(() => useKeyShortcuts({ h: highlight }, true));

    press("q");

    expect(highlight).not.toHaveBeenCalled();
  });

  it("leaves b alone so the sidebar keeps its own shortcut", () => {
    const action = vi.fn();
    // Even a caller that binds every other letter must not capture `b`.
    renderHook(() => useKeyShortcuts({ h: action, c: action, space: action }, true));

    press("b");
    press("b", { ctrlKey: true });

    expect(action).not.toHaveBeenCalled();
  });

  it("reads the latest bindings without re-registering the listener", () => {
    const first = vi.fn();
    const second = vi.fn();
    const addSpy = vi.spyOn(window, "addEventListener");
    const { rerender } = renderHook(
      ({ action }: { action: () => void }) =>
        useKeyShortcuts({ h: action }, true),
      { initialProps: { action: first } },
    );
    const registrations = addSpy.mock.calls.filter(([type]) => type === "keydown").length;

    rerender({ action: second });
    press("h");

    expect(second).toHaveBeenCalledTimes(1);
    expect(first).not.toHaveBeenCalled();
    expect(
      addSpy.mock.calls.filter(([type]) => type === "keydown").length,
    ).toBe(registrations);
  });
});

describe("useKeyShortcuts guards (CAP-32/33)", () => {
  it.each([
    ["ctrl", { ctrlKey: true }],
    ["meta", { metaKey: true }],
    ["alt", { altKey: true }],
  ])("ignores the key while %s is held", (_name, modifier) => {
    const highlight = vi.fn();
    renderHook(() => useKeyShortcuts({ h: highlight }, true));

    press("h", modifier);

    expect(highlight).not.toHaveBeenCalled();
  });

  it("ignores the key while the student is typing in a textarea", () => {
    const highlight = vi.fn();
    renderHook(() => useKeyShortcuts({ h: highlight }, true));
    const textarea = mount(document.createElement("textarea"));

    press("h", {}, textarea);

    expect(highlight).not.toHaveBeenCalled();
  });

  it("ignores the key while the student is typing in an input", () => {
    const highlight = vi.fn();
    renderHook(() => useKeyShortcuts({ h: highlight }, true));
    const input = mount(document.createElement("input"));

    press("h", {}, input);

    expect(highlight).not.toHaveBeenCalled();
  });

  it("ignores the key inside a contenteditable region", () => {
    const highlight = vi.fn();
    renderHook(() => useKeyShortcuts({ h: highlight }, true));
    const editable = mount(document.createElement("div"));
    editable.setAttribute("contenteditable", "true");
    // A press on a descendant is still the student writing.
    const inner = editable.appendChild(document.createElement("span"));

    press("h", {}, inner);

    expect(highlight).not.toHaveBeenCalled();
  });

  it("still fires from a region explicitly marked not editable", () => {
    const highlight = vi.fn();
    renderHook(() => useKeyShortcuts({ h: highlight }, true));
    const frozen = mount(document.createElement("div"));
    frozen.setAttribute("contenteditable", "false");

    press("h", {}, frozen);

    expect(highlight).toHaveBeenCalledTimes(1);
  });
});

describe("useKeyShortcuts lifecycle", () => {
  it("does not listen while disabled", () => {
    const highlight = vi.fn();
    renderHook(() => useKeyShortcuts({ h: highlight }, false));

    press("h");

    expect(highlight).not.toHaveBeenCalled();
  });

  it("starts and stops listening as the caller flips enabled", () => {
    const highlight = vi.fn();
    const { rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) =>
        useKeyShortcuts({ h: highlight }, enabled),
      { initialProps: { enabled: false } },
    );

    press("h");
    expect(highlight).not.toHaveBeenCalled();

    rerender({ enabled: true });
    press("h");
    expect(highlight).toHaveBeenCalledTimes(1);

    rerender({ enabled: false });
    press("h");
    expect(highlight).toHaveBeenCalledTimes(1);
  });

  it("removes the window listener on unmount", () => {
    const highlight = vi.fn();
    const removeSpy = vi.spyOn(window, "removeEventListener");
    const { unmount } = renderHook(() => useKeyShortcuts({ h: highlight }, true));

    unmount();

    // The listener is genuinely detached, not merely inert.
    expect(
      removeSpy.mock.calls.some(([type]) => type === "keydown"),
    ).toBe(true);
    press("h");
    expect(highlight).not.toHaveBeenCalled();
  });
});
