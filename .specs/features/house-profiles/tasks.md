# House Profiles — Tasks

Gate legend — `BT`: `cd backend && uv run pytest` (db-gated tests skip locally;
CI is their authority) · `RF`: `cd backend && uv run ruff check . && uv run ruff
format --check .` · `FIT`: `python3 backend/scripts/check_boundaries.py` ·
`FT`: `cd frontend && npm test` · `TS`: `cd frontend && npx tsc --noEmit`.
Rules: tests derive from ACs and assert spec outcomes; gate green before a task
is done; one atomic commit per task; no attribution, no internal IDs in
messages. Intermediate gates may scope to the affected test module; the full
gate set runs at each phase boundary and before push.

## Phase 1 — Docs (bookkeeping before code)

- **T-01**: ROADMAP row authored (Post-RFC-0007 heading, `house-profiles` row,
  pointer to research + spec) and STATE.md gains AD-350..AD-356 rows (from
  `context.md` D-1..D-7). Verify: rows present, table renders. Commit:
  `docs(specs): plan house profiles cycle`.
- **T-02**: ADR-0020 follow-up amendment section: Flavor A accepted (learner
  picks among operator-curated house profiles), BYO keys stay deferred,
  AD-147 boundary restated (account-level AI choice is account state; UI
  preferences stay device-local), port stays frozen, spend rails/promotion
  unchanged. Verify: section reads as the decision record for D-1..D-7; no
  contradiction with the 2026-09-07 amendment. Commit:
  `docs(adr): accept learner choice among house profiles`.

## Phase 2 — Backend kernel (store + resolution)

- **T-03**: Migration `0029_user_ai_preferences` (upgrade/downgrade) + Core
  table in `metadata.py`. Verify (BT): migration round-trip test on the db-gated
  harness (upgrade applies; downgrade drops; re-upgrade restores). Commit:
  `feat(db): add user ai preference table`.
- **T-04**: `AiPreference` entity + `AiPreferenceRepository` port +
  `SqlAlchemyAiPreferenceRepository` (get/upsert/delete; single row per user;
  user-scoped only). Verify (BT): db-gated repo tests — upsert twice leaves one
  row with the second id; get on missing user → None; delete removes; cascade
  deletes with the user. Commit: `feat(domain): ai preference repository`.
- **T-05**: `build_user_generation_chain(settings, profile_id | None, *,
  explain=False)` + composition seam `get_generation_for_user(user)` with a
  profile-id-keyed cache cleared beside `get_settings.cache_clear()`. Unit tests
  (no db): chosen-declared-profile leads; others follow in registry order
  deduped; None/unknown/stale → default chain; explain flag builds the explain
  chain regardless of preference; two profile ids resolve different leads in one
  process; cache clearing works. Verify (BT, scoped module + full at boundary).
  Commit: `feat(answering): per-user generation chain resolution`.
- **T-06**: Ask/Teach wiring: `get_post_conversation_turn` resolves the caller's
  preference via the request connection and passes the user chain; service
  signature unchanged. Unit/integration tests: ask turn with a chosen eligible
  profile serves from it (stamp asserts the profile id); chosen profile that is
  mode-ineligible serves default; stale id serves default + warning logged;
  budget debit for a fail-over answer prices at the serving profile's catalog
  (HP-05). Verify (BT full at phase boundary; RF; FIT). Commit:
  `feat(conversations): serve ask and teach from the reader's chosen profile`.

## Phase 3 — API surface + copy

- **T-07**: `display_name`/`description` optional fields on
  `GenerationProfileSettings`; catalog assembly excluding the legacy seed.
  Unit tests: env JSON without the new fields parses byte-identically (HP-11);
  seed excluded; fallbacks. Commit:
  `feat(providers): learner-facing profile metadata`.
- **T-08**: Routes `GET /api/ai/profiles`, `GET/PUT/DELETE /api/me/ai-profile`
  (+ 422 unknown id, idempotent DELETE 204) and `MeResponse.ai_profile_id`.
  Tests (db-gated where they touch the db): catalog shape per HP-08; PUT/GET/
  DELETE lifecycle per HP-09; 401 unauthenticated; MeResponse carries the id
  (HP-10). Verify (BT full; RF; FIT at boundary). Commit:
  `feat(web): ai profile catalog and per-user choice endpoints`.

## Phase 4 — Frontend

- **T-09**: `app/lib/auth.ts` MeResponse type + new `app/lib/ai-profiles.ts`
  client (fetch/put/delete + `toAiProfilesError`). Verify (FT/TS): unit tests
  for the error mapping. Commit: `feat(frontend): ai profile client`.
- **T-10**: AccountPanel "AI profile" section: hidden when catalog empty;
  default row + catalog rows with copy; PUT/DELETE on selection; stored-id-not-
  in-catalog renders default (HP-12/13/14); honest error copy. jsdom tests:
  empty-catalog absence; rendering with two profiles; selection calls PUT;
  choosing default calls DELETE; failure renders error. Verify (FT full; TS;
  frontend build if CI-equivalent available). Commit:
  `feat(frontend): account ai profile selector`.

## Phase 5 — Verifier (mandatory, fresh subagent)

Spec-anchored outcome check over HP-01..HP-14 + discrimination sensor
(reorder-mutation, fallback-mutation, explain/quiz independence, selector
visibility) + `validation.md` + lessons. Bound: fix→re-verify ≤ 3 iterations.

## Pre-push

Full gates: BT (suite), RF, FIT, FT, TS. Then Stage 2 (learny-finalize).
