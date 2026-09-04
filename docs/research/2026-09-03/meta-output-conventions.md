---
id: meta-output-conventions
title: Recommended structure for deep/agentic research report output
question: According to official vendor docs (Anthropic, OpenAI, xAI, Google) and adjacent primary sources, how should this fleet structure research reports so they are trustworthy, verifiable, and reusable?
date: 2026-09-03
sources_accessed: 2026-09-03
status: complete
overall_confidence: high
primary_sources_count: 18
---

# Meta — output conventions for agentic research reports

**Question:** What do official 2025–2026 docs from Anthropic, OpenAI, xAI, and Google (plus PRISMA, Diátaxis, and ADR literature) actually prescribe for the *output* of deep/agentic research — and how should Learny’s house style change?

**House samples audited:** [`docs/research/2026-07-12/README.md`](../2026-07-12/README.md) + [`evaluation.md`](../2026-07-12/evaluation.md) + [`comparable-projects.md`](../2026-07-12/comparable-projects.md); [`docs/research/2026-07-18/synthesis.md`](../2026-07-18/synthesis.md) + [`rq01-competitive-landscape.md`](../2026-07-18/rq01-competitive-landscape.md) + [`rq02-highlight-anchoring.md`](../2026-07-18/rq02-highlight-anchoring.md). Live 2026-09-03 RQs already using the inherited TL;DR → evidence → product implications → cycle-sized moves shape were used as a check, not as authority.

---

## TL;DR

Vendors do **not** publish one shared markdown outline. They do converge on a small set of *mechanisms* that make a research artifact trustworthy:

1. **Front-load a structured summary** (Gemini’s example starts with “Executive Summary”; OpenAI ChatGPT Deep Research opens a navigable report; PRISMA requires a 12-item structured abstract). A TL;DR that restates findings *and* flags limits is the right analog — not a slogan.
2. **Bind claims to sources inline**, with a clickable URL (and, when possible, a span). A bibliography at the end is *not* a substitute. Anthropic, OpenAI, xAI, and Gemini all treat inline, position-addressable citations as the trust primitive. Anthropic even runs a **separate Citation Agent** so synthesis cannot skip attribution.
3. **Separate facts from advice.** Nygard ADRs put value-neutral Context before Decision. PRISMA splits results from interpretation. Diátaxis forbids mixing explanation with how-to. The house “why-recommend / why-not” block is the right *decision* genre — it must not leak into the evidence body.
4. **Show method, limits, and freshness.** PRISMA abstracts require eligibility, information sources **plus last-search date**, synthesis method, and limitations. Gemini tells you to prompt for unknowns (“say unavailable, don’t estimate”). OpenAI’s Model Spec requires hedging when uncertainty would change a reader’s action — and OpenAI *admits* Deep Research is weak at confidence calibration, so ordinal labels tied to evidence quality beat fake percentages.
5. **Prefer primary sources; keep a consulted-vs-cited trail.** Anthropic’s research eval rubric scores source quality (primary over SEO farms). OpenAI’s rewriter prompt says “prioritize reliable primary sources.” xAI returns *all* URLs encountered, not only those inlined — transparency about what was looked at and discarded.
6. **Make the artifact reusable by machines and later cycles:** consistent headings, a date stamp, and enough front matter that a synthesizer can parse question / confidence / status without rereading the essay. Gemini: “define the desired output format explicitly.” Anthropic: every subagent gets an expected output format.

**Verdict on the house convention:** keep the four-part *shape* (summary → evidence → product implications with why-recommend/why-not → cycle-sized moves). It already matches vendor front-loading and Diátaxis’s “don’t mix genres.” **Add** YAML front matter, a Method + Limitations pair, per-claim inline links, ordinal confidence, a consulted-vs-cited source list, and a hard split between Findings and Implications. **Drop** endnote-only sourcing, unbounded 12-item “cycle” laundry lists, and treating “unverified” as a dump at the bottom instead of labeling the claim in place.

---

## Method

Searched and fetched (2026-09-03) official engineering blogs, API docs, product help, and published cookbooks from Anthropic, OpenAI, xAI, and Google; then PRISMA 2020 abstracts, Diátaxis explanation, and Nygard ADR. Secondary blogs were used only as pointers; claims below are tied to primary URLs.

**Eligibility:** vendor-owned pages, official cookbooks/prompts, Model Spec, PRISMA statement, Diátaxis, Nygard 2011. **Excluded as authority:** unofficial “how to prompt Gemini” SEO posts, LangChain deep-agent docs (cited once as an *echo*, not a source of truth).

**Not found:** an Anthropic page literally titled “writing for verification.” Closest official artifacts are the Citations API (“track and verify the sources”), the cookbook Citation Agent, and Claude Code’s “Give Claude a way to verify its work.” That naming gap is recorded under Limitations.

---

## What official guidance converges on

| Element | Convergence | House today |
|---|---|---|
| Executive / structured summary | Gemini example #1 is Executive Summary; OpenAI ChatGPT DR is a navigable long-form report; PRISMA 12-item abstract | **Keep** TL;DR; tighten it to question + findings + limits + implication (not a feature list) |
| Claim ↔ citation binding | Inline + span/URL everywhere (Anthropic claim-blocks, OpenAI/xAI `start_index`/`end_index`, Gemini `groundingSupports`, NotebookLM click-to-passage) | **Add** inline link on every nontrivial claim; keep a Sources list as *index*, not as the only trail |
| Confidence / uncertainty | Hedge when it would change action (OpenAI Model Spec); say “unavailable” rather than invent (Gemini); don’t fake numeric calibration (OpenAI + BrowseComp calibration error) | **Add** ordinal High/Medium/Low on recommendations; keep in-place `(unverified)` |
| Findings vs recommendations | ADR Context ≠ Decision; PRISMA results ≠ interpretation; Diátaxis explanation ≠ how-to | **Keep** why-recommend/why-not; **move** them out of the evidence body into Implications |
| Methodology + limitations | PRISMA items 3–6 and 9; Gemini “prompt for unknowns”; OpenAI DR shows activity history | **Add** Method + Limitations as named sections |
| Source-quality tiers | Anthropic eval: primary > secondary; OpenAI rewriter: official/primary; humans caught content-farm bias | **Add** a one-line source-quality note per key claim cluster |
| Freshness | PRISMA “date last searched”; Anthropic lead prompt injects current date; Model Spec treats stale knowledge as a hedge trigger | **Keep** research date + access dates; **add** “as of YYYY-MM-DD” on time-sensitive facts |
| Machine-readability | Explicit output format (Gemini, Anthropic subagent briefs); API annotations are structured JSON | **Add** YAML front matter + frozen heading names |
| Length discipline | OpenAI: thorough *and* efficient; Anthropic: stop at diminishing returns; Nygard ADRs are short — *decisions*, not evidence | **Keep** long evidence files; **cap** TL;DR (~200 words) and cycle list (≤7) |
| Process transparency | OpenAI “sources used” + activity history; xAI consulted-URL list vs inline cites | **Add** consulted-not-cited when a source was read and rejected |

---

## Per-vendor findings

### Anthropic

**Multi-agent research (product engineering).** [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) (Hadfield et al., published 2025-06-13). Output-relevant facts:

- After the lead synthesizes, findings are passed to a **Citation Agent** that “processes the documents and research report to identify specific locations for citations” so “all claims are properly attributed.” Attribution is a *separate pass*, not a hope of the writer.
- Subagents must receive **an objective, an output format, tools/sources, and task boundaries**. Vague briefs caused duplicate or gap-ridden work.
- Eval rubric for free-form research (LLM-as-judge): **factual accuracy** (claims match sources), **citation accuracy** (cited sources match claims), **completeness**, **source quality** (primary over lower-quality secondary), **tool efficiency**. Single judge, 0.0–1.0 + pass/fail, aligned better with humans than a panel of judges.
- Human testers caught a bias toward SEO content farms over academic PDFs / authoritative-but-low-ranked sources; they added **source-quality heuristics** to prompts.
- Appendix: persist subagent artifacts on a filesystem and pass *references* to the lead (“minimize the game of telephone”). For this fleet: the markdown file *is* the artifact; the synthesis must not paraphrase away citations.

**Citations API.** [Citations](https://platform.claude.com/docs/en/build-with-claude/citations). Designed so users can “track and verify the sources behind each response.” Responses split into **text blocks, each a claim plus a list of citations**. Locations are type-specific (`char_location`, `page_location`, `content_block_location`). `cited_text` is extracted from the document (valid pointer, not a model-invented quote). Prompt-based citing is explicitly weaker on recall/precision. Citations and JSON structured outputs are **incompatible** (interleaved citation blocks vs a schema) — relevant if a later cycle wants machine-parsed RQ JSON; markdown with inline links is the portable compromise.

**Cookbook Citation Agent.** [`citations_agent.md`](https://github.com/anthropics/anthropic-cookbook/blob/main/patterns/agents/prompts/citations_agent.md) (raw prompt). Rules that transfer to human-readable markdown:

- Only cite where the source **directly supports** the claim.
- Cite **meaningful semantic units** (complete thoughts); prefer end-of-sentence; don’t fragment on every word.
- Don’t stack redundant citations to the same source in one sentence.
- The synthesizer must **not rewrite** the report while citing (identity check). For us: don’t “clean up” a finding while attaching a URL.

**Cookbook lead agent.** [`research_lead_agent.md`](https://github.com/anthropics/anthropic-cookbook/blob/main/patterns/agents/prompts/research_lead_agent.md). The lead — not a subagent — writes the final report. Current date is injected. Subagent briefs must define high-quality vs unreliable sources. Stop when further research has diminishing returns. (The prompt references `<writing_guidelines>` that are **not in the published file**; do not invent them.)

**Verification (closest to “writing for verification”).** No titled Anthropic essay by that name was found. Official nearby guidance:

- Claude Code: [Best practices — Give Claude a way to verify its work](https://code.claude.com/docs/en/best-practices) — show evidence (command output, tests), don’t assert success.
- [Building verification loops in Claude Code with skills](https://claude.com/blog/building-verification-loops-in-claude-code-with-skills) — a check that can pass/fail.
- For *research* output, the analog is: a reader (or critic agent) can follow each load-bearing sentence to a URL without trusting the narrator.

**Implication:** a Learny RQ report should be written so a Citation Agent *could* run: claims stable, citations at sentence grain, primary sources preferred, quality of sources scored not just counted.

### OpenAI

**Deep Research, ChatGPT.** [Introducing deep research](https://openai.com/index/introducing-deep-research/) (2025-02). “Every output is fully documented, with **clear citations and a summary of its thinking**, making it easy to reference and verify.” Documented limitations (do not copy as features; treat as risks to design against): hallucination/incorrect inference (lower than chat, not zero); **weak distinction of authoritative sources vs rumors**; **weak confidence calibration** (“often failing to convey uncertainty accurately”); formatting errors in reports/citations at launch.

[Deep research in ChatGPT (Help Center)](https://help.openai.com/en/articles/10500283-deep-research): completed research opens fullscreen with a **table of contents**, a **sources used** section, and **activity history**. Export to Markdown / Word / PDF. That is the product’s answer to reusability: navigable structure + source list + process trail.

**Deep Research, API.** [Deep research \| OpenAI API](https://developers.openai.com/api/docs/guides/deep-research) (fetched 2026-09-03). Canonical prompting pattern:

- Specific figures, trends, statistics — “avoid generalities.”
- **Prioritize reliable, up-to-date sources** (peer-reviewed, WHO/CDC, regulators, earnings).
- **Include inline citations and return all source metadata.**
- Final `message` carries `annotations`: `{url, title, start_index, end_index}` over the report text. “When displaying web results … **inline citations should be made clearly visible and clickable**.”

Prompt-rewriter instructions in the same guide: maximize specificity; **describe expected output format including report headers**; request tables when they clarify comparisons; **prioritize reliable primary sources** (official sites, original papers).

**Cookbook.** [Introduction to deep research in the OpenAI API](https://developers.openai.com/cookbook/examples/deep_research_api/introduction_to_deep_research_api) (Glory Jain & Kevin Alwell; page currently archived, dated 2025-06-25). Same annotation model; explicit purpose: “build a citation list or bibliography, add clickable hyperlinks, and **highlight & trace data-backed claims**.”

**Model Spec (2025-04-11).** [model-spec.openai.com/2025-04-11.html](https://model-spec.openai.com/2025-04-11.html).

- **Express uncertainty** when doing so would (or should) change the user’s behavior; rank of outcomes: confident-right > hedged-right > no answer > hedged-wrong > **confident-wrong (worst)**. Default to conversational hedges (“as of …”, “if sources are current”), **not** invented percentages unless asked.
- Types of uncertainty include **outdated information**.
- On contested topics: describe significant views, **allocate attention to evidential support**, cite when appropriate.
- **Be thorough but efficient, while respecting length limits** — no uninformative padding; produce a usable artifact; adapt length to the ask.
- Avoid *excessive* hedging and AI disclaimers (they waste the reader).

**Evals of deep research (not report-rubrics).** [BrowseComp](https://openai.com/index/browsecomp) measures whether an agent finds a short, stable fact — not whether a long report is well structured. Published numbers: Deep Research ~51.5% accuracy with **high calibration error** (~91% in the paper table) — browsing can make models *more* confidently wrong. So “the model sounded sure” is not a quality bar. Anthropic’s five-axis *report* rubric is the better checklist for this fleet; BrowseComp is a reminder to **cite and hedge**, not to optimize vibes.

**Implication:** inline, clickable, span-addressable citations; specified headings; primary sources; hedge time-sensitive and thin evidence; don’t bolt a fake “87% confidence” onto a recommendation.

### xAI / Grok

xAI does **not** publish a “DeepSearch report template” comparable to Gemini’s Executive Summary example. DeepSearch / DeeperSearch are product-mode names for iterative search; the **developer contract** is the Agent Tools API.

**Citations.** [docs.x.ai — Citations](https://docs.x.ai/developers/tools/citations):

- **All citations:** `response.citations` is always a list of URLs the agent *encountered*. “Not every URL … will necessarily be directly referenced in the final answer.” Consulted ≠ cited. Keep both.
- **Inline citations:** markdown `[[N]](url)` at the point of use, plus `annotations` with `url`, `start_index`, `end_index`, `title` (the visible number). Numbers start at 1 and **reuse** when the same URL is cited again.
- Enabling inline citations **does not guarantee** a cite on every answer — the model decides. For this fleet, that is not acceptable: the *house rule* must be stricter than Grok’s default.

**Web search / tools overview.** [Web Search](https://docs.x.ai/developers/tools/web-search), [Tools overview](https://docs.x.ai/developers/tools/overview): final response “with citations where applicable.” Collections search uses `collections://…` URIs so internal vs web sources stay distinguishable ([Collections Search](https://docs.x.ai/developers/tools/collections-search)).

**Implication:** two-layer source trail (consulted list + inline cites); stable numbering; do not treat “we searched” as “we proved.”

### Google (Gemini Deep Research + NotebookLM / Gemini Notebook)

**Deep Research Agent (API, preview).** [Gemini Deep Research Agent](https://ai.google.dev/gemini-api/docs/deep-research) (agent ids `deep-research-preview-04-2026` / `deep-research-max-preview-04-2026`, fetched 2026-09-03). Output-relevant:

- Reports are **cited**; you are told to **review `citations` to verify sources** (web can be malicious).
- **Steerability:** “Define the desired output format explicitly.” Their example technical report is exactly: **1. Executive Summary 2. Key Players (with a comparison table) 3. Supply Chain Risks.** Structure is prompt-defined, not a hidden schema. (Structured JSON output is **not** supported on this agent.)
- **Collaborative planning:** the agent can return a research *plan* for approval before running — process transparency as a first-class product step.
- Best practice: **“Prompt for unknowns”** — “If specific figures for 2025 are not available, explicitly state they are projections or unavailable rather than estimating.”
- Enterprise twin: [Use the Gemini Deep Research Agent](https://docs.cloud.google.com/gemini-enterprise-agent-platform/agents/use-deep-research) — same formatting example, **inline citations**, “always verify the citations … sources are reputable.”

**Grounding (search).** [Grounding with Google Search](https://ai.google.dev/gemini-api/docs/interactions/google-search): `url_citation` annotations and/or `groundingSupports` mapping a **text segment** (`startIndex`/`endIndex`) onto `groundingChunks`. Same claim-to-span idea as OpenAI/xAI/Anthropic.

**NotebookLM / Gemini Notebook.** Official help [Use chat in Gemini Notebook](https://support.google.com/gemininotebook/answer/16179559) (product renamed July 2026 per [notebooklm.google](https://notebooklm.google/)): answers are **restricted to uploaded sources**; citations use **direct quotes**; hover shows the quote; click **navigates to the location**. If the answer isn’t in the sources, the product is documented to refuse rather than fill from parametric memory. That is the gold-standard *user* verification UX — for markdown, the analog is: quote or tightly paraphrase + link, and **say so when the corpus is silent**.

**Implication:** freeze our headings in the prompt/template (Gemini’s lesson); start with an executive summary; never invent missing figures; citations must be jumpable (URL at minimum; quote when the claim is load-bearing).

---

## Adjacent frameworks (not vendors, still primary)

### PRISMA 2020 structured abstracts

[PRISMA 2020 for Abstracts](https://www.prisma-statement.org/abstracts); 12 items listed in the [explanation & elaboration](https://www.bmj.com/content/372/bmj.n160) (Page et al., *BMJ* 2021). Mapped to a product-research TL;DR:

| PRISMA abstract item | Fleet analog |
|---|---|
| 1 Identify the report type | `id` / H1 (`RQ05 — …`, not a blog title) |
| 2 Objective / question | YAML `question` + first TL;DR sentence |
| 3 Eligibility | Method: what counted as a source |
| 4 Information sources + **date last searched** | Method + `sources_accessed` |
| 5 Risk of bias | Source-quality / `(unverified)` |
| 6 Synthesis methods | “Compared in a table; narrative synthesis; no meta-analysis” |
| 7–8 Included evidence + main results | TL;DR findings (no orphan claims) |
| 9 **Limitations of the evidence** | Named Limitations section *and* a TL;DR clause |
| 10 Interpretation / implications | Implications — not mixed into results |
| 11–12 Funding / registration | N/A or “unfunded in-repo research”; skip empty ceremony |

We are not writing systematic reviews. We **are** writing documents other agents will treat as evidence. The abstract checklist is the right *compression* standard: a reader who only sees the TL;DR must not be misled.

### Diátaxis (explanation vs how-to)

[Explanation](https://www.diataxis.fr/explanation/) (official). Explanation is understanding-oriented: context, why, alternatives, even opinion. **It must not absorb instructions.** How-to is a different genre.

House “cycle-sized moves” are how-to. House evidence sections are explanation (plus reference tables). **Separating them is already Diátaxis-correct.** The failure mode Diátaxis warns about is exactly “actionable conclusions” that bury the evidence, or evidence sections that quietly become a backlog. Keep both sections; do not merge them.

### Architecture Decision Records

Nygard, [Documenting Architecture Decisions](https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions) (2011): **Context** (value-neutral forces), **Decision** (“We will …”), **Consequences** (positive, negative, and neutral), **Status**. Fowler’s later note: record **confidence** and what would trigger revisit ([bliki](https://martinfowler.com/bliki/ArchitectureDecisionRecord.html)).

Research reports are **not** ADRs. They are the evidence base that *feeds* ADRs/RFCs (already the Learny rule). Therefore:

- Findings ≈ Context (facts, tensions, citations).
- Implications + why-recommend/why-not ≈ considered options.
- Cycle-sized moves ≈ candidate Decision text — still **proposed**, status lives in the RFC.
- Do not pretend an RQ “Recommendation: Yes” is an accepted ADR.

### Eval rubrics for *report* quality

Use Anthropic’s five axes (above) as the critic’s scorecard. OpenAI BrowseComp / HLE / GAIA measure agent *task* success, not prose quality. If the gap-critique agent needs a rubric, copy Anthropic’s, plus PRISMA’s “limitations present?” and Diátaxis’s “findings/implications/moves not collapsed?”

---

## Audit of the house convention

Inherited shape (kappy/tally → Learny 2026-07-12/18, still used in 2026-09-03 RQs): **TL;DR → evidence with URLs → “what this means for the product” with why-recommend/why-not → cycle-sized moves.**

### Keep

| Practice | Why it already matches vendors |
|---|---|
| Summary first | Gemini exec-summary example; OpenAI “usable artifact”; PRISMA abstract |
| Evidence body with live URLs and **access dates** | Freshness + verifiability; 2026-07-18 rq01/rq02 do this well |
| Comparison / options tables | OpenAI rewriter: request tables for comparisons; Nygard “forces in tension” |
| **Why-recommend / why-not** on decisions | Diátaxis “weigh alternatives”; ADR Consequences including negatives |
| Cycle-sized moves as a **separate** list | Diátaxis how-to extract; Anthropic “scale effort”; Learny spec-driven cycles |
| In-place `(unverified)` and **Open issues** | Gemini “say unavailable”; Model Spec hedge; 2026-07-18 rq01 verification corrections |
| Distill into ADR/RFC; keep the folder as evidence | Nygard: one decision per ADR; research is not the decision log |
| Adversarial verification appendix when a critic refutes a claim | Anthropic citation-accuracy axis; write-for-verification in practice |

2026-07-18 `rq01` is the strongest house sample: Method, per-entity findings with URLs, matrix, then a labeled Recommendation table with why-recommend/why-not, then Open issues + verification corrections. 2026-07-18 `synthesis.md` correctly treats reports as inputs to cycle impact, not as the RFC itself.

### Add

| Gap | Official warrant |
|---|---|
| YAML front matter (`question`, `date`, `sources_accessed`, `status`, `overall_confidence`) | Gemini “define format”; synthesizers need parseable metadata; PRISMA items 2 and 4 |
| Named **Method** (eligibility, where you looked, last-search date) | PRISMA 3–6; Anthropic source-quality heuristics |
| Named **Findings** that contain **no** “ship X” sentences | Nygard Context; PRISMA results vs interpretation |
| Named **Limitations and uncertainty** | PRISMA 9; OpenAI DR known calibration failure; Gemini unknowns |
| **Inline** markdown link on every nontrivial claim (not only a closing Sources list) | Anthropic Citation Agent + Citations API; OpenAI/xAI/Gemini span annotations; NotebookLM click-to-quote |
| Ordinal **confidence** on each recommendation (High/Medium/Low) with a one-line why | Model Spec (influence user action); Fowler ADR confidence; **no** fake percentages |
| **Consulted but not cited** (short) when a source was read and rejected | xAI `citations` vs inline |
| “**As of YYYY-MM-DD**” on prices, version numbers, competitive claims | Model Spec outdated-info; PRISMA last-searched |
| TL;DR length cap (~150–250 words) that includes **limits**, not only wins | PRISMA abstract; OpenAI length discipline |
| Cycle list **cap (≤7)** plus an explicit do-not-build | Anthropic diminishing-returns; OpenAI efficiency; 2026-09-03 rq01’s 12-item list is a backlog, not a cycle |

### Drop (or demote)

| Practice | Why |
|---|---|
| Sources-only-at-the-end (2026-07-18 `rq02` §6 without matching inline density) | Vendors treat inline as the trust primitive; the list is an index |
| “Actionable conclusions first” that *are* the recommendations, with the body as after-the-fact justification (2026-07-12 `evaluation.md`, `embeddings.md`) | Collapses PRISMA results/interpretation and makes the critic unable to audit facts vs advice |
| Unlabeled absence-inferences (“no product documents X, therefore X does not exist”) | 2026-07-18 rq01 already got burned (NotebookLM notes/export). Gemini: say unavailable; don’t estimate |
| Cycle-sized moves mixed into the TL;DR as a 10-line dump | TL;DR should answer the *question*; the backlog belongs in its section |
| Why-recommend/why-not on every bullet in the evidence body | Ceremony; reserve it for Implications |
| Inventing a house “confidence: 82%” | OpenAI Model Spec + BrowseComp: models (and authors) miscalibrate; use ordinal + evidence note |

2026-07-12 `README.md` is a **fleet index**, not a report — keep that genre (table of RQ → question). Don’t force TL;DR onto indexes.

---

## Recommended report template

Normalize each `rqNN-*.md` (and the gap critique / synthesis, with the notes below) to this skeleton. One-line instructions are normative.

```markdown
---
id: rqNN                     # stable slug; synthesis keys off this
title: <noun phrase>
question: <the decision this file must unstick>
date: YYYY-MM-DD             # write date
sources_accessed: YYYY-MM-DD # last search/fetch date (may equal date)
status: complete | draft
overall_confidence: high | medium | low   # of the *recommendation*, not of the prose
primary_sources_count: N     # official docs/specs/repos fetched, not aggregators
---

# RQNN — <Title>

One-line scope constraint if the brief had one (providers, ADRs, out-of-scope).

## TL;DR

150–250 words. Must contain: (1) the answer to `question`, (2) the two or three load-bearing findings, (3) the main limitation / what would change the answer, (4) the implication in one sentence. No claim that does not appear, cited, in Findings. No 10-item backlog.

## Method

Where you looked (vendor docs, specs, repos, help centers). Eligibility (what counted as primary). Anything you did *not* search. Synthesis method (narrative / comparison table). Last-search date. If a claim is an absence-inference, say so here as a method risk.

## Findings

Value-neutral. Headings by *topic*, not by “what we should build.” Every nontrivial claim has an inline markdown link to a primary source; put `(accessed YYYY-MM-DD)` on the first use of that URL. Mark aggregator-only claims `(secondary)` and unverified absences `(unverified — not in cited docs)`. Tables are encouraged for comparisons. **Do not** use “recommend,” “ship,” or “cycle” in this section.

## Limitations and uncertainty

What the evidence cannot support. Freshness risks. Source-quality problems (SEO, vendor benchmarks, missing internals). Conflicts across sources. What a follow-up search should target. This section is not optional even if short.

## Implications for the product

Interpretation only. For each live option (including “do nothing” / “defer”):

**Option X — <name>** (`confidence: high|medium|low`)
- **Why recommend:** <evidence pointers, not new facts>
- **Why not:** <real costs, lock-in, ADR conflicts, what we’d miss>

If only one option is viable, still write the why-not (Nygard: negative consequences).

## Cycle-sized moves

At most **seven** items, each plausibly one spec-driven PR. Rank by leverage. One sentence each: *do this / not that*. No new evidence. Include a **Do not build** line if the research produced one.

## Sources

Numbered list of **cited** URLs with titles and access dates (the index). Optionally `### Consulted, not cited` for rejected sources (xAI’s full-trail idea). Do not dump search SERPs.

## Open issues

Falsifiers: what, if found next month, would rewrite the recommendation.
```

**Gap critique** uses the same front matter and TL;DR, but Findings become “cross-report tensions / coverage holes,” Implications become “what the synthesis must not paper over,” and cycle-sized moves become “required follow-ups before RFC freeze.”

**Synthesis** uses the same split (facts about what the RQs jointly show vs the recommended public-launch arc). Cycle-sized moves here may be grouped into RFC cycles; still keep Findings free of “we will ship.”

---

## Checklist a report must pass

A report is not `status: complete` unless all of these are true:

1. **Front matter present** — `question`, `date`, `sources_accessed`, `overall_confidence` filled.
2. **TL;DR is a structured abstract** — answers the question, includes a limitation, introduces no uncitable novelty, ≤250 words.
3. **Findings ≠ recommendations** — no “ship / build / cycle” in Findings; no new empirical claims in Implications or cycle list.
4. **Every nontrivial claim has an inline source link** — not merely a URL in a closing list. Quotes used when the claim is load-bearing (NotebookLM analog).
5. **Primary over secondary** — load-bearing claims cite vendor docs, specs, or repos; reviews/aggregators labeled `(secondary)`.
6. **Absence is labeled** — “not documented in X as of DATE” ≠ “X cannot do it,” unless a primary source says so.
7. **Dates on time-sensitive facts** — prices, model names, competitor features carry “as of YYYY-MM-DD.”
8. **Confidence is ordinal and scoped** — High/Medium/Low on *recommendations*, with a why; no made-up percentages.
9. **Limitations section exists** and is echoed in the TL;DR.
10. **Why-recommend and why-not** appear on each live option (including defer).
11. **Cycle list is ≤7** and each item is one cycle; do-not-build is explicit when relevant.
12. **Sources index matches inline cites** — every inline URL appears in Sources; consulted-but-rejected sources are not silently omitted if they shaped a negative finding.
13. **Reusable headings** — H2 names match this template so a synthesizer/critic can grep them.
14. **Verification stance** — a critic could follow each load-bearing sentence to a URL without trusting the author’s vibe (Anthropic citation-accuracy axis).

---

## Limitations (this meta-report)

- Anthropic’s published lead-agent prompt references `<writing_guidelines>` that are **not** in the public cookbook file; report-prose style was inferred from the Citation Agent, Citations API, and the engineering blog, not from a missing internal prompt.
- No Anthropic document titled “writing for verification” was found; that phrase in the brief was mapped to Citations + Claude Code verification loops.
- xAI does not document DeepSearch/DeeperSearch as a report schema; API citations docs were used instead.
- Gemini Deep Research is preview (`deep-research-preview-04-2026`); section names in Google’s example are illustrative, not a mandated schema.
- OpenAI’s deep-research cookbook page is marked archived; the live API guide was treated as current.
- This file did not re-audit every 2026-09-03 RQ in progress; keep/add/drop is based on the requested 2026-07-12/18 samples plus a spot-check of current RQs that already use the inherited shape.

---

## Sources

1. Anthropic, “How we built our multi-agent research system,” 2025-06-13 — https://www.anthropic.com/engineering/multi-agent-research-system
2. Anthropic, Citations — https://platform.claude.com/docs/en/build-with-claude/citations
3. Anthropic cookbook, `citations_agent.md` — https://github.com/anthropics/anthropic-cookbook/blob/main/patterns/agents/prompts/citations_agent.md
4. Anthropic cookbook, `research_lead_agent.md` — https://github.com/anthropics/anthropic-cookbook/blob/main/patterns/agents/prompts/research_lead_agent.md
5. Anthropic, Claude Code best practices (verification) — https://code.claude.com/docs/en/best-practices
6. Anthropic, “Building verification loops in Claude Code with skills” — https://claude.com/blog/building-verification-loops-in-claude-code-with-skills
7. OpenAI, “Introducing deep research” — https://openai.com/index/introducing-deep-research/
8. OpenAI Help Center, Deep research in ChatGPT — https://help.openai.com/en/articles/10500283-deep-research
9. OpenAI API, Deep research — https://developers.openai.com/api/docs/guides/deep-research
10. OpenAI Cookbook, Introduction to deep research in the API (2025-06-25, archived) — https://developers.openai.com/cookbook/examples/deep_research_api/introduction_to_deep_research_api
11. OpenAI Model Spec, 2025-04-11 — https://model-spec.openai.com/2025-04-11.html
12. OpenAI, BrowseComp — https://openai.com/index/browsecomp
13. xAI, Citations — https://docs.x.ai/developers/tools/citations
14. xAI, Web Search — https://docs.x.ai/developers/tools/web-search
15. xAI, Tools overview — https://docs.x.ai/developers/tools/overview
16. Google AI, Gemini Deep Research Agent — https://ai.google.dev/gemini-api/docs/deep-research
17. Google Cloud, Use the Gemini Deep Research Agent — https://docs.cloud.google.com/gemini-enterprise-agent-platform/agents/use-deep-research
18. Google AI, Grounding with Google Search — https://ai.google.dev/gemini-api/docs/interactions/google-search
19. Google, Use chat in Gemini Notebook (NotebookLM) — https://support.google.com/gemininotebook/answer/16179559
20. PRISMA 2020 for Abstracts — https://www.prisma-statement.org/abstracts
21. Page et al., PRISMA 2020 explanation and elaboration, *BMJ* 2021 — https://www.bmj.com/content/372/bmj.n160
22. Diátaxis, Explanation — https://www.diataxis.fr/explanation/
23. Michael Nygard, “Documenting Architecture Decisions,” 2011 — https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions
24. Martin Fowler, Architecture Decision Record — https://martinfowler.com/bliki/ArchitectureDecisionRecord.html

All URLs fetched or confirmed 2026-09-03.
