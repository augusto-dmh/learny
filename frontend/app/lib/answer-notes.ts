/**
 * Save a panel answer as a note (RA-20/21).
 *
 * A completed Ask/Teach answer with at least one citation can become a note. The
 * happy path is atomic and anchored: it captures a highlight on the first
 * citation's anchor (via the existing `/sources/{id}/highlights` seam) so the note
 * carries a book anchor, using the first paragraph of that citation's snippet — the
 * verbatim corpus text — as the quote and the answer as the body. When the quoted
 * capture can't bind — the served evidence went stale (409) or the snippet yields
 * no quote — the save still succeeds: it captures the same anchor with no quote,
 * which the book records as a section-level passage. Either way the answer is kept
 * and it is kept attached to where it came from. Any other failure propagates so
 * the UI can show it.
 *
 * The `captureImpl` seam defaults to the real `lib/notes` client and exists so the
 * unit tests can drive both legs without a network.
 */

import { captureHighlight, NoteError } from "./notes";
import { stripCitationMarkers, type Citation } from "./citations";

/**
 * Client-side truncation length for a note title derived from the question. The
 * backend enforces no title cap (only the note body is capped), so this is a
 * display choice for question-derived titles, not a mirror of a server limit.
 */
const TITLE_MAX = 80;

/**
 * The first non-empty paragraph of `text`, trimmed, or `null` when the text has no
 * non-blank content. Paragraphs are split on blank lines (one or more newlines
 * separated only by whitespace).
 */
export function firstParagraph(text: string): string | null {
  for (const block of text.split(/\n\s*\n/)) {
    const trimmed = block.trim();
    if (trimmed) {
      return trimmed;
    }
  }
  return null;
}

/**
 * The outcome of a save: a capture bound to the quoted passage, or — when there
 * is no quote to bind — one bound to the citation's section.
 */
export type SaveOutcome = { outcome: "anchored" | "section" };

/**
 * Save a cited answer as a note. Captures an anchored highlight on the first
 * citation when a quote is available; falls back to capturing the same anchor
 * with no quote on a stale capture (409) or an empty snippet, so the answer is
 * never lost and never lands without a passage. Callers guarantee `citations` is
 * non-empty (RA-22 hides the action otherwise).
 */
export async function saveAnswerAsNote({
  sourceId,
  question,
  answerText,
  citations,
  csrfToken,
  captureImpl = captureHighlight,
}: {
  sourceId: string;
  question: string;
  answerText: string;
  citations: Citation[];
  csrfToken: string;
  captureImpl?: typeof captureHighlight;
}): Promise<SaveOutcome> {
  const anchor = citations[0].anchor;
  const title = question.slice(0, TITLE_MAX);
  const quote = firstParagraph(citations[0].snippet);
  // The inline citation markers belong to the panel that renders them as marks;
  // a note is prose the reader keeps, and `[^1]` in it would point at a citation
  // list the note does not carry.
  const body = stripCitationMarkers(answerText);

  if (quote !== null) {
    try {
      await captureImpl(
        sourceId,
        { anchor, quote_exact: quote, title, body_markdown: body },
        csrfToken,
      );
      return { outcome: "anchored" };
    } catch (err) {
      // SPEC_DEVIATION: design.md names the fall-back kind "stale"; the real
      // `NoteError` kind for the 409 capture conflict (RA-21's "409 stale") is
      // "stale_capture" (lib/notes.ts). Any other error propagates.
      if (!(err instanceof NoteError) || err.kind !== "stale_capture") {
        throw err;
      }
    }
  }

  // No quote to bind — either the snippet had none or the served evidence moved.
  // An empty quote is the book's own shape for "this section, no exact words", so
  // the answer is still filed where it came from rather than nowhere.
  await captureImpl(
    sourceId,
    { anchor, quote_exact: "", title, body_markdown: body },
    csrfToken,
  );
  return { outcome: "section" };
}
