# RFC-002: Learny v2 Roadmap — From MVP to the Definitive Version

- **Status**: Accepted (2026-07-13)
- **Date**: 2026-07-12
- **Driver**: Augusto
- **Approvers**: Augusto
- **Contributors**: Claude (research fleet: 8 parallel research agents + gap critique, see [docs/research/2026-07-12/](../research/2026-07-12/))
- **Impact**: HIGH

## Background

The MVP is complete and QA'd end-to-end ([QA report](../ops/e2e-qa-report-2026-07-12.md)): EPUB ingestion with preserved structure, hybrid retrieval, cited Q&A, and teaching sessions all work — but with deterministic network-free AI adapters, an unstyled frontend, no CI, and several known bugs (F1–F9).

v2 turns Learny into the definitive version: a real application the author studies with daily, credible as a portfolio project, structured as mature open source, and still strictly scoped to **consuming books and studying them**.

This RFC synthesizes the 2026-07-12 research fleet output into a sequenced roadmap. Each cycle is sized for `learny-ship-cycle` (one or a few reviewable PRs).

## Locked product decisions (from the 2026-07-12 grilling session)

1. **Audience**: author + portfolio; OSS-ready structure; no user chasing, no public instance.
2. **AI providers**: Anthropic Claude for generation, OpenAI for embeddings — both behind existing ports (ADR-0007).
3. **Flagship feature**: active recall — citation-grounded quiz generation + FSRS spaced repetition.
4. **Frontend**: real product UI, pragmatic stack, streaming chat.
5. **Ingestion**: PDF via Docling as a second adapter + EPUB structure hardening.
6. **Maturity bar**: CI, QA-finding fixes, OSS hygiene, personal VPS deploy.

## Key research verdicts (details in docs/research/2026-07-12/)

| Question | Verdict | Report |
|---|---|---|
| Does anyone already combine structure-preserving citations + teaching + SRS? | **No — the niche is open.** Chat-with-docs tools have citations but no study loop; flashcard tools have no citations; SRS apps don't ingest books. | comparable-projects |
| Citations API fit? | Excellent: one plain-text document per retrieved chunk; map `document_index → chunk_id`; `char_location` offsets give sub-chunk highlights; streams as `citations_delta`. **Incompatible with structured outputs** (400) — quiz generation must not use the Citations API. | anthropic-generation |
| Models per workload | Q&A + teaching: `claude-sonnet-4-6` (~$0.02/answer, ~$0.12 per 10-turn cached teaching session, 1h-TTL cache). Quiz gen: `claude-haiku-4-5` + structured outputs + Batch API (~$1.80 per 300-section book deck). | anthropic-generation |
| Embedding model | `text-embedding-3-large` @ `dimensions=1536` — fits the existing `vector(1536)` column, ~$0.04/book, materially better Portuguese retrieval (MIRACL 54.9 vs 44.0 for -small). Voyage-4 noted as better-but-1024/2048-dims alternative. | embeddings, followup-eval-embedding-model |
| Quiz item format | **Free-recall + cloze, self-graded Again/Hard/Good/Easy. No MCQ/distractors in v2** — FSRS is trained on recall ratings; distractors are ungroundable and the biggest LLM quality risk; recall+feedback beats MCQ in RCTs. | followup-quiz-item-format, active-recall-srs |
| SRS engine | FSRS-6 via `py-fsrs` (MIT, v6.3.x) behind a `SchedulingPort`; default params; optimizer deferred. Content/scheduling/history table split, Anki-GUID-style upsert so review state survives re-ingestion. | active-recall-srs |
| Frontend streaming | AI SDK `useChat` + FastAPI emitting Vercel's **UI Message Stream protocol** (documented, language-agnostic SSE; official next-fastapi example). Tailwind v4 + shadcn/ui + AI Elements (`InlineCitation`, `Sources` map 1:1 to Learny citations). Existing proxy already streams; one content-encoding bug to fix. | frontend-streaming |
| PDF parser | Docling (MIT, Linux Foundation, v2.112): CPU-viable (~1–3 s/page, OCR off), heading hierarchy + page provenance. **Not for EPUB** (strips anchors — keep ebooklib). marker/PyMuPDF rejected on license. | pdf-docling-epub |
| PDF anchors | Layered: heading-path slug + block ordinal (machine key), page span (human citation), content hash (re-ingest reconciliation). | pdf-docling-epub |
| Evaluation | **Skip Ragas** (mid-rewrite churn; ~200-line custom judge harness fits ADR-0009/0016). Three tiers: deterministic golden fixtures every PR (unchanged); port-level replay snapshots; nightly Haiku-judge evals with cost cap (~$9–18/mo). Retrieval: recall@k on hand-labeled pairs, snapshots pinned to `text-embedding-3-large@1536`. | evaluation, followup-eval-embedding-model |
| CI | One workflow, 4 parallel jobs (pytest w/ pgvector service container, ruff, vitest+build, compose smoke via bake-action + GHA cache); ~4–7 min. | oss-maturity-ci |
| License | **Apache-2.0** (patent grant, enterprise-readable, relicensable later; AGPL protects against a threat Learny doesn't face). | oss-maturity-ci |
| VPS | 8 GB / 4 vCPU (~€14/mo Hetzner-class); GHCR images built in CI, `compose pull && up -d` over SSH; Caddy for TLS; Docling worker on a dedicated queue, concurrency=1, `mem_limit: 4g`. | followup-vps-sizing |

## Proposed roadmap

Ordering rationale: hygiene first (CI protects everything after), retrieval before generation (answer quality depends on it), frontend before the flagship (the review UI needs the component stack), PDF late (independent, heaviest ops risk), deploy last (ships the whole).

### Cycle A — Foundation: fixes + CI + OSS hygiene
- Commit the QA artifacts (README, runbook, report) and the F1 compose fix.
- Fix **F2** (wrap `BotoCoreError` → `StorageUnavailable` so storage outages retry), **F3** (strip `Expect`/hop-by-hop headers in the proxy), **F4** (first-run-fresh-DB golden-test flake).
- GitHub Actions CI per research sketch; branch protection on `main`.
- `LICENSE` (Apache-2.0), `SECURITY.md`, `CONTRIBUTING.md`, Dependabot security-only, `v0.1.0` tag.
- Refresh `CLAUDE.md` (F9) — the "no runtime scaffold" text is long stale.

### Cycle B — Real retrieval: OpenAI embeddings + language-aware FTS
- `OpenAIEmbeddingAdapter` (`text-embedding-3-large`, `dimensions=1536`, batches ≤2048 inputs/≤250k tokens); deterministic adapter remains the CI default.
- Migrations: `embedding_model` per chunk; `language` on documents/chunks (from `dc:language`, fallback `simple`); per-language tsvector regconfig + GIN rebuild (fixes **F8**).
- `reembed_document` Celery task (idempotent, per-batch commits); HNSW drop/rebuild.
- Tier-2 retrieval eval: 30–60 hand-labeled query→chunk pairs, recall@k/MRR snapshots pinned to the model+dims.

### Cycle C — Claude generation: cited answers + teaching
- `AnthropicAnswerAdapter`: Citations API (one plain-text doc per chunk, `document_index` mapping), Sonnet 4.6, streaming; relevance-aware `not_found_in_source` (fixes **F5**).
- `AnthropicTeachingAdapter`: same + prompt caching (frozen system prompt, evidence in first user message, `ttl: "1h"`).
- FastAPI SSE endpoints emitting the UI Message Stream protocol (edge presenter module).
- Eval: port-level replay snapshots (`--record` flag), `@pytest.mark.live` smoke, citation-validity invariants stay exact; judge harness (faithfulness/relevancy, Haiku, structured outputs) wired for nightly.

### Cycle D — Frontend v2: product UI + streaming
- Tailwind v4 + shadcn/ui + AI Elements; app shell (sidebar with library/book tree, auth header, dark mode) — fixes **F6** (navigation, styling, polling, teach dead-ends).
- Ask/Teach rebuilt on `useChat` + `DefaultChatTransport` through the existing proxy; `InlineCitation` popover → "open in book" anchor navigation; `SectionReader` with anchor highlighting.
- Fix the proxy `content-encoding` relay bug; ingestion progress polling.

### Cycle E — Flagship: active recall (quizzes + FSRS)
- Schema: `quiz_items` / `quiz_item_scheduling` / `review_log` (content/scheduling/history split, `content_key` upsert, anchor + snapshot per item).
- `QuizGenerationPort` → Haiku adapter: free-recall + cloze, structured outputs with `source_chunk_id` enum + verbatim `anchor_quote` (verified server-side by string match); embedding-based dedup; Batch API Celery pipeline ("generate deck for this book").
- `SchedulingPort` → py-fsrs adapter (FSRS-6 defaults, 4-button rating); due-queue endpoints; re-ingest reconciliation (keep/stale/orphaned — never delete review state).
- Review UI: due queue, quiz card with reveal + citation footnote, grade bar, session summary. Anki export (`genanki`/CSV).
- Quiz evals: deterministic groundedness checks every PR; answerability round-trip judge nightly.

### Cycle F — Ingestion breadth: PDF (Docling) + EPUB hardening
- Format-agnostic corpus normalization pass: heading-hierarchy inference from flat TOCs, title-inference cascade (kill `part0034`-style names), anchor promotion/section merging with anchor aliasing, trivial-section merge, Gutenberg noise stripping, heading-level clamping (fixes **F7**).
- `DoclingPdfParser` behind the existing ingestion port: `do_ocr=False`, tables on, models baked into a separate worker image; dedicated `ingest-pdf` queue, concurrency=1, `mem_limit`, `worker_max_tasks_per_child=1`.
- PDF anchor scheme (heading path + block ordinal + page span + content hash) and re-ingest reconciliation.

### Cycle G — Ship it: deploy + presentation
- GHCR image builds in CI; deploy job (`compose pull && up -d` over SSH, main-only, gated on green CI); Caddy with persisted cert volume; only 80/443 exposed; runtime `.env` on VPS.
- Nightly eval workflow (cost-capped) + results committed as JSONL.
- README finale: <90s demo GIF of the money path (upload → cited answer → quiz → review), 2–3 screenshots, architecture diagram refresh, "key decisions" ADR section; `v0.x` release with generated notes; retrospective post.

## Operating cost envelope (author-scale usage)

| Item | Cost |
|---|---|
| Embed a book | ~$0.04 |
| Cited answer | ~$0.02 |
| 10-turn teaching session (cached) | ~$0.12 |
| Full quiz deck for a book (batched Haiku) | ~$1.80 |
| Nightly judge evals | ~$9–18/mo |
| VPS (8 GB) | ~€14/mo |

## Out of scope for v2 (explicit)

MCQ/distractor quizzes, FSRS parameter optimizer, Ragas/eval dashboards, multi-provider BYOK adapters, dedicated vector DB, public hosted instance, notes/second-brain features, LangChain/LlamaIndex-style frameworks (ADR-0009 stands).

## Follow-up decision records to write when cycles start

- ADR: Anthropic generation adapters (models per workload, Citations API mapping, caching policy).
- ADR: OpenAI embeddings (`3-large@1536`, per-chunk model versioning, Voyage as recorded alternative).
- ADR: Active recall design (free-recall/cloze, FSRS-6 via py-fsrs, snapshot/reconciliation model).
- ADR: PDF ingestion via Docling + corpus normalization pass.
- ADR amendment to ADR-0016: eval graduation target is a custom judge harness, not Ragas.
- ADR: Apache-2.0 license.
