"use client";

/**
 * Sources panel (T8, SRC-11).
 *
 * Resolves auth state via `/api/auth/me` (through the proxy), lists the user's
 * sources, and uploads an EPUB — all same-origin, never cross-origin. The CSRF
 * token read on mount is reused for the state-changing upload (AD-007).
 *
 * `onRequireAuth` fires when the user is unauthenticated so the caller can do a
 * UX-only redirect. That redirect is convenience ONLY, NOT the security
 * boundary — FastAPI enforces auth and per-user ownership on every `/api/sources*`
 * call regardless of client-side routing (FR-AUTH-007, ADR-017).
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { fetchAuthState, type AuthState } from "@/app/lib/auth";
import {
  fetchSourceStructure,
  listSources,
  startIngestion,
  uploadSource,
  type SourceStructure,
  type StructureSection,
  type SourceSummary,
} from "@/app/lib/sources";

/** Book metadata as one line, filling in readable placeholders for nulls. */
function metadataLine(structure: SourceStructure): string {
  const title = structure.title ?? "Untitled";
  const authors =
    structure.authors.length > 0
      ? structure.authors.join(", ")
      : "Unknown author";
  const language = structure.language ?? "Unknown language";
  return `${title} · ${authors} · ${language}`;
}

/** Recursive TOC tree: one nested <ul> level per depth, titles as leaves. */
function SectionTree({ sections }: { sections: StructureSection[] }) {
  return (
    <ul>
      {sections.map((section, index) => (
        <li key={`${section.anchor}-${index}`}>
          <span>{section.title}</span>
          {section.children.length > 0 ? (
            <SectionTree sections={section.children} />
          ) : null}
        </li>
      ))}
    </ul>
  );
}

export function SourcesPanel({
  onRequireAuth,
}: {
  onRequireAuth?: () => void;
}) {
  const [state, setState] = useState<AuthState | null>(null);
  const [sources, setSources] = useState<SourceSummary[] | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // Id of the source whose ingestion start is currently in flight (one at a
  // time), so we can disable just that row's button and block a double-start.
  const [startingId, setStartingId] = useState<string | null>(null);
  // Id of the source whose structure fetch is in flight, so we disable just
  // that row's toggle; and the loaded structures keyed by source id — a present
  // entry means the row's panel is expanded (CORP-12/13).
  const [structureLoadingId, setStructureLoadingId] = useState<string | null>(
    null,
  );
  const [structures, setStructures] = useState<Record<string, SourceStructure>>(
    {},
  );

  const load = useCallback(async () => {
    const next = await fetchAuthState();
    setState(next);
    // UX-only redirect for unauthenticated users (NOT the security boundary).
    if (!next.authenticated) {
      onRequireAuth?.();
      return;
    }
    setSources(await listSources());
  }, [onRequireAuth]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleUpload(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!state?.authenticated) {
      return;
    }
    if (!file) {
      setError("Choose an EPUB file to upload.");
      return;
    }
    setSubmitting(true);
    try {
      const source = await uploadSource(file, title, state.user.csrf_token);
      setSources((prev) => [source, ...(prev ?? [])]);
      setFile(null);
      setTitle("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleStart(source: SourceSummary) {
    setError(null);
    if (!state?.authenticated) {
      return;
    }
    // SPEC_DEVIATION: the design says "optimistically set the row to processing";
    // we flip to processing only on success and keep the row `uploaded` (button
    // mounted + disabled) during the request. Reason: the "Start ingestion"
    // button renders only for `uploaded` rows, so a pre-await optimistic flip
    // would unmount the button, making the required "button disabled while
    // submitting" state unobservable. End states match spec AC3 exactly
    // (processing on success; error surfaced + not processing on failure).
    setStartingId(source.id);
    try {
      await startIngestion(source.id, state.user.csrf_token);
      setSources((prev) =>
        (prev ?? []).map((s) =>
          s.id === source.id ? { ...s, status: "processing" } : s,
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start ingestion.");
    } finally {
      setStartingId(null);
    }
  }

  async function handleStructure(source: SourceSummary) {
    setError(null);
    // Toggle: an already-open panel collapses, dropping its content.
    if (structures[source.id]) {
      setStructures((prev) => {
        const next = { ...prev };
        delete next[source.id];
        return next;
      });
      return;
    }
    setStructureLoadingId(source.id);
    try {
      const structure = await fetchSourceStructure(source.id);
      setStructures((prev) => ({ ...prev, [source.id]: structure }));
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not load the book structure.",
      );
    } finally {
      setStructureLoadingId(null);
    }
  }

  if (state === null) {
    return <p>Loading…</p>;
  }
  if (!state.authenticated) {
    return <p>You are signed out.</p>;
  }

  return (
    <section aria-label="sources">
      <form onSubmit={handleUpload} aria-label="upload source">
        <label>
          Title
          <input
            type="text"
            name="title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
          />
        </label>
        <label>
          EPUB file
          <input
            type="file"
            name="file"
            accept=".epub,application/epub+zip"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>
        {error ? <p role="alert">{error}</p> : null}
        <button type="submit" disabled={submitting}>
          {submitting ? "Uploading…" : "Upload"}
        </button>
      </form>
      {sources === null ? (
        <p>Loading your sources…</p>
      ) : sources.length === 0 ? (
        <p>No sources yet.</p>
      ) : (
        <ul>
          {sources.map((source) => (
            <li key={source.id}>
              <span>{source.title}</span>
              <span data-testid={`status-${source.id}`}>{source.status}</span>
              {source.status === "uploaded" ? (
                <button
                  type="button"
                  onClick={() => void handleStart(source)}
                  disabled={startingId === source.id}
                >
                  {startingId === source.id ? "Starting…" : "Start ingestion"}
                </button>
              ) : null}
              {source.status === "ready" ? (
                <button
                  type="button"
                  onClick={() => void handleStructure(source)}
                  disabled={structureLoadingId === source.id}
                >
                  {structureLoadingId === source.id
                    ? "Loading…"
                    : structures[source.id]
                      ? "Hide structure"
                      : "View structure"}
                </button>
              ) : null}
              {source.status === "ready" ? (
                <Link href={`/sources/${source.id}/ask`}>Ask</Link>
              ) : null}
              {structures[source.id] ? (
                <div data-testid={`structure-${source.id}`}>
                  <p>{metadataLine(structures[source.id])}</p>
                  <SectionTree sections={structures[source.id].sections} />
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
