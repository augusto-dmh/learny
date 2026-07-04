/**
 * Browser-side auth client (D2).
 *
 * Thin helpers the auth screens use to talk to the backend *through the
 * same-origin Next.js proxy* (`/api/...`, ADR-017). These run in the browser:
 * the session cookie is HttpOnly and is attached/stored by the browser
 * automatically (`credentials: "same-origin"`), so this code never reads or
 * holds the session token. The only token JS handles is the CSRF token returned
 * by `/api/auth/me`, which is echoed in `X-CSRF-Token` on state-changing calls
 * (AD-007).
 *
 * This is UI orchestration, not domain logic, and it lives in the app — not the
 * proxy. FastAPI remains authoritative for every auth decision.
 */

export type UserSummary = {
  id: string;
  email: string;
  created_at: string;
};

export type MeResponse = UserSummary & {
  csrf_token: string;
};

/** Auth state as the UI sees it: either a signed-in user or anonymous. */
export type AuthState =
  | { authenticated: true; user: MeResponse }
  | { authenticated: false };

const JSON_HEADERS = { "content-type": "application/json" } as const;

/**
 * Resolve current auth state by calling the proxy `/api/auth/me`.
 * 200 → authenticated (carries the CSRF token); 401 → anonymous.
 */
export async function fetchAuthState(
  fetchImpl: typeof fetch = fetch,
): Promise<AuthState> {
  const res = await fetchImpl("/api/auth/me", {
    method: "GET",
    credentials: "same-origin",
  });
  if (res.status === 200) {
    const user = (await res.json()) as MeResponse;
    return { authenticated: true, user };
  }
  return { authenticated: false };
}

/** Register a new account; backend sets the session cookie on 201. */
export async function register(
  email: string,
  password: string,
  fetchImpl: typeof fetch = fetch,
): Promise<UserSummary> {
  const res = await fetchImpl("/api/auth/register", {
    method: "POST",
    credentials: "same-origin",
    headers: JSON_HEADERS,
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    throw await toAuthError(res, "Registration failed.");
  }
  return (await res.json()) as UserSummary;
}

/** Log in; backend sets the session cookie on 200. */
export async function login(
  email: string,
  password: string,
  fetchImpl: typeof fetch = fetch,
): Promise<UserSummary> {
  const res = await fetchImpl("/api/auth/login", {
    method: "POST",
    credentials: "same-origin",
    headers: JSON_HEADERS,
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    throw await toAuthError(res, "Invalid email or password.");
  }
  return (await res.json()) as UserSummary;
}

/**
 * Log out. Logout is a state-changing request, so it must carry the
 * session-bound CSRF token in `X-CSRF-Token` (AD-007).
 *
 * Pass `csrfToken` when the caller already holds it (the account UI reads it
 * from `/api/auth/me` on mount) to log out in a single round-trip. When it is
 * omitted, we fall back to fetching `/api/auth/me` to obtain the token. The
 * HttpOnly session cookie rides along automatically in both cases.
 */
export async function logout(
  csrfToken?: string,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  let token = csrfToken;
  if (!token) {
    const state = await fetchAuthState(fetchImpl);
    if (!state.authenticated) {
      return; // already signed out — nothing to revoke
    }
    token = state.user.csrf_token;
  }
  const res = await fetchImpl("/api/auth/logout", {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRF-Token": token },
  });
  if (!res.ok && res.status !== 401) {
    throw await toAuthError(res, "Logout failed.");
  }
}

/** Build an Error from a non-OK response, preferring the backend's detail. */
async function toAuthError(res: Response, fallback: string): Promise<Error> {
  try {
    const body = (await res.json()) as { detail?: string };
    return new Error(body.detail ?? fallback);
  } catch {
    return new Error(fallback);
  }
}
