# Learny v2 research — evaluation

Generated 2026-07-12 by a web-research agent (v2 planning research fleet). Sources/dates inline; verify load-bearing claims before implementation.

---

# Evaluation Strategy for Real LLM Adapters (Claude + OpenAI embeddings)

Research date: 2026-07-12. Versions/prices verified against PyPI, GitHub releases, and vendor docs as of today unless noted.

## Actionable conclusions first

1. **Keep ADR-0016's golden fixtures for everything upstream of the model calls — they don't break.** Parsing, chunking, anchors, citation resolution, FTS/lexical retrieval, and RRF fusion math are all deterministic regardless of provider. Only two layers lose determinism: embedding-based semantic retrieval and generated text (answers, teaching, quizzes).
2. **Do NOT adopt Ragas now.** Ragas 0.4.x (latest 0.4.3, 2026-01-13, https://pypi.org/project/ragas/) just went through a major architecture overhaul (0.4.0 on 2025-12-03: new BasePrompt architecture, collections-API metric migration, deprecated legacy metrics — https://github.com/vibrantlabsai/ragas/releases). Its four core metrics (faithfulness, answer relevancy, context precision, context recall — https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/) are each ~1–3 LLM-judge prompts per sample that you can reimplement in ~200 lines against your own `AnswerGenerationPort` judge. For a single-author portfolio project with hand-authored fixtures, a custom harness is less code than Ragas's dataset/adapter plumbing, avoids a churning dependency, and fits ADR-0009 (no broad frameworks in core). ADR-0016's "golden fixtures before Ragas" graduation criterion is **not yet met and likely never needs to be** — write a short ADR amendment saying the graduation target is now "custom judge harness," not Ragas.
3. **Record/replay at the port boundary, not the HTTP layer.** You already own `EmbeddingPort`/`AnswerGenerationPort`/`TeachingGenerationPort`. A `ReplayEmbeddingAdapter` / `ReplayGenerationAdapter` that loads committed JSON snapshots is simpler and provider-neutral vs. VCR cassettes of raw Anthropic/OpenAI HTTP traffic (which leak headers, break on SDK upgrades, and are flaky with httpx streaming). Keep vcrpy only for a handful of thin adapter contract tests if at all.
4. **Three-tier CI:** deterministic suite on every PR (no network, no key), small live smoke suite behind a marker (adapter contract, ~$0.05/run), judge-based eval suite nightly/on-demand with a cost cap (~$0.20–0.60/run with Haiku/Sonnet as judge).
5. **Track eval scores as committed JSONL + pytest threshold asserts — no dashboard.** Git history *is* the dashboard.

---

## 1. Layered eval architecture

| Layer | Deterministic after v2? | Eval approach |
|---|---|---|
| EPUB parsing → canonical corpus (sections, anchors, metadata) | ✅ unchanged | Existing golden fixtures, exact assertions, every PR |
| Chunking & anchor projection | ✅ unchanged | Existing golden fixtures, every PR |
| Lexical retrieval (Postgres FTS) + RRF fusion math | ✅ unchanged | Golden fixtures with *injected* vector ranks: feed RRF a fixed semantic candidate list, assert fused order exactly |
| Semantic retrieval (real OpenAI embeddings + HNSW) | ⚠️ stable-ish but not asserted exactly | **Recall@k / MRR on hand-labeled query→chunk pairs** (see §2). Two modes: (a) snapshot embeddings replayed offline — deterministic, every PR; (b) live re-embed — nightly, catches provider model drift |
| Answer generation + citations (Claude) | ❌ | Deterministic *structural* checks (citation IDs ∈ retrieved set, anchors resolve, schema valid) on every PR via replay; **LLM-as-judge faithfulness/relevancy** nightly (see §4) |
| Quiz generation | ❌ | Structural checks + groundedness/answerability judge (see §6) |
| Teaching sessions | ❌ | Structural/citation checks only for now; judge later |

Key insight: **citation validity remains a deterministic property even with a nondeterministic generator.** "Every cited chunk ID exists in the retrieved context, every anchor resolves to the fixture corpus, answer cites ≥1 source" are exact assertions you can run on recorded *or* live outputs. This preserves most of the golden-fixture value.

## 2. Retrieval eval with real embeddings

- Hand-label **30–60 query→relevant-chunk-ID pairs** against your fixture EPUB (you authored it — you know ground truth). Store as YAML/JSON next to the existing golden fixtures.
- Metrics: `recall@5`, `recall@10`, `MRR@10` — pure Python, ~40 lines, no library needed. These are the standard non-LLM retrieval metrics (Ragas calls the same thing "context recall (non-LLM)").
- **Snapshot the embeddings**: run `text-embedding-3-small` once over the fixture corpus + queries, commit vectors (a 200-chunk fixture at 1536 dims ≈ 1.2 MB as float32 `.npy`; fine in git, or use Git LFS). PR CI loads snapshots → fully deterministic recall@k with *real-embedding geometry*, catching regressions in query construction, HNSW params, RRF weighting.
- Nightly job re-embeds live and re-runs the same metrics with a **tolerance threshold** (e.g., `recall@10 ≥ 0.85`, not exact rank order) — catches silent provider model updates. Cost: fixture corpus ~50–100K tokens ≈ **$0.001–0.002 per full re-embed** at $0.02/1M (https://developers.openai.com/api/docs/models/text-embedding-3-small; Batch tier $0.01/1M — https://tokenmix.ai/blog/openai-embedding-pricing). Cost is a non-issue; don't bother with batch here.
- Pin the embedding model string + dimensions in config and assert it in the snapshot metadata so a model swap forces snapshot regeneration.

## 3. pytest patterns: replay vs. cassettes vs. live

**Recommended: both, but replay at the port level.**

- **Tier 1 — port-level replay (every PR).** Fake adapters implementing your ports, hydrated from committed JSON ("golden responses"). A small `--record` pytest flag re-runs against live APIs and rewrites the snapshots (reviewed in the diff like any fixture). This is the LLM analog of snapshot testing and is what the community converged on: record once, replay in CI, no keys/cost/flakes (https://langfuse.com/blog/2025-10-21-testing-llm-applications, https://anaynayak.medium.com/eliminating-flaky-tests-using-vcr-tests-for-llms-a3feabf90bc5). Because you own the port schema, snapshots survive SDK upgrades and even a provider swap — HTTP cassettes don't.
- **Tier 2 — HTTP cassettes (optional, adapter-only).** If you want to test the *adapter* code (request shaping, retry, error mapping) without live calls: **vcrpy 8.3.0** (2026-07-04, https://pypi.org/project/vcrpy/) via **pytest-recording 0.13.4** (2025-05-08, https://pypi.org/project/pytest-recording/ — preferred over unmaintained pytest-vcr; usage: https://til.simonwillison.net/pytest/pytest-recording-vcr). Must-dos: `filter_headers=["x-api-key", "authorization"]` so keys never land in cassettes, and `--record-mode=none` in CI so missing cassettes fail instead of silently calling out (https://code.kiwi.com/articles/pytest-cassettes-forget-about-mocks-or-live-requests/). Caveat: vcrpy + httpx **streaming** (Anthropic SDK streams) has a history of rough edges — another reason port-level replay is primary. Honestly, at your scale, 3–5 live smoke tests may replace this tier entirely.
- **Tier 3 — live tests behind a marker.** `@pytest.mark.live`, skipped unless `LEARNY_LIVE_EVAL=1` and keys present. Two flavors: (a) *contract smoke* — one call per adapter asserting schema/citations shape (~$0.02); (b) *judge evals* (§4). Community consensus: "no live LLM calls in CI unless the test is specifically an evaluation run" (https://langfuse.com/blog/2025-10-21-testing-llm-applications).

## 4. Answer quality: minimal LLM-as-judge harness

Skip Ragas/DeepEval (DeepEval is the pytest-native alternative — https://genai.qa/blog/promptfoo-vs-deepeval-vs-ragas/ — but 50+ metrics and a telemetry-heavy platform is overkill vs. anti-overengineering). Build ~200 lines:

- **Faithfulness:** judge prompt receives (retrieved chunks, answer), extracts claims, labels each SUPPORTED/UNSUPPORTED, returns JSON `{claims: [...], supported_ratio}`. This is exactly Ragas faithfulness, minus the framework.
- **Answer relevancy:** judge scores 1–5 whether the answer addresses the question. Keep rubrics in versioned prompt files.
- **Citation precision (deterministic, no judge):** fraction of cited chunks whose text overlaps the answer's claims — you can approximate with string overlap before reaching for a judge.
- Judge model: **claude-haiku-4-5** ($1/$5 per MTok) is sufficient for binary claim-support checks; use **claude-sonnet** tier ($3/$15) if Haiku disagrees with your spot checks. Use structured outputs (`output_config.format` json_schema) so judge output parses deterministically. (Pricing per bundled Anthropic model catalog, cached 2026-06-24; verify at https://platform.claude.com/docs/en/pricing.md.) Judge calls are eligible for the **Batch API at 50% off** — good fit for nightly runs.
- Thresholds: community baselines are faithfulness ≥ 0.75–0.8, relevancy ≥ 0.8 (https://qaskills.sh/blog/rag-evaluation-metrics-complete-2026) — but calibrate against your own first 3 runs, not blog numbers.

## 5. Regression gating & tracking without a dashboard

- Eval set = the golden-fixture Q&A pairs (~30–60 cases) + quiz cases. Version it in-repo (`evals/cases/*.yaml`).
- Each eval run writes `evals/results/YYYY-MM-DD-<git-sha>.jsonl` (one line per case: scores, model IDs, prompt hash). **Commit results from nightly runs via a CI bot commit or artifact upload** — git diff/log gives trend tracking; a 20-line script can print a score table across commits. This fits "no eval dashboard" exactly.
- **Gate = pytest assertions on aggregates**, not per-case: `mean_faithfulness ≥ 0.80`, `recall@10 ≥ 0.85`, `citation_validity == 1.0` (that one stays exact). Per-case flakiness is absorbed by aggregate thresholds; hard-fail only deterministic invariants.
- **Prompt/model changes:** hash the prompt template + model ID into results; require an on-demand eval run (manual `workflow_dispatch`) before merging any PR that changes `prompts/` or model config — enforce with a lightweight CI check that fails if `prompts/**` changed and no eval-results file references the PR's head SHA.

## 6. Quiz-specific evals (flagship feature)

Deterministic layer (every PR, replay):
- Schema validity (question, options, correct index, citation anchors), no duplicate options, correct answer present, **every citation anchor resolves to a fixture chunk**.

Judge layer (nightly), per generated question — three checks drawn from the QG-eval literature:
1. **Groundedness:** "Is the question answerable *using only* the cited passage?" — every claim in question+answer must be verifiable from the source chunk (methodology: https://arxiv.org/html/2410.08764v1, GroUSE benchmark https://arxiv.org/html/2409.06595v3).
2. **Answerability / key correctness (PMAN pattern):** have the judge *answer the question given the cited chunk*, then check its answer matches the marked correct option (https://arxiv.org/html/2309.12546v2 — "Automatic Answerability Evaluation for Question Generation"). This round-trip is the highest-signal quiz check: it catches wrong answer keys, ambiguous stems, and ungrounded questions simultaneously.
3. **Distractor sanity:** judge confirms distractors are plausible-but-wrong given the passage (dimension set from https://arxiv.org/html/2501.03491v1, "Can LLMs Design Good Questions Based on Context?").

Also cheap and deterministic: run your own **retrieval round-trip** — the cited chunk should rank top-k when you query with the generated question; if not, the question probably isn't grounded in that chunk.

## 7. CI wiring sketch (GitHub Actions)

```
PR push  → job "test":        pytest -m "not live"        # golden fixtures + port-replay + snapshot recall@k; no secrets
main     → job "smoke" :      pytest -m "live and smoke"  # 3-5 adapter contract calls, ~$0.05, secrets from repo env
nightly  → job "eval" (cron + workflow_dispatch):
             pytest -m "live and eval"  --maxfail-cost控制 via env LEARNY_EVAL_MAX_CASES / MAX_USD
             re-embed fixture corpus → recall@k with tolerance
             judge harness (Haiku, structured outputs, optionally Batch API)
             upload results JSONL artifact + bot-commit to evals/results/
prompt/model change PR → require green workflow_dispatch eval run on head SHA
```

Cost cap implementation: count tokens per judge call (`usage` field), accumulate, `pytest.exit` when over budget env var.

## 8. Cost estimates (per run)

| Item | Est. tokens | Cost |
|---|---|---|
| Re-embed fixture corpus + queries (text-embedding-3-small, $0.02/M) | ~100K | **$0.002** |
| Live adapter smoke (3 Claude calls, Haiku) | ~10K in / 2K out | **~$0.02** |
| Judge eval, 50 cases × ~3 calls × (2.5K in / 0.3K out), Haiku 4.5 | ~375K in / 45K out | **~$0.60** ($0.30 w/ Batch) |
| Same with Sonnet-tier judge | — | **~$1.80** |
| Ragas 0.4 four-metric run, 50 samples (for comparison; ~2× calls) | — | ~$1–4 |
| **Nightly Haiku judge, 30 days** | — | **~$9–18/mo** |

Flagged uncertainties: (a) Ragas 0.4.x is 7 months into a rewrite — its API may still churn; re-evaluate only if your eval-case count grows past ~200 or you want its synthetic test-set generation. (b) vcrpy 8.x httpx-streaming compatibility with the current Anthropic SDK is unverified — test before committing to Tier 2, or skip it. (c) Score thresholds above are literature defaults, not Learny-calibrated — treat first three eval runs as baseline-setting, not gating.

Sources: [Ragas PyPI](https://pypi.org/project/ragas/) · [Ragas releases](https://github.com/vibrantlabsai/ragas/releases) · [Ragas metrics docs](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/) · [Langfuse LLM testing guide](https://langfuse.com/blog/2025-10-21-testing-llm-applications) · [VCR for LLMs](https://anaynayak.medium.com/eliminating-flaky-tests-using-vcr-tests-for-llms-a3feabf90bc5) · [pytest-recording TIL](https://til.simonwillison.net/pytest/pytest-recording-vcr) · [vcrpy PyPI](https://pypi.org/project/vcrpy/) · [pytest-recording PyPI](https://pypi.org/project/pytest-recording/) · [Kiwi cassettes](https://code.kiwi.com/articles/pytest-cassettes-forget-about-mocks-or-live-requests/) · [Promptfoo vs DeepEval vs RAGAS](https://genai.qa/blog/promptfoo-vs-deepeval-vs-ragas/) · [RAG metric thresholds](https://qaskills.sh/blog/rag-evaluation-metrics-complete-2026) · [OpenAI embedding pricing](https://tokenmix.ai/blog/openai-embedding-pricing) · [text-embedding-3-small](https://developers.openai.com/api/docs/models/text-embedding-3-small) · [Answerability eval (PMAN)](https://arxiv.org/html/2309.12546v2) · [LLM question-generation quality](https://arxiv.org/html/2501.03491v1) · [Legal QA groundedness](https://arxiv.org/html/2410.08764v1) · [GroUSE](https://arxiv.org/html/2409.06595v3) · Project context: `/home/augusto/projects/learny/docs/adr/0016-use-golden-fixtures-for-mvp-evaluation.md`
