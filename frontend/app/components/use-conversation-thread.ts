"use client";

/**
 * One chat thread on the unified conversation surface, shared by Ask and Teach.
 *
 * Starting a conversation and posting a turn are two calls, and this hook owns
 * the seam between them. A thread begins with no conversation at all; the first
 * message creates one and streams into it, and every message after streams
 * straight into the same one.
 *
 * That split is also where an orphan could appear: the create can succeed and
 * the stream then fail or be stopped, leaving a conversation with no grounded
 * turn — something the dock would list and the reader never meant to make. So a
 * conversation created for a first message stays *provisional* until that
 * message finishes, and any abort, network drop, or error discards it. The
 * backend already refuses to persist an ungrounded turn; this keeps the same
 * promise for the conversation the turn would have lived in.
 *
 * A conversation created by an earlier, completed message is never provisional —
 * a later failure leaves the thread and its stored turns exactly as they were.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useChat } from "@ai-sdk/react";

import {
  deleteConversation,
  type ConversationMode,
  type ConversationView,
} from "@/app/lib/conversations";
import {
  createConversationTransport,
  StreamRequestError,
  type LearnyUIMessage,
} from "@/app/lib/streaming";

export type ConversationThread = {
  /** The thread's messages: restored turns first, then anything streamed since. */
  messages: LearnyUIMessage[];
  /** The `useChat` status, passed straight to the prompt input. */
  status: ReturnType<typeof useChat<LearnyUIMessage>>["status"];
  /** Whether a turn is in flight (submitted or streaming). */
  isStreaming: boolean;
  /** The readable failure message to show, or `null`. */
  banner: string | null;
  /** Send one message, creating the conversation first if the thread has none. */
  send: (text: string) => void;
  /** Stop an in-flight turn; a stopped first message discards its conversation. */
  stop: () => void;
};

export function useConversationThread({
  csrf,
  mode,
  conversationId,
  start,
  initialMessages,
  onConversationStarted,
  onConversationKept,
  onConversationDiscarded,
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
  /** Called when a first message lands, which is when its conversation is real. */
  onConversationKept?: () => void;
  /** Called when a provisional conversation is discarded. */
  onConversationDiscarded?: () => void;
  onRequireAuth?: () => void;
}): ConversationThread {
  const [banner, setBanner] = useState<string | null>(null);

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

  // The conversation created for a first message that has not completed yet.
  const provisionalRef = useRef<string | null>(null);

  const discardProvisional = useCallback(async () => {
    const provisional = provisionalRef.current;
    if (!provisional) {
      return;
    }
    provisionalRef.current = null;
    idRef.current = null;
    externalIdRef.current = null;
    onConversationDiscarded?.();
    try {
      await deleteConversation(provisional, csrf);
    } catch {
      // Best effort: the reader already has a readable failure on screen, and a
      // conversation with no turn is not something to interrupt them about.
    }
  }, [csrf, onConversationDiscarded]);

  const resolveConversationId = useCallback(async () => {
    const existing = idRef.current;
    if (existing) {
      return existing;
    }
    const conversation = await start();
    idRef.current = conversation.id;
    externalIdRef.current = conversation.id;
    provisionalRef.current = conversation.id;
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
      setBanner(err.message);
    },
    onFinish: ({ isAbort, isDisconnect, isError }) => {
      if (isAbort || isDisconnect || isError) {
        void discardProvisional();
        return;
      }
      // The first message landed, so its conversation is real from here on — and
      // only now is there a thread for the dock to list. Announcing it at creation
      // instead would offer the reader a row that may be about to be discarded.
      if (provisionalRef.current) {
        provisionalRef.current = null;
        onConversationKept?.();
      }
    },
  });

  const isStreaming = status === "submitted" || status === "streaming";

  const send = useCallback(
    (text: string) => {
      if (!text || isStreaming) {
        return;
      }
      setBanner(null);
      void sendMessage({ text });
    },
    [isStreaming, sendMessage],
  );

  const stopThread = useCallback(() => {
    void stop();
  }, [stop]);

  return { messages, status, isStreaming, banner, send, stop: stopThread };
}
