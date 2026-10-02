/**
 * Browser-side checkpoint client: the end-of-section predict → recall → explain loop.
 *
 * Every call goes through the same-origin proxy (ADR-017) with the session cookie
 * and echoes the CSRF token. FastAPI owns the loop's guarantees, so this file only
 * carries inputs and outputs. Starting a checkpoint returns questions and never an
 * answer. An answer, feedback or passage comes back only from the call that
 * unlocks it. The server, not this client, decides whether an attempt was
 * assisted.
 *
 * The response types mirror `web/checkpoints.py`.
 */

import { clientTimezone } from "@/app/lib/study";

/** One-tap confidence before the answer is shown: 1 not sure … 3 sure. */
export type Confidence = 1 | 2 | 3;

/** Judgment of learning before any attempt: 1 little … 3 most, or skipped. */
export type Prediction = 1 | 2 | 3 | null;

export type CheckpointAttempt = {
  attempt_id: string;
  kind: "recall" | "explain";
  question: string;
};

export type Checkpoint = {
  checkpoint_id: string;
  section_title: string;
  anchor: string;
  attempts: CheckpointAttempt[];
};

export type RecallReveal = {
  answer: string;
  source_excerpt: string;
  anchor: string;
  section_path: string[];
};

export type CitationQuote = {
  anchor: string;
  section_path: string[];
  quote: string;
};

export type ExplainFeedback = {
  feedback: string;
  citations: CitationQuote[];
};

export type RevealedPassage = {
  passage: string;
  anchor: string;
  section_path: string[];
};

export type GradedAttempt = {
  quiz_item_id: string;
  due: string;
  state: number;
};

/** A non-OK checkpoint response: its status and the backend `detail` (or a fallback). */
export class CheckpointError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "CheckpointError";
    this.status = status;
  }
}

async function post<T>(
  path: string,
  body: unknown,
  csrfToken: string,
  fallback: string,
  fetchImpl: typeof fetch,
  extraHeaders: Record<string, string> = {},
): Promise<T> {
  const res = await fetchImpl(path, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "content-type": "application/json",
      "X-CSRF-Token": csrfToken,
      ...extraHeaders,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let message = fallback;
    try {
      const detail = ((await res.json()) as { detail?: unknown }).detail;
      if (typeof detail === "string") {
        message = detail;
      }
    } catch {
      // Keep the readable fallback.
    }
    throw new CheckpointError(res.status, message);
  }
  return (await res.json()) as T;
}

/** Begin a checkpoint on one section (201): questions only, no answers. */
export function startCheckpoint(
  sourceId: string,
  anchor: string,
  prediction: Prediction,
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<Checkpoint> {
  return post<Checkpoint>(
    `/api/sources/${sourceId}/checkpoints`,
    { anchor, prediction },
    csrfToken,
    "Could not start the checkpoint.",
    fetchImpl,
  );
}

/** Store an attempt and its confidence, then get what it unlocks. */
export function respondToAttempt<T extends RecallReveal | ExplainFeedback>(
  attemptId: string,
  response: string,
  confidence: Confidence,
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<T> {
  return post<T>(
    `/api/checkpoint-attempts/${attemptId}/response`,
    { response, confidence },
    csrfToken,
    "Could not save your answer.",
    fetchImpl,
  );
}

/** "Just explain": show the passage before explaining. The attempt becomes assisted. */
export function revealPassage(
  attemptId: string,
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<RevealedPassage> {
  return post<RevealedPassage>(
    `/api/checkpoint-attempts/${attemptId}/reveal`,
    undefined,
    csrfToken,
    "Could not show the passage.",
    fetchImpl,
  );
}

/** Self-assess an attempt once; FSRS schedules the card it reviewed. */
export function gradeAttempt(
  attemptId: string,
  rating: number,
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<GradedAttempt> {
  const tz = clientTimezone();
  return post<GradedAttempt>(
    `/api/checkpoint-attempts/${attemptId}/grade`,
    { rating },
    csrfToken,
    "Could not save your rating.",
    fetchImpl,
    tz ? { "X-Client-Timezone": tz } : {},
  );
}
