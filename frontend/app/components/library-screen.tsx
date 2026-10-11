"use client";

/**
 * Library screen (FE-20/FE-21) — replaces the unstyled SourcesPanel.
 *
 * Resolves auth state via `/api/auth/me` (through the proxy), lists the user's
 * sources as cards with a status badge, uploads an EPUB (unchanged multipart
 * contract), links a ready book through one Open to `/read` (Ask, Tutor, and
 * Review live in overflow; re-ingest stays confirm-gated and is hidden on the
 * sample), and — for a failed source — surfaces the latest ingestion
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
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { fetchAuthState, type AuthState } from "@/app/lib/auth";
import { getIngestion } from "@/app/lib/ingestion";
import { readUrl } from "@/app/lib/read-url";
import {
  generateDeck,
  getQuizOverview,
  quizExportUrl,
  type QuizJob,
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
import { LinkPendingIndicator } from "@/app/components/nav-pending";
import { Spinner } from "@/components/ui/spinner";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

import { useIngestionPolling } from "./use-ingestion-polling";
import { useQuizDeckPolling } from "./use-quiz-deck-polling";
import { useErrorMessage } from "./use-error-message";

/**
 * Quiz-deck controls for one ready source (QUIZ-20). Loads the source's quiz
 * overview once; a load failure leaves the row's reading actions intact and
 * simply shows no quiz controls. Generating a deck starts a job and polls the
 * overview every 3s until the job goes terminal (stopping on unmount). A failed
 * job surfaces its error with the generate button as a retry; a finished deck
 * shows item + due counts, a quiet discarded footnote when generation dropped
 * candidates, a saved/failed-section note when some sections failed, a
 * "source changed" badge when items went stale or
 * orphaned after a re-ingest, a per-source Review link when anything is due, and
 * an Anki export link. A succeeded empty job explains why (no long-enough
 * section, or nothing survived QC) instead of looking like "no deck yet".
 */
function QuizDeckControls({
  sourceId,
  csrfToken,
}: {
  sourceId: string;
  csrfToken: string;
}) {
  const t = useTranslations("library.quiz");
  const errorMessage = useErrorMessage();
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
      setActionError(errorMessage(err, "quizGenerate"));
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
          <Spinner /> {t("generating")}
        </Button>
      ) : (
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => void handleGenerate()}
          disabled={generating}
        >
          {t("generate")}
        </Button>
      )}

      {job?.status === "failed" && job.error ? (
        <p
          role="alert"
          data-testid={`quiz-error-${sourceId}`}
          lang="en"
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

      {job?.status === "succeeded" ? (
        <QuizDeckHonesty sourceId={sourceId} job={job} />
      ) : null}

      {items.length > 0 ? (
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span
              data-testid={`quiz-counts-${sourceId}`}
              className="text-muted-foreground"
            >
              {t("counts", { items: items.length, due })}
            </span>
            {changed > 0 ? (
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Badge variant="outline">{t("sourceChanged")}</Badge>
                  </TooltipTrigger>
                  <TooltipContent>{t("sourceChangedHint")}</TooltipContent>
                </Tooltip>
              </TooltipProvider>
            ) : null}
            {due > 0 ? (
              <Link
                href={`/review?source_id=${sourceId}`}
                className="text-primary underline-offset-4 hover:underline"
              >
                {t("review")}
                <LinkPendingIndicator className="ml-1 align-middle" />
              </Link>
            ) : null}
            <a
              href={quizExportUrl(sourceId)}
              className="text-primary underline-offset-4 hover:underline"
            >
              {t("exportAnki")}
            </a>
          </div>
          {job?.status === "succeeded" && job.generated_count >= 1 ? (
            <QuizDeckYieldNotes sourceId={sourceId} job={job} />
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/**
 * Honest empty-deck copy from a succeeded job's counts (REV-03/04/07). Thin and
 * failed-partial yield notes live next to the item counts, not here.
 */
function QuizDeckHonesty({
  sourceId,
  job,
}: {
  sourceId: string;
  job: QuizJob;
}) {
  const t = useTranslations("library.quiz");
  const generated = job.generated_count;
  const discarded = job.discarded_count;
  const failed = job.failed_sections;

  if (generated === 0 && discarded === 0 && failed === 0) {
    return (
      <p
        data-testid={`quiz-honesty-${sourceId}`}
        className="text-sm text-muted-foreground"
      >
        {t.rich("noSection", {
          link: (chunks) => (
            <Link
              href={`/sources/${sourceId}/read`}
              className="text-primary underline-offset-4 hover:underline"
            >
              {chunks}
            </Link>
          ),
        })}
      </p>
    );
  }

  if (generated === 0 && discarded > 0) {
    return (
      <p
        data-testid={`quiz-honesty-${sourceId}`}
        className="text-sm text-muted-foreground"
      >
        {t("noneSurvived", { discarded })}
      </p>
    );
  }

  return null;
}

/** Quiet discarded footnote and failed-section note on a non-empty succeeded deck. */
function QuizDeckYieldNotes({
  sourceId,
  job,
}: {
  sourceId: string;
  job: QuizJob;
}) {
  const t = useTranslations("library.quiz");
  const discarded = job.discarded_count;
  const failed = job.failed_sections;
  const saved = job.generated_count;

  return (
    <>
      {discarded > 0 ? (
        <p
          data-testid={`quiz-discard-footnote-${sourceId}`}
          className="text-xs text-muted-foreground"
        >
          {t("discardFootnote", { discarded })}
        </p>
      ) : null}
      {failed > 0 ? (
        <p
          data-testid={`quiz-partial-${sourceId}`}
          className="text-sm text-muted-foreground"
        >
          {t("partial", { saved, failed })}
        </p>
      ) : null}
    </>
  );
}

/** Overflow verbs for a ready row: Ask, Tutor, Review, and Re-ingest when owned. */
function ReadyRowOverflow({
  source,
  confirming,
  onRequestReingest,
}: {
  source: SourceSummary;
  confirming: boolean;
  onRequestReingest: () => void;
}) {
  const t = useTranslations("library.row");
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <Button
        type="button"
        size="sm"
        variant="ghost"
        aria-label={t("moreActions")}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((current) => !current)}
      >
        …
      </Button>
      {open ? (
        <div
          role="menu"
          className="absolute top-full left-0 z-20 mt-1 flex min-w-36 flex-col rounded-md border bg-popover p-1 shadow-md"
        >
          <Link
            href={readUrl(source.id, null, { panel: "ask" })}
            className="rounded-sm px-2 py-1.5 text-sm text-primary underline-offset-4 hover:underline"
          >
            {t("ask")}
            <LinkPendingIndicator className="ml-1 align-middle" />
          </Link>
          <Link
            href={readUrl(source.id, null, { panel: "teach" })}
            className="rounded-sm px-2 py-1.5 text-sm text-primary underline-offset-4 hover:underline"
          >
            {t("tutor")}
            <LinkPendingIndicator className="ml-1 align-middle" />
          </Link>
          <Link
            href={`/review?source_id=${source.id}`}
            className="rounded-sm px-2 py-1.5 text-sm text-primary underline-offset-4 hover:underline"
          >
            {t("review")}
            <LinkPendingIndicator className="ml-1 align-middle" />
          </Link>
          {!source.is_sample && !confirming ? (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="justify-start"
              onClick={() => {
                setOpen(false);
                onRequestReingest();
              }}
            >
              {t("reingest")}
            </Button>
          ) : null}
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
  const t = useTranslations("library");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  // One formatter per locale, not one per card per render (the list re-renders
  // on every title keystroke and poll tick).
  const dateFormat = useMemo(
    () => new Intl.DateTimeFormat(locale, { dateStyle: "medium" }),
    [locale],
  );
  const errorMessage = useErrorMessage();
  const [state, setState] = useState<AuthState | null>(null);
  const [sources, setSources] = useState<SourceSummary[] | null>(null);
  // A failed list read, as catalog copy; null while the list loads or loaded.
  const [listError, setListError] = useState<string | null>(null);
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
    Record<string, string | null>
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
    try {
      setSources(await listSources());
      setListError(null);
    } catch (err) {
      setListError(errorMessage(err, "sourcesList"));
    }
    // `errorMessage` is rebuilt every render; listing it would refetch forever.
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
  // its ingestion once and cache the latest event message for display. A message
  // is the backend's own diagnostic record (English data, shown under
  // `lang="en"`); with none, the catalog says the ingestion failed.
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
          const message = latest ?? ingestion.error ?? null;
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
      setError(t("upload.chooseFile"));
      return;
    }
    setSubmitting(true);
    try {
      const source = await uploadSource(file, title, state.user.csrf_token);
      setSources((prev) => [source, ...(prev ?? [])]);
      setFile(null);
      setTitle("");
    } catch (err) {
      setError(errorMessage(err, "sourcesUpload"));
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
      setError(errorMessage(err, "sourcesIngest"));
    } finally {
      setStartingId(null);
      setConfirmingId(null);
    }
  }

  if (state === null) {
    return <p className="text-muted-foreground">{tCommon("loading")}</p>;
  }
  if (!state.authenticated) {
    return <p className="text-muted-foreground">{tCommon("signedOut")}</p>;
  }

  return (
    <section aria-label={t("regionLabel")} className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{t("upload.heading")}</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={handleUpload}
            aria-label={t("upload.formLabel")}
            className="space-y-4"
          >
            <div className="space-y-1.5">
              <label htmlFor="upload-title" className="text-sm font-medium">
                {t("upload.title")}
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
                {t("upload.file")}
              </label>
              <Input
                id="upload-file"
                type="file"
                name="file"
                accept=".epub,.pdf,application/epub+zip,application/pdf"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </div>
            {error ? (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            ) : null}
            <Button type="submit" disabled={submitting}>
              {submitting ? t("upload.uploading") : t("upload.submit")}
            </Button>
          </form>
        </CardContent>
      </Card>

      {sources !== null &&
      sources.some((item) => item.is_sample) &&
      sources.some(
        (item) => !item.is_sample && item.status === "processing",
      ) ? (
        <p className="text-sm text-muted-foreground">
          {t("sampleReady")}
        </p>
      ) : null}

      {sources === null && listError ? (
        <p role="alert" className="text-sm text-destructive">
          {listError}
        </p>
      ) : sources === null ? (
        <p className="text-muted-foreground">{t("loadingSources")}</p>
      ) : (
        <div className="space-y-3">
          <p data-testid="library-count" className="text-sm text-muted-foreground">
            {t("count", { count: sources.length })}
          </p>
          {sources.length === 0 ? (
            <p className="text-muted-foreground">{t("empty")}</p>
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
                        {t("status", { status: source.status })}
                      </Badge>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <AddedOn createdAt={source.created_at} dateFormat={dateFormat} />
                      {source.status === "ready" ? (
                        <>
                          <div className="flex items-center gap-4 text-sm">
                            <Link
                              href={readUrl(source.id, null)}
                              className="text-primary underline-offset-4 hover:underline"
                            >
                              {t("row.open")}
                              <LinkPendingIndicator className="ml-1 align-middle" />
                            </Link>
                            <ReadyRowOverflow
                              source={source}
                              confirming={confirmingId === source.id}
                              onRequestReingest={() => setConfirmingId(source.id)}
                            />
                          </div>
                          <QuizDeckControls
                            sourceId={source.id}
                            csrfToken={state.user.csrf_token}
                          />
                          {confirmingId === source.id && !source.is_sample ? (
                            <div className="space-y-2">
                              <p className="text-sm text-muted-foreground">
                                {t("row.reingestWarning")}
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
                                    ? t("row.reingesting")
                                    : t("row.confirmReingest")}
                                </Button>
                                <Button
                                  type="button"
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => setConfirmingId(null)}
                                  disabled={startingId === source.id}
                                >
                                  {tCommon("cancel")}
                                </Button>
                              </div>
                            </div>
                          ) : null}
                        </>
                      ) : null}
                      {source.status === "uploaded" ? (
                        <Button
                          type="button"
                          size="sm"
                          onClick={() => void handleStart(source)}
                          disabled={startingId === source.id}
                        >
                          {startingId === source.id
                            ? t("row.starting")
                            : t("row.startIngestion")}
                        </Button>
                      ) : null}
                      {source.status === "failed" ? (
                        <div className="space-y-2">
                          {source.id in failureMessages ? (
                            <p
                              data-testid={`failure-${source.id}`}
                              lang={failureMessages[source.id] ? "en" : undefined}
                              className="text-sm text-destructive"
                            >
                              {failureMessages[source.id] ?? t("row.ingestionFailed")}
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
                              ? t("row.restarting")
                              : t("row.restartIngestion")}
                          </Button>
                        </div>
                      ) : null}
                    </CardContent>
                  </Card>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

/**
 * When the book was added, in the interface locale's date format. The date is
 * the backend's `created_at`; one that does not parse renders nothing.
 */
function AddedOn({
  createdAt,
  dateFormat,
}: {
  createdAt: string;
  dateFormat: Intl.DateTimeFormat;
}) {
  const t = useTranslations("library");
  const added = new Date(createdAt);
  if (Number.isNaN(added.getTime())) {
    return null;
  }
  const date = dateFormat.format(added);
  return (
    <p data-testid="source-added" className="text-xs text-muted-foreground">
      {t("added", { date })}
    </p>
  );
}
