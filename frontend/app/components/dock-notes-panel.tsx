"use client";

/**
 * The dock's Notes tab — this book's notes, beside the page they came from.
 *
 * Rows are the book-scoped notes list exactly as the server orders it
 * (newest-edited first), and each one shows what makes a note worth finding
 * again: its title, the passage's section and page, and the stored quote
 * snapshot. A note anchored to the book more than once is one note, and the
 * server's note-shaped list already says so — this renders rows, it does not
 * deduplicate them.
 *
 * The page number is the server's book-global figure; a row whose anchor no
 * longer resolves simply has none, and still shows its quote rather than
 * dropping out of the list.
 *
 * The count the tab carries is the length of this list — an inventory of what
 * the reader has written here, never a score.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { listNotes, type NoteSummary } from "@/app/lib/notes";

/** What the book's Notes tab is showing: its rows, or why it has none. */
export type BookNotes = {
  notes: NoteSummary[] | null;
  error: string | null;
};

/**
 * This book's notes, loaded once per book and re-read when `refreshToken`
 * changes — the reader capturing a passage from the page is exactly that, so a
 * note written while the tab is open appears without a reload.
 *
 * It lives in the dock shell rather than the panel because the tab's count has to
 * be there whether or not the reader is looking at the tab.
 */
export function useBookNotes(sourceId: string, refreshToken = 0): BookNotes {
  const [notes, setNotes] = useState<NoteSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setNotes(await listNotes({ sourceId }));
      setError(null);
    } catch (err) {
      setNotes([]);
      setError(
        err instanceof Error
          ? err.message
          : "Could not load this book's notes.",
      );
    }
  }, [sourceId]);

  useEffect(() => {
    void load();
    // `refreshToken` is a signal to re-read, not data the load depends on.
  }, [load, refreshToken]);

  return { notes, error };
}

export function DockNotesPanel({
  notes,
  error,
  onShowInBook,
}: BookNotes & { onShowInBook?: (anchor: string) => void }) {
  if (error) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {error}
      </p>
    );
  }
  if (notes === null) {
    return <p className="text-sm text-muted-foreground">Loading your notes…</p>;
  }
  if (notes.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Notes on this book only. Select a passage to start a new one — every note
        keeps the passage it came from.
      </p>
    );
  }

  return (
    <ul aria-label="Notes on this book" className="space-y-3">
      {notes.map((note) => (
        <li key={note.id} className="space-y-1 border-b pb-3 last:border-b-0">
          <Link
            href={`/notes/${note.id}`}
            className="text-sm font-medium underline-offset-4 hover:underline"
          >
            {note.title}
          </Link>
          {note.anchor ? (
            <NoteRowPassage anchor={note.anchor} onShowInBook={onShowInBook} />
          ) : null}
        </li>
      ))}
    </ul>
  );
}

/**
 * A row's provenance line: where the note came from, and the words it was taken
 * from. The line is the way back into the book when the dock's host offers one —
 * the reader is already on the page, so reaching the passage should not mean
 * leaving it.
 */
function NoteRowPassage({
  anchor,
  onShowInBook,
}: {
  anchor: NonNullable<NoteSummary["anchor"]>;
  onShowInBook?: (anchor: string) => void;
}) {
  // A page only exists while the anchor still resolves; an orphaned one shows its
  // section alone rather than a number the book can no longer back up.
  const where =
    anchor.page === null
      ? anchor.section_title
      : `${anchor.section_title} · p. ${anchor.page}`;

  return (
    <>
      {onShowInBook ? (
        <button
          type="button"
          onClick={() => onShowInBook(anchor.anchor)}
          className="block text-xs text-muted-foreground underline-offset-4 hover:underline"
        >
          {where}
        </button>
      ) : (
        <p className="text-xs text-muted-foreground">{where}</p>
      )}
      <blockquote className="border-l-2 pl-2 text-xs text-muted-foreground">
        {anchor.quote_exact}
      </blockquote>
    </>
  );
}
