/**
 * Browser-side section-content client (FE-14/FE-15).
 *
 * Reads one section's markdown by anchor through the same-origin Next.js proxy
 * (`/api/...`, ADR-017) so a citation or a tree node opens the cited passage in
 * the reader. A read-only GET, so no CSRF token; the HttpOnly session cookie
 * rides along automatically (`credentials: "same-origin"`).
 *
 * The anchor is `href[#fragment]` — it carries reserved characters (`/`, `#`), so
 * it is `encodeURIComponent`-encoded exactly once into the `anchor` query param.
 * A 404 (unknown anchor, absent corpus, or a non-owned source) is an expected
 * outcome the reader renders as a not-found state, so it returns a typed
 * `not_found` result rather than throwing; other non-OK responses (401, …) throw.
 */

/** One section's readable content, mirroring the backend `SectionContentView`. */
export type SectionView = {
  anchor: string;
  title: string;
  section_path: string[];
  markdown: string;
};

/** The section either resolved, or its anchor matched nothing (404). */
export type SectionResult =
  | { status: "found"; section: SectionView }
  | { status: "not_found" };

/**
 * Fetch one section's content by anchor. Returns `{status: "not_found"}` on 404
 * (the reader's not-found state); throws a readable error on any other non-OK
 * response (e.g. 401 unauthenticated).
 */
export async function getSection(
  sourceId: string,
  anchor: string,
  fetchImpl: typeof fetch = fetch,
): Promise<SectionResult> {
  const res = await fetchImpl(
    `/api/sources/${sourceId}/section?anchor=${encodeURIComponent(anchor)}`,
    { method: "GET", credentials: "same-origin" },
  );
  if (res.status === 404) {
    return { status: "not_found" };
  }
  if (!res.ok) {
    throw await toSectionError(res, "Could not load that section.");
  }
  return { status: "found", section: (await res.json()) as SectionView };
}

/** Build an Error from a non-OK response, preferring the backend's detail. */
async function toSectionError(res: Response, fallback: string): Promise<Error> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    return new Error(typeof body.detail === "string" ? body.detail : fallback);
  } catch {
    return new Error(fallback);
  }
}
