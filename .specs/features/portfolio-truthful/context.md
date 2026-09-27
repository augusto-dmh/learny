# Context — portfolio-truthful

Auto-decided under the ship-cycle rule (recommended option taken, alternatives recorded). Each row mirrors an `AD-NNN` in `.specs/project/STATE.md`.

| # | Decision | Options weighed (why-recommend / why-not) | Chosen |
|---|---|---|---|
| D-1 | Where demo media lives | **Commit under `docs/media/`** — renders from the repo, survives clones / grows the repo, rots on UI change. **Release-attached** — keeps the repo small / breaks when the README is read outside GitHub. **CDN** — fast / one more thing to maintain. | Commit (AD-357) |
| D-2 | Capture without a funded key | **Operator-gated capture, README says pending** — honest / the demo slot stays empty for now. **Deterministic-adapter recording** — possible today / shows extractive answers as the product. | Gated (AD-358) |
| D-3 | Release numbering | **Retroactive tags per arc by completion date** — cadence visible, precedent `v0.3.0` / four releases to write. **Single `v0.7.0`** — one command / hides three arcs. | Retroactive (AD-359) |
| D-4 | Nightly on exhausted balance | **Keep failing, annotate the cause** — honest signal / red badge until funded. **Dispatch-only** — quiet / loses the daily signal. **Skip on credit error** — green / green-by-skip is the lie this cycle removes. | Keep failing (AD-360) |
| D-5 | Dependabot #55/#57 red | Read the failing job: `test_docker_action_versions_are_pinned_to_real_majors` asserts `actions/checkout@v4` literally, so no Dependabot branch can pass. **Apply the bumps in-cycle with the pin tests, close the PRs as superseded** — one PR, green by construction / Dependabot gets no credit. **Rebase** — cannot go green. **Edit their branches** — three PRs for one line each. | Apply in-cycle (AD-361 revised) |
| D-8 | PR #72's CI red on `quay.io/minio/minio` (anonymous pulls refused) | **Build our own image from the GitHub release binary, sha256-pinned** — no credentials, same release, mirrors the `mc` fix / one more image to rebuild on security releases. **bitnamilegacy/minio** — pulls today / frozen namespace, different entrypoint. **Another S3 server** — reopens ADR-0013 for a distribution problem. **quay login** — depends on the vendor that just changed terms. In-cycle because the gate needs green CI. | Own image (AD-362, ADR-0031) |
| D-7 | Package manifests still say 0.3.0 (`test_versions.py` pins it) | **Bump to 0.7.0 with the release** — one truth / a version bump commit. **Leave** — the manifests would contradict the README the same day it is fixed. | Bump (in T9) |
| D-6 | Homepage URL | Only the operator knows whether the VPS instance is public. | Asked at the merge gate |

Environment facts: `backend/.env` does not exist locally (no Anthropic key on this machine); the CI secret's account is out of credit (nightly 400 since 2026-09-22). Dependabot #56 is green; #55/#57 fail `backend-test` on the literal `@v4` pins in the workflow tests. The local `learny_test` database had to be created by hand (fresh volume) and the frontend `node_modules` reinstalled after the 270-commit pull; a stale `frontend/.next` made `tsc` fail until removed.
