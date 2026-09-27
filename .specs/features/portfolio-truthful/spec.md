# Portfolio Truthful Specification

## Problem Statement

Learny's engineering is four roadmaps ahead of its public face: the README, the latest release (`v0.3.0`), the repository metadata, and the demo slots all describe the v3 state, while `main` carries RFC-004 through RFC-0007 plus two post-arc slices (PRs #36–#71). The nightly eval has failed every day since 2026-09-22 — half on an exhausted Anthropic balance, half on two live tests whose call shape rotted when the adapter signature changed and no offline test noticed. For a project whose stated purpose is to be shown in interviews, the first sixty seconds on GitHub currently misrepresent it.

## Goals

- [ ] The README, `CLAUDE.md`, and RFC-0007's outcome describe the state of `main` as of PR #71, with no claim older than the code.
- [ ] Every RFC arc that completed since `v0.3.0` has a tagged GitHub release with generated notes, and the current state is `v0.7.0`.
- [ ] The repository's description, topics, and homepage on GitHub describe the product, not a research placeholder.
- [ ] The live Anthropic smoke tests call the adapter with its current signature, and a future signature drift fails the offline suite, not only the nightly.
- [ ] The three open Dependabot PRs are green and merged, or closed with a recorded reason.
- [ ] The demo media slots are real files committed under `docs/media/`, with a capture procedure the operator can rerun in under thirty minutes.

## Out of Scope

| Feature | Reason |
|---|---|
| Any product feature (economy-profile promotion, BYO keys) | Presentation cycle only; the recorded candidates keep their own roadmap rows |
| Recharging the Anthropic balance or the nightly's judge baselines | Operator billing action; the cycle makes the failure legible, not paid |
| A changelog file | GitHub releases with generated notes are the changelog; a second copy drifts |
| Rewriting ADR/RFC prose beyond RFC-0007's outcome block | Decision records are historical; only the open outcome is a lie by omission |
| Retrospectives for v4–v7 | Calendar-bound documents in their own right; not needed for a truthful README |

---

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
|---|---|---|---|
| Where demo media lives | Committed under `docs/media/` (PNG stills + one GIF ≤ 10 MB), `.gitignore` untouched (it never excluded them; `docs/media/README.md` claimed it did) | GitHub renders repo-relative images in the README; release-attached media breaks when the README is read from a clone. Rejected: external CDN (one more thing to rot) | auto (AD-357) |
| Demo capture needs real Claude answers | The capture task is operator-gated on a funded `LEARNY_ANTHROPIC_API_KEY`; until it runs, the README's demo section states plainly that media is pending and links the capture guide — the commented-out embeds stay out | A deterministic-adapter demo would show extractive answers as if they were the product. Rejected: record with deterministic adapters | auto (AD-358) |
| Release numbering for the four arcs shipped since `v0.3.0` | Retroactive lightweight tags at each arc's completion merge, numbered by completion date: `v0.4.0` = RFC-004 (#45), `v0.5.0` = RFC-006 (#58), `v0.6.0` = RFC-005 (#70), `v0.7.0` = RFC-0007 + this cycle (HEAD after merge); notes generated per range | Precedent: `v0.3.0` was cut retroactively at the RFC-003 completion merge. Version order must follow commit order, so RFC-006 (July) precedes RFC-005 (September). Rejected: one `v0.7.0` only (hides three arcs from the release list) | auto (AD-359) |
| Nightly eval on an exhausted balance | Keep the schedule and keep failing loudly; add no skip. The workflow's failure stays a real signal. The signature-rotted tests are fixed and pinned offline | A green-by-skip nightly is the dishonest state this cycle exists to remove. Rejected: `workflow_dispatch`-only (loses the daily regression signal once credit returns) | auto (AD-360) |
| Dependabot PRs #55/#57 fail `backend-test` | The bumps are applied in this cycle (checkout v6, setup-node v6, upload-artifact v7) together with the tests that pin the action majors; the three PRs are closed at the merge gate with a comment naming this PR as the superseding change | The failures are real: `test_deploy_workflow.py` and `test_eval_workflow.py` pin `@v4` literally, so a Dependabot branch can never go green on its own. Rejected: rebasing (the pin test fails on any rebase), editing Dependabot's branches (three PRs to babysit for one line each) | auto (AD-361, revised after reading the failing job) |
| Deployed instance URL for the repo homepage | Left blank until the operator supplies it at the merge gate | Only the operator knows whether the VPS instance is meant to be public | n — asked at Stage 7 |

**Open questions:** none - all resolved or logged above.

---

## User Stories

### P1: A truthful README ⭐ MVP

**User Story**: As an interviewer opening the repository, I want the README to describe what the code on `main` actually does so that what I read matches what I would find.

**Why P1**: The README is the product's front page; today it stops at v3.

**Acceptance Criteria** (each line is one EARS pattern):

1. The README status paragraph SHALL name the current release as `v0.7.0` and SHALL not contain the string `v3 shipped`.  <!-- ubiquitous -->
2. The README Roadmap section SHALL list RFC-004, RFC-005, RFC-006, and RFC-0007 as shipped, each linking its RFC file, and SHALL list the two recorded candidates (economy-profile promotion, house-profile BYO keys) as not scheduled.  <!-- ubiquitous -->
3. The README Engineering process paragraph SHALL state the ADR count and RFC count equal to the number of files under `docs/adr/` and `docs/rfc/`.  <!-- ubiquitous -->
4. WHEN a README section names a version of Next.js, React, Python, or PostgreSQL THEN it SHALL match the pinned version in `frontend/package.json`, `backend/pyproject.toml`, or the compose image tag.  <!-- event-driven -->
5. The README SHALL contain a section describing the reading-first workspace (reader hub with Chat dock, page unit, position-bound retrieval, learner-chosen AI profiles, safety rails), each item linking the ADR or RFC that introduced it.  <!-- ubiquitous -->
6. IF a demo media file named in `docs/media/README.md` is absent from `docs/media/` THEN the README SHALL not embed it and SHALL state that the capture is pending.  <!-- unwanted-behavior -->
7. `CLAUDE.md`'s Current Status SHALL name RFC-0007 as complete and the post-arc slices as the current state, and SHALL not describe v3 as the driving roadmap.  <!-- ubiquitous -->
8. A test SHALL assert criteria 1, 2, 3, and 6 by reading the README, so drift fails CI.  <!-- ubiquitous -->
9. `backend/pyproject.toml` and `frontend/package.json` SHALL declare the version named as the current release in the README status paragraph, and a test SHALL assert both.  <!-- ubiquitous -->

**Independent Test**: Open `README.md` on `main` and compare every version, count, and "shipped" claim against the files it cites.

---

### P1: The nightly's live smoke tests match the adapter ⭐ MVP

**User Story**: As the operator, I want the nightly eval's failures to mean a regression, not a stale test, so that a red run is worth reading.

**Acceptance Criteria**:

1. The live smoke tests in `backend/tests/test_answering_anthropic.py` SHALL call `AnthropicGenerationAdapter.generate` with keyword arguments its signature accepts.  <!-- ubiquitous -->
2. IF the adapter's `generate` signature drops a keyword the live smoke tests pass THEN the offline suite (`pytest -m "not live"`) SHALL fail.  <!-- unwanted-behavior -->
3. WHEN the nightly job fails because the Anthropic API returns the credit-exhausted 400 THEN the job log SHALL carry a `::error::` annotation naming the operator action (fund the key), and the job SHALL still fail.  <!-- event-driven -->

**Independent Test**: Run `uv run pytest tests/test_answering_anthropic.py -m "not live"` offline: green. Rename a `generate` keyword in a scratch copy: red offline.

---

### P1: Releases for every completed arc ⭐ MVP

**User Story**: As a visitor, I want the Releases sidebar to show one entry per shipped arc so that the project's cadence is visible without reading git history.

**Acceptance Criteria**:

1. WHEN the cycle's PR merges THEN tags `v0.4.0`, `v0.5.0`, `v0.6.0`, and `v0.7.0` SHALL exist on `origin`, each on the commit named in the assumptions table (v0.7.0 on the merge commit).  <!-- event-driven -->
2. Each of the four tags SHALL have a GitHub release whose notes are generated over the range from the previous tag and whose body names the RFC it closes.  <!-- ubiquitous -->
3. The releases SHALL be created only after the merge gate approval, never from the feature branch.  <!-- ubiquitous -->

**Independent Test**: `gh release list` shows seven releases, `v0.1.0` through `v0.7.0`, in commit order.

---

### P2: Repository metadata describes the product

**User Story**: As a recruiter scanning a profile, I want the repository card to say what Learny is and what it is built with.

**Acceptance Criteria**:

1. WHEN the merge gate is approved THEN the GitHub repository description SHALL be a one-sentence product description that does not contain the word `research`.  <!-- event-driven -->
2. The repository SHALL carry at least ten topics, including `rag`, `fastapi`, `nextjs`, `pgvector`, `anthropic`, and `spaced-repetition`.  <!-- ubiquitous -->
3. WHERE the operator supplies a public instance URL, the repository homepage SHALL be set to it.  <!-- optional-feature -->

**Independent Test**: `gh repo view --json description,repositoryTopics,homepageUrl`.

---

### P2: RFC-0007 is closed on the record

**User Story**: As a reader of the decision log, I want RFC-0007's outcome block filled so that a complete arc is not marked pending.

**Acceptance Criteria**:

1. RFC-0007's Status line SHALL read `Accepted` with the date `2026-09-27`, and its Outcome block SHALL name the decision, date, decider, and rationale.  <!-- ubiquitous -->
2. Every row of RFC-0007's Action Items table SHALL read `DONE` with the PR that closed it.  <!-- ubiquitous -->

---

### P2: Dependency bumps are current

**User Story**: As a maintainer, I want the three open Dependabot PRs resolved so that the PR list carries no stale noise.

**Acceptance Criteria**:

1. The workflows under `.github/workflows/` SHALL use `actions/checkout@v6`, `actions/setup-node@v6`, and `actions/upload-artifact@v7`, and the tests that pin action majors SHALL assert those versions.  <!-- ubiquitous -->
2. WHEN the merge gate is approved THEN each of PRs #55, #56, and #57 SHALL be closed with a comment naming the PR that superseded it.  <!-- event-driven -->

---

### P3: Demo media exists and is reproducible

**User Story**: As a visitor, I want a short recording of the money path so that I can see the product without running it.

**Acceptance Criteria**:

1. `docs/media/README.md` SHALL describe a capture procedure runnable against `docker compose up` with a funded Anthropic key and the public-domain sample book, and SHALL not claim that media is git-ignored.  <!-- ubiquitous -->
2. WHEN the operator runs the capture THEN `docs/media/` SHALL contain `demo.gif` (≤ 10 MB) and the three named stills, and the README demo section SHALL embed them.  <!-- event-driven -->

**Independent Test**: The README renders the four assets on GitHub.

---

## Edge Cases

- IF `docs/adr/` gains a file after this cycle THEN the README count test SHALL fail until the paragraph is updated (deliberate: the count is a truth claim).
- IF a Dependabot rebase still fails `backend-test` THEN the PR SHALL stay open with a comment naming the failing test, not be merged.
- WHEN the operator has not supplied a homepage URL at the merge gate THEN the homepage SHALL stay empty rather than pointing at localhost.

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
|---|---|---|---|
| TRUTH-01 | P1: README | Tasks | Implementing (T3) |
| TRUTH-02 | P1: README | Tasks | Implementing (T3) |
| TRUTH-03 | P1: README | Tasks | Implementing (T3) |
| TRUTH-04 | P1: README | Tasks | Implementing (T3) |
| TRUTH-05 | P1: README | Tasks | Implementing (T3) |
| TRUTH-06 | P1: README | Tasks | Implementing (T3) |
| TRUTH-07 | P1: README (CLAUDE.md) | Tasks | Implementing (T5) |
| TRUTH-08 | P1: README (drift test) | Tasks | Implementing (T4) |
| TRUTH-09 | P1: Nightly smoke — signature | Tasks | Implementing (T1) |
| TRUTH-10 | P1: Nightly smoke — offline sensor | Tasks | Implementing (T1) |
| TRUTH-11 | P1: Nightly smoke — credit annotation | Tasks | Implementing (T2) |
| TRUTH-12 | P1: Releases — tags | Merge gate | Pending |
| TRUTH-13 | P1: Releases — notes | Merge gate | Pending |
| TRUTH-14 | P1: Releases — after approval only | Merge gate | Pending |
| TRUTH-15 | P2: Repo metadata — description | Merge gate | Pending |
| TRUTH-16 | P2: Repo metadata — topics | Merge gate | Pending |
| TRUTH-17 | P2: Repo metadata — homepage | Merge gate | Pending |
| TRUTH-18 | P2: RFC-0007 outcome | Tasks | Implementing (T6) |
| TRUTH-19 | P2: RFC-0007 action items | Tasks | Implementing (T6) |
| TRUTH-20 | P2: Dependabot — bumps applied | Tasks | Pending |
| TRUTH-23 | P2: Dependabot — PRs closed as superseded | Merge gate | Pending |
| TRUTH-24 | P1: README (manifest versions) | Tasks | Pending |
| TRUTH-21 | P3: Media guide | Tasks | Pending |
| TRUTH-22 | P3: Media files + embeds | Operator-gated | Pending |

**Coverage:** 24 total, 24 mapped, 0 unmapped

---

## Success Criteria

- [ ] A reader of the README on `main` finds no version, count, or "shipped" claim that the cited file contradicts.
- [ ] `gh release list` shows `v0.1.0` … `v0.7.0`.
- [ ] The next nightly run's failure, if any, is attributable to a regression or a named operator action, never to a stale test.
- [ ] The Pull requests tab shows zero open Dependabot PRs.
