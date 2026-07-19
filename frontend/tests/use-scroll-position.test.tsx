// @vitest-environment jsdom

/**
 * B4 (RD-07/13) — the scroll-position hook writes the reader's place after each
 * scroll-idle window. It debounces a burst of scroll callbacks into a single
 * write, never writes when the topmost section has not changed from the loaded
 * position, and swallows a failed write and retries it on the next scroll-idle.
 *
 * The IntersectionObserver is injected (jsdom has none) so the test drives the
 * callback directly; the reading client is mocked so writes are observed without
 * a network. Fake timers drive the idle debounce.
 */

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  useScrollPosition,
  type ObserverFactory,
} from "../app/components/use-scroll-position";

const { saveMock } = vi.hoisted(() => ({ saveMock: vi.fn() }));
vi.mock("@/app/lib/reading", () => ({ saveReadingPosition: saveMock }));

const A = "part1/ch1.xhtml#s1";
const B = "part1/ch1.xhtml#s2";
const C = "part1/ch1.xhtml#s3";

/** A detached container holding one wrapper per anchor, for the hook to observe. */
function makeContainer(anchors: string[]) {
  const container = document.createElement("div");
  for (const anchor of anchors) {
    const el = document.createElement("div");
    el.setAttribute("data-section-anchor", anchor);
    container.appendChild(el);
  }
  document.body.appendChild(container);
  return container;
}

/** Records observed elements and drives the callback with per-anchor states. */
function fakeObserver() {
  const observed: Element[] = [];
  let cb: IntersectionObserverCallback | null = null;
  const factory: ObserverFactory = (callback) => {
    cb = callback;
    return {
      observe: (el: Element) => observed.push(el),
      unobserve: () => {},
      disconnect: () => {},
      takeRecords: () => [],
      root: null,
      rootMargin: "",
      thresholds: [],
    } as unknown as IntersectionObserver;
  };
  function emit(states: Record<string, boolean>) {
    const entries = observed
      .map((el) => {
        const anchor = el.getAttribute("data-section-anchor")!;
        return anchor in states
          ? ({
              target: el,
              isIntersecting: states[anchor],
            } as unknown as IntersectionObserverEntry)
          : null;
      })
      .filter((e): e is IntersectionObserverEntry => e !== null);
    act(() => cb?.(entries, {} as IntersectionObserver));
  }
  return { factory, emit };
}

function renderScroll(
  container: HTMLElement,
  factory: ObserverFactory,
  initialAnchor: string | null,
) {
  // A stable ref object across renders (as `useRef` would be); an inline
  // `{ current }` would change identity each render and re-run the effect.
  const containerRef = { current: container };
  return renderHook(() =>
    useScrollPosition({
      sourceId: "s1",
      csrf: "csrf-xyz",
      anchors: [A, B, C],
      initialAnchor,
      containerRef,
      observerFactory: factory,
    }),
  );
}

beforeEach(() => {
  vi.useFakeTimers();
  saveMock.mockReset();
  saveMock.mockResolvedValue({ anchor: B, percent: 20, updated_at: "now" });
});

afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = "";
});

describe("useScrollPosition (RD-07/13)", () => {
  it("collapses a burst of scroll callbacks into a single write after the idle window", async () => {
    const obs = fakeObserver();
    renderScroll(makeContainer([A, B, C]), obs.factory, A);

    // Topmost section changes rapidly while the reader is actively scrolling...
    obs.emit({ [A]: false, [B]: true });
    obs.emit({ [B]: false, [C]: true });
    obs.emit({ [C]: false, [B]: true });

    // ...no write yet, and exactly one after the 2s idle window — with the last
    // topmost anchor, not one per scroll event (no write storm).
    expect(saveMock).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(2000);
    expect(saveMock).toHaveBeenCalledTimes(1);
    expect(saveMock).toHaveBeenCalledWith("s1", B, "csrf-xyz");
  });

  it("does not write when the topmost anchor has not changed from the loaded position", async () => {
    const obs = fakeObserver();
    renderScroll(makeContainer([A, B, C]), obs.factory, A);

    // The loaded position (A) is reported visible; no change → no write.
    obs.emit({ [A]: true });
    await vi.advanceTimersByTimeAsync(2000);
    expect(saveMock).not.toHaveBeenCalled();

    // Scrolling to B is a real change → exactly one write, of B.
    obs.emit({ [A]: false, [B]: true });
    await vi.advanceTimersByTimeAsync(2000);
    expect(saveMock).toHaveBeenCalledTimes(1);
    expect(saveMock).toHaveBeenCalledWith("s1", B, "csrf-xyz");
  });

  it("stays silent on a failed write and retries the unsaved position on the next idle", async () => {
    saveMock
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValue({ anchor: B, percent: 20, updated_at: "now" });
    const obs = fakeObserver();
    renderScroll(makeContainer([A, B, C]), obs.factory, A);

    // Scroll to B → first idle write rejects; the rejection is swallowed (the
    // test proceeding past the idle advance without throwing proves it is silent).
    obs.emit({ [A]: false, [B]: true });
    await vi.advanceTimersByTimeAsync(2000);
    expect(saveMock).toHaveBeenCalledTimes(1);

    // The next scroll-idle retries the still-unsaved position (same anchor B).
    obs.emit({ [B]: true });
    await vi.advanceTimersByTimeAsync(2000);
    expect(saveMock).toHaveBeenCalledTimes(2);
    expect(saveMock).toHaveBeenNthCalledWith(2, "s1", B, "csrf-xyz");
  });
});
