---
id: rq04-local-research-and-tlc
title: What the owner's local research already concludes about harnesses, and tlc-spec-driven vs tlc-spec-lean for Learny
question: "What do ~/projects/*-research and shared-skills already conclude about AI harnesses, delivery loops, skills, CI and PR practice, and what exactly does tlc-spec-lean change relative to tlc-spec-driven, including the cost of moving Learny's ship-cycle onto it?"
date: 2026-09-30
status: final
overall_confidence: medium
---

# RQ04: Local research on harnesses, and tlc-spec-driven vs tlc-spec-lean

## TL;DR

- **The owner left `tlc-spec-driven` everywhere but Learny.** Sessions 15–30 Sep: lean 30 across five repos, driven 3. Fala research recommends lean outright; workA round 4 deleted its driven copies and dropped plan-structure gates and lessons on usage evidence.
- **The lessons layer never promoted a lesson anywhere:** Learny 9/0 across 50 features, tally 5/0, Houston 4/0, workA 7/0.
- **Prior research already measured Learny's PRs:** median 4,540 lines, 0/30 formal reviews, merge commits, 60 AI trailers despite the rule. Causes: "PR = cycle" and prose-only rules.
- **Lean keeps the obligations** (EARS, nine dimensions, proofs, independent Verifier). It drops tasks, the component catalogue, per-task adequacy tables and up to five human stops. Its default `light` profile also drops fault injection.
- **Learny's vendored copy is stale:** v3.1.0, two local edits, no validators; this session lists user-level v3.3.0.
- **Verdict:** lean fits v8 better if Learny pins profile `standard` and `learny-ship-cycle` decides what replaces lean's single human plan gate. Confidence: Medium.

## Method

- **Part A (local research).** I listed all 11 folders in the brief (structure plus README or synthesis), then read in depth only the files about harnesses, workflows, delivery, skills, CI or evaluation:
  - `houston-harness-research`: README, research/02, 03, 04, 06 §1–2, 07, 08, the benchmark README, `.specs/` artifacts and the handoff (about 2,100 lines).
  - `fala-research`: research/10 in full, research/12 §0–8 (summary, local-projects table, lessons, tools, the "not adopted" table), decisions-log, two handoffs (about 1,400 lines).
  - `tally-research`: rq03, the harness half of rq04, the synthesis, and the transfer-foundation `STATE.md`, `LESSONS.md` and `AI_STRATEGY.md` head.
  - `houston-roadmap-research`: README and research/04. I also re-aggregated per-project skill use from `scripts/out/fresh_sessions.json` with python3.
  - `houston-session-research`: README, plus the skills section and the voice-note appendix of the idea document.
  - `kappy-research`: README and grep hits from rq04.
  - `desafio-aurora-research`: research/05.
  - `shared-skills`: README.
  - Skimmed and skipped as product-only content: `houston-keyboard-research`, the `houston-resume-research` research files (I used only its `.specs` line counts), `hr-research` (product research containing employer-private passages), `kappy-research` rq01–03, `desafio-aurora` 00–04 and 06–07, fala 01–09 and 11, the fala benchmarks, and the tally Hyperf/hiring rq01–02.
  - Learny context (allowed): `docs/research/2026-06-27/project-workflow-conventions.md` and `agent-skills-source.md`.
- **Part B (skills).** I read in full:
  - `~/.claude/skills/tlc-spec-driven/`: SKILL.md and all 12 references; script docstrings.
  - `~/.claude/skills/tlc-spec-lean/`: SKILL.md, all 5 references, the fixtures, and script docstrings plus the feature-resolution code.
  - I diffed the shared scripts (`lessons.py`, `check_commit.py`) between the two skills.
  - I diffed Learny's vendored `.claude/skills/tlc-spec-driven/` against the user-level copy and read its git history.
  - I read `learny-ship-cycle/SKILL.md` in full. I grepped `pr-review`, `learny-finalize`, `SKILLS.md` and `.claude/skills/README.md` for coupling to tlc artifacts.
- **Measurements.**
  - Line counts for every Learny `.specs/features/*/*.md` (50 features), computed with python3.
  - Line counts for the tally (driven) artifacts and two Houston lean artifact sets.
  - I ran `selftest.py` from tlc-spec-lean and got 46 mutants killed, controls ok, baseline clean.
  - I ran `validate_verification.py`, `validate_plan.py` and `lessons.py status` against Learny read-only with `--root`. Afterwards `git status` was unchanged.
- **User-level config.** I summarised `~/.claude/settings.json` with secrets redacted, the `~/.claude/skills` listing and `~/.claude/plugins` names.
- **Not used:** no Claude transcripts and no web. The skill files contain no URL to the skill's own upstream path (only the author org), so I did not check upstream versions. That is rq05's job.

## Findings

### A. What the local research already concludes

#### A1. Folder inventory

| Folder (date) | Harness relevance | Read |
|---|---|---|
| `houston-harness-research` (2026-09-27) | **High.** Reconstructs 5 workA harness rounds, surveys harness-review tooling, includes a measured benchmark, and a spike built with `tlc-spec-lean` | In depth |
| `fala-research` (2026-09-26..29) | **High.** research/10 covers documentation and planning for one person plus an agent, including tlc-driven vs tlc-lean. research/12 covers commit/PR conventions and measures Learny | 10, 12, decisions, handoffs |
| `houston-roadmap-research` (2026-09-30) | **Medium.** Usage evidence for 304 sessions from 15–30 Sep, including skill counts | README, 04, raw JSON |
| `houston-session-research` (2026-09-07) | **Medium.** 310 sessions; the "pipeline of sessions" thesis; skill usage by role | README, idea §6 and appendix |
| `tally-research` (2026-08-02/03) | **Medium.** Harness lineage learny→drover→herald, one driven cycle archived, skill-shape research | rq03, rq04 §2–3, synthesis, specs |
| `kappy-research` (2026-08-08) | Low. Restates the lineage; "Workflow: RESEARCH → ADR/RFC → tlc-spec-driven → IMPLEMENT → PR" | README, rq04 grep |
| `desafio-aurora-research` (2026-09-26) | Low. One-off PR delivery pattern, `AI-LOG.md`, "setup decorativo é pior que nenhum" | 05 |
| `houston-resume-research`, `houston-keyboard-research` | Product. They only show that lean was used for Houston PRs | Skipped (line counts only) |
| `hr-research` | Product, partly employer-private | Skipped |
| `shared-skills` | One skill (LinkedIn writer); no harness content | README |

#### A2. Conclusions already reached

**1. Harness work runs in "rounds", and the method is mature but manual.**
- `houston-harness-research/research/02-precedente-workA.md` reconstructs five workA rounds between July and September. Each follows the same shape: transcript digest, counting recurrences, cross-checking against SKILL.md, `grilling` to a provenance-tagged `decisions.md`, then one PR.
- Every round's decision document schedules a re-measurement "in ~30 days", and "none has happened yet as a standalone event" (§(a)).
- The manual round of 17 Sep cost US$ 38. The round of 19–20 Sep cost US$ 112 with three Fable subagents (§(e)4).

**2. There is one measured harness evaluation, and it was cheap.**
- `houston-harness-research/research/08-validacao-spike.md` replays the manual workA round of 17 Sep with a deterministic digest plus one agent run.
- The blind run found 13/17 items (76%), invented nothing, took 13.3 min and cost US$ 6.40–7.89 at API prices. The operator triaged its 12 findings in under 20 minutes.
- A second blind window measured the effect of the earlier fixes:

| Counter | Before fixes | After fixes |
|---|---|---|
| Friction per 100 prompts | 7.8 | 6.0 |
| Worktree-guard refusals | 26 | 0 |
| `sleep` blocks | 11 | 2 |

- `benchmark/score.py` scores a `findings.json` against three hand-built answer keys without a model. Run 2 scored 12/17, or 70.6% (`benchmark/README.md`).
- This is the only local evaluation of a harness. **No local evaluation compares `tlc-spec-driven` with `tlc-spec-lean` on the same task.**

**3. The owner has moved to `tlc-spec-lean` everywhere except Learny.**
- **Usage counts.** Re-aggregating `houston-roadmap-research/scripts/out/fresh_sessions.json` (15–30 Sep) gives:

| Skill | Sessions | By repo |
|---|---|---|
| `tlc-spec-lean` | 30 | workA 17, mandato-aberto 6, houston 3, fala 2, workB 2 |
| `tlc-spec-driven` | 3 | learny 1, workB 2 |
| `learny-ship-cycle` | 1 | learny |

  The aggregate in `research/04-evidencia-de-uso.md:76` ranks `tlc-spec-lean` as the most-expanded skill (30). Between 6 Jul and 7 Sep, by contrast, `tlc-spec-driven` had 15 uses (`houston-session-research/houston-ideia-orquestracao-de-sessoes.md` §6).
- **WorkA round 4** (2026-09-19..21, summarised in `houston-harness-research/research/02` §(d)):
  - It recorded "`tlc-spec-driven` 2.0.0 copies removed; `tlc-spec-lean` installed globally for a WorkB trial".
  - The owner's verbatim complaint about driven 2.0.0 was "TOO MUCH SUBAGENTWS … WASTE MONEY" (§(c) C5).
  - It recorded that `validate_tasks.py` "failed first-run 4/4 on format" and that LESSONS had "0 confirmed across 7 candidates" (C5).
  - The primary report lives in workA (`docs/research/2026-09-19-tlc-skills-comparison/`), which is rq01's scope.
- **Fala** (`fala-research/research/10-praticas-solo-e-agentes.md` §1.3) concludes: "`tlc-spec-lean` é o ajuste melhor: uma parada humana por feature, sem tarefas por arquivo … rodar os dois é redundante." Fala then adopted lean for every feature (`HANDOFF-fase-1-plano.md`).
- **Houston.** PRs #19, #23 and the resume feature were all built with lean (`houston-harness-research/HANDOFF-spike-fase-1.md`; `houston-resume-research/HANDOFF-feature-resume.md`).
- **Learny.** Learny chose `tlc-spec-driven` on 2026-06-27 only because it was in the Tech Leads Club catalog ("install shared skills from Tech Leads Club source", `docs/research/2026-06-27/project-workflow-conventions.md`). No alternative was compared.

**4. The lessons layer has never produced a confirmed lesson in any project.**

| Project | Candidates | Confirmed | Source |
|---|---|---|---|
| Learny (50 features) | 9 | 0 | `lessons.py --root learny status` (run 2026-09-30) |
| tally (1 cycle) | 5 | 0 | `tally-research/2026-08-03/specs-transfer-foundation/LESSONS.md` |
| Houston harness spike (lean) | 4 | 0 | `houston-harness-research/.specs/LESSONS.md` |
| workA | 7 | 0 | `houston-harness-research/research/02` §(d) "Recommendations explicitly NOT adopted" |

WorkA dropped the layer because "auto-memory already plays that role" (02 §(d)). Fala 10 §8.1 still lists it as "Adotar". That recommendation came from reading the skill, not from usage.

**5. Rules that live only in prose leak; enforcement has to be mechanical.**
- `fala-research/research/12-convencoes-de-commits-e-prs.md` §6 measured Learny on 2026-09-26:
  - 91.5% conventional commits over the last 200.
  - No `commit-msg` hook; `validate_metadata.py` is called by the skill, not by git.
  - `main` unprotected.
  - Merge commits on 30/30 PRs.
  - **Median PR of 4,540 lines and 50 files**, with only 3 PRs under 1,000 lines.
  - **0 of 30 PRs with a formal review.**
  - **56 `Co-authored-by: Cursor` and 4 `Co-Authored-By: Claude` trailers**, despite the rule against them.
- Its diagnosis: "O learny declara 'Keep PRs small and reviewable' … e tem mediana de 4.540 linhas porque a skill `learny-ship-cycle` fecha 'one roadmap cycle end-to-end' — a PR é o ciclo, não a mudança." (§6.2)
- WorkA round 5 proved by headless probe that its deny list did not load from `src/` (02 §(c) C6). tally rq04 §2 records Learny's "Makefile as contract" as the transferable part of the harness.

**6. Prior PR-practice research recommends the opposite of Learny's current shape.**
- Fala 12 §8 recommends squash with the PR title as the commit that survives, a 400-line PR target with stacked PRs above 1,000, CI linting of PR titles, lefthook plus commitlint, a ruleset on `main`, and an `Assisted-by: Claude Code` trailer instead of a prohibition.
- On the prohibition, §8.10 says "contraria kernel/LLVM/Fedora/Microsoft e falhou na prática (931 + 60 trailers)".
- Houston, the model repo, squashes, has 100% conventional titles and a median PR of 430 lines (§6.1).

**7. The owner's real unit of work is a chain of sessions joined by handoffs.**
- The voice note of 2026-09-07 says: "Eu já trabalho com um pipeline de sessões, não com uma sessão." It describes separate research, planning, execution and QA sessions (`houston-session-research/houston-ideia-orquestracao-de-sessoes.md`; quoted in `houston-harness-research/research/03`).
- The numbers grew over time: 64 handoff-prompt requests in 310 sessions (Jul–Sep), then 124 handoff prompts in 82 sessions between 15 and 30 Sep (`houston-roadmap-research/research/04` line 44).
- Fala formalises the split: Fable plans and stops at each plan approval, then Opus builds in a fresh session (`fala-research/HANDOFF-fase-1-plano.md`).

**8. Ceremony and subagents are the most repeated complaint.** Examples:
- "Execute it inline, do not create subagents, small enough"
- "Why is there a subagent exploring if implementation is done?" (an unannounced verifier)
- "Is this easy enough to not go to plan and just fix?"

These come from `houston-harness-research/research/02` §(c) C5. Separately, 4 explicit "why a subagent" complaints appear in 15–30 Sep (`houston-roadmap-research/research/04` line 92).

**9. Learny's harness is the template the owner copied elsewhere.** tally rq04 §2 says: "Two layers, replicated across learny → drover → herald … 'one roadmap cycle = one PR = one tlc-spec-driven cycle'". The efficacy layer is called "most transferable": golden fixtures, replay snapshots, the LLM judge and calibrated thresholds. Kappy is described as "the most evolved Laravel agent harness" (`kappy-research/2026-08-08/rq04-portfolio-fit.md:22`).

**10. The evidence on context files is weak, so the owner's research keeps instruction files short.** `fala-research/research/10` §5.3 cites:
- Gloaguen et al. 2026: AGENTS.md "não melhora em geral a taxa de sucesso" and adds more than 20% cost.
- Khatri 2026: no measurable correctness change.
- Macedo 2026: no spec-driven framework has a benchmark of its full pipeline.

These are external sources; rq05 should verify them.

**11. There is a tooling map for harness review.** `houston-harness-research/research/04-panorama-ferramentas.md` covers:
- `/insights` and `/fewer-permission-prompts`, whose sources are the vendor's changelog and docs.
- claude-md-doctor, which classifies each rule as Hook, Linter/Test or Judge.
- SkillOpt `skillopt-sleep`, the only tool with a no-regression gate before adoption.
- agent-retro.

Its conclusion: "no agent manager ships session-mined harness recommendations".

#### A3. Agreements and conflicts across folders

| Topic | Agree | Conflict |
|---|---|---|
| Spec shape (what → how → proof) | fala 10 §3.2: all frameworks "divergem no peso da cerimônia, não na forma"; Houston and workA use lean | none |
| Lean vs driven | fala 10, Houston, workA round 4, and usage 30 vs 3 sessions | Learny and kappy/tally (Jul–Aug) still on driven; nobody re-evaluated after lean 1.1.0 |
| Independent verifier / fresh-session review | all folders | none |
| Lessons layer | workA: drop (0/7) | fala 10 "Adotar"; houston 06 §2.3 praises `lessons.py` as a state model. All projects measure 0 confirmed |
| Script gates on plan structure | lean ships them; fala 10 keeps them | workA round 4 rejected them for its own plan skill (4/4 first-run format failures; "user never asked") |
| PR unit | fala 12 and Houston: small squash PRs | Learny and tally/kappy lineage: PR = cycle (tally rq04 calls the pattern transferable) |
| AI attribution | all agree it must be mechanical | Learny/workA: forbid trailers; fala: require `Assisted-by:` |
| Subagent models | everyone agrees: name the model per call | Learny ship-cycle: "never Sonnet", Haiku/Opus, Fable as an upshift; workA round 3: Sonnet for Explore and executors; workA round 4: "Fable never in a subagent" |

### B. `tlc-spec-driven` vs `tlc-spec-lean`

#### B1. Versions and provenance

| Copy | Version | Downloaded | Notes |
|---|---|---|---|
| `~/.claude/skills/tlc-spec-driven/` | 3.3.0 (Felipe Rodrigues) | 2026-09-02 | 5 scripts (`validate_spec`, `validate_tasks`, `validate_state`, `check_commit`, `lessons`) |
| `~/.claude/skills/tlc-spec-lean/` | 1.1.0 (Tech Leads Club) | 2026-09-20 | "Derived from tlc-spec-driven 3.3.0 (Felipe Rodrigues), tlc-plan, and tlc-implement" (SKILL.md). 6 scripts plus fixtures. `selftest.py` passes (46/46) |
| `learny/.claude/skills/tlc-spec-driven/` | **3.1.0** | 2026-06-27 | Only `lessons.py`; **none of the four validators**. 11 of 12 references differ from 3.3.0. Has no EARS (0 mentions in `specify.md` vs 5 in 3.3.0). Sub-agent offer is "more than 3 phases" (one worker per phase) instead of 3.3.0's ~7-task batches. Two local commits: `4fb6ff7` (2026-07-04, "forbid AI-attribution trailers", added to `implement.md`) and `4e40db0` (2026-07-25, lessons script path) |

- **Shadowing.** In this session, with cwd = Learny, the harness lists `tlc-spec-driven` with the 3.3.0 description ("Ships deterministic Python validation scripts…"), not the 3.1.0 one. That suggests the user-level copy is the one in use, which matches workA round 4's finding that "global 3.3.0 won 12/12" (02 §(c) C6). Confirming with `Base directory for this skill` lines in transcripts belongs to rq03.
- **The Learny trailer rule may not be in effect.** The user-level 3.3.0 contains no rule against attribution trailers (grep finds none). `tlc-spec-lean` has one natively: `references/build.md:108` "Never add Co-Authored-By, Made-with, or any agent attribution trailer."
- **Shared scripts are compatible.** The two `lessons.py` files differ only in labels ("Specify/Design" vs "Plan/Checks"; `validation.md` vs `verification.md`), so `.specs/lessons.json` carries over unchanged. Lean's `check_commit.py` also accepts a message string as well as a file path.
- **Neither skill ships a CHANGELOG.** Lean's rationale lives in SKILL.md ("Why this shape") and in `references/build.md` ("What was deliberately removed").

#### B2. Phase by phase

| | tlc-spec-driven 3.3.0 | tlc-spec-lean 1.1.0 |
|---|---|---|
| Phases | Specify → (Discuss) → (Design) → (Tasks) → Execute (Verifier inside Execute) | Plan → Checks → Build → Verify |
| Before code | `spec.md`, then `context.md` (when discuss triggers), `design.md` (Large/Complex), `tasks.md` (Large/Complex) | `plan.md` (problem + shape + criteria in one file), then `checks.md` |
| After code | `validation.md` | `verification.md` |
| Project memory | `.specs/STATE.md` (AD-NNN entries, one block each, "record sparingly") plus Handoff; `lessons.json`/`LESSONS.md` | Same files, but Decisions is a table. "**Where the repo already keeps ADRs or a decision log, use that instead.** Do not start a second log" (`references/memory.md`) |
| Requirements | User stories P1–P3, EARS ACs, requirement IDs `[FEAT]-NN` with a traceability status table, Edge Cases, Success Criteria | Slices S1..Sn ("one observable outcome each, never a layer"), EARS criteria numbered across the plan. No traceability table: checks cite "(FEAT-01, AC 1)" |
| Gray areas | `discuss.md`: "Generate 3-4 feature-specific gray areas", a pace question (Quick/Guided/Detailed), and `context.md` | No separate step. A fixed enumeration of surfaces (`## Observable` with a mandatory `n/a - <reason>`) plus the nine dimensions; leftovers go to `## Assumptions` with `Confirmed? y/n` |
| Design | Architecture with a mermaid `graph TD`, a Code Reuse table, a component catalogue (Purpose/Location/Interfaces/Dependencies/Reuses), data models with types, error-handling table, Risks & Concerns, Tech Decisions; 2–3 approaches for Large | Five bounded sections: `Flow` (one line per hop; only modules that exist or that a door creates), `Impact`, `Relations` ("No columns, no types"), `Surface` (route/in/out/statuses), `Landing` (one-way doors: literal shape plus the rejected alternative) |
| Work breakdown | `tasks.md`: one task = one component/function/endpoint/file; What/Where/Depends on/Reuses/Tools/Done when/Tests/Gate per task; phases; Test Coverage Matrix; Gate Check Commands; granularity, diagram and co-location tables; "ASK About MCPs and Skills" | None. `checks.md`: claims with a concrete value and a `Proof:` naming a specific test; a `Coverage` join (every set member as its own token); `Test policy` (standard/ui); `Swept` (nine dimensions to check ids); `## Handoff` with size arithmetic |
| Execution | Per task: state assumptions and files, write tests from ACs, implement, run the gate, post-gate review with **Test Adequacy Review Checks A–D and two mapping tables per task**, one commit per task with `tasks.md` updated in the same commit | "Satisfy the checks. How is yours." Tests come from the checks; commits are "one coherent piece"; mark the check complete in the same commit; scope guardrail |
| Sub-agents | Offer (never automatic) when there are more than ~8 tasks; ~7 tasks per batch worker, whole phases, sequential | One builder by default. `wc -c/4` arithmetic against a `budget` (default 150k). Over budget: stop and ask "handoff vs one builder". "Do not offer spawn at the start" |
| Context target | "<40k tokens total context"; spec 5k, design 8k, tasks 10k token caps (`context-limits.md`) | Builder budget of 150k declared in AGENTS.md (or equivalent) |

#### B3. Gates and validators

| When | Driven script | Lean script | What changed |
|---|---|---|---|
| Before human review of requirements | `validate_spec.py`: sections, SHALL per AC, assumption cells, ID format | `validate_plan.py` | Adds: Observable rows need a landing or a reasoned `n/a`; Landing rows need a literal shape and a rejected alternative; columns/types in `Relations` fail; Surface rows need statuses; blank sections must say `None - <why>`; criteria must land in Flow/Relations/Surface |
| Before build | `validate_tasks.py`: Tests/Gate fields, backward-only deps, diagram parity, multi-file `Where` warning | `validate_checks.py` | Replaced by the omission catcher: every check needs `Proof:`; a coverage row's declared size must not exceed its assigned members; nine swept dimensions; a `Profile:` line; warns when a `Surface` route has no check |
| Each commit | `check_commit.py` | `check_commit.py` | Same, plus accepts an inline message |
| Done | `validate_state.py`: `validation.md` exists, PASS, at least one `file:line` | `validate_verification.py` | Reads the report's own rows and refuses a PASS they contradict (surviving mutant, unproven member, non-PASS check, unmet test-policy row); the profile must match `checks.md`; `standard` needs fault rows and a recomputed Coverage; `ui` needs binding sources; warns on self-verified; exits 2 when it gated nothing |
| Gate on the gates | none | `selftest.py`: mutates fixtures once per rule (46 mutants killed), negative controls, smoke run | New |

Sizes:

| Skill | SKILL.md | References | Scripts |
|---|---|---|---|
| Driven 3.3.0 | 17.5 KB | 125 KB / 2,435 lines | 1,200 lines |
| Lean 1.1.0 | 20.5 KB | 80 KB / 1,482 lines | 2,267 lines (more of the discipline lives in code) |

#### B4. Verifier model

Both skills share the core rules: author ≠ verifier, a fresh sub-agent, never prompted, evidence-or-zero with a `file:line` plus the assertion expression, runs read-only, at most 3 fix→re-verify rounds, and lessons distilled afterwards. The differences:

| | Driven | Lean |
|---|---|---|
| Inputs | `spec.md`, the diff, the tests, `validate.md` | `plan.md`, `checks.md`, every binding source, `<feature base>..HEAD`, `verify.md` |
| Who dispatches | The orchestrator | "Dispatched by whoever holds the whole feature, never by a builder", over **every** check |
| Fault injection (the "discrimination sensor") | **Always on**: 1–3 mutations by default, ≥5 or mutation tooling for P0 paths | **Profile-gated.** `light` (the default): none. `standard`/`ui`: one fault per distinct assertion surface, capped at 5 |
| Coverage | Re-derived per AC | `light` reads the join; `standard` **recomputes** it from whatever holds authority over each set |
| Extra steps | Code-quality checklist; test-count before/after; interactive UAT | `ui`: compares against binding design sources, including screen arrangement |
| Re-verification | Full | "Round N - scoped": proofs re-run in full; everything else is re-checked only where the fix's diff touched it, and each section says whether it was verified at or carried from a commit |
| Model tier | Mid-to-high, "never the cheapest tier" | Same |

In practice, both lean runs on record used `Profile: light`:
- Houston harness spike: 52 checks, PASS at round 3 (scoped).
- Houston resume: 34 checks, PASS at round 2.

Sources: `houston-harness-research/.specs/features/harness-review-spike/verification.md:1-8`; `houston-resume-research/.specs/features/restore-resumes-conversation/verification.md:1-8`.

#### B5. Sizing logic

- **Driven** uses a four-row auto-sizing matrix (Small ≤3 files, Medium <10 tasks, Large, Complex). It decides which phases and files exist and how deep the dimension sweep and closure gate go. There is a safety valve: if an inline step list exceeds 5 steps, Execute stops and creates `tasks.md`.
- **Lean** has "one bounded escape, not a sizing matrix": a change under roughly three files with no one-way door gets `checks.md` with `## Intent` only. Everything else gets the full plan. Depth of verification is set by the declared **profile** (`light`/`standard`/`ui`), which is "a floor and … not a secret". Builder count is set by token arithmetic against `budget`.

#### B6. Where humans review

| Stop | Driven 3.3.0 | Lean 1.1.0 |
|---|---|---|
| Requirements | Spec confirmation after the closure gate | **Plan approval: the one default stop** ("This is the one place worth stopping for a human by default", `references/plan.md`) |
| Gray areas | Discuss: choose areas, pace question, deep-dive; approve `context.md` | Folded into the plan (at most 2 independent questions per turn, recommendation first) |
| Design | Approach choice (Large/Complex), then design approval | Folded into the plan |
| Tasks | Task approval with validation tables; "ASK About MCPs and Skills" | none |
| Execution | Sub-agent offer when there are more than ~8 tasks; approval of fix plans | Only when the size estimate exceeds the budget (mechanism ask); a check that turns out wrong forces renegotiation; one optional question about writing test-policy rows into the repo guidelines |
| End | Interactive UAT (user-facing) | Flow walk-through (user-facing only) |

Up to about 6 stops with driven on a Large/Complex feature, versus 1 (plus conditional ones) with lean. Learny's `learny-ship-cycle` replaces **all** of driven's stops with an auto-decision rule, leaving only the merge gate.

#### B7. What "freezes obligations instead of the plan" means concretely

- **What driven freezes.** The approved `tasks.md` is the plan the model executes. Each task carries `Where`, `Depends on`, `Tools` and `Done when`, and Execute follows it one task and one commit at a time. Divergence from the spec or design needs a `// SPEC_DEVIATION` marker.
- **What lean freezes.** Only `checks.md` claims, the proofs they name, and the `Test policy` rows. Critical rule 4: they "are fixed once approved".
  - Shape sections have two different rules. `Landing`, `Relations` and `Surface` are **additive**: a door found mid-build gets a new row before the code that closes it, and an approved row is never rewritten. `Flow` and `Impact` are **kept true**: they are edited in the commit that changes the path.
  - Everything else is free: "order, decomposition, how many commits, where files go, naming, error shapes, which helper gets extracted" (`references/build.md`).
- **The stated rationale** (SKILL.md "Why this shape"): "The dominant failure of a coding agent is not bad reasoning, it is a requirement that was read and never became an active obligation … Granularity is not quality … A plan the model must obey competes with the obligations for attention."

#### B8. Ceremony and token cost

- **Reference reading per full cycle.** Driven on a Large path loads SKILL plus specify, discuss, design, tasks, implement, coding-principles, sub-agents, validate, lessons and memory: about 139 KB, roughly 35k tokens. Lean loads SKILL plus plan, checks, build, verify and memory: about 100 KB, roughly 25k tokens.
- **Artifact lines per feature, from real runs:**

| Run | Skill | Lines per feature |
|---|---|---|
| Learny, 50 features (2026-06-27..09) | driven 3.1 via ship-cycle | **median 754**, max 1,524 (`cheaper-intelligence`), 39,318 in total. Per file (median): `tasks.md` 196, `design.md` 169, `spec.md` 157, `validation.md` 154, `context.md` 77, `review-triage.md` 22 |
| tally `transfer-foundation`, 13 tasks | driven | 1,122 (spec 148, context 79, design 151, tasks 449, validation 295) |
| Houston harness spike, 52 checks, 7 doors | lean `light` | 603 (plan 263, checks 236, verification 104) |
| Houston resume, 34 checks, 10 doors | lean `light` | 515 (222 / 191 / 102) |
| Lean fixtures (a complete passing `standard` set) | lean | 253 (114 / 98 / 41) |

  Lean removes `tasks.md`, the largest Learny artifact, and the per-task adequacy tables printed in chat (driven's Execution Template asks for a Check A table and a Check C table for every task). Learny's real artifact length drops by about 20–35%, not by an order of magnitude.
- **Project memory.** Learny's `.specs/project/STATE.md` holds 361 `AD-NNN` rows (up to AD-362) in 464 lines. `learny-ship-cycle` Stage 1 asks for an AD row for every auto-decision. That contradicts driven's own rule to "record sparingly" (`references/memory.md`, all three conditions must hold) and lean's rule to use the existing ADR log instead of a second one.

#### B9. What spec-lean dropped, and why (quoted from `references/build.md`, "What was deliberately removed")

| Removed | Stated reason |
|---|---|
| Granular task breakdown with `Where`/`Tools`/`Depends on` | "buys ordering, not correctness, and competes with the checks for attention" |
| Per-task test adequacy review tables | "author self-review reproduces the author's own blind spot; the Verifier does it once, better" |
| Per-task assumption declaration | "the assumptions that matter are in the spec, closed by its gate" |
| Component catalogue (Purpose/Location/Interfaces/Dependencies) | "reversible detail that goes stale with the authority of a document" |
| `graph TD` as the default diagram | "rots silently while `Flow` is kept true"; a mermaid flowchart only for fan-out, fork or async hand-off |
| `Code Reuse Analysis` table | "the catalogue again"; replaced by a single sentence opening `Flow` on what is reused |
| Pace question and `context.md` | "a meta-question spends a turn deciding how to spend turns" |
| Quota of 3–4 gray areas | "a quota manufactures questions" |
| Offering sub-agents at the start, or asking where to cut | "the cut is logistics; the mechanism is asked only when the estimate exceeds the budget" |

Also dropped, from SKILL.md and plan.md:
- The Specify/Design split. Splitting "would buy two mandatory stops for one feature".
- The sizing matrix, replaced by the single escape described in B5.
- Always-on mutation. It is now behind the profile, and `light` "will not notice a test that passes under a wrong implementation".

#### B10. Migration path for Learny's `.specs/` tree (dry-run evidence)

What Learny has today:
- `.specs/project/STATE.md` (464 lines) and `.specs/project/ROADMAP.md`
- `.specs/codebase/CONVENTIONS.md`
- 50 folders under `.specs/features/`
- `.specs/lessons.json` and `LESSONS.md`

How lean behaves against that tree (read-only, 2026-09-30):

- **Legacy folders can stay.** Lean's validators resolve one feature by name and ignore other folders. `validate_verification.py --root learny` with no feature exits **2**: "gated nothing … no completed feature detected". `validate_plan.py` reports "could not locate a plan.md". So the 50 driven folders are inert, and every call must name the cycle explicitly, because auto-detection never works with more than one feature.
- **Lessons carry over.** `lessons.py --root learny status` reads the existing store: "9 total | confirmed=0 candidate=9".
- **Path mismatch.** Lean (like driven) expects `.specs/STATE.md`, while Learny and ship-cycle use `.specs/project/STATE.md`. Neither skill's scripts read `STATE.md`, so the mismatch is instructional, not mechanical. Lean's memory rule points at `docs/adr/` as the decision log, leaving `STATE.md` with the handoff only.
- **Profile.** Lean wants a `## tlc-spec-lean` block (`profile`, `budget`) "in `AGENTS.md` or equivalent". Learny has no `AGENTS.md`, so the block would go in `CLAUDE.md`.
- **Vendored copy.** The 3.1.0 copy at `.claude/skills/tlc-spec-driven/` would be retired or replaced by a vendored `tlc-spec-lean`. CLAUDE.md says "Use project-local skills", but B1 suggests the user-level copy currently wins.

#### B11. How tightly `learny-ship-cycle` couples to tlc-spec-driven, and what would change

| Location | Current coupling | Change needed to drive lean |
|---|---|---|
| frontmatter `description`; Stage 1 title | "run a tlc-spec-driven cycle"; "Specify → Design → Tasks → Execute" | Plan → Checks → Build → Verify |
| Stage Detection table | "tlc Execute/Verifier incomplete"; "Verifier PASS on branch" | Add rows for `plan.md` without `checks.md`, and `checks.md` without `verification.md`. Define PASS as `validate_verification.py <cycle> --root <repo>` exiting 0 |
| Stage 1 auto-decision rule | Replaces "the human answering Discuss questions"; writes to the cycle's `context.md` and an AD-NNN row | `context.md` no longer exists. Decisions go to `plan.md` `## Assumptions` with `Confirmed? n` (lean: "Never mark `y` for a default nobody saw") and to `Landing` for doors. AD rows only for decisions that reach past the cycle, or an ADR. **And decide whether the plan-approval stop is auto-approved or becomes a second user gate** |
| Stage 1 execution | "When Execute runs one worker per phase", per-phase model selection (the 3.1.0 model) | One builder unless the `## Handoff` arithmetic exceeds `budget`. Ship-cycle must pre-answer lean's mechanism ask (e.g. a standing "handoff") to keep its autonomy contract. Model tiering moves from phases to slices or batches |
| Cost discipline / worker briefs | "discrimination sensor", "one atomic commit per task", "Verifier always Opus" | Fault injection exists only at `standard`/`ui`: pin `standard`. "One coherent piece per commit; mark the check in `checks.md` in the same commit". The Opus Verifier rule is unchanged. "State the goal, not the steps" already matches lean ("the checks are the bar; the route is your call") |
| Stage 2 | PR includes `.specs/features/<cycle>/*` | Same folder, with plan/checks/verification instead |
| Stage 4 `review-triage.md` | In the feature folder | Unchanged (lean does not forbid extra files) |
| `pr-review` Track A (SKILL.md:102) | Reads `spec.md`, `tasks.md`, `validation.md`, `FR-*` IDs | Read `plan.md`, `checks.md`, `verification.md`; criteria numbers and C-ids. Keep a fallback for the legacy folders |
| `learny-finalize` (SKILL.md:50–55) | Forbids "task or phase IDs from `tlc-spec-driven` (`A1`, `B2`…)" and names `tasks.md` | Add C-ids and S-slices; refer to `checks.md` |
| `SKILLS.md:20,24,29,35`; `.claude/skills/README.md:19-27`; `CLAUDE.md` Workflow | Name `tlc-spec-driven` | Rename; add the profile block to CLAUDE.md |

Overall the coupling is moderate. Ship-cycle owns the glue (Stages 0 and 2–8 do not depend on tlc internals), but Stage 1 and Stage Detection read driven-specific artifacts. Two lean semantics conflict with ship-cycle's autonomy contract: the human plan gate and the over-budget mechanism ask.

#### B12. User-level config (`~/.claude`)

- **`settings.json`:**
  - `cleanupPeriodDays: 365`, which was raised on 2026-09-07 per `houston-session-research`.
  - `model: opus`, `effortLevel: high` for every model in `modelSettings`.
  - `env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`.
  - A command status line.
  - `skipDangerousModePermissionPrompt`, `skipAutoPermissionPrompt` and `skipWorkflowUsageWarning` all `true`.
  - An `autoMode` block whose allow and soft-deny entries are for the work repos' PHP/Laravel commands, plus 25 lines of environment text about the work org (not reproduced).
  - **No hooks and no `permissions` block at user level.** Nothing user-level is tailored to Learny.
- **Plugins:** `installed_plugins.json` is empty. The only known marketplace is `claude-plugins-official`. Two `synced` folders hold built-in Anthropic skills.
- **Skills:** 26 entries in `~/.claude/skills`:
  - Both tlc skills.
  - `grilling` and `grill-me` as symlinks into `workA/.claude/skills/`.
  - `houston-pane`.
  - Architecture and quality skills from Tech Leads Club, installed on 2026-06-19.

## Implications for Learny

**I1. Use `tlc-spec-lean` for v8 cycles instead of `tlc-spec-driven`.** Confidence: **Medium**.
- *Why recommend:*
  - The owner already standardised on lean in five repos (30 vs 3 sessions) and wrote down the reasons (fala 10).
  - Lean drops Learny's largest artifact (`tasks.md`, median 196 lines) and every per-task table, while keeping EARS, the nine dimensions, proofs, the Verifier and lessons.
  - Ship-cycle's "state the goal, not the steps" brief already contradicts driven's per-task `Where`/`Tools` plan and matches lean.
  - Learny is not even running the copy it vendors (B1).
  - The ~12 v8 candidate rows are cycle-sized, which lean handles with one builder.
- *Why not:*
  - There is no head-to-head measurement; the evidence is usage, preference and structural reading.
  - Lean is v1.1.0, younger than driven.
  - Its real artifacts are only 20–35% shorter.
  - Migrating touches ship-cycle, pr-review, learny-finalize, SKILLS.md, CLAUDE.md and the skills README.
  - It does nothing about PR size by itself (I5).

**I2. If lean is adopted, pin `profile: standard` (budget 150k) in CLAUDE.md.** Confidence: **High** that `light` would be a regression; **Medium** on `standard` versus `ui`.
- *Why recommend:* Learny's confidence model leans on the discrimination sensor (ship-cycle "Cost discipline"; tally rq04 calls the efficacy layer Learny's most transferable asset). Under lean only `standard`/`ui` inject faults and recompute coverage, and `validate_verification.py` enforces the profile pin.
- *Why not:* `standard` costs up to 5 extra mutation runs per round, and `test-backend` needs `make infra`. Both Houston lean runs passed at `light`. `ui` adds binding-source comparison for the reading-first UI rows, which may be warranted for some v8 rows only.

**I3. Decide what replaces lean's single human plan gate inside ship-cycle.** Confidence: **Medium**.
- *Option A (keep autonomy):* ship-cycle auto-approves the plan, marks every auto-decision `Confirmed? n`, and the plan is reviewed at the merge gate.
  - Why recommend: it preserves the one-approval contract the owner built.
  - Why not: lean's whole design treats plan review as "the one place worth stopping", and the workA complaints about decisions "I haven't said yes for them" (02 §(c) C4) recur when nobody reads the plan.
- *Option B (two gates):* stop once at plan approval and once at merge, as Fala does with its separate plan and build sessions.
  - Why recommend: it catches wrong scope before code, and it matches the owner's own session-chain practice (A2.7).
  - Why not: one more interruption per cycle, and it breaks `auto`/`until` run modes unless the plan gate is also waivable.

**I4. Retire the vendored 3.1.0 copy; if lean is adopted, vendor `tlc-spec-lean` into `.claude/skills/` and confirm which copy loads.** Confidence: **Medium-High**.
- *Why recommend:* The vendored copy is stale (no validators, no EARS, a different sub-agent model). Its Learny-specific edit (no AI trailers) is likely not in effect. WorkA already lost months to a shadowed project skill (02 §(c) C6).
- *Why not:* Vendoring means manual upgrades. The user-level copy would still shadow a same-named project copy unless verified (rq03 should check the `Base directory` evidence).

**I5. Treat PR size and merge shape as a separate decision from the spec skill.** Confidence: **Medium**.
- *Why recommend:* Fala 12 measured a median of 4,540 lines and 0/30 formal reviews, and traced it to "a PR é o ciclo". Lean's coherent commits make stacked or split PRs per slice feasible; driven's one-commit-per-task ordering does not. Houston squash with ~430-line PRs is the owner's local model.
- *Why not:* Learny's evidence-gated nightly and review-triage loop are built around one PR per cycle, and more PRs means more ship-cycle runs and more review cost. tally rq04 explicitly values "one cycle = one PR" as the narrative.

**I6. Make commit and attribution rules mechanical, whichever skill is used.** Confidence: **Medium**.
- *Why recommend:* Both skills ship `check_commit.py` with an optional `commit-msg` hook. Fala 12 shows prose-only rules leaked (60 trailers in Learny), and lean already carries the no-trailer rule.
- *Why not:* The 60 trailers cluster in an 8-day Cursor window (fala 12 §6.2), so the recent leak rate may be near zero (rq03 has the fresh numbers). The owner's other repos switched to `Assisted-by:`, which is a policy choice, not a fix.

**I7. Stop expecting value from the lessons layer; keep `lessons.json` only because it is free.** Confidence: **Medium**.
- *Why recommend:* 0 confirmed lessons across four projects and roughly 60 features. WorkA dropped it with that evidence. Lean says it can be turned off by deleting two files, and "the … flow is unaffected".
- *Why not:* Promotion needs the same phrasing across two features within 45 days, so zero confirmations may reflect phrasing drift rather than no signal. Keeping it costs nothing at a clean PASS.

**I8. Stop growing the AD log in `.specs/project/STATE.md` per auto-decision.** Confidence: **Medium**.
- *Why recommend:* 361 rows contradict driven's "record sparingly" rule and lean's "use the existing log" rule. Learny already has `docs/adr/`.
- *Why not:* The ship-cycle rule exists so auto-decisions are auditable without the conversation. Lean's plan `## Assumptions` would hold the same audit trail per cycle.

**I9. To evaluate the harness itself, reuse the Houston harness-review method instead of another manual round.** Confidence: **Low-Medium**.
- *Why recommend:* It is the only measured evaluation (13/17 recall at about US$ 7 versus US$ 38–112 for manual rounds), and `score.py` makes reruns comparable.
- *Why not:* It was validated on workA only, depends on Houston's `hs-harness` digest (PR #23, unmerged as of 27 Sep), and Learny has fewer sessions to mine.

## Limitations

- **No transcripts read**, so whether the user-level or the vendored `tlc-spec-driven` loads in Learny is inferred from this session's skill listing and workA's 12/12 finding. rq03 should confirm it from `Base directory for this skill:` lines.
- **No head-to-head benchmark** of driven vs lean exists locally. The workA 2026-09-19 tlc comparison is known only through its summary in `houston-harness-research/research/02` (the primary file is rq01's).
- **The 15–30 Sep skill counts** come from `houston-roadmap-research`'s extractor, whose per-session `skills` field counts slightly differently from its aggregate (`tlc-spec-driven` 3 vs 1). The lean count (30) agrees between the two.
- **Learny PR metrics are dated 2026-09-26** (fala 12) and cover the last 30 PRs; rq03 will have fresher numbers.
- **External research** cited inside the owner's folders (Gloaguen, Khatri, Macedo, vendor docs) was not re-verified here.
- **Upstream versions** of both skills were not checked (no skill-path URL in the files). TLC community material on lean belongs to rq05.
- **Some folders were skipped as product content.** `tally-research/rq04` and `desafio-aurora-research` contain private interview material and `hr-research` contains employer-private passages; none of it is reproduced.

## Sources

**Cited:**
- `/home/augusto/projects/houston-harness-research/`: `README.md`; `research/02-precedente-workA.md`; `research/03-sessoes-e-pesquisa-anterior.md`; `research/04-panorama-ferramentas.md`; `research/06-sintese-e-proposta.md`; `research/07-grilling-decisoes.md`; `research/08-validacao-spike.md`; `benchmark/README.md`; `HANDOFF-spike-fase-1.md`; `.specs/LESSONS.md`; `.specs/features/harness-review-spike/{plan,checks,verification}.md`
- `/home/augusto/projects/houston-roadmap-research/`: `README.md`; `research/04-evidencia-de-uso.md`; `scripts/out/fresh_analysis.json`; `scripts/out/fresh_sessions.json`
- `/home/augusto/projects/houston-session-research/`: `README.md`; `houston-ideia-orquestracao-de-sessoes.md`
- `/home/augusto/projects/houston-resume-research/`: `README.md`; `HANDOFF-feature-resume.md`; `.specs/features/restore-resumes-conversation/{plan,checks,verification}.md`
- `/home/augusto/projects/fala-research/`: `README.md`; `research/10-praticas-solo-e-agentes.md`; `research/12-convencoes-de-commits-e-prs.md`; `decisions-log.md`; `HANDOFF-fase-1-plano.md`; `HANDOFF-fase-0-fechamento.md`
- `/home/augusto/projects/tally-research/`: `2026-08-02/rq03-agent-skills-hyperf.md`; `2026-08-02/rq04-developer-profile-harness.md` (harness sections only); `2026-08-02/synthesis.md`; `2026-08-03/specs-transfer-foundation/{STATE.md,LESSONS.md,features/transfer-foundation/*.md}`
- `/home/augusto/projects/kappy-research/`: `README.md`; `2026-08-08/rq04-portfolio-fit.md`
- `/home/augusto/projects/desafio-aurora-research/research/05-padroes-de-entrega.md`
- `/home/augusto/.claude/skills/tlc-spec-driven/`: `SKILL.md`; `references/{specify,discuss,design,tasks,implement,validate,sub-agents,memory,lessons,context-limits}.md`; `scripts/*.py`; `.skill-meta.json`
- `/home/augusto/.claude/skills/tlc-spec-lean/`: `SKILL.md`; `references/{plan,checks,build,verify,memory}.md`; `scripts/*.py`; `scripts/fixtures/*.md`; `.skill-meta.json`
- `/home/augusto/projects/learny/`: `.claude/skills/tlc-spec-driven/` (and git commits `4fb6ff7`, `4e40db0`); `.claude/skills/learny-ship-cycle/SKILL.md`; `.claude/skills/pr-review/SKILL.md`; `.claude/skills/learny-finalize/SKILL.md`; `SKILLS.md`; `.claude/skills/README.md`; `.specs/project/STATE.md`; `.specs/lessons.json`; `.specs/features/*/*.md` (line counts); `docs/research/2026-06-27/project-workflow-conventions.md`; `docs/research/2026-06-27/agent-skills-source.md`
- `/home/augusto/.claude/settings.json` (summarised, secrets redacted); `/home/augusto/.claude/plugins/{installed_plugins,known_marketplaces}.json`; the `/home/augusto/.claude/skills/` listing

**Consulted, not cited:**
- `houston-harness-research/{issue-draft.md,whatsapp/,research/05-houston-hoje.md}`
- `houston-roadmap-research/research/{01,02,03,05}` (headers)
- `houston-keyboard-research/README.md`
- `fala-research/research/README.md`, `research/notes/12-convencoes/{specs-ia-branches,projetos-locais}.md` (heads)
- `hr-research/README.md`
- `kappy-research/2026-08-08/README.md`
- `shared-skills/README.md`
- `tally-research/2026-08-03/tally-backup/repo/AI_STRATEGY.md`
- `learny/.specs/codebase/CONVENTIONS.md`
- `learny/.claude/settings.json` (key names only)
