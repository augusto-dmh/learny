# RQ13 — Deeper AI integration: beyond “chat with your document”

*Fleet: public-launch research, 2026-09-03. Grounded in the shipped adapters (`infrastructure/answering/anthropic.py`, `embeddings/openai.py`, `quiz/anthropic.py`), ADR-0007/0009/0019/0020, and the product/API sources linked below. Not a decision record.*

## TL;DR

Learny is **already deeper than commodity PDF-chat in the backend**: native Claude Citations API (one document block per retrieved chunk), 1-hour prompt caching on Teach, Haiku Message Batches + JSON-schema for decks, OpenAI live embedding sub-batches, SSE UI Message Stream with reasoning, and a reader popover with Explain / Ask / Create card. The product still *feels* like a chat box next to a book. Peers that converted users did not add a smarter chatbot — they **wove generation into the surface**: NotebookLM Studio artifacts, Perplexity claim-level citations, Notion/Readwise selection verbs, Khanmigo practice-woven tutoring, Cursor background work.

The unused 2025–2026 API surface is narrower than it looks. Do **not** treat Citations, structured outputs, or Batches as greenfield — they are shipped. The real gaps are: (1) **answer-path caching and Haiku routing** for cheap selection turns; (2) **cited_text / char spans** sitting unused while the UI only gets chunk ids + `[^n]`; (3) **ingest-time artifacts** (chapter briefs) via the existing quiz-shaped batch pattern; (4) **review follow-ups** so AI is inside FSRS, not beside it; (5) **speech and vision** only after a new port (OpenAI TTS is the cheap speech path; vision is blocked on image extraction, RQ06). Stay behind `GenerationPort` / `EmbeddingPort` / `QuizGenerationPort`. New SDKs need an ADR cycle.

Highest-leverage cycle: **make selection and review the AI surface**, not a bigger Ask tab. Defer NotebookLM-style podcasts.

### What “woven” already means in this repo

Ask and Teach are one `GenerationPort` with `mode=` (ADR-0029), streamed through `POST /api/conversations/{id}/turns/stream`. The reader popover already has five verbs; Explain is a **fixed Sonnet chat template**, not a dedicated cheap turn. Quiz decks already are Studio artifacts (Celery + Message Batches). Review is still a self-grade with no model in the loop. Images never reach a model. There is no `SpeechPort` or `LongContextPort`. Teaching lives in `infrastructure/answering/` (shared adapter), not a `teaching/` package.

A stranger’s first AI action is therefore: type into Ask, or tap Explain and wait on Sonnet + adaptive thinking. That is still “chat with your document,” even though the corpus, citations, and FSRS behind it are not.

---

## 1. Reference-product evidence

Five interaction patterns, named independently of vendors:

| Pattern | What the user does | Who ships it well |
|---|---|---|
| **Selection-anchored action** | Highlight → one verb, result in place or in the dock | Readwise Ghostreader; Notion AI; Learny popover (partial) |
| **Claim-level citation** | Click a mark on a sentence, see the source without leaving the answer | Perplexity; Gemini Notebook chat |
| **Generated artifact** | One click produces a durable object (brief, deck, audio), not a chat turn | Gemini Notebook Studio; Learny quiz decks |
| **Proactive / woven assistant** | The product starts; skipping struggle is harder than engaging | Khanmigo v2; Cursor background agents |
| **AI-filled metadata** | Background job writes summary/tags onto the object | Ghostreader auto-summarize/auto-tag; Notion AI Autofill |

### Gemini Notebook (NotebookLM)

Studio is a **second pane**, not a chat. One click yields Audio Overviews (Deep Dive / Brief / Critique / Debate), Video Overviews, mind maps, reports, flashcards, quizzes; some artifacts auto-generate on first source add and do not count against quota ([create a notebook](https://support.google.com/gemininotebook/answer/16206563); [Audio Overview](https://support.google.com/notebooklm/answer/16212820); [Video Overview](https://support.google.com/gemininotebook/answer/16454555); [2026 student features](https://blog.google/innovation-and-ai/models-and-research/google-labs/notebooklm-student-features/)). Chat stays source-grounded with click-to-passage citations ([chat help](https://support.google.com/notebooklm/answer/16179559)).

**Fit for Learny:** the *artifact* pattern (chapter brief, outline, deck) matches ingest + Celery. The *podcast* pattern is table-stakes for “AI study studio” (RQ01) and **not** Learny’s citation/FSRS moat. Audio Overviews are known to drift; users are warned not to treat them as citable (RQ01). Copy Studio’s “generate in background, persist, reopen” — not the two-host radio show — as the first artifact.

### Perplexity

Every answer is retrieval-first with numbered inline citations; chips show publisher/domain; a popover or sidebar shows the excerpt; “wrong sources” is a feedback class ([citation UX teardown](https://aiuxplayground.com/teardowns/perplexity/citations); [how answers work](https://ziptie.dev/blog/how-perplexity-ai-answers-work/)). The model attaches citations **while generating**, not as a footnote pass.

**Fit:** Learny already does this architecturally (Citations API → `[^n]` → chip row → “Show in book”). The UX gap vs Perplexity is **claim-level hover**: marks sit in the prose, but the cited *sentence* from the API (`cited_text`, `start_char_index`) is discarded. The Vercel `InlineCitation` hover-card in `frontend/components/ai-elements/inline-citation.tsx` is unused by the product `citations.tsx`.

### Notion AI

Space-bar / highlight → Improve, Summarize, Translate, Change tone **in the page**; Autofill writes database properties in the background; Agents run on a schedule ([Notion AI 2026](https://aireviewslab.com/how-to-use-notion-ai/); [inline guide](https://www.eesel.ai/blog/notion-ai-inline)). Context is the surrounding page, not a paste into chat.

**Fit:** Learny’s five-verb popover is the Notion pattern. Explain currently **opens Ask and auto-submits a Sonnet turn** (`ask-panel.tsx` template `Explain this passage…`). That is one click too many for “define this term,” and it bills flagship generation. Autofill maps to **source metadata** (blurb, difficulty, key claims) written at ingest.

### Cursor

Tab / inline edit for local, cheap completions; Agent for multi-step; **background/cloud agents** for long jobs that return a reviewable artifact (diff, PR) ([subagents](https://cursor.com/docs/subagents); [background agents](https://cursor.com/docs/cloud-agent)). Work is not a second chat the user babysits.

**Fit:** Learny already has the Cursor *background* shape for decks (`begin_deck` / Celery poll). Missing: background **chapter briefs**, **note→card regenerate** visibility, and a cheap “Tab-like” path for selection verbs (Haiku, no adaptive thinking).

### Readwise Ghostreader

Selection scope changes the verb set (1–3 words → Define/Lookup/Translate; passage → Chat about this; none → document prompts). `G` / `Shift+G`. Auto-summarize and auto-tag write **document metadata**. Mobile Quick Lookup explains in context of the current article ([overview](https://docs.readwise.io/reader/guides/ghostreader/overview); [custom prompts](https://docs.readwise.io/reader/guides/ghostreader/custom-prompts); [Quick Lookup](https://docs.readwise.io/reader/guides/ghostreader/quick-lookup)).

**Fit:** Learny already branches by selection (Highlight / Note / Explain / Ask / Create card). Missing: **word-vs-passage verb sets**, Define/Simplify that do not open a conversation, and ingest-time summary/tag fields.

### Khanmigo

v1 was an optional chatbot next to content and did not move learning. v2 is **woven into practice**: the tutor sees the current problem, prompts the student to explain, and makes productive struggle harder to skip — “cognitive onloading” ([Sal Khan, 2026-07-15](https://blog.khanacademy.org/khanmigos-first-chapter-changed-how-i-think-about-ai-a-note-from-sal-khan/)). Pedagogy detail is RQ03; the *integration* lesson for this RQ: **AI that sits in a dock tab will be skipped.**

**Fit:** Review is Learny’s practice surface. A wrong grade with no follow-up is Khanmigo v1. A Haiku misconception probe that can mint one FSRS item is v2.

---

## 2. Capability inventory

Pricing as of 2026-09-03: Sonnet 5 **$2 / $10** per MTok (intro made permanent 2026-08-10, [Anthropic](https://www.anthropic.com/news/claude-sonnet-5)); Haiku 4.5 **$1 / $5**; cache reads **0.1×** input; 1h cache writes **2×**; Batch **50%** off ([models overview](https://platform.claude.com/docs/en/models/overview); [prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)). OpenAI `text-embedding-3-large` **$0.13 / $0.065** batch per MTok ([Batch API](https://developers.openai.com/api/docs/guides/batch)).

| Capability | Learny today | Available 2025–2026 | Gap |
|---|---|---|---|
| **Cited generation** | **Native Citations API.** One `text/plain` document per evidence chunk, `citations.enabled` all-or-none, map by `document_index` → `chunk_id`, `[^n]` marks, grounding intersect (ADR-0020). | Same API plus `cited_text` + `char_location` offsets; PDF `page_location`; Files API `file_id`; **image citations not supported** ([citations](https://platform.claude.com/docs/en/build-with-claude/citations)). | Adapter **drops** char spans / `cited_text`. `GeneratedAnswer` is `{text, cited_chunk_ids, model, found}` only. |
| **Citations ⊕ JSON** | Sentinel `NOT_FOUND_IN_SOURCE` because **400 if both** ([docs](https://platform.claude.com/docs/en/build-with-claude/citations)). | Unchanged incompatibility. | Keep two request shapes. Do not “fix” with tools. |
| **Prompt caching** | Teach: frozen system + latest history block, `ttl: "1h"`. Answer: **no** `cache_control`. Logs `cache_read_input_tokens`. | Explicit breakpoints **or** top-level automatic caching that walks the growing prefix. 5m default / 1h paid. | Cache `ANSWER_SYSTEM_PROMPT`. Automatic caching is a smaller teach-path simplification, not a product feature. |
| **Streaming** | `messages.stream` → `AnswerTextDelta` / `AnswerReasoningDelta` / `AnswerCompleted`; SSE UI Message Stream v1 (`text-*`, `reasoning-*`, `data-citations`, `data-answer-status`). | Citations also emit mid-block `citations_delta`; Learny waits for `content_block_stop` so stream == persist. | Correct for fidelity. Optional: stream citation chips earlier. |
| **Thinking / effort** | Adaptive thinking, `output_config.effort` from settings (default `medium`), `max_tokens=4096`. | Haiku uses extended thinking, not `effort`. | Effort on selection-Explain is latency waste. |
| **Structured outputs** | Quiz deck + `suggest_cards` / `suggest_note_cards`: `output_config.format.json_schema`, chunk-id **enum**. Judge uses structured outputs (eval). | GA `output_config.format` + `strict: true` tool use ([structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs); [strict tools](https://platform.claude.com/docs/en/agents-and-tools/tool-use/strict-tool-use)). | **No tool-use loop** in product. QC is Learny-owned substring/dedup, not a second model. |
| **Batch generation** | Anthropic Message Batches for decks (`quiz_model=claude-haiku-4-5`). | Same API; citations legal in batches; stacks with cache. | Decks only. Unused for briefs, tags, contextual headers (RQ05). |
| **Embeddings** | OpenAI live `embeddings.create`, greedy ≤2048 inputs / ~250k tokens. Query embed on every Ask/Teach turn. | **Batch API 50% off**, 24h SLA, 50k embedding inputs/batch. | Ingest pays full price for a job the user already waits on via Celery. |
| **Small-model routing** | Generation always `claude-sonnet-5`. Quiz/suggestions Haiku. Judge Opus. | Haiku supports citations. ~½ input / ½ output vs Sonnet 5. | No `GenerationPort` model-per-call. Explain/Ask-about-selection billed as flagship. |
| **Multimodal** | Reader: Streamdown `rehype-harden` → `[Image blocked: …]` (RQ06). Corpus keeps `img` blocks as `![alt](epub-relative-src)`. **No image bytes to Claude.** | Vision `image` blocks; PDF document blocks (text+page images, ≤100 pages) ([vision](https://platform.claude.com/docs/en/build-with-claude/vision); [PDF support](https://platform.claude.com/docs/en/build-with-claude/pdf-support)). Image citations still impossible. | Blocked on **extracting binaries to MinIO** first. Do not send whole PDFs as a second corpus (fights ADR-0002). |
| **Audio** | None. | **No Anthropic TTS.** OpenAI `/v1/audio/speech` (`tts-1` $15/1M chars; `gpt-4o-mini-tts` ~$0.015/min) ([speech](https://developers.openai.com/api/reference/resources/audio/subresources/speech/methods/create)). ElevenLabs = new SDK. | Needs a `SpeechPort`. OpenAI is already a Learny provider (ADR-0019) — no new vendor if TTS stays behind that SDK in a new adapter. |
| **Long-context fallback** | ADR-0001 accepted; **no port**. | Sonnet 5 1M context. | RQ05; not this report’s first move. |
| **Selection UI** | Five verbs; Explain auto-submits Sonnet chat. | Ghostreader-style Define vs passage vs document. | Verbs exist; **cheap dedicated turns** do not. |

**Request-shape split (do not collapse).** Flagship turns: citations-enabled documents + sentinel + optional thinking. Deck/brief/blurb turns: `output_config.format` JSON, chunk ids as schema enums, **no** citation documents. Mixing them is a 400 — this is the likely class of failure behind the 2026-09-03 walkthrough’s Anthropic 400 (wrong shape / thinking / effort), not “we forgot citations.”

**Files API / PDF-as-document.** Upload-once `file_id` is fine *inside an adapter* for a one-off vision pass. It must not replace `corpus_chunks`. Scanned PDFs without a text layer are not citable ([citations](https://platform.claude.com/docs/en/build-with-claude/citations)). Learny already OCRs via Docling (ADR-0025); keep that as the canonical text.

Ports (ADR-0007): SDKs stay in adapters. Do not add LangChain. A new capability = extend an existing port **or** add a Learny Protocol (`SpeechPort`, later) wired in `dependencies.py`. Deterministic adapters remain the CI default: any new `generate_brief` / `synthesize_speech` method needs a network-free fake that returns fixtures.

---

## 3. Product-idea catalog (port + cost)

Costs are order-of-magnitude for a ~400-page book (~300k words ≈ ~400k tokens) or a single user action. Sonnet 5 $2/$10, Haiku $1/$5, batch 0.5×.

| Idea | User value | Port | Incremental cost | Notes |
|---|---|---|---|---|
| **A. Claim-level citations** | Hover/click `[^n]` shows the API quote; “Show in book” can highlight the char span inside the chunk | Extend `GeneratedAnswer` with Learny `CitedSpan{chunk_id, quote, start, end}` — **adapter maps Citations API, domain never sees `document_index`** | ~$0 (already paid in the generate call; `cited_text` is not billed as output) | Highest trust-UX per dollar. Frontend already has chip + passage; wire `cited_text` into the open passage and unused `InlineCitation` hover. |
| **B. Cache the answer prefix** | Faster/cheaper follow-ups in Ask | `GenerationPort` adapter only | First write 2× on ~1k system tokens; hits 0.1×. Ask is often single-shot → break-even only with history. | Cheap; do with C. |
| **C. Haiku selection turns** | Explain/Define in <3s beside the quote; no conversation unless they continue | `GenerationPort.generate(..., model_hint=)` or a settings-selected “fast” model on `mode=answer` when evidence is a single section | ~$0.003–0.008 vs ~$0.015–0.03 Sonnet; skip thinking | Reuse Citations API (Haiku supports it). Keep Sonnet for typed Ask/Teach. Eval gate on the Haiku arm before flipping Explain. |
| **D. Chapter briefs at ingest** | Book opens with a cited 8–12 sentence brief + outline per chapter — Studio artifact, not chat | **New methods on `QuizGenerationPort`** (same batch + json_schema shape) *or* a thin `CorpusEnrichmentPort` if the result is not quiz-shaped | Haiku batch: ~300 sections × ~2k in / 400 out ≈ **$0.15–0.40/book**; cache a frozen brief prompt | Persist on `corpus_sections` (or a child table). Cite section anchors. Fail open: missing brief ≠ failed ingest. |
| **E. AI source blurb + tags** | Library cards show a grounded one-liner; tags for “dense textbook / narrative” | Same as D, one batch request per book | **<$0.02/book** Haiku | Ghostreader auto-summarize. Do not invent marketing copy beyond the corpus. |
| **F. Semantic search-as-you-type** | TOC/reader filter that ranks by hybrid search, not `title.contains` | Existing `EmbeddingPort.embed_query` + `RetrievalPort.search`; debounce in the web adapter | 1 embed/query after 200ms / 3 chars. `text-embedding-3-large` query is tiny (**≪$0.0001**) | No new provider. Cap `top_k=8`. This is intelligence users feel before they chat (RQ07). |
| **G. Misconception follow-up** | After Again/Hard, optional “why might someone miss this?” + one extra item | `QuizGenerationPort.suggest_cards` (passage already on the item) + optional Teach turn | Haiku ~$0.005/follow-up; opt-in so it does not tax every review | Khanmigo-in-Learny. RQ03/RQ04 own pedagogy/QC; this RQ only places the **surface**. |
| **H. Query rewrite for anaphora** | “what does *he* mean?” uses last turn + section | One extra `GenerationPort` (Haiku, structured `{rewritten}`) then existing retrieve | +1 Haiku call on follow-ups only | RQ05; citations still on the second (Sonnet) call. |
| **I. OpenAI embedding Batch** | Same vectors, 50% ingest embed cost | `EmbeddingPort` async collect, like quiz batches | 400k tokens × $0.13 → $0.05; batch **$0.026**. Latency +minutes | Worth it when ingest already waits on PDF/Docling. Bad if it delays “Ready” past current embed time. |
| **J. TTS read-aloud** | Listen to the current chapter (accessibility + commute) | **New `SpeechPort`**; OpenAI `tts-1` adapter (SDK already allowed under ADR-0019) | ~$0.02–0.08/chapter (`tts-1`); cache audio in MinIO | Not NotebookLM. Read **corpus markdown**, not a generated script. |
| **K. Audio overview** | Two-host podcast of the book | `GenerationPort` script (Sonnet, **no citations in the audio**) + `SpeechPort` ×2 | Script ~$0.05–0.20 + TTS $0.20–1.00/book; drift risk | Table-stakes vs NotebookLM (RQ01/RQ12). Defer until J exists and eval can score groundedness of the *script*. |
| **L. Diagram understanding** | “What does this figure show?” with the image in evidence | `GenerationPort` `image` blocks **after** MinIO-backed figure URLs (RQ06) | Vision tokens dominate; a few figures/turn is fine, a chapter of figures is not | Cannot cite the image (API limit). Cite the caption/section text; treat vision as supporting context. |
| **M. Proactive Teach open** | Opening Teach starts with a tutor question on the section | Prompt + first turn from `GenerationPort` (RQ03 playbook); cache already there | One Sonnet turn ~$0.02 | Integration pattern from Khanmigo; pedagogy from RQ03. |

**Worked public-launch cost (order of magnitude).** 1k DAU, 2 Ask turns + 1 Explain + 0.3 deck regenerations + 1 ingest/week/user is the wrong model — most users will *read*. A realistic early mix: 40% never call a model after ingest+deck; 40% Explain a few times; 20% Ask/Teach heavily.

| Event | Model | Est. USD |
|---|---|---|
| Ingest embed (400k tok, live) | OpenAI 3-large | $0.05 |
| Deck (100 chapter-level Haiku batch items) | Haiku batch | $0.20–0.50 |
| Chapter briefs (same grain) | Haiku batch | $0.15–0.40 |
| Typed Ask/Teach turn (5k in / 0.6k out, uncached) | Sonnet 5 | ~$0.016 |
| Same turn, 1h cache hit on 4k prefix | Sonnet 5 | ~$0.007 |
| Explain-on-selection (2k in / 0.3k out, no thinking) | Haiku | ~$0.004 |
| TTS one chapter (~3k words) | `tts-1` | ~$0.05 |

At 1k DAU × 2 Sonnet turns/day, generation is ~$32/day before caching/Haiku. Routing Explain to Haiku and caching Ask follow-ups is the cost control that makes a free tier survivable (RQ10); Audio Overviews at $0.50–1.00/book are not.

**Do not do:** managed Anthropic Files-as-corpus (fights ADR-0002/0006); sending the whole EPUB as one PDF document; LangChain agents; ElevenLabs until `SpeechPort` + OpenAI TTS is proven; per-keystroke Sonnet; a second chat tab named “Studio.”

---

## 4. Cycle-sized moves

Each is one spec-driven PR-shaped cycle. Why-recommend **and** why-not, as required.

### Cycle 1 — Claim-level citations (A)

**Why recommend:** Trust is the brand (ADR-0003). The API already returns the sentence; the UI already has chips and “Show in book.” Shipping `CitedSpan` is an adapter + view change, not a new model. Matches Perplexity without copying web-search.

**Why not:** Char offsets are into the **snippet sent to Claude**, which must stay byte-identical to the highlighted reader span — any embed-header prepend (RQ05) must stay out of the Citations `document` body (Anthropic’s own warning). Misaligned offsets look worse than `[^n]`. Needs golden tests on offset identity.

### Cycle 2 — Fast selection path (B+C)

**Why recommend:** The popover already promises “Explain this.” Making it Haiku, section-scoped, no thinking, cached system prompt is the Ghostreader/Notion leap. Cuts latency and public-launch token burn (every stranger will mash Explain). `LEARNY_GENERATION_MODEL` stays Sonnet for typed Ask/Teach.

**Why not:** Two models on one port means two eval arms. Haiku may over-cite or sentinel-flinch. If the 400 in the 2026-09-03 walkthrough is request-shape fragility, adding a second shape increases that risk — land Cycle 1’s parser tests first.

### Cycle 3 — Ingest briefs + library blurb (D+E)

**Why recommend:** Studio artifacts without audio. Reuses Message Batches + structured outputs + QC-against-corpus (quote containment). Celery already owns ingest. First-open value for a stranger (RQ07) without a chat.

**Why not:** Another failure mode on ingest (“Ready” but empty briefs). Cost scales with section count; a pathological TOC could submit thousands of batch items — cap to chapter-level (`depth <= 1`) not every leaf. Must not block `ready` on enrichment.

### Cycle 4 — Review follow-up (G)

**Why recommend:** Woven AI on the only daily ritual. Uses `QuizGenerationPort.suggest_cards` (already sync, QC’d, highlight-scoped). Khanmigo’s published correction.

**Why not:** Review latency is sacred (RQ04). A 30s popover after every Again will train people to skip. Must be **opt-in or only after Again**, never on Good/Easy. Formulation QC from RQ04 should land first or follow-ups will mint T1 junk into FSRS.

### Cycle 5 — Typeahead retrieve (F)

**Why recommend:** Makes hybrid search visible. Tiny cost. No prompt. Feels “intelligent” in the reader chrome.

**Why not:** `embed_query` on a noisy prefix retrieves garbage; need min-length + debounce + cancel-in-flight. Do not run this on the public landing page.

### Parked (why-not as the headline)

- **Audio Overviews (K):** why-not — new `SpeechPort`, uncited speech, cost and eval hole, NotebookLM already owns it. **J (read-aloud of real chapter text)** is the honest first audio cycle.
- **Vision (L):** why-not — figures are not even *shown*; RQ06 image extraction is the prerequisite. Claude cannot cite images.
- **Embedding Batch (I):** why-not as a product cycle — 50% of a rounding error at hobby volume; only pair with ingest if Ready-time does not regress.
- **Automatic prompt caching:** why-not as a named cycle — adapter-internal; ship inside Cycle 2.

**Suggested order:** 1 → 2 → 3, with 5 parallelizable after 1. Cycle 4 after RQ04’s formulation QC (or it writes bad cards). J (read-aloud) after RQ06 if it should speak captions; otherwise it can follow 2 using chapter markdown only. K/L never in the first public-launch RFC slice.

```
Cycle 1 (cited spans) ──┬── Cycle 2 (Haiku Explain + answer cache)
                        ├── Cycle 5 (typeahead retrieve)
                        └── Cycle 3 (ingest briefs) ── Cycle 4 (review follow-up, after RQ04)
```

Verification for any of these: golden fixtures stay on the deterministic adapter; a live Anthropic/OpenAI arm is nightly-only (ADR-0016/0028). New structured-output schemas get a local adapter that emits legal JSON so CI does not need keys.

---

## 5. What this RQ does not decide

- Teach playbook / hint ladder → RQ03.
- Card formulation rubric / empty-deck UX → RQ04.
- Contextual embed headers / reranker / long-context → RQ05.
- Showing images in the reader → RQ06.
- Positioning vs NotebookLM podcasts on the landing page → RQ12.

The integration rule for RFC-004: **every new model call must attach to an existing user object** (selection, section, quiz item, source row) or to an ingest job. If the only home is a new chat tab, it is not deep enough.

## Sources (primary)

- Anthropic: [Citations](https://platform.claude.com/docs/en/build-with-claude/citations), [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching), [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs), [Vision](https://platform.claude.com/docs/en/build-with-claude/vision), [PDF support](https://platform.claude.com/docs/en/build-with-claude/pdf-support), [Models / pricing](https://platform.claude.com/docs/en/models/overview), [Sonnet 5 pricing note](https://www.anthropic.com/news/claude-sonnet-5)
- OpenAI: [Batch API](https://developers.openai.com/api/docs/guides/batch), [Speech](https://developers.openai.com/api/reference/resources/audio/subresources/speech/methods/create)
- Products: [Gemini Notebook create](https://support.google.com/gemininotebook/answer/16206563), [Audio Overview](https://support.google.com/notebooklm/answer/16212820), [Khanmigo / Sal Khan 2026-07-15](https://blog.khanacademy.org/khanmigos-first-chapter-changed-how-i-think-about-ai-a-note-from-sal-khan/), [Ghostreader](https://docs.readwise.io/reader/guides/ghostreader/overview), [Cursor subagents](https://cursor.com/docs/subagents)
- In-repo: ADR-0007, ADR-0009, ADR-0020; `docs/research/2026-07-12/anthropic-generation.md`; RQ01, RQ03–RQ06
