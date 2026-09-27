# Review triage — PR #72 (`portfolio-truthful`)

Comments fetched 2026-09-27 from the pr-review lanes (8 inline, 1 PR-level). Each finding was checked against the code on `feat/portfolio-truthful` at `697f973`. Comments are deleted after the fixes land; this file is the surviving record.

| # | Source comment | File:line | Verdict | Action | Rationale |
|---|---|---|---|---|---|
| 1 | 4113838779 (architecture) | README.md:220 | real | fix | RFC-005 and RFC-006 still read `Status: Draft` with empty Outcome blocks while the README, CLAUDE.md, and RFC-0007's rationale call them shipped. Same drift RFC-0007 was closed for. Close both retroactively with the PRs that delivered each cycle (RFC-005 A–F: #47, #59, #60, #61, #62, #70; RFC-006 A–E: #49, #51, #52, #53+#54, #58). |
| 2 | 4113841854 (tests) | backend/tests/test_readme_truth.py:56 | real | fix | The ✅ sensor never reads the linked RFC. Derive the shipped links from the ✅ bullets themselves and assert each linked RFC's status line begins with `Accepted`, so #1 cannot recur silently. |
| 3 | 4113841905 (tests) | backend/tests/test_deploy_workflow.py:246 | real | fix | The `@v\d+` regex ignores `@main` or SHA refs (verified by the lane's mutation). Capture every ref, require the `vN` form, and judge N against a floor per action instead of an exact pin — a floor also stops the exact-pin test from failing the next Dependabot major (the trap this PR is fixing). |
| 4 | 4113841977 (tests) | backend/tests/test_answering_anthropic.py:2445 | real | fix | Nothing forces a live test to call through the helpers; a future `generate(question=…)` in a live test would again wait for a funded nightly. Add an AST check that every `test_live_*` call to `generate` unpacks a `_live_*_call` helper. Drop the redundant second assertion. |
| 5 | 4113841996 (tests) | backend/tests/test_readme_truth.py:19 | real | fix | `_CURRENT_RELEASE` is a fourth copy of the version; `test_versions.py` already pins README ↔ manifests. Derive it from `backend/pyproject.toml`. |
| 6 | 4113848206 (regression) | backend/tests/test_eval_workflow.py:154 | real | fix | Wrong date. `gh run list` shows the last green nightly on 2026-07-26 and 62 consecutive failures from 2026-07-27 (the `question=` TypeError, one day after the keyword was dropped), with the credit-exhausted 400 joining by 2026-08-15. Fix the test comment, context.md, spec.md, STATE.md, and the PR body. The two pushed commit messages that carry the wrong date stay as they are (history is not rewritten); this row records the correction. |
| 7 | 4113848238 (regression) | backend/tests/test_deploy_workflow.py:235 | real | fix | `checkout` and `setup-node` are at v7; the v6 pins are Dependabot's proposals and land as-is, but the test and commit wording "current majors" is false. Fixed together with #3: the test becomes a floor ("at least the majors these PRs adopted"), so a v7 bump PR goes green. Not bumping to v7 here — that is Dependabot's next PR, now able to pass. |
| 8 | 4113848269 (regression) | README.md:224 | real | fix | The rewrite dropped the ADR-0024 / ADR-0025 links and the "Operational runbooks live in docs/ops/" sentence, none of which were carried elsewhere. Restore both in the RFC-003 bullet and the engineering-process paragraph. |
| 9 | 5852021983 (requirements, PR-level) | — | real (notes) | fix wording | ✅ 16 / ❌ 0 / 🔲 8 (the 🔲 are the merge-gate items by design). Its one wording note is right: the PR body says Dependabot #56 "could never go green" while it was green; reword to #55/#57. The v0.4.0–v0.7.0 "released" claims and "no roadmap row open" are merge-gate-dependent by design (recorded in validation.md). |
| — | Verifier T10 caveat (not a PR comment) | backend/tests/test_compose_topology.py:282 | real | fixed in 697f973 | Registry guard widened to `minio/mc` and `dl.min.io`. The GHCR `learny-minio` package is private on first push — flip at the merge gate (report item). |

Lanes with no findings: security (0 comments; annotation string is fixed, log never uploaded), performance (0 comments). Consolidation comment, if posted, is deleted with the rest.

## Delta pass (posted after the first cleanup, against `340c71b`)

The review lanes re-ran on the MinIO commits and the four review-fix commits and posted 6 inline + 2 PR-level comments. Same procedure.

| # | Source comment | File:line | Verdict | Action | Rationale |
|---|---|---|---|---|---|
| 10 | 4113877621 (security) | deploy/minio/Dockerfile:33 | real | fix (document) | The server runs as root like the upstream image; parity, not a regression, but undocumented. Recorded in the Dockerfile header and as an ADR-0031 consequence with the follow-up (chown of existing volumes + `USER`). Not dropping privileges in this PR: it is a data-volume migration. |
| 11 | 4113879024 (tests) | backend/tests/test_compose_topology.py:301 | real | fix | The healthcheck test did not pin `-f`; without it a 503 counts as healthy for every `up --wait`. The test now asserts the exact command and that the Dockerfile installs curl. |
| 12 | 4113879065 (tests) | backend/tests/test_compose_topology.py:267 | real | fix | Presence-only assertions accepted an empty digest. Release stamp and 64-hex digest are now matched by shape. |
| 13 | 4113880450 (architecture) | docs/ops/deploy.md:258 (README.md:176) | real | fix | README's deployment section still said "three images" from v2. Corrected to six with the brace list, and a drift test derives both from the deploy matrix. |
| 14 | 4113880493 (architecture) | backend/tests/test_compose_topology.py:290 | real | fix | The CI test re-derived the `ci.yml` path and loader the module owns and took an unused fixture. Uses `_load(_CI)`; `_MINIO_DOCKERFILE` constant mirrors `_PG_DOCKERFILE`. |
| 15 | 4113881535 (regression) | .specs/features/portfolio-truthful/spec.md:183 | real | fix | The coverage line counted a TRUTH-25 row the table never got (the earlier replace missed because the anchor row had already been marked). Row added. |
| 16 | 5852119739 (requirements, PR-level) | — | real | fix | ✅ 18 / ❌ 2 / 🔲 12; its two ❌ are #13 and #15. |
| 17 | 5852138004 (summary, PR-level) | — | — | delete | Consolidation of the above. |

Also from the owner at the merge gate: no public instance is hosted yet, so the README status sentence now says the production path is built and exercised in CI rather than implying a running deployment; and the branch's 21 commits carried the corporate author email from the global git config — the repository-local identity is now the personal address for every later commit; rewriting the 21 earlier commits (history rewrite + force-push) was left to the owner's decision, and the merge commit itself carries the personal identity.
