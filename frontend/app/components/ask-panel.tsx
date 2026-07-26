"use client";

/**
 * Ask panel (RA-07..09, RA-17/18) — the Ask mode body of the reader side panel.
 *
 * The panel drives the unified conversation surface: a question goes into a
 * whole-book conversation (`mode=answer`, empty scope), created on the thread's
 * first message and continued by every message after it. Because the thread is
 * server-side, a reload no longer loses it — the panel re-reads the conversation
 * it was continuing and replays its stored turns, so what comes back is what the
 * server has, not what the browser remembered.
 *
 * Deltas, citations, the terminal not-found states, and the readable error
 * banner behave as they did before the re-point. Auth is resolved once upstream
 * in `ChapterReader`; the panel receives the session-bound CSRF token as a prop
 * rather than fetching `/api/auth/me` itself.
 *
 * Panel-only additions: an empty-state list of suggested prompts (click ⇒ submit,
 * RA-08); a streaming caret at the tail of the in-flight answer (RA-09); and the
 * selection-verb contract (RA-17/18) — an `explain` pending request auto-submits a
 * fixed template around the quote, an `ask` pending request attaches the quote as
 * context that rides along with the reader's own typed question.
 *
 * `onRequireAuth` is a UX-only redirect for a mid-stream 401, NOT the security
 * boundary — FastAPI enforces auth, ownership, and readiness on every call
 * regardless of client-side routing (FR-AUTH-007, ADR-017).
 */

import { X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  readActiveConversation,
  writeActiveConversation,
} from "@/app/lib/active-conversation";
import {
  ConversationRequestError,
  getConversation,
  startConversation,
} from "@/app/lib/conversations";
import { type PendingPanelRequest } from "@/app/lib/panel";
import {
  assistantView,
  messageText,
  turnsToUIMessages,
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
import { IncludeNotesToggle } from "./include-notes-toggle";
import { isNotFound, NotFoundNotice } from "./not-found-notice";
import { SaveToNoteAction } from "./save-to-note-action";
import { useConversationThread } from "./use-conversation-thread";
import { useIncludeNotes } from "./use-include-notes";

/** The surface name the active-conversation pointer is stored under. */
const SURFACE = "ask";

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

/** A thread the panel is showing: which conversation, and its restored turns. */
type AskThread = {
  key: string;
  conversationId: string | null;
  /** The notes choice this conversation was created with; `null` before there is one. */
  includeNotes: boolean | null;
  initialMessages: LearnyUIMessage[];
};

export function AskPanel({
  sourceId,
  csrf,
  revision = 0,
  pendingRequest,
  onPendingConsumed,
  onShowInBook,
  onRequireAuth,
  onConversationsChanged,
}: {
  sourceId: string;
  csrf: string;
  /** Bumped by the dock to make the panel re-read which conversation is active. */
  revision?: number;
  pendingRequest?: PendingPanelRequest | null;
  onPendingConsumed?: () => void;
  onShowInBook?: (anchor: string) => void;
  onRequireAuth?: () => void;
  onConversationsChanged?: () => void;
}) {
  const [thread, setThread] = useState<AskThread | null>(null);
  const [restoreError, setRestoreError] = useState<string | null>(null);

  // Restore the conversation this book's Ask surface was continuing. The pointer
  // is device-local; the turns are always the server's copy.
  useEffect(() => {
    let cancelled = false;
    const fresh = () => ({
      key: `new-${revision}`,
      conversationId: null,
      includeNotes: null,
      initialMessages: [],
    });
    const stored = readActiveConversation(sourceId, SURFACE);
    setRestoreError(null);
    if (!stored) {
      setThread(fresh());
      return;
    }
    setThread(null);
    void getConversation(stored)
      .then((detail) => {
        if (cancelled) return;
        setThread({
          key: detail.id,
          conversationId: detail.id,
          includeNotes: detail.include_notes,
          initialMessages: turnsToUIMessages(detail.turns),
        });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        // A pointer that outlived its conversation is not an error the reader
        // needs to see — it just means the thread is gone, so start a new one.
        if (err instanceof ConversationRequestError && err.status === 404) {
          writeActiveConversation(sourceId, SURFACE, null);
        } else {
          setRestoreError(
            err instanceof Error
              ? err.message
              : "Could not load that conversation.",
          );
        }
        setThread(fresh());
      });
    return () => {
      cancelled = true;
    };
  }, [sourceId, revision]);

  const handleStarted = useCallback(
    (conversationId: string) => {
      writeActiveConversation(sourceId, SURFACE, conversationId);
      onConversationsChanged?.();
    },
    [sourceId, onConversationsChanged],
  );

  // A first message that lands is when the thread becomes something to find
  // again, so that is when the dock is told to re-read its list.
  const handleKept = useCallback(() => {
    onConversationsChanged?.();
  }, [onConversationsChanged]);

  const handleDiscarded = useCallback(() => {
    writeActiveConversation(sourceId, SURFACE, null);
    onConversationsChanged?.();
  }, [sourceId, onConversationsChanged]);

  if (thread === null) {
    return <p className="text-muted-foreground">Loading…</p>;
  }

  return (
    <AskChat
      key={thread.key}
      sourceId={sourceId}
      csrf={csrf}
      conversationId={thread.conversationId}
      conversationIncludeNotes={thread.includeNotes}
      initialMessages={thread.initialMessages}
      restoreError={restoreError}
      pendingRequest={pendingRequest}
      onPendingConsumed={onPendingConsumed}
      onShowInBook={onShowInBook}
      onRequireAuth={onRequireAuth}
      onConversationStarted={handleStarted}
      onConversationKept={handleKept}
      onConversationDiscarded={handleDiscarded}
    />
  );
}

function AskChat({
  sourceId,
  csrf,
  conversationId,
  conversationIncludeNotes,
  initialMessages,
  restoreError,
  pendingRequest,
  onPendingConsumed,
  onShowInBook,
  onRequireAuth,
  onConversationStarted,
  onConversationKept,
  onConversationDiscarded,
}: {
  sourceId: string;
  csrf: string;
  conversationId: string | null;
  /** The notes choice the conversation carries, or `null` before there is one. */
  conversationIncludeNotes: boolean | null;
  initialMessages: LearnyUIMessage[];
  restoreError: string | null;
  pendingRequest?: PendingPanelRequest | null;
  onPendingConsumed?: () => void;
  onShowInBook?: (anchor: string) => void;
  onRequireAuth?: () => void;
  onConversationStarted: (conversationId: string) => void;
  onConversationKept: () => void;
  onConversationDiscarded: () => void;
}) {
  // A quote the reader chose to "Ask about": it rides along, once, with the next
  // typed question (RA-18) and shows as a dismissable context chip until then.
  const [attachedQuote, setAttachedQuote] = useState<string | null>(null);
  // The notes choice belongs to the conversation, so it is fixed when the thread
  // creates one and is always sent explicitly rather than left to a server guess.
  const notes = useIncludeNotes(SURFACE);
  const includeNotes = notes.includeNotes;

  // Which is why the control stops taking input once a conversation exists: it
  // then reports the choice that conversation was created with. Leaving it live
  // would offer the reader a flip that changes nothing about this thread.
  const [fixedNotes, setFixedNotes] = useState<boolean | null>(
    conversationIncludeNotes,
  );

  const start = useCallback(
    () =>
      startConversation(
        { sourceId, scopeAnchors: [], includeNotes },
        csrf,
      ),
    [sourceId, includeNotes, csrf],
  );

  const handleStarted = useCallback(
    (startedId: string) => {
      setFixedNotes(includeNotes);
      onConversationStarted(startedId);
    },
    [includeNotes, onConversationStarted],
  );

  // A discarded first message leaves no conversation, so the choice is the
  // reader's again.
  const handleDiscarded = useCallback(() => {
    setFixedNotes(null);
    onConversationDiscarded();
  }, [onConversationDiscarded]);

  const { messages, status, isStreaming, banner, send, stop } =
    useConversationThread({
      csrf,
      mode: "answer",
      conversationId,
      start,
      initialMessages,
      onConversationStarted: handleStarted,
      onConversationKept,
      onConversationDiscarded: handleDiscarded,
      onRequireAuth,
    });

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
      send(explainPrompt(pendingRequest.quote));
    } else {
      setAttachedQuote(pendingRequest.quote);
    }
    onPendingConsumed?.();
  }, [pendingRequest, send, onPendingConsumed]);

  const handleSubmit = useCallback(
    (message: PromptInputMessage) => {
      const text = message.text.trim();
      if (!text || isStreaming) {
        return;
      }
      send(attachedQuote ? askAboutPrompt(attachedQuote, text) : text);
      setAttachedQuote(null);
    },
    [attachedQuote, isStreaming, send],
  );

  const alert = banner ?? restoreError;

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
                  onClick={() => send(prompt)}
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
            const notFound = isNotFound(answerStatus);
            const previous = messages[index - 1];
            const question =
              previous?.role === "user" ? messageText(previous) : "";
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
                  {notFound && answerStatus ? (
                    <NotFoundNotice status={answerStatus} />
                  ) : citations ? (
                    <CitationList
                      sourceId={sourceId}
                      citations={citations}
                      onShowInBook={onShowInBook}
                    />
                  ) : null}
                  {!notFound && citations && citations.length > 0 ? (
                    <SaveToNoteAction
                      sourceId={sourceId}
                      question={question}
                      answerText={text}
                      citations={citations}
                      csrf={csrf}
                    />
                  ) : null}
                </MessageContent>
              </Message>
            );
          })}
        </ConversationContent>
      </Conversation>

      {alert ? (
        <p role="alert" className="text-sm text-destructive">
          {alert}
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

      <IncludeNotesToggle
        checked={fixedNotes ?? notes.includeNotes}
        onChange={notes.setIncludeNotes}
        locked={fixedNotes !== null}
      />

      <PromptInput onSubmit={handleSubmit}>
        <PromptInputBody>
          <PromptInputTextarea
            placeholder="Ask a question about this book…"
            disabled={isStreaming}
          />
        </PromptInputBody>
        <PromptInputFooter>
          <PromptInputSubmit status={status} onStop={stop} />
        </PromptInputFooter>
      </PromptInput>
    </div>
  );
}
