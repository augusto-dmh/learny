/**
 * Request failures are typed data, not English sentences.
 *
 * Every browser request client throws an `ApiError` carrying the operation key,
 * the HTTP status and the backend `detail` for a non-OK response; its `message`
 * is the operation key, so no client ever hands a sentence to the screen. The
 * typed errors that predate `ApiError` keep the `kind`/`status` their callers
 * branch on.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  AiProfileRequestError,
  getAiProfileChoice,
  putAiProfileChoice,
} from "../app/lib/ai-profiles";
import { login } from "../app/lib/auth";
import { acceptCard, CardError, suggestCards } from "../app/lib/cards";
import {
  ConversationRequestError,
  listConversations,
  startConversation,
} from "../app/lib/conversations";
import { ApiError, type ApiErrorStatus, type ApiOperation } from "../app/lib/errors";
import { getIngestion } from "../app/lib/ingestion";
import { captureHighlight, listNotes, NoteError, updateNote } from "../app/lib/notes";
import { getDueReviews } from "../app/lib/quiz";
import { getChapter } from "../app/lib/reading";
import { getSection } from "../app/lib/sections";
import { listSources } from "../app/lib/sources";
import { createConversationTransport, StreamRequestError } from "../app/lib/streaming";
import { getStudyDays } from "../app/lib/study";
import { acceptTutorCard, TutorCardError } from "../app/lib/tutor-card";
import { deleteLocale, putLocale } from "@/app/lib/locale";

const DETAIL = "The backend explains this in English.";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function failingFetch(status: number, detail: unknown = DETAIL): typeof fetch {
  return vi.fn(async () => jsonResponse(status, { detail })) as unknown as typeof fetch;
}

/** The streaming transport's fetch wrapper, which reads `globalThis.fetch`. */
function streamFetch(): typeof fetch {
  const transport = createConversationTransport({
    mode: "answer",
    csrfToken: "csrf",
    resolveConversationId: async () => "c1",
  });
  return (transport as unknown as { fetch: typeof fetch }).fetch;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

type Row = {
  client: string;
  operation: ApiOperation;
  call: (fetchImpl: typeof fetch) => Promise<unknown>;
};

const CLIENTS: Row[] = [
  { client: "auth", operation: "authLogin", call: (f) => login("a@b.c", "pw", f) },
  { client: "sources", operation: "sourcesList", call: (f) => listSources(f) },
  { client: "ingestion", operation: "ingestionStatus", call: (f) => getIngestion("s1", f) },
  { client: "sections", operation: "sectionLoad", call: (f) => getSection("s1", "a1", f) },
  { client: "ai-profiles", operation: "aiProfileGet", call: (f) => getAiProfileChoice(f) },
  { client: "quiz", operation: "quizDue", call: (f) => getDueReviews({}, f) },
  { client: "study", operation: "studyActivity", call: (f) => getStudyDays(undefined, f) },
  { client: "reading", operation: "readingChapter", call: (f) => getChapter("s1", null, f) },
  { client: "notes", operation: "notesList", call: (f) => listNotes({}, f) },
  {
    client: "conversations",
    operation: "conversationsList",
    call: (f) => listConversations("s1", {}, f),
  },
  {
    client: "streaming",
    operation: "chatTurn",
    call: (f) => {
      vi.stubGlobal("fetch", f);
      return streamFetch()("/api/conversations/c1/turns/stream", { method: "POST" });
    },
  },
  { client: "cards", operation: "cardsSuggestPassage", call: (f) => suggestCards("s1", "h1", "csrf", f) },
  { client: "tutor-card", operation: "tutorCardSave", call: (f) => acceptTutorCard("c1", "csrf", f) },
  { client: "locale (save)", operation: "localeSave", call: (f) => putLocale("pt-BR", "csrf", f) },
  { client: "locale (reset)", operation: "localeReset", call: (f) => deleteLocale("csrf", f) },
];

describe("request clients", () => {
  it.each(CLIENTS)(
    "every client throws an ApiError with operation status and detail ($client)",
    async ({ operation, call }) => {
      // A status no client special-cases (the reading/section 404 is a result).
      const err = await call(failingFetch(400)).catch((e: unknown) => e);

      expect(err).toBeInstanceOf(ApiError);
      const apiError = err as ApiError;
      expect(apiError.operation).toBe(operation);
      expect(apiError.status).toBe(400);
      expect(apiError.detail).toBe(DETAIL);
      // The message is the operation key, never the backend's sentence.
      expect(apiError.message).toBe(operation);
    },
  );

  it("keeps a list-shaped validation detail as serialized data", async () => {
    const detail = [{ loc: ["body", "title"], msg: "too long" }];
    const err = await listSources(failingFetch(422, detail)).catch((e: unknown) => e);
    expect((err as ApiError).detail).toBe(JSON.stringify(detail));
    expect((err as ApiError).message).toBe("sourcesList");
  });

  it("carries a null detail when the error body is not JSON", async () => {
    const fetchImpl = vi.fn(
      async () => new Response("<html>gateway</html>", { status: 502 }),
    ) as unknown as typeof fetch;
    const err = await listSources(fetchImpl).catch((e: unknown) => e);
    expect(err).toMatchObject({ operation: "sourcesList", status: 502, detail: null });
  });

  it("marks an unreachable stream server with the network status", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    const err = await streamFetch()("/api/conversations/c1/turns/stream", {
      method: "POST",
    }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(StreamRequestError);
    expect(err).toMatchObject({ operation: "chatTurn", status: "network" satisfies ApiErrorStatus });
  });

  it("names the start operation when creating a conversation fails", async () => {
    const err = await startConversation(
      { sourceId: "s1", includeNotes: false },
      "csrf",
      failingFetch(409),
    ).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(StreamRequestError);
    expect(err).toMatchObject({ operation: "conversationsStart", status: 409, detail: DETAIL });
  });
});

describe("typed errors from before ApiError", () => {
  it("legacy typed errors keep their kind and status", async () => {
    // StreamRequestError: a 401 is still recognisable for the login redirect.
    vi.stubGlobal("fetch", failingFetch(401));
    const stream = await streamFetch()("/api/conversations/c1/turns/stream", {
      method: "POST",
    }).catch((e: unknown) => e);
    expect(stream).toBeInstanceOf(StreamRequestError);
    expect(stream).toBeInstanceOf(ApiError);
    expect((stream as StreamRequestError).status).toBe(401);

    // NoteError: the documented kinds still map from their statuses.
    const stale = await captureHighlight(
      "s1",
      { anchor: "a1", quote_exact: "q", title: "t" },
      "csrf",
      failingFetch(409),
    ).catch((e: unknown) => e);
    expect(stale).toBeInstanceOf(NoteError);
    expect(stale).toMatchObject({ kind: "stale_capture", status: 409, operation: "notesCapture" });
    const tooLong = await updateNote("n1", { title: "t" }, "csrf", failingFetch(422)).catch(
      (e: unknown) => e,
    );
    expect(tooLong).toMatchObject({ kind: "body_too_long", status: 422, operation: "notesSave" });
    const unknown = await listNotes({}, failingFetch(404)).catch((e: unknown) => e);
    expect(unknown).toMatchObject({ kind: "unknown", status: 404 });

    // AiProfileRequestError: callers still key off the status.
    const profile = await putAiProfileChoice("house-x", "csrf", failingFetch(422)).catch(
      (e: unknown) => e,
    );
    expect(profile).toBeInstanceOf(AiProfileRequestError);
    expect((profile as AiProfileRequestError).status).toBe(422);

    // CardError, ConversationRequestError, TutorCardError keep theirs too.
    const card = await acceptCard(
      "s1",
      { anchor_id: "h1", item_type: "qa", question: "q", answer: "a" } as never,
      "csrf",
      failingFetch(422),
    ).catch((e: unknown) => e);
    expect(card).toBeInstanceOf(CardError);
    expect(card).toMatchObject({ kind: "invalid", status: 422 });
    const staleCard = await suggestCards("s1", "h1", "csrf", failingFetch(409)).catch(
      (e: unknown) => e,
    );
    expect(staleCard).toMatchObject({ kind: "stale_capture", status: 409 });
    const conversation = await listConversations("s1", {}, failingFetch(404)).catch(
      (e: unknown) => e,
    );
    expect(conversation).toBeInstanceOf(ConversationRequestError);
    expect((conversation as ConversationRequestError).status).toBe(404);
    const tutorCard = await acceptTutorCard("c1", "csrf", failingFetch(409)).catch(
      (e: unknown) => e,
    );
    expect(tutorCard).toBeInstanceOf(TutorCardError);
    expect((tutorCard as TutorCardError).status).toBe(409);
  });
});
