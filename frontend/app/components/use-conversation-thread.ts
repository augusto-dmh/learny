"use client";

/**
 * One chat thread on the unified conversation surface, shared by Ask and Teach.
 *
 * Starting a conversation and posting a turn are two calls, and this hook owns
 * the seam between them. A thread begins with no conversation at all; the first
 * message creates one and streams into it, and every message after streams
 * straight into the same one.
 *
 * A conversation is kept whatever its first message does. A provider failure, a
 * stopped stream, or a dropped connection leaves both the conversation and the
 * question inside it, because the question is the part worth keeping: the
 * backend stores the failed turn, and the reader retries it from the thread
 * instead of watching the thread disappear. Deleting a conversation stays
 * something the reader does deliberately, from the dock.
 *
 * What the create-then-stream split still owns is *when the dock hears about
 * it*: a conversation is announced once its first message settles, not at
 * creation, so no row appears before there is a turn to resume.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useChat } from "@ai-sdk/react";

import {
  type ConversationMode,
  type ConversationView,
} from "@/app/lib/conversations";
import {
  createConversationTransport,
  messageText,
  StreamRequestError,
  type LearnyUIMessage,
} from "@/app/lib/streaming";

/** The turn that failed last, so Retry can resubmit the same question. */
export type FailedTurnState = {
  error: string;
  userText: string;
  messageId: string | null;
};

export type ConversationThread = {
  /** The thread's messages: restored turns first, then anything streamed since. */
  messages: LearnyUIMessage[];
  /** The `useChat` status, passed straight to the prompt input. */
  status: ReturnType<typeof useChat<LearnyUIMessage>>["status"];
  /** Whether a turn is in flight (submitted or streaming). */
  isStreaming: boolean;
  /** The readable failure message to show, or `null`. */
  banner: string | null;
  /** The in-thread failure Retry is bound to, or `null` when none has failed. */
  failedTurn: FailedTurnState | null;
  /** Send one message, creating the conversation first if the thread has none. */
  send: (text: string) => void;
  /** Stop an in-flight turn; the conversation and its question stay. */
  stop: () => void;
};

function lastUserText(messages: LearnyUIMessage[]): string {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "user") {
      return messageText(messages[i]);
    }
  }
  return "";
}

export function useConversationThread({
  csrf,
  mode,
  conversationId,
  start,
  initialMessages,
  onConversationStarted,
  onConversationKept,
  onRequireAuth,
}: {
  csrf: string;
  mode: ConversationMode;
  /** The conversation this thread continues, or `null` to create one on send. */
  conversationId: string | null;
  /** Creates the conversation a first message needs. */
  start: () => Promise<ConversationView>;
  /** Turns already stored on the server, replayed into the chat. */
  initialMessages: LearnyUIMessage[];
  /** Called once a first message has a conversation to stream into. */
  onConversationStarted?: (conversationId: string) => void;
  /** Called once a first message settles, which is when the dock can list it. */
  onConversationKept?: () => void;
  onRequireAuth?: () => void;
}): ConversationThread {
  const [banner, setBanner] = useState<string | null>(null);
  const [failedTurn, setFailedTurn] = useState<FailedTurnState | null>(null);
  const messagesRef = useRef<LearnyUIMessage[]>([]);
  const lastSentRef = useRef("");

  // The id the *transport* streams into. It has to be a ref because it is read
  // and written inside one send, before React has re-rendered with the new value.
  const idRef = useRef<string | null>(conversationId);
  // The last id this hook was told about from outside, so a re-render never
  // clobbers an id the current send just created.
  const externalIdRef = useRef<string | null>(conversationId);
  useEffect(() => {
    if (externalIdRef.current !== conversationId) {
      externalIdRef.current = conversationId;
      idRef.current = conversationId;
    }
  }, [conversationId]);

  // The conversation created for a first message the dock has not heard about.
  const unannouncedRef = useRef<string | null>(null);

  const resolveConversationId = useCallback(async () => {
    const existing = idRef.current;
    if (existing) {
      return existing;
    }
    const conversation = await start();
    idRef.current = conversation.id;
    externalIdRef.current = conversation.id;
    unannouncedRef.current = conversation.id;
    onConversationStarted?.(conversation.id);
    return conversation.id;
  }, [start, onConversationStarted]);

  const transport = useMemo(
    () =>
      createConversationTransport({
        mode,
        csrfToken: csrf,
        resolveConversationId,
      }),
    [mode, csrf, resolveConversationId],
  );

  const { messages, sendMessage, status, stop } = useChat<LearnyUIMessage>({
    transport,
    messages: initialMessages,
    // A thinking model streams reasoning deltas on top of the answer's, and every
    // one of them would otherwise re-render the whole thread — which re-parses the
    // answer's markdown and grows with the transcript. Coalescing to ~20 updates a
    // second is still below what reads as a delay in text appearing.
    experimental_throttle: 50,
    onError: (err) => {
      // A 401 mid-stream redirects to login (parity); everything else renders as
      // a readable banner while any partial text is retained.
      if (err instanceof StreamRequestError && err.status === 401) {
        onRequireAuth?.();
        return;
      }
      const current = messagesRef.current;
      setBanner(err.message);
      setFailedTurn({
        error: err.message,
        userText: lastUserText(current) || lastSentRef.current,
        messageId: current[current.length - 1]?.id ?? null,
      });
    },
    onFinish: () => {
      // The first message has settled — landed, stopped, or failed — and the
      // conversation is the reader's either way, so this is when the dock is
      // told there is a thread to find. Announcing it at creation instead would
      // offer a row before the server had a turn to put in it.
      if (unannouncedRef.current) {
        unannouncedRef.current = null;
        onConversationKept?.();
      }
    },
  });

  messagesRef.current = messages;

  const isStreaming = status === "submitted" || status === "streaming";

  const send = useCallback(
    (text: string) => {
      if (!text || isStreaming) {
        return;
      }
      lastSentRef.current = text;
      setBanner(null);
      void sendMessage({ text });
    },
    [isStreaming, sendMessage],
  );

  const stopThread = useCallback(() => {
    void stop();
  }, [stop]);

  return {
    messages,
    status,
    isStreaming,
    banner,
    failedTurn,
    send,
    stop: stopThread,
  };
}
