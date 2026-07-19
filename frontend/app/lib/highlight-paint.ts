/**
 * Highlight matching (RD-29, matching half).
 *
 * The reader paints a captured highlight back onto the served chapter text by
 * locating its `quote_exact` within the rendered prose. A quote can occur more
 * than once in a section, so the capture also stored up-to-32-char prefix/suffix
 * context (the `deriveCaptureSelection` seam); this module reproduces the
 * disambiguation the backend uses for a fresh capture (ADR-0026 quote-with-context
 * semantics), but read-only and best-effort: a quote that cannot be located
 * *unambiguously* simply does not paint (the caller skips it), never mis-painting
 * the wrong range (spec edge: a formatting-boundary non-match is acceptable, a
 * mis-paint is not).
 */

/**
 * The character offset of `quote` in `haystack`, disambiguated by surrounding
 * context, or `null` when it cannot be placed unambiguously.
 *
 * - A single occurrence resolves to its offset (context is not needed).
 * - Multiple occurrences are filtered to those whose immediately preceding text
 *   ends with `prefix` and whose following text begins with `suffix`; the offset
 *   is returned only when exactly one occurrence survives the filter.
 * - Zero occurrences, or an ambiguous set the context cannot narrow to one,
 *   yield `null` (paint nothing rather than guess).
 *
 * An empty `prefix`/`suffix` matches any context, so a duplicated quote with no
 * distinguishing context stays ambiguous and yields `null`.
 */
export function findQuoteOffset(
  haystack: string,
  quote: string,
  prefix: string,
  suffix: string,
): number | null {
  if (!quote) {
    return null;
  }
  const offsets: number[] = [];
  for (let from = haystack.indexOf(quote); from !== -1; from = haystack.indexOf(quote, from + 1)) {
    offsets.push(from);
  }
  if (offsets.length === 0) {
    return null;
  }
  if (offsets.length === 1) {
    return offsets[0];
  }
  const matches = offsets.filter((index) => {
    const end = index + quote.length;
    const prefixOk =
      prefix === "" ||
      haystack.slice(Math.max(0, index - prefix.length), index) === prefix;
    const suffixOk =
      suffix === "" || haystack.slice(end, end + suffix.length) === suffix;
    return prefixOk && suffixOk;
  });
  return matches.length === 1 ? matches[0] : null;
}

/** The marker class carried by every painted highlight (styled in globals.css). */
const HIGHLIGHT_CLASS = "reader-highlight";

/** The subset of a source highlight the painter needs (see `SourceHighlightView`). */
export type PaintableHighlight = {
  note_id: string;
  quote_exact: string;
  quote_prefix: string;
  quote_suffix: string;
  status: "active" | "stale" | "orphaned";
};

/**
 * Paint the `active` highlights that match text inside `root`, wrapping each
 * located quote in a `<mark class="reader-highlight" data-note-id>` (RD-28/29).
 *
 * Idempotent: any marks a previous paint left are unwrapped first, so repainting
 * the same node with the same highlights yields the same DOM (the repaint effect
 * relies on this — design §Risks). Only text is wrapped; no characters are added
 * or removed, so selection and copy see the prose unchanged. `stale`/`orphaned`
 * anchors never paint (their quotes no longer match the served text by
 * definition), and a quote the context cannot place unambiguously is skipped in
 * silence — never mis-painted onto the wrong range.
 */
export function paintHighlights(
  root: HTMLElement,
  highlights: readonly PaintableHighlight[],
): void {
  unwrapMarks(root);
  for (const highlight of highlights) {
    if (highlight.status !== "active") {
      continue;
    }
    // Rebuilt per highlight: wrapping the previous one split its text nodes.
    const haystack = textOf(root);
    const offset = findQuoteOffset(
      haystack,
      highlight.quote_exact,
      highlight.quote_prefix,
      highlight.quote_suffix,
    );
    if (offset === null) {
      continue;
    }
    wrapRange(root, offset, offset + highlight.quote_exact.length, highlight.note_id);
  }
}

/** Concatenate every text node under `root` in document order. */
function textOf(root: HTMLElement): string {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let text = "";
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    text += node.nodeValue ?? "";
  }
  return text;
}

/**
 * Wrap the characters `[start, end)` of `root`'s concatenated text in highlight
 * marks. A range spanning several text nodes (e.g. across inline formatting)
 * paints one mark slice per node it touches, so the highlight is continuous even
 * where the prose is not a single text node.
 */
function wrapRange(root: HTMLElement, start: number, end: number, noteId: string): void {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  // Snapshot the text nodes and their offsets before mutating: splitText below
  // changes the tree, and we only ever wrap nodes captured up front.
  const nodes: { node: Text; start: number; end: number }[] = [];
  let offset = 0;
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const length = node.nodeValue?.length ?? 0;
    nodes.push({ node: node as Text, start: offset, end: offset + length });
    offset += length;
  }
  for (const { node, start: nodeStart, end: nodeEnd } of nodes) {
    const from = Math.max(start, nodeStart);
    const to = Math.min(end, nodeEnd);
    if (from >= to) {
      continue;
    }
    let target = node;
    const localFrom = from - nodeStart;
    if (localFrom > 0) {
      target = target.splitText(localFrom);
    }
    if (to - from < target.length) {
      target.splitText(to - from);
    }
    const mark = document.createElement("mark");
    mark.className = HIGHLIGHT_CLASS;
    mark.dataset.noteId = noteId;
    target.replaceWith(mark);
    mark.appendChild(target);
  }
}

/** Remove every highlight mark under `root`, restoring the plain text it wrapped. */
function unwrapMarks(root: HTMLElement): void {
  for (const mark of Array.from(root.querySelectorAll(`mark.${HIGHLIGHT_CLASS}`))) {
    const parent = mark.parentNode;
    if (!parent) {
      continue;
    }
    while (mark.firstChild) {
      parent.insertBefore(mark.firstChild, mark);
    }
    parent.removeChild(mark);
    // Merge the freed text back into its neighbours so the next paint measures
    // clean offsets.
    parent.normalize();
  }
}
