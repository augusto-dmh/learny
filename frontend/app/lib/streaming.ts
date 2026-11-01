/**
 * Streaming chat transport for Learny's Ask and Teach surfaces (FE-06, FE-12).
 *
 * The one protocol-aware client module: it configures the Vercel AI SDK
 * `useChat` transport to POST through the same-origin Next.js proxy (`/api/...`,
 * ADR-017) to the UI Message Stream v1 SSE endpoint, mirroring how the backend
 * isolates the wire format in `ui_message_stream.py`. It reshapes each request to
 * Learny's contract (`{message, mode}` — only the latest user message, never the
 * AI-SDK message history, since the server owns the history) and echoes the
 * session-bound CSRF token in `X-CSRF-Token` (AD-007). The HttpOnly session cookie
 * rides along automatically (`credentials: "same-origin"`), so this code never
 * reads or holds the token.
 *
 * FastAPI stays authoritative for auth, ownership, readiness, and generation;
 * these helpers just carry the message in and surface the streamed tokens,
 * citations, answer status, tutor ladder, and typed errors out.
 */

import { DefaultChatTransport, type UIMessage } from "ai";

import type { ConversationAnswerStatus, ConversationMode } from "./conversations";
import { type Citation } from "./citations";
import { ApiError, readErrorBody, type ApiErrorStatus, type ApiOperation } from "./errors";

/**
 * The origin marker a capture-popover Explain turn carries (COST-04, AD-340).
 * The backend accepts exactly this literal and nothing else; a turn marked with
 * it is served by the selection-Explain chain instead of the ask primary, and
 * every turn that is not the popover's Explain verb sends no origin at all.
 */
export const EXPLAIN_SELECTION_ORIGIN = "explain_selection";

/** The origin literal an ask turn may carry; see {@link EXPLAIN_SELECTION_ORIGIN}. */
export type ExplainSelectionOrigin = typeof EXPLAIN_SELECTION_ORIGIN;

/**
 * The answer outcome a surface reports, mirroring the backend status. The
 * unified surface carries all four values on the wire, `not_found_in_scope`
 * included — a scoped conversation coming up empty is a different fact from the
 * whole book coming up empty, and the reader is told which. `failed` is a
 * generation miss: the question stays, the answer does not.
 */
export type AnswerStatus = ConversationAnswerStatus;

/**
 * The work a turn announces it is doing before it has anything to show. The
 * backend emits it once, before retrieval runs, so the wait between the request
 * and the first token is a named phase rather than dead air.
 */
export type AnswerPhase = "searching";

/**
 * What one answer's provider call consumed, as the adapter reported it —
 * the payload of the stream's terminal `data-answer-usage` part and of a
 * restored turn's usage fields. The backend sends the part only when the
 * adapter reported usage, so an absent part is "nothing was reported", not a
 * zero. `cost_usd_micros` is the estimated price at the serving profile's
 * catalog and is set only when the learner's own key paid; a house-served
 * turn costs the learner nothing and reads `null`.
 */
export type AnswerUsage = {
  input_tokens: number;
  output_tokens: number;
  cost_usd_micros: number | null;
  user_keyed: boolean;
};

/**
 * The typed data parts Learny's stream carries alongside the streamed text,
 * matching `ui_message_stream.py`: `data-citations` (the grounded citation
 * snapshots), `data-answer-status`, `data-answer-usage` (the terminal usage
 * report, only when the adapter reported one), `data-tutor-state` (the live
 * tutor ladder, only on Teach turns), and `data-phase`. The model's thinking rides
 * on the protocol's own `reasoning` parts, so it needs no entry here.
 *
 * `phase` is declared because the backend sends it, not because a component reads
 * it: a panel knows it is searching from having nothing yet — no text, no
 * reasoning, a turn in flight — which is true whether or not the frame arrives.
 * The frame stays the protocol's own statement of what the turn is doing, and this
 * entry is what a reader of it would attach to.
 */
export type LearnyDataParts = {
  citations: Citation[];
  "answer-status": { status: AnswerStatus };
  "answer-usage": AnswerUsage;
  phase: { phase: AnswerPhase };
  "tutor-state": {
    phase: string;
    hint_level: string | null;
    check_text: string | null;
  };
};

/** A `useChat` message specialized to Learny's citation + answer-status parts. */
export type LearnyUIMessage = UIMessage<unknown, LearnyDataParts>;

/** The concatenated text of a message's text parts. */
export function messageText(message: LearnyUIMessage): string {
  return message.parts
    .filter((part) => part.type === "text")
    .map((part) => part.text)
    .join("");
}

/**
 * Read a message's collected text, citations, answer status, usage, and
 * reasoning from its parts.
 *
 * `reasoning` is the model's streamed thinking, concatenated the same way the
 * answer text is; it is empty whenever the turn carried none — the provider chose
 * not to think, the local adapter is answering, or the turn is a restored one
 * (reasoning is never persisted, AD-220). Callers key the reasoning region off
 * that emptiness, so a turn without thinking shows no empty shell.
 *
 * `usage` is the turn's terminal usage report, or `null` when the adapter
 * reported nothing — the deterministic local adapter, or an older restored turn
 * predating the usage columns. Callers key the usage line off that null the same
 * way: nothing reported means nothing to show.
 *
 * The announced phase is deliberately not projected: the panels read "searching"
 * off a turn that is in flight with nothing to show yet, which is the same fact
 * without a second source for it to disagree with.
 */
export function assistantView(message: LearnyUIMessage): {
  text: string;
  citations: Citation[] | null;
  status: AnswerStatus | null;
  reasoning: string;
  usage: AnswerUsage | null;
} {
  let text = "";
  let citations: Citation[] | null = null;
  let status: AnswerStatus | null = null;
  let reasoning = "";
  let usage: AnswerUsage | null = null;
  for (const part of message.parts) {
    if (part.type === "text") {
      text += part.text;
    } else if (part.type === "reasoning") {
      reasoning += part.text;
    } else if (part.type === "data-citations") {
      citations = part.data;
    } else if (part.type === "data-answer-status") {
      status = part.data.status;
    } else if (part.type === "data-answer-usage") {
      usage = part.data;
    }
  }
  return { text, citations, status, reasoning, usage };
}

/** The tutor ladder a live Teach stream echoed on the terminal frame, or null. */
export type TutorStreamState = {
  phase: string;
  hintLevel: string | null;
  checkText: string | null;
};

export function tutorStateFrom(message: LearnyUIMessage): TutorStreamState | null {
  for (const part of message.parts) {
    if (part.type === "data-tutor-state") {
      return {
        phase: part.data.phase,
        hintLevel: part.data.hint_level,
        checkText: part.data.check_text,
      };
    }
  }
  return null;
}

/** Newest assistant message that carried a tutor-state part; in-flight frames skip. */
export function latestTutorState(
  messages: LearnyUIMessage[],
): TutorStreamState | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role !== "assistant") {
      continue;
    }
    const state = tutorStateFrom(messages[i]);
    if (state) {
      return state;
    }
  }
  return null;
}

/** A pre-stream HTTP failure (network unreachable, or the status code). */
export type StreamErrorKind = ApiErrorStatus;

/**
 * A pre-stream request failure: an `ApiError` for a chat operation, carrying the
 * originating status (or `"network"`) and, when the guard's body carries one,
 * the backend's machine refusal code. Surfaces read it through
 * `useErrorMessage`, which gives the chat guards (403/404/409/422) their own copy
 * and the shared status classes (401, 429, 5xx, network) theirs; a 401 is keyed
 * off `status` to redirect to login (FE-05).
 *
 * The backend's mid-stream `error` part is not one of these: the AI SDK raises a
 * plain `Error` holding the backend's text, which the surfaces never show — they
 * read it as the catalog's generation-failure copy instead.
 */
export class StreamRequestError extends ApiError {
  constructor(
    status: StreamErrorKind,
    operation: ApiOperation = "chatTurn",
    detail: string | null = null,
    code: string | null = null,
  ) {
    super(operation, status, detail, code);
    this.name = "StreamRequestError";
  }
}

/**
 * `fetch` wrapper the transports use so a non-OK stream start (the eager 401/403/
 * 404/409/422/429/502 guards, which respond before the first SSE byte) surfaces
 * as a `StreamRequestError` instead of the AI SDK's raw response-body text.
 * Reads `globalThis.fetch` at call time so tests that stub it still apply. A user-initiated abort (the stop button) propagates untouched so
 * the SDK settles to a stopped state rather than a network error.
 */
const streamingFetch: typeof fetch = async (input, init) => {
  let response: Response;
  try {
    response = await globalThis.fetch(input, init);
  } catch (err) {
    if (
      init?.signal?.aborted ||
      (err instanceof DOMException && err.name === "AbortError")
    ) {
      throw err;
    }
    throw new StreamRequestError("network");
  }
  if (!response.ok) {
    const { detail, code } = await readErrorBody(response);
    throw new StreamRequestError(response.status, "chatTurn", detail, code);
  }
  return response;
};

/**
 * Transport for a conversation's streaming turns on the unified surface: POSTs
 * `{message: <latest user text>, mode}` to
 * `/api/conversations/{id}/turns/stream` with the CSRF header.
 *
 * Starting a conversation and posting its first turn are two calls, so the id is
 * resolved **lazily**: `resolveConversationId` is awaited on every send and is
 * free to create the conversation the first time and return the same id
 * afterwards. That keeps the create-then-stream split inside the transport
 * instead of forcing every surface to special-case its first message.
 *
 * `mode` is passed explicitly — it is never inferred from the conversation's
 * scope, because a chapter-scoped conversation may still be answering rather
 * than teaching. The notes choice is *not* sent per turn: it belongs to the
 * conversation and is fixed when it is created.
 *
 * A send may hand the transport a per-call body carrying the selection-Explain
 * origin (COST-04); only that literal is forwarded, and only on the turn that
 * carries it — every other turn's body stays exactly `{message, mode}`.
 */
export function createConversationTransport({
  mode,
  csrfToken,
  resolveConversationId,
}: {
  mode: ConversationMode;
  csrfToken: string;
  resolveConversationId: () => Promise<string>;
}): DefaultChatTransport<LearnyUIMessage> {
  return new DefaultChatTransport<LearnyUIMessage>({
    api: "/api/conversations",
    credentials: "same-origin",
    fetch: streamingFetch,
    prepareSendMessagesRequest: async ({ messages, body }) => {
      const conversationId = await resolveConversationId();
      const origin = (body as { origin?: ExplainSelectionOrigin } | undefined)
        ?.origin;
      return {
        api: `/api/conversations/${conversationId}/turns/stream`,
        body:
          origin !== undefined
            ? { message: latestUserText(messages), mode, origin }
            : { message: latestUserText(messages), mode },
        headers: { "X-CSRF-Token": csrfToken },
      };
    },
  });
}

/** The concatenated text of the most recent user message (the just-sent one). */
function latestUserText(messages: LearnyUIMessage[]): string {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.role === "user") {
      return message.parts
        .filter((part) => part.type === "text")
        .map((part) => part.text)
        .join("");
    }
  }
  return "";
}

/**
 * The fields a stored turn must carry to be replayed into the chat. Declared
 * structurally rather than as one surface's response type so this helper stays
 * usable by whichever surface persists turns.
 */
export type PersistedTurn = {
  turn_index: number;
  message: string;
  answer_status: AnswerStatus;
  text: string;
  citations: Citation[];
  /**
   * What the turn's call consumed, as the adapter reported it (the backend
   * `ConversationTurnView`'s usage fields). `null` — or absent, on a turn
   * stored before the usage columns existed — reads exactly as "no usage
   * reported": the replay emits no usage part and the answer shows no usage
   * line.
   */
  usage_input_tokens?: number | null;
  usage_output_tokens?: number | null;
  cost_usd_micros?: number | null;
  user_keyed?: boolean;
};

/**
 * Seed persisted turns into `useChat` messages so a restored thread renders
 * identically to live-streamed turns (FE-12). Each turn becomes a user message
 * (its prompt) followed by an assistant message carrying the response text, the
 * citation snapshots, and the answer status — the same part shape the live
 * stream assembles. A turn whose adapter reported usage replays the same
 * `data-answer-usage` part the live stream's terminal frame carried, so the
 * usage line renders identically either way.
 *
 * No reasoning or phase parts are replayed: thinking is transient (AD-220) and a
 * stored turn has no phase left to announce. The answer text keeps whatever
 * inline citation markers it was stored with, so restored marks render exactly
 * as the streamed ones did.
 */
export function turnsToUIMessages(turns: PersistedTurn[]): LearnyUIMessage[] {
  const messages: LearnyUIMessage[] = [];
  for (const turn of turns) {
    messages.push({
      id: `turn-${turn.turn_index}-user`,
      role: "user",
      parts: [{ type: "text", text: turn.message }],
    });
    // The backend emits its usage part only when the adapter reported usage;
    // both token counts ride together, so replaying on the pair is the same
    // rule the backend applies.
    const usagePart =
      typeof turn.usage_input_tokens === "number" &&
      typeof turn.usage_output_tokens === "number"
        ? [
            {
              type: "data-answer-usage" as const,
              data: {
                input_tokens: turn.usage_input_tokens,
                output_tokens: turn.usage_output_tokens,
                cost_usd_micros: turn.cost_usd_micros ?? null,
                user_keyed: turn.user_keyed ?? false,
              },
            },
          ]
        : [];
    messages.push({
      id: `turn-${turn.turn_index}-assistant`,
      role: "assistant",
      parts: [
        { type: "text", text: turn.text },
        { type: "data-citations", data: turn.citations },
        { type: "data-answer-status", data: { status: turn.answer_status } },
        ...usagePart,
      ],
    });
  }
  return messages;
}
