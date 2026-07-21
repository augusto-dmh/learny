"use client";

/**
 * Library screen (FE-20/FE-21) — replaces the unstyled SourcesPanel.
 *
 * Resolves auth state via `/api/auth/me` (through the proxy), lists the user's
 * sources as cards with a status badge, uploads an EPUB (unchanged multipart
 * contract), links ready books to Ask/Teach/Read (with a confirm-gated
 * re-ingest control that rebuilds the corpus, e.g. after an embedding-provider
 * switch, ADR-0019), and — for a failed source — surfaces the latest ingestion
 * event message alongside a restart control. All
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
  generateDeck,
  getQuizOverview,
  quizExportUrl,
  type QuizOverview,
} from "@/app/lib/quiz";
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
import { Spinner } from "@/components/ui/spinner";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

import { useIngestionPolling } from "./use-ingestion-polling";
import { useQuizDeckPolling } from "./use-quiz-deck-polling";

/**
 * Quiz-deck controls for one ready source (QUIZ-20). Loads the source's quiz
 * overview once; a load failure leaves the row's reading actions intact and
 * simply shows no quiz controls. Generating a deck starts a job and polls the
 * overview every 3s until the job goes terminal (stopping on unmount). A failed
 * job surfaces its error with the generate button as a retry; a finished deck
 * shows item + due counts, a "source changed" badge when items went stale or
 * orphaned after a re-ingest, a per-source Review link when anything is due, and
 * an Anki export link.
 */
function QuizDeckControls({
  sourceId,
  csrfToken,
}: {
  sourceId: string;
  csrfToken: string;
}) {
  const [overview, setOverview] = useState<QuizOverview | null>(null);
  const [generating, setGenerating] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  // Load the overview once; on failure the controls stay hidden (the card
  // degrades to its reading actions rather than crashing).
  useEffect(() => {
    let active = true;
    getQuizOverview(sourceId)
      .then((next) => {
        if (active) setOverview(next);
      })
      .catch(() => {
        // No quiz controls until the overview is known.
      });
    return () => {
      active = false;
    };
  }, [sourceId]);

  const job = overview?.latest_job ?? null;
  const jobActive = job?.status === "queued" || job?.status === "running";

  // While a deck job is in flight, poll the overview every 3s (stopping when it
  // goes terminal or this row unmounts, AD-070).
  useQuizDeckPolling(sourceId, jobActive, setOverview);

  async function handleGenerate() {
    setActionError(null);
    setGenerating(true);
    try {
      const next = await generateDeck(sourceId, csrfToken);
      // Reflect the queued job at once so polling starts on this render.
      setOverview((prev) => ({
        items: prev?.items ?? [],
        counts_by_status: prev?.counts_by_status ?? {},
        due_count: prev?.due_count ?? 0,
        latest_job: next,
      }));
    } catch (err) {
      setActionError(
        err instanceof Error
          ? err.message
          : "Could not start quiz deck generation.",
      );
    } finally {
      setGenerating(false);
    }
  }

  if (overview === null) {
    return null;
  }

  const { items, due_count: due, counts_by_status: counts } = overview;
  const changed = (counts.stale ?? 0) + (counts.orphaned ?? 0);

  return (
    <div className="space-y-2 border-t pt-3" data-testid={`quiz-${sourceId}`}>
      {jobActive ? (
        <Button type="button" size="sm" variant="outline" disabled>
          <Spinner /> Generating deck…
        </Button>
      ) : (
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => void handleGenerate()}
          disabled={generating}
        >
          Generate quiz deck
        </Button>
      )}

      {job?.status === "failed" && job.error ? (
        <p
          role="alert"
          data-testid={`quiz-error-${sourceId}`}
          className="text-sm text-destructive"
        >
          {job.error}
        </p>
      ) : null}
      {actionError ? (
        <p role="alert" className="text-sm text-destructive">
          {actionError}
        </p>
      ) : null}

      {items.length > 0 ? (
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span
            data-testid={`quiz-counts-${sourceId}`}
            className="text-muted-foreground"
          >
            {items.length} {items.length === 1 ? "item" : "items"} · {due} due
          </span>
          {changed > 0 ? (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Badge variant="outline">source changed</Badge>
                </TooltipTrigger>
                <TooltipContent>
                  Some items no longer match the book after re-ingestion and are
                  paused until you review them.
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          ) : null}
          {due > 0 ? (
            <Link
              href={`/review?source_id=${sourceId}`}
              className="text-primary underline-offset-4 hover:underline"
            >
              Review
            </Link>
          ) : null}
          <a
            href={quizExportUrl(sourceId)}
            className="text-primary underline-offset-4 hover:underline"
          >
            Export to Anki
          </a>
        </div>
      ) : null}
    </div>
  );
}

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
  // Id of the ready source whose re-ingest is awaiting confirmation. Re-ingest
  // replaces the corpus and can stale/orphan quiz items, so it never fires on a
  // single click.
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
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
      setConfirmingId(null);
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
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
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
                    <>
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
                      <QuizDeckControls
                        sourceId={source.id}
                        csrfToken={state.user.csrf_token}
                      />
                      {confirmingId === source.id ? (
                        <div className="space-y-2">
                          <p className="text-sm text-muted-foreground">
                            Re-ingesting rebuilds this book&apos;s corpus with
                            the current providers. Existing quiz items may go
                            stale or orphaned.
                          </p>
                          <div className="flex gap-2">
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              onClick={() => void handleStart(source)}
                              disabled={startingId === source.id}
                            >
                              {startingId === source.id
                                ? "Re-ingesting…"
                                : "Confirm re-ingest"}
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              onClick={() => setConfirmingId(null)}
                              disabled={startingId === source.id}
                            >
                              Cancel
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          onClick={() => setConfirmingId(source.id)}
                        >
                          Re-ingest
                        </Button>
                      )}
                    </>
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
