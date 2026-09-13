"use client";

/**
 * Logged-in account panel with logout (D2).
 *
 * Resolves auth state via `/api/auth/me` (through the proxy) and renders the
 * signed-in user plus a logout button. Logout sends the session-bound CSRF
 * token in `X-CSRF-Token` (handled inside `auth.logout`, AD-007).
 *
 * When the deployment actually offers a generation-profile choice, the panel
 * also renders an "AI profile" section: "Operator default (recommended)" plus
 * one honest row per catalog profile. The section exists only when the catalog
 * is non-empty — absent, never a disabled shell — and any failure loading it
 * degrades to that absence rather than an error wall over the account content.
 * A stored id the catalog no longer contains renders as the default entry: the
 * UI never shows a phantom selection. Persisting a choice is not optimistic —
 * a failed save leaves the visible selection untouched and surfaces the
 * backend's own error copy.
 *
 * The `onRequireAuth` callback fires when the user is unauthenticated so the
 * caller can perform a UX-only redirect. NOTE: this redirect is convenience
 * only and is NOT the security boundary — FastAPI enforces auth on every
 * protected endpoint regardless of client-side routing (FR-AUTH-007).
 */

import { useCallback, useEffect, useState } from "react";

import {
  deleteAiProfileChoice,
  getAiProfileChoice,
  listAiProfiles,
  putAiProfileChoice,
  type LearnerProfile,
  type ProfileGrounding,
} from "@/app/lib/ai-profiles";
import { fetchAuthState, logout, type AuthState } from "@/app/lib/auth";
import { Button } from "@/components/ui/button";

/** Honest grounding copy — what the learner gives up per mechanism. */
function groundingHint(grounding: ProfileGrounding): string {
  switch (grounding) {
    case "verified-spans":
      return "Citations are verified against the book.";
    case "prompt-cited":
      return "Citations are model-claimed and may be less precise.";
    case "none":
      return "Answers do not cite the book.";
  }
}

/** Honest availability copy — where the choice actually applies. */
function availabilityHint(profile: LearnerProfile): string {
  if (profile.ask_enabled && profile.teach_enabled) {
    return "Works in Ask and Teach.";
  }
  if (profile.ask_enabled) {
    return "Works in Ask only.";
  }
  if (profile.teach_enabled) {
    return "Works in Teach only.";
  }
  return "Currently works in neither Ask nor Teach.";
}

export function AccountPanel({
  onRequireAuth,
  onLoggedOut,
}: {
  onRequireAuth?: () => void;
  onLoggedOut?: () => void;
}) {
  const [state, setState] = useState<AuthState | null>(null);
  // null = not loaded (or failed to load): the section stays absent either way.
  const [catalog, setCatalog] = useState<LearnerProfile[] | null>(null);
  const [storedChoice, setStoredChoice] = useState<string | null>(null);
  const [aiPending, setAiPending] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const next = await fetchAuthState();
    setState(next);
    // UX-only redirect for unauthenticated users (NOT the security boundary).
    if (!next.authenticated) {
      onRequireAuth?.();
    }
  }, [onRequireAuth]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const authenticated = state?.authenticated === true;
  useEffect(() => {
    if (!authenticated) {
      return;
    }
    let cancelled = false;
    void Promise.all([listAiProfiles(), getAiProfileChoice()])
      .then(([profiles, choice]) => {
        if (cancelled) {
          return;
        }
        setCatalog(profiles);
        setStoredChoice(choice.profile_id);
      })
      .catch(() => {
        // Degrade to section-absent: a failed catalog or choice read must never
        // become an error wall over the rest of the account content.
        if (!cancelled) {
          setCatalog(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [authenticated]);

  async function handleLogout() {
    // Reuse the CSRF token already fetched on mount so logout is a single
    // round-trip (no extra /api/auth/me probe just to read the token).
    const csrfToken =
      state && state.authenticated ? state.user.csrf_token : undefined;
    await logout(csrfToken);
    setState({ authenticated: false });
    onLoggedOut?.();
  }

  /**
   * Persist a choice. Nothing optimistic: the visible selection moves only
   * after the backend confirms, so a failed save changes nothing on screen and
   * the backend's own error copy is surfaced verbatim.
   */
  async function handleChooseProfile(profileId: string | null) {
    if (!state?.authenticated) {
      return;
    }
    setAiError(null);
    setAiPending(true);
    try {
      if (profileId === null) {
        await deleteAiProfileChoice(state.user.csrf_token);
        setStoredChoice(null);
      } else {
        const stored = await putAiProfileChoice(profileId, state.user.csrf_token);
        setStoredChoice(stored.profile_id);
      }
    } catch (error) {
      setAiError(
        error instanceof Error
          ? error.message
          : "Could not save your AI profile choice.",
      );
    } finally {
      setAiPending(false);
    }
  }

  if (state === null) {
    return <p className="text-muted-foreground">Loading…</p>;
  }
  if (!state.authenticated) {
    return <p className="text-muted-foreground">You are signed out.</p>;
  }

  // A stored id absent from the catalog is stale (the operator renamed or
  // removed it): serving already fell back to the operator default, so the UI
  // renders exactly that — never a phantom selection.
  const effectiveChoice =
    catalog !== null &&
    storedChoice !== null &&
    catalog.some((profile) => profile.id === storedChoice)
      ? storedChoice
      : null;

  return (
    <section aria-label="account" className="space-y-4">
      <p className="text-sm">
        Signed in as <strong className="font-medium">{state.user.email}</strong>
      </p>
      {catalog !== null && catalog.length > 0 ? (
        <section aria-label="AI profile" className="space-y-3">
          <h2 className="text-sm font-medium">AI profile</h2>
          <p className="text-sm text-muted-foreground">
            Choose how Ask and Teach generate answers for you.
          </p>
          <div className="space-y-3">
            <label className="flex items-start gap-2.5">
              <input
                type="radio"
                name="ai-profile-choice"
                checked={effectiveChoice === null}
                onChange={() => void handleChooseProfile(null)}
                disabled={aiPending}
                aria-label="Operator default (recommended)"
                className="mt-1"
              />
              <span>
                <span className="block text-sm">
                  Operator default (recommended)
                </span>
                <span className="block text-xs text-muted-foreground">
                  Serving follows the operator&apos;s default chain.
                </span>
              </span>
            </label>
            {catalog.map((profile) => (
              <label key={profile.id} className="flex items-start gap-2.5">
                <input
                  type="radio"
                  name="ai-profile-choice"
                  checked={effectiveChoice === profile.id}
                  onChange={() => void handleChooseProfile(profile.id)}
                  disabled={aiPending}
                  aria-label={profile.display_name}
                  className="mt-1"
                />
                <span>
                  <span className="block text-sm">{profile.display_name}</span>
                  {profile.description ? (
                    <span className="block text-sm text-muted-foreground">
                      {profile.description}
                    </span>
                  ) : null}
                  <span className="block text-xs text-muted-foreground">
                    {groundingHint(profile.grounding)}{" "}
                    {availabilityHint(profile)}
                  </span>
                </span>
              </label>
            ))}
          </div>
          {aiError ? (
            <p role="alert" className="text-sm text-destructive">
              {aiError}
            </p>
          ) : null}
        </section>
      ) : null}
      <Button type="button" variant="outline" onClick={handleLogout}>
        Log out
      </Button>
    </section>
  );
}
