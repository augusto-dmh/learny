// @vitest-environment jsdom

/**
 * E3 gate (hook) — deck-generation polling fires every 3s while a deck job is
 * active, hands each overview back to the caller, does not poll when inactive,
 * stops once the caller flips `active` to false (its terminal signal), cleans up
 * on unmount, and skips a failed poll tick silently while continuing (QUIZ-20,
 * AD-070).
 *
 * The quiz client (URL/method/parsing) is covered by tests/quiz-client.test.ts;
 * here it is mocked so the test exercises the hook's timer and cleanup logic in
 * isolation, mirroring tests/use-ingestion-polling.test.tsx.
 */

import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useQuizDeckPolling } from "../app/components/use-quiz-deck-polling";

const { getQuizOverviewMock } = vi.hoisted(() => ({
  getQuizOverviewMock: vi.fn(),
}));

vi.mock("@/app/lib/quiz", () => ({ getQuizOverview: getQuizOverviewMock }));

function overview(status: string) {
  return {
    items: [],
    counts_by_status: {},
    due_count: 0,
    latest_job: {
      id: "job1",
      status,
      attempts: 1,
      generated_count: 0,
      discarded_count: 0,
      failed_sections: 0,
      error: null,
      created_at: "now",
      updated_at: "now",
    },
  };
}

beforeEach(() => {
  vi.useFakeTimers();
  getQuizOverviewMock.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useQuizDeckPolling", () => {
  it("polls the overview at the 3s interval while the job is active", async () => {
    const running = overview("running");
    getQuizOverviewMock.mockResolvedValue(running);
    const onOverview = vi.fn();

    renderHook(() => useQuizDeckPolling("s1", true, onOverview));

    // Nothing fires before the interval elapses.
    expect(getQuizOverviewMock).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(3000);

    expect(getQuizOverviewMock).toHaveBeenCalledTimes(1);
    expect(getQuizOverviewMock).toHaveBeenCalledWith("s1");
    expect(onOverview).toHaveBeenCalledWith(running);
  });

  it("does not poll when the job is inactive", async () => {
    getQuizOverviewMock.mockResolvedValue(overview("succeeded"));
    const onOverview = vi.fn();

    renderHook(() => useQuizDeckPolling("s1", false, onOverview));

    await vi.advanceTimersByTimeAsync(9000);

    expect(getQuizOverviewMock).not.toHaveBeenCalled();
    expect(onOverview).not.toHaveBeenCalled();
  });

  it("stops polling once the caller flips active to false", async () => {
    getQuizOverviewMock.mockResolvedValue(overview("running"));
    const onOverview = vi.fn();

    const { rerender } = renderHook(
      ({ active }: { active: boolean }) =>
        useQuizDeckPolling("s1", active, onOverview),
      { initialProps: { active: true } },
    );

    await vi.advanceTimersByTimeAsync(3000);
    expect(getQuizOverviewMock).toHaveBeenCalledTimes(1);

    // The caller detected a terminal job and flips active off.
    rerender({ active: false });

    await vi.advanceTimersByTimeAsync(3000);
    expect(getQuizOverviewMock).toHaveBeenCalledTimes(1);
  });

  it("clears the timer on unmount", async () => {
    getQuizOverviewMock.mockResolvedValue(overview("running"));

    const { unmount } = renderHook(() =>
      useQuizDeckPolling("s1", true, vi.fn()),
    );

    await vi.advanceTimersByTimeAsync(3000);
    expect(getQuizOverviewMock).toHaveBeenCalledTimes(1);

    unmount();

    await vi.advanceTimersByTimeAsync(3000);
    expect(getQuizOverviewMock).toHaveBeenCalledTimes(1);
  });

  it("skips a failed poll tick silently and keeps polling", async () => {
    getQuizOverviewMock
      .mockRejectedValueOnce(new Error("temporarily unavailable"))
      .mockResolvedValue(overview("succeeded"));
    const onOverview = vi.fn();

    renderHook(() => useQuizDeckPolling("s1", true, onOverview));

    // First tick rejects: no callback, no throw, polling continues.
    await vi.advanceTimersByTimeAsync(3000);
    expect(getQuizOverviewMock).toHaveBeenCalledTimes(1);
    expect(onOverview).not.toHaveBeenCalled();

    // Second tick resolves: the overview is handed back.
    await vi.advanceTimersByTimeAsync(3000);
    expect(getQuizOverviewMock).toHaveBeenCalledTimes(2);
    expect(onOverview).toHaveBeenCalledTimes(1);
  });
});
