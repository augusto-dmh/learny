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

import { useState } from "react";

import {
  citationIndexFromHref,
  linkCitationMarkers,
  type Citation,
} from "@/app/lib/citations";
import { MessageResponse } from "@/components/ai-elements/message";

import { CitationList } from "./citations";

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

  // Rewriting the markers into links is what puts the marks *in* the prose: the
  // renderer parses one document, so a mark mid-sentence stays mid-sentence.
  // Citations arriving after the text is complete change this string, which is
  // also what re-renders the memoized answer body so the marks light up.
  const body = linkCitationMarkers(text, citations?.length ?? 0);

  return (
    <>
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
              // A mark renders from its number alone — never from which citation
              // is open — because the answer body is memoized on its text and
              // would not re-render to show a changed selection.
              return (
                <button
                  type="button"
                  aria-label={`Citation ${index}`}
                  onClick={() =>
                    setSelected((current) =>
                      current === index ? null : index,
                    )
                  }
                  className="mx-0.5 inline-flex items-baseline rounded-sm bg-secondary px-1 align-super text-[0.65rem] font-medium tabular-nums text-secondary-foreground transition-colors hover:bg-accent"
                >
                  {index}
                </button>
              );
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
        />
      ) : null}
    </>
  );
}
