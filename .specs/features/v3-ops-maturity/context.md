# v3-ops-maturity — Decision Context

Auto-decided per learny-ship-cycle rules (options each carry why-recommend AND why-not; recommended chosen; auditable without the conversation). Mirrored as AD-097..AD-102 in `.specs/project/STATE.md`.

## D-1 — Backup scheduling mechanism (AD-097)

- **Dedicated sidecar container running crond (CHOSEN)** — why: ships with the compose overlay the deploy job already scp's, testable with the existing YAML/text test patterns, self-contained restart policy, no host state. Why not: one more always-on container (~10 MB idle).
- Host cron on the VPS — why: zero new containers. Why not: config lives outside the repo/compose (drift, untestable, undone by VPS rebuild — exactly what the deploy runbook avoids).
- Celery beat + backup task — why: reuses existing worker infra. Why not: puts pg_dump/mc into the app image (bloats it — opposite of OPS-16), couples backup cadence to app deploys, worker crash-loops take backups down with them.
- Ofelia (cron-for-docker) — why: purpose-built scheduler. Why not: third-party image + label DSL for one nightly job; more moving parts than crond in the job's own container.

## D-2 — Backup tooling/image (AD-098)

- **Repo-owned image: alpine + postgresql16-client + minio `mc`, shell scripts (CHOSEN)** — why: full control of dump/prune/mirror semantics, no third-party image trust (lesson: verify third-party tags), scripts live in-repo and are text-testable, one image covers both DB and object backup. Why not: we own the (small) scripts and a 4th build-matrix entry.
- `prodrigestivill/postgres-backup-local` — why: cron+retention prebuilt. Why not: Postgres-only (objects need a second mechanism anyway), third-party image to vet and pin, retention semantics not ours.
- restic/rclone pair — why: encryption + dedup + any-backend. Why not: two more third-party tools and a repo-format state to manage; mc already speaks every S3-compatible target and matches the existing runbook (`mc mirror`).

## D-3 — Offsite topology (AD-099)

- **DB dumps local + offsite copy; bucket objects mirrored offsite-only (CHOSEN)** — why: dumps are small (keep 14 days locally for fast restore, copy offsite for disaster); duplicating the object bucket onto the same VPS disk doubles disk use for near-zero extra safety (same disk), so objects go straight minio→offsite via `mc mirror`. Why not: object restore depends on offsite being configured — accepted: without offsite, objects still live in `minio_data` and the risk is VPS-disk loss, which no local copy mitigates.
- Everything staged locally then pushed — why: uniform. Why not: doubles VPS disk for the bucket, slower, no added safety.
- Everything offsite-only — why: least disk. Why not: restores of last night's DB would depend on network/offsite availability.

## D-4 — Monitoring stack (AD-100)

- **Netdata, single container, pinned tag, loopback-only publish + SSH tunnel (CHOSEN)** — why: one container giving host + per-cgroup/container metrics + built-in dashboards/alerts with zero config, fits the 8 GB VPS, provider-neutral, no public surface change (127.0.0.1 bind, tunnel documented). Why not: ~200–400 MB RAM; UI access needs a tunnel (accepted — ADR-0017/0023 single-public-surface stands).
- Prometheus + Grafana + cAdvisor + node_exporter — why: industry standard, composable. Why not: 4 containers + config surface on a personal VPS; overkill for one operator.
- Uptime Kuma — why: tiny, great uptime alerts. Why not: no resource metrics — doesn't answer "which container is eating memory", the actual operational question here.
- Dozzle (+autoheal) — why: minimal log UI. Why not: logs are already structured/queryable; no metrics.

## D-5 — Runtime image extras fix (AD-101)

- **Plain `uv sync --frozen` (main deps only) in the runtime stage (CHOSEN)** — why: dev extra (pytest/ruff/httpx/docling-core) exists for tests/lint, none of which run in the image; CI installs extras on the runner, not the image. The phase MUST audit import chains first: if any api/worker startup path imports `docling_core`, that import gets guarded or the dependency justified into main deps — auditable outcome required. Why not: risk of a hidden dev-extra import at startup — mitigated by the audit + compose-smoke booting api/worker.
- New `prod` extra listing serving deps — why: explicit. Why not: duplicates the main dependency list; drift risk with zero benefit since main deps already are the prod set.

## D-6 — pdf-worker slimming (AD-102)

- **Bounded investigation: pin CPU-only torch wheels via uv if the lock stays consistent and CI green; otherwise record blocker + measured evidence in ADR-0024 (CHOSEN)** — why: CUDA-bundled torch wheels are the plausible multi-GB culprit and uv supports index pinning; but lockfile surgery affects every environment, so it's do-if-clean with an explicit either-outcome AC (OPS-18). Why not: may end as documentation-only — accepted, "where practical" is the RFC's own bound.
- Skip entirely — why: zero risk. Why not: leaves a recorded ADR-0023 follow-up untouched in the cycle that exists to close such debts.

## D-7 — Monitoring exposure (folded into AD-100)

Loopback-only port publish (`127.0.0.1:19999:19999`) + SSH tunnel, chosen over Caddy-proxying the UI (would widen the public surface + need auth) and over no-publish-at-all (would require exec-into-container acrobatics to view). The deploy-topology test tightens to: caddy is the only service publishing non-loopback ports.
