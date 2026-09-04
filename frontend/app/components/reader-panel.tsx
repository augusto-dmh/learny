"use client";

/**
 * The reader side panel (RA-01..03/06): a fixed-width right-hand column that hosts
 * the book's four working surfaces beside the chapter so studying never leaves the
 * page.
 *
 * The shell owns the tab strip (Chat | Notes | Review), the close control, and
 * this book's conversation list. Open state and the active tab are pure URL
 * state driven by `?panel=`, so the parent renders the panel only when a tab is
 * active — closing it simply drops the query param and restores full reading
 * width, and reading stays non-modal underneath.
 *
 * Chat is the only strip tab that holds a conversation. `PanelMode` (`ask` |
 * `teach`) is the composer arming — Answer vs Tutor — and still keys the
 * per-surface `activeIds`/`revisions` maps. `DockTab` is what the strip speaks.
 * `?panel=ask` / `?panel=teach` / `?panel=chat` all open Chat; the aliases arm
 * Answer vs Tutor. The conversation list therefore renders on Chat only.
 *
 * The conversation list is deliberately mode-agnostic: one book has one set of
 * threads. Which composer continues a given thread follows from the mode its
 * turns were answered in, so resume arms Answer or Tutor rather than asking the
 * reader to guess which mode their thread is behind.
 */

import { X } from "lucide-react";
import { type ReactNode, useCallback, useEffect, useState } from "react";

import {
  readActiveConversation,
  writeActiveConversation,
} from "@/app/lib/active-conversation";
import { type ConversationSummaryView } from "@/app/lib/conversations";
import { type PendingPanelRequest } from "@/app/lib/panel";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { useBelowLg } from "@/hooks/use-below-lg";
import { readControlMinStyle } from "@/app/lib/read-control-size";
import { cn } from "@/lib/utils";

import { AskPanel } from "./ask-panel";
import { ConversationList } from "./conversation-list";
import { DockNotesPanel, useBookNotes } from "./dock-notes-panel";
import { DockReviewPanel, useDueCount } from "./dock-review-panel";
import { TeachPanel } from "./teach-panel";

/** A composer mode that holds a conversation, and so has per-surface thread state. */
export type PanelMode = "ask" | "teach";

/** Every tab in the dock's strip. */
export type DockTab = "chat" | "notes" | "review";

/** Every value `?panel=` may write: strip tabs plus Ask/Teach aliases. */
export type PanelQuery = DockTab | PanelMode;

const TABS: { value: DockTab; label: string }[] = [
  { value: "chat", label: "Chat" },
  { value: "notes", label: "Notes" },
  { value: "review", label: "Review" },
];

const TAB_TITLES: Record<DockTab, string> = {
  chat: "Chat panel",
  notes: "Notes panel",
  review: "Review panel",
};

const LAST_CHAT_MODE_KEY = "learny.chat-mode.v1";

/** The last Answer/Tutor arming for this book, or null when none has been used. */
export function readLastChatMode(sourceId: string): PanelMode | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = localStorage.getItem(LAST_CHAT_MODE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const value = parsed[sourceId];
    return value === "ask" || value === "teach" ? value : null;
  } catch {
    return null;
  }
}

/** Remember which composer Chat last armed for this book. */
export function writeLastChatMode(sourceId: string, mode: PanelMode): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    const raw = localStorage.getItem(LAST_CHAT_MODE_KEY);
    const parsed =
      raw === null ? {} : (JSON.parse(raw) as Record<string, unknown>);
    const next: Record<string, unknown> =
      parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)
        ? parsed
        : {};
    next[sourceId] = mode;
    localStorage.setItem(LAST_CHAT_MODE_KEY, JSON.stringify(next));
  } catch {
    // Private mode: last-used is simply not remembered across reloads.
  }
}

/**
 * Whether a tab is the conversation surface — the guard that keeps the list off
 * Notes and Review.
 */
export function isConversationTab(tab: DockTab): tab is "chat" {
  return tab === "chat";
}

/**
 * The strip tab for a `?panel=` value, or null when it names nothing the dock
 * has. Ask, Teach, and Chat all open the Chat tab (TUTOR-27/28).
 */
export function dockTabFromParam(value: string | null): DockTab | null {
  if (value === "ask" || value === "teach" || value === "chat") {
    return "chat";
  }
  if (value === "notes" || value === "review") {
    return value;
  }
  return null;
}

/**
 * Which composer Chat arms from a `?panel=` value. Aliases win over last-used;
 * `chat` (or an omitted param) uses last-used, defaulting to Answer (TUTOR-28).
 */
export function composerModeFromParam(
  value: string | null | undefined,
  lastUsed: PanelMode | null,
): PanelMode {
  if (value === "teach") {
    return "teach";
  }
  if (value === "ask") {
    return "ask";
  }
  return lastUsed ?? "ask";
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
  panelParam = null,
  onTabChange,
  onClose,
  pendingRequest,
  onPendingConsumed,
  onShowInBook,
  onRequireAuth,
  notesToken = 0,
  currentAnchor = null,
}: {
  sourceId: string;
  csrf: string;
  tab: DockTab;
  /** Raw `?panel=` value so Chat can arm Answer vs Tutor from aliases. */
  panelParam?: string | null;
  onTabChange: (tab: PanelQuery) => void;
  onClose: () => void;
  pendingRequest?: PendingPanelRequest | null;
  onPendingConsumed?: () => void;
  onShowInBook?: (anchor: string) => void;
  onRequireAuth?: () => void;
  /** Bumped by the reader when a passage is captured, so the Notes tab re-reads. */
  notesToken?: number;
  /** Section currently on screen; Tutor Start defaults the picker to it. */
  currentAnchor?: string | null;
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

  const [lastUsed, setLastUsed] = useState<PanelMode | null>(() =>
    readLastChatMode(sourceId),
  );
  const [armedOverride, setArmedOverride] = useState<PanelMode | null>(null);

  useEffect(() => {
    setLastUsed(readLastChatMode(sourceId));
    setArmedOverride(null);
  }, [sourceId]);

  useEffect(() => {
    setArmedOverride(null);
  }, [panelParam]);

  useEffect(() => {
    if (panelParam === "ask" || panelParam === "teach") {
      writeLastChatMode(sourceId, panelParam);
      setLastUsed(panelParam);
    }
  }, [panelParam, sourceId]);

  const armedMode: PanelMode =
    armedOverride ?? composerModeFromParam(panelParam, lastUsed);

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
      const target = panelFor(summary, armedMode);
      writeActiveConversation(sourceId, target, summary.id);
      writeLastChatMode(sourceId, target);
      setLastUsed(target);
      setArmedOverride(target);
      setActiveIds((current) => ({ ...current, [target]: summary.id }));
      setRevisions((current) => ({
        ...current,
        [target]: current[target] + 1,
      }));
      if (target !== armedMode) {
        onTabChange(target);
      }
    },
    [sourceId, conversationTab, armedMode, onTabChange],
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
    const surface = armedMode;
    writeActiveConversation(sourceId, surface, null);
    setActiveIds((current) => ({ ...current, [surface]: null }));
    setRevisions((current) => ({
      ...current,
      [surface]: current[surface] + 1,
    }));
  }, [sourceId, conversationTab, armedMode]);

  const handleAskAboutThis = useCallback(() => {
    writeActiveConversation(sourceId, "ask", null);
    writeLastChatMode(sourceId, "ask");
    setLastUsed("ask");
    setArmedOverride("ask");
    setActiveIds((current) => ({ ...current, ask: null }));
    setRevisions((current) => ({ ...current, ask: current.ask + 1 }));
    onTabChange("ask");
  }, [sourceId, onTabChange]);

  // What each tab is holding, so the reader can see it without opening the tab.
  // Inventory, never achievement: nothing counts up, and nothing is behind.
  const counts: Partial<Record<DockTab, number | null>> = {
    notes: bookNotes.notes?.length ?? null,
    review: bookDue.total,
  };

  const belowLg = useBelowLg();

  const body = (
    <>
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
        {belowLg ? null : (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="Close panel"
            onClick={onClose}
          >
            <X />
          </Button>
        )}
      </div>

      {/* Threads belong to the conversation surfaces; Notes and Review have none. */}
      {conversationTab ? (
        <ConversationList
          sourceId={sourceId}
          csrf={csrf}
          refreshToken={listToken}
          activeConversationId={activeIds[armedMode]}
          onResume={handleResume}
          onNew={handleNew}
          onDeleted={handleDeleted}
        />
      ) : null}

      <div className="min-h-0 flex-1 p-3">
        {tab === "chat" && armedMode === "ask" ? (
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
        ) : tab === "chat" ? (
          <TeachPanel
            sourceId={sourceId}
            csrf={csrf}
            revision={revisions.teach}
            currentAnchor={currentAnchor}
            onShowInBook={onShowInBook}
            onRequireAuth={onRequireAuth}
            onConversationsChanged={handleConversationsChanged}
            onAskAboutThis={handleAskAboutThis}
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
    </>
  );

  if (belowLg) {
    return (
      <Sheet
        open
        onOpenChange={(open) => {
          if (!open) {
            onClose();
          }
        }}
      >
        <SheetContent
          side="bottom"
          showCloseButton={false}
          className="max-h-[85svh] gap-0 p-0 motion-reduce:animate-none motion-reduce:transition-none"
        >
          <SheetHeader className="sr-only">
            <SheetTitle>{TAB_TITLES[tab]}</SheetTitle>
            <SheetDescription>
              Study surfaces for this book, as a bottom sheet.
            </SheetDescription>
          </SheetHeader>
          <Button
            type="button"
            variant="ghost"
            className="absolute top-3 right-3 z-10 size-11"
            style={readControlMinStyle}
            aria-label="Close"
            onClick={onClose}
          >
            <X />
          </Button>
          <ReaderPanelFrame tab={tab} className="flex max-h-[85svh] min-h-0 flex-col overflow-y-auto bg-background">
            {body}
          </ReaderPanelFrame>
        </SheetContent>
      </Sheet>
    );
  }

  return (
    <ReaderPanelFrame
      tab={tab}
      className="sticky top-0 flex h-svh w-[26rem] flex-col overflow-y-auto border-l bg-background max-xl:fixed max-xl:inset-y-0 max-xl:right-0 max-xl:z-30 xl:shrink-0"
    >
      {body}
    </ReaderPanelFrame>
  );
}

function ReaderPanelFrame({
  tab,
  className,
  children,
}: {
  tab: DockTab;
  className: string;
  children: ReactNode;
}) {
  return (
    <aside
      data-testid="reader-panel"
      data-tab={tab}
      aria-label={TAB_TITLES[tab]}
      className={className}
    >
      {children}
    </aside>
  );
}
