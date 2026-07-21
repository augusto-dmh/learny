# Eval Deepening — Decision Context

Auto-decided per the ship-cycle autonomy contract (no user prompts except merge gate). Each decision lists the option set considered, the pick, and why — auditable without the conversation. AD rows mirrored in `.specs/project/STATE.md`.

## D-1 (AD-161) — Silver case authorship

- **Options:** (a) agent authors cases in-cycle by reading passages from the local corpus DB — *recommend:* unblocks the generation A/B, which the ROADMAP says is uninformative without silver; *against:* not literally hand-authored by the user, case quality depends on the agent's reading of PT/EN passages. (b) ship runner + format only, user authors cases during dogfood — *recommend:* purest reading of "hand-authored"; *against:* blocks deliverable 4 of the blessed candidate scope, leaving the cycle half-shipped.
- **Pick: (a).** The candidate's purpose is the A/B evidence; cases are curated per-passage (question written against a specific read passage, expected anchor verified by retrieval), which preserves the intent of "hand-authored" vs template generation. User can revise cases during dogfood — they're local data, not code.

## D-2 (AD-162) — Silver case identity

- **Options:** (a) key by source **checksum + chunk/section anchor** — *recommend:* stable across re-ingestion and DB rebuilds (anchors are the citation-stability invariant, AD-038; checksum identifies the exact file); *against:* re-uploading a different edition breaks cases (acceptable: reported as broken, DEEP-18). (b) key by source UUID — *recommend:* trivial joins; *against:* UUIDs are per-DB, silver set dies on any rebuild.
- **Pick: (a).**

## D-3 (AD-163) — Silver data location & runner placement

- **Options:** (a) data in `evals/silver/` (git-ignored), runner in `backend/tests/eval/test_silver.py` + loader in `backend/tests/eval/silver.py` — *recommend:* mirrors the existing `evals/` results convention and `backend/tests/eval/` harness layout; pytest self-skip matches the live-key skip idiom; *against:* eval data outside `backend/` means the runner needs a repo-root-relative path. (b) data under `backend/tests/eval/silver/` — *recommend:* everything in one tree; *against:* git-ignored data inside the test tree is easy to accidentally commit, and `evals/` is already the data home.
- **Pick: (a).** Gitignore gets `evals/silver/` (whole dir).

## D-4 (AD-164) — Recalibration corpus for the anchored rubric

- **Options:** (a) 12 committed replay snapshots (zero generation spend) + silver outputs once recorded — *recommend:* matches the calibration-first procedure in `docs/ops/eval-calibration.md`; replayed outputs isolate the rubric change from generation drift; *against:* golden-only baseline may shift again once silver dominates. (b) fresh live generations for calibration — *recommend:* most current; *against:* conflates rubric change with generation nondeterminism, spends tokens for no isolation benefit.
- **Pick: (a).** Baseline re-derivation and gate re-pin use golden replayed outputs; silver distributions are recorded as context in the research doc, not gated this cycle.

## D-5 (AD-165) — Judge default policy after the A/B

- **Options:** (a) keep `claude-haiku-4-5` unless material disagreement (defined in design: exact agreement < 60% or within-1 < 90% on the anchored rubric, or any gate-verdict flip) — *recommend:* cheap judge is the point; anchoring exists precisely to fix Haiku's known artifact; *against:* threshold is a judgment call. (b) switch to Opus if it looks at all better — *against:* 5× judge cost with no defined bar; nightly runs pay it forever.
- **Pick: (a).**

## D-6 (AD-166) — Generation default flip authority

- **Options:** (a) flip in-cycle only on a decisive verdict (design defines decisive: Opus strictly better on ≥2 of faithfulness/relevancy/not-found-discipline over silver, no metric worse, after cost is stated), surfaced at the merge gate — *recommend:* the candidate's stated purpose is that the doc decides; merge approval covers the change; *against:* a default flip raises product cost ~5×/token, arguably user-worthy on its own. (b) doc only recommends, user flips later — *recommend:* maximal caution; *against:* re-opens a decision the user already delegated to evidence.
- **Pick: (a)** — with the flip isolated in its own commit so the merge-gate report can point at it and the user can strip it before merging if they disagree.

## D-7 (AD-167) — One judged dataset serves both A/Bs

- **Options:** (a) generation A/B outputs judged by Haiku (primary) and Opus (the judge A/B) — the same scoring pass produces judge-agreement data and a robustness check on the generation verdict — *recommend:* halves judge spend, and agreement measured on exactly the outputs that matter; *against:* judge A/B is then measured on A/B outputs rather than the historical replay set (mitigated: the 12 replayed snapshots are also scored by both judges). (b) independent scoring passes per study — *against:* double spend for the same information.
- **Pick: (a).**

## Environment facts (verified 2026-07-21)

- Local stack up: `learny-db-1`, `learny-redis-1`, `learny-minio-1` (Docker, healthy).
- 8 ready sources (7 distinct books; "Os 5 desafios das equipes" duplicated), all chunks embedded, `search_config` ∈ {portuguese, english, simple}.
- `backend/.env` has `LEARNY_ANTHROPIC_API_KEY` and `LEARNY_OPENAI_API_KEY` (values not read).
- No confirmed tlc lessons in the store.
- Eval seams: judge + prompts `backend/app/eval/`; replay harness `backend/tests/eval/harness.py`; cases `backend/tests/eval/cases.yaml` (12); gate constants `judge.py:53-54` pinned by `test_eval_judge.py:278`; calibration doc `docs/ops/eval-calibration.md`; results sink `evals/results/`.
- **Local gate footgun (found pinning the baseline):** `Settings` loads `backend/.env` (`config.py:23`), and the dogfood `.env` sets real providers — 11 deterministic tests fail unless gates prefix `LEARNY_GENERATION_PROVIDER=local LEARNY_EMBEDDING_PROVIDER=local`. CI unaffected (no `.env`). All cycle gate commands carry the prefix.

## Deferred Ideas

- conftest should pin `LEARNY_GENERATION_PROVIDER`/`LEARNY_EMBEDDING_PROVIDER` to `local` (mirroring its cookie/CSRF pins) so a dogfood-configured `.env` can't fail the deterministic suite. Out of this cycle's scope; surface for a future hygiene task.
