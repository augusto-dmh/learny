# Official / First-Party Agent Skills For The Learny Stack

Date: 2026-07-04

## Purpose

The user asked, using Laravel Boost (`laravel/boost`) as the benchmark for a
framework-team-authored agent skill: are there **official or first-party agent
skills** for the frameworks, libraries, and languages in Learny's stack
(ADR-004: Python/FastAPI, React/Next.js, PostgreSQL/pgvector, Redis/Celery,
Docker Compose, S3/MinIO, EPUB ingestion, OpenAI/Anthropic behind ports)? And is
it worth mining the `tech-leads-club` GitHub org (including private repos) for
reusable skills, agents, or guidelines?

This maps directly to the project policy in `CLAUDE.md` and `SKILLS.md`:
stack-specific skills should come from **official or first-party** sources; a
community best-practices repo is not authoritative until explicitly reviewed.

## Method

A multi-agent survey (68 agents) ran in parallel across: the kappy Laravel Boost
benchmark, the `tech-leads-club/agent-skills` public catalog, eleven
`tech-leads-club` repos (several private, accessed as an org member), and web
sweeps per stack area. Every web-sourced candidate was then adversarially
re-verified (fetch the URL, confirm the claimed publisher actually owns it, and
confirm it is the kind of resource claimed). Directly-observed repo/filesystem
findings were taken as confirmed. **89 findings confirmed** (25
framework-official, 41 vendor-first-party, 23 community). One item
(`developers.openai.com/mcp`) is unverified — its verifier died on a session
limit; treat as probable-but-unconfirmed.

Provenance labels used throughout:
- **framework-official** — published by the framework/library core team or its org.
- **vendor-first-party** — published by a company about *its own* product
  (Vercel↔Next.js, Redis Inc↔Redis, Anthropic↔Claude API).
- **community** — anyone else; reported only when notable, and clearly labeled.

## Headline

**Yes.** A Laravel-Boost-equivalent ecosystem now exists for most of this stack.
The single most important discovery: **FastAPI ships an agent skill inside its
own PyPI package**, installed by `uvx library-skills` — the direct structural
analog to Boost's `php artisan boost:install`. Next.js/Vercel, Astral (uv/ruff),
Redis, and Pydantic all ship first-party skills or plugins through the same
`npx skills add` / `claude plugin install` channels Boost uses. Postgres/pgvector
is covered only by *vendors* (Timescale, Supabase), not by the PostgreSQL core
team. Celery, pytest, SQLAlchemy/Alembic, TypeScript-the-language, Tailwind,
MinIO, and EPUB have **no** official skill — confirmed absences, with fallbacks
noted.

## The benchmark: how Laravel Boost skills are built

Observed directly in `/home/augusto/projects/kappy`. Boost skills
(`laravel-best-practices`, `pest-testing`, `inertia-react-development`,
`tailwindcss-development`, `wayfinder-development`, and the fortify skill shipped
by `laravel/fortify` itself) share a bar worth replicating:
- **`SKILL.md` + progressive `rules/` files** (e.g. laravel-best-practices has a
  prioritized Quick Reference plus ~20 rule files: db-performance, eloquent,
  security, validation, queue-jobs, testing, …).
- **Version-keyed variants** (`.ai/pest/4/skill`, `.ai/tailwindcss/4/skill`);
  `boost:install` installs the variant matching the *installed* dependency version.
- **Trigger-engineered descriptions** with explicit negative scope
  ("invoke when the message includes tailwind"; "NOT for Passport/Socialite").
- **"Consistency First"** — match existing codebase patterns before applying
  defaults; defer detailed API lookups to a live `search-docs` MCP tool.
- **Distributed authorship** — individual first-party packages (`laravel/fortify`)
  ship their own skill under `resources/boost/skills/`; the installer aggregates.

This is the quality/structure target for any FastAPI/Next.js/Postgres skill Learny
adopts or authors.

## Tier 1 — adopt now (official / clean first-party, directly on-stack)

### Backend: Python / FastAPI

- **FastAPI embedded skill** — framework-official (FastAPI team / tiangolo).
  Ships *inside* the `fastapi` PyPI package at `fastapi/.agents/skills/fastapi/`
  (verified present in the `fastapi-0.139.0` wheel: `SKILL.md` + 6 reference files).
  Install: run **`uvx library-skills`** (`tiangolo/library-skills`,
  docs at library-skills.io) in the project — it scans installed deps and
  symlinks embedded skills into `.agents/skills` (and `.claude/skills` if present),
  version-pinned and committable to git. This is the Laravel-Boost analog for the
  backend. https://github.com/fastapi/fastapi/tree/master/fastapi/.agents/skills/fastapi
  · https://github.com/tiangolo/library-skills
  - The same embed pattern is spreading through tiangolo's ecosystem: **SQLModel**
    (`fastapi/sqlmodel`, the only ORM skill in the stack's official ecosystem —
    relevant only if Learny adopts SQLModel over bare SQLAlchemy), plus Typer,
    Asyncer, and even Streamlit embed skills.
- **Pydantic** — framework-official. `llms.txt` / `llms-full.txt` are live and
  current (https://docs.pydantic.dev/latest/llms.txt). A core embedded skill exists
  in the repo (`pydantic/pydantic/.agents/skills/pydantic`) but is **not yet in the
  `2.13.4` wheel** — so `library-skills` can't pick it up; vendor it manually for
  now and switch to the packaged version once it ships in a release.
  There is also a `pydantic/skills` plugin marketplace, but it covers **Pydantic AI
  + Logfire**, not core validation — low priority and partly in tension with the
  Learny-owned-orchestration ADR.
- **Astral (uv / ruff / ty)** — framework-official. Official Claude Code plugin:
  `/plugin marketplace add astral-sh/claude-code-plugins` then
  `/plugin install astral@astral-sh` (team install via committed
  `.claude/settings.json`, which fits Learny's project-local config preference).
  Plus `llms.txt` for uv and ruff. https://github.com/astral-sh/claude-code-plugins

### Frontend: Next.js / React / Vercel

- **Next.js Agent Skills** — framework-official, living *inside* the framework repo
  (`vercel/next.js/skills`, canary) for version alignment — arguably exceeds the
  Boost pattern. Install: `npx skills add vercel/next.js`.
  https://github.com/vercel/next.js/tree/canary/skills
- **Next.js DevTools MCP** — `npx -y next-devtools-mcp@latest`; Next.js 16+ also
  exposes a built-in `/_next/mcp` dev endpoint. Gives the agent live runtime
  insight into the dev server. https://github.com/vercel/next-devtools-mcp
- **Next.js `llms.txt` / `llms-full.txt`** — https://nextjs.org/docs/llms.txt (live).
- **Next.js 16.3+ auto-generates `AGENTS.md`/`CLAUDE.md`** and bundles
  best-practices/migration docs — framework-official guidance for free if Learny is
  on 16.3+ (verify against the installed version). https://github.com/vercel-labs/next-skills
- **Vercel skills collection + CLI** — `vercel-labs/agent-skills` (react-best-practices,
  composition-patterns, web-design-guidelines) installed via the `skills` CLI
  (`npx skills add …`, discovery at skills.sh, `skills-lock.json` for reproducible
  installs). This CLI is the ecosystem's Boost-installer equivalent.
  https://github.com/vercel-labs/skills
  - Provenance nuance: for **React specifically**, Vercel is a major vendor and
    employer of core contributors but not the React team; Meta publishes no React
    skill (only `react.dev/llms.txt`). Treat Vercel React content as strong
    first-party-adjacent, not framework-official.
  - **Read before choosing skills vs AGENTS.md for the frontend:** Vercel's own
    post "AGENTS.md outperforms skills in our agent evals"
    (vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals).

### Data / infra

- **Redis** — vendor-first-party (and the redis org is also the OSS core team, so
  framework-official is defensible). `redis/agent-skills` (redis-core,
  redis-connections, redis-security, redis-observability — all relevant to
  Redis-as-Celery-broker) installed via `npx skills add redis/agent-skills` or the
  Claude Code plugin marketplace. This is the closest Boost-equivalent in the infra
  layer. Plus `redis/mcp-redis` (inspect the broker at dev time) and
  `redis.io/llms.txt`. https://github.com/redis/agent-skills
- **PostgreSQL + pgvector + hybrid search** — **no PostgreSQL-core-team skill exists
  at all** (postgresql.org/llms.txt is 404; pgvector ships nothing). The strongest
  match is **`timescale/pg-aiguide`** (Timescale/Tiger Data, vendor-first-party):
  a `postgres` schema/indexing skill + a dedicated **`pgvector-semantic-search`**
  skill + a `postgres-hybrid-text-search` skill, shipped via `npx skills add
  timescale/pg-aiguide`, a Claude plugin, and an MCP endpoint. **Caveat requiring
  review:** its hybrid-search skill substitutes Timescale's prerelease `pg_textsearch`
  BM25 extension (PG 17/18 only) for Postgres-native `tsvector`/`ts_rank` — its RRF
  fusion *pattern* is reusable but the extension recommendation must not be adopted
  as-is, since ADR-006 specifies pgvector + **built-in** full-text search.
  https://github.com/timescale/pg-aiguide
  - `supabase/agent-skills` has one genuinely generic `supabase-postgres-best-practices`
    skill usable against vanilla Postgres; the Supabase/Neon/PlanetScale *platform*
    skills and MCP servers are **not** applicable (Learny runs plain self-hosted
    Postgres). PlanetScale's skill even opens with a hosting sales pitch.
  - The MCP org's reference Postgres server is **archived/unmaintained**
    (`modelcontextprotocol/servers-archived`) — anything citing
    `@modelcontextprotocol/server-postgres` points at dead code. For a dev-time DB
    MCP, the maintained community option is `crystaldba/postgres-mcp` (Postgres MCP Pro).
- **Docker / Compose** — vendor-first-party, **MCP + llms.txt only, no SKILL.md**.
  Docker MCP Toolkit/Catalog (Docker Desktop 4.62+), `docker/hub-mcp` (accurate image
  tags / compose generation grounded in Docker Hub), `docker/mcp-gateway` (CLI, for
  headless/VPS), and `docs.docker.com/llms.txt`. Useful as the secure way to *run*
  other MCP servers in Learny's Compose-centric dev env. https://docs.docker.com/llms.txt
- **MinIO / S3** — vendor-first-party, MCP only. `minio/mcp-server-aistor`
  (container `quay.io/minio/aistor/mcp-server-aistor`) works against open-source
  MinIO; lets an agent inspect buckets (uploaded EPUBs, object keys). No skill exists.
- **EPUB ingestion / Docling** — framework-official MCP: `docling-project/docling-mcp`
  (LF AI & Data; started by IBM Research). `pip install docling-mcp` /
  `uvx --from docling-mcp docling-mcp-server`. Docling is the leading
  structure-preserving parser candidate for EPUB-first ingestion (headings, sections,
  anchors = the canonical-corpus requirement); per policy it stays a library at the
  edge, orchestration Learny-owned. **Caveat:** docling-mcp's tooling emphasizes PDF;
  core Docling lists EPUB as supported but EPUB-via-MCP is unverified. There is **no
  EPUB agent skill anywhere** — parsing guidance must come from library docs (e.g.
  `ebooklib`) in a project-local skill.

### AI providers (behind Learny's ports/adapters)

- **Anthropic adapter** — `claude-api` skill (already present in this session's skill
  list; `/plugin install claude-api@anthropic-agent-skills`) keeps SDK usage current
  (streaming, prompt caching for RAG contexts) and includes a provider-neutrality
  check that *aligns with the ports/adapters ADR*. Plus `platform.claude.com/llms.txt`
  and the `anthropic-sdk-python` `api.md`/`helpers.md`/`tools.md` machine refs. No
  dedicated SDK skill exists; claude-api + these refs is the sanctioned pattern.
- **OpenAI adapter** — `openai/plugins` → `openai-developers` plugin
  (`openai-api-troubleshooting` + docs-routing; the current first-party equivalent of
  claude-api). Plus `developers.openai.com/llms.txt` (note: `platform.openai.com/llms.txt`
  is 404). `openai/skills` is **deprecated** in favor of `openai/plugins`. **Caution:**
  its `agents-sdk` skill pushes OpenAI Agents SDK orchestration, which Learny's ADRs
  deliberately avoid. `developers.openai.com/mcp` was found but is *unverified*.
- **Anthropic official skills marketplace** (`anthropics/skills`) also offers
  `mcp-builder` (only if Learny later exposes corpus/citations as an MCP server),
  `webapp-testing` (exercise the Next.js auth/proxy + teaching UI end-to-end),
  `document-skills` (pdf/docx/pptx/xlsx — relevant to the *deferred* PDF phase, no
  epub), and `skill-creator` (author project-local skills to spec). The Claude Code
  plugin marketplace (`anthropics/claude-code`) adds general dev-workflow plugins
  (code-review, pr-review-toolkit, feature-dev, security-guidance).

## Tier 2 — TLC catalog skills Learny doesn't have yet (mostly Vercel/OpenAI-sourced)

The `tech-leads-club/agent-skills` catalog (81 active skills, human-curated, Snyk
Agent Scan + static analysis in CI, content-hashed lockfile installs) **contributes
nothing for the backend** — confirmed absence of any Python/FastAPI/SQLAlchemy/
Postgres/pgvector/Redis/Celery/Docker/pytest/TypeScript skill. Its value for Learny
is that it **redistributes vendor-authored content** through one installer
(`npx @tech-leads-club/agent-skills install -s <skill> -a claude-code`):

- **`react-best-practices`** — frontmatter `author: vercel`, compiled header "React
  Best Practices, Vercel Engineering, January 2026" (Vercel's official rules corpus).
- **`react-composition-patterns`** — `author: vercel` (MIT).
- **`web-design-guidelines`** — `author: vercel` (Web Interface Guidelines) — UI-review
  pass for the auth/reading/teaching screens.
- **`security-best-practices` / `security-threat-model` / `security-ownership-map`** —
  `author: github.com/openai/skills`, Apache-2.0 (OpenAI's official security skills;
  generic guidance, so edge-of-first-party).
- **`gh-fix-ci` / `gh-address-comments`** — also OpenAI-sourced.
- Community-grade but relevant: `playwright-skill`, `spec-driven-eval`, `tactical-ddd`,
  `coding-guidelines` (cites Karpathy).

These are the same Vercel/OpenAI artifacts as the direct sources above — installing
via TLC vs the vendor CLI is a convenience/consistency choice, not a provenance one.

## Tier 3 — tech-leads-club org repos (all community by policy; review before trusting)

**Everything here is TypeScript/NestJS/TypeORM/Nx**, not Python, and is "community"
per the sourcing policy — but the user is an org member and several artifacts are
*already* ported into Learny's `.codex/skills` (domain-analysis,
modular-design-principles, pr-review, tlc-spec-driven share TLC lineage), so the
review bar is effectively met for those.

- **`fakeflix`** (private) — the org's flagship agent-tooling repo and the most
  reusable. `.agents/skills/` holds `modular-architecture` (SKILL.md + 4 refs),
  `coupling-analysis`, `domain-analysis`, `pr-review` (multi-agent), `create-e2e-tests`,
  `spec-driven-eval`, plus `AGENTS.md` / `.agents/BUGBOT.md` / `docs/CODING-PATTERNS.md`.
  Structurally comparable to Boost (SKILL.md + references/, progressive loading,
  verification scripts) but **project-scoped, manual copy — no installer**.
- **`architecture-fit-ai`** (private) — `MODULAR-ARCHITECTURE-PRINCIPLES-GUIDELINE.md`,
  an AI-agent-consumable guideline for auditing modular-architecture standards.
  (No MCP server yet — text guideline only.)
- **`modular-architectures-principles`** (public) — the 10-principles whitepaper
  (EN + PT, CC BY 4.0); theory behind the guideline above.
- **`enterprise-apps-classes`** (private) — `docs/` DDD guideline set + `.cursor/rules`.
- **`nj-mmo`** (private) — `.cursor/skills/spec-driven-execution` (a tlc-spec-driven
  orchestrator variant).
- **Checked, nothing reusable:** `team-maturity` (HTML calculators), `push-link`
  (browser extension), `awesome-tech-lead` (link list), `aulas-assinatura-requisicao`
  (JWK lesson scripts), `aula-jwt-dpop` (DPoP demo — and DPoP targets bearer-token PoP,
  which conflicts with Learny's chosen HTTP-only cookie sessions),
  `event-driven-architecture-classes` (RabbitMQ saga course; mild future reference if
  an outbox pattern between FastAPI and Celery is ever needed).

## Confirmed absences (valuable negatives)

No official/first-party agent skill exists for: **Celery** (nothing at all — no
skill, MCP, or llms.txt; the one component with zero official agent mechanism),
**pytest**, **SQLAlchemy**, **Alembic**, **TypeScript-the-language** (Microsoft ships
none; `microsoft/skills` is Azure-SDK-scoped), **Tailwind CSS** (Tailwind Labs has
publicly *declined* llms.txt for funding reasons — Boost's tailwind skill is
Laravel-authored, not Tailwind Labs), **PostgreSQL core**, **pgvector**, **MinIO**
(MCP only), **EPUB parsing**, and **RAG/eval** (Ragas ships only `docs.ragas.io/llms.txt`
+ internal contributor config; no skill). For these, the compliant path is pinned
docs excerpts / `llms.txt` grounding or a **self-authored project-local skill** built
with `skill-architect` / Anthropic's `skill-creator`, grounded in official library docs.

## Ecosystem notes

- The **`SKILL.md` / Agent Skills standard** (agentskills.io) is Anthropic-originated,
  now an open cross-vendor standard (adopted by OpenAI Codex, Cursor, etc.) — so
  Learny's `.codex/skills` are portable. There is **no spec-run official registry**;
  `skills.sh` (Vercel-operated) is the de facto index but lists community skills
  indiscriminately, so per-skill provenance must still be checked.
- Install channels in play, all Boost-like: `uvx library-skills` (Python packages),
  `npx skills add <owner/repo>` (Vercel CLI), `claude plugin marketplace add … &&
  claude plugin install …`, and `npx @tech-leads-club/agent-skills install …`.

## Recommended adoption for Learny (concrete)

1. **`uvx library-skills`** once FastAPI/SQLModel are in `pyproject.toml` → gets the
   FastAPI first-party skill (+ SQLModel if adopted), version-pinned, into
   `.claude/skills` / `.codex/skills`.
2. **Astral plugin** via committed `.claude/settings.json` for uv/ruff.
3. **`npx skills add vercel/next.js`** (+ evaluate Vercel's "AGENTS.md > skills" post)
   for the frontend; add `next-devtools-mcp` at dev time.
4. **`redis/agent-skills`** for the Celery-broker layer; `redis/mcp-redis` for dev-time
   inspection.
5. **`timescale/pg-aiguide`** `postgres` + `pgvector-semantic-search` skills — **but
   review and strip the `pg_textsearch` recommendation** to keep ADR-006's native FTS.
6. **`claude-api`** (already loaded) for the Anthropic adapter; `openai/plugins`
   `openai-developers` for the OpenAI adapter — but avoid the OpenAI Agents-SDK skill.
7. **Author project-local skills** (via `skill-architect`) for the gaps that have no
   official skill and are core to Learny: **EPUB ingestion** (grounded in Docling/ebooklib
   docs), **Celery worker conventions**, and **pgvector + native FTS hybrid retrieval**
   (ADR-006), reusing pg-aiguide's RRF *pattern* without its extension.
8. Keep `llms.txt` endpoints (Pydantic, uv/ruff, Next.js, React, Redis, Docker,
   Anthropic, OpenAI) as grounding references where no skill exists.

Adopting any of the above still requires the explicit review `CLAUDE.md` mandates,
especially the vendor-Postgres skills that embed product preferences.
