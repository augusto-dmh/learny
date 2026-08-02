# Context — v5-eval-dashboard (RFC-005 Cycle D)

Decisions taken under the ship-cycle auto-decision rule (no user prompt). Each records the option set
considered with why-recommend and why-not, the choice, and the rationale, so it is auditable without the
conversation. Mirrored as AD-239..AD-244 in `.specs/project/STATE.md`.

RFC-005 open question #4 ("eval dashboard in or out") was already resolved in the RFC itself — *keep it as a
compact cycle, the most naturally cuttable rider*. This cycle therefore builds the compact version and does not
relitigate scope.

---

## AD-239 — Data source for the rendered runs

| Option | Why recommend | Why not |
| --- | --- | --- |
| **A. Configurable results directory, read recursively; default = the judge's `RESULTS_DIR`** *(chosen)* | No new infrastructure; identical to where the judge already writes; recursion + the setting let an operator `git worktree add` the `eval-results` branch and get the real nightly history with no code change; trivially testable by pointing at a tmp dir | One more setting to document |
| B. Read only `evals/results/` non-recursively | Simplest possible | Renders only the five committed files; the actual accumulating nightly history on the `eval-results` branch stays invisible, which is the thing the RFC asked to render |
| C. Fetch/clone the `eval-results` branch at request time | Shows the true history with no operator step | Puts git, network, and credentials in the request path of a read-only dev page; slow and awkward to test; disproportionate for the RFC's most cuttable cycle |

**Chosen: A.** It is B plus a one-line escape hatch, and it resolves the history/simplicity tension without
putting git in the request path.

## AD-240 — Run identity and duplicate snapshot files

| Option | Why recommend | Why not |
| --- | --- | --- |
| **A. Identify a run by result-file basename; on collision keep the lexicographically greatest path** *(chosen)* | The judge names files `<date>-<git_sha>.jsonl`, so the basename already *is* the run identity; the nightly copies every file into each snapshot dir, so the same seed file appears in all 8 dirs and a naive scan reports it 8 times as fresh data; the judge only appends, so the newest copy is a superset | Two genuinely different runs sharing a date and short sha would collide — not observed, and the sha makes it vanishingly unlikely |
| B. Identify a run by containing directory | Matches the nightly's own layout | Every snapshot dir re-contains the seed files, so one "run" would blend unrelated runs; also wrong for the flat local `evals/results/` |
| C. Deduplicate by content hash | Exact | Misses the append case (newest copy is a strict superset, so hashes differ and both survive) — the very case that produced the duplicates |

**Chosen: A.** Duplicate suppression is a correctness invariant here, not a nicety: without it the trend line is
mostly repeated seed data.

## AD-241 — How the gate verdict is produced

| Option | Why recommend | Why not |
| --- | --- | --- |
| **A. Derive it, mirroring `_assert_aggregates` and importing `FAITHFULNESS_MIN`/`RELEVANCY_MIN` from `app.eval.judge`** *(chosen)* | No verdict field exists in the JSONL, so it must be derived; importing the constants makes threshold drift impossible by construction; `ab.py` already sets this precedent (`ab.py:58` imports the same two constants for exactly this reason) | Duplicates the *rule* (three conditions) even though the constants are shared — mitigated by a test asserting the derived verdict equals the gate's outcome |
| B. Re-type the thresholds in dashboard code | Fewer imports | A dashboard that silently shows a stale threshold after the next recalibration is worse than no dashboard; Cycle B just moved relevancy 3.0→3.1 |
| C. Have the judge write a verdict field into the JSONL | Single source of truth | Changes the writer and does not apply retroactively to the eight already-published nightly snapshots — the exact data being rendered |

**Chosen: A.** Note the gate has **three** conditions, not two: `citation_valid` on every line (declines
included), then the two means over answered lines — and a run with no answered line skips the means entirely
(`judge.py:428-439`). The derived verdict must reproduce all three, including the skip.

## AD-242 — Mixed record families in one file

| Option | Why recommend | Why not |
| --- | --- | --- |
| **A. Partition lines by family before aggregating; generation lines feed `ab.aggregate`, answerability lines get their own small summary** *(chosen)* | `ab.aggregate` reads `line["faithfulness"]` and `line["citation_valid"]` unguarded, so it raises `KeyError` on an answerability line — reproduced against the real `evals/results/2026-07-18-5b85c39.jsonl`; every nightly file mixes ~6 answerability rows with ~1 generation row | Requires a family discriminator (`case_id` vs `item_id`) that is implicit in the writer rather than declared |
| B. Loosen `ab.aggregate` to tolerate missing keys | One code path | Changes a function the Cycle B/C gate and study depend on, to serve a read-only page — a real regression risk on the load-bearing path |
| C. Render only generation lines | Simplest | Silently drops the majority of every nightly file's records |

**Chosen: A.** Discriminate on the identity key the writer emits: `case_id` → generation (`judge.py:347`),
`item_id` → answerability (`judge.py:393`). Confining the change to the reader keeps the gate path untouched.

## AD-243 — Where the surface lives and who may see it

| Option | Why recommend | Why not |
| --- | --- | --- |
| **A. Mirror the instrument precedent — mounted only when a dev flag is set AND the process is not production; authenticated once mounted** *(chosen)* | RFC-005 requires Cycles A–E to stay off surfaces the dogfooding author sees, so gating is a *requirement* here, not taste; `instrument_surface_exposed` (`main.py:38`) is a shipped, tested precedent with the production refusal already reasoned through and logged | Two gates to configure before the page is usable |
| B. Authenticated but always mounted | Simpler to reach | Puts a new surface into the live dogfood window that the RFC's sequencing argument promises is not there |
| C. Unauthenticated dev-only page | Least friction locally | Model names, prompt hashes, and case text behind no auth on any non-production deploy; the precedent costs nothing to follow |

**Chosen: A.** Reuse `instrument_surface_exposed`'s shape with its own flag so the two dev surfaces stay
independently switchable.

## AD-244 — Visualization approach

| Option | Why recommend | Why not |
| --- | --- | --- |
| **A. Hand-rolled inline SVG series using the existing `--color-chart-*` tokens** *(chosen)* | No new runtime dependency in the RFC's explicitly most-cuttable cycle; the tokens already exist in `globals.css`; single-digit run counts need no chart runtime; renders deterministically under jsdom, so it is assertable in Vitest | More code than dropping in a library; no free axes/tooltips |
| B. Add Recharts (or similar) | Batteries included | A runtime dependency and bundle weight for one dev-only page, in the cycle most likely to be cut; the project has deliberately kept broad libraries out of the core |
| C. No visualization — tables only | Cheapest | The RFC's stated value is drawing the recalibrated thresholds as reference lines; a table of numbers does not make drift visible |

**Chosen: A.**

## AD-245 — Verdicts recomputed across a recalibration boundary

Found by pointing the finished reader at the real `eval-results` branch: **9 of the 11 historical runs
render `fail`**, all at relevancy exactly 3.00. They are not regressions. Those runs were judged by
`claude-haiku-4-5` and gated at the old `RELEVANCY_MIN = 3.0`; Cycle B flipped the judge to
`claude-opus-4-8` and re-pinned the threshold to 3.1. Every verdict is re-derived with *today's*
constants (AD-241), so a run that passed its own gate at the time now reads as failing.

| Option | Why recommend | Why not |
| --- | --- | --- |
| **A. Keep the derived verdict, and mark any run whose judge differs from the one in force, with the caveat stated on the page** *(chosen)* | Preserves AD-241's single decision rule and the drift-proofing that motivated it, while making the one thing that invalidates a cross-boundary comparison visible exactly where the comparison happens; costs one payload field | The badge still says `fail` on a run that passed its own gate — mitigated by the marker sitting beside it |
| B. Record each run's thresholds at write time and judge it against those | Historically exact | Does not apply retroactively to the eight already-published snapshots, which are the data being rendered; and it re-opens the writer, which this read-only cycle deliberately does not touch |
| C. Render no verdict for runs predating the recalibration | Never misleading | Blanks the majority of the history, and the RFC asked for gate pass/fail |

**Chosen: A.** The endpoint carries `judge_model_in_force` (from `settings.judge_model`) so the page can
name the mismatch rather than the client keeping its own idea of the current judge. Left unmarked, the
dashboard's most prominent signal would be a wall of red that means "the threshold moved".
