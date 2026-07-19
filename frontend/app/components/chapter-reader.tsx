"use client";

/**
 * Chapter-flow reader (RD-03/04) — renders one chapter as a single continuous,
 * scrollable article.
 *
 * `ChapterFlow` is the found-state renderer: every section of the loaded chapter
 * is laid out in order inside one `.prose-reading` article, each wrapped in a
 * `<section id={anchor} data-section-anchor>` so a deep link (`?anchor=`) or a
 * TOC jump resolves to a DOM id. Each section's markdown is rendered with the
 * same memoized Streamdown the streamed answers use (`MessageResponse` — raw HTML
 * in the markdown stays inert, never injected as live DOM). A `scrollTarget`
 * (the URL anchor, or the resumed reading position) is scrolled into view once
 * per change and its section heading is transiently highlighted so the reader
 * lands on the cited passage.
 *
 * Highlight capture (NF-12) is ported here unchanged: selecting text over a
 * section raises a popover whose actions POST the selection — resolved against
 * that section's served Markdown via the pure `deriveCaptureSelection` seam,
 * never the DOM — to the capture endpoint. The per-section `onMouseUp` closes
 * over the right section so a multi-section chapter resolves each selection
 * against its own Markdown and anchor.
 */

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import {
  CapturePopover,
  deriveCaptureSelection,
  type CaptureAction,
  type CaptureSelection,
} from "@/app/components/notes/capture-popover";
import { captureHighlight, NoteError } from "@/app/lib/notes";
import type { ChapterSectionView, ChapterView } from "@/app/lib/reading";
import { MessageResponse } from "@/components/ai-elements/message";

/** A raised capture popover: the resolved selection payload, its section anchor, and position. */
type ActiveCapture = CaptureSelection & { anchor: string; top: number; left: number };

/**
 * The loaded chapter as one continuous article, with deep-link scroll and inline
 * highlight capture. `scrollTarget` is the anchor to land on (the URL `?anchor=`
 * or the resumed reading position); `csrf` is the token for the capture write
 * (null until auth resolves, though the found state always carries it).
 */
export function ChapterFlow({
  sourceId,
  csrf,
  chapter,
  scrollTarget,
}: {
  sourceId: string;
  csrf: string | null;
  chapter: ChapterView;
  scrollTarget: string | null;
}) {
  const router = useRouter();
  const articleRef = useRef<HTMLElement>(null);
  const [flashAnchor, setFlashAnchor] = useState<string | null>(scrollTarget);
  const [capture, setCapture] = useState<ActiveCapture | null>(null);
  const [pending, setPending] = useState(false);
  const [captureError, setCaptureError] = useState<string | null>(null);

  // Scroll the deep-link / resume target into view once per change and flash its
  // section heading. `getElementById` resolves the anchor verbatim — section ids
  // carry `#fragment`, which a CSS selector could not match.
  useEffect(() => {
    if (!scrollTarget) {
      setFlashAnchor(null);
      return;
    }
    document
      .getElementById(scrollTarget)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
    setFlashAnchor(scrollTarget);
    const timer = setTimeout(() => setFlashAnchor(null), 2000);
    return () => clearTimeout(timer);
  }, [scrollTarget]);

  // On mouse-up over a section, resolve the selection against THAT section's
  // served Markdown; a resolvable selection raises the popover near it, anything
  // else dismisses it. The closure carries the section's anchor for the write.
  function handleMouseUp(section: ChapterSectionView) {
    const selection = window.getSelection();
    const derived = deriveCaptureSelection(
      section.markdown,
      selection?.toString() ?? "",
    );
    if (!derived) {
      setCapture(null);
      return;
    }
    setCaptureError(null);
    setCapture({
      ...derived,
      anchor: section.anchor,
      ...selectionPosition(selection, articleRef.current),
    });
  }

  async function handleCapture(action: CaptureAction) {
    if (!capture || !csrf) {
      return;
    }
    setPending(true);
    setCaptureError(null);
    try {
      const note = await captureHighlight(
        sourceId,
        {
          anchor: capture.anchor,
          quote_exact: capture.quote_exact,
          quote_prefix: capture.quote_prefix,
          quote_suffix: capture.quote_suffix,
          title: capture.quote_exact.slice(0, 120),
        },
        csrf,
      );
      setCapture(null);
      if (action === "highlight-note") {
        router.push(`/notes/${note.id}`);
      }
    } catch (err) {
      setCaptureError(
        err instanceof NoteError && err.kind === "stale_capture"
          ? "The book changed while you were reading. Reload the page to capture this highlight."
          : err instanceof Error
            ? err.message
            : "Could not capture the highlight.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <article ref={articleRef} className="prose-reading relative mx-auto max-w-2xl py-6">
      {chapter.sections.map((section) => {
        const breadcrumb = section.section_path.join(" › ");
        return (
          <section
            key={section.anchor}
            id={section.anchor}
            data-section-anchor={section.anchor}
            onMouseUp={() => handleMouseUp(section)}
            className="scroll-mt-16"
          >
            <div
              data-section-heading={section.anchor}
              data-highlight={flashAnchor === section.anchor ? "on" : "off"}
              className="rounded-md px-2 py-1 transition-colors duration-500 data-[highlight=on]:bg-accent"
            >
              {breadcrumb ? (
                <p className="text-xs text-muted-foreground">{breadcrumb}</p>
              ) : null}
              <h2 className="text-2xl font-semibold">{section.title}</h2>
            </div>
            <MessageResponse>{section.markdown}</MessageResponse>
          </section>
        );
      })}
      {capture ? (
        <CapturePopover
          top={capture.top}
          left={capture.left}
          pending={pending}
          error={captureError}
          onCapture={handleCapture}
        />
      ) : null}
    </article>
  );
}

/**
 * Position the popover just above the selection, in coordinates relative to the
 * article wrapper. Falls back to the wrapper origin when the DOM does not expose
 * range geometry (e.g. jsdom), so capture stays usable and testable.
 */
function selectionPosition(
  selection: Selection | null,
  container: HTMLElement | null,
): { top: number; left: number } {
  if (!selection || selection.rangeCount === 0 || !container) {
    return { top: 0, left: 0 };
  }
  const range = selection.getRangeAt(0);
  const rect = range.getBoundingClientRect?.();
  const containerRect = container.getBoundingClientRect?.();
  if (!rect || !containerRect) {
    return { top: 0, left: 0 };
  }
  return {
    top: rect.top - containerRect.top,
    left: rect.left - containerRect.left,
  };
}
