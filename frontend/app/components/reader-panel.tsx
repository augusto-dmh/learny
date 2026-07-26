"use client";

/**
 * The reader side panel (RA-01..03/06): a fixed-width right-hand column that hosts
 * the Ask and Teach modes beside the chapter so studying never leaves the page.
 *
 * The shell owns the mode switch (an Ask | Teach segmented control), the close
 * control, and this book's conversation list. Open state and mode are pure URL
 * state driven by `?panel=`, so the parent renders the panel only when a mode is
 * active — closing it simply drops the query param and restores full reading
 * width, and reading stays non-modal underneath.
 *
 * The conversation list is deliberately mode-agnostic and shown in both modes:
 * one book has one set of threads. Which panel resumes a given thread follows
 * from its scope — a whole-book conversation is continued as a question, a
 * section-scoped one as teaching — so the shell switches tabs when it has to
 * rather than asking the reader to guess which tab their thread is behind.
 */

import { X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  readActiveConversation,
  writeActiveConversation,
} from "@/app/lib/active-conversation";
import { type ConversationSummaryView } from "@/app/lib/conversations";
import { type PendingPanelRequest } from "@/app/lib/panel";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { AskPanel } from "./ask-panel";
import { ConversationList } from "./conversation-list";
import { TeachPanel } from "./teach-panel";

export type PanelMode = "ask" | "teach";

const MODES: { value: PanelMode; label: string }[] = [
  { value: "ask", label: "Ask" },
  { value: "teach", label: "Teach" },
];

/** Which panel continues a conversation, decided by the scope it was given. */
function panelFor(summary: ConversationSummaryView): PanelMode {
  return summary.scope_anchors.length > 0 ? "teach" : "ask";
}

export function ReaderPanel({
  sourceId,
  csrf,
  mode,
  onModeChange,
  onClose,
  pendingRequest,
  onPendingConsumed,
  onShowInBook,
  onRequireAuth,
}: {
  sourceId: string;
  csrf: string;
  mode: PanelMode;
  onModeChange: (mode: PanelMode) => void;
  onClose: () => void;
  pendingRequest?: PendingPanelRequest | null;
  onPendingConsumed?: () => void;
  onShowInBook?: (anchor: string) => void;
  onRequireAuth?: () => void;
}) {
  // Bumped per surface to tell a panel to re-read which conversation is active;
  // creating one mid-thread deliberately does not bump anything, or the panel
  // would remount in the middle of the message that created it.
  const [revisions, setRevisions] = useState<Record<PanelMode, number>>({
    ask: 0,
    teach: 0,
  });
  const [listToken, setListToken] = useState(0);
  const [activeIds, setActiveIds] = useState<Record<PanelMode, string | null>>({
    ask: null,
    teach: null,
  });

  const syncActiveIds = useCallback(() => {
    setActiveIds({
      ask: readActiveConversation(sourceId, "ask"),
      teach: readActiveConversation(sourceId, "teach"),
    });
  }, [sourceId]);

  useEffect(() => {
    syncActiveIds();
  }, [syncActiveIds]);

  const handleConversationsChanged = useCallback(() => {
    syncActiveIds();
    setListToken((token) => token + 1);
  }, [syncActiveIds]);

  const handleResume = useCallback(
    (summary: ConversationSummaryView) => {
      const target = panelFor(summary);
      writeActiveConversation(sourceId, target, summary.id);
      setActiveIds((current) => ({ ...current, [target]: summary.id }));
      setRevisions((current) => ({
        ...current,
        [target]: current[target] + 1,
      }));
      if (target !== mode) {
        onModeChange(target);
      }
    },
    [sourceId, mode, onModeChange],
  );

  // Deleting the conversation a panel is showing cannot leave that panel
  // rendering a thread the server no longer has, so the surface pointing at it
  // is cleared and told to re-read — which lands it on its empty state.
  const handleDeleted = useCallback(
    (conversationId: string) => {
      for (const surface of ["ask", "teach"] as PanelMode[]) {
        if (readActiveConversation(sourceId, surface) !== conversationId) {
          continue;
        }
        writeActiveConversation(sourceId, surface, null);
        setActiveIds((current) => ({ ...current, [surface]: null }));
        setRevisions((current) => ({
          ...current,
          [surface]: current[surface] + 1,
        }));
      }
    },
    [sourceId],
  );

  const handleNew = useCallback(() => {
    writeActiveConversation(sourceId, mode, null);
    setActiveIds((current) => ({ ...current, [mode]: null }));
    setRevisions((current) => ({ ...current, [mode]: current[mode] + 1 }));
  }, [sourceId, mode]);

  return (
    <aside
      data-testid="reader-panel"
      data-mode={mode}
      aria-label={mode === "ask" ? "Ask panel" : "Teach panel"}
      className="sticky top-0 flex h-[calc(100vh-3rem)] w-[26rem] shrink-0 flex-col overflow-y-auto border-l bg-background"
    >
      <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
        <div role="tablist" aria-label="Panel mode" className="flex gap-1">
          {MODES.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={mode === value}
              onClick={() => onModeChange(value)}
              className={cn(
                "rounded-md px-3 py-1 text-sm font-medium transition-colors",
                mode === value
                  ? "bg-accent text-foreground"
                  : "text-muted-foreground hover:bg-accent/50",
              )}
            >
              {label}
            </button>
          ))}
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label="Close panel"
          onClick={onClose}
        >
          <X />
        </Button>
      </div>

      <ConversationList
        sourceId={sourceId}
        csrf={csrf}
        refreshToken={listToken}
        activeConversationId={activeIds[mode]}
        onResume={handleResume}
        onNew={handleNew}
        onDeleted={handleDeleted}
      />

      <div className="min-h-0 flex-1 p-3">
        {mode === "ask" ? (
          <AskPanel
            sourceId={sourceId}
            csrf={csrf}
            revision={revisions.ask}
            pendingRequest={pendingRequest}
            onPendingConsumed={onPendingConsumed}
            onShowInBook={onShowInBook}
            onRequireAuth={onRequireAuth}
            onConversationsChanged={handleConversationsChanged}
          />
        ) : (
          <TeachPanel
            sourceId={sourceId}
            csrf={csrf}
            revision={revisions.teach}
            onShowInBook={onShowInBook}
            onRequireAuth={onRequireAuth}
            onConversationsChanged={handleConversationsChanged}
          />
        )}
      </div>
    </aside>
  );
}
