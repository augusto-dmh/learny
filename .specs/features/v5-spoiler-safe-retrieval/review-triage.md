# Review Triage — v5-spoiler-safe-retrieval (PR #70)

Reviewer: fresh-context `pr-review` subagent (6 lanes), 2026-09-08. CI 4/4 green at review time.
This file is the surviving record of the review reasoning; the PR comments are scaffolding and
are deleted after fixes land.

| # | Source comment | Where | Verdict | Action | Rationale |
| --- | --- | --- | --- | --- | --- |
| F1 | ⚠️ tests: fail-closed parity on a failing position read is implemented but unpinned (`#discussion_r3960711861`) | `backend/app/application/retrieval.py:187` | **Real** | **Fix** (test) | The dimensions sweep in the spec makes "position-repo read failure propagates, never degrades to unfiltered" a requirement (AD-349 parity), and it has no sensor: a future defensive `try/except` would silently reintroduce the fail-open spoiler path with the suite green — precisely the bug class this cycle kills. Verified in code: no `try/except` around the read today, and no test asserts propagation. Cheap, local, test-only. |
| F2 | 💡 architecture: stale-bound warning carries context only in `extra=`; human dev format drops it (`#discussion_r3960711728`) | `backend/app/infrastructure/db/retrieval.py:375` | **Real** | **Fix** (code + 2 assertion updates) | Verified: the warning is a bare event name; `LEARNY_LOG_FORMAT` defaults to `human` (`app/core/logging.py:161`) whose format string has no attribute accessor, so in the default dev setup the warning is unattributable — undermining SPOILER-14's diagnosability purpose. Interpolating the identifiers via lazy %-formatting (keeping `extra=` for the JSON formatter) is a small, contained improvement; the two `getMessage()` assertions in `test_retrieval.py` update with it. |
| F3 | Requirements accuracy note 1: spec's out-of-scope row claims the eval path does not use the retrieval seam, but `tests/eval_runner.py` wires the real service + adapter (`issuecomment-5589451672`) | `.specs/features/v5-spoiler-safe-retrieval/spec.md` Out of Scope | **Real** (docs inaccuracy) | **Fix** (spec wording) | Verified: `eval_runner.py:228-230` constructs the real `RetrieveEvidence` over `SqlAlchemyRetrievalRepository`. Behaviorally inert (flag default-off, never passed by the runner — T3 worker's report agrees), but the spec sentence is wrong at the seam level and a later cycle could rely on it. Correct the row in `.specs/` (internal doc, not PR-facing). |
| F4 | Requirements accuracy note 2: 4 code commits for 3 spec tasks — mild deviation from one-commit-per-task (`issuecomment-5589451672`) | commit history | **Real but accepted** | **Won't-fix** | Deliberate, recorded decision: the two edge-case tests were a post-Verifier nuance fix dispatched as its own unit and committed on its own — the ship-cycle cost discipline explicitly sanctions per-dispatched-unit chores, and the previous cycle set the same precedent (non-blocking Verifier nuances fixed as separate commits). The per-task atomicity rule governs task workers, not post-verification nuance fixes. |
| F5 | Definition of Done: spec.md Goals/Success checkboxes unticked; traceability statuses stale (`issuecomment-5589451672`) | `.specs/features/v5-spoiler-safe-retrieval/spec.md` | **Real** (bookkeeping) | **Fix** (docs) | tlc's task-completion step requires updating spec traceability; the workers ticked `tasks.md` only. Tick the boxes the gate evidence supports and move traceability statuses to their terminal values. |

**Counts**: 5 findings — 4 real actionable (2 code-level, 2 spec-doc), 1 real-but-won't-fix
(recorded decision). 0 false.

**Post-fix gates**: full backend suite with DSN (only the known pre-existing
`test_eval_retrieval_metrics` threshold failure tolerated — proven local-env-only: it passes in
CI's fresh Postgres), `ruff check` + `ruff format --check`, fitness boundaries. Push after green.
