"use client";

/**
 * Ask panel (RA-07..09, RA-17/18) — the Ask mode body of the reader side panel.
 *
 * This is the `AskChat` composition from the standalone ask screen, ported into
 * the panel: it drives the Vercel AI SDK `useChat` over the *unchanged* streaming
 * Q&A transport (`app/lib/streaming.ts`), so deltas, citations, the not-found
 * terminal state, and the readable error banner behave exactly as they did on the
 * page (parity). Auth is resolved once upstream in `ChapterReader`; the panel
 * receives the session-bound CSRF token as a prop rather than fetching
 * `/api/auth/me` itself.
 *
 * Panel-only additions: an empty-state list of suggested prompts (click ⇒ submit,
 * RA-08); a streaming caret at the tail of the in-flight answer (RA-09); and the
 * selection-verb contract (RA-17/18) — an `explain` pending request auto-submits a
 * fixed template around the quote, an `ask` pending request attaches the quote as
 * context that rides along with the reader's own typed question. The reader wires
 * `pendingRequest` in a later cycle; here it is consumed via props.
 *
 * `onRequireAuth` is a UX-only redirect for a mid-stream 401, NOT the security
 * boundary — FastAPI enforces auth, ownership, and readiness on every stream call
 * regardless of client-side routing (FR-AUTH-007, ADR-017).
 */

import { X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useChat } from "@ai-sdk/react";

import {
  assistantView,
  createQuestionTransport,
  StreamRequestError,
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
import { Button } from "@/components/ui/button";

import { CitationList } from "./citations";

/** A selection verb handed to the panel: one-tap explain, or ask-about context. */
export type PendingPanelRequest = {
  kind: "explain" | "ask";
  quote: string;
  anchor: string;
};

/** Fixed empty-state suggestions; clicking one submits it as a question (RA-08). */
const SUGGESTED_PROMPTS = [
  "Summarize the key ideas in this book.",
  "What are the main arguments the author makes?",
  "Explain a concept from this book I might find difficult.",
];

/** The fixed template a one-tap Explain submits around the selected passage. */
function explainPrompt(quote: string): string {
  return `Explain this passage from the book:\n\n"${quote}"`;
}

/** The submitted body when a typed question rides along with an attached quote. */
function askAboutPrompt(quote: string, question: string): string {
  return `Regarding this passage:\n\n"${quote}"\n\n${question}`;
}

export function AskPanel({
  sourceId,
  csrf,
  pendingRequest,
  onPendingConsumed,
  onRequireAuth,
}: {
  sourceId: string;
  csrf: string;
  pendingRequest?: PendingPanelRequest | null;
  onPendingConsumed?: () => void;
  onRequireAuth?: () => void;
}) {
  const [banner, setBanner] = useState<string | null>(null);
  // A quote the reader chose to "Ask about": it rides along, once, with the next
  // typed question (RA-18) and shows as a dismissable context chip until then.
  const [attachedQuote, setAttachedQuote] = useState<string | null>(null);
  const transport = useMemo(
    () => createQuestionTransport(sourceId, csrf),
    [sourceId, csrf],
  );
  const { messages, sendMessage, status, stop } = useChat<LearnyUIMessage>({
    transport,
    onError: (err) => {
      // A 401 during the stream redirects to login (parity); every other failure
      // renders as a readable banner while any partial text is retained.
      if (err instanceof StreamRequestError && err.status === 401) {
        onRequireAuth?.();
        return;
      }
      setBanner(err.message);
    },
  });

  const isStreaming = status === "submitted" || status === "streaming";

  const submit = useCallback(
    (text: string) => {
      if (!text || isStreaming) {
        return;
      }
      setBanner(null);
      void sendMessage({ text });
    },
    [isStreaming, sendMessage],
  );

  // Consume a selection verb exactly once (ref-guarded against effect re-runs):
  // `explain` auto-submits the fixed template; `ask` stows the quote as context
  // for the reader's next question. The reader clears the request afterward.
  const consumedRef = useRef<PendingPanelRequest | null>(null);
  useEffect(() => {
    if (!pendingRequest || consumedRef.current === pendingRequest) {
      return;
    }
    consumedRef.current = pendingRequest;
    if (pendingRequest.kind === "explain") {
      submit(explainPrompt(pendingRequest.quote));
    } else {
      setAttachedQuote(pendingRequest.quote);
    }
    onPendingConsumed?.();
  }, [pendingRequest, submit, onPendingConsumed]);

  const handleSubmit = useCallback(
    (message: PromptInputMessage) => {
      const text = message.text.trim();
      if (!text || isStreaming) {
        return;
      }
      submit(attachedQuote ? askAboutPrompt(attachedQuote, text) : text);
      setAttachedQuote(null);
    },
    [attachedQuote, isStreaming, submit],
  );

  return (
    <div className="flex h-full flex-col gap-4">
      <Conversation>
        <ConversationContent>
          {messages.length === 0 ? (
            <div aria-label="suggested prompts" className="space-y-2">
              {SUGGESTED_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => submit(prompt)}
                  className="block w-full rounded-md border px-3 py-2 text-left text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                >
                  {prompt}
                </button>
              ))}
            </div>
          ) : null}
          {messages.map((message, index) => {
            const isLast = index === messages.length - 1;
            if (message.role === "user") {
              return (
                <Message from="user" key={message.id}>
                  <MessageContent>
                    {message.parts.map((part, i) =>
                      part.type === "text" ? (
                        <span key={i}>{part.text}</span>
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
                  {isLast && isStreaming ? (
                    <span
                      data-testid="streaming-caret"
                      aria-hidden
                      className="ml-0.5 inline-block h-4 w-px animate-pulse bg-foreground align-text-bottom"
                    />
                  ) : null}
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

      {attachedQuote ? (
        <div
          data-testid="ask-context-chip"
          className="flex items-start justify-between gap-2 rounded-md border bg-muted/50 px-3 py-2 text-xs text-muted-foreground"
        >
          <span className="line-clamp-3 italic">“{attachedQuote}”</span>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="Remove attached passage"
            onClick={() => setAttachedQuote(null)}
          >
            <X />
          </Button>
        </div>
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
