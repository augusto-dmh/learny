# RQ04 — Active-recall quality

*Research memo for the 2026-09-03 public-launch fleet. Grounded in ADR-0021, the current quiz/review code, and the sources listed below. Not a decision record.*

## TL;DR

Great flashcards are **atomic, unambiguous, effortful, and stable months later**. Mediocre ones are grounded-looking trivia: whole-sentence answers, stopword clozes, list dumps, and questions that leak the answer. Learny already has the right *architecture* for a quality product — free-recall + single-mask cloze, server-verified verbatim quotes, embedding dedup, FSRS-6, citation snapshots, a human accept/edit/discard path for highlights and notes. What it does **not** have is a *formulation* bar. The deck prompt asks only for “3 to 6 items”; QC checks only schema, quote containment, cloze blank, and cosine ≥ 0.90. A deck that generates **zero reviewable items is reported as success**, and the library UI shows nothing. Review is a correct 4-button self-grade with Space/1–4, but it has no undo, no interval preview, no flag/edit/suspend, and it snapshots the due queue so FSRS’s 1- and 10-minute learning steps never reappear in-session.

Public-launch bar: (1) explain empty/thin decks with discard reasons, (2) enforce a deterministic formulation rubric on every candidate, (3) make auto-decks previewable like highlight suggestions, (4) add undo + flag/edit on review. Keep the 4-button FSRS scale. Defer per-user FSRS fitting, LLM critique, and two-button grading.

---

## Evidence

### Knowledge formulation (what “great” means)

- **[Wozniak, *Twenty rules of formulating knowledge*](https://www.supermemo.com/en/blog/twenty-rules-of-formulating-knowledge)** (1999, still the SRS canon). Highest-leverage rules for Learny: do not memorize what you do not understand; **learn before you memorize**; **minimum information principle** (one fact, short answer); cloze is the beginner-friendly converter of textbook prose; **avoid sets and enumerations**; combat interference; optimize wording; provide sources. The Dead Sea example is the test: one bloated paragraph-QA is slower to retain than nine atomic items.
- **[Matuschak, *How to write good prompts*](https://andymatuschak.org/prompts)** and the [prompt-attribute notes](https://notes.andymatuschak.org/z9xavmmNq7xvNqzpnJ3HFXx): concise, one atomic unit, unambiguous answer shape, effortful (not yes/no, not pattern-matchable), self-contained (reviewable without the source open), encode from multiple angles. His [cloze caution](https://notes.andymatuschak.org/zPJt42JTcoAPTTTa2vdDonV): pasted-sentence clozes are cheap to write and tend to produce shallow pattern matching because leftover syntax hints the blank.
- **Atomicity vs context.** SuperMemo wants the *answer* tiny. Matuschak wants the *cue* self-contained. Anki medical decks often keep a sentence of clinical context around a single cloze. Excess context is the failure mode discussed in [Anki forums on image occlusion / excess context](https://forums.ankiweb.net/t/image-occlusion-and-the-problem-of-excess-context-in-flashcards/55947): learners memorize word order, not the fact. The Learny-shaped compromise: **one fact per card**, enough stem to name the book-local referent, citation as the backstop (“Open in book”), not a paragraph of leftover prose on the front.

### Cloze design

- SuperMemo: mask a *keyword*, optionally hint the category in parentheses (`…[year]`). Overlapping clozes for enumerations; never one card with a 15-member set.
- Community consensus ([Neurako cloze notes](https://learn.neurako.com/docs/learning-science/cloze-deletion), [Memrizz cloze tips](https://www.memrizz.com/blogs/cloze-deletion-pro-tips-ankis-most-misused-feature), [MDSteps cloze tuning](https://mdsteps.com/articles/usmle-step-1/fixing-anki-fatigue-for-step-1-caps-leeches-and-cloze-tuning)): one blank per card; blank the discriminative term, not a function word; do not over-delete; do not leave the answer guessable from grammar. **AI generators systematically blank the structurally central word**, which is often the most guessable — exactly Learny’s deterministic adapter (`_longest_word`).
- Learny’s single-mask schema (`____` in the question, span as answer) is the right constraint. The missing piece is *which* span is legal.

### LLM-generated card quality (2023–2026)

- **[Gossmann 2023](https://www.alexejgossmann.com/LLMs-for-spaced-repetition/)** rated 100 LLM cards on truthfulness, self-containment, atomicity, “is this a flashcard,” and “would I add this.” GPT-4 beat local models; **“would I add this” was the only metric that matched author taste**. Grounding ≠ desirability.
- **[Savaal (arXiv:2502.12477)](https://arxiv.org/abs/2502.12477)**, TMLR 2026, [code](https://github.com/mit-nms/savaal): extract/rank concepts → retrieve a passage → generate one question per concept. Beats whole-document prompting on depth-of-understanding (reported 1.5–6.5× vs direct). Rubric: specificity, objectivity, groundedness, quality/usability. Learny already sections the book; it does **not** extract concepts before asking Haiku for 3–6 items.
- **[Memory Machines (Kirkby & Matuschak, 2025–26)](https://memory-machines.com/report)**: ~1,500 highlight-anchored prompts, 93 sources. Tiers: T3 ready / T2 needs polish / T1 looks fine but will rot in review / T0 off-target. **Frontier models still emit unusable (T0–T1) prompts ~26–36% of the time.** Judges catch off-target (T0) well and fail at the T1/T2 boundary — the expensive failure. Grounding the judge on labeled peers raised pluckability precision 56% → 78% but is impractical at request time. **Highlights beat whole-document decks** as a targeting signal (one-size-fits-all decks were ~⅓ unwanted).
- Product prior art: [RemNote AI cards](https://www.remnote.com/feature/ai-flashcards) and [Traverse cloze-from-selection](https://traverse.link/meta-learning/active-recall-and-spaced-repetition) both **preview and edit before schedule**. [AnkiBrain](https://flica.app/article/anki-ai-flashcards) is the same idea inside Anki. OSS generators mostly skip QC entirely (already noted in `docs/research/2026-07-12/active-recall-srs.md`). Learny’s highlight/note suggestion chips already match this pattern; auto-deck generation does not.

### FSRS (scheduler is ahead of the product)

- Learny uses **FSRS-6 via `py-fsrs` (`fsrs>=6,<7`)** with population defaults, `desired_retention=0.9`, learning steps 1m then 10m, fuzzing on ([ADR-0021](../../adr/0021-active-recall-design.md), `backend/app/infrastructure/scheduling/fsrs.py`). Correct choice.
- **FSRS-6 vs FSRS-5** ([Expertium](https://expertium.github.io/Algorithm.html), [awesome-fsrs wiki](https://github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm), [py-fsrs 6.0 notes](https://github.com/open-spaced-repetition/py-fsrs/releases)): 21 vs 19 parameters; trainable forgetting-curve decay `w20`; same-day (short-term) stability `S' = S · exp(w17·(G−3+w18)) · S^(−w19)` when elapsed **< 1 day**. Same-day updates ignore exact elapsed minutes (a known limit; FSRS-7 research). py-fsrs applies this automatically.
- **Desired retention** is the real lever ([fsrs4anki tutorial](https://github.com/open-spaced-repetition/fsrs4anki/blob/main/docs/tutorial.md), [Anki FSRS FAQ](https://faqs.ankiweb.net/frequently-asked-questions-about-fsrs.html)): 80–95% is reasonable; 90% is the default; above ~97% workload explodes. Parameters are preset-specific (language vs geography should not share a fit).
- **Optimizer:** Anki 24.06+ will fit on any history; older lore was 400–1000 reviews. Re-optimize monthly or when review count doubles. Same-day reviews after the first are typically dropped from the fit. Duration is **not** used for intervals; it *is* used for “minimum recommended retention.” Learny already stores `review_duration_ms`. ADR-0021 correctly deferred `fsrs[optimizer]` (torch) until volume justifies it.
- **Again/Hard/Good/Easy vs Pass/Fail:** FSRS is trained on 1–4. FAQ Q2: Again+Good only is fine and can even be *more* accurate. Traverse offers a two-button “simple mode.” Do not collapse the schema; a UI-only “simple” mapping (Fail→1, Pass→3) is optional later.
- **No ease hell under FSRS.** SM-2 ease-floor (130%) is the old trap ([analysis of Anki quit reasons](https://my-senpai.com/insights/why-people-quit-anki.html)). The FSRS analogue of a leech is a card whose **observed recall is worse than predicted** ([forum spec](https://forums.ankiweb.net/t/automated-leech-detection/56887), [LeechKit](https://github.com/rbrownwsws/leechkit)), not a high difficulty number alone. Classic Anki still uses 8 review-mode lapses then tag/suspend ([Anki manual](https://docs.ankiweb.net/leeches.html)). Remedy is always the same: **edit the card**, split it, add a cue, or suspend — never grind.

### Review UX that power users will not forgive the absence of

- Anki reviewer: Space/Enter reveal; 1–4 grade; Space after reveal = Good; **Ctrl+Z undo**; **E edit**; `*` mark; `@` suspend; `-` bury; interval shown on the buttons ([2026 shortcut cheat sheet](https://medankigen.com/blog/anki-keyboard-shortcuts)). Undo is the #1 recovery from a mis-tap of 1 vs 4.
- Session design: new cards should complete their **same-day learning steps** in the session (1m / 10m). A snapshot queue that never re-inserts a card due in sixty seconds silently disables FSRS learning.
- Empty generation must be an **outcome with a cause**, not a spinner that vanishes. RemNote/Traverse/ Learny’s own highlight chips already do this (“No cards for this passage”).

---

## Critique of the current pipeline

Read: `backend/app/application/quiz.py`, `quiz_qc.py`, `infrastructure/quiz/{anthropic,local}.py`, `application/reviews.py`, `infrastructure/scheduling/fsrs.py`, `frontend/app/components/{library-screen,review-screen,use-quiz-deck-polling}.tsx`, `frontend/app/components/notes/card-suggestions.tsx`.

### What already matches the evidence

- **Format.** Free-recall + single-mask cloze, no MCQ, self-graded 1–4 into FSRS-6. This is still the right flagship (ADR-0021; Kang/Roediger vs recognition; ungroundable distractors).
- **Grounding.** Persist only if `anchor_quote` is whitespace/case-normalized in the cited chunk (`quote_in_text`); cloze requires `____` in the question and the mask in the quote (`cloze_is_valid`). Provider is never trusted. Citation snapshot has no chunk FK, so re-ingest cannot destroy history.
- **Dedup.** Embed `question + "\n" + answer`, reject cosine ≥ `LEARNY_QUIZ_DEDUP_THRESHOLD` (0.90) against accepted + persisted items.
- **Sacred progress.** `content_key` upsert updates text only; scheduling and `review_log` are untouchable. Note-card regenerate-and-match is the same invariant.
- **Human QC exists — on the good path.** Highlight and note suggestions are accept / inline-edit / discard, never silent bulk insert. Empty suggestion lists already say “No cards for this passage.”
- **Review basics.** Question-only → Reveal → answer + section breadcrumb + excerpt; “Open in book” is reachable *before* reveal; Space then 1–4; duration timed question→grade; session tally.

### Where quality is lost

1. **The generation prompt is a density instruction, not a formulation instruction.** `_section_prompt` in `anthropic.py` asks Haiku to “Write 3 to 6 items… grounded strictly… `free_recall` or `cloze`.” No minimum-information, no “one concept,” no “do not blank function words,” no “answers shorter than one sentence,” no “no lists,” no “question must be answerable without the book.” Savaal’s lesson is that *what you ask for per call* dominates model IQ.
2. **QC is faithfulness, not usefulness.** `_ground` rejects empty fields, unknown chunk, missing quote, invalid cloze. It accepts “What does the passage in «X» state?” with the whole sentence as answer (the local adapter *always* emits this). It accepts a cloze whose mask is the longest alphanumeric token. It does not reject answer-in-question leaks, yes/no, sets, 200-word answers, or `the`/`of`/`is` clozes. ADR-0021 deferred an LLM critique pass for cost; it also deferred the *cheap* checks.
3. **Auto-deck skips human taste.** `RunDeckGeneration.finalize` upserts every survivor and mints FSRS `initial()` immediately. Memory Machines: even a good model will ship ~⅓ unusable prompts, and T1 cards look fine until week four. Highlight chips already have the UI; deck generation bypasses it.
4. **Concept-blind section dump.** Eligible units are **leaf sections ≥ `quiz_min_section_chars` (200)**. Tiny fixture books therefore produce **zero eligible sections**. That is a documented non-error: `begin_deck` starts a pass over `[]` and `finalize` records success with `generated_count=0`. Combined with the local adapter emitting two near-duplicate items per section (free-recall + cloze of the same sentence), real-provider decks can also collapse under 0.90 cosine — ADR-0021 already notes this for the bag-of-tokens embedder.
5. **Discard reasons are a counter, not a taxonomy.** Jobs store `generated_count` / `discarded_count` / `failed_sections`. The UI never renders those numbers. `QuizDeckControls` shows `{n} items · {due} due` **only when `items.length > 0`**. A succeeded job with zero items is indistinguishable from “I have not generated yet,” except the Generate button remains. The walkthrough’s 0.02s empty success is this path.
6. **No post-mint edit/flag/suspend** on `quiz_items`. Status is `active|stale|orphaned` for corpus drift, not learner judgment. The only schedule mutation besides review is note-card `schedule-reset`. A bad auto-card can only be suffered or ignored by leaving it due.
7. **Review session ignores FSRS short-term memory.** py-fsrs will set `due` to ~1 or ~10 minutes after a Learning-state grade. `ReviewScreen` loads the queue once, advances `index`, and never re-fetches. Intra-session learning steps are dropped until a later page load. Interval/stability returned by `submitReview` is unused. No undo: a mis-hit of Again is a durable `review_log` row and a stability hit.
8. **Global FSRS only.** `LEARNY_FSRS_DESIRED_RETENTION` is process-wide. No per-user (or per-book) parameters. Fine at hobby volume; a public multi-tenant instance with mixed literature vs language decks will want at least a retention dial before an optimizer.

### What the app should say when generation yields few/zero items

Map the already-known job fields onto copy. Do not invent a new job state for “empty” — `succeeded` with counts is honest.

| Condition | How we know | Copy |
| --- | --- | --- |
| No eligible leaf sections | `generated_count=0`, `discarded_count=0`, `failed_sections=0`, items still empty | “This book has no section long enough to quiz yet (need about 200+ characters in a leaf chapter). Read further, or highlight a passage to make a card.” |
| Candidates all failed QC | `discarded_count>0`, `generated_count=0` | “We drafted {discarded} items but none were faithful to the text (quote missing, cloze invalid, or too similar to an existing card). Try a longer chapter, or highlight the sentence you care about.” |
| Provider section failures | `failed_sections>0` with some generated | “Saved {n} cards. {k} sections failed to generate — retry when ready.” |
| Thin but non-zero | `generated_count` in 1..3 on a long book | “Only {n} cards survived quality checks. Highlight key passages for better cards — auto-decks work best after you’ve marked what matters.” |
| True success | `generated_count≥1` | Keep counts; add discarded as a quiet footnote (“{d} drafts dropped as duplicates or ungrounded”). |

Highlight/note paths already have the right empty copy; lift that tone onto the library row.

---

## Automatic card-quality rubric

Enforce **deterministically** in `quiz_qc.py` (same module for every adapter). Log a **reason code** onto the job (JSONB `discard_reasons: {code: n}`) so the UI can speak. Do not persist rejected text.

### Hard gates (reject; cheap)

| Code | Check | Why |
| --- | --- | --- |
| `ungrounded` | Existing quote / chunk / cloze-blank checks | Faithfulness (keep) |
| `duplicate` | Existing embedding + `content_key` | Keep |
| `empty` | Existing non-empty Q/A/quote | Keep |
| `answer_in_question` | For free-recall: normalized answer is a substring of the question | Pattern matching, not retrieval |
| `yes_no` | Question matches `^(is\|are\|do\|does\|did\|can\|was\|were)\b` or ends with a binary choice | Not effortful (Matuschak) |
| `cloze_stopword` | Cloze answer in a small closed list (`the`, `a`, `an`, `of`, `to`, `in`, `and`, `or`, `is`, `was`, `it`, …) or length 1–2 letters | Guessable blank |
| `cloze_too_wide` | Cloze answer > 8 words or ≥ 60% of the question’s words | Minimum information |
| `answer_too_long` | Free-recall answer > 12 words **or** > 120 chars | Dead Sea anti-pattern |
| `question_too_long` | Question > 280 chars (cloze: 400) | Optimize wording |
| `set_dump` | Answer has ≥ 4 comma/`/`/`;`-separated proper items | Avoid sets |
| `generic_stem` | Free-recall question matches “what does (the )?(passage\|section\|note\|text)” | Local-adapter smell; also what a lazy LLM emits |

`quiz_max_card_chars` (2000) is a persistence cap for *user-edited* cards, far too loose as a generator gate.

### Soft gates (keep, but tag `needs_review`)

- Cloze whose blank is reconstructable from remaining syntax (optional later; hard without an LLM).
- Free-recall whose answer is a near-copy of `anchor_quote` (copy-the-sentence). Prefer rewriting the question to ask for the *fact*, not the sentence.
- Pair collision: free-recall and cloze of the same sentence both surviving — keep the better type (prefer cloze for terminology, free-recall for “why”), drop the other even if cosine < 0.90.

### Do not auto-enforce with an LLM judge yet

Memory Machines: models cannot reliably separate T1 from T2, and a second Haiku pass doubles deck cost (exactly why ADR-0021 deferred critique). Revisit only after deterministic gates + preview, with a **golden fixture set of labeled cards** (Learny already evaluates groundedness this way). Savaal-style concept extraction is a prompt/orchestration change, not a judge.

### Human loop (the real T1 filter)

Once a card exists: **edit text in place (content only)**, **flag** (hide from due queue, keep history), **split** later. Flag is the Learny-shaped leech/suspend. Do not auto-suspend on 8 lapses in v1 of this; surface “this card keeps failing — edit or flag?” after 4 Again ratings in review-state.

---

## Review-UX recommendations

Keep the 4-button bar. It is the FSRS training distribution and already keyboarded.

**Must-have for public launch (session correctness + trust)**

1. **Undo last grade** (Ctrl/Cmd+Z). Append-only `review_log` stays; add `undone_at` or write a compensating row and restore the previous `quiz_item_scheduling` snapshot (store `prev_snapshot` on the log row, or keep one extra column). Power-user expectation; mis-taps of 1 vs 4 are common.
2. **Re-queue learning steps in-session.** After a grade, if `due` is within the next N minutes, insert the card back into the local queue (or refetch). Otherwise FSRS’s 1m/10m steps are fiction.
3. **Show the next interval on the buttons** after reveal (`in 10m` / `in 4d`). The API already returns `due`. Anki users grade *with* this information; hiding it makes Hard vs Good random.
4. **Flag / edit from the card.** E to edit question+answer (content upsert, schedule untouched — same invariant as note refresh). Flag removes from due (new status `suspended` or a boolean; do **not** reuse `stale`/`orphaned`).
5. **Empty/thin deck copy** as in the table above. Failed jobs already show `job.error`; succeeded-empty must not be silent.

**Should-have (activation and retention)**

6. **Auto-deck preview**, same chip pattern as highlights: generate into a `pending` status (or a suggestions table), accept/edit/discard before `initial()` scheduling. Memory Machines + RemNote/Traverse. Cost: an extra state; benefit: stops T1 cards from entering FSRS.
7. **Desired retention control** (user setting, 0.80–0.95, default 0.90) passed into `FsrsSchedulingAdapter`. One number, documented as “more reviews ↔ stronger memory.” Not a 21-weight UI.
8. **Leech nudge**, not auto-punish: 4 review-state lapses or Again streak → prompt to edit/flag. Keep grinding optional.
9. **Keyboard parity:** Space = Good *after* reveal (Anki muscle memory); `u` undo; `e` edit; `f` flag. Keep 1–4.
10. **Session cap / new-card cap** later (Anki quit analyses: pile overwhelm). Not blocking for a book-sized first deck if preview exists.

**Do not**

- Replace 1–4 with Pass/Fail as the only mode (optional simple mapping later).
- Auto-grade typed answers (self-grade is accepted in ADR-0021; fuzzy match is a future cloze nicety, not a scheduler input).
- Fit FSRS weights on the first public week (torch extra, noisy small-N fits, hexagonal boundary still required).
- Add MCQ “to make it feel like a quiz app.”

---

## Cycle-sized moves

Each is one spec-driven PR-shaped slice. Ordered by public-launch leverage.

### 1. Empty-deck honesty + discard reason codes

**Why recommend:** The walkthrough already failed this: generation “succeeds” in 0.02s with nothing to review and no copy. The job already has counts; QC already knows why it discarded. Smallest change that makes the product feel finished. Unblocks every later quality iteration because we can *see* filter yield.

**Why not:** Does not improve the cards that *do* persist. Reason-code plumbing can bikeshed (`JSONB` vs extra columns). Do not block on a perfect taxonomy — ship the five codes in the table plus `other`.

### 2. Deterministic formulation gates in `quiz_qc.py` + prompt rewrite

**Why recommend:** SuperMemo/Matuschak/Gossmann/Neurako all agree the cheap failures are structural. Putting rules in QC means both Haiku and the local adapter (and note suggestions) get them. Prompt change is the Savaal lesson without a new pipeline: “one fact; short answer; blank the key term; no lists; no yes/no.” Golden fixtures can pin rejects.

**Why not:** Aggressive gates on short books will drive generated_count toward zero — **which is why move 1 must land first**. Stopword lists are language-English. Do not pretend this catches T1 construction failures; it catches T0 and the Dead Sea dump.

### 3. Review undo + interval on buttons + in-session learning-step requeue

**Why recommend:** Makes FSRS actually behave as documented. Undo is table-stakes vs Anki/RemNote. Intervals teach Hard vs Good. All three are review-path only (no generation cost). `review_log` + scheduling snapshot already exist.

**Why not:** Undo needs a careful invariant (do not delete log rows; compensating event). Re-queue can surprise users if a 1-minute card pops while they thought the session was done — copy should say “1 card still in short-term review.” Fuzzing makes interval labels approximate; show buckets (`~10m`, `~4d`).

### 4. Flag + edit on due cards (content-only upsert)

**Why recommend:** Without this, a bad auto-card is a leech with no escape. Edit-in-review is how Anki decks become good; Memory Machines says forgetting is the feedback that creates taste. Same content/schedule split already proven on note regenerate.

**Why not:** Edit can break grounding (user rewrites away from the quote). Policy: edited text is author-owned (already true for note-card accepts: “not re-gated”). Optional “still in book?” check, not a hard block. Flag-status vs new table is a design fork — prefer a `suspended` status next to `stale`/`orphaned` so the due query stays one predicate.

### 5. Auto-deck as preview, not silent schedule

**Why recommend:** Aligns the bulk path with the highlight path that already works. Directly attacks the Memory Machines finding that whole-document decks mismatch reader interest and that ~⅓ of LLM prompts are unusable. Public users will trust cards they clicked.

**Why not:** Extra state (`pending` vs `active`), extra UI on the library card, and delayed time-to-first-review (activation risk). Mitigate: default-accept is wrong; “Accept all that passed gates” as an explicit second click is right. Skip this if move 2’s yield is already high **and** users can flag (move 4) — but preview is still the quality-first option.

### 6. Highlight-first default; auto-deck as fallback

**Why recommend:** Memory Machines: highlights are a strong targeting signal; one-size decks are not. Learny already has passage → suggest → accept beside the reader. Public onboarding should say “mark a sentence, get a card” before “generate a deck for the whole book.” Matches Traverse/RemNote’s selection-cloze, and Learny’s own citation thesis.

**Why not:** Users who want “quiz me on this book” after upload will find highlight-first slower. Keep Generate as a power action, not the only door. Do not remove auto-deck.

### 7. Per-user desired retention (no optimizer)

**Why recommend:** FAQ: this is the most important FSRS setting. One float on the user (or per-source) passed into `Scheduler(desired_retention=…)`. Honest workload/memory tradeoff for public launch. Existing global setting becomes the default.

**Why not:** Easy to present as a junk slider. Copy must be retention vs minutes/day, not “difficulty.” Changing it should not rewrite past `due` until the next review (Anki’s reschedule-on-change is optional and scary).

### 8. Concept-extract-then-generate (Savaal-lite)

**Why recommend:** Best published antidote to shallow section dumps. Learny’s sections are already the retrieval unit; add a structured “3 concepts” object before items. Fits hexagonal ports (still one `QuizGenerationPort`).

**Why not:** Two LLM calls per section (cost, latency, batch complexity). Haiku-on-Haiku without fixtures will invent concepts. Do this **after** prompt+QC (move 2) has a measured leftover-failure rate. Do not pull LangChain because Savaal’s repo did.

### 9. Per-user FSRS optimizer

**Why recommend:** Real interval accuracy after hundreds of reviews; Anki recommends monthly. `review_log` is already the training set. Hexagonal: persist 21 floats per user (or per source-language later) and construct `Scheduler(parameters=…)`.

**Why not:** `fsrs[optimizer]` pulls torch; ADR-0021 deferred it for that reason. Public week-one users have N≈0. Small-N fits can *worsen* defaults. Revisit when a cohort has ≥ a few hundred reviews and ops can run a beat task. Same-day rows should be excluded from the fit, matching Anki.

### 10. LLM critique / Memory Machines-style judge

**Why recommend:** Only known way to even *attempt* T1 construction. Would complement, not replace, deterministic gates.

**Why not:** Evidence says the T1/T2 boundary does not transfer well; doubles generation tokens; ADR-0021 already recorded this deferral. Build a labeled golden set from *our* books first. Do not gate production decks on an uncalibrated Haiku thumbs-down.

---

## Suggested public-launch slice

Ship **1 → 2 → 3 → 4** as the quality bar people feel on day one (honest empty states, fewer garbage cards, a review session that matches FSRS, an escape hatch for the rest). Treat **5–6** as the attractiveness bar (cards feel chosen, not dumped). Park **7** as a small settings cycle. Park **8–10** until eval fixtures say the cheap gates have plateaued.

The product’s unfair advantage is not “an LLM that writes Anki cards.” It is **cards that open the exact sentence in the book**. Every quality investment should preserve that pin and spend tokens on formulation, not on a second model that still cannot taste T1.
