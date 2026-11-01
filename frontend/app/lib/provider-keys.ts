/**
 * Browser-side client for the learner's own provider keys (ADR-0033).
 *
 * The account page's keys section lists the providers this instance offers,
 * saves (or replaces) a key, tests a stored key, deletes it, and shows the
 * learner's month-to-date own-key usage beside the monthly budget they can
 * set or clear. Every call goes through the same-origin Next.js proxy
 * (`/api/...`, ADR-017); the HttpOnly session cookie rides along, and the
 * mutating calls echo the session-bound CSRF token in `X-CSRF-Token`.
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

/**
 * The caller's month-to-date own-key usage and their stored monthly budget,
 * as the backend reports it. Zeros are a quiet month; `budget_usd_micros` is
 * `null` while no budget is set. The cost is the learner's own estimate at
 * the serving catalog — the operator's number is never shown here.
 */
export type ByokUsageView = {
  period: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd_micros: number;
  budget_usd_micros: number | null;
};

/** The keys section: whether it exists on this instance, and its rows. */
export type ProviderKeys = {
  enabled: boolean;
  /**
   * The instance's own hosted declaration — not secret, and reported even
   * while the feature is off, so the hosted disclosure can render wherever
   * the section does.
   */
  hosted: boolean;
  providers: ProviderKeyRow[];
  /** The caller's month-to-date usage and budget, riding every response. */
  usage: ByokUsageView;
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

/**
 * Store (or clear) the caller's own monthly budget. A USD amount greater than
 * 0 and at most 10,000 sets it; `null` clears it, and their key serves the
 * next request — that is what makes the budget soft. The response is the
 * refreshed usage view, never an echo of the submitted value.
 */
export async function putProviderKeyBudget(
  monthlyBudgetUsd: number | null,
  csrfToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<ByokUsageView> {
  const res = await fetchImpl(`${BASE}/budget`, {
    method: "PUT",
    credentials: "same-origin",
    headers: { "content-type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify({ monthly_budget_usd: monthlyBudgetUsd }),
  });
  if (!res.ok) {
    throw await apiErrorFrom(res, "providerKeyBudget");
  }
  return (await res.json()) as ByokUsageView;
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
