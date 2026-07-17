# v2-deploy Context

**Gathered:** 2026-07-17 (auto-decided under learny-ship-cycle's autonomy contract; no user prompts — escalation rule not tripped: no decision locks a provider beyond accepted RFC-002 direction, and every gray area had a clearly defensible recommendation)
**Spec:** `.specs/features/v2-deploy/spec.md`
**Status:** Ready for design

## Feature Boundary

RFC-002 Cycle G: GHCR image builds in CI; SSH deploy job (compose pull && up -d, main-only, green-CI-gated); Caddy TLS edge with persisted certs, only 80/443 exposed; runtime .env on VPS; eval results committed as JSONL; README/runbook/retrospective/v0.2.0 presentation. No provider/domain lock-in, no monitoring stack, no manual media recording.

## Implementation Decisions

### D-1 (AD-090) — Image set, naming, tags, visibility

- **Chosen:** Three images: `ghcr.io/augusto-dmh/learny-backend` (runtime target; serves both `api` and `worker`), `learny-pdf-worker`, `learny-web` (prod target). Tags: `latest` + commit SHA. Push auth via job-scoped `GITHUB_TOKEN` (`packages: write`). Packages made public once, manually, after first push (runbook step).
- **Why:** api/worker already share one build target — separate images would duplicate ~identical layers; SHA tags give immutable rollback handles; public packages let the VPS pull with zero registry credentials (repo is Apache-2.0 OSS).
- **Why not the alternatives:** `learny-api` naming misleads (worker uses it too). Four images (api/worker split) doubles build time for no isolation gain. Private packages force a PAT on the VPS with rotation lifecycle — real secret surface for zero secrecy value.

### D-2 (AD-091) — Deploy workflow shape and gating

- **Chosen:** New `deploy.yml`: triggers `workflow_run` (CI, `completed`) guarded on `conclusion == success && head_branch == main`, plus `workflow_dispatch` (ref-guarded to main). Build jobs (3, parallel) → deploy job (`needs` all three). Workflow-level concurrency group `deploy`, `cancel-in-progress: false`. Deploy job secret-gated like eval.yml: missing `VPS_HOST`/`VPS_USER`/`VPS_SSH_KEY` → green exit + notice.
- **Why:** `workflow_run` is the native "gated on green CI" without duplicating CI jobs; queued (not cancelled) deploys avoid killing a mid-flight VPS update; the secret gate lets the pipeline merge and run green before any VPS exists (proven pattern in eval.yml).
- **Why not:** Extending ci.yml with build/deploy jobs bloats the PR-path workflow and entangles permissions (CI stays `contents: read` only). A `push: main` trigger would race CI instead of gating on it.

### D-3 (AD-092) — Prod compose consumes GHCR images

- **Chosen:** `docker-compose.prod.yml` adds `image: ghcr.io/...:${LEARNY_IMAGE_TAG:-latest}` for api/worker/worker-pdf/web; base keeps `build:` for local dev and compose-smoke. Deploy runs with `LEARNY_IMAGE_TAG=<sha>`; rollback = redeploy an older sha (rollback.md gains this path).
- **Why:** Overlay merge means prod `image:` wins while `build:` stays available locally; `${VAR:-latest}` keeps manual `up` usable; sha-pinning makes deploys reproducible and rollback one env var.
- **Why not:** A separate VPS-only compose file set duplicates topology (drift risk — the base/override/prod triad was AD-042's deliberate design). Deploying `latest` only would make rollback require a rebuild.

### D-4 (AD-093) — Caddy topology

- **Chosen:** `caddy` service in the prod overlay only; `deploy/Caddyfile` with site address `{$LEARNY_DOMAIN}`, `reverse_proxy web:3000`; named volumes `caddy_data` + `caddy_config`; only 80/443 published. To satisfy "only 80/443": api/web host-port publishing moves from base compose into the dev override (the exact pattern already used for db/redis/minio ports).
- **Why:** ADR-0017 routes all browser traffic (incl. SSE) through the Next.js same-origin proxy, so Caddy needs exactly one upstream — api never needs public exposure; compose overlays can add but not remove ports, so the base must be portless for prod to be closed.
- **Why not:** Routing `/api/*` at Caddy directly to api:8000 would bypass the proxy boundary ADR-0017 makes authoritative and reopen CSRF/cookie-domain questions. `!reset` YAML tags in the prod overlay work but are obscure and version-sensitive vs. the established override pattern.

### D-5 (AD-094) — Deploy transport and VPS state

- **Chosen:** Deploy job scps `docker-compose.yml`, `docker-compose.prod.yml`, `deploy/Caddyfile` to fixed `/opt/learny`, then over ssh: `docker compose ... pull` && `up -d --no-build --wait` with `LEARNY_IMAGE_TAG=<sha>`. Runtime secrets stay VPS-local (`secrets/*.env`, `.env` with `LEARNY_DOMAIN`) — created once per runbook, never transferred by CI. worker-pdf deploys too (VPS sized 8 GB for it).
- **Why:** scp-per-deploy keeps the VPS a dumb host (no git checkout to drift); `--no-build` guarantees the VPS never silently builds; `--wait` turns unhealthy deploys into red workflow runs (observability); fixed path avoids another secret.
- **Why not:** git-pull-on-VPS needs repo credentials + a checkout to maintain; docker context over SSH moves the whole compose evaluation client-side but makes env-file resolution (VPS-local secrets) confusing — scp+ssh matches the research design (followup-vps-sizing) and stays debuggable.

### D-6 (AD-095) — Eval results as committed JSONL

- **Chosen:** eval.yml gains a publish step: commit produced `evals/results/*.jsonl` to the dedicated `eval-results` branch (job gets `contents: write`); artifact upload retained; absent key/results → skip green.
- **Why:** Satisfies RFC-002 "results committed as JSONL" with permanent, diffable history while keeping main's history human; no branch-protection interplay.
- **Why not:** Committing to main adds ~30 bot commits/month and fights any future protection rules; artifact-only (status quo) loses history at retention expiry — an explicit RFC line would go unmet.

### D-7 (AD-096) — Presentation scope split

- **Chosen:** In-cycle: README deployment section + Mermaid diagram refresh + decisions/roadmap currency, `docs/ops/deploy.md`, `docs/media/README.md` capture guide with named asset slots + README demo section (no broken embeds), `docs/retrospectives/2026-07-learny-v2.md`, version bump to 0.2.0 both stacks. Manual/deferred: recording the <90s GIF + screenshots (author artifact); `gh release create v0.2.0 --generate-notes` executes at ship-cycle wrap after merge.
- **Why:** Everything automatable ships now; media needs real books, live keys, and a human-paced browser session — the capture guide makes that a 30-minute author task instead of an open-ended one.
- **Why not:** Blocking the cycle on media recording couples a code PR to asset production; committing placeholder binaries or broken image links degrades the README it's meant to polish.

### Agent's Discretion

Exact Caddyfile directives (compression, headers), build-push action versions, runbook prose structure, retrospective content — within the decisions above.

### Declined / Undiscussed Gray Areas → Assumptions

None declined (no user in the loop by design); all gray areas resolved above and mirrored in spec.md's Assumptions table.

## Implicit-Requirement Dimensions Sweep (Large — all dimensions)

- **Input validation & bounds:** workflow_dispatch takes no inputs; ref guard rejects non-main. N/A beyond that — no new user-facing input surface.
- **Failure / partial-failure:** images pushed but deploy fails → next run redeploys (idempotent); `--wait` fails unhealthy deploys; pull failure fails the job (`--no-build`).
- **Idempotency / retry:** `pull` + `up -d` idempotent per sha; re-dispatch safe; eval publish rebase-retries or fails visibly, never force-pushes.
- **Auth boundaries & rate limits:** GHCR via job-scoped GITHUB_TOKEN; VPS via SSH key secret; no PAT; runtime secrets never in CI. App-level auth/rate limits untouched.
- **Concurrency / ordering:** deploy concurrency group (queued); builds precede deploy via `needs`; eval-results branch race handled.
- **Data lifecycle / expiry:** caddy_data persists certs across restarts; eval-results branch grows unbounded — acceptable at ~1 commit/day text JSONL; N/A otherwise.
- **Observability:** deploy visibility = Actions run status (+ `--wait` health); structured logs already shipped (AD-040); metrics stack stays deferred (AD-041).
- **External-dependency failure:** GHCR/SSH outage → red run, manual re-dispatch; Let's Encrypt outage → Caddy retries with backoff, existing certs keep serving from caddy_data.
- **State-transition integrity:** N/A — no new app state machine; deploy state is compose-managed.

## Specific References

RFC-002 §Cycle G; docs/research/2026-07-12/followup-vps-sizing.md (deploy design: build-push per image, scp+ssh, Caddy single exposed container); eval.yml secret-gate pattern; AD-042 compose triad; ADR-0017 proxy boundary.

## Deferred Ideas

- Multi-arch (arm64) builds if a future VPS is ARM.
- Eval-results dashboard rendering the JSONL branch.
- Watchtower-style auto-update — rejected for now; deploys stay CI-driven.
