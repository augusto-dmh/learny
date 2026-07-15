# Learny v2 research — followup-quiz-item-format

Generated 2026-07-12 by a web-research agent (v2 planning research fleet). Sources/dates inline; verify load-bearing claims before implementation.

---

# Quiz item format: free-recall/cloze WITHOUT distractors — resolve the schema conflict in favor of active-recall-srs

**Verdict: the flagship format is free-recall + cloze with no distractors. The MCQ schema (`options` / `correct_index` / distractors) in anthropic-generation should be dropped from v2, and the duplicate-option/distractor-sanity checks in evaluation deleted with it (replaced by answer-groundedness checks). MCQ is a legitimate but deferred "quiz mode" variant, not the flagship.**

## Why (evidence, most decisive first)

**1. SRS-fit is the deciding factor, and it's one-sided.** Learny's flagship is quiz generation *plus spaced repetition*. FSRS — Anki's default scheduler since 23.10 (Oct 2023), trained on ~700M real reviews — models memory from self-graded free-recall reviews with the Again/Hard/Good/Easy signal ([Anki FAQ](https://faqs.ankiweb.net/what-spaced-repetition-algorithm), [fsrs4anki tutorial](https://github.com/open-spaced-repetition/fsrs4anki/blob/main/docs/tutorial.md), [Expertium's technical explanation](https://expertium.github.io/Algorithm.html), all current as of 2026-07). MCQ yields only binary correct/incorrect on a *recognition* task, which (a) collapses the 4-grade input FSRS expects and (b) inflates apparent recall relative to the recall-based data FSRS parameters are fit on. If you adopt FSRS (the obvious choice — MIT-licensed [py-fsrs](https://github.com/open-spaced-repetition/py-fsrs) exists for Python), free-recall/cloze with an Anki-style reveal-then-self-grade loop is the format the algorithm is built for.

**2. Learning science favors recall over recognition when feedback is given — and Learny always gives feedback.** Kang, McDermott & Roediger (2007, *Eur. J. Cognitive Psychology* 19:528–558) found that with corrective feedback, short-answer initial testing produced better long-term retention than MCQ; MCQ only won when no feedback was given ([paper summary](https://notes.andymatuschak.org/zTxLkeaWCdBHQYW73o5n6Ka), [full ref](https://www.scirp.org/reference/referencespapers?referenceid=1436705)). Learny's reveal step *is* feedback — a citation-grounded answer with the source passage — so the free-recall advantage applies directly. The greater retrieval effort also drives deeper encoding of that feedback.

**3. MCQ carries an active harm: the negative suggestion effect.** Roediger & Marsh (2005, *JEP:LMC*) showed students acquire false knowledge from plausible MCQ lures — they later reproduce distractors as facts ([PDF](http://psychnet.wustl.edu/memory/wp-content/uploads/2018/04/Roediger-Marsh-2005_JEPLMC.pdf); see also [Butler & Roediger 2008](https://pubmed.ncbi.nlm.nih.gov/18491500/), which shows feedback reduces but must be relied on to offset it). For a *learning* product (vs. an assessment product), shipping LLM-invented plausible falsehoods next to every true fact is a bad trade.

**4. Distractors are the hard, failure-prone part of LLM generation — and the part that can't be citation-grounded.** 2024–2026 literature consistently identifies distractor quality as the open problem in LLM MCQ generation: hallucinated facts, superficial or accidentally-correct distractors, no reliable automated quality metric ([Docimological quality analysis, *SN Computer Science* 2024](https://link.springer.com/article/10.1007/s42979-024-02963-6); [overgenerate-and-rank, 2024](https://arxiv.org/pdf/2405.05144); [difficulty-controlled distractor generation, Springer 2025](https://link.springer.com/chapter/10.1007/978-3-031-99261-2_14)). That is exactly why the evaluation research needed duplicate-option and distractor-sanity checks. Note the structural conflict with Learny's core principle: question and answer can each be grounded in a cited passage, but a good distractor is *by definition not supported by the text* — it is ungroundable. Dropping distractors deletes an entire failure class and its eval surface.

**5. It matches the entire mature SRS ecosystem and its formulation canon.** Wozniak's 20 rules — the canonical SRS knowledge-formulation guide since 1999 — center on the minimum information principle and call cloze deletion "easy and effective" with "great mnemonic power" ([supermemo.com](https://www.supermemo.com/en/blog/twenty-rules-of-formulating-knowledge)). Anki, SuperMemo, Mochi, RemNote all ship front/back + cloze as primary formats; none flagship MCQ.

## Concrete schema resolution

Replace the anthropic-generation request schema's MCQ shape with two item types:

- `free_recall`: `{question, expected_answer, citations: [chunk anchors]}` — grading: reveal expected_answer + cited passage, user self-rates Again/Hard/Good/Easy → FSRS.
- `cloze`: `{text_with_masks (e.g. {{c1::…}} on a near-verbatim passage sentence), citations}` — masked spans are literally in the source text, so groundedness is checkable by string containment; optionally auto-check typed answers with fuzzy match.

Evaluation checks to keep/replace: drop duplicate-option and distractor-sanity; add (a) expected_answer groundedness against the cited chunk, (b) cloze mask validity (masked span appears in cited passage), (c) citation-anchor resolvability — all deterministic, fitting the golden-fixture eval approach.

## Caveat (flagged)

Well-built MCQ isn't worthless: Little & Bjork showed competitive-distractor MCQs can strengthen retention of related (untested) alternatives ([Marsh, Roediger, Bjork & Bjork 2007, *PBR*](https://bjorklab.psych.ucla.edu/wp-content/uploads/sites/13/2016/07/Marsh_Roediger_BjorkBjork2007PBR.pdf)), and MCQ auto-grades without trust in self-assessment. So MCQ is defensible as a *future* exam-prep mode with mandatory immediate feedback — but it multiplies generation/eval complexity for a worse SRS signal. Defer it; do not carry `options`/`correct_index` into the v2 flagship schema.

Sources: [Kang et al. 2007 (Matuschak notes)](https://notes.andymatuschak.org/zTxLkeaWCdBHQYW73o5n6Ka) · [Roediger & Marsh 2005 PDF](http://psychnet.wustl.edu/memory/wp-content/uploads/2018/04/Roediger-Marsh-2005_JEPLMC.pdf) · [Butler & Roediger 2008](https://pubmed.ncbi.nlm.nih.gov/18491500/) · [Anki FSRS FAQ](https://faqs.ankiweb.net/what-spaced-repetition-algorithm) · [fsrs4anki](https://github.com/open-spaced-repetition/fsrs4anki) · [SuperMemo 20 rules](https://www.supermemo.com/en/blog/twenty-rules-of-formulating-knowledge) · [LLM MCQ quality analysis 2024](https://link.springer.com/article/10.1007/s42979-024-02963-6) · [Distractor generation 2025](https://link.springer.com/chapter/10.1007/978-3-031-99261-2_14)
