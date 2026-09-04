# RQ05 — Retrieval intelligence (pgvector-first)

*Fleet: public-launch research, 2026-09-03. Sources accessed 2026-09-03. Distill into ADRs/RFCs; keep this file as evidence.*

**Question:** How does Learny make answers meaningfully smarter while respecting ADR-0006 (PostgreSQL hybrid RRF; a dedicated vector DB / reranker only as a recorded escape hatch) and the ADR-0019/0020 provider lock (OpenAI embeddings, Anthropic generation)?

---

## TL;DR

Learny already has the architecture the 2024–2026 RAG literature rediscovered: **hybrid dense + lexical fusion, citations as a retrieval output, section-bounded chunks, and a judge gate**. The remaining quality gap is not “switch to Qdrant.” It is that **the semantic arm embeds isolated chunk bodies**, the **evidence budget is 8 chunks** (Anthropic’s own ablations preferred 20), **whole-book synthesis has no long-context fallback despite ADR-0001**, notes are **one vector per note**, and the nightly retrieval gate **cannot see ranking drift** because it scores a 3-chunk synthetic book at ceiling.

Highest-leverage cycle-sized moves, in order:

1. **Structural contextual headers** (full `section_path` + book title prepended to the *embed/FTS text*, original `text` kept for citations) + raise conversation `top_k` toward 12–20. Stays inside one SQL statement.
2. **Harden the retrieval ruler** (real-book labeled pairs + context-recall/precision in the nightly judge) so later cycles can be measured.
3. **Parent-section expansion** after RRF: retrieve leaf chunks, expand to `corpus_sections.markdown` when several hits share a parent. Uses the hierarchy Learny already stores.
4. **Query rewrite for anaphora / follow-ups** (one extra Claude call, same SQL). Defer HyDE.
5. **Paragraph-level note chunking** (already the ADR-0026 upgrade).
6. **Chapter-scope long-context fallback** for synthesis questions (ADR-0001; unimplemented).
7. **Reranker behind a new port** only after (1)–(3) plateau — prefer a **local** multilingual cross-encoder over a third cloud SDK.

Do **not** introduce LlamaIndex/LangChain, Cohere/Voyage SDKs, a vector DB, sentence-window rechunking of books, or agentic multi-hop as the first intelligence cycle.

---

## What exists today (repo facts)

Single statement in `backend/app/infrastructure/db/retrieval.py`: source-scoped CTE → pgvector cosine (HNSW, `ef_search=100`) LIMIT 50 → `websearch_to_tsquery` + `ts_rank_cd` LIMIT 50 → RRF `1/(k+rank)` with `k=60` → `top_k`. Conversations pass `conversation_evidence_top_k=8`. Teaching reuses the same SQL with `anchor = ANY(:anchors)`. Notes (ADR-0026) add two extra RRF arms over whole-note `vector(1536)` + tsvector, weighted, user-scoped.

Chunking (`backend/app/application/chunking.py`): **never crosses a section boundary**; packs blocks to `chunk_max_chars=2000`; sentence-splits only an oversized block. `corpus_sections` already holds parent `markdown`, `section_path`, depth, aliases.

**Asymmetry that matters:** the FTS trigger (migration `0007`) already weights the *deepest* TOC title `'A'` over body `'D'`. The **embedding is the raw chunk body**. Anthropic’s adapter sends `title = section_path[-1]` to the generator, so generation sees a heading the retriever’s semantic arm never encoded. Full ancestor path and book title are in neither embedding.

Answering (`prompts.py` + Citations API): “use only the documents; if they cannot answer, reply with exactly `NOT_FOUND_IN_SOURCE`.” Grounding (ADR-0003) intersects cited chunk ids with retrieved evidence. That is prompt-level abstention, not a sufficient-context check.

Eval: golden fixtures + labeled recall@k/MRR (deterministic arm at 1.0 on a 3-chunk book — `docs/ops/eval-calibration.md` records this as a known limitation) + nightly Opus judge (faithfulness ≥ 0.90, relevancy ≥ 3.1, ADR-0028 answered-only). RAGAS-the-library is not in the stack; the *metrics* (faithfulness, relevancy) already are. **Long-context fallback is accepted in ADR-0001 and absent from the codebase** (no `LongContextPort`, no router).

ADR-0006: reranker “only when the first implementation needs it.” RFC-005 froze “no new retrieval component” for that hardening window; this fleet is the next product bet, so a reranker is again an escape hatch — not a default.

---

## Technique-by-technique evidence

### 1. Contextual chunk headers (Anthropic Contextual Retrieval)

**Claim.** Isolated chunks lose entities, time, and section identity. Anthropic (2024-09-19) prepends 50–100 LLM-written tokens per chunk, then embeds *and* BM25-indexes the contextualized text. On their mix (code, fiction, ArXiv, science): contextual embeddings cut top-20 failure 35% (5.7% → 3.7%); + contextual BM25 49% (→ 2.9%); + Cohere rerank 67% (→ 1.9%). They explicitly report **generic document summaries and HyDE underperformed** this method. Prompt-cached Haiku contextualization ≈ **$1.02 / million document tokens** (~800-token chunks, ~8k-token docs). They also found **top-20 chunks beat top-10 and top-5**.

- Paper/post: [anthropic.com/engineering/contextual-retrieval](https://www.anthropic.com/engineering/contextual-retrieval)
- Cookbook: [platform.claude.com/cookbook/capabilities-contextual-embeddings-guide](https://platform.claude.com/cookbook/capabilities-contextual-embeddings-guide)

**Learny split.** Two implementations, not one:

| Variant | What | Cost | Fits one SQL? |
|---|---|---|---|
| **Structural headers** | Prepend `book_title › path.join(" › ")` (and maybe page_span) to a dedicated `embed_text`; keep `text` as citation snippet. Widen FTS from last-title-only to full path (weight ancestors `'B'`). | Re-embed + trigger change. Zero LLM. | **Yes** — same query, richer vectors/tsvectors |
| **LLM situating text** | Anthropic’s Haiku prompt with whole-document cache | ~$1/M doc tokens + ingest latency | **Ingest pipeline**, SQL unchanged once `embed_text` exists |

Learny already paid for the hard part Anthropic had to *generate*: a canonical section tree. Structural headers should be the default; LLM context is the increment if labeled recall still misses deictic chunks (“revenue grew 3%”). **Never put generated headers in the Citations `document` body** — Anthropic’s own note: distinguish context from chunk, or citations leak situating prose.

**Late chunking** (Jina, [arxiv:2409.04701](https://arxiv.org/abs/2409.04701)) embeds the whole document then mean-pools token spans. It needs a long-context embedding model that exposes token vectors. OpenAI `text-embedding-3-large` does not; adopting it would fight ADR-0019. Record as a named alternative if the embedding port ever grows a late-chunking adapter — not a v-next cycle.

### 2. Query rewriting, decomposition, RAG-Fusion, HyDE

**Rewrite / multi-query / RAG-Fusion.** Generate paraphrases (or sub-questions), retrieve each, fuse with RRF. Origin: Raudaschl 2023; formalized [Rackauckas, arXiv:2402.03367](https://arxiv.org/html/2402.03367). Fusion is the algorithm Learny already uses for dense+sparse. Extra queries are extra SQL executions of the *same* statement, then a Python (or SQL) RRF merge. Cost: 1 LLM call + N embed+search. Risk: off-topic paraphrases pollute the pool (Rackauckas observed this).

**Decomposition** for multi-hop. 2025–2026 papers (e.g. [Question Decomposition for RAG, arXiv:2507.00355](https://arxiv.org/html/2507.00355v1): MRR@10 +36.7%, F1 +11.6% on MultiHop-RAG/HotpotQA when paired with a cross-encoder) show gains on *compositional* questions. Book learners do ask “how does the model in ch.3 differ from the critique in ch.12?” — that is multi-hop over Learny’s own section graph.

**HyDE** ([Gao et al., ACL 2023](https://aclanthology.org/2023.acl-long.99.pdf) / [arxiv:2212.10496](https://arxiv.org/abs/2212.10496)): generate a hypothetical answer, embed *that*, retrieve real passages. Strong vs unsupervised Contriever in 2022; **Anthropic’s 2024 bake-off found it weaker than contextual retrieval** on knowledge-base RAG. For a cited book product it is the wrong default: a hallucinated “hypothetical chapter” in the author’s register can retrieve the wrong school of thought, and the extra generation sits on the user-latency path.

**Fit.** All of these are **pipeline steps in front of the existing SQL**, not a new index. A *single* rewrite of conversational anaphora (“what does *he* mean by that?” + last teacher turn + current section) is the Learny-shaped subset. Full RAG-Fusion (4 paraphrases × hybrid) multiplies OpenAI embed cost and HNSW load; defer until rewrite+headers are measured.

### 3. Cross-encoder rerankers (local vs Cohere/Voyage)

Rerank is retrieve-then-score-(query, doc) pairs. Anthropic used Cohere; +rerank was the last 18 points of their 67% failure cut, on **top-150 → top-20**.

**APIs (2026).**

- Cohere Rerank 4 (`rerank-v4.0-pro` / `fast`), 32k context, multilingual. Rerank 3.5 billed ~**$2 / 1k searches** (1 query × ≤100 docs = 1 search unit; docs >500 tokens split). Docs: [docs.cohere.com/reference/rerank](https://docs.cohere.com/reference/rerank.mdx), [docs.cohere.com/changelog/rerank-v4.0](https://docs.cohere.com/changelog/rerank-v4.0). Requires a **new SDK** → ADR cycle, fights “no new provider SDKs.”
- Voyage `rerank-2.5` / `lite`: $0.05 / $0.02 per 1M tokens, 32k pair window, instruction-following. [docs.voyageai.com/docs/pricing](https://docs.voyageai.com/docs/pricing). Voyage was already the *rejected* embedding alternative in ADR-0019. Same SDK tax.

**Local.** `BAAI/bge-reranker-v2-m3` (Apache-2.0, multilingual — relevant to Learny’s Portuguese-primary corpus) is the production open default; 2026 bake-offs put it within a few nDCG points of Cohere 3 on in-domain data, weaker OOD, **sub-100 ms** for ~50–100 candidates on GPU, CPU-viable at Learny’s 50-candidate cap. Qwen3-Reranker-4B/8B score higher and are heavier than a Compose VPS wants as a *first* sidecar.

**Fit.** **Pipeline after SQL**, never inside the RRF CTE. ADR-0006 already named this hatch. Implementation that respects the lock: a `RerankPort` with a **local** adapter (optional extra Compose service) and a no-op for CI. Do not add Cohere/Voyage until the local model is the measured bottleneck. Hardware: the current VPS Compose stack has no GPU story — CPU bge-m3 on 50 × 2k-char chunks is the honest cost; if that blows p95, *then* an API rerank is the escape hatch.

### 4. Parent-document / hierarchical retrieval

LlamaIndex `HierarchicalNodeParser` + `AutoMergingRetriever` and LangChain `ParentDocumentRetriever` encode the same idea: **search small, return large** when enough children of one parent hit. [LlamaIndex node parsers](https://developers.llamaindex.ai/python/framework/module_guides/loading/node_parsers/modules/).

Learny does not need those libraries (ADR-0009). `corpus_chunks.section_id → corpus_sections.markdown` *is* the parent store. After RRF, if ≥2 of the top-k share a `section_id` (or a parent in `section_path`), replace those snippets with the section markdown (capped), **keep the winning chunk’s anchor** as the citation identity so ADR-0003 stays exact. Teaching already subtree-filters; this is the Q&A dual: *expand* rather than *restrict*.

**Gain.** Fixes the “right sentence, missing surrounding argument” failure that 2000-char packing still produces when a claim spans two blocks in one section. **Cost.** One extra indexed read per distinct section; prompt tokens go up (watch lost-in-the-middle). **Fit.** Pipeline after SQL. Do not flatten hierarchy into overlapping chunk sizes — that would fight CORP-05.

### 5. Sentence-window retrieval

Embed one sentence; at generation time replace it with ±N neighbors ([TruLens/LlamaIndex cookbook](https://www.trulens.org/cookbook/frameworks/llamaindex/llama_index_sentencewindow/)). TruLens bake-offs show it is **not uniformly better**; large windows re-introduce noise.

Learny’s packer already concatenates blocks inside a section up to 2000 chars and only sentence-splits pathological blocks. Re-indexing books as sentence rows would explode HNSW cardinality, break 1:1 citation↔chunk, and duplicate what parent expansion does with real sections. **Skip for books.** A windowed variant is more plausible for *notes* if paragraph chunking still misses a single dense sentence.

### 6. Long-context synthesis fallback (ADR-0001, unimplemented)

Anthropic’s contextual-retrieval post: if the knowledge base is **< ~200k tokens (~500 pages), dump it in the prompt** and cache. [Lost in the Middle](https://aclanthology.org/2024.tacl-1.9.pdf) (Liu et al., TACL 2024): accuracy is U-shaped; middle evidence is underused. [Jin et al., 2024, arXiv:2411.03538](https://arxiv.org/pdf/2411.03538): Claude 3.5 / GPT-4o-class models keep improving with more RAG context out toward 100k; most open models peak then fall.

A real book is often 80–300k tokens. Whole-book dump is the wrong default (cost, latency, middle-loss, citation mapping). **Chapter-or-part dump** is the Learny-shaped fallback: detect synthesis queries (“summarize”, “how does the argument develop”, “compare parts I and II”), retrieve to identify candidate sections, then send `corpus_sections.markdown` for those sections as Citations documents (still Learny chunk/section ids). RAG remains the default for pinpoint questions.

**Fit.** Router + second generation path; not a SQL change. Cost: one Sonnet call over 10–40k tokens instead of 8×2k. Needs a query-type classifier (cheap: regex + one Haiku/Sonnet structured call, or even the existing generation model with a tool-less prefix). Citations must map to section anchors, which already exist.

### 7. Multi-hop / iterative retrieval

HotpotQA-style pipelines (retrieve → generate sub-question → retrieve again) add 1–3 extra round trips and error propagation. 2026 tree/prune variants ([PruneRAG](https://arxiv.org/abs/2601.11024), [RT-RAG](https://arxiv.org/html/2601.11255)) exist to cap that. For a **single owned book**, most “multi-hop” is *cross-section*, which parent expansion + query decomposition already covers without an agent loop. Cross-*book* hop is a product question this fleet should not silently open (authorization, citation UX). **Defer agentic loops.** Ship decomposition as an optional second retrieve fused into the same evidence list.

### 8. Paragraph-level note chunking (ADR-0026 recorded upgrade)

v1 embeds `body_markdown[:notes_embedding_max_chars]` (32k) as one vector. A long note’s embedding averages away a single paragraph the user just wrote — the exact retrieval miss second-brain Q&A will hit first. The 2026-07-18 notes research already chose a **parallel index**, not `corpus_chunks`. The upgrade is `note_chunks` (or split rows) with the same hybrid arms, still user-scoped, still cited as “Your note.” Cost: more embed calls on save (still cents). **Fit.** SQL template change (more note rows in existing arms), not a new engine.

### 9. RAG evaluation practice

Learny already implemented the important half of RAGAS *by hand*: claim-level faithfulness + relevancy, pinned judge (`claude-opus-4-8`), answered-only means (ADR-0028), calibration runbook. Official RAGAS still lists **Context Precision / Context Recall** as the retrieval half ([docs.ragas.io metrics](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/)). Langfuse’s 2026 guidance: faithfulness is a *pattern* (extract claims, NLI against context), not a library requirement.

**Gap:** the retrieval gate is saturated on a toy corpus; generation judge cannot tell a retrieval miss from a synthesis miss. Do not vendor RAGAS into the hexagonal core. Add (a) a **real-book labeled set** (author’s own corpus, not Gutenberg-in-git if licensing is unresolved — store privately, CI via nightly secret), (b) **context recall/precision** in `app.eval` against those labels, (c) keep the existing faithfulness judge. Thresholds: observed mean minus the same safety margins already in `eval-calibration.md`.

### 10. Quote-first grounding and abstention

Learny is ahead of typical RAG demos: Citations API + sentinel + post-hoc citation intersection. Remaining failure modes from 2024–2026:

- **Prompt abstention is a sufficiency check, not a conflict check.** [GRAB-RAG, 2026](https://arxiv.org/html/2608.22228): models abstain when context is *missing*, but still answer ~40%+ of *misleading* contexts. Learny’s notes-vs-book conflict rule (notes research §5) is the product instance of this.
- **More context can reduce abstention.** Google [Sufficient Context, arXiv:2411.06037](https://arxiv.org/pdf/2411.06037) / [research blog](https://research.google/blog/deeper-insights-into-retrieval-augmented-generation-the-role-of-sufficient-context/): RAG raised Gemma’s incorrect-answer rate dramatically vs closed-book; a separate **sufficient-context autorater** plus confidence beat prompt-only “say I don’t know.”
- **Quote-first.** Require the model to ground each claim in a cited span before paraphrase. Claude Citations already returns `cited_text`; the UI already has `[^n]`. A system-prompt addendum (“open with a short quotation or close paraphrase of the supporting span”) is cheap; a **pre-generation sufficient-context bit** (second structured-output call *without* Citations — they are mutually exclusive, ADR-0020) is the real upgrade, and can reuse the eval faithfulness prompt.

The 2026-09-03 walkthrough bug (Anthropic 400 → conversation deleted) is **reliability**, not retrieval — but it is how users will judge “smart answers.” Intelligence cycles should not ship without a surviving conversation + retry.

---

## Fit-assessment table

| Technique | Expected gain (honest) | Cost / complexity | Fits current single-SQL RRF? |
|---|---|---|---|
| Structural contextual headers (full path + title on embed/FTS) | High on books: closes the embed/FTS asymmetry; cheapest 80% of Anthropic’s “add context” result | Re-embed; optional `embed_text` column; FTS trigger widen | **Yes** |
| LLM contextual retrieval (Haiku situating text) | Medium extra on deictic chunks; Anthropic −35 to −49% fail@20 in *their* domains | ~$1/M doc tokens; ingest latency; prompt cache | Ingest only; SQL unchanged |
| Raise evidence `top_k` 8 → 12–20 | Medium; Anthropic: 20 > 10 > 5; watch middle-loss & $ | Prompt tokens, latency | **Yes** (knob) |
| Query rewrite (anaphora + section hint) | Medium on follow-ups / “this passage” | +1 generation + 1 embed per turn | **Pipeline** (N× same SQL) |
| RAG-Fusion (4 paraphrases) | Low–medium; pollution risk | ×N retrieve cost | Pipeline |
| HyDE | Low for cited books; Anthropic bake-off weak | +1 generation on latency path | Pipeline — **don’t** |
| Parent-section expansion | High given real hierarchy | Post-SQL join; bigger prompts | **Pipeline** |
| Sentence-window reindex | Low / negative vs section packer | Chunk explosion | Would fight CORP-05 |
| Chapter long-context fallback | High on synthesis / “whole book” Qs | Router + large prompt; cacheable | **Pipeline** (ADR-0001) |
| Multi-hop agent loop | Niche; overlapping with decomposition | Latency, error propagation | Pipeline — defer |
| Paragraph note chunks | High as notes grow | Extra table/rows; re-embed on save | **SQL arms grow**, same design |
| Local cross-encoder rerank | Medium–high precision@k; Anthropic’s last 18 pts | GPU optional; CPU p95 risk; new port | **Pipeline** (ADR-0006 hatch) |
| Cohere / Voyage rerank API | Similar quality, less ops | New SDK; per-query $; lock conflict | Pipeline — last resort |
| Dedicated vector DB | None at current scale | Ops, citation join split | **No** — escape hatch only |
| RAGAS library | Low vs current judge | Dependency, judge double-pay | Eval only |
| Context recall/precision + real-book labels | Unlocks every other cycle | Dataset work | Eval only |
| Quote-first prompt | Small | Prompt constant | Generation |
| Sufficient-context autorater | Medium on false-answer / weak evidence | Extra structured call | Pipeline (can’t share Citations request) |
| Late chunking | Medium in papers | Incompatible with locked embedding API | **No** without ADR-0019 reopen |

---

## Cycle-sized moves (ranked)

Each is one spec-driven cycle. Ranked by (gain × fit / cost), with **why-recommend** and **why-not**.

### 1. Structural headers + evidence budget (S–M)

**Do:** `embed_text` (or prepend into the embedding input only) = `"{title} — {section_path joined} — {text}"`; widen FTS to full path; keep `text` as the Citations snippet; re-embed via existing Celery path; raise `conversation_evidence_top_k` to 12 (then 20 if judge relevancy holds). Golden retrieval tests must assert citations still match body, not headers.

- **Why-recommend:** Uses structure already paid for; matches Anthropic’s largest cheap lever without Haiku-per-chunk; stays one SQL; Portuguese heading terms start contributing to *semantic* match, not only FTS `'A'`.
- **Why-not:** Re-embed the library (operationally already solved). If `embed_text` is accidentally sent as the citation document, the UI quotes TOC chrome. Headers will not fix true multi-hop or synthesis.

### 2. Retrieval ruler that can move (S)

**Do:** Nightly context-recall@k / MRR on **tens of real labeled questions** against a privately stored book (not the 3-chunk golden). Add context precision (fraction of retrieved chunks that a judge or human marks useful). Do not import RAGAS. Pin thresholds from observed means minus existing margins.

- **Why-recommend:** Calibration doc already admits the current retrieval gate is a crash detector. Without this, cycles 1/3/4 are unfalsifiable.
- **Why-not:** Labeling is author time. A copyrighted book in CI needs a secret fixture, not git. Over-gating on n≈20 will thrash.

### 3. Parent-section expansion (M)

**Do:** After RRF, merge sibling hits into `corpus_sections.markdown` (cap chars), preserve leaf `anchor`/`chunk_id` for citations. Tune merge threshold (e.g. 2+ hits). Optional: put expanded section at prompt edges (Lost-in-the-Middle).

- **Why-recommend:** Hierarchical retrieval without LlamaIndex; unique vs NotebookLM-class flatteners; teaching already thinks in sections.
- **Why-not:** Fat sections blow the token budget and bury the cited span. PDF-normalized “chapters” that are 15k chars need a cap + still-pass-the-winning-chunk. Eval must check citation still resolves.

### 4. Conversational query rewrite (S–M)

**Do:** If the turn has history or a non-empty conversation scope, one Anthropic call (existing generation adapter or a tiny rewrite port) produces a standalone search query; embed that; run the **existing** hybrid SQL once. Deterministic adapter: identity rewrite.

- **Why-recommend:** Dock Ask is beside the chapter — anaphora is the default user language. No new provider. Same SQL.
- **Why-not:** Extra latency before first token. Bad rewrites retrieve the wrong chapter; always fuse original+rewrite with RRF if shipping both. Do not start with 4-way RAG-Fusion.

### 5. Note paragraph chunks (M) — recorded ADR-0026

**Do:** Split `body_markdown` on blank lines / headings; embed each; keep whole-note row for listing. Same two note RRF arms, more rows, smaller `notes_snippet_chars` per hit.

- **Why-recommend:** Second-brain toggle is already on by default; whole-note vectors will fail first as notes lengthen. Design is pre-decided.
- **Why-not:** Overkill while notes are still short. Extra embed-on-save chatter. Don’t dump notes into `corpus_chunks` (re-ingest still kills those rows).

### 6. Chapter-level long-context fallback (M) — ADR-0001

**Do:** Classify synthesis vs pinpoint (start with lexical cues + optional model). For synthesis, take retrieval only to *choose sections*, then send those sections’ markdown as documents. Cache the section pack per source+scope (Anthropic ephemeral cache already used in teaching).

- **Why-recommend:** The established architecture hole; this is how “what is this book arguing?” becomes answerable without pretending RRF on 8 snippets is a synopsis.
- **Why-not:** Cost/latency; Lost-in-the-Middle; citation UX for a whole chapter. Whole-book dumps for 300k-token PDFs are in-scope only with a hard token cap. Needs cycle 2’s eval or you cannot tell fallback from regression.

### 7. Local rerank port (M) — escape hatch, not default

**Do:** After measuring cycles 1+3, if precision@k is the residue: `RerankPort` + `bge-reranker-v2-m3` over the SQL top-50, keep top 12–20. CI no-op. Optional Compose profile.

- **Why-recommend:** Anthropic’s stack order is hybrid+context *then* rerank; ADR-0006 already allows it; local model avoids a third cloud SDK and keeps Portuguese.
- **Why-not:** VPS CPU p95, model license/supply in the image, another moving part before public launch. Cohere/Voyage want an ADR and still may not beat headers+parents on a single book.

### 8. LLM contextual retrieval (M) — only if headers miss

**Do:** Ingest-time Haiku situating text with prompt cache; store beside `embed_text`; never in citation body.

- **Why-recommend:** Best published number in this list for remaining context-isolation.
- **Why-not:** Pays Claude on every re-ingest; Portuguese prompt must be authored; duplicates structural headers for many chunks. Run as an A/B on the new labeled set first.

### 9. Sufficient-context abstention (S)

**Do:** Structured-output judge (existing eval prompt family) on (question, evidence) *before* Citations generation; if insufficient, return `found=False` without calling the Citations path. Quote-first line in `ANSWER_SYSTEM_PROMPT`.

- **Why-recommend:** Walkthrough already showed a red “generation failed”; a calm “not in this book / not in this chapter” is the trust feature. Google’s sufficient-context result is the evidence prompt-only SENTINEL is incomplete.
- **Why-not:** Extra call and latency. Over-abstention on inferential questions (teaching will feel dumb). Keep SENTINEL as backup, not the only signal.

### Explicitly park

- **HyDE, sentence-window book reindex, agentic multi-hop, Qdrant/Weaviate, Cohere/Voyage SDKs, RAGAS-as-core, late chunking under OpenAI embeddings.** Revisit only with measured pain and an ADR.

---

## Implications for the public-launch arc

Smarter answers for a stranger are, in order: **retrieve the right passage in the right section**, **show enough surrounding argument**, **refuse when the book doesn’t say**, **synthesize when the question is the whole chapter**. Learny’s moat is the canonical tree plus citations — intelligence work should deepen that, not replace PostgreSQL.

Cycle 1 (headers + `top_k`) and cycle 2 (a retrieval ruler that can fail) are the unblocking pair. Everything else is a pipeline step on top of the statement that already exists.
