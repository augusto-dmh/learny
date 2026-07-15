# End-to-end QA runbook

Manual QA script covering the full MVP: boot, identity, upload, ingestion, cited Q&A, teaching, security, failure/recovery, production-like run, and the automated suites. Run phases in order — later phases assume earlier state (an account, a `ready` source).

No API keys are needed: the MVP uses deterministic, network-free embedding/answer adapters.

Conventions:

- `BASE=http://localhost:3000` — go through the Next.js proxy, exactly like the browser does. (Hitting `:8000` directly bypasses the proxy and is only used where noted.)
- curl examples keep cookies in a jar: `-b /tmp/qa-cookies -c /tmp/qa-cookies`.
- Writes need the CSRF token from `GET /api/auth/me` sent as `X-CSRF-Token`.

---

## Phase 0 — Preflight

1. Docker + Compose available: `docker compose version`.
2. Ports 3000, 8000, 5432, 6379, 9000, 9001 free: `ss -tlnp | grep -E ':(3000|8000|5432|6379|9000|9001)\b'` → no output.
3. Decide on state: for a from-scratch QA, remove old volumes: `docker compose down -v` (destroys DB + MinIO data).
4. Have an EPUB on hand. Options:
   - Any DRM-free EPUB (e.g. Project Gutenberg: `curl -L -o /tmp/qa-book.epub https://www.gutenberg.org/ebooks/1342.epub3.images`).
   - Build the golden-fixture EPUB used by the test suite (from `backend/`): `uv run python -c "from tests.epub_builder import ..."` (see `tests/fixtures_epub.py`).

**Pass:** all commands succeed, EPUB file exists and is < 50 MiB (`LEARNY_EPUB_MAX_BYTES`).

## Phase 1 — Boot & health

1. `docker compose up --build -d`
2. `docker compose ps` → all six services `healthy` (db, redis, minio, api, worker, web). Worker/web have 20–30s start periods.
3. Liveness: `curl -fsS http://localhost:8000/healthz` → 200.
4. Readiness: `curl -fsS http://localhost:8000/readyz` → 200 (checks Postgres).
5. Migrations applied: `docker compose exec db psql -U learny -d learny -c '\dt'` → tables `users, sessions, sources, ingestion_jobs, ingestion_events, corpus_documents, corpus_sections, corpus_blocks, corpus_chunks, teaching_sessions, teaching_turns, teaching_turn_citations, ...`.
6. Frontend up: open http://localhost:3000 → landing page with login/register.
7. Logs are clean: `docker compose logs api worker --since 2m` → no tracebacks; one structured `http.request` line per probe.

**Pass:** six healthy services, 200s from both probes, schema present, landing page renders.

## Phase 2 — Identity & session

Via UI (http://localhost:3000/register, /login, /account) or curl:

```bash
JAR=/tmp/qa-cookies; BASE=http://localhost:3000
# Register (sets HttpOnly cookie)
curl -si -c $JAR -H 'Content-Type: application/json' \
  -d '{"email":"qa@example.com","password":"correct horse battery staple"}' \
  $BASE/api/auth/register            # → 201 + Set-Cookie: learny_session=...; HttpOnly
# Who am I (also returns csrf_token)
curl -s -b $JAR $BASE/api/auth/me    # → 200 {email, csrf_token}
CSRF=$(curl -s -b $JAR $BASE/api/auth/me | python3 -c 'import sys,json;print(json.load(sys.stdin)["csrf_token"])')
```

Negative checks:

- Duplicate email register → 4xx, no second account.
- Wrong password login → 401, no cookie.
- `GET /api/auth/me` without cookie → 401.
- Logout (`POST /api/auth/logout` with cookie + `X-CSRF-Token`) → 204; `me` afterwards → 401. Log back in and refresh `CSRF` before continuing.
- Cookie flags: `HttpOnly`, `SameSite=Lax` present in `Set-Cookie`.

**Pass:** happy path issues a session; all negatives rejected; no password/token values appear in `docker compose logs api`.

## Phase 3 — Source upload

```bash
# Two curl-specific flags are REQUIRED here:
#  -H 'Expect:'                     curl sends Expect: 100-continue on large
#                                   multipart bodies; the Next proxy's fetch
#                                   (undici) errors on it -> 500 (browsers
#                                   never send it, so the UI is unaffected)
#  ;type=application/epub+zip       the API validates the client-asserted
#                                   part content-type; curl defaults to
#                                   application/octet-stream -> 415
curl -si -b $JAR -H "X-CSRF-Token: $CSRF" -H 'Expect:' \
  -F "file=@/tmp/qa-book.epub;type=application/epub+zip" -F "title=QA Book" \
  $BASE/api/sources                  # → 201 {id, status:"uploaded", ...}
SOURCE_ID=<id from response>
curl -s -b $JAR $BASE/api/sources    # → list contains the source, newest first
```

Checks:

- MinIO console (http://localhost:9001, `learny`/`learny-dev-secret`): bucket `learny-sources` auto-created, one object.
- `GET /api/sources/{id}/structure` before ingestion → 404/empty (no corpus yet).
- Upload without CSRF header → 403. Upload a non-EPUB / oversized file → 4xx.

**Pass:** source row `uploaded`, object in bucket, negatives rejected.

## Phase 4 — Ingestion pipeline

```bash
curl -si -b $JAR -H "X-CSRF-Token: $CSRF" -X POST \
  $BASE/api/sources/$SOURCE_ID/ingestion          # → 202 (job queued)
watch -n 2 "curl -s -b $JAR $BASE/api/sources/$SOURCE_ID/ingestion | python3 -m json.tool"
```

Checks:

- Job walks `queued → running → succeeded`; events accumulate in order (claim, corpus counts, succeeded).
- Source status becomes `ready` (`GET /api/sources/{id}`).
- Second `POST .../ingestion` while one is active → 409 (partial unique index).
- Structure: `GET /api/sources/{id}/structure` → nested TOC matching the book's chapters, with anchors.
- Worker logs (`docker compose logs worker`) show the job with `job_id`/`source_id` stamped on every line.
- DB spot check: `docker compose exec db psql -U learny -d learny -c "select count(*), count(embedding) from corpus_chunks;"` → equal counts (all chunks embedded, 1536-dim).

**Pass:** job `succeeded`, source `ready`, structure preserved, all chunks embedded.

## Phase 5 — Cited Q&A

UI: http://localhost:3000/sources/{id}/ask. Or:

```bash
curl -s -b $JAR -H "X-CSRF-Token: $CSRF" -H 'Content-Type: application/json' \
  -d '{"question":"<something the book actually discusses>"}' \
  $BASE/api/sources/$SOURCE_ID/questions | python3 -m json.tool
```

Checks:

- `answer_status: "answered"`, answer text is extractive (drawn from evidence snippets — the MVP adapter is deterministic, not generative).
- `citations[]` present with `section_path`, `anchor`, `snippet`; anchors match entries from `/structure`.
- Off-topic question ("what is the capital of Mars?") → `answer_status: "not_found_in_source"`, no fabricated citations.
- Raw retrieval: `POST /api/sources/{id}/retrieve {"query":"..."}` → fused evidence list with scores.
- Question on a source that is still `uploaded`/`processing` → 409.

**Pass:** on-topic questions cite real anchors; off-topic questions refuse rather than hallucinate.

## Phase 6 — Teaching sessions

UI: http://localhost:3000/sources/{id}/teach. Or:

```bash
ANCHOR=<an anchor from /structure>
curl -s -b $JAR -H "X-CSRF-Token: $CSRF" -H 'Content-Type: application/json' \
  -d "{\"source_id\":\"$SOURCE_ID\",\"target_anchor\":\"$ANCHOR\"}" \
  $BASE/api/teaching-sessions                      # → 201 {id,...}
SESSION_ID=<id>
curl -s -b $JAR -H "X-CSRF-Token: $CSRF" -H 'Content-Type: application/json' \
  -d '{"message":"explain this section to me"}' \
  $BASE/api/teaching-sessions/$SESSION_ID/turns    # → 201 cited turn
curl -s -b $JAR $BASE/api/teaching-sessions/$SESSION_ID   # full session + ordered turns
curl -s -b $JAR $BASE/api/sources/$SOURCE_ID/teaching-sessions  # session list
```

Checks:

- Turn citations stay within the target anchor's subtree (scoped retrieval).
- Multiple turns keep order; reloading the session page shows full history.
- Citation persistence: re-run ingestion (Phase 4) then reload the old session → turns and citations still render (denormalized snapshots survive corpus replacement).

**Pass:** sessions create, turns cite within scope, history survives re-ingestion.

## Phase 7 — Authorization & abuse

1. Register a second user (fresh cookie jar `/tmp/qa-cookies2`).
2. As user 2: `GET /api/sources/{user1_source_id}` → 404 (not 403 — no existence leak). Same for structure, ingestion, questions, teaching session by id.
3. CSRF: replay a write with cookie but wrong/missing `X-CSRF-Token` → 403. With a forged `Origin: https://evil.example` header → 403.
4. Rate limits: hammer `POST /api/auth/login` with bad credentials in a loop → 429 after the threshold.

**Pass:** strict owner scoping, CSRF/origin gates hold, rate limiting engages.

## Phase 8 — Failure & recovery (worker resilience)

1. Upload a fresh source; `docker compose stop minio`; start ingestion.
2. Job stays `running`/retrying: worker logs show retry with exponential backoff (base 10s); ingestion events record the transient fault.
3. `docker compose start minio` → job recovers and reaches `succeeded` without intervention.
4. Kill the worker mid-job (`docker compose restart worker`) → redelivery (acks_late) resumes the job idempotently; no duplicate corpus rows: chunk counts stable, one corpus per source.
5. `docker compose stop db` → `GET /readyz` → 503 while `/healthz` stays 200. Restart db → readyz recovers.

**Pass:** transient faults retry to success; redelivery is idempotent; readiness reflects DB health.

## Phase 9 — Production-like compose

1. Create git-ignored `secrets/{db,minio,api,worker}.env` from `backend/.env.production.example` (strong `POSTGRES_PASSWORD`, MinIO root creds, matching `LEARNY_DATABASE_URL` and storage keys, `LEARNY_CSRF_TRUSTED_ORIGINS`).
2. `docker compose down` (keep or drop volumes deliberately), then `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`.
3. Verify: no infra ports published on the host (only 3000/8000); `docker compose ps` all healthy; API logs are JSON (`LEARNY_LOG_FORMAT=json`); cookies marked `Secure` (visible in `Set-Cookie`; browsers will require HTTPS to send them — curl-level check only on plain HTTP); missing secrets file → compose refuses to start (spot-check by renaming one).
4. Smoke: repeat Phase 2 register/login + Phase 3–5 happy path once.

**Pass:** prod overlay boots from secrets files only, hardened settings visible, smoke path works.

## Phase 10 — Automated suites & golden fixtures

```bash
# Backend — full suite including DB-backed and golden tests
cd backend
export LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test
docker compose exec db psql -U learny -c 'create database learny_test' 2>/dev/null || true
uv run pytest -ra
uv run ruff check .

# Frontend
cd ../frontend && npm test
```

**Pass:** pytest green (no unexpected skips — DB tests must run, not skip), ruff clean, vitest green.

---

## Sign-off checklist

- [ ] Phase 0 — Preflight
- [ ] Phase 1 — Boot & health
- [ ] Phase 2 — Identity & session
- [ ] Phase 3 — Source upload
- [ ] Phase 4 — Ingestion pipeline
- [ ] Phase 5 — Cited Q&A
- [ ] Phase 6 — Teaching sessions
- [ ] Phase 7 — Authorization & abuse
- [ ] Phase 8 — Failure & recovery
- [ ] Phase 9 — Production-like compose
- [ ] Phase 10 — Automated suites
