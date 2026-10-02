---
id: harness-rq05-external-practice
title: External practice for shipping features with AI coding agents (as of 2026-09-30)
question: "What does current external practice say about spec-driven development, agent loops, agent-ready repos, PR/commit hygiene with agents, CI as an agent sensor, and harness evaluation, and what is tlc-spec-lean?"
date: 2026-09-30
status: final
overall_confidence: Medium
---

# RQ05: External practice for agent-driven delivery

## TL;DR

- **What tlc-spec-lean is.** Tech Leads Club added `tlc-spec-lean` on 2026-09-09 ([PR #186](https://github.com/tech-leads-club/agent-skills/pull/186)) and bumped it to 1.1.0 on 2026-09-18 ([PR #205](https://github.com/tech-leads-club/agent-skills/pull/205)). It is described as the "evolution of `tlc-spec-driven` for models that already know how to implement". It replaces Specify→Design→Tasks→Execute with **Plan→Checks→Build→Verify**. It drops `tasks.md`, the component catalogue, `discuss.md`/`context.md`, auto-sizing and per-task self-review, which the PR calls "babysitting". It keeps EARS criteria, Python gates, an independent Verifier and STATE/lessons.
- **TLC's own benchmark** (private `tech-leads-club/fakeflix`, `bench-results` branch, 2026-09-20/21) has n=2 runs per arm on one PRD. **Lean matched or beat driven on fidelity at about 10–30% lower token cost.** With a strong model, *no framework* matched driven at about half the cost. With a weaker, faster model, both TLC skills clearly beat no-framework and Superpowers.
- **Vendor and practitioner consensus (2026).**
  - Keep always-loaded context short.
  - Turn prose rules into deterministic sensors and hooks.
  - Separate the verifier from the author.
  - Scale ceremony to the size of the change.
  - Stress-test and remove harness parts as models improve.
- **SDD critiques** are consistent: review burden from markdown, spec drift, and a "sledgehammer for a nut". Spec-driven development itself, Spec Kit and OpenSpec all sit at *Assess* on the Thoughtworks Radar.
- **Harness evaluation** is the field's weakest area. Few published A/B results exist.

## Method

- **Scope.** External sources only. I did not read local transcripts or the owner's research folders.
- **Tools.** `WebSearch` (about 25 queries), `WebFetch` (about 35 fetches) and `gh` CLI reads of public TLC repos. I also read the private TLC repo `tech-leads-club/fakeflix`, which the owner's GitHub credentials can access. Its benchmark data is member-only, so it is not citable publicly.
- **Counts.** 63 sources consulted, 50 cited (list below).
- **Source preference.** Primary sources: vendor docs and engineering blogs, arXiv abstracts, repo files, PRs and issues. Secondary summaries are used only where the primary 403'd: [openai.com/index/harness-engineering](https://openai.com/index/harness-engineering/) returned HTTP 403, so its content comes from InfoQ, a summary blog and a search snippet, and is marked as such.
- **Dating.** All access dates are 2026-09-30. Claims tagged *[unverified]* rest on one secondary source or a summary I could not check against the primary. WebFetch returns model-summarized pages, so quotations are as rendered by that summarizer. Numeric claims were cross-checked where possible.

## Findings

### F1. TLC community: tlc-spec-lean, its rationale, and TLC's benchmark

**F1.1 Origin and dates.** `tlc-spec-lean` first shipped in skills-catalog v0.17.7 on 2026-09-09, with the note "add tlc-spec-lean for modern-model spec work" ([releases](https://github.com/tech-leads-club/agent-skills/releases)).
- [PR #186](https://github.com/tech-leads-club/agent-skills/pull/186) by Waldemar Neto added 4,341 lines and was merged the same day.
- The skill page lists v1.1.0, updated 2026-09-18 ([skill page](https://agent-skills.techleads.club/skills/tlc-spec-lean/)).
- Its SKILL.md says it is "Derived from tlc-spec-driven 3.3.0 (Felipe Rodrigues), tlc-plan, and tlc-implement".

**F1.2 Stated weakness of tlc-spec-driven.** PR #186 states the thesis and tabulates the changes.

The thesis, verbatim:

> "What fails on those models is not reasoning — it is an obligation that was read and abandoned, then a *done* claim on top. Driven choreographed the **how**. Lean freezes the **what**, frees the plan, and proves it with someone who did not build it."

What was removed, and why the PR calls each item "babysitting":

| Removed from driven | Stated reason |
|---|---|
| Granular `tasks.md` (`Where`/`Tools`/`Depends on`, one commit per task) | "Fifteen one-file tasks buy ordering, not correctness — and they charge a re-read of the process on every task" |
| Component catalogue (Purpose/Location/Interfaces per class) | "It rots with the authority of a document" |
| `discuss.md` + `context.md` | "Pace questions and a quota of gray areas" |
| Auto-sizing Small/Medium/Large | "The model sized itself and skipped phases" |
| Per-task self-review | "The author re-reads their own blind spot" |

What was kept:
- EARS + SHALL criteria.
- Verifier ≠ author.
- Python gates.
- Lessons + STATE.
- The rule that "spec authorizes local work; push and prod need a go-ahead".

What was added:
- `checks.md`: each check is one observable claim plus the command that settles it.
- A coverage join.
- Profiles `light`/`standard`/`ui`, declared as a floor.
- Fault injection at `standard`+ ("proves the test can fail").
- A token-budget "handoff arithmetic": 150k by default; over budget, the skill stops and asks.

Size: driven 3.3 has 12 reference files of about 21k words; lean 1.0 has 5 files of about 16k words (PR #186 table).

The SKILL.md adds: "A plan the model must obey competes with the obligations for attention."

**F1.3 Open defects in driven's gates (external evidence).**
- [Issue #162](https://github.com/tech-leads-club/agent-skills/issues/162) (opened 2026-08-08, still open) reports that two of driven v3.3.0's deterministic gates pass "without inspecting anything":
  - `validate_spec.py` never reads acceptance criteria when the template's own blank line follows the header.
  - `validate_tasks.py`'s forward-dependency check "cannot fail".
  - The reporter's line: "A gate that cannot fail is worse than no gate."
  - An independent confirmation (2026-09-28) found that 0 of 280 ACs in five template-built specs had been read.
- [Issue #176](https://github.com/tech-leads-club/agent-skills/issues/176): `STATE.md` grows without bound because decisions are append-only. A maintainer accepted it, and nothing yet enforces the file's shape.
- [Issue #164](https://github.com/tech-leads-club/agent-skills/issues/164): context accumulates across 100+-task pipelines. It proposes a per-task "Task Packet" context boundary.

**F1.4 Lean is already being dogfooded and amended.** [Issue #191](https://github.com/tech-leads-club/agent-skills/issues/191) (2026-09-12) reports that 13 checks were mapped 1:1 onto 13 agent eval executions. The reporter calls this unnecessarily expensive. A maintainer accepted adding guidance on grouping compatible checks into shared scenarios.

**F1.5 TLC's `.bench/` self-benchmark.** This lives in the private repo `tech-leads-club/fakeflix`, read via `gh`.

Protocol (`.agents/skills/bench-run/SKILL.md`):
- One frozen PRD (Stripe trial lifecycle) and a frozen acceptance-criteria baseline.
- Each arm runs on its own branch off an immutable `bench-base`.
- Models are pinned per role.
- "Produce → Grade communicates ONLY through git", and the evaluator is fresh and read-only.
- The implementer is PRD-blind.
- Every run starts with `scripts/clean-session.sh`, so prior plans and build output cannot leak into the next run.
- Weights are P0=3/P1=2/P2=0, with a 0.6/0.4 implementation/test split.

Results (`bench-results` branch, commits 2026-09-20 to 2026-09-23):

| Campaign | Arm | Mean Final | Mean tokens | Mean charged | Produce wall-clock (2 runs) |
|---|---|---:|---:|---:|---|
| Grok 4.6 high (produce + grade) | tlc-spec-driven | 0.985 | 23.86M* | $14.14* | 48 / 60 min |
| | tlc-spec-lean | **0.995** | 16.58M | $10.52 | 36 / 37 min |
| | superpowers | 0.915 | 15.04M | $8.75 | 23 / 26 min |
| | no-framework | 0.980 | 10.91M | $6.75 | 22 / 24 min |
| Composer 2.5 Fast produce, Grok grade | tlc-spec-driven | 0.935 | 16.30M | $10.98 | 23 / 17 min |
| | tlc-spec-lean | **0.960** | 12.87M | $9.83 | 15 / 16 min |
| | superpowers | 0.775 | 7.88M | $5.74 | 8 / 9 min |
| | no-framework | 0.845 | 6.25M | $4.81 | 5 / 7 min |

\* Driven run 1's plan tokens were not separable.

Wall-clock times are computed from the recorded `T_START`→`T_IMPL_END`.

In the Composer campaign, the gap comes mostly from test quality: mean T is 0.87 for lean, 0.805 for driven and 0.645 for no-framework. The TLC Verifier ran twice (FAIL then PASS) in three of the four TLC runs.

The authors' summary of the Grok campaign: "no-framework matched driven on fidelity at lower token/charged cost. TLC driven was the most expensive produce window."

Benchmark caveats, all stated in RESULTS.md:
- n=2 per arm, one PRD, one codebase.
- Grok round: produce and grade use the same model family.
- Superpowers ran without worktrees or subagent-driven-development.
- The benchmark measures only plan→implement. It has no PR, review or merge stage.
- Spec Kit and OpenSpec were in the original matrix but not in the published 4-arm runs.

**F1.6 TLC is also moving enforcement into hooks.** [`tech-leads-club/harness-toolkit`](https://github.com/tech-leads-club/harness-toolkit) (created 2026-08-05, pushed 2026-09-24) is a hook runtime for Claude Code and Cursor.
- It has 8 unconfigurable "floor" rules, for example denying `git push --force`, secret reads, and writes to the policy surface.
- It has 3 always-on checks.
- It has 24–25 opt-in "rails", including:
  - "Grind": lint and test on stop, sending the agent back until they pass.
  - A "ship gate": a ship claim must have recent PASS evidence.
  - A "plan gate": declared scope is compared with the diff.
  - Operator rules such as "no PR without a review subagent since HEAD".
- Its README states: "If a message on your screen is not from one of the thirty-six rows below, it is not the harness."

A TLC workshop repo ([tlc-floripa-harness-exercises](https://github.com/tech-leads-club/tlc-floripa-harness-exercises)) includes an exercise titled "Harness agressivo demais destrói a capacidade do modelo" ("an overly aggressive harness destroys the model's capability").

### F2. Spec-driven development landscape and critiques

**F2.1 Tools as of 2026-09-30** (GitHub API reads, 2026-09-30):

| Tool | Version | Stars |
|---|---|---:|
| [GitHub Spec Kit](https://github.com/github/spec-kit) | v1.0.13, 2026-09-29 | 139.6k |
| [OpenSpec](https://github.com/Fission-AI/OpenSpec) | v1.14.0 | 70.8k |
| [BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) | v6.12.0 | 53.7k |
| [obra/superpowers](https://github.com/obra/superpowers) | v6.4.2 | 293k |

- **Spec Kit** has reframed itself. Its README now says "Build with a spec, fix a bug, or assess an idea". SDD, bug fixing and idea assessment are "**independent entry points**, not three mandatory phases", and a bug fix runs a separate assess→fix→test flow. The SDD loop now ends with an iterated `implement → converge`.
- **OpenSpec** uses a three-step propose/apply/archive flow with "spec deltas", aimed at brownfield work ([Thoughtworks blip](https://www.thoughtworks.com/en-us/radar/tools/openspec)).

**F2.2 Thoughtworks Technology Radar Vol. 34 (April 2026)** ([techniques](https://www.thoughtworks.com/en-us/radar/techniques)):

| Ring | Entries relevant here |
|---|---|
| Assess | Spec-driven development; [Spec Kit](https://www.thoughtworks.com/en-in/radar/languages-and-frameworks/github-spec-kit); OpenSpec; Ralph loop; Feedback flywheel; Measuring collaboration quality with coding agents; Team of coding agents |
| Caution | Agent instruction bloat; Codebase cognitive debt; Coding throughput as a productivity measure; Coding agent swarms |
| Trial | Feedback sensors for coding agents; Mutation testing; Progressive context disclosure; Agent Skills; Sandboxed execution |
| Adopt | Curated shared instructions; DORA metrics |

- The Spec Kit blip warns about instruction bloat, context rot, verbose markdown that "can create excessive cognitive load during review", and over-defensive checks.
- The OpenSpec blip advises teams to "continue to monitor and revisit native capabilities and re-evaluate the need for SDD tooling" as agents improve.

**F2.3 Böckeler (martinfowler.com, 2025-10-15)** ([SDD tools](https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html)):
- She distinguishes three levels: spec-first, spec-anchored and spec-as-source.
- Kiro turned a small bug into "4 user stories with 16 acceptance criteria", "like using a sledgehammer to crack a nut".
- On review burden: "I'd rather review code than all these markdown files".
- Agents still ignored instructions despite elaborate specs.
- Spec-as-source risks "the downsides of both MDD and LLMs: Inflexibility *and* non-determinism."

**F2.4 Scott Logic, 2025-11-26** ([Spec Kit "reinvented waterfall?"](https://blog.scottlogic.com/2025/11/26/putting-spec-kit-through-its-paces-radical-idea-or-reinvented-waterfall.html)):
- Spec Kit: 33.5 min of agent time plus about 3.5 h of review for one increment, 2,577 lines of markdown, and one obvious bug.
- Iterative prompting: 8 min of agent time, 15 min of review and 9 min of testing, with no bugs found.
- Conclusion: "The fastest path is still iterative prompting and review, not industrialised specification pipelines."
- Caveat: n=1, and the feature was small.

**F2.5 Evidence for SDD.**
- The Uvik "SDD Benchmark 2026" reports 50 Python tickets, five arms including a control, blind review, OpenSpec 84% merge vs control 72%, and 0.46 vs 0.86 defects per merged ticket ([Uvik](https://uvik.net/spec-driven-development-benchmark/)).
  - **Credibility flag:** the page metadata says it was published 2026-09-24, yet it states "Run: Q4 2026, October 15, 2026", a date in the future. The vendor also sells SDD services. Treat as *[unverified]*.
- An arXiv process taxonomy of Spec Kit, BMAD, OpenSpec, GSD and others ([2606.04967](https://arxiv.org/pdf/2606.04967), 2026-06-04) finds gaps between the verification claims frameworks make and what they actually implement. It also notes that no benchmark covers the full SDD process.
- [SlopCodeBench](https://arxiv.org/abs/2603.24755) (2026-03 to 05) measured how agent code degrades across iterative, spec-evolving checkpoints:
  - Structural erosion rose in 77% of trajectories.
  - Explicit quality guidance "reduces initial verbosity and erosion by up to a third, without affecting degradation rates".

**F2.6 Where human review pays off.** HumanLayer's ACE-FCA argues that review effort pays off most upstream: "a bad line of a **plan** could lead to hundreds of bad lines of code. And a bad line of **research** … thousands", and "I can't read 2000 lines of golang daily. But I *can* read 200 lines of a well-written implementation plan" ([ace-fca.md](https://github.com/humanlayer/advanced-context-engineering-for-coding-agents/blob/main/ace-fca.md), 2025).

**F2.7 Harness components date as models improve.** Anthropic's [harness design for long-running apps](https://www.anthropic.com/engineering/harness-design-long-running-apps) (2026-03-24) used a planner/generator/evaluator harness with negotiated "sprint contracts".
- When moving to Opus 4.6, "the sprint construct was eliminated entirely".
- The principle stated: "every component in a harness encodes an assumption about what the model can't do on its own, and those assumptions are worth stress testing."
- Cost reported: a solo run took 20 min and cost $9; the full harness took 6 h and cost $200 on the same task, with better quality.

**F2.8 Böckeler, "TDD inside the agent loop — theater or actual value?" (2026-08-10)** ([article](https://martinfowler.com/articles/exploring-gen-ai/tdd-in-the-agent-loop.html)):
- Across three greenfield tasks judged blind, TDD-in-loop showed "no clearly discernable difference" in quality and no mutation-score advantage.
- Tokens were 3–4× higher.
- Her root-cause analysis: non-TDD runs did upfront design, while TDD's design "emerged from the sum of many locally-minimal decisions and was rarely revisited".
- She now recommends mutation testing and static analysis instead of instructing agents to do TDD.
- Kent Beck's counter-position: TDD is a "superpower" with agents, and agents delete or disable tests to "pass" ([Augmented Coding](https://newsletter.kentbeck.com/p/augmented-coding-beyond-the-vibes)).

### F3. Vendor and practitioner harness guidance

**F3.1 Anthropic Claude Code best practices** ([docs](https://code.claude.com/docs/en/best-practices), accessed 2026-09-30):

*Context is the constraint.*
- "performance degrades as it fills".

*Verification.*
- "Give Claude a check it can run."
- There are four escalating ways to gate the stop:
  - in the prompt;
  - a `/goal` condition, re-checked by a separate evaluator after every turn;
  - a **Stop hook as a deterministic gate**;
  - a verification subagent or dynamic workflow, "so the agent doing the work isn't the one grading it."

*Planning.*
- "Plan mode is useful, but also adds overhead … If you could describe the diff in one sentence, skip the plan."

*Specs.*
- For larger features, Claude interviews you and writes `SPEC.md`, then a fresh session executes it.
- "The most useful specs are self-contained: they name the files and interfaces involved, state what is out of scope, and end with an end-to-end verification step."

*CLAUDE.md.*
- "For each line, ask: *'Would removing this cause Claude to make mistakes?'* If not, cut it. Bloated CLAUDE.md files cause Claude to ignore your actual instructions!"
- Failure pattern "over-specified CLAUDE.md". Fix: "If Claude already does something correctly without the instruction, delete it or convert it to a hook."

*Adversarial review.*
- "A reviewer prompted to find gaps will usually report some, even when the work is sound … Chasing every finding leads to over-engineering … Tell the reviewer to flag only gaps that affect correctness or the stated requirements."

**F3.2 Anthropic, "Extend Claude Code"** ([features overview](https://code.claude.com/docs/en/features-overview)):
- Keep CLAUDE.md under 200 lines.
- Skills load their descriptions every session and their full content on use. `disable-model-invocation: true` gives zero context cost until invoked, and is recommended for skills with side effects.
- "Put guardrails in hooks … a request, not a guarantee. A `PreToolUse` hook that blocks the edit is enforcement."
- It gives a trigger table for adding features incrementally, for example "Claude gets a convention or command wrong twice → CLAUDE.md".
- **Dynamic workflows** ([docs](https://code.claude.com/docs/en/workflows)) move the orchestration plan into a rerunnable JS script with phases, adversarial cross-checks and resumability. Runs are capped at 16 concurrent and 1,000 total agents. The docs give "a review you run on every branch" as a save-and-reuse example.

**F3.3 Anthropic review and automation features (as of 2026-09-30).**
- [`/code-review`](https://code.claude.com/docs/en/code-review) reviews the local diff in a background subagent. It takes effort levels: low and medium report only high-confidence findings. It has `--fix` and `--comment` flags and an `ultra` cloud review.
- The managed GitHub **Code Review** (research preview, Team/Enterprise):
  - runs a fleet of agents plus a verification step "to filter out false positives";
  - posts severity-tagged inline comments with a neutral check that never blocks merge;
  - is tuned via `REVIEW.md`, including nit caps and "after the first review, suppress new nits";
  - costs "$15-25" on average per review.
  - **Findings are dismissed by resolving threads**: "To dismiss a finding without a code change, resolve its thread."
- [Routines](https://code.claude.com/docs/en/routines) (research preview) run cloud Claude Code sessions on a schedule (minimum 1 h), via an API, or on GitHub PR or release events.
- Per the best-practices page, auto mode, a classifier-gated permission mode, is the default starting mode from v2.1.283.

**F3.4 Anthropic on long-running agents** ([effective harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents), 2025-11-26):
- An initializer agent writes `init.sh`, a progress file and a JSON feature list with pass/fail status.
- Coding sessions read the progress notes and git log, run a smoke test, then do "**one feature at a time** … critical".
- They commit with descriptive messages and update the progress file.
- [Context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) (2025-09-29): "the smallest possible set of high-signal tokens"; just-in-time retrieval; structured note-taking; subagents that return 1–2k-token summaries.

**F3.5 OpenAI "Harness engineering" (Feb 2026; primary page 403, content from secondary sources).** Sources: [InfoQ](https://www.infoq.com/news/2026/02/openai-harness-engineering-codex), [summary](https://alexlavaee.me/blog/openai-agent-first-codebase-learnings/).
- Three engineers produced about 1,500 merged PRs and about 1M lines of code over 5 months, with no hand-written code.
- AGENTS.md is "~100 lines, pointers only"; `docs/` (design docs, exec plans, product specs) is the system of record.
- Layer boundaries are enforced by custom linters and structural tests whose error messages embed the remedy.
- Recurring "garbage collection" encodes "golden principles".
- Agents read logs, metrics and spans from per-worktree app instances.
- On review and merge, via secondary sources: "corrections are cheap, and waiting is expensive", "minimal blocking merge gates", "short-lived" PRs, and flakes handled with re-runs *[secondary]*.

**F3.6 Böckeler, "Harness engineering for coding agent users" (2026-04-02)** ([article](https://martinfowler.com/articles/harness-engineering.html)):
- Guides are feedforward controls; sensors are feedback controls. Computational controls (tests, linters, types) are distinguished from inferential ones (LLM review).
- Harness categories: maintainability, architecture fitness and behaviour; she calls behaviour the least mature.
- Practices: "keep quality left" and "harnessability".
- "A good harness should not necessarily aim to fully eliminate human input, but to direct it to where our input is most important."

**F3.7 Practitioners.**
- **Hashimoto** (2026-02-05, [AI adoption journey](https://mitchellh.com/writing/my-ai-adoption-journey)): "Engineer the harness" means that each AGENTS.md line comes from an observed bad behaviour ("it almost completely resolved them all"), plus scripts for verification. He runs a single background agent, not parallel fleets.
- **Huntley's Ralph** (2025-07-14, [ghuntley.com/ralph](https://ghuntley.com/ralph/)) uses `while :; do cat PROMPT.md | claude-code; done`, specs plus `fix_plan.md`, one item per loop, and tests and types as "backpressure". "There's no way in heck would I use Ralph in an existing code base." The Thoughtworks Radar puts it at *Assess* and notes significant token cost per iteration.
- **Ronacher**, "Astra" (2026-09-07, [lucumr](https://lucumr.pocoo.org/2026/9/7/astra-why/)): a fully autonomous weekend run consumed about 4B tokens over 35 h, cost about $1,200, and produced 75k lines of code in 79 commits with "no deliverable value". Vague goals plus unbounded autonomy led to local optimisation. His [Pi](https://lucumr.pocoo.org/2026/1/31/pi/) philosophy: minimal tools and prompt, no plan mode, self-written extensions.
- **Willison** ([Agentic Engineering Patterns](https://simonwillison.net/guides/agentic-engineering-patterns/), 2026):
  - "Don't file pull requests with code you haven't reviewed yourself"; "Several small PRs beats one big one"; "Agents write convincing looking pull request descriptions. You need to review these too!" ([anti-patterns](https://simonwillison.net/guides/agentic-engineering-patterns/anti-patterns/)).
  - "First run the tests" ([chapter](https://simonwillison.net/guides/agentic-engineering-patterns/first-run-the-tests/)).
  - He trusts agent-written commit messages and treats history as an authored narrative ([git chapter](https://simonwillison.net/guides/agentic-engineering-patterns/using-git-with-coding-agents/)).
- **Kent Beck** ([Augmented Coding](https://newsletter.kentbeck.com/p/augmented-coding-beyond-the-vibes)) lists warning signs: loops, unrequested features, tests disabled or deleted. His rules: TDD, separate structural from behavioural commits, and commit only when green.

**F3.8 Deterministic gates versus prose rules: evidence.**
- [Stripe, "You can't whisper at an AI agent"](https://stripe.dev/blog/ai-steering-experiments) (2026-05-14): "Hard steers, such as errors, explicit instructions in loaded context, and blocking responses, work. Soft steers — warnings, hints, adjacent files, in-band suggestions — often don't."
- [arXiv 2608.23550](https://arxiv.org/abs/2608.23550) (2026-08-24): across 481 CLAUDE.md files, only about 4–16% of security rules had a matching built-in control.
- [ETH Zurich, arXiv 2602.11988](https://arxiv.org/abs/2602.11988) (final version 2026-09-29): context files "do not generally improve task success rates" and add over 20% inference cost. This holds across agents and for both LLM-generated and developer-written files.

**F3.9 marmelab, "State of AI Harness Engineering 2026"** (2026-09-24, [post](https://marmelab.com/blog/2026/09/24/the-state-of-ai-harness-engineering-2026.html)) audited 246 harness repos and 57 publications:
- 60% of harnesses have neither tests nor evals.
- Only 5 of 391 repos record harness usage.
- "Controls exist to fix model weaknesses; when weaknesses disappear, controls become pure cost." It recommends documenting the incident each control prevents.
- Multi-agent caveats it cites:
  - adding a reviewer agent cut success by 8% on one benchmark;
  - Microsoft reported that ">4 handoffs almost always failed";
  - four-role teams scored 72.2% versus 71.8% for the best single agent.
  - These figures are *[unverified, secondary]*.
- Ralph-style fresh-context loops "rely on one toy run, no baseline".

### F4. Agent-ready repositories

- **Stripe Minions** ([part 2](https://www.engineering.fyi/article/minions-stripe-s-one-shot-end-to-end-coding-agents-part-2), mirror of Stripe's post): about 1,000–1,300 PRs per week with mandatory human review.
  - "Blueprints" mix deterministic nodes with agent loops.
  - Lint and a subset of tests run locally first to "shift left", with about 2 CI rounds before merge.
  - Pre-warmed isolated devboxes start in under 10 s *[secondary]*.
  - Rule files are scoped.
- **Factory "Agent Readiness"** (2026-01-20, [post](https://factory.com/news/agent-readiness)) defines 8 pillars: style/validation, build, testing, docs, dev environment, code quality, observability and security. It has 5 levels, with Level 3 as the production target, and argues "The agent is not broken. The environment is." It publishes no outcome data.
- **Thoughtworks Trial blips**: feedback sensors (compilers, linters, structural tests wired into the loop); mutation testing (against "perpetually green" AI tests); sandboxed execution via dev containers or microVMs. *Assess*: architecture drift reduction with LLMs, combining ArchUnit-style tools with LLM fixes as "garbage collection" ([radar](https://www.thoughtworks.com/en-us/radar/techniques)).
- **OpenAI** (F3.5): an app that boots per worktree, plus telemetry the agent can read, plus lint errors that carry remediation text.
- **marmelab**: test harnesses that start in under 1 s; converting passing checks into cheap smoke scripts.

### F5. PR and commit practice with agents

- **PR size.** Agentic-PR mining finds that merge odds fall about 1% per extra LOC unit and that chores merge more often than features (84% vs 66%) (arXiv [2509.14745](https://arxiv.org/abs/2509.14745), [2602.08915](https://arxiv.org/html/2602.08915v2); *[search-snippet level]*). Willison: several small PRs beat one big one.
- **Review capacity is the bottleneck.** He et al. ([arXiv 2607.01904](https://arxiv.org/html/2607.01904v1), 2026-07-02) studied an enterprise "2×" mandate:
  - Throughput reached 2.09×.
  - The share of PRs with any human review fell from 89% to 68%, while automated review rose from about 19% to about 84%.
  - AI PRs were larger, and time from first review to merge grew 20%.
  - Merge and revert rates stayed flat; the authors call these "coarse".
- **Review-bot comment volume hurts.** Fatima et al. ([arXiv 2604.24450](https://arxiv.org/html/2604.24450v1), 2026-08-24) studied 7,416 bot comments on 4,532 agentic PRs:
  - More bot comments correlate with slower resolution (ρ=0.19).
  - Volume dilutes relevance and clarity.
  - Efficiency was "driven primarily by comment quantity rather than feedback quality".
- **Stacked PRs.** GitHub launched native stacked PRs (`gh stack`) in public preview on 2026-07-30, with agent skill support ([secondary coverage](https://explainx.ai/blog/github-stacked-pull-requests-public-preview-july-2026); *[not verified against GitHub's changelog]*).
- **Merge philosophy** splits by throughput. OpenAI runs minimal blocking gates and quick post-merge corrections; Stripe and Atomic CRM keep mandatory human review (marmelab, F3.9).
- **Comment hygiene.** I found no external guidance recommending *deletion* of review comments. Vendor tooling resolves threads and keeps them as an audit trail (F3.3).
- **Solo work.** I found no primary source that addresses trunk-based development versus PR-per-feature for solo developers using agents. Treat this as a coverage gap.

### F6. Evaluating a harness

- **Anthropic** ([demystifying evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents), 2026-01-09):
  - Start with 20–50 tasks drawn from real failures.
  - Use code, model and human graders.
  - "Read the transcripts".
  - Report pass^k (all k runs succeed), not only pass@k, when consistency matters.
  - Isolate trials so state cannot leak between them.
- **Thoughtworks.** *Caution* on throughput metrics; it prefers **first-pass acceptance rate**, iteration cycles, post-merge rework, failed builds and review burden ("Measuring collaboration quality", *Assess*). DORA metrics are *Adopt*.
- **Harness effect size.** marmelab cites 68–88% success for the same model across 8 harnesses *[secondary]*. A contamination-controlled paired study ([arXiv 2609.11987](https://arxiv.org/html/2609.11987v1), 2026-09-08, single author, 256 tasks) found no resolvable average solve-rate difference between native and neutral harnesses (95% CI about ±7–9 pp). It did find a 1.2–1.6× cost-per-solve difference, and opposite effects by task type.
- **Perception gap.** In METR's 2025 RCT (16 developers, 246 issues), developers were 19% slower with AI but believed they were 20% faster ([METR](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/)). METR has since flagged these results as outdated (Feb 2026 update).
- **TLC's fakeflix bench (F1.5)** is the closest worked example of a frozen-task A/B for *spec frameworks*:
  - an immutable base branch;
  - a frozen acceptance baseline;
  - pinned models;
  - a git-only handoff to a fresh read-only grader;
  - k=3 grading;
  - token and charge capture per window.

## Implications for Learny

These are inputs for `synthesis.md`, not decisions. Confidence reflects the external evidence only, not Learny's internal data, which is RQ03.

1. **Evaluate replacing `tlc-spec-driven` with `tlc-spec-lean` as the per-cycle core.** Confidence: **Medium**.
   - Why recommend:
     - TLC's own authors deprecate driven's task choreography, component catalogue and auto-sizing as "babysitting" (F1.2).
     - Their bench shows equal-or-better fidelity at about 10–30% fewer tokens and about 25–40% less produce wall-clock (F1.5).
     - Driven's gates have open "cannot fail" defects (F1.3).
     - Lean keeps the parts that external evidence supports: independent verifier, EARS checks, script gates.
   - Why not:
     - n=2 on one Node PRD, no review or merge stage, and partly same-family grading.
     - Lean is 3 weeks old (v1.1.0) and already has accepted amendments (F1.4).
     - Learny's ship-cycle, finalize and lessons tooling is wired to driven's artifact names, so migration has a cost.
2. **Scale the ceremony to the change. Do not run the full cycle for one-sentence diffs.** Confidence: **High**.
   - Why recommend:
     - Anthropic: "If you could describe the diff in one sentence, skip the plan" (F3.1).
     - Spec Kit now separates bug-fix and assessment flows from SDD (F2.1).
     - Böckeler's "sledgehammer" and Scott Logic's roughly 10× overhead come from running full SDD on small work (F2.3, F2.4).
   - Why not:
     - Lean explicitly removed *self*-sizing because "the model sized itself and skipped phases" (F1.2).
     - Sizing therefore needs a human or rule-based trigger, not model judgement.
3. **Move "must always happen" rules from CLAUDE.md and skill prose into hooks and CI gates (Stop-hook test gate, PreToolUse denies, architecture fitness tests).** Confidence: **High**.
   - Why recommend:
     - Stripe's hard-vs-soft steering result (F3.8), 4–16% rule-to-control coverage (F3.8), and Anthropic's "request, not a guarantee" (F3.2).
     - Thoughtworks *Trial* "feedback sensors" (F4).
     - TLC itself is shipping harness-toolkit (F1.6).
   - Why not:
     - Hooks need their own tests, both should-fire and should-not-fire; 60% of harnesses have none (F3.9).
     - Over-aggressive gating degrades the model (TLC exercise 06, F1.6).
     - Learny already has `make lint` boundaries, so the marginal gain may be small.
4. **Keep CLAUDE.md as a short, pointer-only map, and prune by "would removing this cause a mistake?".** Confidence: **High**.
   - Why recommend:
     - Anthropic recommends under 200 lines (F3.1, F3.2); OpenAI uses about 100 lines (F3.5).
     - Thoughtworks *Caution* on instruction bloat (F2.2).
     - ETH Zurich found no success gain and +20% cost from context files (F3.8).
   - Why not:
     - Learny's CLAUDE.md doubles as a portfolio orientation document for humans.
     - The ETH result measures task success, not onboarding or presentation value.
5. **Make the review step verify before it reports, cap findings at correctness, and resolve rather than delete.** Confidence: **Medium**.
   - Why recommend:
     - Anthropic warns that gap-hunting reviewers manufacture findings (F3.1); its managed review adds a verification step and nit caps (F3.3).
     - Bot-comment volume correlates with slower resolution (F5).
     - Resolved threads keep the audit trail that deletion destroys (F3.3, F5).
   - Why not:
     - A solo portfolio repo may value a clean PR page over an audit trail.
     - The managed Code Review costs $15–25 per review and is Team/Enterprise only. Local `/code-review` is the cheaper equivalent.
6. **Treat the harness as a product with a frozen-task A/B before and after any big change, and track first-pass acceptance and interventions per PR.** Confidence: **Medium**.
   - Why recommend:
     - Anthropic eval guidance (F6).
     - The TLC bench gives a ready-made protocol (F1.5).
     - Thoughtworks recommends first-pass acceptance over throughput (F2.2).
     - Perception is unreliable (METR, F6).
   - Why not:
     - Each arm-run costs about $5–15 in tokens plus wall-clock time (F1.5).
     - At Learny's PR volume (single digits per month), statistical power is low, so qualitative transcript review may give more per dollar.
7. **Prefer a deterministic orchestrator for the outer loop (plan→build→PR→review→merge): saved workflow or script steps for the fixed parts, agent nodes only where judgement is needed.** Confidence: **Low–Medium**.
   - Why recommend:
     - Stripe's blueprints mix deterministic and agent nodes (F4).
     - Claude Code dynamic workflows are rerunnable and resumable (F3.2).
     - Anthropic's verifier-separate-from-author guidance (F3.1).
   - Why not:
     - Multi-agent pipelines often underperform single agents (F3.9, secondary).
     - Workflows allow no mid-run user input, but Learny's gated merge needs a human checkpoint.
     - Learny's ship-cycle skill already works; a rewrite risks churn without measured gain.
8. **Re-justify each harness component against the model generation it was built for, and record the incident each control prevents.** Confidence: **Medium**.
   - Why recommend:
     - Anthropic dropped sprints at Opus 4.6 (F2.7).
     - Thoughtworks says to re-evaluate SDD tooling as models improve (F2.2).
     - marmelab's "controls become pure cost" (F3.9).
     - Hashimoto ties every rule to an observed failure (F3.7).
   - Why not: removing a control is cheap to do and expensive to discover was needed. It needs the evaluation in item 6 first.

## Limitations

- **Primary sources missed.** OpenAI's harness-engineering post returned 403, so it is reconstructed from secondary sources. The original Stripe Minions post and GitHub's stacked-PR changelog were read only through mirrors and secondary coverage.
- **Private data.** The fakeflix benchmark is in a private repo. Its n=2 per arm, single PRD, Cursor-hosted models and missing review/merge stage limit how far it transfers to Learny's Claude Code plus GitHub PR loop.
- **Fetch summarization.** WebFetch outputs are summarized by a model. Verbatim quotes may carry minor paraphrase; numeric claims were spot-checked where a second source existed. One summarized model detail in Böckeler's TDD article seemed inconsistent, so it is omitted.
- **Uvik dating.** The Uvik benchmark has an internally impossible date and is treated as unverified.
- **No solo-developer evidence.** I found no rigorous external evidence on trunk-based versus PR-per-feature for solo developers with agents, or on optimal commit granularity with agents (Beck and Willison are opinion).
- **Secondary statistics.** Several statistics (multi-agent handoff failures, the "+8% reviewer harms", the 68–88% harness spread) come via marmelab's synthesis, not their primary papers.
- **Training-knowledge cutoff.** My training knowledge ends before some of these sources were published. Everything time-sensitive above was taken from fetched pages dated as stated.

## Sources

All accessed 2026-09-30.

### Cited (50)

TLC / tlc-spec-lean
1. tech-leads-club/agent-skills releases — https://github.com/tech-leads-club/agent-skills/releases
2. PR #186 "add tlc-spec-lean" (2026-09-09) — https://github.com/tech-leads-club/agent-skills/pull/186
3. PR #205 "tlc-spec-lean 1.1.0" (2026-09-18) — https://github.com/tech-leads-club/agent-skills/pull/205
4. tlc-spec-lean skill page — https://agent-skills.techleads.club/skills/tlc-spec-lean/
5. tlc-spec-lean SKILL.md — https://github.com/tech-leads-club/agent-skills/tree/main/packages/skills-catalog/skills/(development)/tlc-spec-lean
6. Issue #162 (driven gates cannot fail) — https://github.com/tech-leads-club/agent-skills/issues/162
7. Issue #164 (context boundaries) — https://github.com/tech-leads-club/agent-skills/issues/164
8. Issue #176 (STATE.md growth) — https://github.com/tech-leads-club/agent-skills/issues/176
9. Issue #191 (lean checks vs eval scenarios) — https://github.com/tech-leads-club/agent-skills/issues/191
10. fakeflix `bench-run` skill (private) — github.com/tech-leads-club/fakeflix `.agents/skills/bench-run/SKILL.md`
11. fakeflix RESULTS.md and RESULTS-composer-2.5.md (private, `bench-results` branch) — github.com/tech-leads-club/fakeflix
12. harness-toolkit README — https://github.com/tech-leads-club/harness-toolkit
13. tlc-floripa-harness-exercises README — https://github.com/tech-leads-club/tlc-floripa-harness-exercises

SDD landscape
14. GitHub Spec Kit README — https://github.com/github/spec-kit
15. OpenSpec repo — https://github.com/Fission-AI/OpenSpec
16. BMAD-METHOD repo — https://github.com/bmad-code-org/BMAD-METHOD
17. obra/superpowers repo — https://github.com/obra/superpowers
18. Böckeler, Understanding SDD (2025-10-15) — https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html
19. Scott Logic, Spec Kit (2025-11-26) — https://blog.scottlogic.com/2025/11/26/putting-spec-kit-through-its-paces-radical-idea-or-reinvented-waterfall.html
20. Uvik SDD benchmark (unverified) — https://uvik.net/spec-driven-development-benchmark/
21. Thoughtworks Radar Vol. 34 techniques — https://www.thoughtworks.com/en-us/radar/techniques
22. Thoughtworks OpenSpec blip — https://www.thoughtworks.com/en-us/radar/tools/openspec
23. Thoughtworks Spec Kit blip — https://www.thoughtworks.com/en-in/radar/languages-and-frameworks/github-spec-kit
24. arXiv 2606.04967 process taxonomy — https://arxiv.org/pdf/2606.04967
25. arXiv 2603.24755 SlopCodeBench — https://arxiv.org/abs/2603.24755
26. HumanLayer ACE-FCA — https://github.com/humanlayer/advanced-context-engineering-for-coding-agents/blob/main/ace-fca.md

Vendor and practitioner harness guidance
27. Claude Code best practices — https://code.claude.com/docs/en/best-practices
28. Claude Code, Extend Claude Code — https://code.claude.com/docs/en/features-overview
29. Claude Code dynamic workflows — https://code.claude.com/docs/en/workflows
30. Claude Code Code Review — https://code.claude.com/docs/en/code-review
31. Claude Code routines — https://code.claude.com/docs/en/routines
32. Anthropic, Effective harnesses for long-running agents (2025-11-26) — https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
33. Anthropic, Effective context engineering (2025-09-29) — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
34. Anthropic, Harness design for long-running apps (2026-03-24) — https://www.anthropic.com/engineering/harness-design-long-running-apps
35. Anthropic, Demystifying evals (2026-01-09) — https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
36. InfoQ on OpenAI harness engineering — https://www.infoq.com/news/2026/02/openai-harness-engineering-codex
37. Summary of OpenAI harness engineering — https://alexlavaee.me/blog/openai-agent-first-codebase-learnings/
38. marmelab, State of AI Harness Engineering 2026 — https://marmelab.com/blog/2026/09/24/the-state-of-ai-harness-engineering-2026.html
39. Böckeler, Harness engineering for coding agent users (2026-04-02) — https://martinfowler.com/articles/harness-engineering.html
40. Böckeler, TDD inside the agent loop (2026-08-10) — https://martinfowler.com/articles/exploring-gen-ai/tdd-in-the-agent-loop.html
41. Hashimoto, My AI adoption journey (2026-02-05) — https://mitchellh.com/writing/my-ai-adoption-journey
42. Huntley, Ralph (2025-07-14) — https://ghuntley.com/ralph/
43. Ronacher, Astra (2026-09-07) — https://lucumr.pocoo.org/2026/9/7/astra-why/
44. Ronacher, Pi (2026-01-31) — https://lucumr.pocoo.org/2026/1/31/pi/
45. Willison, Agentic Engineering Patterns (index, anti-patterns, git, first-run-the-tests) — https://simonwillison.net/guides/agentic-engineering-patterns/
46. Kent Beck, Augmented Coding — https://newsletter.kentbeck.com/p/augmented-coding-beyond-the-vibes
47. Stripe, You can't whisper at an AI agent (2026-05-14) — https://stripe.dev/blog/ai-steering-experiments
48. arXiv 2608.23550 "When 'do not' is not deny"; arXiv 2602.11988 "Evaluating AGENTS.md" — https://arxiv.org/abs/2608.23550 , https://arxiv.org/abs/2602.11988

Agent-ready repos, PRs, evaluation
49. Stripe Minions part 2 (mirror) — https://www.engineering.fyi/article/minions-stripe-s-one-shot-end-to-end-coding-agents-part-2 ; Factory Agent Readiness (2026-01-20) — https://factory.com/news/agent-readiness
50. arXiv 2607.01904 (2× mandate), arXiv 2604.24450 (reviewer bots), arXiv 2609.11987 (harness or model), METR 2025 RCT — https://arxiv.org/html/2607.01904v1 , https://arxiv.org/html/2604.24450v1 , https://arxiv.org/html/2609.11987v1 , https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/

### Consulted, not cited separately (13)

- https://openai.com/index/harness-engineering/ (HTTP 403)
- tech-leads-club/agent-skills README — https://github.com/tech-leads-club/agent-skills
- tlc-spec-driven skill page — https://agent-skills.techleads.club/skills/tlc-spec-driven/
- martinfowler.com Exploring Gen AI index — https://martinfowler.com/articles/exploring-gen-ai.html
- arXiv 2509.14745 and 2602.08915 (agentic PR merge studies; search-snippet level only)
- GitHub stacked PRs coverage — https://explainx.ai/blog/github-stacked-pull-requests-public-preview-july-2026 (secondary)
- Claude Code `/goal` docs and coverage — https://code.claude.com/docs/en/goal (via search results)
- Stripe Minions search coverage (topaiproduct, mindstudio)
- Ralph coverage (codecentric, Tessl blog) via search
- METR follow-up coverage (jasonmoon.dev, valueaddvc) — conflicting secondary claims, not used
- Armin Ronacher 2025 "Agentic Coding Recommendations" — https://lucumr.pocoo.org/2025/6/12/agentic-coding/ (via search snippet)
- Factory docs, Agent Readiness overview — https://docs.factory.ai/agent-readiness/overview (via search)
- ai-boost/awesome-harness-engineering — https://github.com/ai-boost/awesome-harness-engineering (via search)
