"use client";

/**
 * Teach screen (FE-11..FE-13) — replaces the unstyled TeachPanel.
 *
 * Drives one source's teaching flow. It resolves auth via `/api/auth/me`
 * (through the proxy) for the CSRF token, then shows a target picker (the section
 * tree, from the structure client + `lib/tree`) and a resume list of previous
 * sessions with their turn counts. Picking either enters the session view, which
 * seeds the Vercel AI SDK `useChat` from the session's persisted turns
 * (`turnsToUIMessages`) so resumed history renders identically to live turns, and
 * streams new turns over the turn transport (`app/lib/streaming.ts`). The
 * conversation follows the same readable state contract as Ask: not-found, a
 * throttle/error banner with partial text retained, and a stop control.
 *
 * `onRequireAuth` is a UX-only redirect for unauthenticated users, NOT the
 * security boundary — FastAPI enforces auth, ownership, readiness, and target
 * scoping on every call regardless of client-side routing (FR-AUTH-007, ADR-017).
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { useChat } from "@ai-sdk/react";

import { fetchAuthState } from "@/app/lib/auth";
import { fetchSourceStructure, type SourceStructure } from "@/app/lib/sources";
import {
  assistantView,
  createTurnTransport,
  StreamRequestError,
  turnsToUIMessages,
  type LearnyUIMessage,
} from "@/app/lib/streaming";
import {
  getTeachingSession,
  listTeachingSessions,
  startTeachingSession,
  type TeachingSessionSummary,
  type TeachingSessionView,
} from "@/app/lib/teaching";
import { flattenSections } from "@/app/lib/tree";
import { Button } from "@/components/ui/button";
import {
  Conversation,
  ConversationContent,
} from "@/components/ai-elements/conversation";
import {
  Message,
  MessageContent,
  MessageResponse,
} from "@/components/ai-elements/message";
import {
  PromptInput,
  PromptInputBody,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputTextarea,
  type PromptInputMessage,
} from "@/components/ai-elements/prompt-input";

import { CitationList } from "./citations";

/** A session the user has entered, plus the messages seeding its conversation. */
type ActiveSession = {
  session: TeachingSessionView;
  initialMessages: LearnyUIMessage[];
};

export function TeachScreen({
  sourceId,
  onRequireAuth,
}: {
  sourceId: string;
  onRequireAuth?: () => void;
}) {
  const [csrf, setCsrf] = useState<string | null>(null);
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [structure, setStructure] = useState<SourceStructure | null>(null);
  const [sessions, setSessions] = useState<TeachingSessionSummary[] | null>(
    null,
  );
  const [selectedAnchor, setSelectedAnchor] = useState("");
  const [active, setActive] = useState<ActiveSession | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [resumingId, setResumingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    const next = await fetchAuthState();
    if (!next.authenticated) {
      setAuthed(false);
      onRequireAuth?.();
      return;
    }
    setCsrf(next.user.csrf_token);
    setAuthed(true);
    try {
      const [struct, list] = await Promise.all([
        fetchSourceStructure(sourceId),
        listTeachingSessions(sourceId),
      ]);
      setStructure(struct);
      setSessions(list);
      const options = flattenSections(struct.sections);
      if (options.length > 0) {
        setSelectedAnchor(options[0].anchor);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load this book.");
    }
  }, [sourceId, onRequireAuth]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleStart(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!csrf || !selectedAnchor) {
      return;
    }
    setStarting(true);
    try {
      const started = await startTeachingSession(
        sourceId,
        selectedAnchor,
        csrf,
      );
      setActive({ session: started, initialMessages: [] });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not start the session.",
      );
    } finally {
      setStarting(false);
    }
  }

  async function handleResume(summary: TeachingSessionSummary) {
    setError(null);
    setResumingId(summary.id);
    try {
      const detail = await getTeachingSession(summary.id);
      setActive({
        session: detail,
        initialMessages: turnsToUIMessages(detail.turns),
      });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not load that session.",
      );
    } finally {
      setResumingId(null);
    }
  }

  if (authed === null) {
    return <p className="text-muted-foreground">Loading…</p>;
  }
  if (!authed || csrf === null) {
    return <p className="text-muted-foreground">You are signed out.</p>;
  }

  if (active !== null) {
    return (
      <TeachChat
        key={active.session.id}
        sourceId={sourceId}
        sessionId={active.session.id}
        csrf={csrf}
        target={active.session.target.section_path.join(" › ")}
        initialMessages={active.initialMessages}
        onRequireAuth={onRequireAuth}
      />
    );
  }

  const options = structure ? flattenSections(structure.sections) : [];

  return (
    <section aria-label="teach" className="space-y-6">
      <form onSubmit={handleStart} aria-label="start session" className="space-y-3">
        <div className="space-y-1.5">
          <label htmlFor="teach-target" className="text-sm font-medium">
            Target
          </label>
          <select
            id="teach-target"
            aria-label="Target"
            value={selectedAnchor}
            onChange={(e) => setSelectedAnchor(e.target.value)}
            className="w-full rounded-md border bg-background px-3 py-2 text-sm"
          >
            {options.map((option) => (
              <option key={`${option.anchor}-${option.label}`} value={option.anchor}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}
        <Button type="submit" disabled={starting || selectedAnchor === ""}>
          {starting ? "Starting…" : "Start session"}
        </Button>
      </form>

      <section aria-label="previous sessions" className="space-y-2">
        <h2 className="text-sm font-medium">Previous sessions</h2>
        {sessions === null ? (
          <p className="text-muted-foreground">Loading…</p>
        ) : sessions.length === 0 ? (
          <p className="text-muted-foreground">No sessions yet.</p>
        ) : (
          <ul className="space-y-2">
            {sessions.map((summary) => (
              <li
                key={summary.id}
                className="flex items-center justify-between gap-2 rounded-md border px-3 py-2 text-sm"
              >
                <span>
                  {summary.target.section_path.join(" › ")}{" "}
                  <span className="text-muted-foreground">
                    ({summary.turn_count} turns)
                  </span>
                </span>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => void handleResume(summary)}
                  disabled={resumingId === summary.id}
                >
                  {resumingId === summary.id ? "Resuming…" : "Resume"}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </section>
  );
}

function TeachChat({
  sourceId,
  sessionId,
  csrf,
  target,
  initialMessages,
  onRequireAuth,
}: {
  sourceId: string;
  sessionId: string;
  csrf: string;
  target: string;
  initialMessages: LearnyUIMessage[];
  onRequireAuth?: () => void;
}) {
  const [banner, setBanner] = useState<string | null>(null);
  const transport = useMemo(
    () => createTurnTransport(sessionId, csrf),
    [sessionId, csrf],
  );
  const { messages, sendMessage, status, stop } = useChat<LearnyUIMessage>({
    transport,
    messages: initialMessages,
    onError: (err) => {
      if (err instanceof StreamRequestError && err.status === 401) {
        onRequireAuth?.();
        return;
      }
      setBanner(err.message);
    },
  });

  const isStreaming = status === "submitted" || status === "streaming";

  const handleSubmit = useCallback(
    (message: PromptInputMessage) => {
      const text = message.text.trim();
      if (!text || isStreaming) {
        return;
      }
      setBanner(null);
      void sendMessage({ text });
    },
    [isStreaming, sendMessage],
  );

  return (
    <section aria-label="teach conversation" className="flex h-full flex-col gap-4">
      <h2 className="text-lg font-semibold">{target}</h2>
      <Conversation>
        <ConversationContent>
          {messages.map((message) => {
            if (message.role === "user") {
              return (
                <Message from="user" key={message.id}>
                  <MessageContent>
                    {message.parts.map((part, index) =>
                      part.type === "text" ? (
                        <span data-testid="user-message" key={index}>
                          {part.text}
                        </span>
                      ) : null,
                    )}
                  </MessageContent>
                </Message>
              );
            }
            const { text, citations, status: answerStatus } =
              assistantView(message);
            const notFound = answerStatus === "not_found_in_source";
            return (
              <Message from="assistant" key={message.id}>
                <MessageContent>
                  {text ? <MessageResponse>{text}</MessageResponse> : null}
                  {notFound ? (
                    <p data-testid="not-found" className="text-muted-foreground">
                      That was not found in this target.
                    </p>
                  ) : citations ? (
                    <CitationList sourceId={sourceId} citations={citations} />
                  ) : null}
                </MessageContent>
              </Message>
            );
          })}
        </ConversationContent>
      </Conversation>

      {banner ? (
        <p role="alert" className="text-sm text-destructive">
          {banner}
        </p>
      ) : null}

      <PromptInput onSubmit={handleSubmit}>
        <PromptInputBody>
          <PromptInputTextarea
            placeholder="Send a message…"
            disabled={isStreaming}
          />
        </PromptInputBody>
        <PromptInputFooter>
          <PromptInputSubmit status={status} onStop={() => void stop()} />
        </PromptInputFooter>
      </PromptInput>
    </section>
  );
}
