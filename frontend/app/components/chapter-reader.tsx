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
 *
 * The margin rail (CAP-18..24) renders the same highlight set as a column beside
 * the article, scoped to the loaded chapter, and yields to the Ask/Teach panel
 * when one is open (AD-139).
 *
 * "Create card" (CAP-01) builds on that same capture: the reader captures the
 * highlight, then asks for card suggestions on the anchor it produced, and renders
 * the resulting chips beside the passage. Sequencing the two calls here — rather
 * than folding generation into the capture endpoint — is what keeps a failed
 * generation from costing the student their highlight.
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
import { InkLine } from "@/app/components/ink-line";
import { MarginRail } from "@/app/components/margin-rail";
import { ReaderPanel, type PanelMode } from "@/app/components/reader-panel";
import { ReadingControls } from "@/app/components/reading-controls";
import { ChapterNav, TocPanel } from "@/app/components/toc-panel";
import { readUrl } from "@/app/lib/read-url";
import { useKeyShortcuts } from "@/app/components/use-key-shortcuts";
import { useReadingSettings } from "@/app/components/use-reading-settings";
import { useRecedingChrome } from "@/app/components/use-receding-chrome";
import {
  useScrollPosition,
  type ObserverFactory,
} from "@/app/components/use-scroll-position";
import { CardSuggestions } from "@/app/components/notes/card-suggestions";
import { fetchAuthState } from "@/app/lib/auth";
import { CardError, suggestCards, type CardSuggestion } from "@/app/lib/cards";
import { paintHighlights } from "@/app/lib/highlight-paint";
import { type PendingPanelRequest } from "@/app/lib/panel";
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

/**
 * What the reader says when the served evidence no longer matches the section — a
 * mid-flight re-ingest moved the passage out from under the selection. Shared by
 * the highlight capture and the capture-to-card flow, which fail the same way.
 */
const STALE_CAPTURE_MESSAGE =
  "The book changed while you were reading. Reload the page to capture this highlight.";

/** Pixels below the popover's top edge to drop the suggestion row, clearing the verbs. */
const SUGGESTIONS_OFFSET = 44;

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
  // The section anchors of the chapter currently in `found` state. A cross-chapter
  // jump changes `?anchor=` to an anchor this set does NOT contain and must reload
  // (RA-14); a same-chapter anchor change (a citation "Show in book" that lands in
  // this chapter, or a TOC jump within it) is served by the in-flow scroll effect,
  // so reloading — which would refetch the same chapter and reset the open panel
  // and scroll — is skipped (RA-13).
  const loadedRef = useRef<{ sourceId: string; anchors: Set<string> } | null>(
    null,
  );

  useEffect(() => {
    const loaded = loadedRef.current;
    if (
      urlAnchor &&
      loaded &&
      loaded.sourceId === sourceId &&
      loaded.anchors.has(urlAnchor)
    ) {
      // Same-chapter anchor change: the flow scrolls to it in place; no reload.
      return;
    }
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
        if (result.status === "not_found") {
          loadedRef.current = null;
          setState({ kind: "not-found" });
        } else {
          // Remember the loaded chapter's anchors so a later same-chapter anchor
          // change scrolls in place instead of reloading (RA-13/14).
          loadedRef.current = {
            sourceId,
            anchors: new Set(
              result.chapter.sections.map((section) => section.anchor),
            ),
          };
          setState({ kind: "found", chapter: result.chapter });
        }
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
  // The loaded chapter's section anchors in document order — the scroll tracker's
  // observation set, the TOC's in-chapter test, and the rail's chapter scope.
  const sectionAnchors = useMemo(
    () => chapter.sections.map((section) => section.anchor),
    [chapter.sections],
  );
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
  // The capture-to-card flow (CAP-01). The highlight is captured first and its
  // anchor id kept here, so a suggestion request that fails afterwards can be
  // retried on its own — the highlight is already saved and must not be captured
  // twice. `suggestions` holds the batch until the student resolves every chip;
  // an empty array is a real answer ("no cards for this passage"), not an error,
  // which is why it is distinct from `null` (no request made yet).
  const [cardAnchorId, setCardAnchorId] = useState<string | null>(null);
  // The note that `cardAnchorId` belongs to. Create card captures a highlight as its
  // first step, so the passage is already saved: the plain capture verbs must reuse
  // that note instead of writing a second one for the same words.
  const [cardNoteId, setCardNoteId] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<CardSuggestion[] | null>(null);
  // A selection verb (Explain/Ask) the reader hands to the Ask panel: it carries
  // the verbatim quote and the selection's section anchor, is opened in ask mode,
  // and is cleared once the panel has consumed it (RA-17/18).
  const [pendingRequest, setPendingRequest] =
    useState<PendingPanelRequest | null>(null);

  // Track the topmost visible section as the reader scrolls, and persist the
  // position after each scroll-idle (RD-07/13).
  const { currentAnchor } = useScrollPosition({
    sourceId,
    csrf,
    anchors: sectionAnchors,
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
    // A new selection starts a new card flow: neither the previous highlight's
    // anchor nor its suggestions belong to this passage.
    setCardAnchorId(null);
    setCardNoteId(null);
    setSuggestions(null);
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
    // Create card already saved this passage. Capturing again would leave the student
    // with two identical highlights for one selection, so reuse what it wrote: the
    // highlight verb has nothing left to do, and the note verb opens the note itself.
    if (cardNoteId) {
      const existing = cardNoteId;
      setCapture(null);
      setSuggestions(null);
      setCardAnchorId(null);
      setCardNoteId(null);
      if (action === "highlight-note") {
        router.push(`/notes/${existing}`);
      }
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
      setCaptureError(captureMessage(err, "Could not capture the highlight."));
    } finally {
      setPending(false);
    }
  }

  // The fifth verb (CAP-01): capture the highlight, then ask for card suggestions
  // on the anchor it produced. The two calls stay separate on purpose — generation
  // has no write side effects — so a failure between them leaves a perfectly good
  // highlight behind. `cardAnchorId` remembers that highlight, so pressing the verb
  // again retries only the generation step instead of capturing the passage twice.
  async function handleCreateCard() {
    if (!capture || !csrf) {
      return;
    }
    setPending(true);
    setCaptureError(null);
    try {
      let anchorId = cardAnchorId;
      if (!anchorId) {
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
        anchorId = note.anchors[0]?.id ?? null;
        if (!anchorId) {
          throw new Error("Could not anchor this passage to the book.");
        }
        setCardAnchorId(anchorId);
        setCardNoteId(note.id);
      }
      setSuggestions(await suggestCards(sourceId, anchorId, csrf));
    } catch (err) {
      setCaptureError(captureMessage(err, "Could not suggest cards for this passage."));
    } finally {
      setPending(false);
    }
  }

  // The student has resolved every suggestion: close the whole flow.
  function handleSuggestionsDismissed() {
    setSuggestions(null);
    setCardAnchorId(null);
    setCardNoteId(null);
    setCapture(null);
  }

  // The two capture verbs on bare keys (CAP-28/29), live only while the popover
  // is up: with nothing selected there is no passage to act on, and a key that
  // fired anyway would do something the student cannot see. Both keys run the
  // very same handlers the buttons do, so the two routes can never diverge.
  useKeyShortcuts(
    {
      h: () => void handleCapture("highlight"),
      c: () => void handleCreateCard(),
    },
    Boolean(capture),
  );

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

  // Bring a cited (or taught) passage into view without leaving the answer
  // (RA-11/13/14). An anchor in the loaded chapter scrolls to it in the flow and
  // flashes its heading, keeping the panel open and the URL anchor in step (the
  // loaded-chapter guard in `ChapterReader` makes this a no-reload replace); an
  // anchor in another chapter navigates there, carrying the open panel along so
  // the answer stays beside the book.
  function handleShowInBook(anchor: string) {
    const inChapter = sectionAnchors.includes(anchor);
    if (!inChapter) {
      router.push(readUrl(sourceId, anchor, { panel: panelMode }));
      return;
    }
    document
      .getElementById(anchor)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
    setFlashAnchor(anchor);
    router.replace(readUrl(sourceId, anchor, { panel: panelMode }));
  }

  // A selection verb routes the passage into the Ask panel: stash the request,
  // dismiss the capture popover, and open the panel in ask mode when it is closed
  // (a shallow URL replace that preserves the anchor). The panel auto-submits an
  // Explain, or attaches an Ask quote to the next typed question (RA-17/18).
  function openAskWithPassage(request: PendingPanelRequest) {
    setPendingRequest(request);
    setCapture(null);
    if (panelMode !== "ask") {
      router.replace(readUrl(sourceId, urlAnchor, { panel: "ask" }));
    }
  }

  function handleExplain(quote: string) {
    if (!capture) {
      return;
    }
    openAskWithPassage({ kind: "explain", quote, anchor: capture.anchor });
  }

  function handleAskAbout(quote: string) {
    if (!capture) {
      return;
    }
    openAskWithPassage({ kind: "ask", quote, anchor: capture.anchor });
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
          chapterSectionAnchors={sectionAnchors}
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
              quote={capture.quote_exact}
              pending={pending}
              error={captureError}
              onCapture={handleCapture}
              onExplain={handleExplain}
              onAskAbout={handleAskAbout}
              onCreateCard={handleCreateCard}
            />
          ) : null}
          {capture && suggestions && cardAnchorId && csrf ? (
            // A sibling of the popover rather than a child of it: the popover
            // suppresses mousedown to keep the selection alive, which would also
            // stop the inline edit fields from taking focus.
            <div
              className="absolute z-10 w-72"
              style={{ top: capture.top + SUGGESTIONS_OFFSET, left: capture.left }}
            >
              <CardSuggestions
                sourceId={sourceId}
                noteAnchorId={cardAnchorId}
                csrf={csrf}
                suggestions={suggestions}
                onDismiss={handleSuggestionsDismissed}
              />
            </div>
          ) : null}
        </article>
        {panelMode ? null : (
          // The panel wins the right-hand column (AD-139): the rail is ambient
          // context for reading, and two columns at once starve the measure.
          <MarginRail
            highlights={highlights}
            chapterAnchors={sectionAnchors}
            onJump={handleShowInBook}
          />
        )}
        {panelMode && csrf ? (
          <ReaderPanel
            sourceId={sourceId}
            csrf={csrf}
            mode={panelMode}
            onModeChange={handlePanelModeChange}
            onClose={handlePanelClose}
            pendingRequest={pendingRequest}
            onPendingConsumed={() => setPendingRequest(null)}
            onShowInBook={handleShowInBook}
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
 * The message for a failed capture-side call. A stale target — the passage moved
 * under the selection — gets the reload prompt whichever call reported it: both the
 * highlight capture (`NoteError`) and the suggestion request (`CardError`) surface
 * the same 409 as kind `stale_capture`. Everything else shows its own message.
 */
function captureMessage(err: unknown, fallback: string): string {
  if (
    (err instanceof NoteError || err instanceof CardError) &&
    err.kind === "stale_capture"
  ) {
    return STALE_CAPTURE_MESSAGE;
  }
  return err instanceof Error ? err.message : fallback;
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
