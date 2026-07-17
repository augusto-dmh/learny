# RFC-003: Learny v3 Roadmap — From Definitive Version to Second Brain

- **Status**: Accepted (2026-07-17)
- **Date**: 2026-07-17
- **Driver**: Augusto
- **Approvers**: Augusto
- **Contributors**: Claude
- **Impact**: HIGH

## Background

v2 is complete and deployed-ready ([RFC-002](0002-learny-v2-roadmap.md), cycles A–G, PRs #17–#27, v0.2.0; [retrospective](../retrospectives/2026-07-learny-v2.md)): real embeddings and Claude generation behind ports, a product UI with streaming, active recall with FSRS, PDF ingestion, and an automated GHCR → VPS deploy behind a Caddy TLS edge. The study loop — upload → read → ask → teach → quiz → review — works end to end.

What v2 deliberately left open, in writing:

- **Eval baselines are deterministic-only.** Real-provider snapshots and the judge threshold gate wait on keyed runs; nightly `eval.yml` persists JSONL to `eval-results` but nothing gates on it yet.
- **The backup/monitoring half of TDD open question #10.** The TLS/proxy half closed in [ADR-0023](../adr/0023-ghcr-ssh-deploy-caddy-edge.md); automated backups and a metrics/monitoring stack remain the last project-wide infrastructure follow-up.
- **Image hygiene** (ADR-0023 follow-ups): the `runtime` backend image installs the `dev` extra; the `pdf-worker` image is multi-gigabyte.
- **Scanned PDFs**: Docling runs with `do_ocr=False`; scanned books fail structurally. Normalization heuristics are language-neutral where localized ones (the author studies Portuguese books) would do better.
- **The product ceiling**: Learny consumes books but everything the user thinks while studying — marginalia, connections, syntheses — leaves no trace. CLAUDE.md has named "broader learning and second-brain workflows" as the eventual direction since the project started.

v3 makes the second brain the flagship — capture, connect, and reuse the reader's own thinking on top of the canonical corpus — and rides the recorded maturity debts along with it.

## Locked product decisions (2026-07-17 scope session)

1. **Flagship**: notes & second-brain workflows, layered on the existing canonical corpus and anchors. Chosen over a public hosted instance (infrastructure-heavy, little new learning value), learning-loop deepening (mostly items v2 deliberately deferred as lower-value), and a no-flagship consolidation release (debts are small enough to ride along).
2. **Supporting tracks**: eval maturity (real baselines + judge gate), ops maturity (backups + monitoring + image hygiene), scanned-PDF OCR + localized normalization heuristics.
3. **Explicitly excluded from v3**: multi-provider/BYOK adapters, public multi-tenant hosting, dedicated vector DB or reranker, MCQ quizzes, FSRS parameter optimizer (all remain recorded candidates, none scheduled).
4. **The flagship is research-gated.** Unlike v2's flagship (active recall, researched 2026-07-12), the notes domain model is not yet designed. Cycle D below is that research + design work; the notes cycles' scopes are provisional until Cycle D locks them. This mirrors the research-fleet-then-decide pattern that produced RFC-002.

## The flagship in one paragraph

The second brain closes the loop that v2 left open: **capture** (highlights and notes taken while reading, asking, or in teaching sessions — anchored to exact passages via the existing anchor scheme), **connect** (links between notes, notes and sections, backlinks, tags), **retrieve** (notes join the hybrid retrieval corpus so cited Q&A can draw on the user's own thinking alongside the book), and **reinforce** (notes feed `QuizGenerationPort` so personal syntheses enter the FSRS review queue). Every stage reuses an existing subsystem — anchors, hybrid retrieval, generation ports, active recall — which is why this flagship fits Learny where a generic notes app would not.

## Proposed roadmap

Ordering rationale: maturity tracks first (small, fully specified, no design risk, and they harden the platform the flagship lands on); OCR next (extends the existing Docling pipeline, independent of everything else); flagship research before flagship build (the one large unknown); build cycles last, on a stable base, with scopes confirmed by the research.

### Cycle A — Ops maturity: backups + monitoring + image hygiene

- Automated backups: scheduled PostgreSQL dumps + MinIO object sync to off-VPS storage, retention policy, restore runbook **with a tested restore path**. Closes the backup half of TDD open question #10; stack choice decided in-cycle by ADR.
- Monitoring: metrics/uptime for the compose stack (lightweight, self-hosted, provider-neutral — candidates weighed in the in-cycle ADR; structured logs from Phase 10 remain the correlation hook).
- ADR-0023 follow-ups: `runtime` image drops the `dev` extra; `pdf-worker` image slimmed / rebuild pain reduced where practical.

### Cycle B — Eval maturity: real baselines + judge gate

- Record real-provider replay snapshots (`text-embedding-3-large@1536` retrieval recall@k/MRR; Claude generation judge baselines) via the existing `--record` paths, committed alongside the deterministic ones.
- Calibrate judge thresholds from accumulated `eval-results` nightly history; turn the threshold gate on in `eval.yml` (fail the nightly run, not PRs — PRs stay offline/deterministic).
- Document the calibration method so future model swaps re-derive thresholds instead of inheriting stale ones.

### Cycle C — Ingestion breadth II: scanned-PDF OCR + localized normalization

- OCR path for scanned PDFs behind the existing `DocumentParserPort` (Docling `do_ocr` enabled selectively — scanned-detection heuristic or per-upload flag; OCR models handled like the baked layout models; memory/time budget re-verified against the `worker-pdf` limits).
- Localized normalization heuristics in `normalize_book` (Portuguese-aware heading/front-matter patterns first, table-driven so other languages are additive).
- Golden fixtures extended with a scanned sample.

### Cycle D — Second-brain research + design (research-gated flagship, part 0)

- Research fleet (pattern of `docs/research/2026-07-12/`, output under `docs/research/<date>/`): comparable products (RemNote, Readwise/Reader, Obsidian ecosystem, Recall — does anyone combine anchored book highlights + AI teaching + SRS + notes?); highlight anchoring below section/block granularity (char spans vs quote-matching, re-ingest survival); notes data model (blocks vs documents, links/backlinks, tags); editor stack for the frontend; how notes enter hybrid retrieval (same chunk table vs parallel index, citation semantics for "your note" vs "the book"); note→quiz mapping; export/portability (Markdown/Obsidian-compatible).
- Deliverables: research reports + a notes-domain ADR + confirmed (or revised) scopes for Cycles E–F. **Gate: Cycles E–F do not start until this ADR is accepted.**

### Cycle E — Second-brain foundation: capture + organize (provisional)

- Schema + domain: notes and highlights as user-owned records anchored to corpus anchors (snapshot semantics so they survive re-ingestion, per the quiz-item precedent), tags, note↔note and note↔section links.
- API + UI: create a highlight/note from a reader selection; notes list/detail; backlinks panel in the reader; edit/delete.

### Cycle F — Second-brain loop: retrieve + reinforce (provisional)

- Notes join retrieval: embedded + indexed alongside book chunks; cited Q&A can cite the user's notes with distinct citation presentation.
- Notes feed active recall: generate quiz items from notes through the existing quiz pipeline; provenance shown at review time.
- Export: Markdown (Obsidian-compatible) vault export of notes + highlights.
- README/demo refresh + v3 retrospective; version to 0.3.0.

## Assumptions

| Assumption | Confidence | Invalidated if |
|---|---|---|
| Author-scale, single-user, self-hosted usage continues through v3 | High | A hosted/multi-user goal appears — re-open the excluded tracks |
| Nightly `eval.yml` runs with real keys will have accumulated history before Cycle B | Medium | Keys/secrets not configured — Cycle B then starts by seeding baselines with fresh keyed runs instead of history |
| The 8 GB VPS absorbs OCR and monitoring workloads | Medium | Cycle A/C load tests say otherwise — resize before, not after |
| Existing anchor scheme can carry sub-section highlight anchoring | Medium | Cycle D research finds it can't — the notes ADR must then extend the anchor model explicitly |

## Operating cost envelope (delta over v2)

| Item | Cost |
|---|---|
| Off-VPS backup storage | ~€0–5/mo |
| Monitoring | €0 (self-hosted on the VPS) |
| Keyed baseline recording (Cycle B, one-time) | ~$5–15 |
| OCR | compute-only (worker time, no API cost) |
| Notes embedding/generation | marginal — same per-token rates as v2 usage |

## Out of scope for v3 (explicit)

Multi-provider/BYOK, public hosted multi-tenant instance, dedicated vector DB/reranker, MCQ/distractor quizzes, FSRS optimizer, `eval-results` dashboard (JSONL history keeps accumulating; a dashboard remains a recorded candidate), LangChain/LlamaIndex-style frameworks (ADR-0009 stands).

## Follow-up decision records to write when cycles start

- ADR: backup + monitoring stack (closes TDD open question #10 fully).
- ADR: scanned-PDF OCR enablement + localized normalization policy.
- ADR: notes & second-brain domain model (the Cycle D gate deliverable).
