# Portfolio Truthful Validation

## Validation: portfolio-truthful - PASS

**Date**: 2026-09-26 (re-verification, iteration 2 of max 3)
**Spec**: `.specs/features/portfolio-truthful/spec.md`
**Diff range**: `main..HEAD` on `feat/portfolio-truthful` (`30520e1`..`2a366ad`, 12 commits: plan + T1–T9 + fixes `00f9ebd` docs, `2a366ad` tests); extended to `30520e1`..`b772cc2` (16 commits) by the T10 addendum below
**Verifier**: independent sub-agent (author ≠ verifier)
**Verdict**: **PASS** — all 16 branch-claimed ACs met; 24/24 mutants killed. Two merge-gate caveats remain by design (TRUTH-19 PR number, TRUTH-12/13 tags).

Iteration 1 (FAIL) found: capture guide keys in a file the containers never read (TRUTH-21), two unlinked workspace items (TRUTH-05), a roadmap test that let a shipped bullet be demoted (surviving mutant), a demo test limited to named slots, no pin on ci.yml action majors, and an RFC-count prose slip. All six are fixed and re-verified below.

---

## Task Completion

| Task | Status | Notes |
| ---- | ------ | ----- |
| T1 | ✅ Done | Live calls via `_live_answer_call`/`_live_teach_call`; offline bind sensor |
| T2 | ✅ Done | Tee + pipefail; failure-only annotation step |
| T3 | ✅ Done | Fix `00f9ebd`: RFC-005/RFC-0007 linked on the three workspace claims; RFC-001 counted as the stack selection |
| T4 | ✅ Done | Fix `2a366ad`: shipped link bound to its `- ✅` bullet; every Demo `docs/media/` embed must resolve |
| T5 | ✅ Done | `CLAUDE.md:9-10` |
| T6 | ✅ Done | Acceptance row PR number pending the PR (merge-gate caveat) |
| T7 | ✅ Done | Fix `00f9ebd`: keys go to `secrets/local-ai.env`, plus a pre-record check that real providers are live |
| T8 | ✅ Done | Fix `2a366ad`: whole-tree action-major pin test |
| T9 | ✅ Done | `test_versions.py` reads the release from the README |

Merge-gate items (TRUTH-12..17, TRUTH-22, TRUTH-23) are correctly declared out of the branch in `tasks.md:319-328` and `spec.md:167-179`. Confirmed untouched remotely in iteration 1: tags `v0.1.0`–`v0.3.0` only, PRs #55/#56/#57 open, repository description unchanged.

---

## Spec-Anchored Acceptance Criteria

### P1: A truthful README

| # | Criterion | Spec-defined outcome | Evidence (`file:line` + assertion / artifact) | Result |
|---|---|---|---|---|
| 1 (TRUTH-01) | Status names current release; no `v3 shipped` | `v0.7.0` in status; string absent | `backend/tests/test_readme_truth.py:42` `assert f"**{_CURRENT_RELEASE}**" in status`; `:43` `assert "v3 shipped" not in _README`; `README.md:5` | ✅ PASS (g1 killed) |
| 2 (TRUTH-02) | RFC-004/005/006/0007 shipped with links; two candidates not scheduled | each RFC link on a shipped bullet | `test_readme_truth.py:56` `assert any(f"]({rfc})" in line for line in shipped_lines)` (`shipped_lines` = lines starting `- ✅`); `:53` file exists; `:62-63` candidates after "Recorded candidates, not scheduled"; `README.md:218-230` | ✅ PASS (g2, n1, g3 killed) |
| 3 (TRUTH-03) | ADR/RFC counts equal files on disk | 30 ADRs, 7 RFCs, read at test time | `test_readme_truth.py:74-75` `int(claim) == len(glob("*.md"))`; `README.md:214` | ✅ PASS (b, b2 killed) |
| 4 (TRUTH-04) | Named versions match pins | Next.js 15, React 19, Python 3.13, PostgreSQL 16 | Docs-only. `README.md:33,44,137-139` vs `frontend/package.json:28,31`, `backend/pyproject.toml:5`, `backend/Dockerfile:8`, `deploy/postgres/Dockerfile:25`, `.github/workflows/ci.yml:34` | ✅ PASS (read) |
| 5 (TRUTH-05) | Workspace section; each item links its ADR/RFC | every item linked | Docs-only. `README.md:111-120`: ADR-0027, ADR-0029, RFC-005 (`:117`), ADR-0028, ADR-0020 + RFC-0007 (`:119`), RFC-0007 (`:120`). All links resolve | ✅ PASS (read) |
| 6 (TRUTH-06) | Absent named media not embedded; pending stated | no dangling embed; pending wording + guide link | `test_readme_truth.py:93` every Demo `docs/media/` embed `is_file()`; `:97` present slot must be embedded; `:99-100` "not recorded yet" + guide link; `docs/media/` holds only `README.md` | ✅ PASS (c, i1, n2, n3 killed) |
| 7 (TRUTH-07) | CLAUDE.md: RFC-0007 complete, post-arc slices current, not v3-driven | per AC | Docs-only. `CLAUDE.md:9-10`; RFC-003 "driving" bullet removed | ✅ PASS (read; release wording is a merge-gate caveat) |
| 8 (TRUTH-08) | A test asserts ACs 1, 2, 3, 6 | assertions reading the README | `backend/tests/test_readme_truth.py:40,49,59,69,88` | ✅ PASS |
| 9 (TRUTH-24) | Manifests equal README release; test asserts both | both `0.7.0` | `backend/tests/test_versions.py:30,36,44-45`; `backend/pyproject.toml:3`, `frontend/package.json:3` | ✅ PASS (e, e2 killed) |

### P1: The nightly's live smoke tests match the adapter

| # | Criterion | Spec-defined outcome | Evidence | Result |
|---|---|---|---|---|
| 1 (TRUTH-09) | Live tests use accepted keywords | no `question=` | `backend/tests/test_answering_anthropic.py:2467,2484,2502` via helpers `:2431-2442`; signature `backend/app/infrastructure/answering/anthropic.py:615-625`. The 2026-09-26 nightly job log shows the old `unexpected keyword argument 'question'` failure | ✅ PASS |
| 2 (TRUTH-10) | Dropping a used keyword fails `-m "not live"` | offline failure | `test_answering_anthropic.py:2456` `signature.bind(object(), **call)`; `:2457` subset assert | ✅ PASS (a, a2 killed) |
| 3 (TRUTH-11) | Credit-exhausted 400 → `::error::` naming the operator action; job still fails | annotation + failure preserved | `backend/tests/test_eval_workflow.py:163-164,169,174-177,183-186`; `.github/workflows/eval.yml:94-95,114-117`. The grep sentence appears 5× in the real 2026-09-26 nightly log | ✅ PASS (d1–d4 killed) |

### P2: RFC-0007 is closed on the record

| # | Criterion | Spec-defined outcome | Evidence | Result |
|---|---|---|---|---|
| 1 (TRUTH-18) | `Accepted` dated `2026-09-27`; Outcome has decision/date/decider/rationale | per AC | Docs-only. `docs/rfc/0007-public-launch-roadmap.md:3,262,264,266,268` | ✅ PASS (read) |
| 2 (TRUTH-19) | Every Action Items row `DONE` with its PR | per AC | `docs/rfc/0007-public-launch-roadmap.md:247-252`; row 247 names "the release-hygiene PR" without a number until the PR exists | ✅ PASS with merge-gate caveat |

### P2: Dependency bumps are current

| # | Criterion | Spec-defined outcome | Evidence | Result |
|---|---|---|---|---|
| 1 (TRUTH-20) | checkout@v6, setup-node@v6, upload-artifact@v7; pin tests assert them | per AC | `backend/tests/test_deploy_workflow.py:233-248` scans every `.github/workflows/*.yml`, `assert seen.get(action) == {major}` for all three actions; also `:228-229` and `backend/tests/test_eval_workflow.py:145`. Artifacts `ci.yml:56,90,112,113,132`, `deploy.yml:61,111`, `eval.yml:55,124` | ✅ PASS (f, f2, h1, h2, n4, n5 killed) |

### P3: Demo media exists and is reproducible

| # | Criterion | Spec-defined outcome | Evidence | Result |
|---|---|---|---|---|
| 1 (TRUTH-21) | Guide runnable against `docker compose up` with a funded key + sample book; no git-ignored claim | procedure works as written | Docs-only. `docs/media/README.md:20` keys go to `secrets/local-ai.env`, which `docker-compose.override.yml:78-81,93-94,102-103` loads into `api`, `worker`, `worker-pdf`; `secrets/` is git-ignored (`.gitignore:9`). `:29` pre-record check that generation is live. `:36-37` compose + `make seed-sample`. `:3` media committed, GIF ≤ 10 MB; `git check-ignore` exits 1 for all slots | ✅ PASS (read) |

**Status**: ✅ 16/16 branch-claimed ACs covered; no open spec-precision gap on the branch.

---

## Discrimination Sensor

Isolated scratch: `git worktree add <scratchpad>/verify-wt HEAD` at `2a366ad`, sharing the backend venv. The worktree run imported its own `app` package, so adapter-side faults were valid. Between mutants: `git checkout -- .` plus `git clean` of the two directories where files were added, with the worktree asserted clean. Baseline in the scratch: 157 passed, 3 deselected across the five target modules.

| # | Mutated location | Description | Failing test | Killed? |
|---|---|---|---|---|
| a | `backend/tests/test_answering_anthropic.py:2432` | `"message"` → `"question"` in the answer helper | `test_live_call_shapes_bind_to_the_adapter_signature` | ✅ |
| a2 | `backend/app/infrastructure/answering/anthropic.py:622` | `generate()` drops `target_section_path` | same | ✅ |
| b | `README.md:214` | `30 [ADRs]` → `31` | `test_engineering_process_counts_match_the_decision_record_directories` | ✅ |
| b2 | `README.md:214` | `7 [RFCs]` → `6` | same | ✅ |
| c | `README.md:11` | embed missing `docs/media/demo.gif` | `test_demo_section_embeds_present_assets_and_declares_the_rest_pending` | ✅ |
| d1 | `.github/workflows/eval.yml:94` | remove `set -o pipefail` | `test_run_step_tees_its_output_and_keeps_pytests_exit_code` | ✅ |
| d2 | `.github/workflows/eval.yml:114` | drop `failure() &&` | `test_balance_step_runs_only_after_a_failure_with_the_key_present` | ✅ |
| d3 | `.github/workflows/eval.yml:90` | `continue-on-error: true` on the run step | `test_nothing_downgrades_the_nightly_failure` | ✅ |
| d4 | `.github/workflows/eval.yml:116` | grep a different sentence | `test_balance_step_emits_an_error_annotation_naming_the_operator_action` | ✅ |
| e | `frontend/package.json:3` | version `0.3.0` | `test_frontend_version_matches_the_readme_release` + lockfile test | ✅ |
| e2 | `backend/pyproject.toml:3` | version `0.3.0` | `test_backend_version_matches_the_readme_release` | ✅ |
| f | `.github/workflows/deploy.yml:61` | `checkout@v6` → `@v4` | `test_docker_action_versions_are_pinned_to_real_majors` + `test_every_workflow_uses_the_current_action_majors` | ✅ |
| f2 | `.github/workflows/eval.yml:124` | `upload-artifact@v7` → `@v4` | `test_artifact_upload_step_is_retained` | ✅ |
| g1 | `README.md:5` | status `v0.7.0` → `v0.6.0` | `test_status_paragraph_names_the_current_release_and_not_a_superseded_one` | ✅ |
| g2 | `README.md:221` | RFC-005 bullet `- ✅` → `- ⏳` (iteration 1 survivor) | `test_roadmap_section_lists_each_shipped_rfc_with_a_link` | ✅ |
| g3 | `README.md:229` | drop the BYO-keys candidate | `test_roadmap_section_names_the_recorded_candidates_as_not_scheduled` | ✅ |
| h1 | `.github/workflows/ci.yml:113` | `setup-node@v6` → `@v4` (iteration 1 survivor) | `test_every_workflow_uses_the_current_action_majors` | ✅ |
| h2 | `.github/workflows/ci.yml:56` | `checkout@v6` → `@v4` (iteration 1 survivor) | same | ✅ |
| i1 | `README.md:11` | embed missing unlisted `docs/media/screenshot-reader.png` (iteration 1 survivor) | demo test | ✅ |
| n1 | `README.md:223` | RFC-0007 shipped bullet loses its link; the link survives on the releases line | roadmap test | ✅ (new per-line assertion) |
| n2 | `README.md:11` | embed a missing named slot `screenshot-ask.png` | demo test | ✅ (new resolve assertion; replaces the removed slot check) |
| n3 | `docs/media/demo.gif` (new file) | present slot left un-embedded | demo test | ✅ |
| n4 | `.github/workflows/extra.yml` (new file) | new workflow with `actions/checkout@v5` | `test_every_workflow_uses_the_current_action_majors` | ✅ (whole-tree scan) |
| n5 | `.github/workflows/eval.yml:124` | `upload-artifact@v7` → `@v6`, new test only | same | ✅ |

**Sensor depth**: lightweight-plus (24 mutants).
**Result**: 24/24 killed - PASS. All four iteration-1 survivors (g2, i1, h1, h2) are now killed.

**Isolation**: the real tree's `git status --porcelain` before the sensor was ` M .specs/LESSONS.md`, ` M .specs/lessons.json`, `?? validation.md`, from the lead's L-028/L-029 recording. After `git worktree remove --force` + `prune` it was identical, and md5 of all three files matched. Side effect: running `uv run` in the worktree against the shared venv repointed its editable install at the worktree. The next `uv run` in the real tree (`make lint`) restored it; `app` resolves to `/home/augusto/projects/learny/backend/app`.

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| Minimum code | ✅ Fixes are two test tightenings, one new 16-line pin test, and wording/link edits |
| Surgical changes | ✅ `_WORKFLOWS_DIR` extraction in `test_deploy_workflow.py` is the only refactor, needed by the new test |
| No scope creep | ✅ |
| Matches patterns | ✅ Same file-assertion style as `test_eval_workflow.py` |
| Spec-anchored outcome check | ✅ AC2 now pins "shipped" per RFC on its own bullet |
| Per-layer Coverage Expectation met | ✅ README ACs 1, 2, 3, 6 each have a discriminating assertion |
| Every test maps to a spec requirement | ✅ New pin test maps to TRUTH-20; the new demo assertion maps to TRUTH-06 |
| Documented guidelines followed | ✅ `CLAUDE.md` verification vocabulary; `make lint` green |

The rewritten demo test dropped the explicit "missing slot not embedded" branch. The general "every embed resolves" loop at `test_readme_truth.py:93` subsumes it, and n2 proves it.

---

## Edge Cases

- [x] A new ADR file fails the count test until the README is updated (`test_readme_truth.py:74`; b killed).
- [x] Dependabot PRs are not touched from the branch; closure is a merge-gate item.
- [x] No homepage URL supplied → homepage stays empty; nothing on the branch sets it.

---

## Gate Check

- **Gate command**: build gate `make lint && make test-backend`. The lead waived re-running the full backend suite; the author reported 2057 + 79 passed and 15 skipped before the fixes.
- **`make lint`** at `2a366ad`: exit 0 (ruff check, ruff format --check 320 files, `tsc --noEmit`, architecture boundaries clean).
- **Targeted modules at `2a366ad`** (`-m "not live"`): 157 passed, 3 deselected (live), 0 failed.
- **Test count delta (targeted)**: `test_answering_anthropic.py` 107 → 108 offline; `test_eval_workflow.py` +4; `test_readme_truth.py` +5 (new); `test_deploy_workflow.py` +1; `test_versions.py` 3 → 3, with the hard-coded `0.3.0` replaced by the README-derived release (not weakened).

---

## Truth Audit (README prose vs repository)

| Claim | Backing | Result |
|---|---|---|
| Versions Next.js 15, React 19, Python 3.13, PostgreSQL 16 | AC4 row | ✅ |
| Every relative README link resolves | scripted check in iteration 1; the three new links point at existing RFC files | ✅ |
| RFC-004/005/006/0007 roadmap bullets | `.specs/project/ROADMAP.md:82-87,102-107,120-125,140-146` | ✅ |
| Workspace claims (page unit 275, `/read` route, invites, ADR-0020 house-profile amendment) | `backend/app/core/config.py:398`, `frontend/app/(read)/sources/[id]/read/page.tsx`, `backend/app/application/invites.py`, `docs/adr/0020-use-anthropic-claude-for-generation.md:235` | ✅ |
| BYO keys 3+ cycles, encryption-at-rest and open-relay problems | `docs/research/2026-09-07/README.md:17` | ✅ |
| "7 RFCs hold the stack selection (RFC-001) and the six roadmap proposals" | `docs/rfc/0001-technology-stack-selection.md` + 0002–0007 | ✅ (fixed) |
| API table rows | `backend/app/infrastructure/web/ai.py:68,84,93`, `study.py:95,114`, `evals.py:201`, `instrument.py:108` | ✅ |
| `v0.4.0`–`v0.7.0` releases (`README.md:218`, `CLAUDE.md:9`) | created at the merge gate (TRUTH-12/13) | ⚠️ caveat: true once the merge gate runs |

---

## Remaining Caveats (merge-gate by design, not failures)

1. **TRUTH-19**: `docs/rfc/0007-public-launch-roadmap.md:247`. Fill in the PR number once the PR is opened.
2. **TRUTH-12/13 dependency**: `README.md:218` and `CLAUDE.md:9` name releases `v0.4.0`–`v0.7.0`. `CLAUDE.md:10` says no roadmap row is open, while `.specs/project/ROADMAP.md:157` still shows `portfolio-truthful` as "Not started". Both become true when the merge-gate tags and releases are cut and the wrap marks the row Done. The merge gate must not be skipped.
3. **Nit, not a gap**: `docs/media/README.md:20` says the override "mounts" `secrets/local-ai.env`. It injects the file via `env_file`, and the effect on the containers is the same.

---

## Requirement Traceability Update

| Requirement | Previous Status | New Status |
| ----------- | --------------- | ---------- |
| TRUTH-01..11, TRUTH-18, TRUTH-20, TRUTH-21, TRUTH-24 | Implementing / Needs Fix | ✅ Verified |
| TRUTH-19 | Implementing | ✅ Verified (PR number at merge gate) |
| TRUTH-12..17, TRUTH-22, TRUTH-23 | Pending (merge gate / operator) | Pending, correctly out of branch scope |

(The Verifier does not edit `spec.md`; the orchestrator applies these statuses.)

---

## Summary

**Overall**: ✅ Ready (subject to the merge-gate checklist)

**Spec-anchored check**: 16/16 branch-claimed ACs matched the spec outcome; 0 open spec-precision gaps on the branch
**Sensor**: 24/24 mutations killed, including all four iteration-1 survivors and five fresh mutants on the new assertions
**Gate**: `make lint` green; targeted modules 157 passed, 0 failed

**Lessons**: already recorded by the orchestrator as L-028/L-029; `lessons.py` was not run by the Verifier.

**Next steps**: open the PR and fill the RFC-0007 row-247 PR number, then run the merge-gate checklist (tags/releases, repo metadata, Dependabot closures) and mark the roadmap row Done at wrap.

---

## T10 addendum — MinIO image built from the official release binary (TRUTH-25)

**Date**: 2026-09-26 (scoped verification of one task added after the iteration-2 PASS)
**Diff range**: `main..HEAD` = `30520e1`..`b772cc2` (16 commits); T10 is commit `b772cc2`. The commits between `2a366ad` and `b772cc2` (`b45b32b`, `48284ce`, `4baba3a`) are docs-only follow-ups, outside this scope.
**T10 verdict**: **PASS**, so the top-level verdict stays **PASS**. One spec-precision gap is flagged below; it is not blocking because the artifact itself satisfies the clause.

### Spec-anchored check

| Clause of TRUTH-25 (`spec.md:127`) | Evidence (`file:line`) | Test assertion | Result |
|---|---|---|---|
| Base Compose builds `minio` from `deploy/minio/` | `docker-compose.yml:105-113` | `backend/tests/test_compose_topology.py:263` `base["minio"]["build"]["context"] == "./deploy/minio"`; `:264` `"image" not in base["minio"]` | ✅ |
| Dockerfile pins a MinIO release | `deploy/minio/Dockerfile:14` `ARG MINIO_RELEASE=RELEASE.2024-10-13T13-34-11Z` | `test_compose_topology.py:266` | ✅ |
| …and its sha256 | `deploy/minio/Dockerfile:20` (digest), `:27` `sha256sum -c -` | `test_compose_topology.py:267`, `:272` | ✅ The digest's correctness is enforced at `docker build`, not by pytest (probe p1). It equals the release's published `.sha256sum` (see reproducibility) |
| …downloads from MinIO's GitHub releases | `deploy/minio/Dockerfile:26` | `test_compose_topology.py:268-271` exact URL template | ✅ |
| Prod overlay runs `ghcr.io/augusto-dmh/learny-minio:${LEARNY_IMAGE_TAG}` | `docker-compose.prod.yml:60` | `backend/tests/test_deploy_topology.py:142` (parametrized `test_prod_app_services_use_the_ghcr_image_ref`) | ✅ |
| Deploy matrix builds it | `.github/workflows/deploy.yml:60-61` | `backend/tests/test_deploy_workflow.py:128` (`test_build_matrix_covers_every_published_image`); runbook list and count tests derive from the matrix | ✅ |
| No non-comment compose/workflow line references a MinIO-controlled registry | Independent grep over all six tracked compose/workflow files: the only non-comment MinIO lines are `ci.yml:65,68` (`learny-minio:ci`, local build), `ci.yml:80` and `docker-compose.yml:118` (health URL), and `docker-compose.prod.yml:60` (GHCR) | `test_compose_topology.py:274-282` scans those files for `quay.io/minio` and `minio/minio` | ✅ artifact / ⚠️ Spec-precision gap: the guard is narrower than the clause (probe p2) |
| (task scope) healthcheck on `/minio/health/live` | `docker-compose.yml:118`; CI wait loop `ci.yml:80` | `test_compose_topology.py:289-290` | ✅ |
| (task scope) runbook names six images | `docs/ops/deploy.md:232` (visibility list), `:258` ("Six images") | `test_deploy_workflow.py` runbook count and list tests | ✅ |
| (task scope) README ADR count | `README.md:214` "31 [ADRs]"; `docs/adr/` holds 31 files | `test_readme_truth.py:74` (passes at `b772cc2`) | ✅ |

### Discrimination sensor

Scratch: `git worktree add <scratchpad>/verify-wt HEAD` at `b772cc2`, shared venv. The tests only parse YAML, so no docker was run. Baseline: 82 passed across `test_compose_topology.py`, `test_deploy_topology.py`, `test_deploy_workflow.py`.

| # | Mutation | Failing test(s) | Result |
|---|---|---|---|
| m1 | `deploy/minio/Dockerfile:27` `sha256sum -c` line removed | `test_minio_builds_from_the_repo_owned_image` | ✅ Killed |
| m2 | base `minio` build block replaced by `image: quay.io/minio/minio:latest` | `test_minio_builds_from_the_repo_owned_image`, `test_base_app_services_still_build_from_source` | ✅ Killed |
| m3 | `learny-minio` dropped from the deploy matrix | `test_build_matrix_covers_every_published_image`, `test_every_ghcr_image_the_prod_overlay_runs_is_published`, `test_the_runbook_lists_every_published_image_for_the_visibility_flip`, `test_the_runbook_states_the_right_number_of_published_images` | ✅ Killed |
| m4 | healthcheck back to `["CMD", "mc", "ready", "local"]` | `test_minio_healthcheck_uses_the_health_endpoint` | ✅ Killed |
| m5 | `docs/ops/deploy.md:258` "Six images" → "Five images" | `test_the_runbook_states_the_right_number_of_published_images` | ✅ Killed |
| m6 | prod overlay back to `quay.io/minio/minio:RELEASE.2024-10-13T13-34-11Z` | `test_minio_builds_from_the_repo_owned_image`, `test_prod_app_services_use_the_ghcr_image_ref[minio-…]` | ✅ Killed |
| m7 | `ci.yml:68` Start MinIO runs the quay image again | `test_minio_builds_from_the_repo_owned_image` | ✅ Killed |
| m8 | Dockerfile URL moved to `dl.min.io` | `test_minio_builds_from_the_repo_owned_image` | ✅ Killed |
| m9 | `docs/ops/deploy.md:232` visibility list drops `learny-minio` | `test_the_runbook_lists_every_published_image_for_the_visibility_flip` | ✅ Killed |
| p1 | probe: pinned digest altered | none | Survived. Expected: a wrong digest fails `docker build` at `sha256sum -c` in CI's Start MinIO and compose-smoke jobs, and pytest cannot check it offline without downloading the ~104 MB binary. The committed digest was checked by hand against the published checksum |
| p2 | probe: override gains a non-comment `image: minio/mc:latest` (Docker Hub, MinIO-controlled) | none (`-k test_minio_builds_from_the_repo_owned_image`) | ❌ Survived → spec-precision gap |

**Result**: 9/9 task mutants killed - PASS. Probe p1 is a build-time-enforced limit. Probe p2 is a hardening item.

**Isolation**: the real tree's `git status --porcelain` was empty before and identical after `git worktree remove --force` + `prune`. `make lint` was run in the real tree afterwards (exit 0) and restored the editable install; `app` resolves to `/home/augusto/projects/learny/backend/app`. Post-cleanup in the real tree: `test_readme_truth.py` + the three topology/workflow modules give 87 passed.

### ADR-0031 claims, reproduced from this session (curl/gh, no docker)

| Claim (`docs/adr/0031-build-minio-from-the-official-release-binary.md:12,14`) | Probe | Observed |
|---|---|---|
| `dl.min.io` answers 410 for the server binary (as for `mc`) | `curl -I` on `…/server/minio/release/linux-amd64/archive/minio.RELEASE.2024-10-13T13-34-11Z`, `…/linux-amd64/minio`, `…/client/mc/release/linux-amd64/mc` | 410, 410, 410 ✅ |
| `quay.io/minio/minio` refuses anonymous pulls for the pinned tag while other public quay repos pull | anonymous registry token then manifest GET | `minio/minio:RELEASE.2024-10-13T13-34-11Z` → 401 `UNAUTHORIZED`; control `prometheus/prometheus:latest` → 200 ✅ |
| GitHub release assets exist for the pinned tag, with a checksum per asset | `gh release view RELEASE.2024-10-13T13-34-11Z -R minio/minio`; `curl -I -L` on the binary; fetch `.sha256sum` | `minio.linux-amd64.RELEASE.2024-10-13T13-34-11Z` (104,063,128 bytes) → 200; its `.sha256sum` reads `1126bbb3276321e7fed0167682d92a03572862f73802658f616af43d9a951e6a`, **identical** to `deploy/minio/Dockerfile:20` ✅ |

"For later ones" (later releases also publish assets) was not probed.

### Gaps and caveats (T10)

1. **[Spec-precision, non-blocking]** `backend/tests/test_compose_topology.py:282` guards only `quay.io/minio` and `minio/minio`, while `spec.md:127` forbids any MinIO-controlled registry. A Docker Hub `minio/mc`, a `docker.io/minio/...`, or a `dl.min.io` fetch in a workflow would pass (probe p2). No such line exists today. Hardening: match `quay.io/minio`, `dl.min.io`, and any image reference whose namespace is `minio/` (excluding `learny-minio` and `./deploy/minio`).
2. **[Operator, merge gate]** GHCR creates `learny-minio` as a private package on its first push. The VPS pulls anonymously, so the first deploy after merge fails until the package is flipped to Public. This is already listed at `docs/ops/deploy.md:232`; it belongs on the merge-gate checklist.
3. **[Note]** The Dockerfile fetches `linux-amd64` only, which matches GitHub's `ubuntu-latest` runners and the amd64 VPS. An arm64 host would need a second pinned asset and digest.
