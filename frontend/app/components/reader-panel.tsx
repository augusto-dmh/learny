"use client";

/**
 * The reader side panel (RA-01..03/06): a fixed-width right-hand column that hosts
 * the Ask and Teach modes beside the chapter so studying never leaves the page.
 *
 * This shell owns the mode switch (an Ask | Teach segmented control) and the
 * close control, and renders the active mode's body — `AskPanel` (ported) or the
 * Teach placeholder (ported in a later task). Open state and mode are pure URL
 * state driven by `?panel=`, so the parent renders the panel only when a mode is
 * active — closing it simply drops the query param and restores full reading
 * width, and reading stays non-modal underneath.
 */

import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { AskPanel, type PendingPanelRequest } from "./ask-panel";
import { TeachPanel } from "./teach-panel";

export type PanelMode = "ask" | "teach";

const MODES: { value: PanelMode; label: string }[] = [
  { value: "ask", label: "Ask" },
  { value: "teach", label: "Teach" },
];

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
      <div className="min-h-0 flex-1 p-3">
        {mode === "ask" ? (
          <AskPanel
            sourceId={sourceId}
            csrf={csrf}
            pendingRequest={pendingRequest}
            onPendingConsumed={onPendingConsumed}
            onRequireAuth={onRequireAuth}
          />
        ) : (
          <TeachPanel
            sourceId={sourceId}
            csrf={csrf}
            onShowInBook={onShowInBook}
            onRequireAuth={onRequireAuth}
          />
        )}
      </div>
    </aside>
  );
}
