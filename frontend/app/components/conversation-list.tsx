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
 * Selecting a row resumes it in place; renaming and deleting happen here too,
 * because this is the only screen that shows a conversation as an object rather
 * than as a conversation you are having. A book with no conversations says so
 * rather than showing an empty box.
 */

import { Check, Pencil, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  deleteConversation,
  listConversations,
  renameConversation,
  type ConversationSummaryView,
} from "@/app/lib/conversations";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function ConversationList({
  sourceId,
  csrf,
  refreshToken = 0,
  activeConversationId,
  onResume,
  onNew,
  onDeleted,
}: {
  sourceId: string;
  csrf: string;
  /** Bumped by the dock when a panel creates or discards a conversation. */
  refreshToken?: number;
  activeConversationId?: string | null;
  onResume: (summary: ConversationSummaryView) => void;
  onNew: () => void;
  onDeleted?: (conversationId: string) => void;
}) {
  const [rows, setRows] = useState<ConversationSummaryView[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

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

  const handleRename = useCallback(
    async (conversationId: string) => {
      const title = draftTitle.trim();
      // A blank title is not a rename: the stored one is left exactly as it was.
      if (!title) {
        return;
      }
      setBusyId(conversationId);
      setError(null);
      try {
        const renamed = await renameConversation(conversationId, title, csrf);
        setRows((current) =>
          (current ?? []).map((row) =>
            row.id === conversationId ? { ...row, title: renamed.title } : row,
          ),
        );
        setRenamingId(null);
      } catch (err: unknown) {
        setError(
          err instanceof Error
            ? err.message
            : "Could not rename that conversation.",
        );
      } finally {
        setBusyId(null);
      }
    },
    [draftTitle, csrf],
  );

  const handleDelete = useCallback(
    async (conversationId: string) => {
      setBusyId(conversationId);
      setError(null);
      try {
        await deleteConversation(conversationId, csrf);
        setRows((current) =>
          (current ?? []).filter((row) => row.id !== conversationId),
        );
        onDeleted?.(conversationId);
      } catch (err: unknown) {
        setError(
          err instanceof Error
            ? err.message
            : "Could not delete that conversation.",
        );
      } finally {
        setBusyId(null);
      }
    },
    [csrf, onDeleted],
  );

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
              {renamingId === row.id ? (
                <>
                  <input
                    aria-label="New title"
                    value={draftTitle}
                    onChange={(event) => setDraftTitle(event.target.value)}
                    className="min-w-0 flex-1 rounded-md border bg-background px-2 py-1 text-sm"
                  />
                  <Button
                    type="button"
                    size="icon-sm"
                    variant="ghost"
                    aria-label="Save title"
                    disabled={busyId === row.id || draftTitle.trim() === ""}
                    onClick={() => void handleRename(row.id)}
                  >
                    <Check />
                  </Button>
                  <Button
                    type="button"
                    size="icon-sm"
                    variant="ghost"
                    aria-label="Cancel rename"
                    onClick={() => setRenamingId(null)}
                  >
                    <X />
                  </Button>
                </>
              ) : (
                <>
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
                  <Button
                    type="button"
                    size="icon-sm"
                    variant="ghost"
                    aria-label={`Rename ${row.title}`}
                    onClick={() => {
                      setRenamingId(row.id);
                      setDraftTitle(row.title);
                    }}
                  >
                    <Pencil />
                  </Button>
                  <Button
                    type="button"
                    size="icon-sm"
                    variant="ghost"
                    aria-label={`Delete ${row.title}`}
                    disabled={busyId === row.id}
                    onClick={() => void handleDelete(row.id)}
                  >
                    <Trash2 />
                  </Button>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
