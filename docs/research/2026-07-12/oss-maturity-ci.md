# Learny v2 research — oss-maturity-ci

Generated 2026-07-12 by a web-research agent (v2 planning research fleet). Sources/dates inline; verify load-bearing claims before implementation.

---

# Engineering Maturity Research: CI, OSS Hygiene, Portfolio Presentation — Learny v2

**Research date: 2026-07-12.** All action versions verified against official docs today.

## Top-line conclusions

1. **CI**: One workflow, 4 parallel jobs (backend-test, lint, frontend, compose-smoke). Use `astral-sh/setup-uv` (v8.x, current per [docs.astral.sh/uv GitHub guide](https://docs.astral.sh/uv/guides/integration/github/), fetched 2026-07-12) with `enable-cache: true`, `pgvector/pgvector:pg16` as a service container with `pg_isready` healthcheck, `astral-sh/ruff-action` (v4.1.0, released 2026-07-05 per [repo](https://github.com/astral-sh/ruff-action)) for lint+format, `actions/setup-node` with `cache: npm` for vitest, and `docker/bake-action` with `type=gha` cache for the compose smoke test. Realistic budget: **4–7 min wall-clock** with warm caches.
2. **License: Apache-2.0.** Best fit for "portfolio + OSS-ready app that might grow": permissive (maximizes portfolio reach and enterprise readability), adds an explicit patent grant MIT lacks, and — critically — as sole copyright holder you can always relicense or add a hosted offering later. AGPL only makes sense if you fear competitors hosting Learny, which contradicts the "no user chasing, no public instance" decision.
3. **Hygiene**: Ship README + LICENSE + a short CONTRIBUTING + SECURITY.md (4 lines is fine) + CI badge + tagged `v0.x` releases with generated notes. **Skip**: issue templates, CODE_OF_CONDUCT, changelog automation, Dependabot noise-tuning beyond security updates — successful solo-maintainer apps skip these until contributors actually appear.
4. **Presentation**: The highest-leverage artifact is a **<90s demo GIF/video at the top of the README** plus an architecture diagram; Learny's 18 ADRs are a genuine differentiator — surface them, don't bury them.

---

## 1. CI workflow sketch

```yaml
# .github/workflows/ci.yml
name: CI
on:
  push: { branches: [main] }
  pull_request:
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  backend-test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16        # NOT plain postgres:16
        env:
          POSTGRES_USER: learny
          POSTGRES_PASSWORD: learny
          POSTGRES_DB: learny_test
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s --health-timeout 5s --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@<pinned-sha>   # v8.x; pin SHA (Astral's own docs pin)
        with:
          enable-cache: true
          cache-dependency-glob: "uv.lock"
      - run: uv python install                   # respects .python-version (3.13)
      - run: uv sync --locked --all-extras --dev # --locked fails CI on stale lock
      - run: uv run alembic upgrade head         # migrations create the vector ext
        env: { DATABASE_URL: postgresql://learny:learny@localhost:5432/learny_test }
      - run: uv run pytest -q
        env:
          DATABASE_URL: postgresql://learny:learny@localhost:5432/learny_test
          REDIS_URL: redis://localhost:6379/0

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/ruff-action@v4          # ruff check (default)
      - uses: astral-sh/ruff-action@v4
        with: { args: "format --check --diff" }

  frontend:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: frontend } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version-file: frontend/package.json   # or .nvmrc
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npx vitest run          # non-watch mode; add `npm run lint`/tsc if wired
      - run: npm run build           # catches Next.js build breaks vitest misses

  compose-smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/bake-action@v6            # builds compose targets w/ gha cache
        with:
          files: docker-compose.yml
          load: true
          set: |
            *.cache-from=type=gha
            *.cache-to=type=gha,mode=max
      - run: docker compose up -d --no-build
      - run: timeout 90 bash -c 'until curl -sf localhost:8000/health; do sleep 3; done'
      - run: docker compose logs && docker compose down -v
        if: always()
```

### Pitfalls (the ones that actually bite)

- **pgvector extension is NOT auto-created.** The `pgvector/pgvector:pg16` image ships the extension binaries but a CI service container gets a fresh DB with no init scripts mounted (you can't mount volumes into `services:` containers). `CREATE EXTENSION IF NOT EXISTS vector` must run via your Alembic migration (best — it also proves migrations work in CI) or a one-off `psql` step before pytest. This is the #1 failure mode people hit ([pgvector/setup-pgvector](https://github.com/pgvector/setup-pgvector) confirms the service-container + `pg_isready` healthcheck pattern; fetched 2026-07-12).
- **Healthcheck is mandatory, not optional**: without `options: --health-cmd pg_isready ...`, steps start before Postgres accepts connections and you get flaky `connection refused` ([GitHub Docs: PostgreSQL service containers](https://docs.github.com/actions/guides/creating-postgresql-service-containers)). GitHub waits for `healthy` before running steps.
- **`pg_isready` returns ready slightly before the specific DB accepts writes** in rare cases; the Alembic step doubles as a connection smoke test.
- **uv caching**: `enable-cache: true` + `cache-dependency-glob: "uv.lock"` is the official pattern; run `uv cache prune --ci` implicitly handled by the action. On GitHub-hosted runners Astral notes it's often *faster to omit pre-built wheels from cache* and re-download — don't over-tune; defaults are fine ([uv GitHub Actions guide](https://docs.astral.sh/uv/guides/integration/github/)). Pin the action to a SHA (Astral's own docs show SHA-pinned `v8.1.0`).
- **Node caching**: `actions/setup-node` with `cache: npm` caches `~/.npm`, not `node_modules` — caching `node_modules` directly is officially discouraged (breaks across Node versions). `npm ci` from warm `~/.npm` is ~20–40s for a typical Next.js app.
- **Compose smoke test**: plain `docker compose build` gets **zero layer caching** on ephemeral runners. `docker/bake-action` reads `docker-compose.yml` targets and supports `type=gha` cache; use `mode=max` for multi-stage Dockerfiles so intermediate stages cache too ([Docker docs: GHA cache backend](https://docs.docker.com/build/ci/github-actions/cache/), [bake with compose files](https://isaacjordan.me/blog/2024/11/fast-docker-builds-in-github-actions-with-compose-files)). GHA cache has a 10 GB/repo limit — with ~4 images, prune stages or accept eviction.
- **`concurrency` + `cancel-in-progress`** saves minutes on force-pushes; trivially cheap to add.

### Time budget

Community heuristic (uncontroversial, not from one canonical source): PR feedback under **10 min**, ideally under 5. Expected for Learny with warm caches: lint ~30–60s, frontend ~2–3 min, backend-test ~2–4 min (service container pull `pgvector/pgvector:pg16` ≈ 30s, uv sync ≈ 10–30s cached), compose-smoke ~3–5 min (the long pole; consider running it only on `main` + when `Dockerfile`/`compose` paths change via `paths` filter if it drags).

---

## 2. License recommendation: **Apache-2.0**

| | MIT | Apache-2.0 | AGPL-3.0 |
|---|---|---|---|
| Portfolio friction | none | none | some (readers must think about it) |
| Patent grant | ❌ | ✅ explicit | ✅ |
| Blocks competitors hosting your app | ❌ | ❌ | ✅ (network copyleft) |
| Enterprise/corporate readability | rubber-stamp | rubber-stamp | often flat-banned |
| Future hosted version by *you* | fine | fine | fine (you own copyright) |

**Recommended: Apache-2.0.** Reasoning:

- For an **app** (not a library), MIT's main advantage — frictionless embedding as a dependency — barely applies. Apache-2.0 costs nothing extra and adds the explicit patent grant and clearer contribution terms (§5 treats submitted contributions as licensed under Apache-2.0, a lightweight implicit CLA), which reads as more "grown-up" for a project positioning itself as production-shaped ([license comparison guide](https://www.opensourcealternatives.to/blog/open-source-license-guide), [OSSAlt MIT/Apache/AGPL 2026 guide](https://ossalt.com/guides/oss-licensing-guide-mit-apache-agpl-2026)).
- **AGPL** exists to close the SaaS loophole — forcing anyone who hosts a modified Learny to publish their changes. That protects a commercial hosted product from free-riders (the Plausible/Cal.com playbook), but Learny's locked decisions are "author + portfolio, no public instance, no user chasing." AGPL's cost (enterprise viewers who reflexively distrust it, contributor hesitance) buys protection you don't need. Fortune-500-type shops rubber-stamp MIT/Apache but require legal review for AGPL ([DEV 2026 license guide](https://dev.to/juanisidoro/open-source-licenses-which-one-should-you-pick-mit-gpl-apache-agpl-and-more-2026-guide-p90)).
- **The future-hosted-version hedge**: as sole author who accepts contributions under Apache-2.0's §5, you retain the ability to relicense (e.g., to AGPL or BSL) *before* meaningful external contributions arrive. The decision is reversible now and gets harder later — but with zero contributors today, Apache-2.0 loses you nothing. If Learny ever heads toward a commercial hosted product, relicense then.
- Practicalities: add `LICENSE` (full Apache-2.0 text) + `license = "Apache-2.0"` in `pyproject.toml` + `"license": "Apache-2.0"` in `package.json`. A `NOTICE` file is optional at this stage.

---

## 3. OSS hygiene checklist (prioritized)

What small successful OSS apps actually ship vs. skip ([opensource.guide security best practices](https://opensource.guide/security-best-practices-for-your-project/), [cfpb open-source checklist](https://github.com/cfpb/open-source-project-template/blob/main/opensource-checklist.md)):

**Tier 1 — do now (each <1h):**
1. `LICENSE` (Apache-2.0).
2. README overhaul (see §4) with CI badge (`![CI](…/workflows/ci.yml/badge.svg)`).
3. `SECURITY.md` — minimal is fine and builds trust: "Report vulnerabilities via GitHub private vulnerability reporting; I triage within a week; no bounty." Enable GitHub's *private vulnerability reporting* in repo settings ([opensource.guide](https://opensource.guide/security-best-practices-for-your-project/)).
4. `CONTRIBUTING.md` — short: dev setup (`docker compose up`, `uv sync`, `npm ci`), how to run tests, "conventional commits enforced", "open an issue before large PRs". One page max.
5. Tagged releases: **use SemVer-shaped `v0.x.y` tags** with GitHub's auto-generated release notes. For an app (not a library) strict SemVer semantics are low-value — version numbers mostly signal momentum and give a rollback anchor for your VPS deploys ([Bernát Gábor on version numbers](https://bernat.tech/posts/version-numbers/), [SemVer vs CalVer by project type](https://frontside.com/blog/2022-02-09-semver-or-calver-by-project-type/)). `0.x` honestly signals "personal project, no stability contract." Tag `v1.0.0` only as a deliberate milestone. CalVer is the alternative if you ever adopt a fixed cadence — you won't, so skip it. Conventional commits (already in use) make release notes nearly free; full changelog automation (release-please etc.) is Tier-3 at best.
6. Dependabot/`dependabot.yml` for **security updates only** (pip + npm + github-actions ecosystems); weekly version-bump PRs are noise for a solo repo.

**Tier 2 — cheap, do soon:**
7. Repo metadata: description, topics (`rag`, `fastapi`, `pgvector`, `spaced-repetition`, …), pinned on your profile.
8. `.github/PULL_REQUEST_TEMPLATE.md` — only if you expect external PRs; otherwise skip.
9. Branch protection on `main` requiring CI green (you already merge via PRs).

**Skip at this stage (revisit when a second contributor appears):**
- Issue templates / issue forms — empty template chooser on a zero-issue repo looks like cargo-culting.
- `CODE_OF_CONDUCT.md` — meaningful with a community; noise without one.
- CLA bots, all-contributors, Discussions, roadmap project boards, OpenSSF badge.
- Changelog automation, semantic-release.

---

## 4. Portfolio presentation checklist

What actually moves reviewers, per hiring-manager-facing guidance ([shuai.io on showcasing side projects](https://www.shuai.io/blog/how-to-showcase-side-projects-that-attract-tech-opportunities), [techotlist 2026](https://techotlist.com/blogs/job-search/side-projects-that-impress-hiring-managers), [Hakia portfolio guide 2026](https://hakia.com/skills/building-portfolio/)) — consistent themes: reviewers spend ~1–3 minutes, on mute, and never clone the repo. Prioritized:

1. **Demo GIF/video at the very top of the README** (below the one-line pitch). <90 seconds, captioned/annotated (many watch muted), showing the *money path*: upload EPUB → ask question → cited answer → quiz card → review. GIF inline + link to a longer video. Pipeline: record with OBS or `wf-recorder` (WSL2: record the Windows browser with ShareX/ScreenToGif), convert via `ffmpeg -i demo.mp4 -vf "fps=12,scale=960:-1" demo.gif` or use ScreenToGif/Gifski for size control; keep <10 MB for GitHub inline rendering; store in `docs/assets/` (or a `.github/assets/` dir), not git-LFS.
2. **README structure** (write for a senior engineer from a different specialty): one-sentence pitch → demo → "why this exists" (2–3 sentences) → architecture diagram → key technical decisions with ADR links → quickstart (`docker compose up` in ≤3 commands) → test/eval story → roadmap. Badges: CI status + license + Python/Node versions. 2–4 badges, not 10.
3. **Architecture diagram** — one Mermaid or Excalidraw diagram in the README showing FastAPI/Celery/Postgres+pgvector/Redis/MinIO/Next.js proxy and the ingestion→corpus→embed→retrieve flow. Mermaid renders natively on GitHub and diffs cleanly.
4. **Surface the 18 ADRs.** This is Learny's standout credibility asset — almost no side projects have them. Add a "Key decisions" README section linking 4–5 of the most interesting (hybrid retrieval, ports/adapters for AI providers, worker architecture, citations-first) + a link to the full `docs/adr/` index. Depth of *reasoning* is what distinguishes senior-signal projects ([shuai.io](https://www.shuai.io/blog/how-to-showcase-side-projects-that-attract-tech-opportunities)).
5. **Tests/eval story**: a short README paragraph — "N tests, golden-fixture evaluation for ingestion/retrieval/citations, CI on every PR." A coverage badge is optional; a *described eval methodology* is rarer and stronger for a RAG app.
6. **Screenshots**: 2–3 static PNGs (reader view with citations, quiz session) below the fold for skimmers who won't wait for the GIF. Re-shoot after the Tailwind UI lands — don't invest in a screenshot pipeline before the real UI exists; then a simple Playwright script (`page.screenshot()`) against `docker compose up` keeps them reproducible.
7. **One retrospective blog post / long-form README appendix** ("what I'd do differently") — explicitly cited as the depth signal a repo link alone can't provide ([techotlist](https://techotlist.com/blogs/job-search/side-projects-that-impress-hiring-managers)).

**Uncertainty flags**: (a) exact current `setup-uv` patch version — docs showed SHA-pinned v8.1.0 on 2026-07-12; check for newer before pinning. (b) `docker/bake-action` major (v6) — verify against the repo when writing the workflow; the `set: *.cache-from/to` pattern is stable. (c) CI-time numbers are estimates from typical stacks, not measurements of this repo. (d) pgvector image tag: `pg16` matches your Postgres 16; the setup-pgvector README currently exemplifies `pg18-trixie` — `pg16` tags exist on Docker Hub but confirm the exact tag (`pg16` vs `pg16-bookworm`) when writing the workflow.

Sources: [uv GitHub Actions guide](https://docs.astral.sh/uv/guides/integration/github/) · [pgvector/setup-pgvector](https://github.com/pgvector/setup-pgvector) · [GitHub Docs: Postgres service containers](https://docs.github.com/actions/guides/creating-postgresql-service-containers) · [astral-sh/ruff-action](https://github.com/astral-sh/ruff-action) · [Docker GHA cache](https://docs.docker.com/build/ci/github-actions/cache/) · [bake + compose](https://isaacjordan.me/blog/2024/11/fast-docker-builds-in-github-actions-with-compose-files) · [license guide 2026](https://www.opensourcealternatives.to/blog/open-source-license-guide) · [OSSAlt licensing](https://ossalt.com/guides/oss-licensing-guide-mit-apache-agpl-2026) · [DEV license guide](https://dev.to/juanisidoro/open-source-licenses-which-one-should-you-pick-mit-gpl-apache-agpl-and-more-2026-guide-p90) · [opensource.guide security](https://opensource.guide/security-best-practices-for-your-project/) · [cfpb OSS checklist](https://github.com/cfpb/open-source-project-template/blob/main/opensource-checklist.md) · [version numbers](https://bernat.tech/posts/version-numbers/) · [SemVer/CalVer by project type](https://frontside.com/blog/2022-02-09-semver-or-calver-by-project-type/) · [shuai.io showcasing](https://www.shuai.io/blog/how-to-showcase-side-projects-that-attract-tech-opportunities) · [techotlist 2026](https://techotlist.com/blogs/job-search/side-projects-that-impress-hiring-managers) · [Hakia portfolio 2026](https://hakia.com/skills/building-portfolio/)
