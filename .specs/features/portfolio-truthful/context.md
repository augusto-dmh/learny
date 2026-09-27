# Context — portfolio-truthful

Auto-decided under the ship-cycle rule (recommended option taken, alternatives recorded). Each row mirrors an `AD-NNN` in `.specs/project/STATE.md`.

| # | Decision | Options weighed (why-recommend / why-not) | Chosen |
|---|---|---|---|
| D-1 | Where demo media lives | **Commit under `docs/media/`** — renders from the repo, survives clones / grows the repo, rots on UI change. **Release-attached** — keeps the repo small / breaks when the README is read outside GitHub. **CDN** — fast / one more thing to maintain. | Commit (AD-357) |
| D-2 | Capture without a funded key | **Operator-gated capture, README says pending** — honest / the demo slot stays empty for now. **Deterministic-adapter recording** — possible today / shows extractive answers as the product. | Gated (AD-358) |
| D-3 | Release numbering | **Retroactive tags per arc by completion date** — cadence visible, precedent `v0.3.0` / four releases to write. **Single `v0.7.0`** — one command / hides three arcs. | Retroactive (AD-359) |
| D-4 | Nightly on exhausted balance | **Keep failing, annotate the cause** — honest signal / red badge until funded. **Dispatch-only** — quiet / loses the daily signal. **Skip on credit error** — green / green-by-skip is the lie this cycle removes. | Keep failing (AD-360) |
| D-5 | Dependabot #55/#57 red | **Rebase then merge when green** — usual stale-base cause / one more CI round. **Close** — quiet / leaves majors behind. | Rebase (AD-361) |
| D-6 | Homepage URL | Only the operator knows whether the VPS instance is public. | Asked at the merge gate |

Environment facts: `backend/.env` does not exist locally (no Anthropic key on this machine); the CI secret's account is out of credit (nightly 400 since 2026-09-22). Dependabot #56 is green; #55/#57 fail `backend-test`, cause not yet read.
