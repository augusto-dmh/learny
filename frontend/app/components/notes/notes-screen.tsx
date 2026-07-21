"use client";

/**
 * Notes list screen (NF-13/14).
 *
 * Resolves auth via `/api/auth/me` (through the proxy) for the CSRF token, then
 * lists the caller's notes as cards — each showing its title (a captured
 * highlight carries its quote as the title, so an empty-body note still reads as
 * its passage), its tags as chips, and a badge per distinct anchor status with a
 * distinct treatment for an orphaned anchor (NF-14). A tag chip filters the list
 * to that tag (re-fetched server-side, case-insensitive); a clear control drops
 * the filter. A small form creates a note and opens it for editing.
 *
 * `onRequireAuth` is a UX-only redirect for unauthenticated users, NOT the
 * security boundary — FastAPI enforces auth and per-user ownership on every notes
 * call regardless of client-side routing (FR-AUTH-007, ADR-017).
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { fetchAuthState } from "@/app/lib/auth";
import { createNote, listNotes, type NoteSummary } from "@/app/lib/notes";
import { AnchorStatusBadge } from "@/app/components/notes/anchor-status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export function NotesScreen({
  onRequireAuth,
}: {
  onRequireAuth?: () => void;
}) {
  const router = useRouter();
  const [csrf, setCsrf] = useState<string | null>(null);
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [notes, setNotes] = useState<NoteSummary[] | null>(null);
  const [activeTag, setActiveTag] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const auth = await fetchAuthState();
    if (!auth.authenticated) {
      setAuthed(false);
      onRequireAuth?.();
      return;
    }
    setAuthed(true);
    setCsrf(auth.user.csrf_token);
    setLoadError(null);
    try {
      setNotes(await listNotes(activeTag ? { tag: activeTag } : {}));
    } catch (err) {
      setLoadError(
        err instanceof Error ? err.message : "Could not load your notes.",
      );
    }
  }, [activeTag, onRequireAuth]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    setCreateError(null);
    if (!csrf || !title.trim()) {
      return;
    }
    setCreating(true);
    try {
      const note = await createNote({ title: title.trim() }, csrf);
      router.push(`/notes/${note.id}`);
    } catch (err) {
      setCreateError(
        err instanceof Error ? err.message : "Could not create the note.",
      );
      setCreating(false);
    }
  }

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
            Export vault
          </a>
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>New note</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleCreate} aria-label="create note" className="space-y-4">
            <div className="space-y-1.5">
              <label htmlFor="note-title" className="text-sm font-medium">
                Title
              </label>
              <Input
                id="note-title"
                type="text"
                name="title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
              />
            </div>
            {createError ? (
              <p role="alert" className="text-sm text-destructive">
                {createError}
              </p>
            ) : null}
            <Button type="submit" disabled={creating || !title.trim()}>
              {creating ? "Creating…" : "Create note"}
            </Button>
          </form>
        </CardContent>
      </Card>

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
          {activeTag ? "No notes with that tag." : "No notes yet."}
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
