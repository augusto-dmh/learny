# Learny v2 research — active-recall-srs

Generated 2026-07-12 by a web-research agent (v2 planning research fleet). Sources/dates inline; verify load-bearing claims before implementation.

---

# Active Recall + Spaced Repetition for Learny v2 — Research Report

## 1. Recommended MVP scope

**Build now:**
- **QA-style quiz items** (free-recall question + reference answer, LLM-graded or self-graded) + **cloze items** as a second type. Both generated per corpus section, each grounded in exactly one passage anchor with a snapshotted text excerpt.
- **FSRS-6 scheduling via py-fsrs** with default parameters, 4-button rating (Again/Hard/Good/Easy), `desired_retention=0.9`, fuzzing on.
- **Review session endpoint**: "due cards for user" query, review submission that appends to a review log and updates card state, "show source" that resolves the anchor to the live corpus (fallback to snapshot).
- **Generation QC pipeline**: grounding check (answer must be entailed by the source chunk), dedup within a book, self-critique filter pass.

**Defer:**
- **FSRS parameter optimizer** — it's a separate `pip install "fsrs[optimizer]"` extra (pulls torch/pandas); default 21 weights are what every new Anki user runs on, and optimization only pays off after hundreds of reviews per user. Ship a nightly/monthly Celery task later ([py-fsrs README](https://github.com/open-spaced-repetition/py-fsrs), v6.3.1, Mar 2026).
- **MCQ/distractors** — evidence says recognition formats add no retention benefit over short-answer (see §3) and distractor quality is the hardest LLM QC problem. Skip distractor columns for MVP; keep the door open in the schema via a nullable JSONB field.
- Per-user desired-retention settings, deck/tag organization, leech detection, interleaved multi-book sessions, Ragas-style eval dashboards.

## 2. FSRS integration recipe

**State of FSRS, mid-2026:** FSRS-6 is current; it's the built-in scheduler family in Anki (FSRS shipped natively in Anki 23.10; FSRS-6 available since Anki 25.07). FSRS-6 has **21 parameters** (adds w20, a personalizable forgetting-curve shape) vs FSRS-5's 19; FSRS-4.5 is legacy ([fsrs4anki releases](https://github.com/open-spaced-repetition/fsrs4anki/releases), [Expertium's technical explanation](https://expertium.github.io/Algorithm.html), [Anki forums FSRS-5 vs 6](https://forums.ankiweb.net/t/fsrs-5-vs-6-is-there-any-statictical-data-that-proofs-that-the-new-version-of-fsrs-6-is-better-than-previous-ones/59748)).

**py-fsrs** ([GitHub](https://github.com/open-spaced-repetition/py-fsrs), [PyPI `fsrs`](https://pypi.org/project/fsrs/)): v6.3.1 (Mar 10, 2026), MIT license, ~450 stars, 36 releases, Python 3.10+, maintained by the open-spaced-repetition org (same org as Anki's FSRS engine). Mature enough to depend on. **All datetimes must be UTC** — matches Learny's conventions.

Minimal correct integration (this is genuinely all of it):

```python
from fsrs import Scheduler, Card, Rating, State

scheduler = Scheduler(          # defaults shown
    desired_retention=0.9,
    learning_steps=(timedelta(minutes=1), timedelta(minutes=10)),
    enable_fuzzing=True, maximum_interval=36500,
)
card = Card()                                  # new card
card, review_log = scheduler.review_card(card, Rating.Good, review_datetime=now_utc)
# persist card fields + review_log row; card.due drives the "due" query
```

- **Card states:** `Learning` → `Review` → `Relearning` (on lapse). py-fsrs manages transitions; you never write state logic.
- **Rating scale:** Again=1, Hard=2, Good=3, Easy=4. Map UI buttons 1:1; don't invent your own scale — FSRS weights are trained on it.
- **Persistence:** `Card.to_dict()`/`from_dict()` exist, but for Postgres store the fields as real columns (`state, step, stability, difficulty, due, last_review`) so `WHERE due <= now()` is indexable. Keep `ReviewLog` rows forever — they are the optimizer's training data and your analytics.
- **Learny hexagonal fit:** wrap py-fsrs behind a `SchedulingPort` (domain speaks "review item, get next due"; adapter speaks py-fsrs). It's deterministic and network-free — trivially unit-testable, consistent with your existing deterministic adapters.
- **Optimizer at MVP: no.** Defaults are the population-fit weights; Anki users run these until they accumulate review history. When added later: Celery beat task per user, feed all `ReviewLog` rows, store the 21 floats per user (or per user+book) in a `fsrs_params` row, version them.

## 3. Learning science → quiz design rules

- **Testing effect is the bedrock:** retrieval practice beats rereading across hundreds of studies; effortful retrieval strengthens memory ([Retrieval-Based Learning: A Decade of Progress](https://files.eric.ed.gov/fulltext/ED599273.pdf); [forward testing effect, PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC3983480/)).
- **Recall vs recognition:** a 2024 RCT comparing very-short-answer vs MCQ retrieval practice found **no retention difference**, but VSAQ had better diagnostic value and exposed misconceptions; VSAQ needs feedback because initial success is lower (58.6% vs 73.9%) ([PMC11684041](https://pmc.ncbi.nlm.nih.gov/articles/PMC11684041/), 2024). Combined with distractor-generation risk, this justifies MVP = free recall + reference answer shown after rating (self-grade, Anki-style) — feedback is built into the flow.
- **Successive relearning (Rawson & Dunlosky):** the prescriptive recipe is ~3 correct recalls in initial learning, then 1 correct recall per spaced session; spaced correct recalls beat massed ones for retention ([Rawson & Dunlosky 2022, Current Directions](https://journals.sagepub.com/doi/full/10.1177/09637214221100484); [retrievalpractice.org](https://www.retrievalpractice.org/strategies/2018/successive-relearning)). FSRS's Learning steps + Review state implement exactly this pattern.
- **Questions per section:** no hard evidence for a fixed number — density should follow testable concepts, not length. Practical heuristic: **3–6 items per leaf section**, one concept per item (SuperMemo's "minimum information principle"). Flagged as heuristic, not evidence.
- **Interleaving:** strongest evidence is for discrimination between similar categories (math/motor learning); FSRS due-date fuzzing plus shuffling due cards across sections/books gives you interleaving for free. Don't build anything explicit at MVP.
- **Cloze:** widely used (Anki first-class type), good for terminology/definitions; QA better for application/why questions. Ship both, bias toward QA.

## 4. Generation + QC patterns, prior art

**Savaal** ([arXiv 2502.12477](https://arxiv.org/pdf/2502.12477), Feb 2025) is the best prior art: a three-stage concept-driven pipeline (extract main ideas → rank/select concepts → retrieve passages and generate questions with retrieved context, not the whole document), evaluated by 76 human experts; beat direct whole-document prompting on depth-of-understanding by 1.5–6.5×. Its evaluation rubric — **Specificity, Objectivity, Groundedness, Quality** — is directly reusable as an LLM-judge checklist. Key transferable insight: **generate from retrieved/sectioned context, never whole-book context** — which Learny's corpus sections already give you.

**Recipe for Learny (Celery task per section, after ingest/embed):**
1. **Generate** — prompt with: section text + section path + book metadata; ask for N items as JSON: `{type: qa|cloze, question, answer, anchor_quote}` where `anchor_quote` must be a **verbatim quote from the section** supporting the answer. Requiring a verbatim quote is the single highest-leverage grounding trick: you can validate it with a string/normalized match against the chunk, no second LLM call. (This mirrors how Anthropic's [Citations API](https://docs.claude.com/en/docs/build-with-claude/citations) grounds spans in provided documents — a natural upgrade path when Claude adapters land, but the quote-then-verify pattern works with any model.)
2. **Validate (deterministic):** anchor_quote found in chunk → map to anchor; JSON schema valid; question ≤1 concept (length caps); answer non-empty.
3. **Critique (LLM pass):** judge each item against Savaal-style rubric — answerable from the quote alone (groundedness), unambiguous, not trivially contained in the question, tests understanding not copy-paste. Drop failures; don't repair (regeneration is cheaper than repair loops).
4. **Dedup:** embed question+answer with the existing EmbeddingPort; reject items with cosine similarity above ~0.9 to an accepted item in the same book, plus exact normalized-text match. (OSS flashcard generators — [obsidian-flashcards-llm](https://github.com/crybot/obsidian-flashcards-llm), [remnote-flashcard-generator](https://github.com/GrannyProgramming/remnote-flashcard-generator), [Median](https://github.com/5uru/Median) — mostly skip QC entirely; chunk-then-generate plus your embedding infra already puts you ahead of the OSS field.)

## 5. Citation-grounded design & surviving re-ingest

Prior art for anchor-tied, regeneration-safe cards is thin; the closest is **Anki's GUID upsert**: notes carry a stable GUID so re-import **updates content in place while preserving card scheduling** ([Anki manual, text-file import](https://docs.ankiweb.net/importing/text-files.html)). Adopt the same principle:

- Each quiz item stores **both** a live anchor reference (`document_id + section_path + anchor`) and a **snapshot** (`source_excerpt`, chunk hash) — same pattern as Learny's teaching-turn citation snapshots. "Show source" resolves the live anchor; if the anchor vanished after re-ingest, show the snapshot with a "source changed" badge.
- On re-ingest, a Celery reconciliation step per item: anchor still exists and chunk hash unchanged → keep; anchor exists but text changed → re-run grounding check (is `anchor_quote` still present?), pass → keep scheduling, fail → mark `stale`; anchor gone → try relocating the quote via exact/FTS match in new corpus, else `orphaned`. **Never delete review state** — FSRS memory state describes the user's memory, not the document. Stale/orphaned items are suspended from the due queue pending regeneration or user dismissal.
- Store a `content_key = hash(normalized question+answer)`: if regeneration after re-ingest produces an equivalent item, upsert onto the existing row (Anki-GUID style) and keep its FSRS state.

## 6. Data model sketch (PostgreSQL)

```
quiz_items
  id uuid PK, user_id FK, document_id FK
  item_type text ('qa'|'cloze'), question text, answer text
  distractors jsonb NULL                      -- deferred, keep column
  section_path text, anchor text              -- live citation reference
  source_excerpt text, chunk_hash text        -- snapshot (re-ingest survival)
  content_key text                            -- dedup/upsert identity
  status text ('active'|'stale'|'orphaned'|'suspended'|'rejected')
  generation_meta jsonb                       -- model, prompt version, critique scores
  UNIQUE (user_id, document_id, content_key)

quiz_item_scheduling            -- 1:1 with quiz_items at MVP (per-user items);
  quiz_item_id PK/FK            -- split keeps FSRS columns swappable/regenerable
  state smallint, step smallint NULL
  stability float NULL, difficulty float NULL
  due timestamptz NOT NULL, last_review timestamptz NULL
  INDEX (due) WHERE status-eligible           -- the "due cards" query

review_log                      -- append-only; optimizer training data
  id PK, quiz_item_id FK, user_id FK
  rating smallint (1-4), review_datetime timestamptz
  review_duration_ms int NULL
```

Everything lives in Postgres (source of truth, per CLAUDE.md); Redis stays transport-only. Anki's model (notes → cards → revlog, GUID identity) validates the split of *content* (quiz_items) from *scheduling state* (quiz_item_scheduling) from *history* (review_log) ([Anki import/export internals](https://deepwiki.com/ankitects/anki/3.7-import-and-export)). Since items are generated per user per book (not shared), 1:1 item↔scheduling is fine at MVP; the table split future-proofs shared decks.

**Uncertainties flagged:** questions-per-section count is heuristic, not evidence; Savaal's per-stage prompts weren't in the abstract (full PDF worth reading before writing prompts); FSRS-6 availability details in Anki reflect release notes as of mid-2026 — pin py-fsrs to `>=6,<7` since major versions track the FSRS model.

**Sources:** [py-fsrs](https://github.com/open-spaced-repetition/py-fsrs) · [fsrs PyPI](https://pypi.org/project/fsrs/) · [fsrs4anki releases](https://github.com/open-spaced-repetition/fsrs4anki/releases) · [FSRS technical explanation](https://expertium.github.io/Algorithm.html) · [Anki FSRS forum thread](https://forums.ankiweb.net/t/fsrs-5-vs-6-is-there-any-statictical-data-that-proofs-that-the-new-version-of-fsrs-6-is-better-than-previous-ones/59748) · [VSAQ vs MCQ, 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11684041/) · [Retrieval-based learning decade review](https://files.eric.ed.gov/fulltext/ED599273.pdf) · [Forward testing effect](https://pmc.ncbi.nlm.nih.gov/articles/PMC3983480/) · [Rawson & Dunlosky 2022](https://journals.sagepub.com/doi/full/10.1177/09637214221100484) · [Successive relearning strategy](https://www.retrievalpractice.org/strategies/2018/successive-relearning) · [Savaal, arXiv 2502.12477](https://arxiv.org/pdf/2502.12477) · [Anki text-file import (GUID upsert)](https://docs.ankiweb.net/importing/text-files.html) · [Anki import internals](https://deepwiki.com/ankitects/anki/3.7-import-and-export) · [Claude Citations API](https://docs.claude.com/en/docs/build-with-claude/citations) · OSS generators: [obsidian-flashcards-llm](https://github.com/crybot/obsidian-flashcards-llm), [remnote-flashcard-generator](https://github.com/GrannyProgramming/remnote-flashcard-generator), [Median](https://github.com/5uru/Median)
