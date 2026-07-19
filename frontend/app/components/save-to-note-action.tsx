"use client";

/**
 * "Save to note" on a completed, cited answer (RA-20/21). Renders only where the
 * caller has already established the answer has ≥1 citation and is not not-found
 * (RA-22). Delegates the anchored-capture / plain-note fallback to
 * `saveAnswerAsNote`; a save failure surfaces an inline message (no retry loop —
 * the button simply stays available for a manual retry).
 *
 * Shared by both reader panels (Ask and Teach), so it lives in its own module
 * rather than as a secondary export of either panel.
 */

import { useCallback, useState } from "react";

import { saveAnswerAsNote } from "@/app/lib/answer-notes";
import { type Citation } from "@/app/lib/questions";
import { Button } from "@/components/ui/button";

export function SaveToNoteAction({
  sourceId,
  question,
  answerText,
  citations,
  csrf,
}: {
  sourceId: string;
  question: string;
  answerText: string;
  citations: Citation[];
  csrf: string;
}) {
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">(
    "idle",
  );

  const handleSave = useCallback(async () => {
    setState("saving");
    try {
      await saveAnswerAsNote({
        sourceId,
        question,
        answerText,
        citations,
        csrfToken: csrf,
      });
      setState("saved");
    } catch {
      setState("error");
    }
  }, [sourceId, question, answerText, citations, csrf]);

  if (state === "saved") {
    return (
      <p data-testid="save-note-status" className="text-xs text-muted-foreground">
        Saved to notes.
      </p>
    );
  }

  return (
    <div className="space-y-1">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={() => void handleSave()}
        disabled={state === "saving"}
      >
        {state === "saving" ? "Saving…" : "Save to note"}
      </Button>
      {state === "error" ? (
        <p
          role="alert"
          data-testid="save-note-error"
          className="text-xs text-destructive"
        >
          Could not save this answer as a note. Please try again.
        </p>
      ) : null}
    </div>
  );
}
