# installable-and-adult-launch review triage

## PR #87 (batch A — installable, offline, low-bandwidth)

- Review mode: **degraded inline** — this lane's session cannot spawn the fresh-context reviewer sub-agent (limit-death clause, recorded in `verification.md`), so the review was a mechanical self-review pass over the full diff at the reviewed head (the merge with current `main`, all five CI jobs green). The coordinator's independent review runs from its own session where slots allow; no PR comments existed at merge time (both comment endpoints returned `[]`, fetched 2026-10-31), so there were no findings to triage and no comments to delete.
- Self-review findings considered and resolved during the build (kept here as the surviving record): (1) the Streamdown memo keeps already-rendered figures when the data-saver flip lands mid-chapter — fixed with the remount key on `ChapterMarkdown` (tested); (2) the registrar's user post must survive a service-worker update, so it re-posts on every page load instead of deduping (tested); (3) the root-layout metadata test asserted the exact metadata object and broke when the manifest link landed — updated with the claim (test commit on the PR).
- Verdict: clean; merged with the standing authorization of 2026-10-29 (PR #87, merged 2026-11-01).

## PR #88 (batch B — adults only, legal in Portuguese, the capped guest Ask)

- Review mode: **degraded inline** (same clause). The first CI round caught two real findings the lane's own post-build verification had missed; both are real, both fixed:
  1. **The retired lessons layer came back** — recording a lesson via the vendored `lessons.py add` recreated `.specs/lessons.json`, which the harness sensor holds absent (`test_the_lessons_files_gone_stay_gone`). Real; fixed by removing the files and keeping the durable environment note in `verification.md` instead.
  2. **The registration redirect test still modeled the old form** — the home-redirects test clicked only the ToS checkbox, and the new required age checkbox correctly blocked submit. Real; fixed by modeling both checkboxes and asserting the attestation rides the register body.
- Root cause behind finding 2 (recorded as practice for the rest of this lane): the post-build isolated re-verification *sampled* the heavy-load-failed files instead of covering every one, and the full isolated frontend run before push is now the lane's rule — on the fixed head it is green except the known Windows-local `i18n-typed-keys` spawn pair (CI-green on Linux).
- No PR comments existed at the gate; comments will be re-fetched and deleted after the coordinator's review per D4.
