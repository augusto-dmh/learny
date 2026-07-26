"use client";

/**
 * Teach panel (RA-10/11) — the Teach mode body of the reader side panel.
 *
 * Teaching is a conversation scoped to one section: the reader picks a target,
 * and the first message creates a conversation whose scope is that target's
 * anchor and whose turns are taught rather than answered. Everything after runs
 * on the same unified surface the Ask panel uses — same start, read, turn, and
 * turn-stream — so a taught thread is persisted, resumable, and manageable like
 * any other conversation.
 *
 * Because the dock owns the per-book conversation list, the panel no longer
 * keeps a resume list of its own; it restores whichever conversation this book's
 * Teach surface is pointed at and otherwise offers the target picker.
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

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  readActiveConversation,
  writeActiveConversation,
} from "@/app/lib/active-conversation";
import {
  ConversationRequestError,
  getConversation,
  startConversation,
} from "@/app/lib/conversations";
import { fetchSourceStructure, type SourceStructure } from "@/app/lib/sources";
import {
  assistantView,
  messageText,
  turnsToUIMessages,
  type LearnyUIMessage,
} from "@/app/lib/streaming";
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
import { IncludeNotesToggle } from "./include-notes-toggle";
import { isNotFound, NotFoundNotice } from "./not-found-notice";
import { SaveToNoteAction } from "./save-to-note-action";
import { useConversationThread } from "./use-conversation-thread";
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
};

export function TeachPanel({
  sourceId,
  csrf,
  revision = 0,
  onShowInBook,
  onRequireAuth,
  onConversationsChanged,
}: {
  sourceId: string;
  csrf: string;
  /** Bumped by the dock to make the panel re-read which conversation is active. */
  revision?: number;
  onShowInBook?: (anchor: string) => void;
  onRequireAuth?: () => void;
  onConversationsChanged?: () => void;
}) {
  const [structure, setStructure] = useState<SourceStructure | null>(null);
  const [selectedAnchor, setSelectedAnchor] = useState("");
  const [thread, setThread] = useState<TeachThread | null>(null);
  const [restoring, setRestoring] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const startCountRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    void fetchSourceStructure(sourceId)
      .then((struct) => {
        if (cancelled) return;
        setStructure(struct);
        const options = flattenSections(struct.sections);
        if (options.length > 0) {
          setSelectedAnchor((current) => current || options[0].anchor);
        }
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
  }, [sourceId]);

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

  const handleDiscarded = useCallback(() => {
    writeActiveConversation(sourceId, SURFACE, null);
    onConversationsChanged?.();
  }, [sourceId, onConversationsChanged]);

  function handleStart(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!selectedAnchor) {
      return;
    }
    startCountRef.current += 1;
    const option = options.find((o) => o.anchor === selectedAnchor);
    setThread({
      key: `new-${startCountRef.current}`,
      conversationId: null,
      includeNotes: null,
      targetAnchor: selectedAnchor,
      fallbackLabel: option?.label ?? selectedAnchor,
      initialMessages: [],
    });
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
        onShowInBook={onShowInBook}
        onRequireAuth={onRequireAuth}
        onConversationStarted={handleStarted}
        onConversationDiscarded={handleDiscarded}
      />
    );
  }

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
        <Button type="submit" disabled={selectedAnchor === ""}>
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
  onShowInBook,
  onRequireAuth,
  onConversationStarted,
  onConversationDiscarded,
}: {
  sourceId: string;
  csrf: string;
  conversationId: string | null;
  /** The notes choice the conversation carries, or `null` before there is one. */
  conversationIncludeNotes: boolean | null;
  targetAnchor: string;
  target: string;
  initialMessages: LearnyUIMessage[];
  onShowInBook?: (anchor: string) => void;
  onRequireAuth?: () => void;
  onConversationStarted: (conversationId: string) => void;
  onConversationDiscarded: () => void;
}) {
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
        {
          sourceId,
          scopeAnchors: [targetAnchor],
          includeNotes,
          title: target,
        },
        csrf,
      ),
    [sourceId, targetAnchor, includeNotes, target, csrf],
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
      mode: "teach",
      conversationId,
      start,
      initialMessages,
      onConversationStarted: handleStarted,
      onConversationDiscarded: handleDiscarded,
      onRequireAuth,
    });

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
              return (
                <Message from="user" key={message.id}>
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

      {banner ? (
        <p role="alert" className="text-sm text-destructive">
          {banner}
        </p>
      ) : null}

      <IncludeNotesToggle
        checked={fixedNotes ?? notes.includeNotes}
        onChange={notes.setIncludeNotes}
        locked={fixedNotes !== null}
      />

      <PromptInput onSubmit={handleSubmit}>
        <PromptInputBody>
          <PromptInputTextarea
            placeholder="Send a message…"
            disabled={isStreaming}
          />
        </PromptInputBody>
        <PromptInputFooter>
          <PromptInputSubmit status={status} onStop={stop} />
        </PromptInputFooter>
      </PromptInput>
    </section>
  );
}
