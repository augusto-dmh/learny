"use client";

/**
 * Teach panel (RA-10/11) — the Teach mode body of the reader side panel.
 *
 * Teaching is a conversation scoped to one section: the reader picks a target
 * and Start creates it immediately, then streams a frozen opening turn so the
 * tutor speaks first. Everything after runs on the same unified surface the Ask
 * panel uses — same start, read, turn, and turn-stream — so a taught thread is
 * persisted, resumable, and manageable like any other conversation.
 *
 * Because the dock owns the per-book conversation list, the panel no longer
 * keeps a resume list of its own; it restores whichever conversation this book's
 * Teach surface is pointed at and otherwise offers the target picker.
 *
 * A turn in flight always says what it is doing, exactly as Ask does: the phase
 * line while the book is being searched, the model's thinking in a collapsible
 * region while it thinks, then the streaming answer — and the taught answer
 * carries the same inline citation marks, opening passages in flow beneath it.
 *
 * Panel-only addition: when a session activates — on start AND on restore — the
 * panel asks the reader to bring the taught passage into view via `onShowInBook`,
 * exactly once per activation, so the book sits on the target while teaching runs
 * beside it (RA-11).
 *
 * `onRequireAuth` is a UX-only redirect for a mid-stream 401, NOT the security
 * boundary — FastAPI enforces auth, ownership, readiness, and scope resolution
 * on every call regardless of client-side routing (FR-AUTH-007, ADR-017).
 */

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  readActiveConversation,
  writeActiveConversation,
} from "@/app/lib/active-conversation";
import {
  ConversationRequestError,
  getConversation,
  startConversation,
} from "@/app/lib/conversations";
import {
  isTutorOpeningMessage,
  TUTOR_DONT_KNOW_MESSAGE,
  TUTOR_JUST_EXPLAIN_MESSAGE,
  TUTOR_OPENING_MESSAGE,
} from "@/app/lib/tutor";
import { fetchSourceStructure, type SourceStructure } from "@/app/lib/sources";
import {
  assistantView,
  errorMessageFor,
  messageText,
  StreamRequestError,
  turnsToUIMessages,
  type LearnyUIMessage,
} from "@/app/lib/streaming";
import { flattenSections } from "@/app/lib/tree";
import { Button } from "@/components/ui/button";
import {
  Conversation,
  ConversationContent,
} from "@/components/ai-elements/conversation";
import { Message, MessageContent } from "@/components/ai-elements/message";
import {
  PromptInput,
  PromptInputBody,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputTextarea,
  type PromptInputMessage,
} from "@/components/ai-elements/prompt-input";

import { AnswerPhaseIndicator, ReasoningRegion } from "./answer-phase";
import { CitedAnswer } from "./cited-answer";
import { FailedTurn } from "./failed-turn";
import { IncludeNotesToggle } from "./include-notes-toggle";
import { isNotFound, NotFoundNotice } from "./not-found-notice";
import { SaveToNoteAction } from "./save-to-note-action";
import { useConversationThread, type ConversationThread } from "./use-conversation-thread";
import { useIncludeNotes } from "./use-include-notes";

/** The surface name the active-conversation pointer is stored under. */
const SURFACE = "teach";

/** A taught thread the panel is showing: its target, and its restored turns. */
type TeachThread = {
  key: string;
  conversationId: string | null;
  /** The notes choice this conversation was created with; `null` before there is one. */
  includeNotes: boolean | null;
  targetAnchor: string;
  /** Shown when the target anchor no longer resolves against the live structure. */
  fallbackLabel: string;
  initialMessages: LearnyUIMessage[];
  tutorPhase: string | null;
};

export function TeachPanel({
  sourceId,
  csrf,
  revision = 0,
  currentAnchor = null,
  onShowInBook,
  onRequireAuth,
  onConversationsChanged,
  onAskAboutThis,
}: {
  sourceId: string;
  csrf: string;
  /** Bumped by the dock to make the panel re-read which conversation is active. */
  revision?: number;
  /** Section currently on screen; the picker defaults to it when it is a target. */
  currentAnchor?: string | null;
  onShowInBook?: (anchor: string) => void;
  onRequireAuth?: () => void;
  onConversationsChanged?: () => void;
  /** Switch Chat to a new Answer conversation on this book (TUTOR-33). */
  onAskAboutThis?: () => void;
}) {
  const [structure, setStructure] = useState<SourceStructure | null>(null);
  const [selectedAnchor, setSelectedAnchor] = useState("");
  const [thread, setThread] = useState<TeachThread | null>(null);
  const [restoring, setRestoring] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pickerTouchedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    void fetchSourceStructure(sourceId)
      .then((struct) => {
        if (cancelled) return;
        setStructure(struct);
        const options = flattenSections(struct.sections);
        if (options.length === 0) {
          return;
        }
        setSelectedAnchor((current) => {
          if (current) {
            return current;
          }
          if (
            currentAnchor &&
            options.some((option) => option.anchor === currentAnchor)
          ) {
            return currentAnchor;
          }
          return options[0].anchor;
        });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(
          err instanceof Error ? err.message : "Could not load this book.",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [sourceId, currentAnchor]);

  useEffect(() => {
    if (pickerTouchedRef.current || !structure) {
      return;
    }
    const options = flattenSections(structure.sections);
    if (
      currentAnchor &&
      options.some((option) => option.anchor === currentAnchor)
    ) {
      setSelectedAnchor(currentAnchor);
    }
  }, [currentAnchor, structure]);

  // Restore the conversation this book's Teach surface is pointed at. The turns
  // are always the server's copy; only the pointer is remembered locally.
  useEffect(() => {
    let cancelled = false;
    const stored = readActiveConversation(sourceId, SURFACE);
    if (!stored) {
      setThread(null);
      setRestoring(false);
      return;
    }
    setRestoring(true);
    void getConversation(stored)
      .then((detail) => {
        if (cancelled) return;
        setThread({
          key: detail.id,
          conversationId: detail.id,
          includeNotes: detail.include_notes,
          targetAnchor: detail.scope_anchors[0] ?? "",
          fallbackLabel: detail.title,
          initialMessages: turnsToUIMessages(detail.turns),
          tutorPhase: detail.tutor_phase ?? null,
        });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ConversationRequestError && err.status === 404) {
          writeActiveConversation(sourceId, SURFACE, null);
        } else {
          setError(
            err instanceof Error
              ? err.message
              : "Could not load that conversation.",
          );
        }
        setThread(null);
      })
      .finally(() => {
        if (!cancelled) setRestoring(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sourceId, revision]);

  const options = useMemo(
    () => (structure ? flattenSections(structure.sections) : []),
    [structure],
  );

  // The taught passage's breadcrumb, resolved against the live structure so a
  // restored thread reads the same as a freshly started one.
  const targetLabel = thread
    ? (options.find((option) => option.anchor === thread.targetAnchor)?.label ??
      thread.fallbackLabel)
    : "";

  // Bring the taught passage into view once per activation (start AND restore),
  // never per turn (RA-11).
  const shownForThreadRef = useRef<string | null>(null);
  useEffect(() => {
    if (thread && thread.targetAnchor && shownForThreadRef.current !== thread.key) {
      shownForThreadRef.current = thread.key;
      onShowInBook?.(thread.targetAnchor);
    }
  }, [thread, onShowInBook]);

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

  async function handleStart(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!selectedAnchor || starting) {
      return;
    }
    setStarting(true);
    const option = options.find((o) => o.anchor === selectedAnchor);
    try {
      const conversation = await startConversation(
        {
          sourceId,
          scopeAnchors: [selectedAnchor],
          includeNotes: false,
          title: option?.label ?? selectedAnchor,
        },
        csrf,
      );
      writeActiveConversation(sourceId, SURFACE, conversation.id);
      onConversationsChanged?.();
      setThread({
        key: conversation.id,
        conversationId: conversation.id,
        includeNotes: false,
        targetAnchor: selectedAnchor,
        fallbackLabel: option?.label ?? selectedAnchor,
        initialMessages: [],
        tutorPhase: conversation.tutor_phase ?? null,
      });
    } catch (err: unknown) {
      if (err instanceof StreamRequestError && err.status === 401) {
        onRequireAuth?.();
        return;
      }
      setError(
        err instanceof StreamRequestError
          ? err.message
          : "This conversation cannot be created. Please try again.",
      );
    } finally {
      setStarting(false);
    }
  }

  if (restoring) {
    return <p className="text-muted-foreground">Loading…</p>;
  }

  if (thread !== null) {
    return (
      <TeachChat
        key={thread.key}
        sourceId={sourceId}
        csrf={csrf}
        conversationId={thread.conversationId}
        conversationIncludeNotes={thread.includeNotes}
        targetAnchor={thread.targetAnchor}
        target={targetLabel}
        initialMessages={thread.initialMessages}
        tutorPhase={thread.tutorPhase}
        onShowInBook={onShowInBook}
        onRequireAuth={onRequireAuth}
        onConversationStarted={handleStarted}
        onConversationKept={handleKept}
        onAskAboutThis={onAskAboutThis}
      />
    );
  }

  return (
    <section aria-label="teach" className="space-y-6">
      <p className="text-sm text-muted-foreground">
        Tutor walks you through a section. Answer is for questions about the
        book.
      </p>
      <form onSubmit={handleStart} aria-label="start session" className="space-y-3">
        <div className="space-y-1.5">
          <label htmlFor="teach-target" className="text-sm font-medium">
            Target
          </label>
          <select
            id="teach-target"
            aria-label="Target"
            value={selectedAnchor}
            onChange={(e) => {
              pickerTouchedRef.current = true;
              setSelectedAnchor(e.target.value);
            }}
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
        <Button type="submit" disabled={selectedAnchor === "" || starting}>
          Start session
        </Button>
      </form>
    </section>
  );
}

function TeachChat({
  sourceId,
  csrf,
  conversationId,
  conversationIncludeNotes,
  targetAnchor,
  target,
  initialMessages,
  tutorPhase: initialTutorPhase,
  onShowInBook,
  onRequireAuth,
  onConversationStarted,
  onConversationKept,
  onAskAboutThis,
}: {
  sourceId: string;
  csrf: string;
  conversationId: string | null;
  /** The notes choice the conversation carries, or `null` before there is one. */
  conversationIncludeNotes: boolean | null;
  targetAnchor: string;
  target: string;
  initialMessages: LearnyUIMessage[];
  tutorPhase: string | null;
  onShowInBook?: (anchor: string) => void;
  onRequireAuth?: () => void;
  onConversationStarted: (conversationId: string) => void;
  onConversationKept: () => void;
  onAskAboutThis?: () => void;
}) {
  // The notes choice belongs to the conversation, so it is fixed when the thread
  // creates one and is always sent explicitly rather than left to a server guess.
  const notes = useIncludeNotes(SURFACE);

  // The control reports the choice that conversation was created with. Leaving
  // it live would offer the reader a flip that changes nothing about this thread.
  const [fixedNotes, setFixedNotes] = useState<boolean | null>(
    conversationIncludeNotes,
  );

  const start = useCallback(
    () =>
      startConversation(
        {
          sourceId,
          scopeAnchors: [targetAnchor],
          includeNotes: false,
          title: target,
        },
        csrf,
      ),
    [sourceId, targetAnchor, target, csrf],
  );

  const handleStarted = useCallback(
    (startedId: string) => {
      setFixedNotes(false);
      onConversationStarted(startedId);
    },
    [onConversationStarted],
  );

  const { messages, status, isStreaming, banner, failedTurn, send, stop } =
    useConversationThread({
      csrf,
      mode: "teach",
      conversationId,
      start,
      initialMessages,
      onConversationStarted: handleStarted,
      onConversationKept,
      onRequireAuth,
    });

  const openedForIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (!conversationId || initialMessages.length > 0) {
      return;
    }
    if (openedForIdRef.current === conversationId) {
      return;
    }
    openedForIdRef.current = conversationId;
    send(TUTOR_OPENING_MESSAGE);
  }, [conversationId, initialMessages.length, send]);

  const openingPersisted =
    failedTurn !== null ||
    messages.some((message) => {
      if (message.role !== "assistant") {
        return false;
      }
      const { status: answerStatus } = assistantView(message);
      return (
        answerStatus === "answered" ||
        answerStatus === "not_found_in_source" ||
        answerStatus === "not_found_in_scope" ||
        answerStatus === "failed"
      );
    });
  // Hide the composer while the opening is in flight — including the gap
  // after create and the tail of the stream after the status frame lands.
  const openingInFlight =
    initialMessages.length === 0 &&
    failedTurn === null &&
    (isStreaming || !openingPersisted);

  const [tutorPhase, setTutorPhase] = useState(initialTutorPhase);
  useEffect(() => {
    setTutorPhase(initialTutorPhase);
  }, [initialTutorPhase]);

  useEffect(() => {
    if (!conversationId || isStreaming) {
      return;
    }
    let cancelled = false;
    void getConversation(conversationId)
      .then((detail) => {
        if (!cancelled) {
          setTutorPhase(detail.tutor_phase ?? null);
        }
      })
      .catch(() => {
        // Phase is advisory for the composer; a failed read leaves the last known value.
      });
    return () => {
      cancelled = true;
    };
  }, [conversationId, isStreaming, messages.length]);

  const sessionClosed = tutorPhase === "close";

  const retryFailedTurn = useCallback(() => {
    if (!failedTurn?.userText) {
      return;
    }
    send(failedTurn.userText);
  }, [failedTurn, send]);

  const handleSubmit = useCallback(
    (message: PromptInputMessage) => {
      const text = message.text.trim();
      if (!text || isStreaming) {
        return;
      }
      send(text);
    },
    [isStreaming, send],
  );

  return (
    <section aria-label="teach conversation" className="flex h-full flex-col gap-4">
      <h2 className="text-lg font-semibold">{target}</h2>
      <Conversation>
        <ConversationContent>
          {messages.map((message, index) => {
            if (message.role === "user") {
              const opening = isTutorOpeningMessage(messageText(message));
              return (
                <Fragment key={message.id}>
                  {opening ? null : (
                    <Message from="user">
                      <MessageContent>
                        {message.parts.map((part, i) =>
                          part.type === "text" ? (
                            <span data-testid="user-message" key={i}>
                              {part.text}
                            </span>
                          ) : null,
                        )}
                      </MessageContent>
                    </Message>
                  )}
                  {failedTurn?.messageId === message.id ? (
                    <Message from="assistant">
                      <MessageContent>
                        <FailedTurn
                          error={failedTurn.error}
                          onRetry={retryFailedTurn}
                          retryDisabled={isStreaming}
                        />
                      </MessageContent>
                    </Message>
                  ) : null}
                </Fragment>
              );
            }
            const { text, citations, status: answerStatus, reasoning } =
              assistantView(message);
            const notFound = isNotFound(answerStatus);
            const restoredFailed = answerStatus === "failed";
            const liveFailed = failedTurn?.messageId === message.id;
            const previous = messages[index - 1];
            const question =
              previous?.role === "user" ? messageText(previous) : "";
            // The turn is still working while it is the live one and has neither
            // thought nor spoken yet — that is the gap the phase line fills.
            const pending = index === messages.length - 1 && isStreaming;
            return (
              <Message from="assistant" key={message.id}>
                <MessageContent>
                  {reasoning && !notFound && !restoredFailed ? (
                    <ReasoningRegion
                      text={reasoning}
                      thinking={pending && !text}
                    />
                  ) : null}
                  {pending && !text && !reasoning ? (
                    <AnswerPhaseIndicator />
                  ) : null}
                  {restoredFailed && !text ? null : (
                    <CitedAnswer
                      sourceId={sourceId}
                      text={text}
                      citations={notFound || restoredFailed ? null : citations}
                      onShowInBook={onShowInBook}
                    />
                  )}
                  {notFound && answerStatus ? (
                    <NotFoundNotice status={answerStatus} />
                  ) : null}
                  {!notFound && !restoredFailed && citations && citations.length > 0 ? (
                    <SaveToNoteAction
                      sourceId={sourceId}
                      question={question}
                      answerText={text}
                      citations={citations}
                      csrf={csrf}
                    />
                  ) : null}
                  {liveFailed || restoredFailed ? (
                    <FailedTurn
                      error={
                        liveFailed && failedTurn
                          ? failedTurn.error
                          : errorMessageFor(502)
                      }
                      onRetry={() =>
                        send(
                          (liveFailed && failedTurn?.userText) || question,
                        )
                      }
                      retryDisabled={isStreaming}
                    />
                  ) : null}
                </MessageContent>
              </Message>
            );
          })}
          {/* The message is sent but the answer's message does not exist yet:
              the same search is already under way, so it reads the same. */}
          {isStreaming && messages[messages.length - 1]?.role === "user" ? (
            <AnswerPhaseIndicator />
          ) : null}
          {failedTurn &&
          !messages.some((message) => message.id === failedTurn.messageId) ? (
            <Message from="assistant">
              <MessageContent>
                <FailedTurn
                  error={failedTurn.error}
                  onRetry={retryFailedTurn}
                  retryDisabled={isStreaming}
                />
              </MessageContent>
            </Message>
          ) : null}
        </ConversationContent>
      </Conversation>

      {banner ? (
        <p role="alert" className="text-sm text-destructive">
          {banner}
        </p>
      ) : null}

      {sessionClosed ? (
        <ClosedSessionHandoff onAskAboutThis={onAskAboutThis} />
      ) : openingInFlight ? null : (
        <TutorComposer
          notesChecked={fixedNotes ?? notes.includeNotes}
          onNotesChange={notes.setIncludeNotes}
          notesLocked={fixedNotes !== null}
          onSubmit={handleSubmit}
          onJustExplain={() => send(TUTOR_JUST_EXPLAIN_MESSAGE)}
          onDontKnow={() => send(TUTOR_DONT_KNOW_MESSAGE)}
          chipsDisabled={isStreaming}
          status={status}
          onStop={stop}
          streaming={isStreaming}
        />
      )}
    </section>
  );
}

function TutorChips({
  onJustExplain,
  onDontKnow,
  disabled,
}: {
  onJustExplain: () => void;
  onDontKnow: () => void;
  disabled: boolean;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={disabled}
        onClick={onJustExplain}
      >
        {TUTOR_JUST_EXPLAIN_MESSAGE}
      </Button>
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={disabled}
        onClick={onDontKnow}
      >
        {TUTOR_DONT_KNOW_MESSAGE}
      </Button>
    </div>
  );
}

function TutorComposer({
  notesChecked,
  onNotesChange,
  notesLocked,
  onSubmit,
  onJustExplain,
  onDontKnow,
  chipsDisabled,
  status,
  onStop,
  streaming,
}: {
  notesChecked: boolean;
  onNotesChange: (value: boolean) => void;
  notesLocked: boolean;
  onSubmit: (message: PromptInputMessage) => void;
  onJustExplain: () => void;
  onDontKnow: () => void;
  chipsDisabled: boolean;
  status: ConversationThread["status"];
  onStop: () => void;
  streaming: boolean;
}) {
  return (
    <>
      <IncludeNotesToggle
        checked={notesChecked}
        onChange={onNotesChange}
        locked={notesLocked}
      />
      <TutorChips
        onJustExplain={onJustExplain}
        onDontKnow={onDontKnow}
        disabled={chipsDisabled}
      />
      <PromptInput onSubmit={onSubmit}>
        <PromptInputBody>
          <PromptInputTextarea
            placeholder="Send a message…"
            disabled={streaming}
          />
        </PromptInputBody>
        <PromptInputFooter>
          <PromptInputSubmit status={status} onStop={onStop} />
        </PromptInputFooter>
      </PromptInput>
    </>
  );
}

function ClosedSessionHandoff({
  onAskAboutThis,
}: {
  onAskAboutThis?: () => void;
}) {
  return (
    <Button type="button" onClick={() => onAskAboutThis?.()}>
      Ask about this
    </Button>
  );
}

