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

import { List } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import {
  CapturePopover,
  deriveCaptureSelection,
  type CaptureAction,
  type CaptureSelection,
} from "@/app/components/notes/capture-popover";
import { ReaderPanel, type PanelMode } from "@/app/components/reader-panel";
import { ReadingControls } from "@/app/components/reading-controls";
import { ChapterNav, TocPanel, readUrl } from "@/app/components/toc-panel";
import { useReadingSettings } from "@/app/components/use-reading-settings";
import { useRecedingChrome } from "@/app/components/use-receding-chrome";
import {
  useScrollPosition,
  type ObserverFactory,
} from "@/app/components/use-scroll-position";
import { fetchAuthState } from "@/app/lib/auth";
import { paintHighlights } from "@/app/lib/highlight-paint";
import { captureHighlight, NoteError } from "@/app/lib/notes";
import {
  getChapter,
  listHighlights,
  minutesLeft,
  type ChapterSectionView,
  type ChapterView,
  type SourceHighlightView,
} from "@/app/lib/reading";
import { MessageResponse } from "@/components/ai-elements/message";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/** A stable empty highlight list, so sections without highlights never repaint. */
const NO_HIGHLIGHTS: SourceHighlightView[] = [];

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
  // The caller's existing highlights, painted into the flow once they arrive.
  // They are P2 and non-blocking: the chapter renders without waiting on them,
  // and a failed fetch simply leaves the prose unpainted (RD-28/29).
  const [highlights, setHighlights] = useState<SourceHighlightView[]>([]);

  useEffect(() => {
    let active = true;
    setState({ kind: "loading" });
    setHighlights([]);
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
      // Fetch highlights alongside consuming the chapter; they paint in when
      // ready without gating first contentful render, and a failure is ignored.
      void listHighlights(sourceId)
        .then((found) => {
          if (active) {
            setHighlights(found);
          }
        })
        .catch(() => {});
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
      highlights={highlights}
      onRequireAuth={onRequireAuth}
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
  highlights = [],
  observerFactory,
  onRequireAuth,
}: {
  sourceId: string;
  csrf: string | null;
  chapter: ChapterView;
  scrollTarget: string | null;
  highlights?: SourceHighlightView[];
  observerFactory?: ObserverFactory;
  onRequireAuth?: () => void;
}) {
  const router = useRouter();
  // The open panel and the current deep-link anchor are independent URL state.
  // An unknown `panel` value renders the panel closed; toggling it or switching
  // modes preserves the anchor and never refetches the chapter (the load effect
  // lives in `ChapterReader` and is not keyed on `panel`).
  const searchParams = useSearchParams();
  const urlAnchor = searchParams.get("anchor");
  const panelParam = searchParams.get("panel");
  const panelMode: PanelMode | null =
    panelParam === "ask" ? "ask" : panelParam === "teach" ? "teach" : null;
  const articleRef = useRef<HTMLElement>(null);
  // Device-local reading surface: type size, spacing, and Default/Paper (RD-18).
  const reading = useReadingSettings();
  const { size, leading, appearance } = reading;
  // Group the caller's highlights by section anchor so each section paints only
  // its own (RD-28). The grouped arrays stay referentially stable while
  // `highlights` is unchanged, so a re-render (scroll/progress) never triggers a
  // needless repaint; status rides along because `paintHighlights` paints
  // `active` only.
  const highlightsByAnchor = useMemo(() => {
    const byAnchor = new Map<string, SourceHighlightView[]>();
    for (const highlight of highlights) {
      const list = byAnchor.get(highlight.anchor);
      if (list) {
        list.push(highlight);
      } else {
        byAnchor.set(highlight.anchor, [highlight]);
      }
    }
    return byAnchor;
  }, [highlights]);
  const [flashAnchor, setFlashAnchor] = useState<string | null>(scrollTarget);
  // The below-lg table of contents collapses behind the top-bar toggle (RD-25).
  const [tocOpen, setTocOpen] = useState(false);
  // Top bar recedes on downward scroll, restores on upward scroll (RD-31).
  const chromeHidden = useRecedingChrome();
  // When a deep link opens away from the stored reading position, offer a
  // one-click return to it (RD-24). A same-chapter TOC jump refreshes this to
  // the pre-jump section below.
  const [returnAnchor, setReturnAnchor] = useState<string | null>(() => {
    const stored = chapter.reading_position?.anchor ?? null;
    return stored && scrollTarget && scrollTarget !== stored ? stored : null;
  });
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

  // Once a return chip is showing, dismiss it after the reader has scrolled a
  // way past where the jump landed — they have settled into the new spot (RD-24).
  useEffect(() => {
    if (!returnAnchor) {
      return;
    }
    let baseline: number | null = null;
    function onScroll(event: Event) {
      const target = event.target;
      const y = target instanceof HTMLElement ? target.scrollTop : window.scrollY;
      if (baseline === null) {
        baseline = y;
        return;
      }
      if (Math.abs(y - baseline) > 400) {
        setReturnAnchor(null);
      }
    }
    window.addEventListener("scroll", onScroll, true);
    return () => window.removeEventListener("scroll", onScroll, true);
  }, [returnAnchor]);

  // Opening a panel mode or switching between modes is pure URL state: replace
  // the query in place (preserving the anchor) so it is deep-linkable and the
  // back button works, without a chapter refetch or a scroll reset.
  function handlePanelModeChange(mode: PanelMode) {
    router.replace(readUrl(sourceId, urlAnchor, { panel: mode }));
  }

  // Closing drops the panel param, restoring full reading width; the anchor rides
  // along so the reader stays where they were.
  function handlePanelClose() {
    router.replace(readUrl(sourceId, urlAnchor));
  }

  // A TOC click inside the loaded chapter scrolls within the flow rather than
  // reloading, and keeps the URL anchor in step so the deep link stays shareable.
  function handleSameChapterNavigate(anchor: string) {
    // Remember where the reader was so the chip can bring them back (RD-24).
    if (currentAnchor && currentAnchor !== anchor) {
      setReturnAnchor(currentAnchor);
    }
    document
      .getElementById(anchor)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
    router.replace(`/sources/${sourceId}/read?anchor=${encodeURIComponent(anchor)}`);
    setTocOpen(false);
  }

  // One-click return to the pre-jump position: scroll to it if it is in this
  // chapter, otherwise load its chapter; then dismiss the chip (RD-24).
  function handleReturn() {
    if (!returnAnchor) {
      return;
    }
    const target = document.getElementById(returnAnchor);
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
      router.replace(
        `/sources/${sourceId}/read?anchor=${encodeURIComponent(returnAnchor)}`,
      );
    } else {
      router.push(
        `/sources/${sourceId}/read?anchor=${encodeURIComponent(returnAnchor)}`,
      );
    }
    setReturnAnchor(null);
  }

  return (
    <div>
      <div className="sticky top-0 z-20">
        <div
          data-testid="reader-top-bar"
          className={cn(
            "flex items-center justify-between gap-4 border-b bg-background/80 px-4 py-2 backdrop-blur transition-transform duration-200 motion-reduce:transition-none",
            chromeHidden && "-translate-y-full",
          )}
        >
          <div className="flex min-w-0 items-center gap-2">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label="Table of contents"
              aria-expanded={tocOpen}
              className="lg:hidden"
              onClick={() => setTocOpen((prev) => !prev)}
            >
              <List />
            </Button>
            <span className="min-w-0 truncate text-sm font-medium">
              {chapter.chapter_title}
            </span>
          </div>
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
        <InkLine percent={bookPercent} />
      </div>
      <div className="lg:flex lg:items-start lg:gap-6">
        <TocPanel
          sourceId={sourceId}
          currentAnchor={currentAnchor}
          chapterAnchor={chapter.chapter_anchor}
          chapterSectionAnchors={chapter.sections.map((section) => section.anchor)}
          open={tocOpen}
          onSameChapterNavigate={handleSameChapterNavigate}
        />
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
          {chapter.sections.map((section) => (
            <FlowSection
              key={section.anchor}
              section={section}
              flashing={flashAnchor === section.anchor}
              highlights={highlightsByAnchor.get(section.anchor) ?? NO_HIGHLIGHTS}
              onMouseUp={() => handleMouseUp(section)}
            />
          ))}
          <ChapterNav
            sourceId={sourceId}
            prevAnchor={chapter.prev_anchor}
            nextAnchor={chapter.next_anchor}
          />
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
        {panelMode && csrf ? (
          <ReaderPanel
            sourceId={sourceId}
            csrf={csrf}
            mode={panelMode}
            onModeChange={handlePanelModeChange}
            onClose={handlePanelClose}
            onRequireAuth={onRequireAuth}
          />
        ) : null}
      </div>
      {returnAnchor ? <ReturnChip onReturn={handleReturn} /> : null}
    </div>
  );
}

/**
 * One section of the chapter flow: its structural heading (transiently flashed
 * when it is the deep-link target) and its Markdown rendered by the memoized
 * Streamdown. After the Markdown commits, the section's `active` highlights are
 * painted into the rendered prose (RD-28/29).
 *
 * The paint runs in an effect keyed on the Markdown and the section's highlights,
 * both stable across unrelated re-renders, so the injected marks survive: the
 * memoized `MessageResponse` subtree does not re-render while its Markdown is
 * unchanged, and the effect only repaints when the content or the highlight set
 * actually changes. `paintHighlights` is idempotent (unwrap-first), so even a
 * repaint yields the same DOM.
 */
function FlowSection({
  section,
  flashing,
  highlights,
  onMouseUp,
}: {
  section: ChapterSectionView;
  flashing: boolean;
  highlights: SourceHighlightView[];
  onMouseUp: () => void;
}) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const breadcrumb = section.section_path.join(" › ");

  useEffect(() => {
    const body = bodyRef.current;
    if (body) {
      paintHighlights(body, highlights);
    }
  }, [section.markdown, highlights]);

  return (
    <section
      id={section.anchor}
      data-section-anchor={section.anchor}
      onMouseUp={onMouseUp}
      className="scroll-mt-16"
    >
      <div
        data-section-heading={section.anchor}
        data-highlight={flashing ? "on" : "off"}
        className="rounded-md px-2 py-1 transition-colors duration-500 data-[highlight=on]:bg-accent"
      >
        {breadcrumb ? (
          <p className="text-xs text-muted-foreground">{breadcrumb}</p>
        ) : null}
        <h2 className="text-2xl font-semibold">{section.title}</h2>
      </div>
      <div ref={bodyRef}>
        <MessageResponse>{section.markdown}</MessageResponse>
      </div>
    </section>
  );
}

/**
 * The whole-book progress hairline (RD-30): a token-only rule whose fill tracks
 * the reading percent. It sits below the top bar and stays put when the bar
 * recedes, so progress is always legible. Colours come from identity tokens
 * (`--border` rail, `--primary` ink) — no raw hexes, so the leak scan stays green.
 */
function InkLine({ percent }: { percent: number }) {
  const clamped = Math.max(0, Math.min(100, percent));
  return (
    <div
      data-testid="ink-line"
      aria-hidden
      className="h-px w-full bg-border"
    >
      <div
        data-testid="ink-line-fill"
        style={{ width: `${clamped}%` }}
        className="h-full bg-primary transition-[width] duration-300 motion-reduce:transition-none"
      />
    </div>
  );
}

/**
 * The jump-back affordance (RD-24): a floating control that returns the reader to
 * the position they jumped away from. It is only mounted while a return target is
 * live, so its presence is itself the "there is somewhere to go back to" signal.
 */
function ReturnChip({ onReturn }: { onReturn: () => void }) {
  return (
    <button
      type="button"
      onClick={onReturn}
      className="fixed bottom-6 left-1/2 z-30 -translate-x-1/2 rounded-full border bg-card px-4 py-2 text-sm font-medium shadow-md ring-1 ring-foreground/10 transition-colors hover:bg-accent"
    >
      Return to where you were
    </button>
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
