"use client";

/**
 * Section reader (FE-15/FE-17) — renders one cited section in context.
 *
 * Reads the section anchor from the URL (`?anchor=`, auto-decoded by
 * `useSearchParams`), resolves auth through `/api/auth/me`, then fetches the
 * section via `getSection` and renders its markdown with the same renderer the
 * streamed answers use (`MessageResponse`, a memoized Streamdown — raw HTML in
 * the markdown stays inert, never injected as live DOM). The section heading is
 * scrolled into view and transiently highlighted so a citation lands on its
 * passage.
 *
 * States: no anchor → a pick-a-section empty state (the sidebar tree is the
 * entry); unknown anchor → a readable not-found state with a way back; any other
 * load failure → a readable error. A 401 redirects via `onRequireAuth` — a
 * UX-only convenience, NOT the security boundary: FastAPI enforces auth and
 * ownership on `/api/sources/{id}/section` regardless of client-side routing
 * (FR-AUTH-007, ADR-017).
 */

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { fetchAuthState } from "@/app/lib/auth";
import { getSection, type SectionView } from "@/app/lib/sections";
import { MessageResponse } from "@/components/ai-elements/message";

export function SectionReader({
  sourceId,
  onRequireAuth,
}: {
  sourceId: string;
  onRequireAuth?: () => void;
}) {
  // `useSearchParams().get()` decodes the percent-encoded anchor built by the
  // citation popover and sidebar tree links, closing the round-trip.
  const anchor = useSearchParams().get("anchor");

  if (!anchor) {
    return (
      <div className="mx-auto max-w-2xl py-12 text-center text-muted-foreground">
        <p>Pick a section from the sidebar to start reading.</p>
      </div>
    );
  }

  return (
    <SectionContent
      sourceId={sourceId}
      anchor={anchor}
      onRequireAuth={onRequireAuth}
    />
  );
}

type LoadState =
  | { kind: "loading" }
  | { kind: "signed-out" }
  | { kind: "not-found" }
  | { kind: "error"; message: string }
  | { kind: "found"; section: SectionView };

/** Resolve auth, fetch the section by anchor, and render the resolved state. */
function SectionContent({
  sourceId,
  anchor,
  onRequireAuth,
}: {
  sourceId: string;
  anchor: string;
  onRequireAuth?: () => void;
}) {
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    let active = true;
    setState({ kind: "loading" });
    void (async () => {
      const auth = await fetchAuthState();
      if (!active) {
        return;
      }
      if (!auth.authenticated) {
        setState({ kind: "signed-out" });
        onRequireAuth?.();
        return;
      }
      try {
        const result = await getSection(sourceId, anchor);
        if (!active) {
          return;
        }
        setState(
          result.status === "not_found"
            ? { kind: "not-found" }
            : { kind: "found", section: result.section },
        );
      } catch (err) {
        if (!active) {
          return;
        }
        setState({
          kind: "error",
          message:
            err instanceof Error ? err.message : "Could not load that section.",
        });
      }
    })();
    return () => {
      active = false;
    };
  }, [sourceId, anchor, onRequireAuth]);

  if (state.kind === "loading") {
    return <p className="text-muted-foreground">Loading…</p>;
  }
  if (state.kind === "signed-out") {
    return <p className="text-muted-foreground">You are signed out.</p>;
  }
  if (state.kind === "not-found") {
    return (
      <div className="mx-auto max-w-2xl py-12 text-center">
        <p className="text-muted-foreground">
          We couldn&apos;t find that section.
        </p>
        <Link
          href="/sources"
          className="text-primary underline-offset-4 hover:underline"
        >
          Back to your library
        </Link>
      </div>
    );
  }
  if (state.kind === "error") {
    return (
      <div className="mx-auto max-w-2xl py-12">
        <p role="alert" className="text-destructive">
          {state.message}
        </p>
      </div>
    );
  }
  return <FoundSection section={state.section} />;
}

/** The resolved section: highlighted heading + breadcrumb + rendered markdown. */
function FoundSection({ section }: { section: SectionView }) {
  const titleRef = useRef<HTMLDivElement>(null);
  const [highlighted, setHighlighted] = useState(true);

  useEffect(() => {
    titleRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    const timer = setTimeout(() => setHighlighted(false), 2000);
    return () => clearTimeout(timer);
  }, []);

  const breadcrumb = section.section_path.join(" › ");

  return (
    <article className="mx-auto max-w-2xl py-6">
      <div
        ref={titleRef}
        data-testid="section-title"
        data-highlight={highlighted ? "on" : "off"}
        className="scroll-mt-16 rounded-md px-2 py-1 transition-colors duration-500 data-[highlight=on]:bg-accent"
      >
        {breadcrumb ? (
          <p className="text-xs text-muted-foreground">{breadcrumb}</p>
        ) : null}
        <h1 className="text-2xl font-semibold">{section.title}</h1>
      </div>
      <div className="prose prose-sm mt-4 max-w-none dark:prose-invert">
        <MessageResponse>{section.markdown}</MessageResponse>
      </div>
    </article>
  );
}
