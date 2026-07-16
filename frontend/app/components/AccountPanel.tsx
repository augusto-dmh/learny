"use client";

/**
 * Logged-in account panel with logout (D2).
 *
 * Resolves auth state via `/api/auth/me` (through the proxy) and renders the
 * signed-in user plus a logout button. Logout sends the session-bound CSRF
 * token in `X-CSRF-Token` (handled inside `auth.logout`, AD-007).
 *
 * The `onRequireAuth` callback fires when the user is unauthenticated so the
 * caller can perform a UX-only redirect. NOTE: this redirect is convenience
 * only and is NOT the security boundary — FastAPI enforces auth on every
 * protected endpoint regardless of client-side routing (FR-AUTH-007).
 */

import { useCallback, useEffect, useState } from "react";

import { fetchAuthState, logout, type AuthState } from "@/app/lib/auth";
import { Button } from "@/components/ui/button";

export function AccountPanel({
  onRequireAuth,
  onLoggedOut,
}: {
  onRequireAuth?: () => void;
  onLoggedOut?: () => void;
}) {
  const [state, setState] = useState<AuthState | null>(null);

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

  async function handleLogout() {
    // Reuse the CSRF token already fetched on mount so logout is a single
    // round-trip (no extra /api/auth/me probe just to read the token).
    const csrfToken =
      state && state.authenticated ? state.user.csrf_token : undefined;
    await logout(csrfToken);
    setState({ authenticated: false });
    onLoggedOut?.();
  }

  if (state === null) {
    return <p className="text-muted-foreground">Loading…</p>;
  }
  if (!state.authenticated) {
    return <p className="text-muted-foreground">You are signed out.</p>;
  }

  return (
    <section aria-label="account" className="space-y-4">
      <p className="text-sm">
        Signed in as <strong className="font-medium">{state.user.email}</strong>
      </p>
      <Button type="button" variant="outline" onClick={handleLogout}>
        Log out
      </Button>
    </section>
  );
}
