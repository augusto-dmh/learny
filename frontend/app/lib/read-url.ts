import type { PanelQuery } from "@/app/components/reader-panel";

/**
 * The reader route for a source, with an optional anchor (encoded exactly once)
 * and an optional open dock tab. Both query params are independent, so a jump
 * can preserve the open panel and a tab switch can preserve the anchor.
 *
 * The single home for the reader-route URL contract: the TOC/chapter navigation,
 * the citation "open in book" link, and the saved-note jump-back all build the
 * same route through here so the shape never drifts across call sites. Ask and
 * Teach remain valid `panel` values so capture verbs and tombstones can still
 * write `?panel=ask` / `?panel=teach`.
 */
export function readUrl(
  sourceId: string,
  anchor: string | null,
  options: { panel?: PanelQuery | null } = {},
): string {
  const query: string[] = [];
  if (anchor) {
    query.push(`anchor=${encodeURIComponent(anchor)}`);
  }
  if (options.panel) {
    query.push(`panel=${options.panel}`);
  }
  return `/sources/${sourceId}/read${query.length ? `?${query.join("&")}` : ""}`;
}
