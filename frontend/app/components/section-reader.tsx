"use client";

/**
 * Section reader (FE-15/FE-17) — renders one cited section in context.
 *
 * Reads the section anchor from the URL (`?anchor=`, auto-decoded by
 * `useSearchParams`), resolves auth through `/api/auth/me`, then fetches the
 * section via `getSection` and renders its markdown with the same renderer the
 * streamed answers use (`MessageResponse`, a memoized Streamdown — raw HTML in
 * the markdown stays inert, never injected as live DOM). The section heading is
 * scrolled into view and transiently highlighted so a citation lands on its
 * passage.
 *
 * States: no anchor → a pick-a-section empty state (the sidebar tree is the
 * entry); unknown anchor → a readable not-found state with a way back; any other
 * load failure → a readable error. A 401 redirects via `onRequireAuth` — a
 * UX-only convenience, NOT the security boundary: FastAPI enforces auth and
 * ownership on `/api/sources/{id}/section` regardless of client-side routing
 * (FR-AUTH-007, ADR-017).
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { fetchAuthState } from "@/app/lib/auth";
import { captureHighlight, NoteError } from "@/app/lib/notes";
import { getSection, type SectionView } from "@/app/lib/sections";
import {
  CapturePopover,
  deriveCaptureSelection,
  type CaptureAction,
  type CaptureSelection,
} from "@/app/components/notes/capture-popover";
import { MessageResponse } from "@/components/ai-elements/message";

export function SectionReader({
  sourceId,
  onRequireAuth,
}: {
  sourceId: string;
  onRequireAuth?: () => void;
}) {
  // `useSearchParams().get()` decodes the percent-encoded anchor built by the
  // citation popover and sidebar tree links, closing the round-trip.
  const anchor = useSearchParams().get("anchor");

  if (!anchor) {
    return (
      <div className="mx-auto max-w-2xl py-12 text-center text-muted-foreground">
        <p>Pick a section from the sidebar to start reading.</p>
      </div>
    );
  }

  return (
    <SectionContent
      sourceId={sourceId}
      anchor={anchor}
      onRequireAuth={onRequireAuth}
    />
  );
}

type LoadState =
  | { kind: "loading" }
  | { kind: "signed-out" }
  | { kind: "not-found" }
  | { kind: "error"; message: string }
  | { kind: "found"; section: SectionView };

/** Resolve auth, fetch the section by anchor, and render the resolved state. */
function SectionContent({
  sourceId,
  anchor,
  onRequireAuth,
}: {
  sourceId: string;
  anchor: string;
  onRequireAuth?: () => void;
}) {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  // The CSRF token for the capture write (AD-007), read from the same
  // `/api/auth/me` resolve that gates the section read.
  const [csrf, setCsrf] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setState({ kind: "loading" });
    void (async () => {
      const auth = await fetchAuthState();
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
        const result = await getSection(sourceId, anchor);
        if (!active) {
          return;
        }
        setState(
          result.status === "not_found"
            ? { kind: "not-found" }
            : { kind: "found", section: result.section },
        );
      } catch (err) {
        if (!active) {
          return;
        }
        setState({
          kind: "error",
          message:
            err instanceof Error ? err.message : "Could not load that section.",
        });
      }
    })();
    return () => {
      active = false;
    };
  }, [sourceId, anchor, onRequireAuth]);

  if (state.kind === "loading") {
    return <p className="text-muted-foreground">Loading…</p>;
  }
  if (state.kind === "signed-out") {
    return <p className="text-muted-foreground">You are signed out.</p>;
  }
  if (state.kind === "not-found") {
    return (
      <div className="mx-auto max-w-2xl py-12 text-center">
        <p className="text-muted-foreground">
          We couldn&apos;t find that section.
        </p>
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
  return <FoundSection sourceId={sourceId} csrf={csrf} section={state.section} />;
}

/** A raised capture popover: the resolved selection payload plus its position. */
type ActiveCapture = CaptureSelection & { top: number; left: number };

/**
 * The resolved section: highlighted heading + breadcrumb + rendered markdown, with
 * reader highlight capture (NF-12). Selecting text over the prose raises a popover
 * whose "Highlight"/"Highlight + note" actions POST the selection (resolved against
 * the served Markdown, never the DOM) to the capture endpoint; "Highlight + note"
 * then opens the created note. A stale capture (the corpus was replaced mid-read)
 * surfaces a reload prompt rather than a silent failure.
 */
function FoundSection({
  sourceId,
  csrf,
  section,
}: {
  sourceId: string;
  csrf: string | null;
  section: SectionView;
}) {
  const router = useRouter();
  const titleRef = useRef<HTMLDivElement>(null);
  const proseRef = useRef<HTMLDivElement>(null);
  const [highlighted, setHighlighted] = useState(true);
  const [capture, setCapture] = useState<ActiveCapture | null>(null);
  const [pending, setPending] = useState(false);
  const [captureError, setCaptureError] = useState<string | null>(null);

  useEffect(() => {
    titleRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    const timer = setTimeout(() => setHighlighted(false), 2000);
    return () => clearTimeout(timer);
  }, []);

  // On mouse-up over the prose, resolve the selection against the served Markdown;
  // a resolvable selection raises the popover near it, anything else dismisses it.
  function handleMouseUp() {
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
    setCapture({ ...derived, ...selectionPosition(selection, proseRef.current) });
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
          anchor: section.anchor,
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

  const breadcrumb = section.section_path.join(" › ");

  return (
    <article className="relative mx-auto max-w-2xl py-6">
      <div
        ref={titleRef}
        data-testid="section-title"
        data-highlight={highlighted ? "on" : "off"}
        className="scroll-mt-16 rounded-md px-2 py-1 transition-colors duration-500 data-[highlight=on]:bg-accent"
      >
        {breadcrumb ? (
          <p className="text-xs text-muted-foreground">{breadcrumb}</p>
        ) : null}
        <h1 className="text-2xl font-semibold">{section.title}</h1>
      </div>
      <div
        ref={proseRef}
        onMouseUp={handleMouseUp}
        className="prose-reading mt-4"
      >
        <MessageResponse>{section.markdown}</MessageResponse>
      </div>
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
 * prose wrapper. Falls back to the wrapper origin when the DOM does not expose
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
