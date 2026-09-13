# House Profiles Specification (curated per-user generation profiles)

Scope source: `docs/research/2026-09-07/provider-adapter-architecture.md` §3.2 Flavor A
(the recorded one-cycle slice) + §4 Q11; handoff records in `.specs/project/STATE.md`
(PR #69 and PR #70 entries both record this as the next cycle). The precondition —
the routing adapter + per-profile pricing (RFC-0007 Cycle G, PR #69) — is shipped.
Run shape: **single cycle**, research + ADR-0020 follow-up amendment + Flavor-A build.

## Problem Statement

Learners cannot choose how their answers are generated. The profile registry
(`backend/app/infrastructure/providers/profiles.py`) and the routing chain
(`backend/app/infrastructure/answering/routing.py`) are operator-wide: every user
serves from the same chain led by the registry's primary profile. When the operator
enables a second profile (e.g. the economy tier), there is no per-user way to serve
a learner from it, no place to store that choice, and no surface that honestly
states what a non-default profile costs in answer quality. Nothing per-user exists
in the AI plane: the `User` entity carries email/ToS/verification only, and the
frontend device-local settings hooks explicitly cite the "no per-user preferences
table" precedent (AD-147) — which this cycle amends for AI serving choice only.

## Goals

- [ ] ADR-0020 gains a follow-up amendment: end-user choice among operator-curated
      house profiles is accepted (Flavor A); BYO keys stay deferred (pricing-gated);
      the AD-147 device-local boundary is restated (account-level AI choice is
      account state; UI preferences stay device-local).
- [ ] One stored preference per user naming a declared profile; unsetting restores
      the operator default.
- [ ] Ask/Teach turn generation resolves per-user: the chosen profile leads the
      chain when it is declared and mode-eligible; the operator default chain
      follows; unset/unknown/mode-ineligible choices serve the operator default.
- [ ] The catalog and the choice are honest: learner-visible copy per profile
      (what it is, what it trades away), served by new optional fields on the
      profile registry.
- [ ] An account-page selector, visible only when the deployment actually offers a
      choice; the choice rides `MeResponse`.

## Out of Scope

| Feature | Reason |
|---|---|
| BYO API keys (Flavor B) | 3+ cycles + crypto + security review; pricing-gated (RQ10); the follow-up amendment keeps it deferred |
| Quiz deck / card-suggestion routing per user | `QuizGenerationPort` sits outside the profile registry and decks pin their provider at `begin_deck`; no recorded demand |
| Selection-Explain chain per user | The explain chain is a house cost lever (Cycle G); user choice must not move it |
| Per-user effort overrides | Effort is a profile value per ADR-0020 amendment ¶4; the choice is between profiles, not dials |
| Enabling / promoting any profile (e.g. economy) | Promotion is the operator's eval-gated act (ADR-0020 amendment ¶8); this cycle only makes an enabled profile selectable |
| Per-mode preferences (separate ask/teach choices) | UI complexity with no recorded demand; one preference names one profile |
| Model-picker UI beyond the account page | The account page is the recorded slice (§3.2 Flavor A item 5); in-reader surfaces are later product calls |

---

## Assumptions & Open Questions

Every ambiguity is resolved or recorded here — nothing is left silently unclear.
Decisions made under the ship-cycle auto-decision rule (options + recommendation in
`context.md`, AD rows in STATE.md).

| Assumption / decision | Chosen default | Rationale | Confirmed? |
|---|---|---|---|
| Research deliverable | The 2026-09-07 architecture doc **is** the research; no new research doc | Re-researching the recorded slice would duplicate it; the cycle cites it and moves to the amendment + build | y |
| Resolution semantics | Reorder, keep fail-over: chosen profile leads, default chain follows (deduped) | Fail-over is a shipped trust feature (ADR-0020 amendment ¶5–6); a hard pin would punish users for house infra failures; budget stays honest via per-answer `profile_id` stamps | y |
| Selector visibility | Hidden unless the deployment offers ≥1 selectable non-default profile | Honesty: a dead selector in single-profile deployments is worse than absence; economy ships inert today, so most deployments see nothing until the operator enables it | y |
| Profile copy fields | New optional `display_name` + `description` on `GenerationProfileSettings` (empty → UI falls back to id / hides copy) | Honest degradation copy ("answers may cite less precisely") is operator judgment, not derivable from enums; optional fields keep existing env JSON parsing (extra="forbid") | y |
| API shape | `GET /api/ai/profiles` (catalog) + `GET/PUT/DELETE /api/me/ai-profile` (choice); `MeResponse` grows `ai_profile_id: str \| null` | No per-user mutable endpoint exists today; choice and catalog are different resources | y |
| Stale persisted profile | Resolves to the operator default with a log warning; never errors a turn; UI shows unset when the id is not in the catalog | Operators rename/remove profiles; a learner's choice must never break asking | y |
| Table shape | `user_ai_preferences`: one row per user (PK `user_id`, FK→users ON DELETE CASCADE), `profile_id text NOT NULL`, timestamps | The recorded slice ("a per-user preference row + two-tier adapter resolution"); upsert keeps one row per user | y |

**Open questions:** none — all resolved or logged above.

---

## Requirements & Acceptance Criteria

IDs are traceable: `HP-NN`. Every AC asserts a spec-defined outcome.

### Preference store

- **HP-01**: Migration `0029_user_ai_preferences` creates the table with PK
  `user_id` referencing `users(id)` ON DELETE CASCADE, `profile_id` non-null text,
  `created_at`/`updated_at` UTC defaults; `alembic upgrade head` then one
  downgrade step drops it cleanly (round-trip proven).
- **HP-02**: An `AiPreferenceRepository` port (domain) + SQLAlchemy adapter
  (infrastructure) supports get-by-user, upsert (re-PUT replaces the profile id on
  the single row), and delete; deleting the user deletes the row (cascade).

### Per-user resolution

- **HP-03**: For an Ask or Teach turn, the generation chain is resolved per user:
  if the user's stored profile id names a profile in the current registry that is
  eligible for the requested mode, that profile leads the chain and the remaining
  registry entries follow in registry order (no duplicates); otherwise the chain
  is exactly the operator default chain. A turn served from a non-lead entry is
  indistinguishable in shape from today's fail-over turns.
- **HP-04**: The selection-Explain chain and the quiz/card generation paths are
  byte-for-byte unaffected by any stored preference (house-routed always).
- **HP-05**: Spend accounting is unchanged in mechanism: each answer stamps the
  serving profile id and the debit resolves that profile's catalog — a fail-over
  away from the chosen profile debits at the profile that actually served.
- **HP-06**: The streaming bound is unchanged: a user-resolved chain may fail over
  only before the first emitted delta.
- **HP-07**: The rails are unchanged and precede any port touch regardless of the
  resolved profile: kill switch, USD cap, per-kind counters, user-keyed rate
  limits.

### API surface

- **HP-08**: `GET /api/ai/profiles` (authenticated) returns the selectable catalog
  derived from the declared registry: per profile — id, display_name (falls back
  to id when unset), description (may be empty), grounding kind, ask/teach
  eligibility. The synthetic legacy seed never appears; unauthenticated requests
  are rejected.
- **HP-09**: `GET /api/me/ai-profile` returns `{profile_id: string | null}`;
  `PUT` with a declared profile id stores it (re-PUT replaces); `PUT` with an
  unknown id is a 422 whose detail names the problem; `DELETE` unsets and is
  idempotent (204 even when nothing was set).
- **HP-10**: `MeResponse` grows `ai_profile_id: string | null` reflecting the
  stored row (null when unset).
- **HP-11**: `GenerationProfileSettings` gains optional `display_name` and
  `description` string fields (default empty); deployments whose env JSON omits
  them parse byte-identically to today.

### Account UI

- **HP-12**: The account page renders an "AI profile" section only when the
  catalog contains at least one selectable profile; the section lists "Operator
  default (recommended)" plus each catalog profile with its copy. With an empty
  catalog the section is absent — not disabled.
- **HP-13**: Choosing an entry persists via PUT (choosing the default entry
  DELETEs); the selector reflects the stored choice from the choice endpoint, and
  a failure surfaces the backend's honest error copy.
- **HP-14**: A stored id that is absent from the catalog renders as the default
  entry (serving is the operator default in that state) — the UI never shows a
  phantom selection.

---

## Verification notes

- Local gate (this environment): full backend pytest suite minus db-gated tests
  (no Docker in this WSL session → no local Postgres), ruff + format check,
  boundary fitness gate, frontend vitest, tsc. DB-gated coverage (HP-01/HP-02 and
  any API tests marked requires_db) is exercised by CI's Postgres service
  container; a green CI run is the authority for those.
- Discrimination sensors must include: chosen-profile-leads (mutate the reorder →
  chain serves default), unknown-id fallback (mutate the fallback → turn errors or
  serves the stale id), mode-ineligible fallback, explain/quiz independence
  (mutate a shared resolution path → explain chain moves), and selector
  visibility (mutate the catalog-empty rule → dead section renders).
