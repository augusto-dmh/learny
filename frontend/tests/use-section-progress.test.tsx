// @vitest-environment jsdom

/**
 * How far the reader has travelled through the section they are reading.
 *
 * The figure the reader watches is a word count, exact at every section boundary
 * and motionless in between. This hook supplies the term that fills the gap: the
 * fraction of the current section the viewport has passed. Two things have to be
 * true of it at once — it has to move continuously as the reader scrolls, and it
 * must not make the reader pay for that. A scroll event fires far more often than
 * the screen redraws, and each measurement reads layout and can re-render the
 * whole reader, so the hook collapses a burst into a single animation frame and
 * cancels the pending one when the reader leaves.
 *
 * `requestAnimationFrame` is stubbed with a queue the test drives by hand, so
 * "one measurement per frame" and "nothing measures after unmount" are both
 * observable rather than timing-dependent.
 */

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useSectionProgress } from "../app/components/use-section-progress";

const ANCHOR = "part1/ch1.xhtml#s1";
const HEADER = 100;

/** A hand-driven animation-frame queue in place of the browser's. */
function frameQueue() {
  const queued = new Map<number, FrameRequestCallback>();
  let nextId = 1;
  const request = vi.fn((cb: FrameRequestCallback) => {
    const id = nextId++;
    queued.set(id, cb);
    return id;
  });
  const cancel = vi.fn((id: number) => {
    queued.delete(id);
  });
  vi.stubGlobal("requestAnimationFrame", request);
  vi.stubGlobal("cancelAnimationFrame", cancel);
  return {
    request,
    cancel,
    /** Run everything waiting on the next frame, as the browser would. */
    paint() {
      const callbacks = [...queued.values()];
      queued.clear();
      act(() => {
        for (const cb of callbacks) {
          cb(0);
        }
      });
    },
  };
}

/** A section element in the document whose geometry the test controls. */
function section(anchor = ANCHOR, geometry = { top: 0, height: 1000 }) {
  const el = document.createElement("div");
  el.id = anchor;
  document.body.appendChild(el);
  const measured = vi.fn(
    () => ({ top: geometry.top, height: geometry.height }) as DOMRect,
  );
  el.getBoundingClientRect = measured;
  return {
    measured,
    /** Move the section relative to the viewport, as scrolling would. */
    scrollTo(top: number) {
      geometry.top = top;
    },
  };
}

function scroll(times = 1) {
  act(() => {
    for (let i = 0; i < times; i++) {
      window.dispatchEvent(new Event("scroll"));
    }
  });
}

afterEach(() => {
  // Explicit: the hook attaches window listeners, and a hook left mounted would
  // measure into the next test's frame queue.
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  document.body.innerHTML = "";
});

describe("useSectionProgress", () => {
  it("measures the section it is given before any scroll happens", () => {
    // A deep link opens mid-section: the figure has to be right on the first
    // paint, not one frame late.
    frameQueue();
    section(ANCHOR, { top: -400, height: 1000 });

    const { result } = renderHook(() => useSectionProgress(ANCHOR, HEADER));

    expect(result.current).toBeCloseTo(0.5, 5);
  });

  it("moves the figure as the section passes the reading line", () => {
    const frames = frameQueue();
    const el = section(ANCHOR, { top: 0, height: 1000 });
    const { result } = renderHook(() => useSectionProgress(ANCHOR, HEADER));
    expect(result.current).toBeCloseTo(0.1, 5);

    el.scrollTo(-650);
    scroll();
    frames.paint();

    expect(result.current).toBeCloseTo(0.75, 5);
  });

  it("stays within the section it is measuring, in both directions", () => {
    const frames = frameQueue();
    const el = section(ANCHOR, { top: 5000, height: 1000 });
    const { result } = renderHook(() => useSectionProgress(ANCHOR, HEADER));
    // Far below the reading line: the reader has passed none of this section.
    expect(result.current).toBe(0);

    el.scrollTo(-9000);
    scroll();
    frames.paint();

    // Far above it: passed, not more than passed.
    expect(result.current).toBe(1);
  });

  it("collapses a burst of scroll events into a single measurement", () => {
    const frames = frameQueue();
    const el = section(ANCHOR, { top: 0, height: 1000 });
    renderHook(() => useSectionProgress(ANCHOR, HEADER));
    expect(el.measured).toHaveBeenCalledTimes(1); // the mount measurement

    scroll(20);

    // Twenty events, one frame asked for, and nothing measured until it runs.
    expect(frames.request).toHaveBeenCalledTimes(1);
    expect(el.measured).toHaveBeenCalledTimes(1);
    frames.paint();
    expect(el.measured).toHaveBeenCalledTimes(2);
  });

  it("measures again on the frame after the one that ran", () => {
    // Coalescing must not latch: the reader keeps scrolling and the figure keeps up.
    const frames = frameQueue();
    const el = section(ANCHOR, { top: 0, height: 1000 });
    const { result } = renderHook(() => useSectionProgress(ANCHOR, HEADER));

    el.scrollTo(-400);
    scroll(5);
    frames.paint();
    el.scrollTo(-900);
    scroll(5);
    frames.paint();

    expect(el.measured).toHaveBeenCalledTimes(3);
    expect(result.current).toBeCloseTo(1, 5);
  });

  it("resizing the window remeasures, on a frame like everything else", () => {
    const frames = frameQueue();
    const el = section(ANCHOR, { top: 0, height: 1000 });
    const { result } = renderHook(() => useSectionProgress(ANCHOR, HEADER));

    el.scrollTo(-150);
    act(() => {
      window.dispatchEvent(new Event("resize"));
    });
    expect(el.measured).toHaveBeenCalledTimes(1);
    frames.paint();

    expect(result.current).toBeCloseTo(0.25, 5);
  });

  it("leaves no frame pending after unmount", () => {
    const frames = frameQueue();
    const el = section();
    const { unmount } = renderHook(() => useSectionProgress(ANCHOR, HEADER));
    scroll();

    unmount();

    expect(frames.cancel).toHaveBeenCalledTimes(1);
    // The queue is empty, so the frame that was waiting never measures a section
    // the reader has left.
    frames.paint();
    expect(el.measured).toHaveBeenCalledTimes(1);
  });

  it("leaves no frame pending when the reader moves to another section", () => {
    const frames = frameQueue();
    const first = section(ANCHOR);
    const second = section("part1/ch1.xhtml#s2", { top: -500, height: 1000 });
    const { result, rerender } = renderHook(
      ({ anchor }) => useSectionProgress(anchor, HEADER),
      { initialProps: { anchor: ANCHOR } },
    );
    scroll();

    rerender({ anchor: "part1/ch1.xhtml#s2" });

    expect(frames.cancel).toHaveBeenCalledTimes(1);
    frames.paint();
    // The stale frame measured nothing; the new section measured on mount only.
    expect(first.measured).toHaveBeenCalledTimes(1);
    expect(second.measured).toHaveBeenCalledTimes(1);
    expect(result.current).toBeCloseTo(0.6, 5);
  });

  it("reads zero where the section has no geometry to measure", () => {
    // Server render, jsdom, a section not laid out yet: the figure falls back to
    // the staircase it was before this hook existed rather than guessing.
    frameQueue();
    section(ANCHOR, { top: -400, height: 0 });

    const { result } = renderHook(() => useSectionProgress(ANCHOR, HEADER));

    expect(result.current).toBe(0);
  });

  it("reads zero, and listens to nothing, without a current section", () => {
    const frames = frameQueue();
    section();

    const { result } = renderHook(() => useSectionProgress(null, HEADER));
    scroll(5);

    expect(result.current).toBe(0);
    expect(frames.request).not.toHaveBeenCalled();
  });
});
