/**
 * The page unit, made visible (RFC-006 Cycle B).
 *
 * An EPUB reflows, so the book has no page a reader can hold on to. The unit is
 * derived instead: the server owns the quantum (`words_per_page` on the chapter
 * response) and every section arrives with the words that precede it, so a page
 * boundary is arithmetic over word counts already stored — no re-ingestion, no
 * new corpus data.
 *
 * Numbering is book-global: page 1 begins at the book's first word and chapters
 * continue the count, so "p. 58" means the same thing wherever it is quoted.
 * That is why these helpers take *book* word offsets rather than section-local
 * ones, and why the running count is never reset at a boundary — the remainder
 * carries forward exactly as it does in the printed book.
 *
 * The split is between the section's Markdown blocks and only ever after a
 * paragraph: a rule inside a paragraph would break the passage the reader is
 * mid-sentence in, and a rule dropped between a list's items would restart the
 * list. When a boundary falls on a block that cannot carry a rule, the rule
 * defers to the next paragraph that can and takes its page number from there.
 */

/**
 * The book-global word offset of each section's first word.
 *
 * A chapter arrives with the words that precede *it*; each of its sections then
 * starts wherever the previous one ended. That running sum is what makes a
 * section's page rules continue the book rather than restart at every heading,
 * so it belongs beside the arithmetic it feeds — the offsets are the input
 * `pageAt` and `paginateSection` are given.
 *
 * The result is positional: entry `i` is section `i`'s offset, so the caller
 * indexes it alongside the sections it rendered.
 */
export function sectionOffsets(
  sections: readonly { word_count: number }[],
  wordsBeforeChapter: number,
): number[] {
  let running = wordsBeforeChapter;
  return sections.map((section) => {
    const before = running;
    running += section.word_count;
    return before;
  });
}

/** The 1-based page number of the point with `wordsBefore` words before it. */
export function pageAt(wordsBefore: number, wordsPerPage: number): number {
  if (wordsPerPage <= 0) {
    return 1;
  }
  return Math.floor(Math.max(0, wordsBefore) / wordsPerPage) + 1;
}

/**
 * A run of the section's Markdown, and the page rule that follows it — `null`
 * when nothing follows (the section's last run always is).
 */
export type PagedRun = { markdown: string; pageAfter: number | null };

/**
 * Split a section's Markdown into runs separated by page boundaries.
 *
 * `wordsBefore` is the book-global word offset of the section's first word, so
 * the first rule continues the book's numbering. A section with no boundary in
 * it (the common case) yields exactly one run carrying the served Markdown
 * untouched, so the overwhelming majority of sections render byte-for-byte as
 * they did before pages existed.
 */
export function paginateSection(
  markdown: string,
  { wordsBefore, wordsPerPage }: { wordsBefore: number; wordsPerPage: number },
): PagedRun[] {
  const whole: PagedRun[] = [{ markdown, pageAfter: null }];
  if (wordsPerPage <= 0) {
    return whole;
  }
  const blocks = splitBlocks(markdown);
  if (blocks.length < 2) {
    return whole;
  }
  const runs: PagedRun[] = [];
  let pending: string[] = [];
  let running = Math.max(0, wordsBefore);
  let page = pageAt(running, wordsPerPage);
  blocks.forEach((block, index) => {
    pending.push(block);
    running += countWords(block);
    const reached = pageAt(running, wordsPerPage);
    // Never after the final block: a rule there would rule off the section, not
    // a page turn inside it.
    const last = index === blocks.length - 1;
    if (reached > page && !last && isParagraph(block)) {
      runs.push({ markdown: pending.join("\n\n"), pageAfter: reached });
      pending = [];
      page = reached;
    }
  });
  if (runs.length === 0) {
    return whole;
  }
  if (pending.length > 0) {
    runs.push({ markdown: pending.join("\n\n"), pageAfter: null });
  }
  return runs;
}

/** Words in a block, counted the way a reader would: whitespace-separated runs. */
export function countWords(text: string): number {
  const trimmed = text.trim();
  return trimmed === "" ? 0 : trimmed.split(/\s+/).length;
}

/** A fence opening or closing a code block, which blank lines do not split. */
const FENCE = /^\s{0,3}(`{3,}|~{3,})/;

/**
 * Split Markdown into top-level blocks on blank lines, keeping fenced code
 * whole — a blank line inside a fence is part of the code, not a block break.
 */
function splitBlocks(markdown: string): string[] {
  const blocks: string[] = [];
  let current: string[] = [];
  let fence: string | null = null;
  for (const line of markdown.split("\n")) {
    const match = FENCE.exec(line);
    if (match) {
      const marker = match[1][0];
      fence = fence === null ? marker : fence === marker ? null : fence;
    }
    if (fence === null && line.trim() === "") {
      if (current.length > 0) {
        blocks.push(current.join("\n"));
        current = [];
      }
      continue;
    }
    current.push(line);
  }
  if (current.length > 0) {
    blocks.push(current.join("\n"));
  }
  return blocks;
}

/** Block openers that mean the block is not a plain paragraph. */
const NOT_PARAGRAPH = /^\s{0,3}(#{1,6}\s|[-*+]\s|\d+[.)]\s|>|\||`{3,}|~{3,}|<|!\[)/;

/**
 * Whether a rule may follow this block: only a plain paragraph qualifies. A
 * heading owns the passage under it, a rule between two list items or two rows
 * of a table would cut a structure in half, and an indented block is somebody
 * else's continuation.
 */
function isParagraph(block: string): boolean {
  const first = block.split("\n")[0];
  return (
    first.trim() !== "" && !/^\s{2,}/.test(first) && !NOT_PARAGRAPH.test(first)
  );
}
