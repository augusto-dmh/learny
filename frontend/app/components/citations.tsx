"use client";

/**
 * Citation list + "open in book" popover (FE-16).
 *
 * Renders the grounded citations attached to a streamed answer or teaching turn
 * as compact chips. Clicking a chip opens a popover with the citation's
 * section-path breadcrumb, its verbatim passage, and a way into the reader at that
 * citation's anchor — turning citations into navigation, not decoration. The
 * popover never surfaces retrieval machinery (`chunk_id`, `score`): it speaks the
 * book's passage, not the index behind it (RA-12).
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
 * SPEC_DEVIATION: design named the AI Elements `InlineCitation`/`Sources`
 * compositions, but those model web sources — the card trigger derives a hostname
 * via `new URL(...)` (throws on a book anchor) and `Source` renders an external
 * `target="_blank"` link. Learny's citations are in-app book sections, so this
 * composes the vendored shadcn `Popover` primitive (owned source, AD-071) into a
 * click popover instead. Behavior matches FE-16 exactly.
 */

import Link from "next/link";
import { BookOpenIcon, StickyNoteIcon } from "lucide-react";

import { type Citation } from "@/app/lib/questions";
import { readUrl } from "@/app/lib/read-url";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

/** The citations attached to one answer, as clickable "open in book" chips. */
export function CitationList({
  sourceId,
  citations,
  onShowInBook,
}: {
  sourceId: string;
  citations: Citation[];
  /** In-reader jump: provided → "Show in book" button; absent → reader-route link. */
  onShowInBook?: (anchor: string) => void;
}) {
  if (citations.length === 0) {
    return null;
  }
  return (
    <div aria-label="citations" className="mt-3 flex flex-wrap gap-1.5">
      {citations.map((citation, index) =>
        citation.origin === "note" ? (
          <NoteCitationPopover
            key={citation.chunk_id}
            citation={citation}
            index={index + 1}
          />
        ) : (
          <CitationPopover
            key={citation.chunk_id}
            sourceId={sourceId}
            citation={citation}
            index={index + 1}
            onShowInBook={onShowInBook}
          />
        ),
      )}
    </div>
  );
}

/**
 * One note citation chip: opens a popover with the note's title, the cited
 * passage, and a link into the note itself (NL-03). Visibly distinct from a book
 * citation — a note glyph, a "Your note — <title>" label, and an "Open note" link
 * to `/notes/{id}` instead of any into-the-book action.
 */
function NoteCitationPopover({
  citation,
  index,
}: {
  citation: Citation;
  index: number;
}) {
  const title = citation.note_title ?? "";
  const label = title ? `Your note — ${title}` : "Your note";
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`Your note: ${title}`}
          className="inline-flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5 text-xs font-medium text-secondary-foreground transition-colors hover:bg-accent"
        >
          <span className="tabular-nums">{index}</span>
          <StickyNoteIcon className="size-3" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80">
        <p className="text-xs font-medium text-muted-foreground">{label}</p>
        <blockquote className="prose-reading border-l-2 border-muted pl-3 italic text-muted-foreground">
          {citation.snippet}
        </blockquote>
        <Link
          href={`/notes/${citation.note_id}`}
          className="inline-flex items-center gap-1.5 text-sm text-primary underline-offset-4 hover:underline"
        >
          <StickyNoteIcon className="size-3.5" />
          Open note
        </Link>
      </PopoverContent>
    </Popover>
  );
}

/** One citation chip: opens a popover with breadcrumb, passage, and reader jump. */
function CitationPopover({
  sourceId,
  citation,
  index,
  onShowInBook,
}: {
  sourceId: string;
  citation: Citation;
  index: number;
  onShowInBook?: (anchor: string) => void;
}) {
  const breadcrumb = citation.section_path.join(" › ");
  const href = readUrl(sourceId, citation.anchor);
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`Citation: ${breadcrumb}`}
          className="inline-flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5 text-xs font-medium text-secondary-foreground transition-colors hover:bg-accent"
        >
          <span className="tabular-nums">{index}</span>
          <BookOpenIcon className="size-3" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80">
        <p className="text-xs font-medium text-muted-foreground">{breadcrumb}</p>
        <blockquote className="prose-reading border-l-2 border-muted pl-3 italic text-muted-foreground">
          {citation.snippet}
        </blockquote>
        {onShowInBook ? (
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
            href={href}
            className="inline-flex items-center gap-1.5 text-sm text-primary underline-offset-4 hover:underline"
          >
            <BookOpenIcon className="size-3.5" />
            Open in book
          </Link>
        )}
      </PopoverContent>
    </Popover>
  );
}
