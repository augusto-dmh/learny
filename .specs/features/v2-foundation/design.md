# v2-foundation — Design (lite)

No new architecture this cycle; each work item's design is already fixed by an existing verified artifact. This file maps spec IDs to their design source and records the few implementation-level choices.

| Area | Design source | Notes |
|---|---|---|
| Artifacts landing (FND-01) | Authored files in working tree (user-approved) | Commit as-is; docs-only commits first so later fix commits diff cleanly. |
| Compose F1 guard (FND-02) | `docker-compose.yml` (already fixed) | Extend `backend/tests/test_compose_prod.py` (it already parses compose files) with a worker-storage-env assertion against the base file. |
| F2 storage classification (FND-03..06) | QA report + `s3.py` reading | Single seam: wrap `_ensure_bucket` body and each public method in `except ClientError → (ObjectNotFound|StorageUnavailable)` / `except BotoCoreError → StorageUnavailable`. Keep `_NOT_FOUND_CODES` logic. Tests: botocore `stubber` won't raise `EndpointConnectionError`, so use a fake client object raising `EndpointConnectionError`/`BotoCoreError` from `head_bucket`/`get_object`/`put_object` — mirrors existing test style in `test_storage_s3.py`. |
| F3 proxy headers (FND-07..10) | `frontend-streaming.md` research §3 + QA F3 | In `proxy.ts`: add `REQUEST_STRIP` set (expect + hop-by-hop) applied in `buildProxyRequest`; add `RESPONSE_STRIP` set (`content-encoding`, `content-length`) applied in `relayResponse`. Case-insensitive (Headers API is already). Extend `tests/proxy*.test.ts`. |
| F4 first-run determinism (FND-11..12) | Diagnose in-repo (`backend/tests/conftest.py`) | Known repro: fresh DB + full suite → 8 golden failures (SQLAlchemy f405), rerun green, subsets green. Diagnosis task runs the repro, reads conftest's engine/migration bootstrap, fixes the mechanism (expected: bootstrap connection state shared with test engine — isolate + dispose). Gate: scripted fresh-DB full-suite run passes first time. |
| CI (FND-13..15) | `docs/research/2026-07-12/oss-maturity-ci.md` | Adaptations: `LEARNY_TEST_DATABASE_URL` (+`LEARNY_REDIS_URL`) not `DATABASE_URL`; healthz path `/healthz`; migrations run by conftest (not a separate step — verify while implementing); pin actions to major versions (SHA-pinning deferred — solo repo, Dependabot watches actions). compose-smoke uses plain `docker compose up -d --build` + healthz poll if bake-action friction appears; bake-action with GHA cache is the first attempt. |
| Hygiene (FND-16..17) | oss-maturity-ci research §3 | LICENSE at root; SECURITY.md at root; CONTRIBUTING.md at root; `.github/dependabot.yml` with `open-pull-requests-limit: 0` on version updates semantics — implement as ecosystems with security updates only (no version-update schedule blocks beyond required syntax). |
| Docs refresh (FND-18..19) | RFC-002 + current reality | CLAUDE.md: rewrite Current Status (MVP shipped, deterministic adapters, v2 = RFC-002 cycles); adjust Established Direction bullets that RFC-002 supersedes (EPUB-only → PDF planned Cycle F; add active-recall flagship; provider choices now decided); keep durable conventions untouched. ROADMAP.md: append "v2 (RFC-002)" table, cycles A–G, `v2-foundation` = In progress. |

## Phases

- **A — Land artifacts** (docs commits, compose guard test)
- **B — Defect fixes** (F2, F3, F4 — each with tests, atomic commits)
- **C — CI + hygiene + docs refresh** (workflow, license/security/contributing/dependabot, CLAUDE.md/ROADMAP.md, STATE.md updates)

3 phases → execute inline (no sub-agent offer per trigger rule). Verifier runs automatically after the last task.
