"use client";

/**
 * Ingestion progress polling (FE-19).
 *
 * For every source currently `processing`, poll its ingestion job every 3s and,
 * once the job reaches a terminal state, patch the source's projected status the
 * way the backend does (`succeeded` → `ready`, `failed` → `failed`; `queued`/
 * `running` stay `processing`, so polling continues). Each source's timer is
 * cleared when it goes terminal, and all timers are cleared on unmount. A failed
 * poll tick is skipped silently — the badge is left unchanged and polling
 * continues on the next interval.
 */

import { useEffect } from "react";

import { getIngestion } from "@/app/lib/ingestion";
import { type SourceSummary } from "@/app/lib/sources";

const POLL_INTERVAL_MS = 3000;

/** Project an ingestion job status onto its source status (backend mapping). */
function sourceStatusFor(ingestionStatus: string): string {
  if (ingestionStatus === "succeeded") {
    return "ready";
  }
  if (ingestionStatus === "failed") {
    return "failed";
  }
  return "processing";
}

export function useIngestionPolling(
  sources: SourceSummary[] | null,
  onStatusChange: (sourceId: string, status: string) => void,
): void {
  useEffect(() => {
    if (!sources) {
      return;
    }
    const timers = new Map<string, ReturnType<typeof setInterval>>();

    for (const source of sources) {
      if (source.status !== "processing") {
        continue;
      }
      const id = source.id;
      timers.set(
        id,
        setInterval(() => {
          getIngestion(id)
            .then((ingestion) => {
              const next = sourceStatusFor(ingestion.status);
              if (next === "processing") {
                return; // still in flight — keep polling
              }
              const timer = timers.get(id);
              if (timer !== undefined) {
                clearInterval(timer);
                timers.delete(id);
              }
              onStatusChange(id, next);
            })
            .catch(() => {
              // Transient read failure — skip this tick, keep polling.
            });
        }, POLL_INTERVAL_MS),
      );
    }

    return () => {
      for (const timer of timers.values()) {
        clearInterval(timer);
      }
      timers.clear();
    };
  }, [sources, onStatusChange]);
}
