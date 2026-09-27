# Portfolio Truthful Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user - do not proceed without it.**

---

**Design**: none — Medium scope, design inline (docs + one test module + one workflow step)
**Status**: Approved (ship-cycle auto-approval, recommended options recorded in `context.md`)

---

## Test Coverage Matrix

> Generated from codebase, project guidelines, and spec - confirm before Execute. Guidelines found: `CLAUDE.md` (verification vocabulary: `make lint`, `make test-backend`, `make check`), `CONTRIBUTING.md`, `backend/pyproject.toml` (`live`/`eval` markers), `.specs/codebase/CONVENTIONS.md`.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
|---|---|---|---|---|
| Live smoke tests (`backend/tests/test_answering_anthropic.py`) | unit (offline sensor) | Every AC of the nightly-smoke story: current signature used; a keyword drift fails offline | `backend/tests/test_answering_anthropic.py` | `cd /home/augusto/projects/learny/backend && uv run pytest tests/test_answering_anthropic.py -m "not live" -q` |
| Workflow files (`.github/workflows/eval.yml`) | unit (file assertions, precedent `test_eval_workflow.py`) | The credit-exhausted annotation step exists, runs on failure, and the job still fails | `backend/tests/test_eval_workflow.py` | `cd /home/augusto/projects/learny/backend && uv run pytest tests/test_eval_workflow.py -q` |
| README truth claims | unit (file assertions, precedent `test_ops_docs.py`) | ACs 1, 2, 3, 6 of the README story, each as its own assertion | `backend/tests/test_readme_truth.py` | `cd /home/augusto/projects/learny/backend && uv run pytest tests/test_readme_truth.py -q` |
| Prose docs (`README.md`, `CLAUDE.md`, `docs/rfc/0007-*.md`, `docs/media/README.md`) | none | build gate only (the README drift test covers the README) | - | build gate only |

## Gate Check Commands

> Generated from codebase - confirm before Execute.

| Gate Level | When to Use | Command |
|---|---|---|
| Quick | After a task touching one test module | `cd /home/augusto/projects/learny/backend && uv run pytest <module> -q` |
| Full | After tasks with DB-backed tests (none this cycle) | `cd /home/augusto/projects/learny && make infra && make test-backend` |
| Build | After phase completion or docs-only tasks | `cd /home/augusto/projects/learny && make lint && make test-backend` |

---

## Execution Plan

Phases are ordered and run sequentially - each phase completes before the next begins, and tasks within a phase execute in order.

### Phase 1: The nightly means what it says

```
T1 → T2
```

### Phase 2: Truthful documents

Executed in order T3, T4, T5, T6, T7; only the arrows below are dependencies.

```
T3 → T4
T3 → T5
T3 → T7
T6
```

### Phase 3: Versions and dependencies

```
T8
T3 → T9
```

---

## Task Breakdown

### T1: Repair the live smoke tests and pin their call shape offline ✅ Complete

**What**: The three live smoke tests call `AnthropicGenerationAdapter.generate` with the keywords its signature accepts, and an offline test proves that the keywords the live tests use are accepted by the current signature (so a future drift fails `pytest -m "not live"`).
**Where**: `backend/tests/test_answering_anthropic.py`
**Depends on**: None
**Reuses**: the module's `_evidence` helper and `MODE_ANSWER`/`MODE_TEACH` constants; the offline call shapes at lines 165–415
**Requirement**: TRUTH-09, TRUTH-10

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `test_live_answer_returns_cited_prose` and `test_live_irrelevant_evidence_returns_sentinel_not_found` no longer pass `question=`; they use the same shape as the offline answer tests.
- [x] An offline test binds the live tests' call keywords to the adapter signature so that removing or renaming one of those keywords fails offline (the sensor must not merely re-state the signature; it must exercise the live tests' own argument set). Proven: renaming `message`→`question` in the helper fails `test_live_call_shapes_bind_to_the_adapter_signature` offline.
- [x] Gate check passes: quick gate on `tests/test_answering_anthropic.py -m "not live"` — 108 passed, 3 deselected.
- [x] Test count: 107 → 108 offline (no silent deletions).

**Tests**: unit
**Gate**: quick

**Commit**: `fix(eval): call the live smoke tests with the adapter's current signature`

---

### T2: Name the operator action when the nightly dies on an exhausted balance ✅ Complete

**What**: The nightly job captures pytest output and, when the run failed and the output carries Anthropic's credit-exhausted message, emits a `::error::` annotation that names the action (fund `LEARNY_ANTHROPIC_API_KEY`'s account) while the job still fails.
**Where**: `.github/workflows/eval.yml`
**Depends on**: T1
**Reuses**: the existing `steps.secret.outputs.present` gating; `backend/tests/test_eval_workflow.py` assertions style
**Requirement**: TRUTH-11

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] The pytest step's output is preserved for a later step without changing its exit code.
- [x] A step guarded by `if: failure()` (and the secret gate) greps for the credit-exhausted message and emits `::error::` naming the operator action; it never masks the failure.
- [x] `backend/tests/test_eval_workflow.py` asserts the annotation step's presence, its `failure()` guard, and that no step downgrades the job's failure (e.g. no `continue-on-error` on the pytest step).
- [x] Gate check passes: quick gate on `tests/test_eval_workflow.py`.

**Tests**: unit
**Evidence**: quick gate 16 passed (test_eval_workflow.py); build gate: make lint green, backend suite 2057 passed + 79 storage-module passes after MinIO came up (env-only failures), 15 skipped
**Gate**: build

**Commit**: `ci(eval): name the operator action when the nightly dies on an exhausted balance`

---

### T3: Bring the README to the state of `main` ✅ Complete

**What**: Rewrite the README's status paragraph, Demo section, Engineering process paragraph, Roadmap section, and add a "Reading-first workspace" section, so every version, count, and shipped claim matches the repository at PR #71.
**Where**: `README.md`
**Depends on**: None
**Reuses**: `.specs/project/ROADMAP.md` tables (v4–v7 rows) for the shipped list; ADR/RFC file names for links
**Requirement**: TRUTH-01, TRUTH-02, TRUTH-03, TRUTH-04, TRUTH-05, TRUTH-06

**Tools**:

- MCP: NONE
- Skill: `docs-writer`

**Done when**:

- [x] Status paragraph names `v0.7.0`; the string `v3 shipped` is gone.
- [x] Roadmap section lists RFC-004/005/006/0007 as shipped with links, plus the two recorded, unscheduled candidates.
- [x] Engineering process paragraph states the ADR and RFC counts equal to the files under `docs/adr/` and `docs/rfc/`.
- [x] Every named version (Next.js, React, Python, PostgreSQL) matches its manifest or compose tag.
- [x] A "Reading-first workspace" section covers reader hub + Chat dock, page unit, position-bound retrieval, learner-chosen AI profiles, safety rails — each linking its ADR/RFC.
- [x] Demo section embeds nothing that is absent from `docs/media/` and says the capture is pending, linking the guide.
- [x] Gate check passes: build gate.

**Tests**: none
**Evidence**: build gate as T2; README drift test (T4) passes on this text
**Gate**: build

**Commit**: `docs(readme): describe the repository as it is after the public-launch arc`

---

### T4: Pin the README's truth claims with a test ✅ Complete

**What**: A test module reads `README.md` and asserts the release name, the shipped-RFC list, the ADR/RFC counts against the filesystem, and that no `docs/media/` embed points at a missing file.
**Where**: `backend/tests/test_readme_truth.py`
**Depends on**: T3
**Reuses**: `backend/tests/test_ops_docs.py` (repo-root path resolution, file-reading assertion style)
**Requirement**: TRUTH-08

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] One test per README AC 1, 2, 3, 6 — four tests, each failing on the specific drift it names (a wrong count, a missing RFC link, a stale release string, a dangling image).
- [x] The count assertions read `docs/adr/` and `docs/rfc/` at test time, not a hard-coded number.
- [x] Gate check passes: quick gate on `tests/test_readme_truth.py`.

**Tests**: unit
**Evidence**: quick gate 5 passed; sensor: a stale count or release string fails the module
**Gate**: quick

**Commit**: `test(docs): fail the suite when the readme drifts from the repository`

---

### T5: Bring `CLAUDE.md`'s Current Status to the same state ✅ Complete

**What**: Replace the Current Status bullets that describe v3 as the driving roadmap with bullets naming RFC-004 through RFC-0007 as shipped, the post-arc slices as the current state, and the recorded candidates.
**Where**: `CLAUDE.md`
**Depends on**: T3
**Reuses**: the README Roadmap section wording (T3)
**Requirement**: TRUTH-07

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Current Status names RFC-0007 complete and the two post-arc slices merged; no bullet says v3 work is driven by RFC-003.
- [x] The operational and constraints sections are untouched except where they name a stale version.
- [x] Gate check passes: build gate.

**Tests**: none
**Evidence**: build gate as T2 (docs only)
**Gate**: build

**Commit**: `docs: bring the project context file to the current roadmap state`

---

### T6: Close RFC-0007 on the record ✅ Complete

**What**: Fill RFC-0007's Status line, Outcome block, and Action Items table with the decisions and PRs that closed them.
**Where**: `docs/rfc/0007-public-launch-roadmap.md`
**Depends on**: None
**Reuses**: the ROADMAP v7 table for the PR numbers
**Requirement**: TRUTH-18, TRUTH-19

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Status reads `Accepted (2026-09-27)`; Outcome names decision, date, decider, rationale.
- [x] Every Action Items row reads `DONE` with its closing PR.
- [x] Gate check passes: build gate.

**Tests**: none
**Evidence**: build gate as T2 (docs only)
**Gate**: build

**Commit**: `docs(rfc): close the public-launch roadmap on the record`

---

### T7: Make the demo capture guide runnable and honest ✅ Complete

**What**: Rewrite `docs/media/README.md` so it describes a capture against `docker compose up` with a funded Anthropic key and the public-domain sample book, names the four committed asset files, and drops the false claim that media is git-ignored.
**Where**: `docs/media/README.md`
**Depends on**: T3
**Reuses**: the README Demo section (T3) for the embed paths; `docs/ops/` for the compose invocation
**Requirement**: TRUTH-21

**Tools**:

- MCP: NONE
- Skill: `docs-writer`

**Done when**:

- [x] Prerequisites name the key and the sample book; steps are runnable in under thirty minutes on Linux.
- [x] The "Not committed" paragraph is gone; the guide states the assets are committed and size-capped (GIF ≤ 10 MB).
- [x] Gate check passes: build gate.

**Tests**: none
**Evidence**: build gate as T2 (docs only)
**Gate**: build

**Commit**: `docs(media): make the demo capture guide runnable against the current stack`

---

### T8: Apply the pending GitHub Actions major bumps with their pin tests

**What**: Every workflow uses `actions/checkout@v6`, `actions/setup-node@v6`, and `actions/upload-artifact@v7`, and the tests that pin action majors assert those versions.
**Where**: `.github/workflows/` (ci.yml, deploy.yml, eval.yml) and the pin assertions in `backend/tests/test_deploy_workflow.py` / `backend/tests/test_eval_workflow.py`
**Depends on**: None
**Reuses**: Dependabot PRs #55–#57 as the diff reference (same bumps)
**Requirement**: TRUTH-20

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `grep -rn "uses: actions/" .github/workflows` shows only `checkout@v6`, `setup-node@v6`, `upload-artifact@v7`.
- [ ] The pin tests assert the new majors (and would fail on `@v4`).
- [ ] Gate check passes: quick gate on `tests/test_deploy_workflow.py tests/test_eval_workflow.py`.

**Tests**: unit
**Gate**: quick

**Commit**: `build(ci): move to the current majors of checkout, setup-node, and upload-artifact`

---

### T9: Declare the release version in both package manifests ✅ Complete

**What**: `backend/pyproject.toml` (with `uv.lock`) and `frontend/package.json` (with `package-lock.json`) declare `0.7.0`, and `backend/tests/test_versions.py` asserts both equal the README's current release.
**Where**: the two package manifests and their lock files, plus `backend/tests/test_versions.py`
**Depends on**: T3
**Reuses**: `uv version 0.7.0`; `npm version 0.7.0 --no-git-tag-version`
**Requirement**: TRUTH-24

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Both manifests and both lock files carry `0.7.0`.
- [x] `test_versions.py` reads the release from the README status paragraph and asserts both manifests equal it (no hard-coded `0.3.0` remains).
- [x] Gate check passes: build gate.

**Tests**: unit
**Evidence**: quick gate 3 passed (test_versions.py); uv lock --check clean
**Gate**: build

**Commit**: `build: declare version 0.7.0 in the backend and frontend manifests`

---

## Merge-gate checklist (not branch tasks — remote, run after Stage 7 approval)

These carry requirement IDs but are executed against `origin`/GitHub only after the user approves the merge; they are recorded here so the Verifier and the wrap report can account for them.

| Item | Requirement | Command sketch |
|---|---|---|
| Tags + releases `v0.4.0` (#45 `1b85c61`), `v0.5.0` (#58 `b8b3d30`), `v0.6.0` (#70 `0b04a6c`), `v0.7.0` (merge commit) | TRUTH-12, 13, 14 | `git tag vX.Y.0 <sha> && git push origin vX.Y.0 && gh release create vX.Y.0 --generate-notes --notes-start-tag <prev> --notes-file <body>` |
| Repo description + topics (+ homepage if supplied) | TRUTH-15, 16, 17 | `gh repo edit --description ... --add-topic ...` |
| Dependabot #55/#56/#57 closed as superseded by this PR | TRUTH-23 | `gh pr close N --comment "Superseded by #<this PR>, which applies the same bump together with the tests that pin the action majors."` |
| Demo capture (needs a funded key) + README embeds | TRUTH-22 | per `docs/media/README.md`; a follow-up commit on `main` |

---

## Phase Execution Map

```
Phase 1 → Phase 2

Phase 1:  T1 ------→ T2
Phase 2:  T3 ------→ T4
          T3 ------→ T5
          T6
          T3 ------→ T7
Phase 3:  T8
          T3 ------→ T9
```

Nine tasks — executed inline (the ship-cycle orchestrator is the single worker); the Verifier runs as a fresh sub-agent after T9.

## Task Granularity Check

| Task | Scope | Status |
|---|---|---|
| T1 | 1 test module | ✅ Granular |
| T2 | 1 workflow file (+ its test module) | ✅ Granular |
| T3 | 1 file | ✅ Granular |
| T4 | 1 test module | ✅ Granular |
| T5 | 1 file | ✅ Granular |
| T6 | 1 file | ✅ Granular |
| T7 | 1 file | ✅ Granular |
| T8 | 1 dependency bump (3 workflow files + 2 pin assertions) | ⚠️ cohesive: one bump, one commit |
| T9 | 1 version bump (2 manifests + locks + 1 test) | ⚠️ cohesive: one bump, one commit |

## Diagram-Definition Cross-Check

| Task | Depends On (task body) | Diagram Shows | Status |
|---|---|---|---|
| T1 | None | start of Phase 1 | ✅ Match |
| T2 | T1 | T1 → T2 | ✅ Match |
| T3 | None | start of Phase 2 | ✅ Match |
| T4 | T3 | T3 → T4 | ✅ Match |
| T5 | T3 | T3 → T5 | ✅ Match |
| T6 | None | standalone | ✅ Match |
| T7 | T3 | T3 → T7 | ✅ Match |
| T8 | None | standalone | ✅ Match |
| T9 | T3 | T3 → T9 | ✅ Match |

## Test Co-location Validation

| Task | Code Layer Created/Modified | Matrix Requires | Task Says | Status |
|---|---|---|---|---|
| T1 | live smoke tests | unit | unit | ✅ OK |
| T2 | workflow file | unit | unit | ✅ OK |
| T3 | prose docs | none | none | ✅ OK |
| T4 | README truth test | unit | unit | ✅ OK |
| T5 | prose docs | none | none | ✅ OK |
| T6 | prose docs | none | none | ✅ OK |
| T7 | prose docs | none | none | ✅ OK |
| T8 | workflow files | unit | unit | ✅ OK |
| T9 | manifests + version test | unit | unit | ✅ OK |
