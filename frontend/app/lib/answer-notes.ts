/**
 * Save a panel answer as a note (RA-20/21).
 *
 * A completed Ask/Teach answer with at least one citation can become a note. The
 * happy path is atomic and anchored: it captures a highlight on the first
 * citation's anchor (via the existing `/sources/{id}/highlights` seam) so the note
 * carries a book anchor, using the first paragraph of that citation's snippet — the
 * verbatim corpus text — as the quote and the answer as the body. When the capture
 * can't bind — the served evidence went stale (409) or the snippet yields no quote
 * — it degrades honestly to a plain note whose body carries the answer plus a
 * jump-back link to the anchor. Any other failure propagates so the UI can show it.
 *
 * The `captureImpl`/`createImpl` seams default to the real `lib/notes` clients and
 * exist so the unit tests can drive both legs without a network.
 */

import {
  captureHighlight,
  createNote,
  NoteError,
} from "./notes";
import { type Citation } from "./questions";
import { readUrl } from "./read-url";

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

/** The outcome of a save: an anchored highlight capture, or the plain-note fallback. */
export type SaveOutcome = { outcome: "anchored" | "plain" };

/**
 * Save a cited answer as a note. Captures an anchored highlight on the first
 * citation when a quote is available; falls back to a plain note carrying a
 * jump-back link on a stale capture (409) or an empty snippet. Callers guarantee
 * `citations` is non-empty (RA-22 hides the action otherwise).
 */
export async function saveAnswerAsNote({
  sourceId,
  question,
  answerText,
  citations,
  csrfToken,
  captureImpl = captureHighlight,
  createImpl = createNote,
}: {
  sourceId: string;
  question: string;
  answerText: string;
  citations: Citation[];
  csrfToken: string;
  captureImpl?: typeof captureHighlight;
  createImpl?: typeof createNote;
}): Promise<SaveOutcome> {
  const anchor = citations[0].anchor;
  const title = question.slice(0, TITLE_MAX);
  const quote = firstParagraph(citations[0].snippet);

  if (quote !== null) {
    try {
      await captureImpl(
        sourceId,
        { anchor, quote_exact: quote, title, body_markdown: answerText },
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

  const link = readUrl(sourceId, anchor);
  await createImpl(
    { title, body_markdown: `${answerText}\n\n[Open in book](${link})` },
    csrfToken,
  );
  return { outcome: "plain" };
}
