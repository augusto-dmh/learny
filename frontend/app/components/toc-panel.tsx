"use client";

/**
 * In-reader table of contents and chapter navigation (RD-06/22/23/25).
 *
 * `TocPanel` lists the whole book's structure (the same `/structure` data the
 * library sidebar uses), fetched once on mount and cached, marking the current
 * chapter and — as the reader scrolls — the current section from the live scroll
 * state. Clicking an entry inside the loaded chapter scrolls to it in the flow
 * (no chapter reload); clicking an entry in another chapter loads that chapter.
 * Either way the URL `?anchor=` is kept in step so a deep link is always shareable.
 * At ≥lg the panel is a persistent side column; below lg it collapses behind the
 * top-bar toggle so it never squeezes the prose column.
 *
 * `ChapterNav` renders the previous/next-chapter controls from the chapter's
 * adjacent anchors, and renders nothing at a book edge (a single-chapter book has
 * neither) so the reader only ever sees a control that goes somewhere.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { readUrl } from "@/app/lib/read-url";
import { fetchSourceStructure } from "@/app/lib/sources";
import type { SourceStructure } from "@/app/lib/sources";
import { flattenSections } from "@/app/lib/tree";
import { cn } from "@/lib/utils";

export function TocPanel({
  sourceId,
  currentAnchor,
  chapterAnchor,
  chapterSectionAnchors,
  open,
  onSameChapterNavigate,
  fetchStructureImpl = fetchSourceStructure,
}: {
  sourceId: string;
  /** The topmost visible section (from scroll state) — the current section. */
  currentAnchor: string | null;
  /** The loaded chapter's anchor — the current chapter. */
  chapterAnchor: string;
  /** Anchors in the loaded chapter, to route same-chapter clicks to in-flow scroll. */
  chapterSectionAnchors: readonly string[];
  /** Whether the collapsed (below-lg) panel is open; always shown at ≥lg. */
  open: boolean;
  /** In-flow scroll for a same-chapter target (the parent also updates the URL). */
  onSameChapterNavigate: (anchor: string) => void;
  fetchStructureImpl?: typeof fetchSourceStructure;
}) {
  const router = useRouter();
  const [structure, setStructure] = useState<SourceStructure | null>(null);
  const [error, setError] = useState<string | null>(null);

  // The structure is fetched once per source and cached; scrolling and collapsing
  // never re-fetch it (the panel stays mounted).
  useEffect(() => {
    let active = true;
    fetchStructureImpl(sourceId)
      .then((next) => {
        if (active) setStructure(next);
      })
      .catch((err: unknown) => {
        if (active) {
          setError(
            err instanceof Error ? err.message : "Could not load the contents.",
          );
        }
      });
    return () => {
      active = false;
    };
  }, [sourceId, fetchStructureImpl]);

  function handleClick(anchor: string) {
    if (chapterSectionAnchors.includes(anchor)) {
      // Same chapter: scroll within the flow (the parent also replaces the URL).
      onSameChapterNavigate(anchor);
    } else {
      // Another chapter: load it (a new content round-trip), updating the URL.
      router.push(readUrl(sourceId, anchor));
    }
  }

  const sections = structure ? flattenSections(structure.sections) : [];

  return (
    <aside
      data-testid="toc-panel"
      data-state={open ? "open" : "closed"}
      aria-label="Table of contents"
      className={cn(
        "w-64 shrink-0 overflow-y-auto border-r pr-2 text-sm lg:block",
        open ? "block" : "hidden",
      )}
    >
      {error ? (
        // The TOC is a navigation aid, not the content: a failed structure load
        // degrades to a quiet note (never a content-competing alert) so the
        // chapter — and its deep links — stay fully usable.
        <p className="px-2 py-1 text-xs text-muted-foreground">{error}</p>
      ) : (
        <ul className="flex flex-col py-2">
          {sections.map((section) => {
            const isCurrentSection = section.anchor === currentAnchor;
            const isCurrentChapter = section.anchor === chapterAnchor;
            return (
              <li key={`${section.anchor}-${section.label}`}>
                <button
                  type="button"
                  onClick={() => handleClick(section.anchor)}
                  aria-current={isCurrentSection ? "location" : undefined}
                  data-current-chapter={isCurrentChapter ? "true" : undefined}
                  style={{ paddingLeft: `${0.5 + section.depth * 0.75}rem` }}
                  className={cn(
                    "w-full truncate rounded-md py-1 pr-2 text-left transition-colors hover:bg-accent/50",
                    isCurrentSection
                      ? "font-medium text-foreground"
                      : "text-muted-foreground",
                  )}
                >
                  {section.title}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}

export function ChapterNav({
  sourceId,
  prevAnchor,
  nextAnchor,
}: {
  sourceId: string;
  prevAnchor: string | null;
  nextAnchor: string | null;
}) {
  // At a book edge with neither neighbour (a single-chapter book) there is
  // nothing to navigate to, so the whole control is absent.
  if (!prevAnchor && !nextAnchor) {
    return null;
  }
  return (
    <nav
      aria-label="Chapter navigation"
      className="mt-8 flex items-center justify-between border-t pt-4 text-sm"
    >
      {prevAnchor ? (
        <Link
          href={readUrl(sourceId, prevAnchor)}
          className="text-primary underline-offset-4 hover:underline"
        >
          ← Previous chapter
        </Link>
      ) : (
        <span />
      )}
      {nextAnchor ? (
        <Link
          href={readUrl(sourceId, nextAnchor)}
          className="text-primary underline-offset-4 hover:underline"
        >
          Next chapter →
        </Link>
      ) : (
        <span />
      )}
    </nav>
  );
}
