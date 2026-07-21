"use client";

/**
 * Note detail screen (NF-13/14).
 *
 * Resolves auth via `/api/auth/me` for the CSRF token, then loads one owned note
 * and its backlinks. The body is edited in a plain textarea with a preview toggle
 * that renders the Markdown with the same `MessageResponse` (Streamdown) the reader
 * uses — raw HTML in the note stays inert. Title and comma-separated tags edit
 * alongside it; Save is enabled only while the form is dirty and persists via the
 * notes client (re-deriving wikilinks/tags server-side). The backlinks panel lists
 * the notes that link here, and the anchored-passages list shows each captured
 * highlight's quote snapshot with a status badge — an orphaned anchor keeps its
 * quote and a distinct badge (NF-14) — and a jump-back link into the reader for a
 * still-anchored passage. Delete is confirm-gated and returns to the list.
 *
 * `onRequireAuth` is a UX-only redirect for unauthenticated users, NOT the
 * security boundary — FastAPI enforces auth and ownership on every notes call
 * (FR-AUTH-007, ADR-017).
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { fetchAuthState } from "@/app/lib/auth";
import {
  deleteNote,
  getBacklinks,
  getNote,
  NoteError,
  updateNote,
  type Backlink,
  type NoteDetail,
} from "@/app/lib/notes";
import { AnchorStatusBadge } from "@/app/components/notes/anchor-status-badge";
import { NoteCardSuggestions } from "@/app/components/notes/note-card-suggestions";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { MessageResponse } from "@/components/ai-elements/message";

/** Comma-separated tag text ↔ the tags array the API carries. */
function parseTags(text: string): string[] {
  return text
    .split(",")
    .map((tag) => tag.trim())
    .filter((tag) => tag.length > 0);
}

export function NoteDetailScreen({
  noteId,
  onRequireAuth,
}: {
  noteId: string;
  onRequireAuth?: () => void;
}) {
  const router = useRouter();
  const [csrf, setCsrf] = useState<string | null>(null);
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [note, setNote] = useState<NoteDetail | null>(null);
  const [backlinks, setBacklinks] = useState<Backlink[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Edit buffers plus the saved baseline they are diffed against for dirty state.
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [tagsText, setTagsText] = useState("");
  const [baseline, setBaseline] = useState({ title: "", body: "", tags: "" });

  const [preview, setPreview] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // Load the buffers and baseline from a fetched note.
  const hydrate = useCallback((detail: NoteDetail) => {
    setNote(detail);
    setTitle(detail.title);
    setBody(detail.body_markdown);
    const tags = detail.tags.join(", ");
    setTagsText(tags);
    setBaseline({ title: detail.title, body: detail.body_markdown, tags });
  }, []);

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
      const [detail, links] = await Promise.all([
        getNote(noteId),
        getBacklinks(noteId),
      ]);
      hydrate(detail);
      setBacklinks(links);
    } catch (err) {
      setLoadError(
        err instanceof Error ? err.message : "Could not load that note.",
      );
    }
  }, [noteId, hydrate, onRequireAuth]);

  useEffect(() => {
    void load();
  }, [load]);

  const dirty =
    title !== baseline.title ||
    body !== baseline.body ||
    tagsText !== baseline.tags;

  async function handleSave() {
    if (!csrf || !dirty) {
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      const updated = await updateNote(
        noteId,
        { title, body_markdown: body, tags: parseTags(tagsText) },
        csrf,
      );
      hydrate(updated);
    } catch (err) {
      setSaveError(
        err instanceof NoteError && err.kind === "body_too_long"
          ? "This note is too long to save."
          : err instanceof Error
            ? err.message
            : "Could not save the note.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!csrf) {
      return;
    }
    setDeleting(true);
    try {
      await deleteNote(noteId, csrf);
      router.push("/notes");
    } catch (err) {
      setSaveError(
        err instanceof Error ? err.message : "Could not delete the note.",
      );
      setDeleting(false);
      setConfirmingDelete(false);
    }
  }

  if (authed === null) {
    return <p className="text-muted-foreground">Loading…</p>;
  }
  if (!authed) {
    return <p className="text-muted-foreground">You are signed out.</p>;
  }
  if (loadError) {
    return (
      <div className="mx-auto max-w-2xl py-12 text-center">
        <p role="alert" className="text-destructive">
          {loadError}
        </p>
        <Link
          href="/notes"
          className="text-primary underline-offset-4 hover:underline"
        >
          Back to your notes
        </Link>
      </div>
    );
  }
  if (note === null) {
    return <p className="text-muted-foreground">Loading the note…</p>;
  }

  return (
    <section aria-label="note" className="mx-auto max-w-2xl space-y-6">
      <div className="space-y-1.5">
        <label htmlFor="note-title" className="text-sm font-medium">
          Title
        </label>
        <Input
          id="note-title"
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
      </div>

      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <label htmlFor="note-body" className="text-sm font-medium">
            Body
          </label>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => setPreview((p) => !p)}
          >
            {preview ? "Edit" : "Preview"}
          </Button>
        </div>
        {preview ? (
          <div
            data-testid="note-preview"
            className="prose prose-sm min-h-40 max-w-none rounded-md border p-3 dark:prose-invert"
          >
            <MessageResponse>{body}</MessageResponse>
          </div>
        ) : (
          <textarea
            id="note-body"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            className="min-h-40 w-full rounded-md border bg-transparent p-3 text-sm"
          />
        )}
      </div>

      <div className="space-y-1.5">
        <label htmlFor="note-tags" className="text-sm font-medium">
          Tags
        </label>
        <Input
          id="note-tags"
          type="text"
          value={tagsText}
          placeholder="comma, separated, tags"
          onChange={(e) => setTagsText(e.target.value)}
        />
      </div>

      {saveError ? (
        <p role="alert" className="text-sm text-destructive">
          {saveError}
        </p>
      ) : null}

      <div className="flex items-center gap-2">
        <Button
          type="button"
          onClick={() => void handleSave()}
          disabled={!dirty || saving}
        >
          {saving ? "Saving…" : "Save"}
        </Button>
        {confirmingDelete ? (
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">Delete this note?</span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void handleDelete()}
              disabled={deleting}
            >
              {deleting ? "Deleting…" : "Confirm delete"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setConfirmingDelete(false)}
              disabled={deleting}
            >
              Cancel
            </Button>
          </div>
        ) : (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setConfirmingDelete(true)}
          >
            Delete
          </Button>
        )}
      </div>

      {csrf ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Review</CardTitle>
          </CardHeader>
          <CardContent>
            <NoteCardSuggestions noteId={noteId} csrf={csrf} />
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Anchored passages</CardTitle>
        </CardHeader>
        <CardContent>
          {note.anchors.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No highlights anchored to this note.
            </p>
          ) : (
            <ul className="space-y-3">
              {note.anchors.map((anchor) => (
                <li key={anchor.id} className="space-y-1.5" data-testid={`anchor-${anchor.id}`}>
                  <div className="flex items-center gap-2">
                    <AnchorStatusBadge status={anchor.status} />
                    <span className="text-xs text-muted-foreground">
                      {anchor.source_title}
                    </span>
                  </div>
                  <blockquote className="border-l-2 pl-3 text-sm text-muted-foreground">
                    {anchor.quote_exact}
                  </blockquote>
                  {anchor.status === "orphaned" ? (
                    <p className="text-xs text-muted-foreground">
                      This passage is no longer in the book.
                    </p>
                  ) : (
                    <Link
                      href={`/sources/${anchor.source_id}/read?anchor=${encodeURIComponent(
                        anchor.anchor,
                      )}`}
                      className="text-sm text-primary underline-offset-4 hover:underline"
                    >
                      Jump to passage
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Backlinks</CardTitle>
        </CardHeader>
        <CardContent>
          {backlinks.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No notes link here yet.
            </p>
          ) : (
            <ul className="space-y-1.5">
              {backlinks.map((backlink) => (
                <li key={backlink.note_id}>
                  <Link
                    href={`/notes/${backlink.note_id}`}
                    className="text-sm text-primary underline-offset-4 hover:underline"
                  >
                    {backlink.title}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
