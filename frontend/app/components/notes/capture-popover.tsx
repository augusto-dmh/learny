"use client";

/**
 * Reader capture popover (NF-12) — the small overlay the chapter reader raises on
 * a text selection, offering "Highlight" (a bare highlight) and "Highlight + note"
 * (highlight, then open the new note). It is deliberately presentational: the
 * reader owns the selection, the capture call, and the pending/error state and
 * feeds them in, so `chapter-reader.tsx` stays readable.
 *
 * `deriveCaptureSelection` is the pure seam behind it (design §Risks): the
 * selection payload is computed against the SERVED Markdown string, never against
 * DOM ranges. The DOM only supplies the selected string; this function collapses
 * its whitespace (the backend's `normalize_text` idiom — runs of whitespace to a
 * single space) and locates it in the section's Markdown to derive the 32-char
 * prefix/suffix context. A selection that does not occur verbatim in the Markdown
 * (a formatting-only span, or one crossing a block boundary) yields `null`, and
 * the reader shows no popover.
 */

import { Button } from "@/components/ui/button";

const WHITESPACE = /\s+/g;
const CONTEXT_CHARS = 32;

/** The two capture actions the popover offers. */
export type CaptureAction = "highlight" | "highlight-note";

/** The selection payload resolved against the served Markdown, or `null`. */
export type CaptureSelection = {
  quote_exact: string;
  quote_prefix: string;
  quote_suffix: string;
};

/**
 * Resolve a reader selection to a capture payload against the served `markdown`,
 * or `null` when the selection is empty or does not occur verbatim in the Markdown
 * (a formatting-only or cross-block span). Whitespace is collapsed on both sides to
 * match the backend's normalized matching; the returned `quote_exact` keeps its
 * original case (the backend lowercases only for matching, and stores the quote as
 * given for the orphan badge), and the 32-char prefix/suffix are the surrounding
 * context the server uses to disambiguate a repeated quote.
 */
export function deriveCaptureSelection(
  markdown: string,
  selectedText: string,
): CaptureSelection | null {
  const quote = selectedText.replace(WHITESPACE, " ").trim();
  if (!quote) {
    return null;
  }
  const haystack = markdown.replace(WHITESPACE, " ");
  const index = haystack.indexOf(quote);
  if (index === -1) {
    return null;
  }
  const end = index + quote.length;
  return {
    quote_exact: quote,
    quote_prefix: haystack.slice(Math.max(0, index - CONTEXT_CHARS), index),
    quote_suffix: haystack.slice(end, end + CONTEXT_CHARS),
  };
}

/**
 * The floating capture actions. Positioned absolutely within the reader's
 * relatively-positioned prose wrapper via `top`/`left` (both in px, measured from
 * that wrapper). While a capture is in flight the actions disable; a failure (e.g.
 * a stale-capture reload prompt) renders below them.
 *
 * When the reader supplies `onExplain`/`onAskAbout`/`onCreateCard` the popover grows
 * to the full five-verb selection set (RA-15): Highlight and Note run the capture
 * flow unchanged (RA-16); Explain and Ask carry the verbatim `quote` up to the
 * reader panel; and Create card starts the capture-to-card flow (CAP-01), which the
 * reader owns because it sequences a highlight capture and a suggestion request.
 * Absent those callbacks it stays the original two-button capture popover, so the
 * highlight-capture flow is byte-identical wherever the verbs are not wired.
 */
export function CapturePopover({
  top,
  left,
  quote,
  pending,
  error,
  onCapture,
  onExplain,
  onAskAbout,
  onCreateCard,
}: {
  top: number;
  left: number;
  /** The resolved selection text, carried to Explain/Ask when the verbs are wired. */
  quote?: string;
  pending: boolean;
  error: string | null;
  onCapture: (action: CaptureAction) => void;
  onExplain?: (quote: string) => void;
  onAskAbout?: (quote: string) => void;
  onCreateCard?: () => void;
}) {
  // The full verb set only when the reader wires the panel- and card-bound verbs;
  // otherwise the popover is the original two-action capture control (RA-15/16).
  const verbs = Boolean(onExplain && onAskAbout && onCreateCard);
  return (
    <div
      role="dialog"
      aria-label="Capture highlight"
      className="absolute z-10 flex flex-col gap-1 rounded-md border bg-popover p-1 shadow-md"
      style={{ top, left }}
      // Keep the browser selection alive while the popover is clicked so the
      // capture reads the same range that raised it.
      onMouseDown={(event) => event.preventDefault()}
    >
      <div className="flex flex-wrap gap-1">
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={pending}
          onClick={() => onCapture("highlight")}
        >
          Highlight
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={pending}
          onClick={() => onCapture("highlight-note")}
        >
          {verbs ? "Note" : "Highlight + note"}
        </Button>
        {verbs ? (
          <>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={pending}
              onClick={() => onExplain?.(quote ?? "")}
            >
              Explain
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={pending}
              onClick={() => onAskAbout?.(quote ?? "")}
            >
              Ask
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={pending}
              onClick={() => onCreateCard?.()}
            >
              Create card
            </Button>
          </>
        ) : null}
      </div>
      {error ? (
        <p role="alert" className="px-2 pb-1 text-xs text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}
