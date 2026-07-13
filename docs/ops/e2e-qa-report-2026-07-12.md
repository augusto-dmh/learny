# End-to-end QA report — 2026-07-12

First full manual QA of the MVP, following [e2e-qa.md](e2e-qa.md). Executed against
a from-scratch local dev compose stack, then a from-scratch production-like stack.
Books used: *Pride and Prejudice* (Gutenberg epub3, English) via API, and
*Os 5 Desafios das Equipes* (Portuguese) via the browser UI.

## Verdict

The MVP works end-to-end: registration, session auth, EPUB upload to object
storage, async ingestion into the canonical corpus, hybrid retrieval, cited Q&A,
scoped teaching sessions, owner isolation, CSRF/origin/rate-limit gates, crash
redelivery, citation persistence across re-ingestion, and the hardened prod
overlay all verified working. **Two real bugs were found (one fixed during QA,
one open), one CI-breaking test flake, and a set of quality/UX gaps.**

## Phase results

| Phase | Result |
|---|---|
| 0 Preflight | ✅ |
| 1 Boot & health | ✅ six healthy services, migrations from zero, probes 200 |
| 2 Identity & session | ✅ incl. negatives (409 dup, 401s, cookie flags, log redaction) |
| 3 Source upload | ✅ after F2/F3 workarounds; bucket auto-created; 403/415 negatives |
| 4 Ingestion | ❌→✅ failed on F1 (worker storage env, fixed); then 392/392 chunks embedded |
| 5 Cited Q&A | ✅ answered+citations; ⚠️ F5 (no refusal at whole-book scope) |
| 6 Teaching | ✅ scoped answers + honest not-found; UI verified with Portuguese book |
| 7 Authorization & abuse | ✅ all cross-user probes 404, CSRF/origin 403, login 429 after 10 |
| 8 Failure & recovery | ⚠️ storage-outage retry FAILS (F4); worker-kill redelivery ✅ (no dupes); readyz 503/recover ✅; citation persistence after corpus replacement ✅ |
| 9 Production-like | ✅ fail-fast secrets, no infra ports, JSON logs, Secure cookies, full smoke |
| 10 Automated suites | ⚠️ frontend 92/92 ✅, ruff ✅; backend 497 pass but F6 first-run flake |

## Findings

### F1 — FIXED: worker had no object-storage endpoint in compose (critical)
`docker-compose.yml` gave `api` `LEARNY_STORAGE_ENDPOINT: http://minio:9000` but
not `worker`, which fell back to `http://localhost:9000` → every Docker ingestion
failed at the fetch-bytes step. Never caught because unit tests use fakes and the
golden pipeline runs in-process without S3. **Fixed during QA** (endpoint/bucket/
region added to the worker service in the base compose; change is uncommitted).

### F2 — OPEN: transient storage faults are terminal, not retried (high)
`backend/app/infrastructure/storage/s3.py`: `_ensure_bucket()` catches only
`ClientError`, and in `get_object()` the `_ensure_bucket()` call sits before the
`try`. An unreachable endpoint raises `EndpointConnectionError` (a
`BotoCoreError`) that escapes unclassified, so the ingestion task marks the job
terminally `failed` (attempts: 1) instead of raising `RetryableIngestionError`
with backoff. Empirically confirmed: with MinIO stopped, the job died in ~20s
with no retry. Fix: wrap the whole storage call surface so `BotoCoreError` →
`StorageUnavailable`; then Phase 8's stop/start-MinIO scenario should recover
automatically.

### F3 — OPEN: Next proxy 500s on `Expect: 100-continue` (medium)
`frontend/app/lib/proxy.ts` forwards request headers verbatim; undici's fetch
throws `UND_ERR_NOT_SUPPORTED` on `Expect`, so large multipart uploads from curl
and non-browser clients return 500 before reaching FastAPI (also masking what
should be 403/415 responses). Browsers don't send `Expect`, so the UI works.
Fix: strip `Expect` (and other hop-by-hop headers) in `buildProxyRequest`.

### F4 — OPEN: backend suite fails on first run against a fresh test DB (medium, CI-breaking)
Repro: `drop database learny_test; create database learny_test;` then
`pytest tests/` → the 8 DB-backed golden tests fail with an SQLAlchemy
inactive-transaction error; a second identical run is green, and any subset
(golden files alone, suite minus golden, files 1–15 + golden) passes even on a
fresh DB. Ordering/state-dependent; needs its own investigation. Until fixed,
CI from scratch will be red on first run.

### F5 — OPEN: no refusal for off-topic questions at whole-book scope (quality)
`answer_status: "not_found_in_source"` only triggers when retrieval returns zero
evidence (e.g. empty teaching targets). At whole-book scope hybrid retrieval
always returns something, and the deterministic adapter answers — "What is the
capital of Japan?" produced a confident extractive answer with 3 citations.
Everything cited is genuinely from the book (no fabrication), but the status is
wrong. Expected to improve with real embeddings + an LLM adapter that judges
evidence relevance; consider a minimum-relevance threshold either way.

### F6 — OPEN: UI has no navigation, no styling, and several dead-ends (UX)
- Landing page says "Scaffold is up." and never links to `/sources` or `/account`;
  every product screen must be reached by typing the URL.
- Zero CSS in the frontend (no stylesheet, no framework) — bare browser HTML.
- Sources list doesn't poll during ingestion; users must manually reload.
- Teach screen: once in a session there is no back/new-session control (only a
  page reload), and the target dropdown defaults to the first section — usually
  a contentless title page, which yields "not found" on every question.

### F7 — OPEN: real-world EPUB structure is noisy (quality)
Gutenberg/commercial EPUBs produce flat trees with filename-derived titles
(`wrap0000`, `part0034`) and attach all text to caption-level anchors while
file-level sections own nothing. Golden fixtures are much cleaner than reality.
Affects the teach target picker most (F6 compounds it).

### F8 — OPEN: full-text search is hardcoded to English (i18n)
The generated `search_vector` column and `websearch_to_tsquery('english', …)`
stem in English. Portuguese books (verified with a real one) lose lexical recall
on inflected forms; exact words still match. Consider per-document language
config from EPUB metadata (`corpus_documents.language` already exists).

### F9 — Docs drift: `CLAUDE.md` says the repo has no runtime scaffold (stale)
The MVP is fully implemented; the "Current Status" section is out of date.

## Fixed vs open

- Fixed during QA: F1 (compose worker env — **uncommitted**, needs a PR).
- New docs from this QA (also uncommitted): root `README.md`,
  `docs/ops/e2e-qa.md`, this report.
- Suggested fix order: F2 (data-loss-adjacent) → F3+F4 (small, unblock CI/tooling)
  → F6 nav/polling (small UX wins) → F5/F7/F8 (product quality, pair with the
  real-provider adapter work) → F9 (one-paragraph doc fix).
