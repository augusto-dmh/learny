/**
 * The guest sample ask client (AD-320 thaw).
 *
 * Thin browser-side call to the one unauthenticated ask route, shaped like the
 * other `app/lib` request clients: an `ApiError` carrying the `sampleAsk`
 * operation key for a non-OK response, and the parsed answer otherwise. No
 * session, no CSRF token — the route is for signed-out visitors by design and
 * is capped backend-side, so this layer holds no policy.
 */

import { apiErrorFrom } from "./errors";
import type { Citation } from "./citations";

export type SampleAskResult = {
  /** False for the honest misses: nothing relevant, or nothing grounded. */
  found: boolean;
  answer: string | null;
  citations: Citation[];
  /** Always true on this route: the answer is the shared sample's. */
  sample: boolean;
};

/** Ask the shared sample one question; backend rate limit + budget apply. */
export async function askSample(
  question: string,
  fetchImpl: typeof fetch = fetch,
): Promise<SampleAskResult> {
  const res = await fetchImpl("/api/sample/ask", {
    method: "POST",
    credentials: "same-origin",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) {
    throw await apiErrorFrom(res, "sampleAsk");
  }
  return (await res.json()) as SampleAskResult;
}
