"use client";

/**
 * One answer and the evidence under it (ANSW-07/08).
 *
 * The backend writes `[^n]` markers into the answer text at the points its
 * citations attach (AD-222), so where a claim came from is part of the answer
 * rather than a list underneath it. Here those markers become numbered marks in
 * the rendered prose, and activating one — or its chip in the row below — opens
 * that citation's passage in flow beneath the answer.
 *
 * One region, not one per mark: the answer stays readable, and checking a second
 * source swaps the passage rather than stacking another box. A marker with no
 * citation behind it stays plain text (`lib/citations`), so a dropped grounding
 * leaves prose, never a control that leads nowhere.
 *
 * The markers are plain text, which is why a restored turn renders identical
 * marks: the stored answer carries the same tokens the stream did.
 */

import { createContext, useContext, useId, useMemo, useState } from "react";

import {
  citationIndexFromHref,
  linkCitationMarkers,
  type Citation,
} from "@/app/lib/citations";
import { MessageResponse } from "@/components/ai-elements/message";

import { CitationList } from "./citations";

/**
 * What an inline mark needs to know, delivered by context rather than by props.
 *
 * The marks are rendered deep inside the memoized answer body, which only
 * re-renders when the answer *text* changes — so a mark cannot be handed the
 * current selection as a prop and stay truthful about it. Context is the one
 * channel that reaches through that memo, which is what lets a mark carry live
 * `aria-expanded` state instead of whichever value it happened to be born with.
 */
const MarkSelectionContext = createContext<{
  selected: number | null;
  passageId: string;
  toggle: (index: number) => void;
}>({ selected: null, passageId: "", toggle: () => {} });

/** One numbered mark in the prose; a second activation closes what it opened. */
function CitationMark({ index }: { index: number }) {
  const { selected, passageId, toggle } = useContext(MarkSelectionContext);
  const open = selected === index;
  return (
    <button
      type="button"
      aria-label={`Citation ${index}`}
      aria-expanded={open}
      aria-controls={open ? passageId : undefined}
      onClick={() => toggle(index)}
      className="mx-0.5 inline-flex items-baseline rounded-sm bg-secondary px-1 align-super text-[0.65rem] font-medium tabular-nums text-secondary-foreground transition-colors hover:bg-accent"
    >
      {index}
    </button>
  );
}

export function CitedAnswer({
  sourceId,
  text,
  citations,
  onShowInBook,
  trailing,
}: {
  sourceId: string;
  text: string;
  /** The turn's citations, or `null` while it has none yet (or is not-found). */
  citations: Citation[] | null;
  onShowInBook?: (anchor: string) => void;
  /** Rendered at the tail of the answer text — the Ask panel's streaming caret. */
  trailing?: React.ReactNode;
}) {
  const [selected, setSelected] = useState<number | null>(null);
  const passageId = useId();
  const markSelection = useMemo(
    () => ({
      selected,
      passageId,
      toggle: (index: number) =>
        setSelected((current) => (current === index ? null : index)),
    }),
    [selected, passageId],
  );

  // Rewriting the markers into links is what puts the marks *in* the prose: the
  // renderer parses one document, so a mark mid-sentence stays mid-sentence.
  // Citations arriving after the text is complete change this string, which is
  // also what re-renders the memoized answer body so the marks light up.
  const body = linkCitationMarkers(text, citations?.length ?? 0);

  return (
    <MarkSelectionContext.Provider value={markSelection}>
      {body ? (
        <MessageResponse
          components={{
            a({ href, children, ...props }) {
              const index = citationIndexFromHref(href);
              if (index === null) {
                // Not a mark, so it is a link the model or the book authored —
                // untrusted text either way. Keep the renderer's own hardening
                // on it: a new context, with no handle back on `window.opener`.
                return (
                  <a
                    href={href}
                    rel="noreferrer noopener"
                    target="_blank"
                    {...props}
                  >
                    {children}
                  </a>
                );
              }
              // The mark takes no props from here: the answer body is memoized on
              // its text, so anything passed down would freeze at the value it had
              // when the body last rendered. It reads the selection from context.
              return <CitationMark index={index} />;
            },
          }}
        >
          {body}
        </MessageResponse>
      ) : null}
      {trailing}
      {citations ? (
        <CitationList
          sourceId={sourceId}
          citations={citations}
          onShowInBook={onShowInBook}
          selected={selected}
          onSelect={setSelected}
          passageId={passageId}
        />
      ) : null}
    </MarkSelectionContext.Provider>
  );
}
