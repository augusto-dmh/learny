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
};
