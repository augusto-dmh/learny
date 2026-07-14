# v2-foundation — Review Triage

PR #17. Sources: 10 inline review comments + 2 PR-level comments (fresh-context pr-review run) + 1 finding from the PR's first live CI run. Verdicts judged against the code and live evidence, not reviewer authority.

| # | Source / location | Finding | Verdict | Action | Rationale |
|---|---|---|---|---|---|
| 1 | inline, ci.yml:52 (Critical) | `astral-sh/setup-uv@v8` does not exist | **Real** (verified: max tag v7) | **Fix** → `@v7` | Job fails at workflow resolution; confirmed by live run (backend-test failed in 3s). Version came from the research doc — research overstated the current major. |
| 2 | inline, ci.yml:67 (Critical) | `astral-sh/ruff-action@v4` does not exist | **Real** (verified: max tag v3) | **Fix** → `@v3` | Same failure mode (lint failed in 4s). |
| 3 | inline, ci.yml:12 (Security) | No least-privilege `permissions:` block | **Real** | **Fix** → top-level `permissions: contents: read` | All four jobs only read the repo; default token grants more than needed. |
| 4 | inline, ci.yml:52 (Security) | Mutable action tags while dependabot disables github-actions version updates — recorded mitigation inactive | **Real** | **Fix** → enable version updates for the `github-actions` ecosystem only (remove its `open-pull-requests-limit: 0`) | Cheapest way to keep the mitigation honest; SHA-pinning adds maintenance without Dependabot bumps. pip/npm stay security-only per the cycle decision. |
| 5 | inline, test_storage_s3.py (Warning) | Live S3 adapter tests skip silently in CI (no MinIO service) | Real | **Won't fix (this cycle)** | GH service containers can't override the image command MinIO needs; the adapter's fault paths are unit-tested, and compose-smoke boots real MinIO every run. Revisit with the deploy cycle's CI work. |
| 6 | inline, ci.yml lint job (Warning) | CI lints with a floating ruff version, not the locked one | **Real** | **Fix** → `version-file: backend/uv.lock` on ruff-action | Keeps CI lint identical to the locked local ruff. |
| 7 | inline, migrations/env.py (Warning) | The settings-fallback branch (no caller-provided URL) is now untested | **Real** | **Fix** → add `test_upgrade_falls_back_to_settings_url` | The CLI/container path relies on it; cheap to cover with the same monkeypatch pattern. |
| 8 | inline, ci.yml compose-smoke (Suggestion) | Smoke gates only API health, not worker/web | **Real** | **Fix** → `docker compose up -d --build --wait` | `--wait` blocks on every service healthcheck (worker celery ping, web fetch probe), strictly stronger than the healthz poll. |
| 9 | inline, test_storage_s3.py (Suggestion) | `_ensure_bucket` create-on-miss recovery has no unit test | **Real** | **Fix** → stub returns success after 404 head; assert operation completes | Completes the adapter's decision-table coverage. |
| 10 | inline, test_compose_prod.py (Suggestion) | Compose regression test pins only the worker's storage env, not the api's | **Real** | **Fix** → assert the api service's storage env too | Same regression class; two more assert lines. |
| 11 | live CI run (compose-smoke job) | `docker compose up --no-build` fails: `No such image: learny-worker:latest` — bake deduped api/worker's identical build definitions and never tagged the worker image | **Real** | **Fix** → drop bake; single `docker compose up -d --build --wait` step | Correctness over cache: cold builds cost ~3–5 min within budget; the bake+GHA-cache optimization returns with the deploy cycle's image pipeline, where images get distinct registry tags anyway. Also subsumes #8's health gating. |
| 12 | PR-level requirements comment | All 19 criteria implemented; remaining items process-level (first CI run, post-merge tag) | Real (observation) | No action | First CI run is in progress on this PR; tag happens post-merge by design. |

Summary: 11 findings real (10 review + 1 live-run), 0 false; 9 fix now, 1 won't-fix with rationale, 1 no-action observation.
