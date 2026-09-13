# House Profiles — Design

Evidence seams: Explore survey 2026-09-12 (post-PR #70 `main`); research seams in
`docs/research/2026-09-07/provider-adapter-architecture.md` §3.2 (line numbers
there predate Cycle G — this doc is authoritative for current refs).

## Components

### 1. Preference store (backend)

- **Table** `user_ai_preferences` (`backend/app/infrastructure/db/metadata.py`,
  Core style like `users` at metadata.py:81): `user_id` PK → `users.id` ON
  DELETE CASCADE, `profile_id` Text NOT NULL, `created_at`/`updated_at`
  TIMESTAMP(timezone=True) server-default now. Migration
  `backend/migrations/versions/0029_user_ai_preferences.py` (revision
  `0029_user_ai_preferences`, down_revision `0028_quiz_deck_spend_marker`),
  upgrade creates, downgrade drops.
- **Entity** `AiPreference` frozen dataclass (`domain/entities.py`, near `User`):
  `user_id: UUID`, `profile_id: str`, `created_at`, `updated_at`.
- **Port** `AiPreferenceRepository` (`domain/ports.py`, near `UserRepository`
  :123): `get_by_user(user_id) -> AiPreference | None`,
  `upsert(user_id, profile_id) -> AiPreference` (single row per user — insert or
  update in one statement; Postgres `ON CONFLICT` on the PK or
  merge-by-select-then-write under the request transaction),
  `delete(user_id) -> bool` (True when a row was removed — idempotent DELETE
  needs this signal only for the 204-vs-204 sameness, not the body).
- **Adapter** `SqlAlchemyAiPreferenceRepository`
  (`infrastructure/db/repositories.py`, mirroring `SqlAlchemyUserRepository`
  :121). Ownership/scope: rows are only ever touched by their own user — every
  method filters by `user_id`; no listing surface exists.

### 2. Per-user chain resolution (backend, the kernel)

Today: `build_generation_chain(settings, *, explain=False)`
(`infrastructure/answering/__init__.py:111`) builds one `RoutingGenerationAdapter`
over the registry order; `get_generation()` / `get_explain_generation()`
(`infrastructure/web/dependencies.py:688-700`) cache it per process with
`@lru_cache`. A per-user choice cannot ride those cached deps.

Design:

- New pure builder beside the existing one:
  `build_user_generation_chain(settings, profile_id: str | None, *, explain=False) -> GenerationPort`.
  Resolution rule (HP-03/AD-352): resolve the registry; if `profile_id` names a
  declared profile, the user chain = [chosen] + [registry others in order,
  deduped]; the `RoutingGenerationAdapter` mode-eligibility walk
  (`_eligible_entries`, routing.py:127) is unchanged, so a chosen profile that is
  not eligible for the requested mode simply is not served for that mode and the
  walk falls through to the registry remainder — which is exactly today's
  behavior when the lead is ineligible. `None`, unknown, or stale ids → the
  default chain. The explain chain never consults the preference (HP-04): the
  explain path keeps calling `build_generation_chain(explain=True)`.
- Composition-root seam: `get_generation_for_user(user: User) -> GenerationPort`
  in `dependencies.py`. Caching: a small process-level dict keyed by profile id
  (registry is process-static under `@lru_cache get_settings`), built from the
  same `_build_sub_adapter` factory — SDK clients construct lazily on first use
  (`answering/anthropic.py:415`), so cached chains cost nothing until used. The
  cache MUST be cleared by the same test hook that clears `get_settings`
  (conftest `_force_local_providers` / wherever `get_settings.cache_clear()` is
  called) — export a `clear_generation_chain_caches()` from the composition root
  and call it beside every existing `cache_clear()` in conftest. Never cache on
  the `User` object; cache on the resolved profile id only.
- Ask/Teach wiring: `get_post_conversation_turn`
  (dependencies.py:764-798) gains the preference lookup — `SqlAlchemyAiPreference
  Repository(conn).get_by_user(user.id)` — and passes the resolved chain into the
  service exactly where it passes `generation`/`explain_generation` today. The
  service signature must not grow a user/profile parameter it does not need: the
  resolution is a composition-root concern; the application service keeps
  receiving a `GenerationPort` (ADR-0007 boundary preserved).
- Rails order is untouched: `assert_generation` runs inside the application
  service before any port touch (conversations.py:820 lineage) regardless of
  which chain resolved (HP-07). Budget mechanism untouched (HP-05): the router
  stamps `profile_id` per answer (routing.py:221,266) and
  `DailyBudget.usage_micros` resolves that profile's catalog
  (budget.py:162); the worker mirror (`tasks.py:490`) is out of scope and
  unchanged.

### 3. Profile copy fields + catalog (backend)

- `GenerationProfileSettings` (providers/profiles.py:59): add
  `display_name: str = ""` and `description: str = ""`. No validation beyond
  str-typed; empty means "UI falls back / hides".
- Catalog assembly (new module or beside the registry resolution in
  `providers/profiles.py`): selectable = declared entries only — exclude the
  synthetic legacy seed (`_legacy_seed_profile`, profiles.py:123). Payload per
  HP-08: `id`, `display_name` (fallback id), `description`, `grounding`,
  `ask_enabled`, `teach_enabled`.
- Routes (new `infrastructure/web/ai_profiles.py`, `APIRouter`):
  - `GET /api/ai/profiles` → `{profiles: [ ... ]}` (authenticated user dep;
    401 otherwise — same `get_authenticated_user` chain as other routers).
  - `GET /api/me/ai-profile` → `{profile_id: str | null}`.
  - `PUT /api/me/ai-profile` body `{profile_id: str}` → validates against
    `resolve_generation_profiles(settings)`; unknown → 422 detail naming the
    problem (HP-09); stores via `upsert`.
  - `DELETE /api/me/ai-profile` → 204, idempotent.
- `MeResponse` (auth.py:99) gains `ai_profile_id: str | None`; the `me` handler
  (auth.py:289) reads the preference through the same repository. Existing
  clients ignore the new field (additive).

### 4. Account UI (frontend)

- `app/lib/auth.ts`: `MeResponse` grows `ai_profile_id: string | null`.
  New `app/lib/ai-profiles.ts` (mirrors the per-module client + `toXError`
  pattern): `fetchAiProfiles()`, `fetchMyAiProfile()`, `putMyAiProfile(id)`,
  `deleteMyAiProfile()`.
- `AccountPanel.tsx`: new section, rendered only when the catalog has ≥1
  selectable profile (HP-12/AD-355 — the section is absent, not disabled).
  Rows: "Operator default (recommended)" + one row per catalog profile —
  display name, description line (when non-empty), grounding/eligibility
  hint. Selection = PUT; choosing default = DELETE; reflects
  `ai_profile_id` but renders default when the stored id is absent from the
  catalog (HP-14); failures surface `toAiProfilesError` copy. Use the existing
  shadcn `select` or a radio-row list matching `AccountPanel`'s current styling.
- Device-local hooks (`use-reading-settings.ts` etc.) are untouched — their
  AD-147 citations remain true for UI preferences; only AI serving choice
  becomes account state (per the follow-up amendment).

## ADR / bookkeeping

- ADR-0020 gains `## Amendment (2026-09): End-User Choice Among House Profiles`:
  Flavor A accepted; BYO stays deferred; AD-147 boundary restated; port stays
  frozen (copy lives beside the port in the registry).
- ROADMAP.md: new row authored under a "Post-RFC-0007" heading (handoff-recorded
  slice), pointing at the research doc + this spec.
- STATE.md: AD-350..AD-356 rows.

## Risks / traps for implementers

- **`extra="forbid"` on `GenerationProfileSettings`**: the new fields MUST have
  defaults or every existing deployment's env JSON fails parsing (HP-11 pins
  this).
- **`@lru_cache` chain singletons**: wiring per-user resolution through
  `get_generation` directly would silently serve one user's chain to everyone —
  the new seam must be keyed per profile id, and its cache cleared in tests
  beside `get_settings.cache_clear()`. A test must prove two users with
  different choices resolve different leads in the same process.
- **Mode eligibility is per-mode**: a chosen profile with `ask_enabled=false`
  must not serve ask turns; the walk falls through. Do not pre-filter the user's
  chain to eligible-only at build time — the router's eligibility walk is the
  single eligibility authority (building eligible-only chains would duplicate
  that logic and drift).
- **Service boundary**: do not pass `profile_id`/user into
  `PostConversationTurn`; resolution stays in the composition root (ADR-0007;
  the fitness gate `check_boundaries.py` guards the layering).
- **Quiz/card deps**: `get_card_generation`, `get_explain_generation`,
  `build_quiz_adapter` must not gain preference args — HP-04 is testable via
  mutation (a shared-resolution mutation must not move these paths).
- **DELETE idempotency**: `DELETE` on an unset preference is 204, not 404
  (HP-09).

## Phase plan (workers)

1. **Docs**: ADR-0020 follow-up amendment + ROADMAP row + STATE AD rows
   (planning artifacts + docs in their own commits).
2. **Backend kernel**: migration + entity + port + adapter + resolution builder
   + composition seam + ask/teach wiring + db-gated and unit tests.
3. **API + copy**: profile fields + catalog + routes + MeResponse + tests.
4. **Frontend**: client lib + AccountPanel section + tests.
5. **Verifier**: fresh subagent (spec-anchored outcome check + discrimination
   sensor + validation.md).
