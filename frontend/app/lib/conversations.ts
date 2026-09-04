/**
 * Browser-side conversations client — the unified grounded-conversation surface.
 *
 * One resource covers what Ask and Teach used to split between them: a
 * conversation is a scope (the section anchors retrieval may see, empty meaning
 * the whole book) plus per-turn modes. These helpers drive it *through the
 * same-origin Next.js proxy* (`/api/...`, ADR-017) — never cross-origin. The
 * HttpOnly session cookie rides along automatically (`credentials:
 * "same-origin"`), so this code never reads or holds the session token; the
 * mutating calls echo the session-bound CSRF token in `X-CSRF-Token`.
 *
 * FastAPI remains authoritative for auth, ownership, readiness, scope
 * resolution, and generation; these helpers just carry inputs in and surface the
 * conversation/turn/error out. Streaming a turn is not here — that is the
 * transport in `streaming.ts`, which shares this module's mode vocabulary.
 *
 * Failure shapes differ by call on purpose. Starting a conversation is the first
 * half of sending a message, so it raises the same `StreamRequestError` the
 * stream raises: the panel then handles a 401 or a throttle identically whether
 * it happened on the create or on the stream. The management calls raise
 * `ConversationRequestError`, which keeps the backend's readable `detail` and its
 * status so a caller can tell "this conversation is gone" (404) from a transient
 * failure.
 */

import { type Citation } from "./citations";
import { StreamRequestError } from "./streaming";

/** How a single turn is answered. Conversations are not typed by mode. */
export type ConversationMode = "answer" | "teach";

/**
 * A turn's outcome. `not_found_in_scope` means retrieval came up empty inside a
 * conversation's declared scope — the answer may still live elsewhere in the
 * book — while `not_found_in_source` means the whole book came up empty.
 * `failed` is a generation or transport failure: the user's message is kept,
 * the answer is empty, and there are no citations.
 */
export type ConversationAnswerStatus =
  | "answered"
  | "not_found_in_scope"
  | "not_found_in_source"
  | "failed";

/** One conversation, mirroring the backend `ConversationView`. */
export type ConversationView = {
  id: string;
  source_id: string;
  title: string;
  scope_anchors: string[];
  include_notes: boolean;
  target_anchor?: string | null;
  target_title?: string | null;
  tutor_phase?: string | null;
  hint_level?: string | null;
  tutor_check_text?: string | null;
  created_at: string;
  updated_at: string;
};

/**
 * One grounded turn, mirroring the backend `ConversationTurnView`. `text` is
 * `""` and `citations` is empty for both not-found outcomes; `model` and
 * `evidence_count` diagnostics are present on every outcome.
 */
export type ConversationTurnView = {
  turn_index: number;
  message: string;
  mode: ConversationMode;
  answer_status: ConversationAnswerStatus;
  text: string;
  citations: Citation[];
  evidence_count: number;
  model: string;
  created_at: string;
};

/** A conversation with its ordered, cited history (`turn_index` ascending). */
export type ConversationDetailView = ConversationView & {
  turns: ConversationTurnView[];
};

/** A list row, mirroring the backend `ConversationSummaryView`. */
export type ConversationSummaryView = ConversationView & {
  source_title: string;
  turn_count: number;
  /**
   * The mode of the conversation's newest turn — where the thread resumes — or
   * `null` when it has no turn to speak for it. Mode belongs to a turn, so a
   * conversation has no single one; the newest is the exchange being continued.
   */
  last_turn_mode: ConversationMode | null;
};

/**
 * A failed management call, carrying the backend's readable `detail` and the
 * status that produced it. Callers key off `status` to tell an absent
 * conversation (404 — a pointer that outlived its thread) from anything else.
 */
export class ConversationRequestError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ConversationRequestError";
    this.status = status;
  }
}

/**
 * Start a conversation over an owned, ready source.
 *
 * `includeNotes` is required by the wire: the notes choice is explicit per
 * conversation, so an omitted flag is a 422 rather than a server guess. An empty
 * `scopeAnchors` is the one spelling of "the whole book"; a non-empty one scopes
 * retrieval to those sections for the conversation's whole life. A blank/absent
 * `title` asks the server to name it.
 */
export async function startConversation(
  input: {
    sourceId: string;
    scopeAnchors?: string[];
    includeNotes: boolean;
    title?: string;
  },
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<ConversationView> {
  const res = await fetchImpl("/api/conversations", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "content-type": "application/json",
      "X-CSRF-Token": csrfToken,
    },
    body: JSON.stringify({
      source_id: input.sourceId,
      scope_anchors: input.scopeAnchors ?? [],
      include_notes: input.includeNotes,
      ...(input.title ? { title: input.title } : {}),
    }),
  });
  if (!res.ok) {
    throw new StreamRequestError(res.status);
  }
  return (await res.json()) as ConversationView;
}

/**
 * List the caller's conversations for one book, newest activity first. The page
 * is bounded server-side; `limit`/`offset` walk the same total order, so paging
 * never drops or repeats a row.
 */
export async function listConversations(
  sourceId: string,
  options: { limit?: number; offset?: number } = {},
  fetchImpl: typeof fetch = fetch,
): Promise<ConversationSummaryView[]> {
  const params = new URLSearchParams({ source_id: sourceId });
  if (options.limit !== undefined) {
    params.set("limit", String(options.limit));
  }
  if (options.offset !== undefined) {
    params.set("offset", String(options.offset));
  }
  const res = await fetchImpl(`/api/conversations?${params.toString()}`, {
    method: "GET",
    credentials: "same-origin",
  });
  if (!res.ok) {
    throw await toConversationError(res, "Could not load your conversations.");
  }
  return (await res.json()) as ConversationSummaryView[];
}

/** Read one owned conversation with its ordered, cited turns. */
export async function getConversation(
  conversationId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<ConversationDetailView> {
  const res = await fetchImpl(`/api/conversations/${conversationId}`, {
    method: "GET",
    credentials: "same-origin",
  });
  if (!res.ok) {
    throw await toConversationError(res, "Could not load that conversation.");
  }
  return (await res.json()) as ConversationDetailView;
}

/** Retitle an owned conversation. A blank or oversize title is a 422. */
export async function renameConversation(
  conversationId: string,
  title: string,
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<ConversationView> {
  const res = await fetchImpl(`/api/conversations/${conversationId}`, {
    method: "PATCH",
    credentials: "same-origin",
    headers: {
      "content-type": "application/json",
      "X-CSRF-Token": csrfToken,
    },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) {
    throw await toConversationError(res, "Could not rename that conversation.");
  }
  return (await res.json()) as ConversationView;
}

/** Delete an owned conversation with its turns and citations (204, no body). */
export async function deleteConversation(
  conversationId: string,
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  const res = await fetchImpl(`/api/conversations/${conversationId}`, {
    method: "DELETE",
    credentials: "same-origin",
    headers: { "X-CSRF-Token": csrfToken },
  });
  if (!res.ok) {
    throw await toConversationError(res, "Could not delete that conversation.");
  }
}

/**
 * Build an error from a non-OK response, preferring the backend's `detail`.
 * FastAPI validation errors (422) carry `detail` as a list of error objects, not
 * a string — those fall back to the readable message instead of rendering a
 * stringified list, mirroring the other clients.
 */
async function toConversationError(
  res: Response,
  fallback: string,
): Promise<ConversationRequestError> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    return new ConversationRequestError(
      res.status,
      typeof body.detail === "string" ? body.detail : fallback,
    );
  } catch {
    return new ConversationRequestError(res.status, fallback);
  }
}
