"use client";

/**
 * The dock's per-book conversation list — where a thread goes to be found again.
 *
 * One list covers the whole book, not one per tab: a thread is a conversation
 * whatever mode its turns were answered in, and a reader looking for "the one
 * about chapter three" does not think of it as an Ask thread or a Teach session.
 * Rows are newest-activity first, as the server returns them, and carry the turn
 * count so a long thread is distinguishable from an abandoned one.
 *
 * Selecting a row resumes it in place. A book with no conversations says so
 * rather than showing an empty box.
 */

import { useEffect, useState } from "react";

import {
  listConversations,
  type ConversationSummaryView,
} from "@/app/lib/conversations";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function ConversationList({
  sourceId,
  refreshToken = 0,
  activeConversationId,
  onResume,
  onNew,
}: {
  sourceId: string;
  /** Bumped by the dock when a panel creates or discards a conversation. */
  refreshToken?: number;
  activeConversationId?: string | null;
  onResume: (summary: ConversationSummaryView) => void;
  onNew: () => void;
}) {
  const [rows, setRows] = useState<ConversationSummaryView[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    void listConversations(sourceId)
      .then((listed) => {
        if (!cancelled) setRows(listed);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setRows([]);
        setError(
          err instanceof Error
            ? err.message
            : "Could not load your conversations.",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [sourceId, refreshToken]);

  return (
    <section aria-label="conversations" className="space-y-2 border-b px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Conversations
        </h2>
        <Button type="button" size="sm" variant="ghost" onClick={onNew}>
          New conversation
        </Button>
      </div>

      {error ? (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      ) : null}

      {rows === null ? (
        <p className="text-xs text-muted-foreground">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="text-xs text-muted-foreground">No conversations yet.</p>
      ) : (
        <ul className="space-y-1">
          {rows.map((row) => (
            <li
              key={row.id}
              className={cn(
                "flex items-center justify-between gap-1 rounded-md px-2 py-1 text-sm",
                row.id === activeConversationId ? "bg-accent" : null,
              )}
            >
              <button
                type="button"
                aria-label={`Resume ${row.title}`}
                aria-current={row.id === activeConversationId || undefined}
                onClick={() => onResume(row)}
                className="min-w-0 flex-1 truncate text-left hover:underline"
              >
                {row.title}{" "}
                <span className="text-xs text-muted-foreground">
                  ({row.turn_count} turns)
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
