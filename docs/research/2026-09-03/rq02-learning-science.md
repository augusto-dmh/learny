# RQ02 — Science of learning: what Learny under-exploits

*Evidence archive for the 2026-09-03 public-launch fleet. Distill into an RFC/ADR; do not treat this file as product policy.*

- **Question:** Which evidence-backed learning-science principles is Learny under-exploiting, and what concrete feature would implement each?
- **Learny today (code + 2026-09-03 walkthrough):** structured reading, cited Q&A, a section-scoped Teach chat, FSRS-6 free-recall + cloze cards generated from sections/notes, highlights/notes, a 12-week study heatmap. Review is question → Reveal → Again/Hard/Good/Easy. The due queue is `due ASC, id ASC`, cross-source unless filtered. Teach’s system prompt is a *patient explainer*, not a quizzer. Ask’s empty-state prompts are *summarize / main arguments / explain a concept*. Book figures render as blocked placeholders.

## TL;DR

Learny already ships the two techniques Dunlosky et al. (2013) rated **high utility** — practice testing and distributed practice — via free-recall/cloze cards on FSRS-6. That is the right core. The remaining gap is not “add more SRS.” It is that **encoding and tutoring still invite passive consumption**, while **review under-uses the rest of the high- and moderate-utility toolkit**.

Biggest misses, in order of expected learning impact:

1. **Successive relearning** after a chapter (criterion retrieval, not one-and-done cards dumped into FSRS).
2. **Retrieval-first tutoring** (quiz / hint before explanation) so Teach does not become a crutch — the 2024–2025 AI-tutor evidence says unguarded answer-giving can *harm* later independent performance.
3. **Pretesting** on a section before first read.
4. **Learner-generated questions and why/how explanations** (generation + elaborative interrogation + self-explanation). Ask currently offers *summarization*, which Dunlosky rated **low utility**.
5. **Interleaving and discrimination**, **delayed judgments of learning**, **concrete-example / transfer items**, and **dual coding** (figures + sketch-from-memory).

Highlights and the heatmap are capture/adherence, not study. Highlighting is a low-utility *learning* technique; keep it as a second-brain verb, not as the thing that “counts as studying.”

---

## Principle-by-principle

Utility labels below follow Dunlosky, Rawson, Marsh, Nathan & Willingham (2013), *Psychological Science in the Public Interest*: [doi:10.1177/1529100612453266](https://doi.org/10.1177/1529100612453266). The Learning Scientists’ six-strategy set (spacing, retrieval, elaboration, interleaving, concrete examples, dual coding) is the practitioner overlay: [learningscientists.org/blog/2016/8/18-1](https://www.learningscientists.org/blog/2016/8/18-1).

### 1. Testing effect / retrieval practice — **partially served**

Pulling information from memory beats restudy for long-term retention. Canonical demonstrations: Roediger & Karpicke (2006), *Psychological Science*, [doi:10.1111/j.1467-9280.2006.01693.x](https://doi.org/10.1111/j.1467-9280.2006.01693.x); Karpicke & Roediger (2008), *Science*, [doi:10.1126/science.1152408](https://doi.org/10.1126/science.1152408) (repeated retrieval, not extra study, produced the durable gains). Synthesis: Carpenter, Pan & Butler (2022), *Nature Reviews Psychology*, [doi:10.1038/s44159-022-00089-1](https://doi.org/10.1038/s44159-022-00089-1). Practitioner: [learningscientists.org/blog/2016/6/23-1](https://www.learningscientists.org/blog/2016/6/23-1). Dunlosky utility: **high**.

**Mechanism:** each successful (or effortful-then-feedback) retrieval strengthens the cue→target path and improves later access more than additional encoding. Feedback after the attempt matters; peeking does not count.

**Learny:** Review is a real retrieval event (question hidden, then reveal, then FSRS grade). Pins back to the passage are correct *feedback*, if used after the attempt. Gaps: Teach and Explain *give* the answer; Ask’s default prompts are restudy/summary; there is no closed-book recitation of a just-read section; self-grading after reveal lets a learner skip producing an answer at all.

**Feature:** **Closed-book section recitation.** On finishing a section, hide the text, prompt “reconstruct the argument / list the claims,” then show the section with misses highlighted. Optionally mint cards only from failed retrievals. Same loop can sit in Teach: the tutor *asks first*.

### 2. Spacing effect / spaced repetition — **already served** (with caveats)

Spreading practice over time beats massing for delayed tests. Reviews: Cepeda, Pashler, Vul, Wixted & Rohrer (2006), *Psychological Bulletin*, [doi:10.1037/0033-2909.132.3.354](https://doi.org/10.1037/0033-2909.132.3.354); Cepeda, Vul, Rohrer, Wixted & Pashler (2008), *Psychological Science*, [doi:10.1111/j.1467-9280.2008.02209.x](https://doi.org/10.1111/j.1467-9280.2008.02209.x) (optimal gap scales with the retention interval). Carpenter et al. (2022) above. Practitioner: [learningscientists.org/blog/2016/7/21-1](https://www.learningscientists.org/blog/2016/7/21-1). Dunlosky utility: **high**.

**Mechanism:** some forgetting between sessions makes the next retrieval more potent; expanding or model-based intervals (FSRS’s stability/difficulty) approximate that.

**Learny:** FSRS-6 behind `SchedulingPort` (`desired_retention=0.9`, fuzzing on, default learning steps) is a correct implementation of *card-level* spacing ([ADR-0021](../../adr/0021-active-recall-design.md)). The heatmap is **adherence**, not spacing. Caveats: new cards are due immediately (good for first retrieval, easy to mass 40 new items in one sitting); early review of not-yet-due cards is allowed (cramming); there is no spacing of *re-reading* a chapter.

**Feature (small):** a **new-card budget** (e.g. 10–20/day) plus a “learn this section now” session that *is* massed *on purpose* for the first criterion pass, then hands the survivors to FSRS. Do not add a second scheduler.

### 3. Interleaving — **partially served**

Switching among similar categories/problem types beats blocked practice when the skill is *discriminating* which method or concept applies. Rohrer & Taylor (2007), *Instructional Science*; Rohrer (2012), *Educational Psychology Review*, [doi:10.1007/s10648-012-9202-2](https://doi.org/10.1007/s10648-012-9202-2). Meta-analysis: Brunmair & Richter (2019), *Psychological Bulletin*, [doi:10.1037/bul0000209](https://doi.org/10.1037/bul0000209) — benefits are **moderator-heavy** (strongest for similar visual/categorical material and math; weaker or null when items are unrelated). Practitioner: [learningscientists.org/blog/2016/8/11-1](https://www.learningscientists.org/blog/2016/8/11-1). Dunlosky utility: **moderate**.

**Mechanism:** interleaving forces contrastive processing (“how is this different from the last item?”), which blocked study skips.

**Learny:** the cross-source due queue plus FSRS fuzzing mixes books a little. `due ASC, id ASC` still **blocks** cards that became due together (often the same section). Per-source Review in the dock *reduces* interleaving. No items ask “which of these two nearby claims…”.

**Feature:** shuffle the served queue by `source_id` / `section_path` (not by due time alone); generate **contrast pairs** from adjacent sections (same schema as free-recall: question, answer, verbatim `anchor_quote`).

### 4. Elaborative interrogation — **unserved** (Ask is a near-miss)

Learners ask *why/how* and produce the answer, linking new claims to prior knowledge. McDaniel & Donnelly (1996), *Journal of Educational Psychology*, [doi:10.1037/0022-0663.88.3.508](https://doi.org/10.1037/0022-0663.88.3.508); Dunlosky et al. (2013) rate it **moderate** (works best when the learner has enough background to generate a true explanation). Practitioner: [learningscientists.org/blog/2016/7/7-1](https://www.learningscientists.org/blog/2016/7/7-1).

**Mechanism:** generating a causal/explanatory link creates additional retrieval routes and organizes the knowledge; wrong elaborations need a check against the text.

**Learny:** the Explain verb and Teach *produce the elaboration for the reader*. Suggested Ask prompts never say “why does the author claim…”. Notes *can* be elaborations if the user writes them, but nothing scaffolds how/why.

**Feature:** **Why/how chip on a selection.** Learner types an answer first; then cited Q&A grades it against the passage (same grounding port). Persist good answers as notes (`origin=elaboration`).

### 5. Self-explanation — **partially served**

Explaining *to oneself* how a worked example or sentence follows — during encoding — improves comprehension and transfer. Chi, de Leeuw, Chiu & LaVancher (1994), *Cognitive Science*, [doi:10.1207/s1532690xci1203_1](https://doi.org/10.1207/s1532690xci1203_1). Meta-analysis: Bisra, Liu, Nesbit, Salimi & Winne (2018), *Educational Psychology Review*, [doi:10.1007/s10648-018-9434-x](https://doi.org/10.1007/s10648-018-9434-x) (prompted self-explanation beats unprompted; effect sizes moderate). Dunlosky utility: **moderate**.

**Mechanism:** gap detection — you notice what you cannot yet explain — plus integration of the current sentence with the running mental model.

**Learny:** notes-from-selection are the right *affordance* if the reader writes a paraphrase rather than a highlight dump. Teach inverts the direction (system explains). No in-flow “why does this sentence follow?” pause.

**Feature:** optional **section-end prompt**: “In your own words, why does this section’s conclusion follow?” Compare to a cited model answer; promote the learner’s text to a note + a free-recall card.

### 6. Generation effect — **partially served** (and partly inverted)

Material you *produce* is remembered better than material you only read. Slamecka & Graf (1978), *Journal of Experimental Psychology: Human Learning and Memory*, [doi:10.1037/0278-7393.4.6.592](https://doi.org/10.1037/0278-7393.4.6.592). Meta-analysis: Bertsch, Pesta, Wiscott & McDaniel (2007), *Memory & Cognition*, [doi:10.3758/BF03193441](https://doi.org/10.3758/BF03193441). Closely related to retrieval; generation of *questions* is additional encoding work.

**Mechanism:** production requires semantic processing and creates a distinctive memory trace of “I made this.”

**Learny:** answering a free-recall card *is* generation. **Authoring** the card is not: Haiku writes 3–6 items per section; highlight→suggest-cards is still model-authored. Cloze is a weak generate-the-blank. This is the opposite of “make your own questions,” which the Learning Scientists recommend when no practice test exists.

**Feature:** **You ask first.** On a highlight, require one learner-written question (or “this passage answers: …”) before showing AI suggestions. Keep the learner’s wording if they accept it (`origin=learner`); QC still requires a verbatim `anchor_quote`.

### 7. Desirable difficulties (Bjork) — **partially served**

Conditions that slow or impair *current* performance can improve *later* performance: retrieval vs restudy, spacing vs massing, interleaving vs blocking, reduced feedback, variation. Bjork (1994) in Metcalfe & Shimamura (eds.), *Metacognition*; Bjork & Bjork (2011), [bjorklab.psych.ucla.edu](https://bjorklab.psych.ucla.edu/research/). The retrieval-effort hypothesis: difficult-but-successful retrievals beat easy ones.

**Mechanism:** extra processing recruited to succeed under constraint is what later tests need; fluency during study is a false friend (see JOLs).

**Learny:** rejecting MCQ (ADR-0021) was the right difficulty choice. FSRS + hidden answers are desirable. Ask/Teach/Explain **remove** difficulty. Self-grade Easy-spam collapses it. Bastani, Bastani, Sungu, Ge, Kabakcı & Mariman (2024), *Generative AI can harm learning*, [SSRN 4895486](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4895486) / [doi:10.2139/ssrn.4895486](https://doi.org/10.2139/ssrn.4895486): a GPT-4 tutor raised practice scores while available, but students who had used the **unrestricted** tutor did **worse** than controls once it was taken away (~17% in their high-school math RCT); a **guardrailed** (hints, not answers) tutor avoided that harm.

**Feature:** Teach default = **hint ladder** (Socratic question → cue → cited excerpt → full explanation). One-tap “just explain” remains available but is not the empty-state. Product implication: never let the model be the thing that performs the retrieval.

### 8. Dual coding — **unserved**

Verbal + visual traces beat words alone when the image is meaningful, not decorative. Paivio’s dual-coding theory; instructional tests in Mayer’s multimedia work (e.g. Mayer & Anderson, 1992, *Journal of Educational Psychology*). Learning Scientists strategy #6. Dunlosky’s “imagery for text” was **low** as a *student-invented* keyword image for arbitrary prose — different from *author-provided* diagrams.

**Mechanism:** two codes (and the links between them) give two retrieval routes; sketching from memory is retrieval + dual code.

**Learny:** walkthrough: figures are blocked placeholders. Cards are text-only. No “redraw this diagram” item type.

**Feature:** (a) **render corpus images** (product-quality, also dual-coding). (b) optional review type: show caption, learner sketches or describes the figure, then reveal the plate. Stay inside existing `(question, answer, anchor_quote)` plus an image object key — no new scheduler.

### 9. Concrete examples — **unserved**

Abstract ideas stick when tied to specific examples; multiple examples + contrast beat a single example. Rawson, Thomas & Jacoby (2015), *Educational Psychology Review*, [doi:10.1007/s10648-014-9273-3](https://doi.org/10.1007/s10648-014-9273-3). Practitioner: [learningscientists.org/blog/2016/8/25-1](https://www.learningscientists.org/blog/2016/8/25-1). Related: concreteness fading (start concrete, fade to abstract).

**Mechanism:** examples supply distinctive, imageable cues and support induction of the category; one example is often encoded as a story, not as the concept.

**Learny:** books contain examples; generation does not prefer “give an example / what is this an instance of?” items. No example-sets for interleaving.

**Feature:** extend `QuizGenerationPort` with `item_intent=example|contrast` (still `free_recall` on the wire): “Give one example the author uses for X” / “How does example A differ from B?” Ground in the same verbatim-quote QC.

### 10. Successive relearning — **partially served**

The prescriptive recipe: in an **initial** session, retrieve to a criterion (Rawson & Dunlosky typically **~3 correct recalls**), then **one** successful recall in each later spaced session. Combines testing + spacing; classroom exams rose about a letter grade vs spaced restudy. Rawson & Dunlosky (2011), *JEP: General*, [doi:10.1037/a0023956](https://doi.org/10.1037/a0023956); Rawson, Dunlosky & Sciartelli (2013), *Educational Psychology Review*; Rawson & Dunlosky (2022), *Current Directions*, [doi:10.1177/09637214221100484](https://doi.org/10.1177/09637214221100484). Practitioner: [retrievalpractice.org/strategies/2018/successive-relearning](https://www.retrievalpractice.org/strategies/2018/successive-relearning). When students could drop cards themselves, the exam benefit vanished — **do not let fluency drop items**.

**Mechanism:** criterion retrieval ensures the trace exists; spaced relearning keeps it; “one and done” under-learns.

**Learny:** FSRS *learning steps* (default minutes-scale Again/Good loops) are a weak cousin, then the card graduates to multi-day intervals. There is **no** “3 correct in this sitting” after finishing a chapter. Bulk deck generation can dump a book’s worth of new cards, each due now — the opposite of a criterion session on *today’s* section. Learner-controlled dropping is not a feature (good).

**Feature:** **Learn session** scoped to a section: cycle its new cards until each has *n* Goods this sitting (n=2 or 3), *then* write FSRS review state. Cap new cards introduced per day. Reuse `review_log`; add a `session_kind=learn|review` flag.

### 11. Pretesting effect — **unserved**

Attempting questions **before** studying the answers, even when attempts fail, improves later learning of those items (errorful generation), given subsequent study/feedback. Richland, Kornell & Kao (2009), *JEP: Applied*, [doi:10.1037/a0016496](https://doi.org/10.1037/a0016496). Pan & Sana (2021), *JEP: Applied*, [doi:10.1037/xap0000345](https://doi.org/10.1037/xap0000345): pretesting can match or approach post-testing for the tested content. Related **forward testing effect**: a test on earlier material improves encoding of *what comes next* (Pastötter & Bäuml; Yang, Potts & Shanks, 2018 review).

**Mechanism:** unsuccessful search activates related knowledge and makes the subsequent text more “answer-shaped”; it also allocates attention to the tested ideas.

**Learny:** decks exist after ingest, so the items could be asked *before* first read — they are not. Review is only for `due` items. Opening a chapter has no pretest.

**Feature:** **Before you read** on a never-opened section: 3–5 existing (or just-generated) items, no FSRS penalty for Again, then jump into the chapter with those sentences highlighted. First real FSRS review still follows the learn/review rules above.

### 12. Transfer-appropriate processing — **partially served**

You remember best when the practice operations match the test operations. Morris, Bransford & Franks (1977), *Journal of Verbal Learning and Verbal Behavior*, [doi:10.1016/S0022-5371(77)80016-9](https://doi.org/10.1016/S0022-5371(77)80016-9). Free-recall practice helps free recall; recognition practice helps recognition; explaining practice helps explaining. Carpenter et al. (2022) note retrieval often *does* transfer, but format match still matters for the skill you actually want.

**Mechanism:** memory is not a blob of “strength”; it is compatibility between encoding and later cues.

**Learny:** free-recall/cloze match “can I produce this fact/term?” They do **not** match “can I teach this section?” or “can I apply this idea to a new case?” Teach never becomes the test. No application items.

**Feature:** two TAP variants, still grounded: (1) **teach-back** — learner explains the section in the Teach box *without* seeing the model’s lecture first; (2) **application prompt** — “given this new case (from the next paragraph / a held-out example), which claim applies?” Cite the source claim.

### 13. Metacognition / judgments of learning — **unserved**

Learners’ JOLs are poorly calibrated: rereading and highlighting feel like knowledge; retrieval feels like failure. Koriat (1997), *Psychological Review*, [doi:10.1037/0033-295X.104.3.499](https://doi.org/10.1037/0033-295X.104.3.499). Delayed JOLs (predict after a gap, from the cue only) are more accurate: Rhodes & Tauber (2011) meta-analysis, *Psychological Bulletin*, [doi:10.1037/a0021705](https://doi.org/10.1037/a0021705). Overconfidence causes under-study: Dunlosky & Rawson (2012), *Learning and Instruction*, [doi:10.1016/j.learninstruc.2011.11.002](https://doi.org/10.1016/j.learninstruc.2011.11.002). Kornell & Bjork (2007), *Psychonomic Bulletin & Review*: students mismanage their own schedules.

**Mechanism:** JOLs use fluency cues (ease of reading) unless you force a retrieval-based cue. Delayed, cue-only predictions track actual memory better.

**Learny:** Again/Hard/Good/Easy is a **post-reveal** quality rating for FSRS, not a prediction. The heatmap counts activity, not accuracy. Nothing says “you rated Easy last time and missed it today.” Summarize-prompts *inflate* fluency.

**Feature:** **Predict then reveal.** Before Reveal, a binary or 0–100 “I’ll remember this in a week.” Store beside `review_log`. Periodically show calibration (predicted vs later Again). Do not auto-reschedule from JOLs — FSRS stays the scheduler; this is a metacognitive mirror.

---

## Mapping table

| Principle | Dunlosky utility | Status | Proposed Learny feature (mechanism) |
|---|---|---|---|
| Testing / retrieval | High | Partially served | Closed-book section recitation + tutor-asks-first (effortful retrieval + feedback) |
| Spacing / SRS | High | Already served | Keep FSRS; add new-card cap + learn-session so spacing is not drowned by massed news |
| Interleaving | Moderate | Partially served | Shuffle due queue across sections; contrast-pair items (discrimination) |
| Elaborative interrogation | Moderate | Unserved | Why/how chip: learner answers, then cited check |
| Self-explanation | Moderate | Partially served | Section-end “why does this follow?” in own words |
| Generation effect | *(not in Dunlosky 10)* | Partially served | Learner-authored question before AI card suggestions |
| Desirable difficulties | *(framework)* | Partially served | Hint-ladder Teach; don’t peek-to-Easy |
| Dual coding | *(LS #6; imagery-for-text was Low)* | Unserved | Render figures; sketch/describe-the-plate cards |
| Concrete examples | *(LS #5)* | Unserved | Example/contrast item intents in quiz generation |
| Successive relearning | *(combo of High+High)* | Partially served | Criterion learn session (2–3 Goods) before long-interval FSRS |
| Pretesting | *(related to testing)* | Unserved | 3–5 items before first read of a section; no FSRS hit |
| Transfer-appropriate processing | *(framework)* | Partially served | Teach-back and application items matching the skill wanted |
| Metacognition / JOLs | *(why learners avoid the above)* | Unserved | Delayed, cue-only prediction before Reveal + calibration view |
| Highlighting / rereading / summarization | **Low** | Over-offered as “study” | Keep highlights as capture; rewrite Ask empty-state away from Summarize |

---

## Cycle-sized moves

Ranked by expected learning impact for a public learner using Learny as the study environment (not as an Anki sidecar). Each is one spec-driven cycle. Overlap with RQ03 (tutor pedagogy) and RQ04 (card quality) is flagged, not duplicated as architecture.

### 1. Criterion learn-session after a section (successive relearning)

**Why recommend:** Highest-utility combo in the literature (retrieval × spacing with a **criterion**, not one-and-done). Learny already has items, FSRS, `review_log`, and section anchors — this is a session policy, not a new domain. Directly fixes “Generate quiz deck succeeded in 0.02s with nothing reviewable” *and* “40 new cards due now.” Classroom successive-relearning work is among the few that moved **course exams**, not just lab tests.

**Why not:** Needs a UX for “you are not done with this section”; easy to annoy readers who wanted a book, not a drill. Criterion *n* is a product choice (2 vs 3) with little Learny-specific evidence. Must not reset FSRS on content regen (ADR-0021 invariant). If card quality is garbage, you will criterion-learn junk — pair with RQ04 or keep n small.

### 2. Retrieval-first Teach (hint ladder; answers are the last rung)

**Why recommend:** Teach is the surface most likely to *undo* the testing effect. Bastani et al. (2024) is the load-bearing 2024–2026 result: unguarded generative tutors inflate practice performance and can **impair** independent post-tests; guardrails that withhold the answer protect learning. Matches Bjork: the tutor should supply desirable difficulty, not fluency. Citations stay on every hint (ADR-0003).

**Why not:** Overlaps RQ03; a bad Socratic loop feels worse than a good explainer. Latency/cost: more turns per section. Some readers genuinely want an explanation first (novices with no schema — also a Dunlosky boundary for elaborative interrogation). Keep “just explain” as an explicit opt-out, not the default.

### 3. Pretest on first open of a section

**Why recommend:** Unserved; items often already exist; Richland/Pan evidence is specific and cheap to productize. Also a forward-testing gift for the rest of the chapter. Frames Learny as a *study* app at the exact moment people start reading.

**Why not:** Friction at the worst moment (curiosity to read). Failed pretests feel bad without careful copy (“wrong is the point”). Useless if the deck is empty (tiny fixture books). Do not write FSRS Again on a pretest.

### 4. Rewrite Ask/Explain empty states: retrieve, don’t summarize

**Why recommend:** Dunlosky rated summarization **low** and practice testing **high**. Current `SUGGESTED_PROMPTS` (“Summarize the key ideas…”) and `Explain this passage` train the *wrong* habit on day one. Smallest cycle: change copy + make Explain a two-step (your paraphrase → cited model). High leverage per line of code.

**Why not:** Summaries are what users *ask* chatbots for; changing this fights user expectation. A two-step Explain is slower. Does not by itself schedule anything — impact is encoding quality, not the forgetting curve.

### 5. Learner-authored questions before AI suggestions (generation)

**Why recommend:** Restores the generation effect that bulk Haiku decks invert. One extra field on the already-shipped highlight→card path (RFC-004 capture). QC unchanged. Produces questions in the learner’s cues (TAP).

**Why not:** Many users will type garbage or skip. Cannot be the only card source (coverage). Slightly more AI cost if you still suggest after. Do not drop server-side verbatim grounding.

### 6. Interleaved due-queue + contrast items

**Why recommend:** Free mixing is a one-query change; contrast items attack the actual interleaving mechanism (discrimination), which FSRS fuzzing does not. Cross-source Home review already wants this.

**Why not:** Brunmair & Richter: **not** a universal boost — interleaving unrelated history dates does little. Contrast generation is a new QC failure mode (two quotes, one relation). Per-book dock review should stay blocked-on-purpose for “finish this chapter’s dues.”

### 7. Predict-then-reveal JOLs + calibration

**Why recommend:** Attacks the reason people reread and skip retrieval (fluency). Delayed cue-only JOLs are the calibrated kind (Rhodes & Tauber). Fits the existing Reveal button. Heatmap stays adherence; this is the missing *accuracy* signal.

**Why not:** Extra tap every card will be hated if mandatory. JOLs must **not** drive FSRS (different construct; would poison the scheduler). Calibration UI can feel like a grade. Ship as optional, default on for the first N reviews of a card.

### 8. Example/contrast quiz intents + teach-back TAP

**Why recommend:** Moves practice toward application and induction, which fact cloze will not. Still groundable. Complements interleaving.

**Why not:** Harder generation/QC than term cloze; “example” items go stale if they are too book-specific to transfer. Teach-back grading is subjective (same honesty problem as self-graded recall). Defer auto-grading of teach-back.

### 9. Restore figures + optional plate cards (dual coding)

**Why recommend:** Blocked images are already a product defect; fixing them unlocks Mayer-style multimedia and sketch-from-memory retrieval. Visible “attractiveness” win for public launch.

**Why not:** Dual-coding evidence is weaker and more boundary-conditioned than testing/spacing. EPUB/PDF image pipelines are ingestion work (scope risk vs Docling/ebooklib). Decorative images can hurt (Mayer’s coherence principle). Do not generate unrelated decorative AI art.

---

## Explicit non-recommendations

- **Do not add MCQ as the flagship format.** ADR-0021 still holds: FSRS wants recall ratings; distractors are ungroundable. Recognition ≠ the testing effect you already bought.
- **Do not treat highlighting or the heatmap as learning interventions.** Low-utility techniques plus adherence chrome. Silent grace on the heatmap is already the right register.
- **Do not add a second scheduler** (SM-2 alongside FSRS, or JOL-based intervals).
- **Do not optimize FSRS parameters** until review volume exists (already deferred in ADR-0021).

## Method note

Primary emphasis: Dunlosky et al. (2013); Roediger & Karpicke testing-effect papers; Cepeda spacing reviews; Carpenter, Pan & Butler (2022) spacing/retrieval review; Bjork desirable difficulties; Rawson & Dunlosky successive relearning; Richland/Pan pretesting; Bisra et al. self-explanation meta; Brunmair & Richter interleaving meta; Rhodes & Tauber delayed JOLs; Bastani et al. (2024) on unguarded AI tutors. Learning Scientists posts used as the practitioner mapping, not as primary evidence. Some publisher PDFs (Sage, Nature, Wharton) were blocked or timed out from this environment; DOI links above are the canonical records.
