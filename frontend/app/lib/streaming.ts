/**
 * Streaming chat transport for Learny's Ask and Teach surfaces (FE-06, FE-12).
 *
 * The one protocol-aware client module: it configures the Vercel AI SDK
 * `useChat` transport to POST through the same-origin Next.js proxy (`/api/...`,
 * ADR-017) to the Cycle-C UI Message Stream v1 SSE endpoints, mirroring how the
 * backend isolates the wire format in `ui_message_stream.py`. It reshapes each
 * request to Learny's contracts (`{question}` / `{message}` — only the latest
 * user message, never the AI-SDK message history, since the server owns history
 * or is stateless) and echoes the session-bound CSRF token in `X-CSRF-Token`
 * (AD-007). The HttpOnly session cookie rides along automatically
 * (`credentials: "same-origin"`), so this code never reads or holds the token.
 *
 * FastAPI stays authoritative for auth, ownership, readiness, and generation;
 * these helpers just carry the question/message in and surface the streamed
 * tokens, citations, answer status, and readable errors out.
 */

import { DefaultChatTransport, type UIMessage } from "ai";

import { type Citation } from "./questions";
import { type TeachingTurnView } from "./teaching";

/** The answer outcome both surfaces report, mirroring the backend status. */
export type AnswerStatus = "answered" | "not_found_in_source";

/**
 * The typed data parts Learny's stream carries alongside the streamed text,
 * matching `ui_message_stream.py`: `data-citations` (the grounded citation
 * snapshots) and `data-answer-status` (`answered` | `not_found_in_source`).
 */
export type LearnyDataParts = {
  citations: Citation[];
  "answer-status": { status: AnswerStatus };
};

/** A `useChat` message specialized to Learny's citation + answer-status parts. */
export type LearnyUIMessage = UIMessage<unknown, LearnyDataParts>;

/** A pre-stream HTTP failure (network unreachable, or the status code). */
export type StreamErrorKind = number | "network";

/**
 * The readable message each chat surface renders for a stream that fails before
 * the first byte (the eager backend guards return these as plain JSON errors),
 * or for an unreachable server. The backend's mid-stream `error` part carries its
 * own readable text ("Answer generation failed…"), which the surfaces render
 * directly; this maps the pre-stream statuses to the same generation wording for
 * 502 so both failure paths read alike.
 */
export function errorMessageFor(kind: StreamErrorKind): string {
  switch (kind) {
    case 401:
      return "Your session has expired. Please sign in again.";
    case 403:
      return "Your session could not be verified. Refresh the page and try again.";
    case 404:
      return "This book could not be found.";
    case 409:
      return "This book is still processing. Try again once it is ready.";
    case 422:
      return "That request could not be processed. Please revise it and try again.";
    case 429:
      return "Too many requests. Please wait a moment and try again.";
    case 502:
      return "Answer generation failed. Please try again.";
    case "network":
      return "Something went wrong reaching the server. Please try again.";
    default:
      return "Something went wrong. Please try again.";
  }
}

/**
 * A pre-stream request failure carrying the originating status (or `"network"`).
 * Its message is the readable string; surfaces show `error.message` and can key
 * a 401 off `status` to redirect to login (FE-05).
 */
export class StreamRequestError extends Error {
  readonly status: StreamErrorKind;

  constructor(status: StreamErrorKind) {
    super(errorMessageFor(status));
    this.name = "StreamRequestError";
    this.status = status;
  }
}

/**
 * `fetch` wrapper the transports use so a non-OK stream start (the eager 401/403/
 * 404/409/422/429/502 guards, which respond before the first SSE byte) surfaces
 * as a `StreamRequestError` with a readable message instead of the AI SDK's raw
 * response-body text. Reads `globalThis.fetch` at call time so tests that stub it
 * still apply. A user-initiated abort (the stop button) propagates untouched so
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
    throw new StreamRequestError(response.status);
  }
  return response;
};

/**
 * Transport for a source's streaming Q&A: POSTs `{question: <latest user text>}`
 * to `/api/sources/{id}/questions/stream` with the CSRF header (FE-06).
 */
export function createQuestionTransport(
  sourceId: string,
  csrfToken: string,
): DefaultChatTransport<LearnyUIMessage> {
  const api = `/api/sources/${sourceId}/questions/stream`;
  return new DefaultChatTransport<LearnyUIMessage>({
    api,
    credentials: "same-origin",
    fetch: streamingFetch,
    prepareSendMessagesRequest: ({ messages }) => ({
      api,
      body: { question: latestUserText(messages) },
      headers: { "X-CSRF-Token": csrfToken },
    }),
  });
}

/**
 * Transport for a teaching session's streaming turns: POSTs
 * `{message: <latest user text>}` to `/api/teaching-sessions/{id}/turns/stream`
 * with the CSRF header (FE-12).
 */
export function createTurnTransport(
  sessionId: string,
  csrfToken: string,
): DefaultChatTransport<LearnyUIMessage> {
  const api = `/api/teaching-sessions/${sessionId}/turns/stream`;
  return new DefaultChatTransport<LearnyUIMessage>({
    api,
    credentials: "same-origin",
    fetch: streamingFetch,
    prepareSendMessagesRequest: ({ messages }) => ({
      api,
      body: { message: latestUserText(messages) },
      headers: { "X-CSRF-Token": csrfToken },
    }),
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
 * Seed persisted teaching turns into `useChat` messages so a resumed session
 * renders identically to live-streamed turns (FE-12). Each turn becomes a user
 * message (its prompt) followed by an assistant message carrying the response
 * text, the citation snapshots, and the answer status — the same part shape the
 * live stream assembles.
 */
export function turnsToUIMessages(
  turns: TeachingTurnView[],
): LearnyUIMessage[] {
  const messages: LearnyUIMessage[] = [];
  for (const turn of turns) {
    messages.push({
      id: `turn-${turn.turn_index}-user`,
      role: "user",
      parts: [{ type: "text", text: turn.message }],
    });
    messages.push({
      id: `turn-${turn.turn_index}-assistant`,
      role: "assistant",
      parts: [
        { type: "text", text: turn.text },
        { type: "data-citations", data: turn.citations },
        { type: "data-answer-status", data: { status: turn.answer_status } },
      ],
    });
  }
  return messages;
}
