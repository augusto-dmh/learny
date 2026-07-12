"use client";

/**
 * Teach panel (E2, TEACH-22).
 *
 * Resolves auth state via `/api/auth/me` (through the proxy), then drives one
 * source's teaching flow — all same-origin, never cross-origin. The CSRF token
 * read on mount is reused for the state-changing start/turn calls (AD-007),
 * mirroring `AskPanel`.
 *
 * Two views:
 * - No session yet: a target picker built from the source's structure endpoint
 *   plus a resume list of the source's previous sessions.
 * - In a session (freshly started or resumed): the target's conversation — each
 *   turn's user message and its cited response (section-path breadcrumb +
 *   snippet) or an explicit not-found callout — with a composer.
 *
 * `onRequireAuth` fires when the user is unauthenticated so the caller can do a
 * UX-only redirect. That redirect is convenience ONLY, NOT the security
 * boundary — FastAPI enforces auth, ownership, readiness, and target scoping on
 * every teaching call regardless of client-side routing (FR-AUTH-007, ADR-017).
 */

import { useCallback, useEffect, useState } from "react";

import { fetchAuthState, type AuthState } from "@/app/lib/auth";
import {
  fetchSourceStructure,
  type SourceStructure,
  type StructureSection,
} from "@/app/lib/sources";
import {
  getTeachingSession,
  listTeachingSessions,
  postTeachingTurn,
  startTeachingSession,
  type TeachingSessionDetail,
  type TeachingSessionSummary,
} from "@/app/lib/teaching";

/** One selectable target flattened out of the nested structure tree. */
type TargetOption = {
  anchor: string;
  label: string;
};

/** Flatten the nested section tree into a depth-first list of pickable targets. */
function flattenSections(sections: StructureSection[]): TargetOption[] {
  const options: TargetOption[] = [];
  for (const section of sections) {
    options.push({
      anchor: section.anchor,
      label: section.section_path.join(" › "),
    });
    options.push(...flattenSections(section.children));
  }
  return options;
}

export function TeachPanel({
  sourceId,
  onRequireAuth,
}: {
  sourceId: string;
  onRequireAuth?: () => void;
}) {
  const [state, setState] = useState<AuthState | null>(null);
  const [structure, setStructure] = useState<SourceStructure | null>(null);
  const [sessions, setSessions] = useState<TeachingSessionSummary[] | null>(
    null,
  );
  const [selectedAnchor, setSelectedAnchor] = useState("");
  const [session, setSession] = useState<TeachingSessionDetail | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [sending, setSending] = useState(false);
  const [resumingId, setResumingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    const next = await fetchAuthState();
    setState(next);
    // UX-only redirect for unauthenticated users (NOT the security boundary).
    if (!next.authenticated) {
      onRequireAuth?.();
      return;
    }
    try {
      const [struct, list] = await Promise.all([
        fetchSourceStructure(sourceId),
        listTeachingSessions(sourceId),
      ]);
      setStructure(struct);
      setSessions(list);
      const options = flattenSections(struct.sections);
      if (options.length > 0) {
        setSelectedAnchor(options[0].anchor);
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not load this book.",
      );
    }
  }, [sourceId, onRequireAuth]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleStart(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!state?.authenticated || !selectedAnchor) {
      return;
    }
    setStarting(true);
    try {
      const started = await startTeachingSession(
        sourceId,
        selectedAnchor,
        state.user.csrf_token,
      );
      // A freshly started session opens with no turns yet.
      setSession({ ...started, turns: [] });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not start the session.",
      );
    } finally {
      setStarting(false);
    }
  }

  async function handleResume(summary: TeachingSessionSummary) {
    setError(null);
    setResumingId(summary.id);
    try {
      const detail = await getTeachingSession(summary.id);
      setSession(detail);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not load that session.",
      );
    } finally {
      setResumingId(null);
    }
  }

  async function handleSend(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!state?.authenticated || !session) {
      return;
    }
    setSending(true);
    try {
      const turn = await postTeachingTurn(
        session.id,
        message,
        state.user.csrf_token,
      );
      // Append the new cited turn to the conversation and clear the composer.
      setSession({ ...session, turns: [...session.turns, turn] });
      setMessage("");
    } catch (err) {
      // Surface the readable error; the composer stays usable so the owner can
      // retry (409/422/429/502 all land here).
      setError(
        err instanceof Error ? err.message : "Could not send your message.",
      );
    } finally {
      setSending(false);
    }
  }

  if (state === null) {
    return <p>Loading…</p>;
  }
  if (!state.authenticated) {
    return <p>You are signed out.</p>;
  }

  if (session !== null) {
    return (
      <section aria-label="teach conversation">
        <h2>{session.target.section_path.join(" › ")}</h2>
        <ol>
          {session.turns.map((turn) => (
            <li key={turn.turn_index} data-testid={`turn-${turn.turn_index}`}>
              <p data-testid="user-message">{turn.message}</p>
              {turn.answer_status === "answered" ? (
                <div data-testid="answer">
                  <p>{turn.text}</p>
                  <ul>
                    {turn.citations.map((citation) => (
                      <li key={citation.chunk_id}>
                        <span>{citation.section_path.join(" › ")}</span>
                        <span>{citation.snippet}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                <p data-testid="not-found">
                  That was not found in this target.
                </p>
              )}
            </li>
          ))}
        </ol>
        <form onSubmit={handleSend} aria-label="send message">
          <label>
            Message
            <input
              type="text"
              name="message"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              required
            />
          </label>
          {error ? <p role="alert">{error}</p> : null}
          <button type="submit" disabled={sending}>
            {sending ? "Sending…" : "Send"}
          </button>
        </form>
      </section>
    );
  }

  return (
    <section aria-label="teach">
      <form onSubmit={handleStart} aria-label="start session">
        <label>
          Target
          <select
            name="target"
            value={selectedAnchor}
            onChange={(e) => setSelectedAnchor(e.target.value)}
          >
            {structure === null
              ? null
              : flattenSections(structure.sections).map((option) => (
                  <option key={option.anchor} value={option.anchor}>
                    {option.label}
                  </option>
                ))}
          </select>
        </label>
        {error ? <p role="alert">{error}</p> : null}
        <button type="submit" disabled={starting || selectedAnchor === ""}>
          {starting ? "Starting…" : "Start session"}
        </button>
      </form>
      <section aria-label="previous sessions">
        <h2>Previous sessions</h2>
        {sessions === null ? (
          <p>Loading…</p>
        ) : sessions.length === 0 ? (
          <p>No sessions yet.</p>
        ) : (
          <ul>
            {sessions.map((summary) => (
              <li key={summary.id}>
                <span>{summary.target.section_path.join(" › ")}</span>
                <button
                  type="button"
                  onClick={() => void handleResume(summary)}
                  disabled={resumingId === summary.id}
                >
                  {resumingId === summary.id ? "Resuming…" : "Resume"}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </section>
  );
}
