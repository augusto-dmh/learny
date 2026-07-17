// @vitest-environment jsdom

/**
 * C gate (hook) — ingestion polling fires every 3s for processing sources,
 * patches the source status the backend way on a terminal job, stops polling
 * once terminal, cleans up all timers on unmount, and skips a failed poll tick
 * silently while continuing to poll (FE-19).
 *
 * The ingestion client (URL/method/parsing) is covered by
 * tests/ingestion-client.test.ts; here it is injected so the test exercises the
 * hook's timer, mapping, and cleanup logic in isolation.
 */

import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useIngestionPolling } from "../app/components/use-ingestion-polling";

const { getIngestionMock } = vi.hoisted(() => ({ getIngestionMock: vi.fn() }));

vi.mock("@/app/lib/ingestion", () => ({ getIngestion: getIngestionMock }));

/** An ingestion job in the given lifecycle state. */
function ingestion(status: string) {
  return {
    id: "j1",
    status,
    attempts: 0,
    error: null,
    created_at: "now",
    updated_at: "now",
    events: [],
  };
}

function processingSource(id = "s1") {
  return {
    id,
    title: "Book",
    filename: `${id}.epub`,
    byte_size: 3,
    content_type: "application/epub+zip",
    status: "processing",
    created_at: "now",
  };
}

beforeEach(() => {
  vi.useFakeTimers();
  getIngestionMock.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useIngestionPolling", () => {
  it("polls a processing source's ingestion at the 3s interval", async () => {
    getIngestionMock.mockResolvedValue(ingestion("running"));
    const onStatusChange = vi.fn();

    renderHook(() => useIngestionPolling([processingSource()], onStatusChange));

    // Nothing fires before the interval elapses.
    expect(getIngestionMock).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(3000);

    expect(getIngestionMock).toHaveBeenCalledTimes(1);
    expect(getIngestionMock).toHaveBeenCalledWith("s1");
    // Still running → no status patch.
    expect(onStatusChange).not.toHaveBeenCalled();
  });

  it("patches the source to ready when the job succeeds", async () => {
    getIngestionMock.mockResolvedValue(ingestion("succeeded"));
    const onStatusChange = vi.fn();

    renderHook(() => useIngestionPolling([processingSource()], onStatusChange));

    await vi.advanceTimersByTimeAsync(3000);

    expect(onStatusChange).toHaveBeenCalledWith("s1", "ready");
  });

  it("patches the source to failed when the job fails", async () => {
    getIngestionMock.mockResolvedValue(ingestion("failed"));
    const onStatusChange = vi.fn();

    renderHook(() => useIngestionPolling([processingSource()], onStatusChange));

    await vi.advanceTimersByTimeAsync(3000);

    expect(onStatusChange).toHaveBeenCalledWith("s1", "failed");
  });

  it("stops polling once the job reaches a terminal status", async () => {
    getIngestionMock.mockResolvedValue(ingestion("succeeded"));
    const onStatusChange = vi.fn();

    renderHook(() => useIngestionPolling([processingSource()], onStatusChange));

    await vi.advanceTimersByTimeAsync(3000);
    expect(getIngestionMock).toHaveBeenCalledTimes(1);
    expect(onStatusChange).toHaveBeenCalledTimes(1);

    // Timer was cleared on the terminal tick — no further polling.
    await vi.advanceTimersByTimeAsync(3000);
    expect(getIngestionMock).toHaveBeenCalledTimes(1);
  });

  it("clears all timers on unmount", async () => {
    getIngestionMock.mockResolvedValue(ingestion("running"));

    const { unmount } = renderHook(() =>
      useIngestionPolling([processingSource()], vi.fn()),
    );

    await vi.advanceTimersByTimeAsync(3000);
    expect(getIngestionMock).toHaveBeenCalledTimes(1);

    unmount();

    await vi.advanceTimersByTimeAsync(3000);
    expect(getIngestionMock).toHaveBeenCalledTimes(1);
  });

  it("skips a failed poll tick silently and keeps polling", async () => {
    getIngestionMock
      .mockRejectedValueOnce(new Error("temporarily unavailable"))
      .mockResolvedValue(ingestion("succeeded"));
    const onStatusChange = vi.fn();

    renderHook(() => useIngestionPolling([processingSource()], onStatusChange));

    // First tick fails: no status change, no throw, polling continues.
    await vi.advanceTimersByTimeAsync(3000);
    expect(getIngestionMock).toHaveBeenCalledTimes(1);
    expect(onStatusChange).not.toHaveBeenCalled();

    // Second tick succeeds: the source is patched to ready.
    await vi.advanceTimersByTimeAsync(3000);
    expect(getIngestionMock).toHaveBeenCalledTimes(2);
    expect(onStatusChange).toHaveBeenCalledWith("s1", "ready");
  });
});
