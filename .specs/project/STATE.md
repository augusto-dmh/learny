# STATE — live handoff and open cross-cycle decisions

The decision log `AD-001`..`AD-362`, every cycle's handoff through v7 and `portfolio-truthful`, the old blockers, known gaps and preferences are archived verbatim in [archive/STATE-v1-v7.md](archive/STATE-v1-v7.md). Architecture lives in `docs/adr/`; a cycle's own decisions live in its `plan.md` `## Assumptions`. This file keeps only what the next session needs to act on.

## Handoff

- **Parallel lanes (from 2026-10-02).** Up to four ship cycles run at once, each in its own worktree under `.worktrees/` with its own test database and Compose project; the main checkout runs one lane. Wrap commits (`docs(specs)`) go straight to `main` after `git pull --rebase`; ROADMAP/STATE conflicts are additive — keep both sides.
- **`harness-reset` PR A (sensors and hygiene) — in flight on `chore/harness-reset-sensors`.** Adds `LEARNY_REQUIRE_DB=1` (CI + Verifier), the CI `commits` job (`Assisted-by: Claude Code` required), digest-pinned upstream images (ADR-0032), the eval schedule off, this file's archive, and the skill prune. After merge, on the owner's yes: the `main-guard` ruleset (see Open decisions). NEXT in this lane: `harness-reset` PR B (vendor `tlc-spec-lean`, rewire ship-cycle Stage Detection/Stage 1, `pr-review` Track A, two lanes + door gate).
- **v8 rows** (`pt-br-interface`, `byok-secrets-and-chains`, `byok-hosted-policy`, `local-models-self-host`) are being shipped in the other lanes; their status lives in `ROADMAP.md`.
- **Operator items still open** (carried from `portfolio-truthful`): (1) flip the GHCR `learny-minio` package public before any VPS deploy; (2) fund the Anthropic key behind `LEARNY_ANTHROPIC_API_KEY`, then run the live eval by manual dispatch; (3) record the demo per `docs/media/README.md` once a funded key exists. Recorded candidates: pin GitHub Actions `uses:` to commit SHAs with an update path, secret-holding and GHCR-push jobs first (ADR-0032 follow-up, from the PR A review); MinIO unprivileged user + volume migration (ADR-0031 follow-up); economy-profile promotion after a funded, manually dispatched candidate eval run.

## Open decisions

Owner decisions taken 2026-10-02 on the delivery-harness research (`docs/research/2026-09-30/harness/synthesis.md`). They bind every lane until a later decision supersedes them. New cross-cycle decisions continue as `AD-363` onward in this section.

| # | Decision | Consequence |
|---|---|---|
| D1 | Door-only plan gate: one question listing the plan's one-way doors and unconfirmed assumptions; waivable in `auto` mode | Ship-cycle stops twice: the door gate before checks, the merge gate before merging |
| D2 | One PR per batch of slices; over the lean budget, sequential batches each become their own PR | The Verifier runs scoped to each batch's checks before its PR, and over every check before the last |
| D3 | AI attribution is the trailer `Assisted-by: Claude Code` on every commit, set via `attribution` in `.claude/settings.json` | CI's `commits` job requires it and rejects agent `Co-authored-by`/`Made-with`; overrides tlc-spec-lean's no-trailer rule |
| D4 | Keep deleting PR review comments after triage | `review-triage.md` stays the only review record |
| D5 | Live eval schedule off, manual dispatch kept, reason recorded | **Supersedes AD-360** (keep the schedule red). Economy-profile promotion waits for a funded manual run |
| D6 | Keep merge commits, add commit lint in CI | `gh pr merge --merge` unchanged; never `--admin` |
| Ruleset | `main-guard` on `main`: PR required, CI (`backend-test`, `lint`, `frontend`, `compose-smoke`, `commits`) green, no force-push or deletion, up-to-date branch not required, Repository-admin bypass `always` | Approved at the `harness-reset` door gate; applied only after PR A merges, on the owner's explicit yes. Stage 8 wrap pushes to `main` are recorded admin bypasses |
