# How to run a multi-report research fleet so the pile becomes a decision

*Meta-research for the 2026-09-03 public-launch fleet. Sources accessed 2026-09-03. This file is process guidance, not product research. Do not treat it as a thirteenth RQ.*

---

## 1. TL;DR

Official vendor systems and systematic-review practice agree on one shape: **plan with exclusive task contracts → parallel workers who do not coordinate mid-flight → a critic that scores completeness and conflict, not prose quality → a synthesizer who owns the final artifact and traces every load-bearing claim back to a worker report.** The aggregate is more than a pile of reports only when (a) workers were scoped so they cannot all search the same query, (b) overlap is *reconciled* rather than concatenated, and (c) the last document is decision-ready (recommendation, conflict resolution, confidence, traceability, explicit out-of-scope).

Learny’s house convention (project-brief → parallel `rqNN` reports → `gap-critique.md` → `synthesis.md` → README index) is the right skeleton. It is Anthropic orchestrator-workers plus OpenAI “manager owns the answer” plus Gemini’s frozen research plan, written as files. It is **under-specified at the two places vendors say fleets fail**: exclusive subagent briefs (scope, effort, output contract, “do not research X”) and a synthesis that is more than a roundup.

**For this fleet (rq01–rq12 already in flight on the old template): do not rewrite the twelve reports.** Compensate in `gap-critique.md` with a **claim matrix + conflict log + coverage map**, cheap in-place corrections only for load-bearing falsehoods, and at most 0–3 follow-up memos. Put the RFC-004 recommendation, cycle sequence, must-be-true / out-of-scope, confidence labels, and `rqNN` traceability in `synthesis.md`. The synthesizer writes that document; a critic does not.

---

## 2. Per-source findings

### 2.1 Anthropic — multi-agent research system

**Primary:** [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) (2025-06-13).

Orchestrator-worker, not a chat roundtable. A **LeadResearcher** analyzes the query, writes a strategy to **Memory** (so the plan survives context truncation), spawns specialized **Subagents** in parallel, synthesizes their compressed findings, and may run another wave if gaps remain. A separate **CitationAgent** then walks the report and source documents and attaches claim-level citations. Subagents are isolation units: own context window, own search trajectory, **almost no knowledge of siblings**. That isolation is what enables true parallelism and is also why vague briefs cause duplicate work.

Concrete practices:

| Practice | What they actually do |
|---|---|
| Subagent brief contract | Every worker gets an **objective**, an **output format**, **tools/sources to use**, and **task boundaries / done-when**. Short instructions like “research the semiconductor shortage” caused one agent to study 2021 auto chips while two others duplicated 2025 supply chains. |
| Effort calibration | Embedded scaling rules: simple fact-finding = 1 agent, 3–10 tool calls; comparisons = 2–4 subagents, 10–15 calls each; complex research = 10+ with divided responsibilities. Early systems spawned 50 subagents for simple queries and searched endlessly for nonexistent sources. |
| Search strategy | Start **wide then narrow**. Agents default to over-specific queries that return nothing. |
| Merge | Subagents **compress** (condensed summaries / fact lists) back to the lead. The lead, not a worker, writes the final report. Appendix: write bulky artifacts to a **filesystem** and pass **references**, not full dumps, to avoid a game of telephone. |
| Stop condition | When further research has diminishing returns, **stop spawning** and write the report. Over-collection is a named failure mode. |
| Critique | Production path is **citation attribution**, not a second full research pass. Evaluation used a **single LLM-as-judge** with a rubric (factual accuracy, citation accuracy, completeness, source quality, tool efficiency), scores 0.0–1.0 plus pass/fail. Multiple judges for components were *less* consistent than one well-prompted judge. Humans still catch SEO-farm bias that evals miss. |
| Known failure modes | Overlapping work from vague briefs; over-collection; agents distracting each other with excessive updates; lead cannot steer running subagents (synchronous batches); compounding errors in long stateful runs. |

**Cookbook prompts** make the brief contract explicit: [research_lead_agent.md](https://github.com/anthropics/anthropic-cookbook/blob/main/patterns/agents/prompts/research_lead_agent.md). Classify the query as **depth-first** (same question, many perspectives), **breadth-first** (independent sub-questions), or **straightforward**. For breadth-first: “Define extremely clear, crisp, and understandable **boundaries between sub-topics to prevent overlap**.” One core objective per subagent. Name high-quality sources and sources to avoid. Default ~3 subagents; 5–10 for high complexity; **never more than 20**; prefer fewer capable workers over many thin ones. **Never create a subagent to write the final report.** Demo variant: researchers write notes to `files/research_notes/`, then a writer compiles ([claude-agent-sdk-demos/research-agent](https://github.com/anthropics/claude-agent-sdk-demos/tree/main/research-agent)).

### 2.2 Anthropic — workflow patterns (composable, not “always multi-agent”)

**Primary:** [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) (2024-12-19). Cookbooks: [orchestrator_workers.ipynb](https://github.com/anthropics/anthropic-cookbook/blob/main/patterns/agents/orchestrator_workers.ipynb), [evaluator_optimizer.ipynb](https://github.com/anthropics/anthropic-cookbook/blob/main/patterns/agents/evaluator_optimizer.ipynb).

- **Workflows** = predefined code paths. **Agents** = the model directs its own loop. Use the simplest thing that works.
- **Parallelization / sectioning:** independent subtasks, aggregate programmatically. This is Learny’s “12 RQs in parallel.” **Voting:** same task, multiple attempts, for confidence. Do not confuse the two.
- **Orchestrator-workers:** the orchestrator **decides subtasks at runtime** (XML task list in the cookbook). Use when you cannot pre-define the split. Workers receive **the original task plus their slice**. Cookbook explicitly suggests a later **synthesis phase**.
- **Evaluator-optimizer:** generator ↔ evaluator loop against a **fixed rubric**, `PASS` / `NEEDS_IMPROVEMENT`, stop on pass or max iterations. Fit when (1) human feedback would demonstrably improve the draft and (2) an LLM can give that feedback. Best for complex search that must decide “is another round warranted?” Not for rewriting twelve finished reports from scratch.

Transparency principle from the essay: **show the plan**. A frozen `project-brief.md` is that plan in a file fleet.

### 2.3 OpenAI — Deep Research (one model plans and synthesizes)

**Primary:** [Introducing deep research](https://openai.com/index/introducing-deep-research/); [Deep research System Card](https://openai.com/index/deep-research-system-card/) (2025-02-25) and [PDF](https://cdn.openai.com/deep-research-system-card.pdf); [Deep research API](https://developers.openai.com/api/docs/guides/deep-research).

ChatGPT Deep Research is **one browsing-optimized reasoning model** executing a multi-step trajectory: search, interpret, pivot, cite. It is **not** a published orchestrator-of-twelve-workers. Training (end-to-end RL on hard browsing tasks) taught it to plan, backtrack, and synthesize hundreds of sources into an analyst-level report.

Process that *does* decompose, in ChatGPT product (API docs, “Prompting deep research models”):

1. **Clarification** (smaller model) — 2–3 questions on goals, constraints, preferences. Do not research yet.
2. **Prompt rewriting** — expand into a fully-formed research brief (specificity, output format, tables, source priority, language). Do not invent unstated constraints; mark them open-ended.
3. **Deep research** — the expanded prompt is the only input; the model **will not ask again**.

The Responses API **omits** steps 1–2. Developers must supply the brief. **`max_tool_calls`** is the documented lever against over-collection (cost/latency). Require **inline citations and source metadata** in the prompt. Prefer primary sites and original papers over aggregators/SEO blogs — the same source-quality heuristic Anthropic had to add after humans spotted content-farm bias.

The system card is **safety** (web-browsing risks, PII, prompt injection, Preparedness evals), not a merge-protocol paper. Treat it as: long-horizon browsing agents need independent mitigations; do not confuse it with a completeness critic.

### 2.4 OpenAI — Agents SDK planner/worker, handoffs, cookbook pipeline

**Primary:** [Agent orchestration](https://openai.github.io/openai-agents-python/multi_agent/); [Orchestration and handoffs](https://developers.openai.com/api/docs/guides/agents/orchestration); [Deep Research API with the Agents SDK](https://developers.openai.com/cookbook/examples/deep_research_api/introduction_to_deep_research_api_agents); [multi-agent portfolio cookbook](https://developers.openai.com/cookbook/examples/agents_sdk/multi-agent-portfolio-collaboration/multi-agent-portfolio-collaboration).

Two patterns, and the distinction matters for fleets:

| Pattern | Who owns the final answer? | Use when |
|---|---|---|
| **Agents as tools** (`Agent.as_tool()`) | **Manager stays in control**, calls specialists for bounded subtasks, **combines** outputs | You want one synthesis, shared guardrails, parallel specialists |
| **Handoffs** | Specialist **becomes** the active agent for the rest of the turn | Routing *is* the workflow; specialist should speak directly |

A Learny file fleet is **agents-as-tools**: workers write `rqNN` files; the synthesizer owns RFC-shaped output. Handoffs are what you do if a specialist were allowed to publish the synthesis themselves — vendors warn that loses the global view.

Cookbook four-agent pipeline (official): **Triage → Clarifier (optional) → Instruction builder → Research agent**. Instruction-builder rules that map onto RQ briefs: maximize specificity; fill missing dimensions as *open-ended*; never invent constraints; **explicitly request tables** for comparisons; **state the output format**; prioritize official/primary sources.

SDK docs also name **chaining** (research → outline → write → **critique** → improve) and **parallel** `asyncio.gather` for independent tasks. Start with one agent; split only when isolation of prompt, tools, or policy pays for the extra traces.

**Not official:** third-party writeups (e.g. Towards AI) add a **Critique Agent** that can force a second research run, then a Report Agent, capped at two deep-research passes. Useful adjacent pattern; do not cite it as OpenAI docs. Official cookbook stops at producing the research artifact after prompt enrichment.

### 2.5 xAI — Grok DeepSearch / DeeperSearch

**Official, thin on internals:**

- Product: [Grok 3 Beta — The Age of Reasoning Agents](https://x.ai/news/grok-3) (2025-02-19). DeepSearch is “our first agent,” designed to **synthesize key information, reason about conflicting facts and opinions, and distill clarity from complexity**. Output: a **summary trace** that is a concise comprehensive report. Think mode separately spends test-time compute to **correct errors, explore alternatives, verify**.
- API: [Web Search](https://docs.x.ai/developers/tools/web-search), [Advanced usage](https://docs.x.ai/developers/tools/advanced-usage), [Collections Search](https://docs.x.ai/developers/tools/collections-search). There is **no developer-doc object named DeepSearch/DeeperSearch**. Research is “give Grok `web_search` + `x_search` + optional `collections_search` / `code_execution`; the model orchestrates.” Documented hybrid strategy when internal + web tools are both on: **internal corpus first → external context → synthesis with citations from both** (`collections://` and `https://`). Domain allow/deny lists constrain search. Combine web + X for news vs social; add code execution when numbers must be computed.

**Not in official docs (treat as unverified if a later RQ repeats them):** consumer-blog claims of a hard 10-step limit, “seven consistency layers,” or DeeperSearch as “two steps further.” xAI has not published an Anthropic-grade orchestrator post. What *is* official and reusable: **conflict-aware synthesis is the product promise**, citations appear when search tools ran, and **ground in the local corpus before the open web** — which for Learny fleets means: read `project-brief.md` and ADRs before another NotebookLM thinkpiece.

### 2.6 Google — Gemini Deep Research

**Primary:** [Gemini Deep Research overview](https://gemini.google/overview/deep-research/); [Use Deep Research in Gemini Apps](https://support.google.com/gemini/answer/15719111); [Gemini API Deep Research Agent](https://ai.google.dev/gemini-api/docs/deep-research).

This is the closest consumer analog to a **human-gated fleet plan**:

1. **Plan:** prompt → multi-point research plan (sub-tasks).
2. **Human edit:** Apps UI “Edit plan”; API `collaborative_planning=true` until the user sets it false. **You must flip the flag to execute** — saying “looks good” is not enough.
3. **Execute:** the model decides which sub-tasks are parallel vs sequential; thinking panel shows what has been learned and the next move.
4. **Synthesize:** “critically evaluates the information, **identifies key themes and inconsistencies**, structures the report… **multiple passes of self-critique**.”
5. **Reliability:** long-running jobs use an async task manager with **shared state between planner and task models** so a single failure does not restart the whole job.

Engineering notes that transfer: multi-step planning must trade coverage against wait time; context is the plan plus everything gathered so far; synthesis is **theme + contradiction**, not a catena of section summaries. For a file fleet, `project-brief.md` is the editable plan; spawning 12 researchers before the owner has frozen boundaries is skipping Gemini’s most important UX.

### 2.7 Systematic review — PRISMA flow (dedupe → screen → extract → synthesize)

**Primary:** [PRISMA 2020 flow diagram](https://www.prisma-statement.org/prisma-2020-flow-diagram); [PRISMA 2020 statement (BMJ)](https://doi.org/10.1136/bmj.n71); [explanation & elaboration](https://pmc.ncbi.nlm.nih.gov/articles/PMC8005925/).

Information flow (new reviews): **identify** records (per database) → **remove duplicates** (and automation-ineligible) → **screen** titles/abstracts → **retrieve** full texts → **eligibility** (exclude with **reasons**) → **include** in synthesis. Counts must add up. Dual independent screening is more reliable than one reviewer. Synthesis methods (item 13) must be **pre-specified**: what is eligible for each synthesis, how data were prepared, narrative vs quantitative, how heterogeneity/conflict was handled.

Transfer to a fleet: the 12 markdown files are **databases**. Before synthesis, **dedupe claims** (same competitor fact, same pedagogy citation, same pricing number appearing in three RQs). Screen for **in-scope vs neighbor-scope**. Extract into a structured table. Synthesize with a stated rule for disagreement. A README table of filenames is not a PRISMA flow.

### 2.8 Knowledge synthesis — evidence tables, GRADE, claim/evidence matrices

**Primary:** Cochrane Handbook [Ch. 14 — Summary of findings and GRADE](https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-14). Adjacent: [CCA / evidence matrices in overviews](https://doi.org/10.1017/rsm.2025.10056); EviSearch reconciliation protocol ([arXiv:2604.14165](https://arxiv.org/html/2604.14165)); SLIDERS evidence-table reconciliation ([arXiv:2604.22294](https://arxiv.gg/abs/2604.22294)).

- **Summary of findings:** decision-makers get a **short table** (Cochrane: ≤7 outcomes) with effect, volume of evidence, and **certainty** (high / moderate / low / very low). Certainty is a structured judgment (bias, inconsistency, indirectness, imprecision, publication bias), not a vibe. SoF tables belong **up front**, before the narrative.
- **Evidence / citation matrix (overviews of reviews):** rows = reviews, columns = unique primary studies, cells = presence. Quantifies overlap (corrected covered area). For fleets: rows = `rqNN`, columns = **atomic claims** (or unique primary URLs).
- **Reconciliation agents (EviSearch):** two extractors; if they agree, take the value; if they disagree, **forced re-read of the source page** before committing. Labels: both correct / A right / B right / both wrong (low confidence → human). Do not average conflicting numbers in the synthesizer’s head.

A **claim matrix** is the software-research equivalent: claim × supporting RQs × sources × agree/conflict × confidence × action (adopt / adopt-with-caveat / defer / discard).

### 2.9 LLM-as-judge / red-team completeness

**Primary:** Zheng et al., [Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685) (NeurIPS 2023). Combined with Anthropic’s research-eval section above.

- LLM judges can match human agreement (~80%+) on open-ended output **if** the rubric is explicit.
- Biases to design against: **position** (first/last wins), **verbosity** (longer looks better), **self-enhancement**. Mitigations: single-answer grading against a rubric (Anthropic found this more consistent than a panel of judges), don’t let the author-model grade itself, require evidence pointers not adjectives.
- A completeness critic should score **coverage of the brief**, **source quality**, **citation match**, and **unresolved conflicts** — not “is this well written?”
- Academic DeepVerifier-style work (ACL Findings 2026) argues holistic “is this a good report?” judges underperform **decomposed, source-checkable** verification questions. Same lesson as EviSearch: split the audit.

Human red-team still catches what rubrics miss (Anthropic: content farms). For Learny fleets, the owner reading the synthesis against the live app is that pass.

---

## 3. Audit of the house fleet convention

Compared against: this folder’s [README.md](README.md) and [project-brief.md](project-brief.md); completed samples [2026-07-12](../2026-07-12/README.md) (8 reports + gap-critique + 3 follow-ups → RFC-002) and [2026-07-18](../2026-07-18/synthesis.md) plus [student-experience/synthesis.md](../2026-07-18/student-experience/synthesis.md) (RQ reports with adversarial verification → ADR-0026 / RFC-004).

### 3.1 Keep

| Artifact / habit | Why it already matches primary guidance |
|---|---|
| Dated folder under `docs/research/YYYY-MM-DD/` | Durable evidence archive; CLAUDE.md already requires materializing conclusions into ADR/RFC, not a second `STATE.md`. |
| **`project-brief.md` as frozen working memory** | Gemini collaborative plan + OpenAI clarification/rewrite + Anthropic Memory. Thesis, walkthrough, constraints, success criterion, RQ list. |
| **README index** with one-line “question it answers” | Navigation norm; maps to PRISMA “what was searched.” |
| **Parallel `rqNN-<slug>.md`** | Anthropic breadth-first + OpenAI sectioning + agents-as-tools. Isolation is correct. |
| **Hexagonal / ADR constraints in the brief** | OpenAI “don’t invent constraints”; xAI “internal corpus first.” |
| **House report shape** (July 18): Method → findings → **capability/claim tables** → Recommendation with **why-recommend and why-not** → Open issues → **Verification corrections** | Output contract + AskUserQuestion convention + in-place repair instead of silent rewrite. |
| **`gap-critique.md` as a separate critic** | Evaluator role distinct from generators. July 12’s three GAPs were load-bearing (quiz format vs schema, VPS sizing, embed model mismatch) — that is the right altitude. |
| **Bounded follow-up memos** (`followup-*.md`) | Evaluator-optimizer with a stop condition. Do not loop the whole fleet. |
| **`synthesis.md` as RFC-shaped output** | Anthropic: lead writes the report. July 18 student-experience synthesis: tensions **resolved**, cycle sequence, explicit deferrals — this is the gold sample, not a literature review. |
| **Adversarial verification + append corrections** (July 18 rq01) | CitationAgent / EviSearch: refute in place; don’t pretend the first draft was clean. |
| **Materialize into RFC/ADR; keep folder as evidence** | Stated in the 2026-09-03 brief; matches house docs policy. |

### 3.2 Add (the convention is missing these)

| Gap in the convention | Vendor/primary source | What to add |
|---|---|---|
| RQ list is **one sentence each**, no exclusive boundaries | Anthropic semiconductor-shortage failure; lead-agent prompt “crisp boundaries” | Per-RQ **owns / may-cite / do-not-research** lines in the brief **before** spawn. |
| No **effort calibration** | Anthropic scaling rules; OpenAI `max_tool_calls`; Gemini coverage vs wait | e.g. secondary RQ (pricing) = thinner budget than flagship pedagogy. |
| No **output contract** in the brief | OpenAI instruction-builder; Anthropic “expected output format” | Mandate Method, tables for comparisons, Recommendation A/B/C with why-not, Open issues, source access dates. (July 18 did this by culture, not by brief.) |
| No **overlap / claim matrix** | PRISMA dedupe; Cochrane evidence matrix; EviSearch | Required section of `gap-critique.md`. |
| Critique is **completeness-only** (July 12) or **died and was inlined** (July 18) | Evaluator-optimizer + CitationAgent | Fleet critic: coverage **and** conflicts **and** citation/source-quality flags. One pass. |
| Synthesis sometimes lists RQ recs without **confidence** or **must-be-true** | GRADE SoF; 2026-09-03 success criterion already asks for must-be-true / out-of-scope | SoF-like table up front in synthesis (≤7 launch bets). |
| No rule **who writes synthesis** | Anthropic: never a subagent | Synthesizer = orchestrator role; critic does not draft RFC-004. |
| README status is binary (not started / done) | Gemini thinking panel; PRISMA counts | After synthesis: one-line finding + link to synthesis section. |
| 12 parallel RQs with no anti-overlap | Anthropic: default 3, 5–10 complex, prefer fewer | 12 is defensible for a **pre-defined breadth-first** public-launch map (closer to parallelization than runtime orchestrator) **only if** boundaries are exclusive. This fleet’s RQ list has known collisions (below). |

### 3.3 Drop / stop doing

| Habit | Why drop |
|---|---|
| Treating **concatenation of RQ recommendations** as synthesis | Vendors: identify inconsistencies; GRADE: force a small decision set. July 12 without follow-ups would have shipped a contradictory quiz schema. |
| **Per-report evaluator-optimizer loops** as the default after 12 drafts exist | Anthropic: extra loops cost 15× tokens; OpenAI: don’t Deep-Research trivia. One fleet critic + 0–3 follow-ups. |
| **Rewriting worker reports** to match the synthesis | July 18: append verification corrections; leave the evidence trail. Filesystem artifacts stay. |
| **Spawning a 13th “write the RFC” researcher** that never reads siblings | Anthropic: lead writes the report from worker products. |
| **Gap-critique that only lists missing topics** without saying which RQ already covered them under another name | Creates fake follow-up work (PRISMA: you must count what was already included). |
| Unofficial third-party “DeepSearch has N steps” lore in later RQs | Not in xAI docs. |

### 3.4 This fleet’s structural overlaps (predictable collisions)

The 2026-09-03 brief is strong on **product snapshot and constraints**, weak on **exclusive slices**. Expect duplicate NotebookLM / citation / FSRS / landing-page material unless the critic matrices it:

| Collision zone | RQs | Who should own the *decision* |
|---|---|---|
| Competitive set + positioning vs NotebookLM | rq01, rq12, bits of rq03/rq05 | rq01 owns the landscape table; rq12 owns GTM/landing; synthesis cites both |
| Learning science → tutor → quiz quality | rq02, rq03, rq04 | rq02 principles; rq03 session design; rq04 item/QC/review UX |
| Retrieval “smarter answers” vs citations-as-product | rq05, rq03, rq01 | rq05 owns ranking/hybrid; others may only consume the constraint |
| Reader UX vs IA vs onboarding | rq06, rq11, rq07 | rq06 reading surface; rq11 sitemap/IA; rq07 first session |
| Streaks/heatmap vs “don’t cheapen” vs landing | rq08, rq12, walkthrough in brief | rq08 mechanics; rq12 copy; brief already records the heatmap exists |
| Abuse/cost caps vs pricing | rq09, rq10 | rq09 operational caps (must); rq10 commercial packaging (secondary) |

The brief already marks pricing **secondary**. Official effort-calibration would have given rq10 a shorter contract; the critic should not let it dominate synthesis.

---

## 4. Recommended fleet playbook (future fleets)

Steps and artifacts. This is **parallelization with a frozen plan** (Anthropic “sectioning” + Gemini collaborative planning), not a runtime orchestrator that invents RQs after spawn — unless the owner explicitly wants a lead agent to propose the RQ list.

### Phase 0 — Protocol (human + lead)

**Artifact: `project-brief.md` (frozen before workers start).**

Contents:

1. Thesis, current product snapshot, constraints (ADRs), success criterion (what the synthesis must be).
2. Query type: breadth-first / depth-first / mixed.
3. RQ table with, **per RQ**:
   - One-sentence question
   - **Owns** (decisions this report is allowed to make)
   - **Must not decide** (neighbors)
   - **May cite** (facts it can reuse if encountered)
   - Effort (S/M/L; tool-call / hour budget)
   - Required tables (e.g. competitor matrix, GRADE-like certainty)
4. Global **output contract** (see below).
5. Source-quality rules (primary docs, access dates, flag unverified, no SEO farms).
6. Owner sign-off = Gemini “Start research.”

**Artifact: `README.md`** — index + status checkboxes. Do not wait until the end.

Optional: `overlap-matrix.md` if >8 RQs — claim-families vs RQ owners, filled *before* research.

### Phase 1 — Parallel workers

**Artifacts: `rqNN-<slug>.md` only.** Workers do not read each other’s drafts (Anthropic isolation). They **do** read the brief and named ADRs/RFCs (xAI internal-first).

**Output contract (paste into every worker prompt):**

```
# RQ-NN — <title>
- Status, date, question (copy from brief Owns line)
## Method (sources, dates, what you did not search)
## Findings (structured; tables for comparisons)
## Recommendation (options; mark one recommended; why-recommend AND why-not for every option)
## Open issues (unverified, absence-inferences, watch-items)
## Sources (primary URLs + access dates)
```

Done-when: the Recommendation is implementable inside stated constraints, or it explicitly says “insufficient evidence” and names what would change the call. Stop searching (Anthropic diminishing returns).

If a worker hits a **blocking fact owned by another RQ**, record it as a pointer (“rq07 should decide time-to-value metric”) rather than deciding it.

**Filesystem, not telephone:** write the report to disk; return a short abstract to the orchestrator. Do not paste 8k-word reports into a synthesizer prompt if the file can be read.

### Phase 2 — Screen and extract (critic)

**Artifact: `gap-critique.md`.** One critic, one pass. Author ≠ critic.

Rubric (single LLM-as-judge + human skim), adapted from Anthropic’s research judge + PRISMA + GRADE:

| Axis | Pass if |
|---|---|
| Spec conformance | Output contract present; ≥N primary sources; unverified labeled |
| Coverage | Every **Owns** line in the brief has an answer or an explicit “unknown” |
| Source quality | Load-bearing claims cite primary URLs, not aggregators |
| Citation match | Spot-check: quoted fact exists at URL (CitationAgent / EviSearch pass 2) |
| Dedupe | Claim matrix filled; duplicates listed, not re-researched |
| Conflict | Disagreements listed with both citations; none silently averaged |
| Effort / scope creep | Secondary RQs did not swallow the synthesis agenda |

**Claim matrix (required table):**

| Claim (atomic) | RQs asserting | Agree? | Best primary source | Confidence | Action |
|---|---|---|---|---|---|
| … | rq01, rq12 | conflict | URL | low/med/high | synthesis must resolve |

**Coverage map:** brief Owns lines × answered / partial / missing.

**Follow-up gate:** only spawn `followup-*.md` if a gap would **change a synthesis decision** (July 12: quiz format, VPS fit, embed model). Cap 3. That is evaluator-optimizer with a stop condition.

Do **not** require per-report rewrite loops. Optional cheap retrofit: a 10-line `## Scope note` at the top if the report drifted, or a `## Verification corrections` appendix (July 18).

### Phase 3 — Synthesize (orchestrator / lead)

**Artifact: `synthesis.md`.** The lead writes it. Workers do not.

Minimum contents (beyond a summary):

1. **Summary of findings table** (≤7 launch bets): recommendation, which RQs, confidence, RFC cycle impact.
2. **Conflict resolutions** (numbered; each cites RQ sections). Unresolved → explicit deferral, not a fudge.
3. **Traceability:** every cycle/workstream row → `rqNN` + heading.
4. **Must-be-true / out-of-scope per cycle** (this fleet’s stated success criterion).
5. **Watch-items** (e.g. competitor ships SRS) with what document to refresh, not “re-open architecture.”
6. **Assumption check** against locked ADRs/RFCs (July 18 pattern).

Then materialize: RFC and/or ADR. Leave the folder as the evidence base.

### Phase 4 — Index

Update README: all checkboxes, and optionally a “Finding” column pointing at synthesis headings. That is the navigation norm: **index → brief → RQs → critic → synthesis → RFC**.

### Subagent brief template (copy-paste for future orchestrators)

```
You are RQ-NN only.
Objective: <one core question>
Owns: <decisions>
Must not decide: <neighbor RQs>
Do not spend budget on: <list>
Read first: project-brief.md, <ADR/RFC paths>
Sources: official/primary; access dates; flag unverified
Effort: S/M/L; stop when Recommendation is evidence-complete
Output: the house contract; Recommendation options with why-not
Write to: docs/research/YYYY-MM-DD/rqNN-<slug>.md
Do not write synthesis.md or gap-critique.md.
```

---

## 5. Actionable guidance for THIS fleet (rq01–rq12 already in flight)

Workers are using the **July 18-style template** (Method / findings / recommendation / open issues), not the exclusive-boundary brief above. **Do not stop them to retrofit contracts. Do not rewrite twelve files to a new template.** Repair at the critic and synthesizer, which is what Anthropic’s lead + citation pass and OpenAI’s manager-owns-the-answer pattern are for.

### 5.1 Cheap retrofit of the twelve reports (optional, only if cheap)

Do these **only** when the critic finds a load-bearing problem. Budget minutes, not a second fleet.

1. **In-place `## Verification corrections`** (July 18 rq01) if a primary source refutes a claim the synthesis would otherwise adopt. Leave the original text; don’t history-hole.
2. **One-line scope sticker** at the top if a report decided a neighbor’s question: `Owns for synthesis: … / Defer to rqNN: …`
3. **Do not** add missing exclusive-boundary preambles to all 12. The claim matrix replaces that.
4. **Do not** run evaluator-optimizer rewrite loops per file. Completeness of *the fleet* is the critic’s job.

If a report is empty or aborted, the critic records it as PRISMA “not retrieved”; the synthesizer does not hallucinate its recommendation.

### 5.2 How `gap-critique.md` should compensate

One document, one author (not an rqNN researcher). Suggested structure:

```
# Gap critique — 2026-09-03 public-launch fleet
## Method (rubric, what you spot-checked, what you did not re-research)
## Coverage map (brief Owns × status)
## Claim matrix (required)
## Conflict log (only real disagreements)
## Source-quality / unverified flags (by RQ)
## True gaps (would change RFC-004 if unanswered)
## Duplicate work (ignore in synthesis; pick a canonical RQ)
## Follow-up recommendation (0–3 memos max, or none)
```

**Critique is one fleet-level pass, not twelve.** Per-report nitpicks belong in the matrix (“rq06 restates rq11 IA”) rather than twelve mini-reviews.

**Confidence labeling here, not only in synthesis:** high = multiple primaries agree; moderate = one primary or consistent secondary; low = absence-inference, aggregator, or conflict. GRADE vocabulary is enough; don’t fake I² statistics.

**True gaps vs fake gaps:** July 12 was the right bar — contradictions that would ship the wrong schema. “Rq10 didn’t compare Lemon Squeezy vs Stripe Billing” is not a true gap if pricing is secondary and the synthesis only needs “use Stripe, meter AI.” “Rq01 and rq12 disagree whether NotebookLM is the competitive frame” **is** a true gap.

**Follow-ups:** spawn only for true gaps. Name the file `followup-<topic>.md` and link it from the critic. If none, say so.

### 5.3 How `synthesis.md` should compensate

This is the document that makes the pile a public-launch arc (candidate RFC-004). It must contain:

1. **SoF-style launch table (≤7 rows).** Examples of row types, not a pre-decided RFC: intelligence bets, attractiveness bets, operational-readiness bets. Each row: decision, confidence, `rqNN` traces, suggested cycle size. Pricing may be one row marked secondary or “out of v1 public launch.”
2. **Conflict reconciliation** using the critic’s log. Pattern from July 18 student-experience: numbered tensions, **resolution that names the winning RQ and why**, not “both have a point.” If evidence is insufficient, defer with a trigger.
3. **Traceability.** Cycle/workstream → RQ heading → (optional) primary URL for the load-bearing fact. If a reader cannot click from “do X” to evidence, it isn’t synthesized.
4. **Must-be-true / out-of-scope per cycle** — already the brief’s success metric. Honor hexagonal ports, pgvector-first, Compose-on-VPS, small spec-driven cycles.
5. **Assumption check** against ADR-0003/0006/0007/0008/0019/0020/0023/0026 and RFC-003 leftovers.
6. **Watch-items** (competitor moves, provider outages, the 2026-09-03 observed Anthropic 400 on Ask) with “refresh which section,” not “redesign the company.”

**The synthesizer reads files from disk** (Anthropic filesystem pattern). Do not rely on chat memory of twelve reports.

**The synthesizer does not re-research the landscape.** If evidence is missing, send a follow-up or label low confidence. Gemini’s self-critique passes are **on the synthesis draft** (themes + inconsistencies), not a thirteenth web crawl.

### 5.4 Index

When critique + synthesis exist: tick README boxes; add this file to the table as process meta (not an RQ). Optional “Finding” column after synthesis exists — don’t block on it.

### 5.5 Explicit non-goals for the remaining passes

- Do not merge overlapping prose from rq01 and rq12 into a mega-competitor chapter inside both files.
- Do not let rq10’s billing shape drive cycle 1 if the brief says product quality first.
- Do not replace the critic with “each researcher self-critiques” — Zheng/Anthropic: independent judge, single rubric.
- Do not wait for a CitationAgent overhaul of all footnotes; spot-check load-bearing URLs only.

---

## 6. Mapping: vendor stages → Learny files

| Vendor stage | Learny artifact |
|---|---|
| Gemini plan + human edit; OpenAI clarify/rewrite; Anthropic Memory | `project-brief.md` |
| Anthropic subagents; OpenAI agents-as-tools; PRISMA identify | `rqNN-*.md` |
| PRISMA dedupe/screen; LLM-as-judge completeness; EviSearch reconcile; Anthropic citation pass | `gap-critique.md` (+ optional `followup-*.md`) |
| Anthropic lead report; Gemini synthesis + self-critique; GRADE SoF; OpenAI manager final answer | `synthesis.md` → RFC/ADR |
| Navigation | `README.md` |

The house shape is right. The missing tissue is **exclusive briefs (too late for this fleet)** and **claim-level merge (not too late)**. This fleet’s remaining value is entirely in how honestly the critic matrices overlap and how decision-ready the synthesizer is willing to be.
