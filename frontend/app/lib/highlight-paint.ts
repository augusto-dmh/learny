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
