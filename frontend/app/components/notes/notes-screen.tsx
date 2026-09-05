"use client";

/**
 * Notes list screen (NF-13/14).
 *
 * Resolves auth via `/api/auth/me` (through the proxy), then lists the caller's
 * notes as cards — each showing its title (a captured highlight carries its quote
 * as the title, so an empty-body note still reads as its passage), its tags as
 * chips, and a badge per distinct anchor status with a distinct treatment for an
 * orphaned anchor (NF-14). A tag chip filters the list to that tag (re-fetched
 * server-side, case-insensitive); a clear control drops the filter.
 *
 * The screen reads notes; it does not mint them. A note is born from a passage in
 * the reader or from saving an answer, so that it keeps where it came from — there
 * is no title-only form here any more.
 *
 * This is the cross-book surface: unfiltered it holds every book's notes, and a
 * book picker narrows it to one without leaving the route. Narrowing re-fetches
 * server-side over the same endpoint the reader's dock reads, and picking "All
 * books" restores the cross-book list. A book the caller does not own answers 404
 * like every other source read; that surfaces as the list's readable error rather
 * than a broken screen.
 *
 * `onRequireAuth` is a UX-only redirect for unauthenticated users, NOT the
 * security boundary — FastAPI enforces auth and per-user ownership on every notes
 * call regardless of client-side routing (FR-AUTH-007, ADR-017).
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { fetchAuthState } from "@/app/lib/auth";
import { listNotes, type NoteSummary } from "@/app/lib/notes";
import { listSources, type SourceSummary } from "@/app/lib/sources";
import { AnchorStatusBadge } from "@/app/components/notes/anchor-status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export function NotesScreen({
  onRequireAuth,
}: {
  onRequireAuth?: () => void;
}) {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [notes, setNotes] = useState<NoteSummary[] | null>(null);
  const [activeTag, setActiveTag] = useState<string | null>(null);
  const [activeSourceId, setActiveSourceId] = useState<string | null>(null);
  const [sources, setSources] = useState<SourceSummary[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const auth = await fetchAuthState();
    if (!auth.authenticated) {
      setAuthed(false);
      onRequireAuth?.();
      return;
    }
    setAuthed(true);
    setLoadError(null);
    try {
      setNotes(
        await listNotes({
          ...(activeTag ? { tag: activeTag } : {}),
          ...(activeSourceId ? { sourceId: activeSourceId } : {}),
        }),
      );
    } catch (err) {
      setLoadError(
        err instanceof Error ? err.message : "Could not load your notes.",
      );
    }
  }, [activeTag, activeSourceId, onRequireAuth]);

  useEffect(() => {
    void load();
  }, [load]);

  // The books the picker offers. Loaded once the caller is known, and separately
  // from the list so narrowing to a book never re-reads the library. A library
  // that fails to load simply leaves the picker out — the notes themselves are
  // what this screen is for.
  useEffect(() => {
    if (!authed) {
      return;
    }
    let cancelled = false;
    void listSources()
      .then((loaded) => {
        if (!cancelled) {
          setSources(loaded);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [authed]);

  if (authed === null) {
    return <p className="text-muted-foreground">Loading…</p>;
  }
  if (!authed) {
    return <p className="text-muted-foreground">You are signed out.</p>;
  }

  return (
    <section aria-label="notes" className="space-y-6">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Notes</h1>
        {/* Plain same-origin GET download (auth cookie, no CSRF) — the proxy streams
            the deterministic Obsidian vault zip straight from FastAPI (NL-16). */}
        <Button asChild variant="outline">
          <a href="/api/export/vault" download="learny-vault.zip">
            Download notes
          </a>
        </Button>
      </div>

      {sources.length > 0 ? (
        <div className="flex items-center gap-2 text-sm">
          <label htmlFor="notes-book-filter" className="text-muted-foreground">
            Book
          </label>
          <select
            id="notes-book-filter"
            value={activeSourceId ?? ""}
            onChange={(event) =>
              setActiveSourceId(event.target.value || null)
            }
            className="h-8 rounded-lg border border-input bg-transparent px-2.5 py-1 outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            {/* Clearing the filter is picking every book again, so it is the
                same control rather than a separate reset. */}
            <option value="">All books</option>
            {sources.map((source) => (
              <option key={source.id} value={source.id}>
                {source.title}
              </option>
            ))}
          </select>
        </div>
      ) : null}

      {activeTag ? (
        <div className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">Filtered by</span>
          <Badge variant="secondary">{activeTag}</Badge>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => setActiveTag(null)}
          >
            Clear filter
          </Button>
        </div>
      ) : null}

      {loadError ? (
        <p role="alert" className="text-sm text-destructive">
          {loadError}
        </p>
      ) : notes === null ? (
        <p className="text-muted-foreground">Loading your notes…</p>
      ) : notes.length === 0 ? (
        <p className="text-muted-foreground">
          {activeTag
            ? "No notes with that tag."
            : activeSourceId
              ? "No notes from this book yet."
              : "No notes yet. Open a book and select a passage to start one."}
        </p>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2">
          {notes.map((note) => (
            <li key={note.id}>
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">
                    <Link
                      href={`/notes/${note.id}`}
                      className="underline-offset-4 hover:underline"
                    >
                      {note.title}
                    </Link>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {note.tags.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5">
                      {note.tags.map((tag) => (
                        <button
                          key={tag}
                          type="button"
                          onClick={() => setActiveTag(tag)}
                          aria-label={`Filter by ${tag}`}
                        >
                          <Badge variant="secondary">{tag}</Badge>
                        </button>
                      ))}
                    </div>
                  ) : null}
                  {uniqueStatuses(note.anchor_statuses).length > 0 ? (
                    <div className="flex flex-wrap gap-1.5">
                      {uniqueStatuses(note.anchor_statuses).map((status) => (
                        <AnchorStatusBadge key={status} status={status} />
                      ))}
                    </div>
                  ) : null}
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** The distinct anchor statuses on a note, in first-seen order (badge inputs). */
function uniqueStatuses(statuses: string[]): string[] {
  return [...new Set(statuses)];
}
