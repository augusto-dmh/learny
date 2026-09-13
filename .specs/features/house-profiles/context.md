# House Profiles — Context (auto-decisions under the ship-cycle rule)

Every decision below was made autonomously per the learny-ship-cycle auto-decision
rule: option sets with why-recommend AND why-not, recommended option chosen,
recorded here and as AD-3xx rows in `.specs/project/STATE.md` for audit without
this conversation. Escalation rule checked: none of these change product direction
beyond the recorded slice (the slice itself was recorded twice in the handoff —
PR #69 and PR #70 entries — and recommended by the accepted 2026-09-07 research).

## D-1 — Cycle shape: build now, citing the 2026-09-07 research; no new research doc → AD-350

- **Options:**
  - *Build cycle citing existing research (chosen).* Why recommend: the slice was
    researched and recorded twice (research doc §3.2 Flavor A; handoffs of PR #69
    and #70); its precondition (router + per-profile pricing) shipped in Cycle G;
    another docs-only cycle would stall a recorded, unblocked slice. Why not: a
    fresh research pass could surface new provider/UX facts — but the slice is
    provider-agnostic (it wires preference + resolution, not a vendor).
  - *Research-only cycle, build later.* Why: mirrors `v3-notes-research` (D before
    E/F). Why not: that split existed because E–F were gated on an unwritten
    domain ADR; here the amendment is a follow-up to an accepted amendment with
    the twelve inputs already answered.
  - *Full RFC first.* Why: end-user choice is product surface; an RFC would weigh
    pricing (RQ10). Why not: RFC-0007's research already scoped exactly this
    one-cycle slice and deferred only BYO + pricing to a future RFC; re-litigating
    it per cycle contradicts the recorded handoffs.
- **Choice:** build now; ADR-0020 gains a follow-up amendment as the decision
  record; the 09-07 docs are cited as the research evidence.

## D-2 — Choice scope: one preference, Ask/Teach turn generation only → AD-351

- **Options:**
  - *One preference; Ask/Teach turns only (chosen).* Why recommend: matches the
    recorded slice verbatim ("a per-user preference row + two-tier adapter
    resolution"); quiz decks pin provider at `begin_deck` and the quiz port sits
    outside the registry — wiring it in risks the exact foreign-vendor-poll bug
    Cycle G fixed, for zero recorded demand. Why not: a user on the economy
    profile still generates cards/quizzes at house cost — but card/quiz spend is
    already metered and capped at the house level, and per-user quiz routing is a
    coherent follow-up if demand appears.
  - *Include quiz + card paths.* Why: consistency ("my profile everywhere"). Why
    not: deck handles pin a provider string, not a profile id; mid-flight
    semantics are undefined; `QuizDeckHandle` schema churn for no recorded need.
  - *Per-mode preferences (ask profile ≠ teach profile).* Why: maximal control.
    Why not: two rows/two selectors for a choice the catalog can't currently
    distinguish in value; the recorded slice names one row.
- **Choice:** one preference per user; applies to Ask/Teach turn generation
  (the `RoutingGenerationAdapter` surface) only. Explain chain, quiz, cards stay
  house-routed (HP-04).

## D-3 — Resolution semantics: reorder with fail-over preserved, never a hard pin → AD-352

- **Options:**
  - *Chosen profile leads; default chain follows deduped (chosen).* Why
    recommend: keeps the shipped trust features intact — transport fail-over,
    rate-limit backoff, stream-before-first-delta bound (ADR-0020 amendment
    ¶5–6) — while honoring the choice whenever the chosen profile can serve the
    mode; budget stays honest because answers stamp the serving profile and the
    debit resolves that catalog (HP-05). Why not: a failing chosen profile
    silently serves from another — mitigated by the stamps and by only offering
    mode-eligible profiles in the catalog.
  - *Hard pin (chosen profile only; honest failure on its outage).* Why: purest
    "you get what you picked". Why not: punishes the learner for house
    infrastructure failure and contradicts the router's design intent; the
    operator default doesn't behave that way either.
  - *Per-user effort overrides beside the profile.* Why: finer control. Why not:
    ADR-0020 amendment ¶4 makes effort a profile value; dials beside profiles
    re-opens what the amendment closed.
- **Choice:** reorder semantics (HP-03). Unset / unknown / removed / mode-
  ineligible stored ids all collapse to exactly the operator default chain
  (HP-03, HP-14; stale-id resilience is AD-355).

## D-4 — Learner-visible copy: optional `display_name` + `description` on the profile → AD-353

- **Options:**
  - *Optional `display_name`/`description` fields on `GenerationProfileSettings`
    (chosen).* Why recommend: honest degradation copy ("economy: answers may cite
    less precisely") is the operator's judgment call — the exact rationale the
    research gives for degradation UX (§3.2 Flavor A item 4); optional fields
    keep existing env JSON parsing under `extra="forbid"` byte-identical (HP-11).
    Why not: settings JSON grows two fields operators may leave empty — the UI
    fallback (id / hidden copy) covers that.
  - *Derive copy from `grounding`/effort enums.* Why: zero new config. Why not:
    enums can't say "US-hosted open weights" or why citations may be less
    precise; templated copy would be generic to the point of dishonesty.
  - *Separate catalog config surface.* Why: copy without touching profile
    settings. Why not: two sources of truth for the same registry; the registry
    is already the single declaration point (AD-344 lineage).
- **Choice:** two optional fields; empty `display_name` falls back to id in the
  API payload; empty `description` hides the copy line (HP-08, HP-11).

## D-5 — API shape: catalog resource + choice subresource; MeResponse grows the id → AD-354

- **Options:**
  - *`GET /api/ai/profiles` + `GET/PUT/DELETE /api/me/ai-profile` + `MeResponse
    .ai_profile_id` (chosen).* Why recommend: catalog and choice are different
    resources with different caches/owners; `MeResponse` currently carries no
    mutable state, so the account page gets the choice id on its existing first
    paint without an extra roundtrip. Why not: one more router file.
  - *Fold both into the auth router under `/api/auth/me`.* Why: fewer files. Why
    not: AI serving config is not auth; the auth router is the wrong neighborhood
    as the surface grows.
  - *`PATCH /api/me` generic preferences endpoint.* Why: future-proof for more
    preferences. Why not: invents a generic mechanism for one field; no such
    endpoint exists today (survey §6); generic preference bags resurrect exactly
    the AD-147 tension this cycle is carefully scoping.
- **Choice:** the two-resource shape (HP-08…HP-10). Unknown id on PUT → 422 with
  a detail naming the problem; DELETE is idempotent 204 (HP-09).

## D-6 — Selector visibility honesty: hidden when the deployment offers no choice → AD-356

- **Options:**
  - *Hidden unless ≥1 selectable non-default profile is declared (chosen).* Why
    recommend: the product's honesty culture (empty-deck honesty, library
    honesty); a permanently-single-option selector is dead UI, and today every
    deployment ships inert-economy or nothing — so most deployments should see
    nothing until the operator's eval-gated enablement. Why not: discoverability
    — nobody learns the feature exists — acceptable: it appears exactly when the
    operator turns it on.
  - *Always visible with a single "Default" row.* Why: stable UI. Why not: dead
    control in every current deployment; implies a choice that does not exist.
- **Choice:** visibility rule (HP-12); "selectable" = declared in the registry
  (the synthetic legacy seed never appears — HP-08). Resolution of the wording
  tension with AD-355 ("≥1 selectable **non-default** profile"): HP-12 governs —
  the section is visible iff the catalog is non-empty. The catalog contains only
  declared non-seed profiles, so a sole entry IS the operator default and
  choosing it is an accepted no-op (the honest machinery still works end to
  end); tightening the rule to two entries would hide a *meaningful* choice in
  mixed registries where one declared entry is not the primary.

## D-7 — Stale persisted profile: fall back to operator default, never error → AD-356

- **Options:**
  - *Resolve to operator default + log warning; UI renders unset (chosen).* Why
    recommend: operators rename/remove profiles; a learner's stored choice must
    never break asking (the retrieval cycle's fail-closed lesson applies to
    *evidence bounds*, not preference convenience — a missing profile is not a
    correctness invariant, it is a stale hint). Why not: silence could confuse —
    mitigated by the UI rendering unset (HP-14) so the learner can re-choose.
  - *Reject turns until the user re-chooses.* Why: forces freshness. Why not:
    converts an operator config edit into user-facing breakage; unacceptable.
- **Choice:** stale ids collapse to the default chain with a warning (HP-03);
  PUT validates against the current registry so new typos never persist (HP-09).

## Environment facts (for workers and the verifier)

- No Docker in this WSL session → no local Postgres/Redis; db-gated tests
  (`LEARNY_TEST_DATABASE_URL` unset) skip locally. CI's `backend-test` job is the
  authority for HP-01/HP-02 and other requires_db coverage. Do not weaken,
  skip, or fake these tests to make a local gate look green.
- Autouse `_force_local_providers` (backend/tests/conftest.py) pins provider env
  to `local` and clears `get_settings.cache_clear()`; any new process-level cache
  introduced for per-user chains must be registered for the same clearing or
  keyed so tests cannot leak adapters across settings (design.md §risks).
- Gates: `cd backend && uv run pytest`, `uv run ruff check . && uv run ruff
  format --check .`, `python3 backend/scripts/check_boundaries.py`; `cd frontend
  && npm test`, `npx tsc --noEmit`.
