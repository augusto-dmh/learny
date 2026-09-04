"use client";

/**
 * The reader side panel (RA-01..03/06): a fixed-width right-hand column that hosts
 * the book's four working surfaces beside the chapter so studying never leaves the
 * page.
 *
 * The shell owns the tab strip (Ask | Teach | Notes | Review), the close control,
 * and this book's conversation list. Open state and the active tab are pure URL
 * state driven by `?panel=`, so the parent renders the panel only when a tab is
 * active — closing it simply drops the query param and restores full reading
 * width, and reading stays non-modal underneath.
 *
 * Only two of those tabs hold a conversation. `PanelMode` stays the conversation
 * subset — it keys the per-surface `activeIds`/`revisions` maps, where a key that
 * can never hold a conversation would be a lie — while `DockTab` is what the strip
 * and `?panel=` speak. The conversation list therefore renders on conversation
 * tabs only.
 *
 * The conversation list is deliberately mode-agnostic and shown in both
 * conversation tabs: one book has one set of threads. Which panel resumes a given
 * thread follows from the mode its turns were answered in, so the shell switches
 * tabs when it has to rather than asking the reader to guess which tab their
 * thread is behind.
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
import { DockNotesPanel, useBookNotes } from "./dock-notes-panel";
import { DockReviewPanel, useDueCount } from "./dock-review-panel";
import { TeachPanel } from "./teach-panel";

/** A dock surface that holds a conversation, and so has per-surface thread state. */
export type PanelMode = "ask" | "teach";

/** Every tab in the dock's strip, and every value `?panel=` accepts. */
export type DockTab = PanelMode | "notes" | "review";

const TABS: { value: DockTab; label: string }[] = [
  { value: "ask", label: "Ask" },
  { value: "teach", label: "Teach" },
  { value: "notes", label: "Notes" },
  { value: "review", label: "Review" },
];

const TAB_TITLES: Record<DockTab, string> = {
  ask: "Ask panel",
  teach: "Teach panel",
  notes: "Notes panel",
  review: "Review panel",
};

/**
 * Whether a tab is one of the conversation surfaces — the guard that keeps the
 * conversation state maps keyed by something that can actually hold a thread.
 */
export function isConversationTab(tab: DockTab): tab is PanelMode {
  return tab === "ask" || tab === "teach";
}

/** The `?panel=` value, or null when it names no tab the dock has. */
export function dockTabFromParam(value: string | null): DockTab | null {
  return TABS.some((tab) => tab.value === value) ? (value as DockTab) : null;
}

/**
 * Which panel continues a conversation, decided by the mode its last turn was
 * answered in.
 *
 * Scope is deliberately not consulted. A conversation's scope says which
 * sections retrieval may see, not how its turns are answered: a chapter-scoped
 * conversation whose turns were *asked* is an Ask thread, and resuming it into
 * Teach would silently change what the reader's next message does. Mode is
 * recorded on every turn, so it is read rather than inferred — the same rule the
 * generation adapters keep on the other side of the wire.
 *
 * The list row carries it, so this is a decision, not a request: fetching the
 * conversation to read one word would pull every turn and every citation, and
 * the panel then loads the same payload again to restore the thread.
 *
 * A conversation with no turn to speak for it leaves the reader on the tab they
 * are already on: there is nothing that says otherwise, and guessing is what
 * this exists to avoid.
 */
function panelFor(
  summary: ConversationSummaryView,
  fallback: PanelMode,
): PanelMode {
  if (!summary.last_turn_mode) {
    return fallback;
  }
  return summary.last_turn_mode === "teach" ? "teach" : "ask";
}

/**
 * What a tab is holding, when it is holding anything. An empty queue is an empty
 * tab, not a "0" — a zero here would be a scoreboard, and the dock keeps no score.
 */
function TabCount({ value }: { value?: number | null }) {
  if (!value) {
    return null;
  }
  return (
    <span className="ml-1.5 rounded-4xl bg-secondary px-1.5 text-xs font-normal text-secondary-foreground">
      {value}
    </span>
  );
}

export function ReaderPanel({
  sourceId,
  csrf,
  tab,
  onTabChange,
  onClose,
  pendingRequest,
  onPendingConsumed,
  onShowInBook,
  onRequireAuth,
  notesToken = 0,
}: {
  sourceId: string;
  csrf: string;
  tab: DockTab;
  onTabChange: (tab: DockTab) => void;
  onClose: () => void;
  pendingRequest?: PendingPanelRequest | null;
  onPendingConsumed?: () => void;
  onShowInBook?: (anchor: string) => void;
  onRequireAuth?: () => void;
  /** Bumped by the reader when a passage is captured, so the Notes tab re-reads. */
  notesToken?: number;
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

  // Null on Notes and Review: those tabs hold no thread, so there is nothing for
  // a resume to land in and no list rendered to ask for one.
  const conversationTab = isConversationTab(tab) ? tab : null;

  // Loaded by the shell, not the tab: a count on a tab is only useful before the
  // reader has opened it.
  const bookNotes = useBookNotes(sourceId, notesToken);
  const bookDue = useDueCount(sourceId);

  // Which panel continues a thread is on the row the reader clicked, so a resume
  // resolves in the click that asked for it — no request to race, and no window
  // in which a second click could land the reader wherever the slower fetch
  // finished.
  const handleResume = useCallback(
    (summary: ConversationSummaryView) => {
      if (!conversationTab) {
        return;
      }
      const target = panelFor(summary, conversationTab);
      writeActiveConversation(sourceId, target, summary.id);
      setActiveIds((current) => ({ ...current, [target]: summary.id }));
      setRevisions((current) => ({
        ...current,
        [target]: current[target] + 1,
      }));
      if (target !== conversationTab) {
        onTabChange(target);
      }
    },
    [sourceId, conversationTab, onTabChange],
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
    if (!conversationTab) {
      return;
    }
    const surface = conversationTab;
    writeActiveConversation(sourceId, surface, null);
    setActiveIds((current) => ({ ...current, [surface]: null }));
    setRevisions((current) => ({
      ...current,
      [surface]: current[surface] + 1,
    }));
  }, [sourceId, conversationTab]);

  // What each tab is holding, so the reader can see it without opening the tab.
  // Inventory, never achievement: nothing counts up, and nothing is behind.
  const counts: Partial<Record<DockTab, number | null>> = {
    notes: bookNotes.notes?.length ?? null,
    review: bookDue.total,
  };

  return (
    <aside
      data-testid="reader-panel"
      data-tab={tab}
      aria-label={TAB_TITLES[tab]}
      className="sticky top-0 flex h-svh w-[26rem] flex-col overflow-y-auto border-l bg-background max-xl:fixed max-xl:inset-y-0 max-xl:right-0 max-xl:z-30 xl:shrink-0"
    >
      <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
        <div role="tablist" aria-label="Dock tabs" className="flex gap-1">
          {TABS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={tab === value}
              onClick={() => onTabChange(value)}
              className={cn(
                "rounded-md px-2 py-1 text-sm font-medium transition-colors",
                tab === value
                  ? "bg-accent text-foreground"
                  : "text-muted-foreground hover:bg-accent/50",
              )}
            >
              {label}
              <TabCount value={counts[value]} />
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

      {/* Threads belong to the conversation surfaces; Notes and Review have none. */}
      {conversationTab ? (
        <ConversationList
          sourceId={sourceId}
          csrf={csrf}
          refreshToken={listToken}
          activeConversationId={activeIds[conversationTab]}
          onResume={handleResume}
          onNew={handleNew}
          onDeleted={handleDeleted}
        />
      ) : null}

      <div className="min-h-0 flex-1 p-3">
        {tab === "ask" ? (
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
        ) : tab === "teach" ? (
          <TeachPanel
            sourceId={sourceId}
            csrf={csrf}
            revision={revisions.teach}
            onShowInBook={onShowInBook}
            onRequireAuth={onRequireAuth}
            onConversationsChanged={handleConversationsChanged}
          />
        ) : tab === "notes" ? (
          <DockNotesPanel {...bookNotes} onShowInBook={onShowInBook} />
        ) : (
          <DockReviewPanel
            {...bookDue}
            sourceId={sourceId}
            onRequireAuth={onRequireAuth}
          />
        )}
      </div>
    </aside>
  );
}
