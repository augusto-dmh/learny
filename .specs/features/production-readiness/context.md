# Production-Like Readiness Context

**Gathered:** 2026-07-12
**Spec:** `.specs/features/production-readiness/spec.md`
**Status:** Ready for design

> Decisions below were made under **learny-ship-cycle Stage 1 auto-decision rule**: each is stated
> with the option set (why-recommend AND why-not) and the recommended choice, recorded here and as
> `AD-040..AD-044` in `.specs/project/STATE.md`. No decision met the escalation bar (no product/MVP
> scope change; no external dependency an ADR reserves is locked — the opposite: they stay deferred;
> every choice has a defensible recommendation).

---

## Feature Boundary

Deliver TDD-001 Phase 10 (Production-like readiness) as three provider-neutral slices: a production
Docker Compose **overlay**, backend **observability hooks** (request-correlated structured logs), and
operator **runbooks** (backup/restore + rollback). No monitoring/metrics/TLS/reverse-proxy/VPS vendor
is locked; TDD open question #10 stays open and is the flagged blocking follow-up.

---

## Implementation Decisions

### D-1 — Cycle scope & shape (AD-040)

- **Options:**
  - (a) Full Phase-10 including a metrics scrape endpoint + monitoring stack + TLS/reverse proxy.
    - *Why:* literal reading of the TDD metrics table; nothing left for later.
    - *Why not:* locks the observability/TLS/proxy implementation that ADR-0008 §5 and TDD OQ #10
      explicitly defer; large, un-reviewable, and picks vendors the project hasn't decided.
  - (b) **Chosen** — observability hooks (structured correlated logs) + prod Compose overlay + ops
    runbooks; provider-neutral; OQ #10 stays open.
    - *Why:* satisfies Phase 10's outcome ("MVP can run in local and first production-like topology"
      + "observability hooks, backups/restore notes, rollback checks") while honoring ADR-0008 §5 and
      CLAUDE.md (monitoring stack reserved for its own ADR).
    - *Why not:* no live metrics dashboard yet — accepted, deferred to OQ #10.
- **Choice:** (b). Flagged at merge gate: OQ #10 is the blocking follow-up for a metrics/monitoring surface.

### D-2 — Observability mechanism (AD-041)

- **Options:**
  - (a) Prometheus `/metrics` endpoint + `prometheus-client` dependency.
    - *Why:* industry-standard scrape surface; the TDD metric families map cleanly to counters/histograms.
    - *Why not:* adds a dependency and commits the exposition format/monitoring direction OQ #10 defers;
      contradicts ADR-0008 §5.
  - (b) Hand-rolled in-process metrics registry + text endpoint.
    - *Why:* dependency-free.
    - *Why not:* still picks an exposition format, is error-prone, and duplicates what a real client does.
  - (c) **Chosen** — request-ID + trace-context middleware + structured JSON logging (env-toggled)
    carrying the required trace fields + per-request latency/outcome access log + worker lifecycle
    duration; standard library only; **no** scrape endpoint, **no** new dependency.
    - *Why:* correlated, latency-bearing, structured logs are the substrate every metric in the TDD
      table is derived from; fully provider-neutral; any log-based metrics/monitoring stack can consume
      them later without rework.
    - *Why not:* no ready-made counters/histograms to scrape — accepted; deferred to OQ #10.
- **Choice:** (c).

### D-3 — Deployment shape: overlay vs standalone (AD-042)

- **Options:**
  - (a) Standalone `docker-compose.prod.yml` that redefines the whole topology.
    - *Why:* one self-contained prod file.
    - *Why not:* duplicates the base topology and drifts from local, violating ADR-0008 §3 ("keep local
      Compose aligned with the production-like topology").
  - (b) **Chosen** — an **overlay** applied via `-f docker-compose.yml -f docker-compose.prod.yml` that
    only overrides prod-specific keys (ports, restart, images, env, commands).
    - *Why:* single source of topology truth; local stays aligned; small, reviewable diff.
    - *Why not:* operators must remember the two-`-f` invocation — mitigated by documenting it in the
      rollback/backup runbooks and the overlay header.
- **Choice:** (b). Hardening in the overlay: no host ports for `db`/`redis`/`minio`; `restart:
  unless-stopped`; pinned image tags (no `:latest`); secrets via `env_file`/env injection;
  `LEARNY_SESSION_COOKIE_SECURE=true` + `LEARNY_ENVIRONMENT=production` + `LEARNY_LOG_FORMAT=json`;
  production run commands (uvicorn multi-worker; Next.js build+start). Reverse proxy + TLS documented
  as an external front, not embedded (OQ #10).

### D-4 — Ops docs location & shape (AD-043)

- **Options:**
  - (a) Inline comments in the compose files.
    - *Why:* co-located with config.
    - *Why not:* not discoverable, can't hold a restore drill or a triggers table, easily stale.
  - (b) **Chosen** — `docs/ops/backups.md` + `docs/ops/rollback.md` with provider-neutral commands.
    - *Why:* durable, discoverable operator knowledge in repo docs; mirrors how prior cycles put durable
      decisions/notes under `docs/`.
    - *Why not:* docs can drift from reality — mitigated by presence/content tests and keeping commands
      provider-neutral.
- **Choice:** (b).

### D-5 — Slice cadence (AD-044)

- **Options:**
  - (a) Force a frontend user-facing slice to honor AD-010 full-slice cadence.
    - *Why:* consistency with the full-slice rule.
    - *Why not:* production readiness genuinely has no end-user surface; a synthetic UI change would be
      make-work.
  - (b) **Chosen** — backend + config + docs only (a production frontend **build target** is added, but
    no UI behavior changes); deliberate flagged departure from AD-010 (precedent AD-023, AD-039).
    - *Why:* matches the nature of the work; precedent exists; flagged at the merge gate.
    - *Why not:* departs from full-slice cadence — accepted and surfaced.
- **Choice:** (b).

### Agent's Discretion

- Exact request-ID length bound and sanitization charset; JSON field names; which image tags to pin to;
  wording of the runbooks; number of uvicorn workers in the prod command (a sensible small default,
  documented as tunable).

### Declined / Undiscussed Gray Areas → Assumptions

- None declined (auto-decision mode). All resolved decisions are logged in the spec's Assumptions &
  Open Questions table and above.

---

## Specific References

- ADR-0008 (Docker Compose on a VPS; §3 keep local aligned, §5 defer observability/TLS/proxy/backup).
- TDD-001 §Monitoring And Observability (required trace fields, metrics table, logs), §Rollback And
  Failure Handling (deployment rollback, operational rollback triggers, idempotency/recovery), OQ #10.
- Existing seams reused: `app/core/logging.py` (`SensitiveDataFilter`, idempotent `configure_logging`),
  worker `ingestion.run` structured `extra=` logging, `app/core/config.py` `LEARNY_`-prefixed settings.

---

## Deferred Ideas

- Metrics scrape endpoint + monitoring/alerting stack + TLS/reverse-proxy product + retention/offsite
  backup policy + VPS provider + CI/CD image pipeline → all TDD OQ #10 (the flagged blocking follow-up).
- Corpus/index output versioning for citation-stable rollback (TDD deployment-rollback bullet) → its own
  decision on top of AD-018 atomic-replace.
