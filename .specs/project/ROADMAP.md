# ROADMAP

The authoritative roadmap is the **TDD-001 Implementation Plan** (`docs/tdd/0001-mvp-architecture.md`, Phases 1–10).
This file only tracks how those phases map onto tlc cycles. Do not duplicate TDD content here.

| tlc Cycle | TDD Phases | Status |
|---|---|---|
| `scaffold-and-identity` | 1 (Repository scaffold) + 2 (Identity foundation) | Done (PR #4) |
| `source-storage` | 3 (Source storage) | Done (PR #7, #8) |
| `worker-foundation` | 4 (Worker foundation) | Done (PR #9) |
| `epub-corpus-pipeline` | 5 (EPUB corpus pipeline) | Done (PR #10) |
| `retrieval-indexes` | 6 (Retrieval indexes) | Done (PR #12) |
| `cited-qa` | 7 (Cited Q&A) | Done (PR #13) |
| `teaching-sessions` | 8 (Teaching sessions) | Done (PR #14) |
| `golden-fixtures` | 9 (Golden fixtures) | Done (PR #15) |
| `production-readiness` | 10 (Production-like readiness) | Done (PR #16) |

All 10 TDD-001 phases are now shipped — the MVP roadmap is complete.

## v2 (RFC-002)

v2 is driven by the accepted [RFC-002 roadmap](../../docs/rfc/0002-learny-v2-roadmap.md)
(cycles A–G); it resolves the MVP's open follow-ups (cloud LLM/embedding provider ADR,
TDD open question #10 lands in Cycle G). Research evidence: `docs/research/2026-07-12/`.

| tlc Cycle | RFC-002 Cycle | Scope | Status |
|---|---|---|---|
| `v2-foundation` | A | QA artifacts + F2/F3/F4 fixes + CI + OSS hygiene | Done (PR #17, v0.1.0) |
| `v2-embeddings` | B | Real embeddings (OpenAI 3-large@1536) + language-aware FTS | Done (PR #20) |
| `v2-generation` | C | Claude generation: cited answers + teaching + eval harness | Done (PR #23) |
| `v2-frontend` | D | Frontend v2: product UI + streaming | Done (PR #24) |
| `v2-active-recall` | E | Active recall: quizzes + FSRS | Done (PR #25) |
| `v2-ingestion-breadth` | F | PDF (Docling) + EPUB hardening | Done (PR #26) |
| `v2-deploy` | G | Deploy (GHCR→VPS, Caddy) + presentation | Done (PR #27) |

RFC-002 is complete — all seven v2 cycles shipped (v0.2.0).

## v3 (RFC-003)

v3 is driven by the accepted [RFC-003 roadmap](../../docs/rfc/0003-learny-v3-roadmap.md)
(cycles A–F): notes & second-brain as the research-gated flagship, plus eval maturity,
ops maturity, and scanned-PDF OCR. Cycles E–F scopes are provisional until the Cycle D
notes-domain ADR is accepted.

| tlc Cycle | RFC-003 Cycle | Scope | Status |
|---|---|---|---|
| `v3-ops-maturity` | A | Backups + monitoring (TDD OQ #10) + image hygiene | Done (PR #28) |
| `v3-eval-maturity` | B | Real-provider baselines + judge threshold gate | Done (PR #35) |
| `v3-ocr` | C | Scanned-PDF OCR + localized normalization | Done (PR #29) — ran before B per AD-103 |
| `v3-notes-research` | D | Second-brain research + notes-domain ADR (gate for E–F) | Done (PR #30) — ADR-0026 Accepted 2026-07-18, E–F unblocked |
| `v3-notes-foundation` | E | Capture + organize: highlights, notes, links (per ADR-0026) | Done (PR #31) |
| `v3-notes-loop` | F | Retrieve + reinforce: notes in RAG + quiz, export | Done (PR #43, v0.3.0) — RFC-003 complete |

## Recorded candidates (not scheduled; user-blessed 2026-07-18)

- **`eval-deepening`** (half-day, after RFC-004 Cycle A): (1) local **silver eval
  set** — 10–20 hand-authored Q→expected-passage cases over the user's real books
  (data git-ignored: copyrighted text; only a small runner committed); (2)
  **relevancy rubric anchoring** — per-score exemplars in the judge prompt (fixes
  the Haiku-parks-at-3 artifact; prompt_hash changes → one recalibration pass);
  (3) **judge A/B** Haiku 4.5 vs Opus 4.8 on identical outputs; (4) **generation
  A/B** Sonnet 5 vs Opus 4.8 over golden + silver → research doc under
  `docs/research/` that decides whether the product default moves to Opus.
  Sequencing rationale: comparison over the synthetic golden set alone is
  uninformative (both models ace it) — silver set must exist first; product
  default stays `claude-sonnet-5` until that evidence exists. Origin: user
  provocation post-Cycle-B, reasoning in the 2026-07-18 session.
  Status: Done (2026-07-21) — silver tier + anchored rubric shipped; both A/B
  studies run and decided in `docs/research/2026-07-21/eval-deepening-ab.md`.
  Generation default stays `claude-sonnet-5` (Opus not strictly better on silver);
  the study's judge-switch verdict (8/60 gate flips) was overridden at the merge
  gate — judge stays `claude-haiku-4-5` until baselines are re-derived under Opus
  and the decline-faithfulness semantics are settled (deferral recorded in the
  research doc).

v4 is driven by the accepted [RFC-004 roadmap](../../docs/rfc/0004-student-experience-roadmap.md)
(cycles A–F, reading-first student experience; identity per ADR-027). RFC-003
Cycle F interleaves after RFC-004 Cycle C.

| tlc Cycle | RFC-004 Cycle | Scope | Status |
|---|---|---|---|
| `v4-identity-foundation` | A | Iron Gall tokens + fonts + reading typography + Paper scaffolding | Done (PR #36) |
| `v4-reader-core` | B | Chapter flow, position, progress, Aa popover, ink-line signature | Done (PR #37) |
| `v4-reader-apparatus` | C | Ask/Teach as panel modes, citations-as-passages — unblocks RFC-003 F | Done (PR #38) |
| `v4-capture-pipeline` | D | Cards at the highlight, margin rail, review pins | Done (PR #39) |
| `v4-home-ia` | E | Two-card Home, streak/heatmap, nav collapse | Done (PR #44) |
| `v4-polish-gate` | F | Restyle completion + 14-day dogfood gate | Polish shipped (PR #45); dogfood window open 2026-07-21, retrospective closes the RFC |

## v5 (RFC-005 — Draft, RESUMED after RFC-006)

v5 is proposed in [RFC-005](../../docs/rfc/0005-evidence-gated-hardening-roadmap.md)
(**Draft, work-in-window authorized 2026-07-24**): evidence-gated hardening plus one
product beachhead, written into the open RFC-004 dogfood window. The RFC paused after
Cycle A for the 2026-07-24 dogfood findings (RFC-006, below) and **resumed once
RFC-006 completed**: Cycle B shipped the Opus judge flip, and Cycle C the de-noised
generation verdict. Cycles D–F remain queued in RFC order (E stays pullable forward
if worker pain bites). Formal acceptance remains pending the RFC-004 dogfood
retrospective (~2026-08-04). Targets v0.5.0.

| tlc Cycle | RFC-005 Cycle | Scope | Status |
|---|---|---|---|
| `v5-offline-suite-honesty` | A | conftest provider pin (offline-suite leak) + teach-panel resume deflake | Done (PR #47) |
| `v5-opus-judge-recalibration` | B | Decline-faithfulness contract (ADR-0028) + Opus judge re-derivation → flip-or-stay | Done (PR #59) — FLIP: judge default now `claude-opus-4-8`, thresholds re-pinned (0.90 / 3.1), nightly tier = the 12 replay snapshots |
| `v5-generation-denoise` | C | Multi-run Sonnet-vs-Opus A/B, per-metric variance | Done (PR #60) — de-noised STAY on `claude-sonnet-5` under the opus judge (2 complete runs + partial run 3, 137/144 units — operator credit halt, deviation recorded; complete-runs cross-check agrees); committed study runner closes the uncommitted-driver gap |
| `v5-eval-dashboard` | D | Read-only render of the nightly eval JSONL (compact, cuttable) | Done (PR #61) — dev-only `/dev/evals`, gated + unlinked; verdicts derived from the gate's own predicate (one owner, shared with the nightly assert); runs de-duplicated by file name so the published history's 27 files read as 11 runs; runs judged by a superseded judge are marked |
| `v5-worker-recovery-hardening` | E | Celery worker liveness/heartbeat + WAL/PITR restore drill | Done (PR #62) — worker-lost rejection guarded by a durable attempts cap; WAL archiving onto periodic physical base backups (the RFC's "WAL on top of the logical dump" was not implementable — a dump carries no WAL position); point-in-time restore proven by a CI drill with a control run that makes its discriminating assertion able to fail. No `broker_heartbeat`: AMQP-only, inert on Redis |
| `v5-spoiler-safe-retrieval` | F | Position-scoped retrieval (build now, deploy after the retrospective) | Paused (deploy also dogfood-gated) |

## v6 (RFC-006 — Draft)

v6 is proposed in [RFC-006](../../docs/rfc/0006-reading-first-ux-overhaul.md)
(**Draft, proposed 2026-07-24**), which holds the window RFC-005 gave up: the reader
becomes the hub, the two missing foundations (a page unit and one grounded-conversation
model) get built, and the app finally measures itself. Source evidence: thirteen dogfood
findings from the 2026-07-24 session, recorded in the RFC. Ordering is foundations-first
and C precedes D by the driver's explicit call; ADR-0029 must be accepted before Cycle C.

| tlc Cycle | RFC-006 Cycle | Scope | Status |
|---|---|---|---|
| `v6-instrument` | A | Request/query/task timings, `Server-Timing`, dev-only surface | Done (PR #49) |
| `v6-page-unit` | B | Page unit (~275 words), reader typography, live progress, study heatmap | Done (PR #51) |
| `v6-conversation-model` | C | Unified scoped conversations per ADR-0029 (backend-first) | Done (PR #52) — ADR-0029 shipped in the PR |
| `v6-workspace-conversations` | D (1 of 2) | Ask/Teach re-pointed onto the unified conversation API, dock conversation management, legacy surface retired, generation ports converged, list pagination | Done (PR #53) |
| `v6-workspace-notes` | D (2 of 2) | Dock Notes + Review tabs, notes-by-source filter, `/notes` re-scoped per book, notes provenance (title-only creation retired) | Done (PR #54) |
| `v6-answer-experience` | E | Thinking + streaming states, inline citations, app-wide loading pattern | Done (PR #58) — RFC-006 complete |

Cycle D was split at spec time, as RFC-006 §Cycle D authorized. Three of its listed
deliverables were already shipped by earlier cycles — the `/ask` and `/teach` route
redirects (RFC-004 Cycle C), the contents rail (`TocPanel`), and the per-source
due-cards filter — so the remainder divides along two disjoint axes rather than the
RFC's literal "dock + redirects / notes & review" seam. Rationale and the rejected
alternatives: AD-203.

## v7 (RFC-0007 — Draft)

v7 is proposed in [RFC-0007](../../docs/rfc/0007-public-launch-roadmap.md) (**Draft, research 2026-09-03**): the public-launch arc. Evidence: `docs/research/2026-09-03/`. Bet 1 gates activation and any launch motion.

| tlc Cycle | RFC-0007 | Scope | Status |
|---|---|---|---|
| `trustworthy-cited-ask` | A / Bet 1 | Keep the thread on failed Ask; pin both Anthropic request shapes; claim-level citation spans | Done (PR #63) |
| `reader-people-read-in` | B / Bet 2 | Safe figures; immersive `/read` chrome; phone column | Done (PR #64) |
| `teach-becomes-tutor` | C / Bet 3 | Frozen teach playbook; tutor-opens; Chat dock merge; one FSRS card on passed check | Done (PR #65) |
| `review-worth-returning` | D / Bet 4 | Empty-deck honesty, formulation gates, undo/session, flag/edit | Done (PR #66) |
| `first-session-converts` | E / Bet 5 | Shared sample, canned Ask, starter deck, library honesty, landing, activation | In progress |
| *(Bets 6–7)* | F–G | Safety rails; cheaper intelligence | Not started |
