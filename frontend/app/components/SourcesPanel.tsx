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

import { useCallback, useEffect, useState } from "react";

import { fetchAuthState, type AuthState } from "@/app/lib/auth";
import { listSources, uploadSource, type SourceSummary } from "@/app/lib/sources";

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
            <li key={source.id}>{source.title}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
