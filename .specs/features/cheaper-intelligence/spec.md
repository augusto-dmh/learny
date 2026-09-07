# Cheaper Intelligence Specification (RFC-0007 Cycle G / Bet 7)

Scope source: `docs/research/2026-09-07/` (README synthesis + `provider-adapter-architecture.md`
prerequisite order + §4 amendment checklist), `docs/rfc/0007-public-launch-roadmap.md` §Cycle G.
Run shape: **single cycle**, **ADR-0020 amendment first** (owner call, 2026-09-07).

## Problem Statement

Every generation surface bills Anthropic Sonnet 5 list prices (~$1,100/month at ~50k cited
turns), the adapters raise untyped errors so no routing decision can be made on them, and the
quiz batch poll path would poll a foreign vendor if the operator ever changed providers
mid-deck. The roadmap row promises cheaper intelligence at the same trust: effort/cache cost
moves, an eval-gated economy tier, and an outage fallback — but the research shows the order is
load-bearing: taxonomy → provider pinning → per-profile pricing → router → eval gate → cost moves.

## Goals

- [ ] ADR-0020 amended (accepted) before any routing/fallback code lands.
- [ ] The six prerequisite items from the 2026-09-07 architecture doc ship in order, in one cycle.
- [ ] Measured, judge-gated cost moves: per-mode effort, teach cache reorder, Haiku selection-Explain.
- [ ] An OpenAI-compatible adapter + first economy profile (Fireworks-US GLM-5.3-Flash), inactive
      until a green nightly promotes it.

## Out of Scope

| Feature | Reason |
|---|---|
| BYO API keys (Flavor B) | 3+ cycles + crypto + security review; gated on a paid tier (RQ10); explicitly scoped out of the ADR-0020 amendment |
| Curated per-user house profiles (Flavor A) | One cycle *behind* the router; recorded as the next cycle |
| Model-picker UI | RFC Cycle G exclusion |
| Embedding-provider swap | ADR-0019 stands (dimensions not portable; switch = full re-embed) |
| Semantic answer caching | RFC Cycle G exclusion |
| Subscription-as-API (GLM Coding Plan, OAuth bridges, free tiers) | Prohibited by provider terms; dead end per `subscription-as-api.md` |
| Cross-provider quiz-deck routing | A half-submitted batch has no portable second home; deck path pins at `begin_deck` |
| Automated promotion (auto-reorder on green nightly) | Promotion is a recorded operator act, not code |
| Gemini / DeepSeek / MiniMax profiles | The adapter kind + registry make them config-only later; one concrete economy profile this cycle |
| Startup-credit applications | Owner action, not code |

---

## Assumptions & Open Questions

Every ambiguity is resolved or recorded here — nothing is left silently unclear. Decisions made
under the ship-cycle auto-decision rule (options + recommendation recorded in `context.md`,
AD rows in STATE.md).

| Assumption / decision | Chosen default | Rationale | Confirmed? |
|---|---|---|---|
| One cycle vs G1/G2 split | Single cycle (all six prerequisites + adapter + profile) | Owner invocation 2026-09-07 | y |
| Amendment vehicle | Amend ADR-0020 in place (new amendment section) | Roadmap row says "ADR-0020 amendment first"; no superseding-ADR precedent in `docs/adr/` | y |
| First economy host | Fireworks-US-hosted GLM-5.3-Flash, declared inactive | US-hosted open weights satisfies the RFC exclusion ("no CN first-party inference; US-hosted fallback only") at the price floor (~$0.22/$0.75 w/ surcharge); Gemini deferred (2027 price doubling, training-tier caveats) but remains a config-only add | y |
| `effort` placement | Adapter constructor arg fed per profile (per-mode values on the profile); port never grows an effort argument | Status quo shape (`answering/anthropic.py`); research §4 Q4 | y |
| Ask effort default at merge | Stays `medium`; flip to `low` is the operator's post-merge act gated on a green candidate nightly | RFC: "effort=low on Ask, judge-gated" — the gate precedes the flip | y |
| Selection-Explain routing marker | Ask request grows an explicit origin marker (frontend sends it from the capture-popover Explain verb) | Backend cannot otherwise distinguish the verb; mirrors the existing `origin=tutor` pattern | y |
| Suggest/accept metering | USD debit only; **no** new integer caps on suggest paths | DOOR-08 named ask/teach caps only; inventing caps is scope creep | y |
| Legacy provider settings | `generation_provider`/`generation_model`/`generation_effort` remain recognized and seed the default registry; the registry is the single source of truth when declared | Keeps .env/compose/deploy docs working; offline default untouched | y |
| Incumbent primary promotion status | Sonnet primary grandfathered as grounded-eligible; new profiles are Ask-ineligible until their green nightly | The amendment adds tiers; it does not re-litigate the primary | y |

**Open questions:** none — all resolved or logged above.

---

## User Stories

### P1: ADR-0020 amendment accepted first ⭐ MVP

**User Story**: As the operator, I want ADR-0020 amended before routing exists so the fallback
tier is governed by an accepted decision, not discovered in production.

**Why P1**: RFC Cycle G: "The fallback adapter requires an accepted amendment to ADR-0020 before
Cycle G's fallback work begins." The roadmap row itself says "ADR-0020 amendment first".

**Acceptance Criteria**:

1. AMD-01: WHEN the routing/fallback work begins THEN `docs/adr/0020-*.md` SHALL carry an
   **Accepted** amendment section answering the twelve decision inputs (research §4): Claude
   stays the Ask/Teach primary; the second adapter lands with the first concrete profile;
   degradation is declared per-profile via capability flags (never a port method, never a runtime
   probe); effort stays a constructor parameter fed per profile; turn-path fallback obeys the
   streaming rule; the deck path pins its provider at `begin_deck`; the error taxonomy defines
   cross-provider retryability; spend uses per-profile price catalogs; promotion is eval-gated
   process; the rails apply to every profile; embeddings do not diversify; end-user choice is
   explicitly deferred (curated profiles = future cycle, BYO keys = pricing-gated roadmap); and
   the ADR-0009 line is restated for the new surface (no routing frameworks in the composition
   root, user-supplied endpoints never a configuration input).

**Independent Test**: ADR diff shows the amendment section with all twelve answers; no fallback
commit precedes it in the branch history.

---

### P1: Learny-owned provider error taxonomy ⭐ MVP

**User Story**: As the router, I need typed provider errors so fallback decisions are made on
classes, not on string-matching exceptions.

**Why P1**: Prerequisite 1 — today everything raises untyped; the only classification is a
logging side-channel.

**Acceptance Criteria**:

1. TAX-01: WHEN a provider call exceeds the adapter's wall-clock bound THEN the adapter SHALL
   raise a Learny-owned `Timeout` error (bounds anchored at the adapters' existing timeouts:
   generate 120s, suggest 30s).
2. TAX-02: WHEN the provider returns 429 THEN the adapter SHALL raise `RateLimited`; WHEN 5xx /
   overloaded / unavailable THEN `ProviderUnavailable`; WHEN a 4xx shape/auth/validation
   rejection THEN `RequestRejected` — each translated **inside** the adapter that owns the SDK.
3. TAX-03: WHEN the application service observes any of these THEN caller-visible behavior SHALL
   be unchanged (`AnswerGenerationFailed` mapping and error envelopes exactly as today) — the
   taxonomy is routing metadata, not a new user-facing surface.
4. TAX-04: WHEN the deterministic local adapter runs THEN its failure behavior SHALL be unchanged
   (it touches no network and raises no taxonomy errors).

**Independent Test**: Stubbed-transport unit tests drive each class through the Anthropic (and
later OpenAI-compatible) adapter and assert the raised Learny type.

---

### P1: Quiz batch polls pinned to the handle's provider ⭐ MVP

**User Story**: As the operator, I want an in-flight deck to finish on the provider that started
it so a mid-flight config flip can never poll vendor B with vendor A's batch id.

**Why P1**: Prerequisite 2 — `QuizDeckHandle.provider` exists but nothing reads it; this is the
hidden risk blocking any routing at all.

**Acceptance Criteria**:

1. PIN-01: WHEN a deck poll task collects a batch THEN it SHALL build the quiz adapter for the
   provider recorded on the handle, not from current settings.
2. PIN-02: WHEN the handle names a provider the current configuration no longer declares THEN the
   job SHALL fail terminally with an operator-actionable reason — never silently poll a foreign
   provider.
3. PIN-03: WHEN a deck begins THEN the handle SHALL carry the beginning provider's identity
   through Celery JSON round-trips (existing field, now load-bearing and under test).

**Independent Test**: A poll task test with a handle naming provider X while settings declare
provider Y asserts the adapter is built for X (and the terminal path for an undeclared X).

---

### P1: Per-profile price catalogs + honest metering ⭐ MVP

**User Story**: As the operator, I want each learner's day debited at the prices of the profile
that actually served them, with cache and suggest usage counted, so the ledger is honest under
routing.

**Why P1**: Prerequisite 3 — the single `price_*` triple over-charges economy traffic into the
daily cap and under-charges premium fallback; the RFC's ledger bullet requires tokens
(thinking included) and USD.

**Acceptance Criteria**:

1. PRICE-01: WHEN a successful generation call is debited THEN the USD SHALL be computed from
   the serving profile's price catalog, not a single global pair.
2. PRICE-02: WHEN a provider reports cache-read / cache-creation tokens THEN the debit SHALL
   price them at the profile's cache prices; WHEN no cache fields are reported THEN the debit
   SHALL be input+output only (TokenUsage grows optional cache fields; Anthropic adapter
   populates them from usage).
3. PRICE-03: WHEN a suggest/accept provider call completes (selection cards, tutor-card
   suggest/accept) THEN the ledger SHALL debit its usage like turn paths — USD only, no new
   integer caps.
4. PRICE-04: WHEN the serving profile cannot be resolved from a result (unknown model) THEN the
   debit SHALL fall back to the primary profile's catalog **and** log a warning — never a silent
   misprice.
5. PRICE-05: WHEN embeddings are debited THEN pricing SHALL be unchanged (single house embedding
   provider; ADR-0019).

**Independent Test**: Budget tests debit the same TokenUsage through two profiles and assert
different micros; a cache-field usage asserts the cache-priced debit; a suggest call asserts a
ledger row.

---

### P1: Profile registry + routing adapter ⭐ MVP

**User Story**: As the operator, I want a settings-declared ordered profile registry behind one
routing adapter so fallback/effort/caching are configuration, and the application never learns
routing exists.

**Why P1**: Prerequisite 4 — the ADR-0007 shape ("fallback routing under Learny's control"), no
framework (ADR-0009).

**Acceptance Criteria**:

1. ROUTE-01: WHEN the turn-path generation adapter is built THEN it SHALL be the routing adapter
   over the settings-declared ordered profile registry; each profile declares kind
   (`local | anthropic | openai-compatible`), model, base URL (where applicable), API-key
   **env-var name**, per-mode effort values, max_tokens, its own price catalog, and capability
   flags (grounded eligibility for Ask/Teach).
2. ROUTE-02: WHEN the serving profile raises `Timeout` or `ProviderUnavailable` THEN the router
   SHALL attempt the next eligible profile; WHEN `RateLimited` THEN one same-provider backoff
   retry, then the next eligible; WHEN `RequestRejected` THEN no blind cross-provider retry (only
   a profile whose adapter builds a different request shape may be tried).
3. ROUTE-03: WHEN a grounded turn (ask; teach per its carve-outs) is served THEN only
   grounded-eligible profiles may serve it; WHEN none is reachable THEN the turn SHALL fail
   honest (not-found / `AnswerGenerationFailed`) — never a silently degraded answer (AD-027 /
   AD-295 intact).
4. ROUTE-04: WHEN a stream has emitted its first delta THEN the router SHALL NOT fail over;
   fail-over is only legal before the first delta, after which errors surface exactly as today.
5. ROUTE-05: WHEN a declared profile's key env var is missing at composition THEN startup SHALL
   fail fast (current factory discipline, extended to the registry).
6. ROUTE-06: WHEN no registry is declared THEN behavior SHALL equal today's single-provider
   configuration (legacy settings seed the default registry; `local` default and the offline
   suite untouched).
7. ROUTE-07: WHEN any profile serves a turn THEN the budget assert, user-keyed rate limits, and
   the kill switch SHALL apply unchanged **before** any provider touch — rails are per-user, not
   per-profile.
8. ROUTE-08: WHEN a fallback fires (or any profile serves) THEN the outcome SHALL identify the
   serving profile/model so spend mapping and logs attribute correctly.

**Independent Test**: A fake two-profile chain drives each error class through the router
(buffered and streaming, before/after first delta) and asserts chain behavior, honest failure,
and attribution.

---

### P1: Eval-gated promotion ⭐ MVP

**User Story**: As the operator, I want a candidate profile judged by the existing nightly
before it can serve Ask so promotion is evidence, not hope.

**Why P1**: Prerequisite 5 — the mechanics exist (`generation_model` recorded per case, nightly
cron, threshold assert); they need to fit the registry.

**Acceptance Criteria**:

1. EVAL-01: WHEN the nightly eval records a case THEN the JSONL SHALL identify the serving
   profile id and model; the aggregate thresholds assert unchanged (faithfulness ≥ 0.90,
   relevancy ≥ 3.1, `citation_valid` 12/12).
2. EVAL-02: WHEN an operator runs the eval against a candidate profile (env-driven override) THEN
   production defaults SHALL be untouched — promotion is the registry-reorder commit after a
   green nightly, recorded in STATE.md.
3. EVAL-03: WHEN a profile has no green nightly THEN the shipped configuration SHALL mark it
   Ask-ineligible (the incumbent primary is grandfathered).

**Independent Test**: Judge/eval tests assert the profile fields land in the JSONL case and the
gate predicate still flips on a below-threshold aggregate.

---

### P1: rq15 cost moves as profile values ⭐ MVP

**User Story**: As the operator, I want the already-spec'd cost levers (effort diet, teach cache
reorder, Haiku selection-Explain) to land as profile values so the bill drops without touching
the trust contract.

**Why P1**: The roadmap row's "effort/cache" deliverables, per the research's step 6.

**Acceptance Criteria**:

1. COST-01: WHEN a turn is served THEN effort SHALL come from the serving profile's per-mode
   value (ask/teach may differ); the port SHALL NOT grow an effort argument; shipped defaults
   preserve current behavior (`medium`) — the Ask→`low` flip is the operator's judge-gated
   post-merge act.
2. COST-02: WHEN a teach prompt is assembled THEN stable per-section documents SHALL sit before
   the cache breakpoint (adapter-internal reorder), with the teach playbook contract and
   grounding behavior unchanged.
3. COST-03: WHEN an Anthropic generation call completes THEN cache-read / cache-creation token
   counts SHALL be captured (log + metering via PRICE-02) so the reorder's saving is measured,
   not assumed.
4. COST-04: WHEN an ask-mode turn carries the selection-Explain origin marker THEN the router
   SHALL serve it from the designated cheap grounded profile (Haiku 4.5); WHEN that profile
   raises a transport-class error THEN the turn SHALL fall back to the Ask primary.
5. COST-05: WHEN Explain is served from the cheap profile THEN citations and grounding SHALL
   behave identically to any ask turn (same port contract, AD-027 backstop).

**Independent Test**: Prompt-assembly test asserts document/breakpoint order on teach; an
origin-marked turn test asserts cheap-profile selection and transport-error fallback; grounding
tests unchanged and green.

---

### P1: OpenAI-compatible adapter + first economy profile ⭐ MVP

**User Story**: As the operator, I want a real OpenAI-compatible adapter and a declared
Fireworks-US GLM-5.3-Flash profile so the economy tier exists — inactive until a green nightly
promotes it.

**Why P1**: The roadmap row's "fallback" deliverable; research §4 Q2: add the second adapter
with the first concrete profile, not speculatively.

**Acceptance Criteria**:

1. ECON-01: WHEN the registry names an `openai-compatible` profile THEN turns SHALL be served by
   a new Learny-owned adapter implementing `GenerationPort` (Learny DTOs in/out; the port gains
   no new members).
2. ECON-02: WHEN it serves an answer-mode turn THEN it SHALL request prompt-id citations
   (`[^n]` markers into supplied documents) and the existing grounding intersection SHALL verify
   them; its capability flags SHALL declare the degraded grounding (Ask-ineligible until
   promoted).
3. ECON-03: WHEN it reports usage THEN input/output (plus cache fields when the host provides
   them) SHALL map into `TokenUsage`; WHEN it reports none THEN the debit is 0 (existing rule).
4. ECON-04: WHEN the first economy profile is declared THEN it SHALL ship **inactive**
   (Ask-ineligible, non-default, outage-eligible only after promotion) with its price pair and
   key env-var name in config.
5. ECON-05: WHEN a profile's effort value cannot be expressed on its adapter kind THEN the
   adapter SHALL ignore it (declared degradation — no error, no port change).
6. ECON-06: WHEN CI runs THEN the new adapter SHALL be exercised via stubbed transport only —
   the offline suite stays network-free (provider-pinned conftest discipline).

**Independent Test**: Contract tests drive the adapter through generate / generate_stream /
taxonomy translation / usage extraction with a stubbed HTTP layer.

---

## Edge Cases

- WHEN the registry is misconfigured (duplicate profile ids, empty chain, unknown kind, missing
  key env) THEN composition SHALL fail fast with an actionable message — never a silent
  single-profile downgrade.
- WHEN the chain is only `local` THEN routing SHALL be a pass-through (CI/offline behavior
  byte-identical).
- WHEN a stream errors after the first delta THEN the SSE contract SHALL surface the error
  exactly as today (no rewind, no second `AnswerCompleted`).
- WHEN a deck is mid-flight and its provider is removed from config THEN the job SHALL fail
  terminally per PIN-02.
- WHEN two profiles name the same model THEN price resolution SHALL be unambiguous (the router
  stamps the serving profile on the result; design pins the mechanism).
- WHEN the operator flips profiles between a stream-open and its commit THEN the in-flight turn
  SHALL complete on the profile that opened it (adapters are built per chain at composition;
  no mid-turn re-resolution).
- WHEN `answer` mode on a non-grounded profile would have been "cheaper" THEN the router SHALL
  still refuse it (honest failure beats silent degradation — rq14's product-killer warning).

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
|---|---|---|---|
| AMD-01 | P1: ADR amendment | Design | Pending |
| TAX-01..04 | P1: Error taxonomy | Design | Pending |
| PIN-01..03 | P1: Quiz poll pinning | Design | Pending |
| PRICE-01..05 | P1: Per-profile pricing + metering | Design | Pending |
| ROUTE-01..08 | P1: Registry + router | Design | Pending |
| EVAL-01..03 | P1: Eval-gated promotion | Design | Pending |
| COST-01..05 | P1: rq15 cost moves | Design | Pending |
| ECON-01..06 | P1: OpenAI-compat adapter + economy profile | Design | Pending |

**Coverage:** 35 total, 35 mapped to tasks (below), 0 unmapped.

---

## Success Criteria

- [ ] All gates green: ruff, backend pytest, frontend build/tests — offline, no new network need.
- [ ] Verifier PASS with per-AC evidence and killed discrimination mutants.
- [ ] ADR-0020 amendment accepted and precedes all routing commits in history.
- [ ] Nightly eval unaffected at merge (primary profile behavior unchanged: effort `medium`,
      Sonnet pricing, existing thresholds).
- [ ] The economy profile is declared but provably inert (Ask-ineligible, non-default).
