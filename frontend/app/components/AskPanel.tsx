"use client";

/**
 * Ask panel (D2, QA-18..QA-21).
 *
 * Resolves auth state via `/api/auth/me` (through the proxy), then lets the
 * owner ask a question against one ready source and inspect the cited answer —
 * all same-origin, never cross-origin. The CSRF token read on mount is reused
 * for the state-changing ask (AD-007), mirroring `SourcesPanel`.
 *
 * `onRequireAuth` fires when the user is unauthenticated so the caller can do a
 * UX-only redirect. That redirect is convenience ONLY, NOT the security
 * boundary — FastAPI enforces auth, ownership, and readiness on every
 * `/api/sources/{id}/questions` call regardless of client-side routing
 * (FR-AUTH-007, ADR-017).
 */

import { useCallback, useEffect, useState } from "react";

import { fetchAuthState, type AuthState } from "@/app/lib/auth";
import { askQuestion, type AnswerView } from "@/app/lib/questions";

export function AskPanel({
  sourceId,
  onRequireAuth,
}: {
  sourceId: string;
  onRequireAuth?: () => void;
}) {
  const [state, setState] = useState<AuthState | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AnswerView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    const next = await fetchAuthState();
    setState(next);
    // UX-only redirect for unauthenticated users (NOT the security boundary).
    if (!next.authenticated) {
      onRequireAuth?.();
    }
  }, [onRequireAuth]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleAsk(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!state?.authenticated) {
      return;
    }
    setSubmitting(true);
    try {
      const result = await askQuestion(sourceId, question, state.user.csrf_token);
      // A fresh answer replaces any prior result; a prior error was cleared above.
      setAnswer(result);
    } catch (err) {
      // Surface the readable error and drop any stale answer; the form stays
      // mounted and usable so the owner can retry (QA-20).
      setAnswer(null);
      setError(err instanceof Error ? err.message : "Could not get an answer.");
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
    <section aria-label="ask">
      <form onSubmit={handleAsk} aria-label="ask question">
        <label>
          Question
          <input
            type="text"
            name="question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            required
          />
        </label>
        {error ? <p role="alert">{error}</p> : null}
        <button type="submit" disabled={submitting}>
          {submitting ? "Asking…" : "Ask"}
        </button>
      </form>
      {answer === null ? null : answer.answer_status === "answered" ? (
        <div data-testid="answer">
          <p>{answer.answer}</p>
          <ul>
            {answer.citations.map((citation) => (
              <li key={citation.chunk_id}>
                <span>{citation.section_path.join(" › ")}</span>
                <span>{citation.snippet}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p data-testid="not-found">
          That question was not found in this source.
        </p>
      )}
    </section>
  );
}
