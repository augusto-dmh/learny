"use client";

/**
 * Citation list + "open in book" popover (FE-16).
 *
 * Renders the grounded citations attached to a streamed answer or teaching turn
 * as compact chips. Clicking a chip opens a popover with the citation's
 * section-path breadcrumb, its snippet, and an "Open in book" link into the
 * reader at that citation's anchor — turning citations into navigation, not
 * decoration.
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
import { BookOpenIcon } from "lucide-react";

import { type Citation } from "@/app/lib/questions";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

/** The citations attached to one answer, as clickable "open in book" chips. */
export function CitationList({
  sourceId,
  citations,
}: {
  sourceId: string;
  citations: Citation[];
}) {
  if (citations.length === 0) {
    return null;
  }
  return (
    <div aria-label="citations" className="mt-3 flex flex-wrap gap-1.5">
      {citations.map((citation, index) => (
        <CitationPopover
          key={citation.chunk_id}
          sourceId={sourceId}
          citation={citation}
          index={index + 1}
        />
      ))}
    </div>
  );
}

/** One citation chip: opens a popover with breadcrumb, snippet, and reader link. */
function CitationPopover({
  sourceId,
  citation,
  index,
}: {
  sourceId: string;
  citation: Citation;
  index: number;
}) {
  const breadcrumb = citation.section_path.join(" › ");
  const href = `/sources/${sourceId}/read?anchor=${encodeURIComponent(
    citation.anchor,
  )}`;
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
        <Link
          href={href}
          className="inline-flex items-center gap-1.5 text-sm text-primary underline-offset-4 hover:underline"
        >
          <BookOpenIcon className="size-3.5" />
          Open in book
        </Link>
      </PopoverContent>
    </Popover>
  );
}
