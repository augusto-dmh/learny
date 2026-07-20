"use client";

/**
 * Margin rail (CAP-18..24) — the chapter's own annotations, beside the text.
 *
 * The rail lists the highlights and notes belonging to the *loaded chapter only*
 * (CAP-A7): it is reading-column furniture, not a notes browser, so a highlight
 * from another chapter — or another book — is filtered out by the chapter's own
 * section anchors. `/notes` remains the cross-book surface.
 *
 * Entries sit in document order, which here means the order of the chapter's
 * sections; several highlights inside one section keep the order the server
 * returned them in. Each entry shows its quote snapshot, and the origin note's
 * title as well when the student actually wrote something on it (CAP-19).
 *
 * An orphaned highlight — its passage gone after a re-ingest, kept forever per
 * ADR-026 — is the one entry that cannot be jumped to, because there is nothing
 * left in the chapter to scroll to. It renders from its stored quote snapshot and
 * offers its origin note instead (CAP-20/22), which is why it is a link rather
 * than a jump button: the "do not attempt a scroll" rule is structural, not a
 * conditional inside a handler. Orphan styling is `AnchorStatusBadge`'s job, not
 * this component's, so the treatment reads identically here and in `/notes`.
 *
 * Layout is AD-139: a flex sibling to the right of the article at `lg` and up,
 * and — because the reader's row is only `lg:flex` — the same markup falls in
 * after the article below `lg`, where the `<details>` makes it collapsible so it
 * never pushes the text off a small screen. The reader hides the rail outright
 * while the Ask/Teach panel is open (CAP-24); two right-hand columns would starve
 * the 65ch measure ADR-027 exists to protect.
 */

import Link from "next/link";
import { useMemo } from "react";

import { AnchorStatusBadge } from "@/app/components/notes/anchor-status-badge";
import type { SourceHighlightView } from "@/app/lib/reading";

/**
 * The chapter's annotations. `chapterAnchors` are the loaded chapter's section
 * anchors, in document order — they are both the scope filter and the sort key.
 * `onJump` brings a painted highlight into view; it is never called for an
 * orphaned entry.
 */
export function MarginRail({
  highlights,
  chapterAnchors,
  onJump,
}: {
  highlights: SourceHighlightView[];
  chapterAnchors: string[];
  onJump: (anchor: string) => void;
}) {
  const entries = useMemo(() => {
    // Position in the chapter, and membership of it, in one lookup.
    const order = new Map(chapterAnchors.map((anchor, index) => [anchor, index]));
    return highlights
      .filter((highlight) => order.has(highlight.anchor))
      .map((highlight, received) => ({ highlight, received }))
      .sort(
        (a, b) =>
          order.get(a.highlight.anchor)! - order.get(b.highlight.anchor)! ||
          a.received - b.received,
      )
      .map(({ highlight }) => highlight);
  }, [highlights, chapterAnchors]);

  return (
    <aside
      data-testid="margin-rail"
      aria-label="Chapter annotations"
      className="mt-6 lg:mt-0 lg:w-56 lg:shrink-0"
    >
      <details open>
        <summary className="cursor-pointer py-2 text-xs font-medium text-muted-foreground">
          In this chapter
        </summary>
        {entries.length === 0 ? (
          // An empty column reads as a rendering bug; say so instead (CAP-23).
          <p className="px-1 py-2 text-xs text-muted-foreground">
            Nothing highlighted in this chapter yet.
          </p>
        ) : (
          <ul className="flex flex-col gap-2 py-1">
            {entries.map((entry, index) => (
              <RailEntry
                key={`${entry.note_id}-${entry.anchor}-${index}`}
                highlight={entry}
                onJump={onJump}
              />
            ))}
          </ul>
        )}
      </details>
    </aside>
  );
}

/**
 * One annotation. The quote snapshot always renders — it is the only thing an
 * orphaned entry has left — and the note's title joins it when the student wrote
 * a body, so a real note is identified by what they called it rather than by the
 * sentence that started it.
 */
function RailEntry({
  highlight,
  onJump,
}: {
  highlight: SourceHighlightView;
  onJump: (anchor: string) => void;
}) {
  const orphaned = highlight.status === "orphaned";
  const label = (
    <>
      {highlight.has_body ? (
        <span className="block text-xs font-medium text-foreground">
          {highlight.note_title}
        </span>
      ) : null}
      <span
        data-testid="rail-quote"
        className="mt-0.5 block line-clamp-3 text-xs text-muted-foreground"
      >
        {highlight.quote_exact}
      </span>
    </>
  );

  return (
    <li data-testid="rail-entry" data-anchor={highlight.anchor}>
      {orphaned ? (
        // No jump target exists any more, so the entry offers the note instead.
        <Link
          href={`/notes/${highlight.note_id}`}
          className="block rounded-md border-l-2 px-2 py-1 text-left transition-colors hover:bg-accent"
        >
          {label}
        </Link>
      ) : (
        <button
          type="button"
          onClick={() => onJump(highlight.anchor)}
          className="block w-full rounded-md border-l-2 px-2 py-1 text-left transition-colors hover:bg-accent"
        >
          {label}
        </button>
      )}
      {highlight.status === "active" ? null : (
        <div className="px-2 pt-1">
          <AnchorStatusBadge status={highlight.status} />
        </div>
      )}
    </li>
  );
}
