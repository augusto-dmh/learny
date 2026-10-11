/**
 * Browser-side client for the learner's own provider keys (ADR-0033).
 *
 * The account page's keys section lists the providers this instance offers,
 * saves (or replaces) a key, tests a stored key and deletes it. Every call goes
 * through the same-origin Next.js proxy (`/api/...`, ADR-017); the HttpOnly
 * session cookie rides along, and the mutating calls echo the session-bound
 * CSRF token in `X-CSRF-Token`.
 *
 * A key travels in exactly one request body (the save) and never comes back:
 * every response carries the provider row with `last4` and the date added. This
 * module keeps no copy of the key it sent.
 *
 * Failures raise an `ApiError` carrying the operation and status; the learner
 * reads catalog copy chosen from them, never the backend `detail`.
 */

import { apiErrorFrom } from "./errors";

/** A provider whose learner keys this instance may accept. */
export type KeyProvider = "anthropic" | "openai" | "gemini";

/** One declared profile a provider's key powers, with its mode eligibility. */
export type PoweredProfile = {
  profile_id: string;
  display_name: string;
  ask: boolean;
  teach: boolean;
};

/** One offered provider and the caller's key state for it. Never key material. */
export type ProviderKeyRow = {
  provider: KeyProvider;
  /** The provider's brand name, the same in every locale. */
  label: string;
  configured: boolean;
  last4: string | null;
  added_at: string | null;
  powers: PoweredProfile[];
  /** Whether the key also powers flashcard suggestions and decks. */
  powers_cards: boolean;
};

/** The keys section: whether it exists on this instance, and its rows. */
export type ProviderKeys = {
  enabled: boolean;
  providers: ProviderKeyRow[];
};

/** Why a key test failed. */
export type KeyTestReason = "rejected" | "rate_limited" | "unavailable";

/** A key test outcome. */
export type KeyTestResult = { ok: true; reason: null } | { ok: false; reason: KeyTestReason };

const BASE = "/api/me/provider-keys";

/** List the offered providers with the caller's key state. */
export async function listProviderKeys(fetchImpl: typeof fetch = fetch): Promise<ProviderKeys> {
  const res = await fetchImpl(BASE, { method: "GET", credentials: "same-origin" });
  if (!res.ok) {
    throw await apiErrorFrom(res, "providerKeysList");
  }
  return (await res.json()) as ProviderKeys;
}

/** Save (or replace) the caller's key for `provider`; returns the row, not the key. */
export async function putProviderKey(
  provider: KeyProvider,
  apiKey: string,
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<ProviderKeyRow> {
  const res = await fetchImpl(`${BASE}/${provider}`, {
    method: "PUT",
    credentials: "same-origin",
    headers: { "content-type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify({ api_key: apiKey }),
  });
  if (!res.ok) {
    throw await apiErrorFrom(res, "providerKeySave");
  }
  return (await res.json()) as ProviderKeyRow;
}

/** Test the stored key for `provider` (one model-list call; no tokens billed). */
export async function testProviderKey(
  provider: KeyProvider,
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<KeyTestResult> {
  const res = await fetchImpl(`${BASE}/${provider}/test`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRF-Token": csrfToken },
  });
  if (!res.ok) {
    throw await apiErrorFrom(res, "providerKeyTest");
  }
  return (await res.json()) as KeyTestResult;
}

/** Delete the caller's key for `provider`. Idempotent: 204 even when none was stored. */
export async function deleteProviderKey(
  provider: KeyProvider,
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  const res = await fetchImpl(`${BASE}/${provider}`, {
    method: "DELETE",
    credentials: "same-origin",
    headers: { "X-CSRF-Token": csrfToken },
  });
  if (!res.ok) {
    throw await apiErrorFrom(res, "providerKeyDelete");
  }
}
