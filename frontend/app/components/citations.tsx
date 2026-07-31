"use client";

/**
 * The citations attached to an answer: a numbered chip row, and the one cited
 * passage the reader is currently looking at, in flow beneath it (FE-16, ANSW-07/08).
 *
 * Selecting a chip — or an inline mark in the answer text, which selects into the
 * same region — opens that citation's passage below the answer: its section-path
 * breadcrumb, its verbatim snippet, and a way into the reader at that citation's
 * anchor. Turning citations into navigation, not decoration, without covering the
 * reading column: the passage expands the message it belongs to and is clamped, so
 * a long quote scrolls inside its own box instead of pushing the answer off screen.
 * The passage never surfaces retrieval machinery (`chunk_id`, `score`): it speaks
 * the book's passage, not the index behind it (RA-12).
 *
 * Inside the reader panel the caller passes `onShowInBook`, so the action becomes
 * an in-place "Show in book" button that jumps the open chapter while the answer
 * stays visible (RA-13/14). Outside it (no callback), the action falls back to an
 * "Open in book" link into the reader route.
 *
 * The anchor is `href[#fragment]` (reserved `/` and `#`), so it is
 * `encodeURIComponent`-encoded exactly once into the reader route's `anchor`
 * query param; the reader decodes it via `useSearchParams`.
 *
 * The chip row stays even when the answer carries inline marks: it is the
 * inventory of everything the answer is grounded in, and the fallback for an
 * answer whose text has no markers at all (spec AC4).
 */

import Link from "next/link";
import { BookOpenIcon, StickyNoteIcon, X } from "lucide-react";
import { useState } from "react";

import { type Citation } from "@/app/lib/citations";
import { readUrl } from "@/app/lib/read-url";
import { Button } from "@/components/ui/button";

/**
 * The citations attached to one answer: numbered chips, and the open passage.
 *
 * Selection is the caller's when it is passed (the answer's inline marks and the
 * chips must open the same one region, so the message that renders both owns
 * which is open) and the list's own otherwise, so a citation list on its own is
 * still fully usable.
 */
export function CitationList({
  sourceId,
  citations,
  onShowInBook,
  selected: selectedProp,
  onSelect,
}: {
  sourceId: string;
  citations: Citation[];
  /** In-reader jump: provided → "Show in book" button; absent → reader-route link. */
  onShowInBook?: (anchor: string) => void;
  /** The 1-based citation whose passage is open, when the caller owns selection. */
  selected?: number | null;
  onSelect?: (selected: number | null) => void;
}) {
  const [ownSelected, setOwnSelected] = useState<number | null>(null);
  const selected = selectedProp === undefined ? ownSelected : selectedProp;
  const select = onSelect ?? setOwnSelected;

  if (citations.length === 0) {
    return null;
  }
  const open =
    selected !== null && selected >= 1 && selected <= citations.length
      ? citations[selected - 1]
      : null;

  return (
    <div className="mt-3 space-y-2">
      <div aria-label="citations" className="flex flex-wrap gap-1.5">
        {citations.map((citation, index) => (
          <CitationChip
            key={citation.chunk_id}
            citation={citation}
            index={index + 1}
            open={selected === index + 1}
            onToggle={() => select(selected === index + 1 ? null : index + 1)}
          />
        ))}
      </div>
      {open ? (
        <CitationPassage
          sourceId={sourceId}
          citation={open}
          onShowInBook={onShowInBook}
          onClose={() => select(null)}
        />
      ) : null}
    </div>
  );
}

/** One numbered chip; a second activation closes the passage it opened. */
function CitationChip({
  citation,
  index,
  open,
  onToggle,
}: {
  citation: Citation;
  index: number;
  open: boolean;
  onToggle: () => void;
}) {
  const isNote = citation.origin === "note";
  const label = isNote
    ? `Your note: ${citation.note_title ?? ""}`
    : `Citation: ${citation.section_path.join(" › ")}`;
  return (
    <button
      type="button"
      aria-label={label}
      aria-expanded={open}
      onClick={onToggle}
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium transition-colors ${
        open
          ? "bg-accent text-accent-foreground"
          : "bg-secondary text-secondary-foreground hover:bg-accent"
      }`}
    >
      <span className="tabular-nums">{index}</span>
      {isNote ? (
        <StickyNoteIcon className="size-3" />
      ) : (
        <BookOpenIcon className="size-3" />
      )}
    </button>
  );
}

/**
 * The open citation's passage, in flow beneath the answer: where it comes from,
 * what it says, and the way into it.
 *
 * A note citation reads distinctly — a "Your note — <title>" label and an "Open
 * note" link to `/notes/{id}` — and carries no into-the-book action, because the
 * passage it quotes is the reader's own (NL-03).
 */
function CitationPassage({
  sourceId,
  citation,
  onShowInBook,
  onClose,
}: {
  sourceId: string;
  citation: Citation;
  onShowInBook?: (anchor: string) => void;
  onClose: () => void;
}) {
  const isNote = citation.origin === "note";
  const title = citation.note_title ?? "";
  const label = isNote
    ? title
      ? `Your note — ${title}`
      : "Your note"
    : citation.section_path.join(" › ");

  return (
    <div
      data-testid="citation-passage"
      className="space-y-2 rounded-md border bg-muted/30 p-3"
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-medium text-muted-foreground">{label}</p>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label="Close passage"
          onClick={onClose}
        >
          <X />
        </Button>
      </div>
      {/* Clamped: a long passage scrolls in its own box rather than pushing the
          answer it belongs to off the screen. */}
      <blockquote className="prose-reading max-h-40 overflow-y-auto border-l-2 border-muted pl-3 italic text-muted-foreground">
        {citation.snippet}
      </blockquote>
      {isNote ? (
        <Link
          href={`/notes/${citation.note_id}`}
          className="inline-flex items-center gap-1.5 text-sm text-primary underline-offset-4 hover:underline"
        >
          <StickyNoteIcon className="size-3.5" />
          Open note
        </Link>
      ) : onShowInBook ? (
        <button
          type="button"
          onClick={() => onShowInBook(citation.anchor)}
          className="inline-flex items-center gap-1.5 text-sm text-primary underline-offset-4 hover:underline"
        >
          <BookOpenIcon className="size-3.5" />
          Show in book
        </button>
      ) : (
        <Link
          href={readUrl(sourceId, citation.anchor)}
          className="inline-flex items-center gap-1.5 text-sm text-primary underline-offset-4 hover:underline"
        >
          <BookOpenIcon className="size-3.5" />
          Open in book
        </Link>
      )}
    </div>
  );
}
