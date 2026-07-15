# Learny v2 research — followup-vps-sizing

Generated 2026-07-12 by a web-research agent (v2 planning research fleet). Sources/dates inline; verify load-bearing claims before implementation.

---

# Personal VPS Deployment — Concrete Requirements (researched 2026-07-12)

## Bottom line

**Get an 8 GB / 4 vCPU VPS (e.g. Hetzner CPX31-class, ~€14/mo), build images in GitHub Actions → push to GHCR (free for public images) → SSH deploy job runs `docker compose pull && up -d`, put Caddy in front for automatic TLS, and keep runtime secrets in a chmod-600 `.env` on the VPS.** 4 GB is survivable only with strict Docling worker limits; don't build images on the VPS.

## 1. Resource sizing

**Docling worker (the dominant cost).** Confirmed figures:

- Baseline: ~2 GB free RAM minimum for CPU inference with default models; the self-hosted Docling server image needs ~4 GB disk with models baked in ([hwdsl2/docker-docling](https://github.com/hwdsl2/docker-docling), Jan 2026 README).
- Real-world PDF conversion spikes 3–4 GB RAM at 100% CPU; OCR on large PDFs wants 4 GB+ ([docling #2877](https://github.com/docling-project/docling/issues/2877)). Known memory regressions/leaks exist across versions ([#2786](https://github.com/docling-project/docling/issues/2786), [#2788](https://github.com/docling-project/docling/issues/2788), [#2779](https://github.com/docling-project/docling/issues/2779) — "consumes all available memory and gets killed"), so treat the worker as OOM-prone and cap it.
- Image delta for Learny's worker image: `pip install docling --extra-index-url https://download.pytorch.org/whl/cpu` (CPU torch, per [official install docs](https://docling-project.github.io/docling/getting_started/installation/)) adds roughly 1.5–2 GB installed; model weights are ~358 MB for [ds4sd/docling-models](https://huggingface.co/ds4sd/docling-models) plus easyocr models. Prefetch with `docling-tools models download` at image build (bake into image or a named volume) so first ingestion doesn't download at runtime ([advanced options](https://docling-project.github.io/docling/usage/advanced_options/)). Use `opencv-python-headless` in Docker ([FAQ](https://docling-project.github.io/docling/faq/)).
- Mitigations, all officially recommended ([perf discussion #2516](https://github.com/docling-project/docling/discussions/2516)): pypdfium2 backend, disable enrichments you don't need (code/formula/picture classification), `num_threads` = vCPUs, and — Celery-side — a **dedicated `ingest-pdf` queue with `concurrency=1`**, `mem_limit: 4g`, hard task time limits, and `worker_max_tasks_per_child=1` to reclaim leaked memory.

**Whole-stack budget (steady state → peak):** Postgres 16+pgvector 0.5–1 GB, Redis ~128 MB, MinIO ~512 MB, FastAPI ~256 MB, Next.js ~256 MB, general Celery worker ~512 MB, Caddy ~50 MB ≈ **2.5–3 GB before Docling**. Add a 3–4 GB Docling spike → **8 GB RAM is the safe size; 4 GB only with concurrency=1 + mem_limit + 2–4 GB swap as OOM backstop.** Disk: images ~8–10 GB total (Docling worker is the fat one) + Postgres/MinIO volumes; a 40–80 GB disk is plenty. CPU: 3–4 shared vCPUs fine; ingestion is batch, latency doesn't matter.

## 2. Image delivery pipeline

**Recommendation: registry (GHCR), not build-on-VPS.** Building the ~2 GB Docling worker image on the VPS competes for the same RAM/CPU as the running stack and can OOM it; registry pulls are cheap and atomic. GHCR fits the OSS/portfolio goal: **container storage and bandwidth are currently free, with unlimited pulls for public images** ([GitHub Packages billing](https://docs.github.com/en/billing/concepts/product-billing/github-packages)); pulls from Actions with `GITHUB_TOKEN` don't count against transfer quotas.

**CI deploy job shape** (standard, well-documented pattern — e.g. [davidhuertas.dev walkthrough](https://davidhuertas.dev/en/posts/deploy-docker-containers-in-vps-with-github-actions/), [erikmd gist](https://gist.github.com/erikmd/ba9edc8bf0919287b6291ca4b6449864)):

1. `docker/build-push-action` per image (api, worker, worker-docling, web) with `cache-from/to: type=gha` — the single biggest build-time win; tag with `:sha` + `:latest`, push to `ghcr.io/augusto-dmh/learny-*`.
2. `scp` the prod `docker-compose.yml` to the VPS, then `ssh` (e.g. [appleboy actions](https://github.com/marketplace/actions/docker-compose-deployment-ssh) or plain `ssh` with a dedicated deploy key): `docker login ghcr.io` (fine-grained PAT with `read:packages`, or skip login entirely if images are public), `docker compose pull && docker compose up -d --remove-orphans`, `docker image prune -f`.
3. Gate on CI passing; deploy only from `main`.

## 3. Secrets & TLS

**TLS: Caddy as the single exposed container.** Automatic Let's Encrypt issuance, HTTP→HTTPS redirect, and renewal with a 3-line Caddyfile (`reverse_proxy web:3000` / `api:8000` by compose service name). **Critical: persist `caddy_data:/data`** — recreating Caddy without it re-requests certs every boot and hits Let's Encrypt rate-limit bans within a day ([Caddy Docker HTTPS guide, Jan 2026](https://oneuptime.com/blog/post/2026-01-16-docker-caddy-automatic-https/view); [production patterns](https://rdp.sh/en/blog/caddy-reverse-proxy-patterns-that-actually-work-in-production)). Publish **only 80/443** (+ SSH); Postgres/Redis/MinIO/API get no host ports — Docker-network-internal only — plus ufw as belt-and-braces.

**Secrets: two planes, no vault needed at this scale.**

- *CI plane (GitHub Actions Secrets):* SSH private key + host, GHCR PAT if images stay private. Never in workflow YAML.
- *Runtime plane (VPS):* one `.env` file next to the compose file, `chmod 600`, root-owned, never committed — holds `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, Postgres/Redis/MinIO passwords, session secret. Reference via `env_file:` in compose. Manage it by hand over SSH (it changes rarely); optionally scp it from a GitHub Secret during deploy, but hand-managed is simpler and keeps AI keys out of GitHub entirely. SOPS+age is the upgrade path if you later want encrypted secrets in-repo — not needed now.
- Set `requirepass` on Redis and non-default MinIO root credentials even though they're network-internal.

**Uncertainty flags:** Docling RAM figures are community-reported, not official spec (official FAQ documents no hardware minimums); actual peak depends on PDF size/OCR. GHCR free bandwidth is "currently free" with one-month change notice — a public-image strategy is immune to that risk.

Sources: [docker-docling](https://github.com/hwdsl2/docker-docling) · [docling #2877](https://github.com/docling-project/docling/issues/2877) · [docling #2516](https://github.com/docling-project/docling/discussions/2516) · [docling install docs](https://docling-project.github.io/docling/getting_started/installation/) · [docling FAQ](https://docling-project.github.io/docling/faq/) · [ds4sd/docling-models](https://huggingface.co/ds4sd/docling-models) · [GitHub Packages billing](https://docs.github.com/en/billing/concepts/product-billing/github-packages) · [VPS deploy w/ Actions](https://davidhuertas.dev/en/posts/deploy-docker-containers-in-vps-with-github-actions/) · [compose-over-SSH gist](https://gist.github.com/erikmd/ba9edc8bf0919287b6291ca4b6449864) · [Caddy Docker HTTPS](https://oneuptime.com/blog/post/2026-01-16-docker-caddy-automatic-https/view) · [Caddy production patterns](https://rdp.sh/en/blog/caddy-reverse-proxy-patterns-that-actually-work-in-production)
