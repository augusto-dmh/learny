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

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, type CSSProperties } from "react";

import {
  CapturePopover,
  deriveCaptureSelection,
  type CaptureAction,
  type CaptureSelection,
} from "@/app/components/notes/capture-popover";
import { ReadingControls } from "@/app/components/reading-controls";
import { useReadingSettings } from "@/app/components/use-reading-settings";
import {
  useScrollPosition,
  type ObserverFactory,
} from "@/app/components/use-scroll-position";
import { fetchAuthState } from "@/app/lib/auth";
import { captureHighlight, NoteError } from "@/app/lib/notes";
import {
  getChapter,
  minutesLeft,
  type ChapterSectionView,
  type ChapterView,
} from "@/app/lib/reading";
import { MessageResponse } from "@/components/ai-elements/message";
import { Skeleton } from "@/components/ui/skeleton";

type LoadState =
  | { kind: "loading" }
  | { kind: "signed-out" }
  | { kind: "not-found" }
  | { kind: "error"; message: string }
  | { kind: "found"; chapter: ChapterView };

/**
 * The reader entry point: resolves auth and the chapter *in parallel* (no
 * sequential auth→content chain, RD-26), then renders the resolved state. The URL
 * `?anchor=` is the deep-link target; when it is absent the chapter request omits
 * the anchor and the server resumes the stored position (RD-10) — still one
 * content round-trip.
 *
 * A 401 on the content fetch behaves exactly as before: `/api/auth/me` reports
 * anonymous and `onRequireAuth` redirects to login (a UX convenience, NOT the
 * security boundary — FastAPI enforces auth and ownership on every reader route
 * regardless of client-side routing, FR-AUTH-007/ADR-017).
 */
export function ChapterReader({
  sourceId,
  onRequireAuth,
}: {
  sourceId: string;
  onRequireAuth?: () => void;
}) {
  // `useSearchParams().get()` decodes the percent-encoded anchor; `null` when
  // absent, which asks the server to resume the stored reading position.
  const urlAnchor = useSearchParams().get("anchor");
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  // The CSRF token for the capture write (AD-007), read from the same
  // `/api/auth/me` resolve that gates the chapter read.
  const [csrf, setCsrf] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setState({ kind: "loading" });
    // Dispatch both requests before awaiting either — parallel, not chained.
    const authPromise = fetchAuthState();
    const chapterPromise = getChapter(sourceId, urlAnchor);
    // If we bail before consuming it (signed-out), a 401 on the content fetch
    // still needs a rejection handler so it is never an unhandled rejection.
    chapterPromise.catch(() => {});
    void (async () => {
      const auth = await authPromise;
      if (!active) {
        return;
      }
      if (!auth.authenticated) {
        setState({ kind: "signed-out" });
        onRequireAuth?.();
        return;
      }
      setCsrf(auth.user.csrf_token);
      try {
        const result = await chapterPromise;
        if (!active) {
          return;
        }
        setState(
          result.status === "not_found"
            ? { kind: "not-found" }
            : { kind: "found", chapter: result.chapter },
        );
      } catch (err) {
        if (!active) {
          return;
        }
        setState({
          kind: "error",
          message:
            err instanceof Error ? err.message : "Could not load this chapter.",
        });
      }
    })();
    return () => {
      active = false;
    };
  }, [sourceId, urlAnchor, onRequireAuth]);

  if (state.kind === "loading") {
    return <ReadingSkeleton />;
  }
  if (state.kind === "signed-out") {
    return <p className="text-muted-foreground">You are signed out.</p>;
  }
  if (state.kind === "not-found") {
    return (
      <div className="mx-auto max-w-2xl py-12 text-center">
        <p className="text-muted-foreground">We couldn’t find that chapter.</p>
        <Link
          href="/sources"
          className="text-primary underline-offset-4 hover:underline"
        >
          Back to your library
        </Link>
      </div>
    );
  }
  if (state.kind === "error") {
    return (
      <div className="mx-auto max-w-2xl py-12">
        <p role="alert" className="text-destructive">
          {state.message}
        </p>
      </div>
    );
  }
  // Deep-link target: the URL anchor, or the resumed position, or the chapter top.
  const scrollTarget = urlAnchor ?? state.chapter.reading_position?.anchor ?? null;
  return (
    <ChapterFlow
      sourceId={sourceId}
      csrf={csrf}
      chapter={state.chapter}
      scrollTarget={scrollTarget}
    />
  );
}

/** A reading-surface skeleton shown while the chapter loads (RD-27) — not bare text. */
function ReadingSkeleton() {
  return (
    <div
      data-testid="reading-skeleton"
      aria-hidden
      className="mx-auto max-w-2xl space-y-4 py-6"
    >
      <Skeleton className="h-8 w-2/3" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-5/6" />
      <Skeleton className="h-4 w-11/12" />
    </div>
  );
}

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
  observerFactory,
}: {
  sourceId: string;
  csrf: string | null;
  chapter: ChapterView;
  scrollTarget: string | null;
  observerFactory?: ObserverFactory;
}) {
  const router = useRouter();
  const articleRef = useRef<HTMLElement>(null);
  // Device-local reading surface: type size, spacing, and Default/Paper (RD-18).
  const reading = useReadingSettings();
  const { size, leading, appearance } = reading;
  const [flashAnchor, setFlashAnchor] = useState<string | null>(scrollTarget);
  const [capture, setCapture] = useState<ActiveCapture | null>(null);
  const [pending, setPending] = useState(false);
  const [captureError, setCaptureError] = useState<string | null>(null);

  // Track the topmost visible section as the reader scrolls, and persist the
  // position after each scroll-idle (RD-07/13).
  const { currentAnchor } = useScrollPosition({
    sourceId,
    csrf,
    anchors: chapter.sections.map((section) => section.anchor),
    initialAnchor: scrollTarget,
    containerRef: articleRef,
    observerFactory,
  });

  // Live progress from the current section's word offset (RD-11): whole-book
  // percent read, and chapter minutes-left at 220 wpm.
  const currentIndex = currentAnchor
    ? chapter.sections.findIndex((section) => section.anchor === currentAnchor)
    : -1;
  const wordsReadInChapter =
    currentIndex > 0
      ? chapter.sections
          .slice(0, currentIndex)
          .reduce((sum, section) => sum + section.word_count, 0)
      : 0;
  const bookPercent =
    chapter.total_word_count > 0
      ? ((chapter.words_before_chapter + wordsReadInChapter) /
          chapter.total_word_count) *
        100
      : 0;
  const chapterMinutesLeft = minutesLeft(
    chapter.chapter_word_count - wordsReadInChapter,
  );

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
    <div>
      <div
        data-testid="reader-top-bar"
        className="sticky top-0 z-20 flex items-center justify-between gap-4 border-b bg-background/80 px-4 py-2 backdrop-blur"
      >
        <span className="min-w-0 truncate text-sm font-medium">
          {chapter.chapter_title}
        </span>
        <div className="flex shrink-0 items-center gap-2">
          <span
            data-testid="reading-progress"
            className="text-xs text-muted-foreground tabular-nums"
          >
            {Math.round(bookPercent)}% read · {chapterMinutesLeft} min left
          </span>
          <ReadingControls
            size={reading.size}
            leading={reading.leading}
            appearance={reading.appearance}
            onSizeChange={reading.setSize}
            onLeadingChange={reading.setLeading}
            onAppearanceChange={reading.setAppearance}
          />
        </div>
      </div>
      <article
        ref={articleRef}
        data-appearance={appearance}
        style={
          {
            "--reading-size": `${size}px`,
            "--reading-leading": `${leading}`,
          } as CSSProperties
        }
        className="prose-reading relative mx-auto max-w-2xl bg-background py-6 text-foreground"
      >
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
    </div>
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
