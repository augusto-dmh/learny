"use client";

/**
 * The two states a turn shows before it has an answer (ANSW-01/02).
 *
 * Asking a book a question used to be dead air: the request went out, retrieval
 * and the model's thinking happened off-screen, and the panel showed nothing
 * until the first token. Both are now phases the reader can see — the backend
 * announces the search before it runs and streams the model's thinking as it
 * happens, and these two components are how the panels show them.
 *
 * Reasoning is transient (AD-220): it streams, folds away when the answer starts,
 * and is gone on a restored thread. A turn that carried no thinking renders no
 * region at all — the caller keys that off empty reasoning text, so there is
 * never an empty shell to open.
 */

import { ChevronDownIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Shimmer } from "@/components/ai-elements/shimmer";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

/**
 * The in-flight turn's phase line: the panel is waiting on the backend's search
 * for evidence and has nothing else to show yet.
 *
 * It stands in for the whole gap between submitting and the first reasoning or
 * text part — including the moment before the `searching` frame arrives, which is
 * the request still in flight toward the same search.
 */
export function AnswerPhaseIndicator() {
  return (
    <p role="status" className="text-sm">
      <Shimmer as="span">Searching the book…</Shimmer>
    </p>
  );
}

/**
 * The model's streamed thinking, in a region that is open while it thinks and
 * folds itself away once the answer starts — reopenable for as long as the turn
 * is on screen.
 *
 * `thinking` is the caller's answer to "is this reasoning still the live phase":
 * true while the turn is streaming and no answer text has arrived. A turn that is
 * already finished (or restored) starts collapsed, so a completed thread reads as
 * answers with their thinking tucked behind a line, not as a wall of scratchpad.
 */
export function ReasoningRegion({
  text,
  thinking,
}: {
  text: string;
  thinking: boolean;
}) {
  const [open, setOpen] = useState(thinking);

  // Collapse exactly once, on the transition out of thinking (the first answer
  // token), and never again — so a reader who reopens it keeps it open.
  const wasThinking = useRef(thinking);
  useEffect(() => {
    if (wasThinking.current && !thinking) {
      setOpen(false);
    }
    wasThinking.current = thinking;
  }, [thinking]);

  return (
    <section aria-label="reasoning" className="mb-2">
      <Collapsible open={open} onOpenChange={setOpen}>
        <CollapsibleTrigger className="group inline-flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground">
          {thinking ? (
            <Shimmer as="span" className="text-xs">
              Thinking…
            </Shimmer>
          ) : (
            <span>Thought process</span>
          )}
          <ChevronDownIcon
            aria-hidden
            className="size-3 transition-transform group-data-[state=open]:rotate-180"
          />
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="mt-1.5 max-h-40 overflow-y-auto whitespace-pre-wrap border-l-2 border-muted pl-3 text-xs text-muted-foreground">
            {text}
          </div>
        </CollapsibleContent>
      </Collapsible>
    </section>
  );
}
