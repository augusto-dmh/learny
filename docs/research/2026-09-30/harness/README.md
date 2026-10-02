# Research drop 2026-09-30 — harness and delivery loop

*Trigger: owner request (2026-09-30) to check, before starting the uncommitted `v8` roadmap, whether Learny's cycle model (`tlc-spec-driven` wrapped by `learny-ship-cycle`) is still the right way to ship with an AI agent, using evidence from the owner's ~700 Claude Code sessions across projects, his local research folders, and current external practice. Delta on top of `docs/research/2026-07-24/ai-harness-session-analysis.md`. Sibling of the product drop in `..` (study-home delta).*

| File | Question it answers |
|---|---|
| [project-brief.md](project-brief.md) | Frozen questions, fleet scopes, output contract |
| `rq01-workA-usage.md` (local-only) | How the owner ships in workA (451 transcripts, 119 PRs) |
| `rq02-other-projects-usage.md` (local-only) | WorkB, Houston, mandato-aberto, fala and others (251 sessions); lean vs driven in practice |
| [rq03-learny-harness-audit.md](rq03-learny-harness-audit.md) | What Learny's harness costs and buys; adoption of the 07-24 plan |
| [rq04-local-research-and-tlc.md](rq04-local-research-and-tlc.md) | What the owner's `*-research` folders already concluded; `tlc-spec-driven` vs `tlc-spec-lean` file by file |
| [rq05-external-practice.md](rq05-external-practice.md) | TLC's rationale and benchmark for lean; SDD critiques; vendor harness guidance |
| [gap-critique.md](gap-critique.md) | Claim matrix, conflicts and resolutions, coverage gaps |
| [synthesis.md](synthesis.md) | Recommendation, target harness, sequenced moves, pilot scorecard, open decisions |

> **Local-only files.** `rq01` and `rq02` analyse the owner's work repositories and are kept out of the repository; this index, the gap critique and the synthesis cite their aggregate numbers. Work repositories are aliased `workA`…`workG` throughout.

## Thesis in one line

Keep the loop and the orchestrator; replace what runs inside it — `tlc-spec-lean` in two rule-chosen lanes, mechanical sensors instead of prose rules, and a paperwork diet — and prove it on the first two v8 rows.

## Owner decisions (2026-10-02)

D1 door-only plan gate · D2 one PR per batch of slices · D3 `Assisted-by: Claude Code` trailer · D4 keep deleting review comments · D5 nightly schedule off, manual dispatch · D6 merge commits + commit lint — details and the two lean deviations in `synthesis.md`.
