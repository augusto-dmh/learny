/**
 * The citation shape every grounded surface shares, mirroring the backend
 * `EvidenceView`.
 *
 * It lives on its own because it belongs to no single caller: conversations carry
 * it on turns, the streaming transport carries it on a data part, the citation
 * list renders it, and saving an answer to a note reads it. Hanging it off any one
 * of those would make the others depend on that surface for a type that outlives
 * it.
 */

/**
 * One grounded citation.
 *
 * `origin`/`note_id`/`note_title` are present only for a citation drawn from the
 * user's own note (NL-03); the backend omits them for book citations, so they are
 * optional and a book-only payload still typechecks. When `origin` is `"note"` the
 * citation is rendered distinctly ("Your note — …") and links to the note, never
 * into the book.
 */
export type Citation = {
  chunk_id: string;
  source_id: string;
  section_path: string[];
  anchor: string;
  page_span: Record<string, unknown> | null;
  snippet: string;
  score: number;
  origin?: "book" | "note";
  note_id?: string;
  note_title?: string;
  /**
   * Claim-level span when the adapter mapped one. The three keys travel together
   * and are omitted on legacy rows and the deterministic adapter (ASK-17).
   * `document_index` is adapter-only and never appears here.
   */
  quoted_text?: string;
  start_char?: number;
  end_char?: number;
};

/**
 * The inline citation marker the backend writes into answer text: `[^n]`, where
 * *n* is the 1-based position of the citation in the turn's citation list (both
 * are the same first-occurrence walk, so marker *n* is `citations[n - 1]` by
 * construction — AD-222).
 *
 * The marker is plain text, which is what makes a mark survive persistence: a
 * restored turn carries the same tokens the stream did and renders the same
 * marks from them.
 */
const MARKER = /\[\^(\d+)\]/g;

/** The link a rendered mark carries, from which its citation number is read back. */
const MARK_HREF_PREFIX = "#citation-";

/**
 * Rewrite each marker backed by one of `count` citations into a Markdown link the
 * answer renderer turns into an interactive mark.
 *
 * A marker with no citation behind it — grounding the model claimed but the turn
 * did not carry — is left exactly as written, so it renders as the plain text it
 * is rather than a control that leads nowhere.
 */
export function linkCitationMarkers(text: string, count: number): string {
  return text.replace(MARKER, (token, digits: string) => {
    const index = Number(digits);
    return index >= 1 && index <= count
      ? `[${index}](${MARK_HREF_PREFIX}${index})`
      : token;
  });
}

/** The 1-based citation a rendered mark's link points at, or `null` for any other link. */
export function citationIndexFromHref(href: string | undefined): number | null {
  if (!href || !href.startsWith(MARK_HREF_PREFIX)) {
    return null;
  }
  const index = Number(href.slice(MARK_HREF_PREFIX.length));
  return Number.isInteger(index) && index >= 1 ? index : null;
}

/**
 * The answer text with its markers removed — what an answer reads like outside
 * the panel that renders marks.
 *
 * Saving an answer as a note takes this path: a note is prose the reader keeps,
 * and `[^1]` in it would point at a citation list the note does not carry.
 */
export function stripCitationMarkers(text: string): string {
  return text.replace(MARKER, "");
}
