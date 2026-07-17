"use client";

/**
 * Library screen (FE-20/FE-21) — replaces the unstyled SourcesPanel.
 *
 * Resolves auth state via `/api/auth/me` (through the proxy), lists the user's
 * sources as cards with a status badge, uploads an EPUB (unchanged multipart
 * contract), links ready books to Ask/Teach/Read, and — for a failed source —
 * surfaces the latest ingestion event message alongside a restart control. All
 * same-origin; the CSRF token read on mount is reused for the state-changing
 * upload and (re)start calls (AD-007).
 *
 * `onRequireAuth` fires when the user is unauthenticated so the caller can do a
 * UX-only redirect. That redirect is convenience ONLY, NOT the security
 * boundary — FastAPI enforces auth and per-user ownership on every
 * `/api/sources*` call regardless of client-side routing (FR-AUTH-007, ADR-017).
 */

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { fetchAuthState, type AuthState } from "@/app/lib/auth";
import { getIngestion } from "@/app/lib/ingestion";
import {
  listSources,
  startIngestion,
  uploadSource,
  type SourceSummary,
} from "@/app/lib/sources";
import { statusVariant } from "@/app/lib/status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";

import { useIngestionPolling } from "./use-ingestion-polling";

export function LibraryScreen({
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
  // Id of the source whose ingestion (re)start is in flight, so we disable just
  // that row's button and block a double-start.
  const [startingId, setStartingId] = useState<string | null>(null);
  // Latest ingestion event message per failed source (FE-20).
  const [failureMessages, setFailureMessages] = useState<
    Record<string, string>
  >({});
  // Source ids whose failure message we have already fetched, so the effect
  // never re-requests (kept in a ref so it is not a render dependency).
  const fetchedFailures = useRef<Set<string>>(new Set());

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

  // Patch one source's projected status in place (FE-19 badge update).
  const patchStatus = useCallback((sourceId: string, status: string) => {
    setSources((prev) =>
      (prev ?? []).map((s) => (s.id === sourceId ? { ...s, status } : s)),
    );
  }, []);

  useIngestionPolling(sources, patchStatus);

  // For each failed source (on load or after a poll flips one to failed), fetch
  // its ingestion once and cache the latest event message for display.
  useEffect(() => {
    if (!sources) {
      return;
    }
    for (const source of sources) {
      if (source.status !== "failed" || fetchedFailures.current.has(source.id)) {
        continue;
      }
      fetchedFailures.current.add(source.id);
      getIngestion(source.id)
        .then((ingestion) => {
          const latest = [...ingestion.events]
            .reverse()
            .find((event) => event.message)?.message;
          const message = latest ?? ingestion.error ?? "Ingestion failed.";
          setFailureMessages((prev) => ({ ...prev, [source.id]: message }));
        })
        .catch(() => {
          // Leave the message absent; the restart control still renders.
        });
    }
  }, [sources]);

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
    setStartingId(source.id);
    try {
      await startIngestion(source.id, state.user.csrf_token);
      // Restarting a failed source clears its cached message so it can be
      // re-fetched if it fails again.
      fetchedFailures.current.delete(source.id);
      setFailureMessages((prev) => {
        const next = { ...prev };
        delete next[source.id];
        return next;
      });
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

  if (state === null) {
    return <p className="text-muted-foreground">Loading…</p>;
  }
  if (!state.authenticated) {
    return <p className="text-muted-foreground">You are signed out.</p>;
  }

  return (
    <section aria-label="library" className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Add a book</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleUpload} aria-label="upload source" className="space-y-4">
            <div className="space-y-1.5">
              <label htmlFor="upload-title" className="text-sm font-medium">
                Title
              </label>
              <Input
                id="upload-title"
                type="text"
                name="title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="upload-file" className="text-sm font-medium">
                EPUB file
              </label>
              <Input
                id="upload-file"
                type="file"
                name="file"
                accept=".epub,application/epub+zip"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </div>
            {error ? (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            ) : null}
            <Button type="submit" disabled={submitting}>
              {submitting ? "Uploading…" : "Upload"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {sources === null ? (
        <p className="text-muted-foreground">Loading your sources…</p>
      ) : sources.length === 0 ? (
        <p className="text-muted-foreground">No sources yet.</p>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2">
          {sources.map((source) => (
            <li key={source.id}>
              <Card>
                <CardHeader className="flex flex-row items-center justify-between gap-2">
                  <CardTitle className="text-base">{source.title}</CardTitle>
                  <Badge
                    variant={statusVariant(source.status)}
                    data-testid={`status-${source.id}`}
                  >
                    {source.status}
                  </Badge>
                </CardHeader>
                <CardContent className="space-y-3">
                  {source.status === "ready" ? (
                    <div className="flex gap-4 text-sm">
                      <Link
                        href={`/sources/${source.id}/ask`}
                        className="text-primary underline-offset-4 hover:underline"
                      >
                        Ask
                      </Link>
                      <Link
                        href={`/sources/${source.id}/teach`}
                        className="text-primary underline-offset-4 hover:underline"
                      >
                        Teach
                      </Link>
                      <Link
                        href={`/sources/${source.id}/read`}
                        className="text-primary underline-offset-4 hover:underline"
                      >
                        Read
                      </Link>
                    </div>
                  ) : null}
                  {source.status === "uploaded" ? (
                    <Button
                      type="button"
                      size="sm"
                      onClick={() => void handleStart(source)}
                      disabled={startingId === source.id}
                    >
                      {startingId === source.id ? "Starting…" : "Start ingestion"}
                    </Button>
                  ) : null}
                  {source.status === "failed" ? (
                    <div className="space-y-2">
                      {failureMessages[source.id] ? (
                        <p
                          data-testid={`failure-${source.id}`}
                          className="text-sm text-destructive"
                        >
                          {failureMessages[source.id]}
                        </p>
                      ) : null}
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => void handleStart(source)}
                        disabled={startingId === source.id}
                      >
                        {startingId === source.id
                          ? "Restarting…"
                          : "Restart ingestion"}
                      </Button>
                    </div>
                  ) : null}
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
