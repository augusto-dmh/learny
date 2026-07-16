"use client";

/**
 * Ask screen (FE-06..FE-10) — replaces the unstyled AskPanel.
 *
 * Streams a grounded, cited answer for one ready source. It resolves auth via
 * `/api/auth/me` (through the proxy) to obtain the session-bound CSRF token, then
 * drives the Vercel AI SDK `useChat` over the streaming Q&A transport
 * (`app/lib/streaming.ts`): the question POSTs to
 * `/api/sources/{id}/questions/stream`, text deltas render as they arrive, and
 * the terminal citation + answer-status parts render either the citation chips or
 * the explicit not-found state. Errors (mid-stream `error` part, a non-OK start
 * incl. 429, or stop) settle to a readable banner with partial text retained and
 * the input re-enabled.
 *
 * `onRequireAuth` is a UX-only redirect for unauthenticated users, NOT the
 * security boundary — FastAPI enforces auth, ownership, and readiness on every
 * stream call regardless of client-side routing (FR-AUTH-007, ADR-017).
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { useChat } from "@ai-sdk/react";

import { fetchAuthState } from "@/app/lib/auth";
import { type Citation } from "@/app/lib/questions";
import {
  createQuestionTransport,
  StreamRequestError,
  type AnswerStatus,
  type LearnyUIMessage,
} from "@/app/lib/streaming";
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

export function AskScreen({
  sourceId,
  onRequireAuth,
}: {
  sourceId: string;
  onRequireAuth?: () => void;
}) {
  const [csrf, setCsrf] = useState<string | null>(null);
  const [authed, setAuthed] = useState<boolean | null>(null);

  useEffect(() => {
    let active = true;
    void fetchAuthState().then((next) => {
      if (!active) {
        return;
      }
      if (next.authenticated) {
        setCsrf(next.user.csrf_token);
        setAuthed(true);
      } else {
        setAuthed(false);
        onRequireAuth?.();
      }
    });
    return () => {
      active = false;
    };
  }, [onRequireAuth]);

  if (authed === null) {
    return <p className="text-muted-foreground">Loading…</p>;
  }
  if (!authed || csrf === null) {
    return <p className="text-muted-foreground">You are signed out.</p>;
  }
  return (
    <AskChat sourceId={sourceId} csrf={csrf} onRequireAuth={onRequireAuth} />
  );
}

/** Read a message's collected text, citations, and answer status from its parts. */
function assistantView(message: LearnyUIMessage): {
  text: string;
  citations: Citation[] | null;
  status: AnswerStatus | null;
} {
  let text = "";
  let citations: Citation[] | null = null;
  let status: AnswerStatus | null = null;
  for (const part of message.parts) {
    if (part.type === "text") {
      text += part.text;
    } else if (part.type === "data-citations") {
      citations = part.data;
    } else if (part.type === "data-answer-status") {
      status = part.data.status;
    }
  }
  return { text, citations, status };
}

function AskChat({
  sourceId,
  csrf,
  onRequireAuth,
}: {
  sourceId: string;
  csrf: string;
  onRequireAuth?: () => void;
}) {
  const [banner, setBanner] = useState<string | null>(null);
  const transport = useMemo(
    () => createQuestionTransport(sourceId, csrf),
    [sourceId, csrf],
  );
  const { messages, sendMessage, status, stop } = useChat<LearnyUIMessage>({
    transport,
    onError: (err) => {
      // A 401 during the stream redirects to login (FE-05); every other failure
      // renders as a readable banner while any partial text is retained (FE-09).
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
    <div className="flex h-full flex-col gap-4">
      <Conversation>
        <ConversationContent>
          {messages.map((message) => {
            if (message.role === "user") {
              return (
                <Message from="user" key={message.id}>
                  <MessageContent>
                    {message.parts.map((part, index) =>
                      part.type === "text" ? (
                        <span key={index}>{part.text}</span>
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
                      That question was not found in this source.
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
            placeholder="Ask a question about this book…"
            disabled={isStreaming}
          />
        </PromptInputBody>
        <PromptInputFooter>
          <PromptInputSubmit status={status} onStop={() => void stop()} />
        </PromptInputFooter>
      </PromptInput>
    </div>
  );
}
