---
id: harness-project-brief
title: Harness and delivery-loop review before the v8 roadmap
date: 2026-09-30
status: frozen
---

# Project brief — is Learny's cycle model the right harness for v8?

*Trigger: owner request (2026-09-30). A long `v8` candidate roadmap now sits uncommitted in `.specs/project/ROADMAP.md`. Before starting it, the owner wants evidence on whether the delivery harness — the `tlc-spec-driven` cycle wrapped by `learny-ship-cycle`, the PR/commit conventions, the skills, CI and infra — is the best way to ship features with an AI agent, or whether it has become heavyweight. The TLC community now promotes `tlc-spec-lean` as the next step after `tlc-spec-driven`; the owner believes loops of cycles make sense, but perhaps not in the shape Learny uses today.*

## Questions

1. **How does the owner actually use AI across projects?** Evidence from ~700 Claude Code transcripts in `~/.claude/projects/` (mostly `workA/src`, `workB/src`, `workA`, `houston`), not only Learny's. What workflows recur, what works, where the owner intervenes, and how other repos' harnesses differ from Learny's.
2. **What does Learny's harness cost and buy today?** Skills, ship-cycle, `.specs/` artifacts, lessons, PR/commit shape, CI and nightly, and which of the 2026-07-24 recommendations were adopted.
3. **What does `tlc-spec-lean` change relative to `tlc-spec-driven`**, and what do the owner's other research folders (`~/projects/*-research`, `shared-skills`) already conclude about harnesses?
4. **What does current external practice (as of 2026-09-30) say** about spec-driven development, agent loops, agent-ready repos, PR/commit hygiene with agents, CI as an agent sensor, and harness evaluation?
5. **Decision:** what to keep, change, and drop in Learny's harness before the first v8 cycle, sized as concrete moves.

## Baseline (do not restate; report deltas)

- `docs/research/2026-07-24/ai-harness-session-analysis.md` — Learny-only, 30 transcripts, P1–P12 friction list and a three-tier action plan.
- `docs/research/2026-09-03/meta-fleet-process.md` and `meta-output-conventions.md` — the house research-fleet process and report shape this drop follows.

## Fleet

| File | Scope (exclusive) |
|---|---|
| `rq01-workA-usage.md` | Transcripts and harness of `workA` (src, root, every `.claude/worktrees/*` and `workA-*` copy) |
| `rq02-other-projects-usage.md` | Transcripts and harnesses of `workB` (+ worktrees), `houston`, `workC`, `mandato-aberto`, `fala`, `workD`, `workE`, `workF`, `workG`, the `projects` and home roots |
| `rq03-learny-harness-audit.md` | Learny's own harness, transcripts, `.specs/`, git/PR/CI metrics, adoption of the 2026-07-24 plan |
| `rq04-local-research-and-tlc.md` | `~/projects/*-research`, `shared-skills`, user-level `~/.claude` config, `tlc-spec-driven` vs `tlc-spec-lean` skill diff |
| `rq05-external-practice.md` | Web: TLC community material on spec-lean, spec-driven dev landscape, Anthropic/OpenAI harness guidance, loop patterns, PR/CI practice with agents |
| `gap-critique.md` | Claim matrix, conflicts, coverage gaps (lead) |
| `synthesis.md` | Recommendation, keep/change/drop, migration moves (lead) |

## Output contract (every rq file)

YAML front matter (`id`, `title`, `question`, `date`, `status`, `overall_confidence`) → **TL;DR** (≤200 words) → **Method** (what was read, how, counts) → **Findings** (facts with evidence: transcript session id + date, file path, or URL; no advice) → **Implications for Learny** (each with why-recommend / why-not and High/Medium/Low confidence) → **Limitations** → **Sources** (consulted vs cited). English. Quote the owner verbatim (Portuguese is fine) when a quote is evidence.

## Out of scope

Product direction and the v8 rows themselves (owned by `../synthesis.md`). Provider choice (ADR-0019/0020). No changes to code, skills, settings, or the roadmap in this drop — findings only.
