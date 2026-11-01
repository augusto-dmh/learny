# installable-and-adult-launch checks

Profile: standard
Plan: `.specs/features/installable-and-adult-launch/plan.md`

20 checks in 2 slices · 2 one-way doors · 0 open

Proof commands run from the worktree root and are written below in their runnable form; backend DB proofs read `LEARNY_TEST_DATABASE_URL` and `LEARNY_REQUIRE_DB` from the environment (this lane's Postgres on 5438 hosts `learny_test`, Redis on 6384); the backend proofs inherit `LEARNY_REQUIRE_DB=1` and `LEARNY_TEST_DATABASE_URL` from the invoking shell — never an inline POSIX env prefix, which Windows cmd cannot run. Frontend proofs must run under Node 24 (the machine default 25 breaks jsdom `localStorage` in vitest workers; CI on Node 20 is unaffected). Vitest proofs may name shared test files with `-t` filters.

Mutations: 3
Build: cd backend && uv run ruff check . && uv run ruff format --check . ; cd frontend && npx tsc --noEmit ; cd frontend && npx vitest run tests/i18n-copy.test.ts ; python backend/scripts/check_commits.py origin/main..HEAD

## Checks

### S1 - installable, offline, low-bandwidth · batch A · ~70k

**C1** - The app serves a web app manifest declaring `name`, `short_name`, `start_url: "/"`, `display: "standalone"`, icons at 192px and 512px with one `any` and one `maskable` purpose, and the document links it (AC 1)
Proof: `cd frontend && npx vitest run tests/pwa-install.test.tsx -t "manifest declares the installable shape and the document links it"`

**C2** - The app shell registers the service worker at `/sw.js` with `{ type: "module" }`, and `/sw.js` exists as a static asset (AC 2)
Proof: `cd frontend && npx vitest run tests/pwa-install.test.tsx -t "registers the service worker module at /sw.js"`

**C3** - A signed-in learner's 200 `GET /api/sources/{id}/chapter*` and `GET /api/sources/{id}/structure` responses are stored network-first in that learner's reader cache, and the cache names one user per name (AC 3)
Proof: `cd frontend && npx vitest run tests/offline-cache-policy.test.ts -t "caches chapter and structure reads in the reading user's cache"`
Proof: `cd frontend && npx vitest run tests/offline-cache-policy.test.ts -t "names one reader cache per user id"`

**C4** - Offline, the service worker serves the cached chapter/structure response; with no cached entry it propagates the failed network request honestly - no fabricated book content (AC 4)
Proof: `cd frontend && npx vitest run tests/offline-cache-policy.test.ts -t "serves the cached chapter when the network is gone and fails honestly without one"`

**C5** - A request that is not a same-origin GET, or is not the chapter/structure pattern, passes through uncached: every other `/api/` response, every write, every cross-origin request (AC 5)
Proof: `cd frontend && npx vitest run tests/offline-cache-policy.test.ts -t "never caches writes, other api reads, or cross-origin requests"`

**C6** - When the signed-in user changes (logout, or a different learner signs in), every reader cache not belonging to the current user is deleted; the same user re-posted purges nothing (AC 6)
Proof: `cd frontend && npx vitest run tests/offline-cache-policy.test.ts -t "purges every other learner's reader cache when the user changes"`

**C7** - While data saver is active (browser `Save-Data`, or the reader control on) the reader does not request book figures and shows the low-bandwidth notice, with copy in both catalogs (AC 7)
Proof: `cd frontend && npx vitest run tests/data-saver.test.tsx -t "hides book figures and shows the notice while data saver is active"`

**C8** - Toggling Data saver in the reading-controls popover applies immediately, persists device-local across reloads, and an explicit Off overrides a browser `Save-Data` signal (AC 8)
Proof: `cd frontend && npx vitest run tests/data-saver.test.tsx -t "persists the toggle and applies it immediately, and Off overrides Save-Data"`

### S2 - adults only, legal in Portuguese, a capped guest Ask · batch B · ~85k

**C9** - A register request without `age_attested` (absent or false) is refused with 422 and creates no user, credential, session, or invite consumption - even with a valid email, a valid password, and `accepted_tos: true` (AC 9)
Proof: `cd backend && uv run pytest tests/test_web_auth_age.py -k "refuses_register_without_the_age_attestation"`

**C10** - A register request with `accepted_tos: true` and `age_attested: true` creates the account and session exactly as before (AC 10)
Proof: `cd backend && uv run pytest tests/test_web_auth_age.py -k "registers_with_the_attestation_as_before"`

**C11** - The register form shows a required 18-or-older confirmation beside the terms checkbox, with copy from both catalogs (AC 11)
Proof: `cd frontend && npx vitest run tests/auth-screens.test.tsx -t "register requires the 18-or-older confirmation in both locales"`

**C12** - `/privacy`, `/terms` and `/copyright` render their full content from the catalogs in the negotiated locale (both catalogs carry every section), the legal-pages exemption in the hard-coded-string sensor is removed, the privacy page carries the LGPD data-subject-rights section and an international-transfer note, and the terms state the 18+ requirement (AC 12)
Proof: `cd frontend && npx vitest run tests/legal-pages.test.tsx -t "carries the LGPD rights list, the transfer note, and the ANPD route"`
Proof: `cd frontend && npx vitest run tests/legal-pages.test.tsx -t "render the pt-BR catalogs: headings, the rights list, and the age line"`
Proof: `cd frontend && npx vitest run tests/i18n-hardcoded.test.ts -t "the source tree is clean"`

**C13** - A signed-out visitor posting a question to `POST /api/sample/ask` gets 200 with a grounded answer, citations, and `sample: true`, with no user, session, conversation, turn, or activation-event row created; the requested language reaches the generation port while citations stay verbatim; a generation failure answers 502 with the generic body (AC 13)
Proof: `cd backend && uv run pytest tests/test_web_sample_ask.py -k "guest_askes_the_sample_grounded_without_an_account"`

**C14** - An empty or over-ceiling guest question is refused 422 before any retrieval, generation, or budget spend (AC 14)
Proof: `cd backend && uv run pytest tests/test_web_sample_ask.py -k "refuses_an_empty_or_oversized_question_before_any_spend"`

**C15** - When the per-IP guest ask cap for the window is spent, the endpoint answers 429 with `Retry-After`, keyed on the trusted-proxy client IP + route so different visitors get separate budgets and header tricks mint nothing (AC 15)
Proof: `cd backend && uv run pytest tests/test_web_sample_ask.py -k "rate_limits_guest_asks_per_client_ip"`

**C16** - When the sample's daily budget is spent (USD at cap or ask count reached), the refusal is the honest 429 exhausted outcome before generation; with the operator kill switch on it is 503 (AC 16)
Proof: `cd backend && uv run pytest tests/test_web_sample_ask.py -k "refuses_honestly_when_the_sample_budget_is_gone"`

**C17** - A missing sample source answers 503; a generation that grounds nothing answers 200 with `found: false` and no citations - the same grounding contract as every Ask (AC 17)
Proof: `cd backend && uv run pytest tests/test_web_sample_ask.py -k "answers_the_honest_outcomes_for_a_missing_sample_or_nothing_grounded"`

**C18** - A successful guest ask debits the sample's own daily ledger row (assert before, record after: USD at the serving profile's prices plus the ask count) and writes nothing else; a refused call debits nothing (AC 18)
Proof: `cd backend && uv run pytest tests/test_web_sample_ask.py -k "debits_the_sample_ledger_only_after_success"`

**C19** - The landing page offers the sample ask to a signed-out visitor: question input prefilled with the sample's suggested question, a visible shared-sample label, the submit gesture rendering the cited answer, and catalog copy for the refusals in en and pt-BR (AC 19)
Proof: `cd frontend && npx vitest run tests/landing-sample-ask.test.tsx -t "offers the sample ask and labels the answer as the shared sample"`

## Coverage

| Set (size) | Member -> proof | Unproven |
| --- | --- | --- |
| `POST /api/sample/ask` statuses (6) | 200 C13 · 422 C14 · 429 limiter C15 · 429 budget C16 · 503 sample/paused C16, C17 · 502 C13 | - |
| `POST /api/auth/register` with the attestation (2) | 201 both-true C10 · 422 absent/false C9 | - |
| SW fetch decisions (5) | chapter/structure GET cached C3 · non-matching same-origin GET passthrough C5 · write/cross-origin passthrough C5 · offline fallback C4 · no-entry honest failure C4 | - |
| auth change on a shared device (3) | logout purges C6 · different learner purges C6 · same user re-posted keeps C6 | - |
| data saver states (3) | `Save-Data` on C7 · control on C7, C8 · control Off overrides C8 | - |
| legal pages (3) | `/privacy` C12 · `/terms` C12 · `/copyright` C12 | - |
| guest caps (3) | question ceiling C14 · per-IP window C15 · daily budget C16 | - |
| manifest icon entries (2) | `any` 192/512 C1 · `maskable` 192/512 C1 | - |
| Landing door 1: the guest route shape (7) | 200 C13 · 422 C14 · 429 C15 · 429 budget C16 · 503 C17 · 502 C13 · body `{found, answer, citations, sample}` C13 | - |
| Landing door 2: the sample operator ledger identity (1) | debit to the sample operator's row C18 | - |

## Swept

- validation: C14 (question ceiling at the boundary, before any spend), C1 (manifest fields), C5 (SW URL matcher)
- failure modes: C4 (offline without an entry fails honestly), C13 (generation failure 502, generic body), C16 (budget exhausted honest 429), C17 (missing sample 503)
- idempotency: n/a - each guest ask is a distinct spend; a retried POST costs its cap slot, which is the guard
- authorization: C9 (attestation gate before any write), C15 (per-IP limiter on the trusted proxy IP), C6 (no other learner's cache survives a user change), C13 (guest reads only the sample through `readable_source`, no activation row for a guest)
- concurrency: C15 (fixed-window limiter), C18 (ledger day row written atomically by the existing spend repository)
- data lifecycle: C6 (cache purge on user change), C3 (entry cap keeps the reader cache bounded), C18 (ledger rows are day-scoped by the existing table)
- dependency failure: C17 (sample missing), existing - limiter failure fails closed 503 (`_hit`), Redis-backed limiter shared with the auth rails
- state transitions: n/a - no entity changes state in this cycle
- observability: existing - one content-free log line per completed ask mirrors the conversation-turn convention; no metric or log requirement is new

## Handoff

- **Batches (owner decision D2):** S1 ~70k + S2 ~85k = ~155k over the 150k budget, so the build splits at the slice boundary into two sequential PRs: batch A (S1, PWA/offline/data-saver) and batch B (S2, attestation/legal/guest Ask). The Verifier runs scoped to batch A's checks (C1-C8) before the batch A PR, and over every check (C1-C19) before the batch B PR.
- **Settled mid-build:** none
- **Dispatched:** (Verifier entries written when sent)
- **Boundary:** C1-C8 closed at `db7c209` (batch A: d1807ba PWA/offline, db7c209 data saver)
- **Abandoned:** none
- **Walked:** no binding capture exists for this cycle; the landing sample-ask surface and the register form are proven by tests per the plan's no-reference rule (outcomes, not layout)
