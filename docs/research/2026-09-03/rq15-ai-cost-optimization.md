# RQ15 — AI cost optimization (engineering)

*Fleet: public-launch research, 2026-09-03. Sources accessed 2026-09-03. Distill into ADRs/RFCs; keep this file as evidence. Sibling RQ10 covers pricing/billing; this report is the unit-cost engineering half.*

**Question:** What are the highest-leverage techniques to cut Learny's AI cost per user, with real numbers from official docs, without hurting citation quality?

---

## TL;DR

Learny's bill is **generation, not embeddings**. A typical cited Ask on `claude-sonnet-5` costs about **$0.020**, of which **~$0.012 is billed thinking** (output tokens at $10/MTok) and **~$0.008 is evidence input**. Embeddings are ~**$0.04/book** and **fractions of a cent** per query. Quiz decks are already on **Haiku 4.5 + Message Batches (50% off)**. Teaching already stamps a 1-hour `cache_control` breakpoint — but it currently caches the *cheap* prefix (frozen system prompt + history) and leaves the *expensive* evidence documents *after* the breakpoint, and that prefix is usually **below Sonnet 5's 1,024-token cache minimum** until several turns have accumulated. The answer path has **no cache marker at all**.

Highest-leverage order: **(1)** persist a real cost ledger (usage already partially logged; USD and thinking tokens are not), **(2)** diet thinking on Ask (`effort=low`, judge-gated; keep `medium` on Teach), **(3)** move stable teach-section documents *before* the cache breakpoint so the 1h TTL actually hits, **(4)** add the same history breakpoint to multi-turn Ask, **(5)** only then A/B Haiku for Ask behind the nightly faithfulness gate. Do **not** switch embedding models for cost, do **not** semantic-cache cited answers, do **not** put LiteLLM in the request path (ADR-0009).

Estimated monthly AI cost for a defined "typical active learner": **~$1.16 today → ~$0.81 after (2)+(3)** (~30%) **→ ~$0.61** if Ask also survives a Haiku+no-think gate (~47%). Arithmetic and sources below.

---

## Learny cost-driver inventory (from the code)

Read 2026-09-03: `backend/app/core/config.py`, `infrastructure/answering/{prompts,anthropic}.py`, `infrastructure/embeddings/openai.py`, `infrastructure/quiz/anthropic.py`, `worker/tasks.py` (`ingestion` embed, `notes.embed`, `notes.refresh_cards`), `eval/judge.py`.

| Driver | When | Model (settings default) | Shape in code | Sync? |
|---|---|---|---|---|
| Book ingest embed | Once per ingest / re-embed | OpenAI `text-embedding-3-large@1536` | Chunks of `chunk_max_chars=2000`; Celery batches of 128; `stale_chunks_for_source` + per-chunk `embedding_model` (ADR-0019) | Async Celery, **sync OpenAI API** (not Batch) |
| Query embed | Every retrieve (Ask, Teach, raw retrieve) | same | `embed_query(question)` — one short string | Sync, hot path |
| Note embed | Create/edit note | same | Whole note, truncated to `notes_embedding_max_chars=32000` | Async Celery |
| Quiz-item embed | Deck finalize / card accept / note refresh | same | `"question\\nanswer"` for cosine dedup / match | Worker |
| Cited Ask | Each `mode=answer` turn | `claude-sonnet-5`, `effort=medium`, `max_tokens=4096` | Frozen `ANSWER_SYSTEM_PROMPT` (**no** `cache_control`); **8** evidence docs (`conversation_evidence_top_k`); each doc = full chunk `snippet`; Citations API; adaptive thinking `display=summarized` | Sync / SSE |
| Cited Teach | Each `mode=teach` turn | same | Frozen `TEACHING_SYSTEM_PROMPT` + 1h `cache_control`; second breakpoint on **latest history** assistant block; history capped at **6** turns; **evidence documents appended after that**, with the new learner message | Sync / SSE |
| Quiz deck | `POST .../quiz/deck` | `claude-haiku-4-5` | **Already** `messages.batches.create`: one structured-output request per eligible section (`quiz_min_section_chars=200`, 3–6 items); poll ≤ `quiz_batch_timeout_s=3600` | Async Celery + Batch API |
| Quote / note card suggest | Reader waiting | Haiku, **online** `messages.create` | One section or note body; 30s timeout | Sync, **not** batched |
| Note-card regenerate | Edit of a promoted note | Haiku online via `notes.refresh_cards` | Same suggest path | Async Celery, **not** Batch |
| Nightly judge | Ops, not users | `claude-opus-4-8` | Two structured-output calls/case; gate faithfulness ≥ 0.90, relevancy ≥ 3.1 | Nightly |

**Prompt construction that matters for tokens.** `_build_documents` sends **the entire chunk snippet** as a citations-enabled plain-text document (not a truncated RAG window). Eight chunks × ~2,000 chars ≈ **~4,000 input tokens** of evidence (char/4 heuristic, same as the embedding adapter). System prompts are ~80–90 tokens and **byte-stable** (no ids/timestamps) — intentionally cacheable, per the prompts module docstring. `generation_max_tokens=4096` bounds **thinking + answer together**. `_log_call` records `input_tokens`, `output_tokens`, `cache_read_input_tokens` — **not** `cache_creation_input_tokens`, **not** `usage.output_tokens_details.thinking_tokens`, **not** USD.

**Already done (do not rebuild):** Haiku + Message Batches for decks; 1h TTL chosen for human think-time; Matryoshka 1536-dim embeddings; per-chunk model versioning + resumable re-embed; judge gate as the quality backstop for any downgrade.

---

## 1. Prompt caching

### Official mechanics and prices (Anthropic)

Source: [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching), [Pricing](https://platform.claude.com/docs/en/about-claude/pricing) (fetched 2026-09-03).

| Operation | Multiplier vs base input | Sonnet 5 | Haiku 4.5 |
|---|---|---|---|
| Uncached input | 1.0× | **$2 / MTok** | **$1 / MTok** |
| 5-min cache write | 1.25× | $2.50 | $1.25 |
| 1-hour cache write | 2.0× | $4 | $2 |
| Cache read / refresh | 0.1× (0.025× only on Fable/Mythos 5.1) | **$0.20** | **$0.10** |
| Output (incl. thinking) | — | **$10 / MTok** | **$5 / MTok** |

Sonnet 5's **$2/$10 is now the standard price** (the scheduled 2026-09-01 rise to $3/$15 "will not occur"). Break-even: 5-min TTL pays off after **one** subsequent read; 1h TTL after **two**. Minimum cacheable prefix on the Claude API: **1,024 tokens for Sonnet 5**; **4,096 for Haiku 4.5**. Below that, `cache_control` is a silent no-op (`cache_creation_input_tokens` and `cache_read_input_tokens` both 0). Max **4** breakpoints. Prefix match is strict; changing `effort` / thinking config **invalidates** the cache ([Thinking](https://platform.claude.com/docs/en/build-with-claude/thinking)). Automatic top-level `cache_control` now exists and walks the last cacheable block — **wrong** for Learny's shape, because the last block is the new user turn (evidence + question). Explicit breakpoints on the *stable* prefix are the correct pattern.

Learny already uses `ttl: "1h"` on Teach. That is the right TTL: teaching has human gaps ≫ 5 minutes.

### OpenAI automatic caching (relevant only if generation ever leaves Anthropic)

[OpenAI prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching): GPT-5.6+ writes at **1.25×**, reads at **0.1×**, minimum **1,024** tokens. Flagship cheap tier on the 2026-09-03 pricing page: `gpt-5.6-luna` **$0.20 / $0.02 cached / $0.25 write / $1.20 out** per MTok ([OpenAI pricing](https://developers.openai.com/api/docs/pricing)). **No Citations API of Learny's shape** — ADR-0020 stays.

### Quantified Teach session (8 turns, 1h TTL)

Assumptions (labeled): 4,000 evidence + 90 system + 80 message; history grows ~500 tok/turn, capped at 6 prior turns; **800 thinking + 400 visible = 1,200 billed output** (thinking volume is an estimate — Learny does not log `thinking_tokens` yet; 800 is a medium-effort midpoint, not a measurement).

**Today (cache miss on evidence; system+history often < 1,024 until mid-session):**

- Turn 1: `4170×$2/M + 1200×$10/M` = $0.00834 + $0.012 = **$0.0203**
- Turns 2–8: input climbs to ~6,670 → ~$0.0133 + $0.012 = **~$0.025**
- **Session ≈ $0.19** (output/thinking is ~$0.096 of that)

**If the section's documents sit *before* the 1h breakpoint** (stable across a scoped teach session — the retrieval already filters to the target anchors):

- Turn 1 write 4,090 tok at 2×: `4090×$4/M + 80×$2/M + 1200×$10/M` = $0.0164 + $0.0002 + $0.012 = **$0.0286**
- Turns 2–8 read: `4090×$0.20/M + ~800 new×$2/M + 1200×$10/M` = $0.00082 + $0.0016 + $0.012 = **$0.0144**
- **Session ≈ $0.13** (~31% off). Break-even vs uncached is by turn 3, which an 8-turn session clears.

**If thinking were also cut to ~200 tok (`effort=low`)** on the cached session: turn 1 ≈ $0.023, later ≈ $0.008 → **session ≈ $0.08** (~58% off vs $0.19).

**Ask path:** a one-shot Ask cannot cache a ~90-token system prompt (≪ 1,024). Multi-turn Ask *can* cache history once it crosses the minimum — but `AnthropicGenerationAdapter` currently sets `cache_control` **only** when `mode == teach`. That is a one-line structural gap, not a research unknown.

---

## 2. Batch APIs

### Official

- Anthropic Message Batches: **50% off input and output**; up to **100k requests / 256 MB**; most finish **< 1 h**, hard cap **24 h**; results unordered, key by `custom_id`; caching **stacks** with batch (hits best-effort, 30–98%). [Batch processing](https://platform.claude.com/docs/en/build-with-claude/batch-processing), [Pricing](https://platform.claude.com/docs/en/about-claude/pricing). Haiku 4.5 batch: **$0.50 / $2.50** per MTok (vs $1/$5 online).
- OpenAI Batch: **50% off**, **24 h** window; embeddings included; 50k requests / 200 MB; embeddings batches also cap **50k embedding inputs**. [Batch API](https://developers.openai.com/api/docs/guides/batch). `text-embedding-3-large` **$0.13 → $0.065 / MTok**.

### Fit to Learny's Celery pipelines

| Pipeline | Batch-shaped today? | Verdict |
|---|---|---|
| Quiz **deck** | **Yes** — `AnthropicQuizAdapter.begin_deck` | Keep. Already capturing the 50%. |
| Quote / note **suggest** | No — student is waiting (30s timeout) | **Do not** batch. Latency > discount. |
| `notes.refresh_cards` | Async Celery, user not blocked | **Yes, underused.** Same structured-output shape as one batch item. One note = one request, so a *per-note* batch is pointless; a **queued flush** (N pending refreshes → one batch every N minutes) is the fit. |
| Ingest / re-embed | Async Celery, already sub-batched to 2048 inputs | **Technically yes**, economically weak: $0.042 → $0.021 per 320k-token book. Worth it for a bulk library import, not for single-book ingest. |
| Nightly judge | Embarrassingly parallel cases | **Yes.** Opus 4.8 batch is $2.50/$12.50 vs $5/$25. Ops cost, not per-user. |

A 40-section deck at ~2,500 in / 700 out per section, Haiku batch: `40 × (2500×0.50e-6 + 700×2.50e-6) = $0.12`. Online would be **$0.24**. The code already takes the cheap path.

---

## 3. Model tiering / routing

Current price ratios (official, 2026-09-03):

| Role | Model | In / out per MTok | vs Sonnet 5 |
|---|---|---|---|
| Flagship cited gen (locked) | `claude-sonnet-5` | $2 / $10 | 1× |
| Cheap Claude | `claude-haiku-4-5` | $1 / $5 | **0.5×** both sides |
| Quality ceiling / judge | `claude-opus-4-8` | $5 / $25 | 2.5× |
| OpenAI mini-class (no citations API) | `gpt-5.6-luna` | $0.20 / $1.20 | ~0.10× in, ~0.12× out |

Haiku 4.5 **supports the Citations API** (Haiku 3 did not). Quiz already uses Haiku. The open question is **Ask**.

**Keep Sonnet for:** cited Ask (faithfulness is the product), Teach (multi-turn pedagogy; Haiku's 4,096-token cache minimum also makes short teach prefixes uncacheable). **Keep Haiku for:** decks, suggestions, note refresh. **Never Opus on the user path** at 2.5× unless the judge says Sonnet failed.

**Router pattern that fits hexagonal ports:** a `GenerationPort` implementation that selects model by `mode` + a settings flag, **not** a LiteLLM proxy. Quality gate already exists: golden fixtures (offline) + nightly Opus judge (`FAITHFULNESS_MIN=0.90`, `RELEVANCY_MIN=3.1`, ADR-0028 answered-only). A Haiku Ask flip is: run the live judge tier on `generation_model=claude-haiku-4-5`, compare to the Sonnet-5 JSONL, flip only if aggregates hold. Sibling RQ05 wants *more* evidence, not a cheaper model — those are independent knobs; change one per cycle.

Open-weight hosted embeddings (Qwen3-Embedding-0.6B/8B, Apache-2.0, MRL/Matryoshka, [Qwen3-Embedding](https://qwenlm.github.io/blog/qwen3-embedding/)) are a **quality/hosting** option, not a cost win vs $0.04/book, and they break `vector(1536)` unless truncated.

---

## 4. Embedding economics

Official: [text-embedding-3-large](https://developers.openai.com/api/docs/models/text-embedding-3-large) **$0.13 / MTok** (Batch $0.065); [embeddings guide](https://developers.openai.com/api/docs/guides/embeddings) — `dimensions` is Matryoshka; API-renormalized; `-large` at 256 dims still beat ada-002 on MTEB. Learny already requests **1536**. Voyage-4 ([docs.voyageai.com/docs/pricing](https://docs.voyageai.com/docs/pricing)): $0.12 / $0.06 / $0.02 per MTok (large/base/lite) + **200M free tokens**, dims **1024/256/512/2048 — no 1536**. ADR-0019 already rejected Voyage for the column; the `EmbeddingPort` + per-chunk `embedding_model` **is** the migration path if a later cycle accepts a column change.

| Corpus | Tokens | 3-large sync | 3-large Batch | 3-small sync |
|---|---|---|---|---|
| One book (prior research: 400×800 tok) | 320k | **$0.042** | $0.021 | $0.006 |
| 50-book library | 16M | $2.08 | $1.04 | $0.32 |
| One query (~20 tok) | 20 | **$0.0000026** | n/a | n/a |
| One note (~400 tok) | 400 | $0.00005 | n/a | n/a |

**Re-embed is never worth it for cost.** 3-small is 6.5× cheaper and **materially worse multilingual** (MIRACL 44.0 vs 54.9 in ADR-0019) — the wrong trade for Portuguese-primary content. Re-embed *is* worth it for a measured quality upgrade (Voyage / Qwen3) after an eval cycle; the task `reembed.document` already exists.

**Query-embedding cache** (normalize + hash → Redis/Postgres, TTL hours): correct and tiny. Saves latency more than money.

**Semantic cache of answers (GPTCache-style):** **reject for a citations product.** Same question after re-ingest cites dead `chunk_id`s; same wording across two books must not share an answer; "close" cosine matches are how you serve the wrong passage with a confident `[^1]`. Exact-match replay of a *grounded* turn for the same `(user, source, corpus_version, question)` is a different, safe idea — that is HTTP/application caching of an immutable citation snapshot, not semantic cache.

---

## 5. Token diet

Learny today: `conversation_evidence_top_k=8`, full `chunk_max_chars=2000` snippets, `max_tokens=4096`, streaming does **not** truncate the billed completion (the client abort *does* close the provider stream — already wired).

Literature vs settings:

- Liu et al., *Lost in the Middle* ([TACL 2024](https://aclanthology.org/2024.tacl-1.9.pdf)): U-shaped use of long context; stuffing 20 docs can *hurt* vs fewer. Position matters more than raw k.
- Anthropic's own RAG citations guidance (and sibling RQ05) prefers **more** chunks (on the order of 12–20) for recall. That is a **quality** bet that **raises** cost: 8→20 at 500 tok/chunk is **+6,000 input** ≈ **+$0.012/Ask** (~+60% of today's input line, ~+25% of the whole call). Do not raise k as a cost optimization.
- Tight 3–5 *reranked* chunks is the lost-in-the-middle recommendation. Learny has **no reranker** (ADR-0006 escape hatch). Cutting 8→4 without a reranker is how you starve citations. **Don't diet k until retrieval quality is measured on real books** (RQ05's ruler gap).

**What *is* a token diet here:**

1. **Thinking**, not evidence. Official: thinking is billed as **output**, counts toward `max_tokens`, and `display: summarized|omitted` does **not** reduce the bill ([Thinking](https://platform.claude.com/docs/en/build-with-claude/thinking)). `effort=low` is the documented first lever ("Lower cost or latency… lower `effort` first"). Ask is extractive over provided docs — a candidate for `low` or even `thinking: disabled` if the model allows it. Teach should stay `medium`.
2. **Snippet cap distinct from chunk size.** Retrieval already has `retrieval_notes_snippet_chars=2000`. Book evidence has no parallel cap — the generator sees the whole packed chunk. A `conversation_evidence_snippet_chars=1200` (still enough for a citation span) would cut evidence ~40% if eval holds.
3. Streaming truncation is a **UX** stop, not a cost control, unless the adapter cancels the provider stream (it does on disconnect). Do not add a small `max_tokens` on Teach — thinking will hit `stop_reason=max_tokens` and return a partial cited answer.

---

## 6. Observability (substrate for quotas)

Today: one content-free log line per Anthropic call with raw token counts and `cache_read_input_tokens`. No USD, no user rollup, no thinking split, no cache-write visibility. That is not enough to cap a public tenant.

What the proxies do, that Learny should **copy as a thin port** (not adopt as architecture):

| System | What to copy | Official |
|---|---|---|
| LiteLLM | Per-user / per-key `max_budget` + `budget_duration`, spend from a price catalog × usage | [Budgets](https://docs.litellm.ai/docs/proxy/users), [Customers](https://docs.litellm.ai/docs/proxy/customers) |
| Helicone | `Helicone-User-Id` + custom properties → cost per user / feature | [Custom properties](https://docs.helicone.ai/features/advanced-usage/custom-properties), [User metrics](https://docs.helicone.ai/features/advanced-usage/user-metrics) |
| Langfuse | Ingest usage from the provider response; infer USD from a model price table; alert on threshold | [Token and cost tracking](https://langfuse.com/docs/observability/features/token-and-cost-tracking) |

**Learny shape (ADR-0007/0009):** extend `_log_call` (and the embedding adapter) to persist `{user_id, request_id, mode, model, effort, input, output, cache_read, cache_write, thinking, usd}` into Postgres. Price table is config (the numbers in §1–§4). A `SpendPort` enforces a monthly USD ceiling the same way RQ10's quota story needs. Do **not** put LiteLLM in front of `GenerationPort` — that would make LiteLLM the orchestrator.

Judge/eval spend is `eval_budget_usd=10` per live study (already modeled). Nightly Opus is an ops line item (~tens of dollars/month at 50 cases × 2 calls), not a per-user driver.

---

## Savings table

| Technique | Est. % of **typical-MAU** bill | Quality risk | Effort |
|---|---|---|---|
| Cost ledger + per-user USD (no model change) | 0% direct; enables every cap | None | **S** (log fields + one table) |
| `effort=low` on Ask only | **~15–25%** | Medium — faithfulness/relevancy may dip; **gate with nightly judge** | **S** |
| Disable thinking on Ask (if model allows) | **~25–35%** | High without a gate; Teach unchanged | S–M |
| Move teach evidence *before* 1h breakpoint | **~8–12%** (all of Teach's input wedge) | Low if scope is stable; miss if retrieval set changes every turn | **M** |
| `cache_control` on Ask history (multi-turn) | **~2–5%** | None | **S** |
| Haiku Ask, judge-gated | **~15–25% extra** on Ask (0.5× tokens; less if thinking stays on) | **High** on citation faithfulness — *the* product claim | M (eval cycle) |
| Batch note-card refresh flush | **<2%** | None | M |
| OpenAI Batch for ingest embed | **<4%** ($0.02/book) | None | M (new adapter path) |
| Switch to 3-small / drop dims further | ~3% | **High** multilingual retrieval | Don't for cost |
| Cut evidence 8→4 without reranker | ~8% of bill (input only) | **High** citation misses | Don't |
| Raise k 8→20 (RQ05) | **−10 to −25%** (cost *up*) | Quality *up* if retrieval holds | Separate intelligence cycle |
| Semantic answer cache | Looks like 20–40% in other apps | **Unacceptable** for citations | Reject |
| Quiz already batched Haiku | 0% remaining (already taken) | — | Done |

Percentages are of the **$1.16 typical-MAU** model below, not of a single call.

---

## Before / after per-user cost model

**Defined "typical active learner" / month** (stated, not measured — replace with the ledger in cycle 1): 1 book ingested (320k tok), 30 Ask turns, 2 teach sessions of 8 turns, 1 quiz deck (40 sections), 8 notes saved, 4 note-card suggestions, 46 query embeddings.

**Unit costs used:** Sonnet 5 $2/$10; Haiku batch $0.50/$2.50; Haiku online $1/$5; embeddings $0.13/MTok. Ask/Teach unit = §1 ($0.0203 Ask; $0.187 Teach session). Deck = $0.12. Suggestion ≈ $0.0035.

### Today

| Line | Arithmetic | USD |
|---|---|---|
| Ask × 30 | 30 × $0.0203 | **0.61** |
| Teach × 2 sessions | 2 × $0.187 | **0.37** |
| Quiz deck × 1 | $0.12 | **0.12** |
| Note suggest × 4 + 1 refresh | 5 × $0.0035 | **0.02** |
| Ingest embed | 320k × $0.13 / 1M | **0.04** |
| Query + note embeds | ~1k tok × $0.13 / 1M | **0.00** |
| **Total / typical MAU** | | **≈ $1.16** |

Power-user sketch (3 books, 80 Asks, 8 teach sessions, 3 decks): ≈ **$3.6 / month**. Embeddings still <$0.15 of that.

### After package A (no model change): Ask `effort=low` (~200 think tok → Ask $0.014) + teach evidence cached ($0.13/session)

| Line | USD |
|---|---|
| Ask 30 × $0.014 | 0.42 |
| Teach 2 × $0.13 | 0.26 |
| Quiz + notes + embed | 0.18 |
| **Total** | **≈ $0.86** (**−26%**) |

### After package B (A + Haiku Ask, thinking off, **only if judge holds**)

Ask 30 × `(4170×$1/M + 400×$5/M)` = 30 × $0.00617 = **$0.19**; Teach stays Sonnet cached **$0.26**; rest **$0.18** → **≈ $0.63** (**−46%**).

**Sensitivity.** If measured thinking is 2,000 tok not 800, today's Ask is `$0.0083 + $0.020 = $0.028` and thinking diet becomes the *entire* story (~50% of the user bill). That is why the ledger is cycle 1: these rows are scaffolding until `thinking_tokens` is real.

**At 1,000 typical MAUs:** ~$1,160/mo today, ~$860 after A, ~$630 after B — plus ops (nightly Opus judge, not included). This is the number RQ10 should price a free tier against, not the $0.02/answer folklore from the July research (which used Sonnet 4.6 at $3/$15 and **ignored thinking**).

---

## Cycle-sized moves

Each is one spec-driven PR-sized cycle. Why-recommend **and** why-not, as required.

### Cycle 1 — Cost ledger behind a `SpendPort`

**Why-recommend:** `_log_call` already has the SDK `usage` object and never persists it; without USD + `thinking_tokens` + `cache_creation_input_tokens` every later optimization is a guess. This is the quota substrate RQ09/RQ10 need, implemented as a Learny table + price catalog (copy Langfuse's "usage × model definition" idea, not their SDK). Small, testable, no quality risk.

**Why-not:** it does not cut the bill by itself; a naive "block user at $X" without product copy is a support incident. Do not import LiteLLM to get this table.

### Cycle 2 — Thinking diet on Ask (`effort=low`), Teach stays `medium`

**Why-recommend:** official first lever for cost/latency; thinking is billed as output at **$10/MTok**; Ask is extractive over documents the Citations API already sees. One settings split (`generation_effort` vs a new `ask_effort`) + a live judge compare against the committed Sonnet-5 JSONL. Biggest dollar lever that does not touch retrieval.

**Why-not:** if the gate fails (faithfulness < 0.90 or relevancy < 3.1), revert; do not also disable thinking in the same cycle. Changing effort **invalidates** prompt caches — land Cycle 3 after this, or keep Teach's effort constant so its cache still hits.

### Cycle 3 — Teach cache that actually caches the book

**Why-recommend:** the 1h breakpoint is already there and currently protects ~90 tokens of system prompt plus history, often **under the 1,024 minimum**, while ~4,000 evidence tokens sit in the volatile suffix. Scoped teaching retrieval is already anchor-bounded — the document set is the stable prefix the docs tell you to mark. Combined with Cycle 2 this is package A (~25–30% MAU).

**Why-not:** if each teach turn re-retrieves a *different* top-8, the prefix hash misses every time and you **pay 2× writes**. Measure `cache_read_input_tokens` for a week before calling it done. Do not "fix" this by stuffing the whole chapter (lost-in-the-middle + cost up).

### Cycle 4 — Ask history `cache_control` (same helper Teach uses)

**Why-recommend:** unified conversations (ADR-0029) already replay history on Ask; the adapter just skips the marker. Zero quality risk. Helps long Ask threads once history ≥ 1,024 tok.

**Why-not:** single-shot Asks (the common path) still miss the minimum. Do not pad the system prompt to 1,024 tokens to force a hit — that *increases* cost.

### Cycle 5 — Haiku Ask A/B, judge-gated (only after 1–2)

**Why-recommend:** 2× cheaper tokens, Citations API exists, quiz already proved Haiku+schema. At public scale this is the difference between a $1 and a $0.60 MAU.

**Why-not:** citation faithfulness *is* the product. A silent Haiku default is how you ship fluent wrong answers. Requires a full live-judge re-baseline (Opus judge, answered-only, ADR-0028). Do not route Teach to Haiku in the same cycle (cache minimum 4,096 + pedagogy).

### Explicit non-cycles

- **Embedding model swap / 3-small / Voyage-for-cost:** pennies; Portuguese quality is the reason ADR-0019 exists.
- **OpenAI Batch on every ingest:** extra adapter complexity for $0.02/book.
- **Semantic answer cache.**
- **LiteLLM/Helicone in the generation path** (gateway as orchestrator). Use them as a *reference* for the SpendPort, or as an optional ops sidecar, not as core.
- **Raising `top_k` for cost.** That is RQ05's quality cycle and it *increases* spend; if it ships, Cycle 1's ledger will show it.
