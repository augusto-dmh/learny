# local-models-self-host review triage (PR #84)

Independent review posted 2026-10-31 on PR #84: 5 inline comments (ids 4433126712,
4433126746, 4433127452, 4433127534, 4433127630) + 2 PR-level comments (requirements
review 6548504612, consolidation 6548504970). The consolidation comment restates the
five inline findings; the requirements review's single Missing item (capture
provenance `git_sha`) restates inline 4433126712. One row per distinct finding below;
each PR-level comment maps to those rows. Verdicts judged on the code as it exists
(worktree `feat/local-models-self-host` at `ce5e4eb`), not on the reviewer's authority.
This file is the surviving record — the PR comments are deleted after the fixes land.

## F1 — capture provenance sha resolved one directory above the repo root

- Source: inline 4433126712 (`backend/app/cli/capture_local_golden.py:180`); also the
  requirements comment's Missing item and the consolidation's Critical row.
- Verdict: **real** (critical). `_output_dir` is `<repo>/evals/local`, so
  `_output_dir.parents[2]` is the *parent of the repository root*. Verified empirically
  in this worktree: from `C:\dev\learny\.worktrees` git resolves the outer checkout's
  HEAD — the capture would stamp `034c74a` (main's head) instead of the branch's
  `ce5e4eb`, and in a normal clone layout it stamps `"unknown"`. Either way the
  provenance field and the filename are wrong, which breaks the runbook's
  "commit the file so the claim and its evidence travel together" workflow. This also
  corrects verification.md's round-1 observation that called the field "cosmetic" —
  under the test's `tmp_path` patch it only ever showed `"unknown"`; the foreign-sha
  path was invisible to the verification because the test seams hide it.
- Action: **fix** — resolve the repo root as `_output_dir.parents[1]` (the directory
  that holds `evals/`), compute the sha once per run (it was one subprocess per record
  plus one for the filename — 17 per capture), and pin both behaviors with tests: the
  stamp equals `git rev-parse --short HEAD` run at the repo root, and the fallback
  outside a repository stays `"unknown"`.

## F2 — the hosted OpenAI key is forwarded as Bearer to the operator-supplied `--base-url`

- Source: inline 4433126746 (`backend/app/cli/capture_local_golden.py:262`).
- Verdict: **real** (the exposure exists as described): `api_key=settings.openai_api_key
  or _KEY_PLACEHOLDER` puts the environment's real hosted key on every request the
  capture makes, to whatever URL `--base-url` names.
- Action: **fix** — the capture sends the fixed placeholder unconditionally and never
  reads the hosted key. Rationale for this default over gating/loopback checks: the
  documented capture targets (Ollama, LM Studio) are keyless and ignore the header
  entirely, so on the documented path the real key buys nothing and only leaks; the
  runner exists precisely to point at the operator's own local runtime, so the
  defensible default is "this command carries no real credential", recorded in the ops
  runbook. A runtime that genuinely requires a real key is not a local capture and is
  out of `evals/local`'s scope (noted in the runbook rather than built as an opt-out
  flag — no second credential surface for an operator tool).
- Won't-fix companion: the embedding factory's compat branch
  (`settings.openai_api_key or "local-embedding-runtime"`, documented in the runbook's
  embeddings section) is a different trust shape: its base URL is a *deployment
  configuration* the operator deliberately sets (and some OpenAI-compatible proxies
  require a real key), not a per-invocation CLI flag. Changing it would alter documented
  app runtime behavior beyond this review's defect; the runbook already states the
  convention. Recorded as accepted.

## F3 — `SettingsDimVector()` unparameterized vs the shipped `vector(1536)` DDL

- Source: inline 4433127452 (`backend/app/infrastructure/db/metadata.py:81`).
- Verdict: **real**. Verified: the type renders bare `VECTOR` (`dim: None`) while all
  three embedding columns ship as `vector(1536)` (migrations 0005 `corpus_chunks`,
  0008 `quiz_items`, 0013 `notes`), and the Alembic environment runs
  `compare_type=True` in both online and offline modes — so a fresh autogenerate can
  see a type mismatch and emit typmod-dropping ALTERs. The class docstring itself
  promises "The column DDL stays the migration's ``vector(1536)``".
- Action: **fix** — the type declares the migrations' width in its constructor
  (`super().__init__(1536)`); the bind-processor override keeps validating every write
  against the configured `LEARNY_EMBEDDING_DIM`, so the write contract is unchanged and
  the metadata now states the truth. Pinned by a test asserting the declared DDL width
  renders `VECTOR(1536)`. Known accepted residual: after an operator runs the documented
  resize procedure to a non-default dimension, the constant no longer matches the live
  column — a pre-existing tension of a fixed metadata constant vs a manual data
  operation, unchanged by this fix (the default-state drift is what the fix removes).

## F4 — stamp predicate narrows the arm served by the embedding-only HNSW index

- Source: inline 4433127534 (`backend/app/infrastructure/db/retrieval.py:76`).
- Verdict: **real but bounded and transient** — the reviewer's own rating. The equality
  predicate on `embedding_model` does filter rows the HNSW index (on `embedding` alone)
  has already traversed; the worst case (fully stale corpus) is exactly the state the
  feature sends to lexical-only answers, at operator scale, until re-embedding
  completes.
- Action: **won't-fix in code**; record the accepted trade in the ops runbook. The
  predicate *is* the feature's recorded guarantee (a foreign-stamped corpus is never
  fused — pinned by exact-RRF arithmetic tests), and there is no schema-level fix (a
  composite (stamp, vector) HNSW index is not supported). The alternative the reviewer
  names — iterative HNSW scans (pgvector ≥ 0.8, opt-in per session) — would change query
  semantics that the verification's exact-RRF proofs pin, for a transient underfill
  during a manual re-embed window; not a trade worth taking in this cycle. The db image
  digest pin is left alone (shared deploy infrastructure, out of the review's scope).

## F5 — a same-day re-capture silently overwrites the previous JSONL artifact

- Source: inline 4433127630 (`backend/app/cli/capture_local_golden.py:313`).
- Verdict: **real**. The artifact path is `<date>-<sha>-<model>.jsonl` opened with mode
  `"w"`; once F1 is fixed the name is deterministic per day+sha+model, so the runbook's
  iterate-and-capture loop destroys the earlier record with no warning.
- Action: **fix** — refuse to overwrite: the runner checks the artifact path before any
  network attempt or database write and exits `3` with a message naming the existing
  file; the operator deletes or moves the earlier run explicitly. Refusal (rather than a
  silent `-2` suffix) is the defensible default: the runbook's workflow is one committed
  capture per claim, and a forced explicit decision is what keeps "the claim and its
  evidence travel together" honest. Exit-code contract updated in the module docstring,
  the ops runbook and the drift sensor.

## Verification addendum

F1/F2/F5 change the capture runner and F3 changes the declared column type, so the
affected verification claims were re-run after the fixes; see the addendum appended to
verification.md.
