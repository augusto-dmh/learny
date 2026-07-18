# Learny Project-Local Skills

Learny keeps project-local skills so future sessions use the same architecture,
artifact, workflow, and stack conventions without depending only on user-global
state. Skills fall into three groups: **workflow/architecture** skills (from the
Tech Leads Club catalog), **vendored official stack skills** (from framework/
vendor sources), and **Learny-authored stack skills** (written in-repo for gaps
that have no official skill).

## Workflow & architecture skills (Tech Leads Club)

Source: `https://github.com/tech-leads-club/agent-skills`

- `domain-analysis`
- `modular-design-principles`
- `create-adr`
- `create-rfc`
- `create-technical-design-doc`
- `tlc-spec-driven`
- `skill-architect`
- `pr-review`
- `learny-finalize` (Learny-specific publishing conventions)

Install notes: the architecture/artifact skills were brought in from the Tech
Leads Club installs used during the first research pass; `tlc-spec-driven` and
`skill-architect` were installed with
`npx @tech-leads-club/agent-skills install --skill tlc-spec-driven skill-architect --agent codex --force`.

## Vendored official stack skills

Added 2026-07-04 after the official-agent-skills survey
(`docs/research/2026-07-04/official-agent-skills-for-stack.md`). These are
framework/vendor-authored skills, installed with the Vercel `skills` CLI using
`--copy` (real committed files, not symlinks) into `.claude/skills/`. Each
passed the CLI's Snyk +
Socket security scan. Provenance and content hashes are pinned in the repo-root
`skills-lock.json`; refresh with `npx skills update`.

| Skill | Source repo | Provenance | Why |
|---|---|---|---|
| `fastapi` | `fastapi/fastapi` | framework-official (FastAPI team) | Backend framework conventions |
| `redis-core` | `redis/agent-skills` | Redis Inc (vendor/core-team) | Data modeling & key naming |
| `redis-connections` | `redis/agent-skills` | Redis Inc | Client pooling/pipelining (Celery broker) |
| `redis-observability` | `redis/agent-skills` | Redis Inc | Monitoring & incident triage |
| `redis-security` | `redis/agent-skills` | Redis Inc | Auth/ACL/TLS hardening for prod |
| `ruff` | `astral-sh/claude-code-plugins` | Astral (ruff author) | Python lint/format |
| `uv` | `astral-sh/claude-code-plugins` | Astral (uv author) | Python package/project manager |
| `vercel-react-best-practices` | `vercel-labs/agent-skills` | Vercel Engineering | React/Next.js App Router performance |
| `vercel-composition-patterns` | `vercel-labs/agent-skills` | Vercel Engineering | React composition/component APIs |
| `web-design-guidelines` | `vercel-labs/agent-skills` | Vercel (Web Interface Guidelines) | UI/accessibility review |

## Community workflow skills (user-accepted)

Added 2026-07-18 at the user's explicit request (reviewed before install, per the
CLAUDE.md third-party-skill constraint). Installed with `npx skills add
mattpocock/skills --skill grill-me --skill grilling --copy`; pinned in
`skills-lock.json`. These are interactive planning aids, not authoritative
project guidance.

| Skill | Source repo | Provenance | Why |
|---|---|---|---|
| `grill-me` | `mattpocock/skills` | Matt Pocock (community) | `/grill-me` launcher for a grilling session |
| `grilling` | `mattpocock/skills` | Matt Pocock (community) | Relentless one-question-at-a-time interview to stress-test a plan before a cycle |

Deliberately **not** installed and why:
- `vercel/next.js` skills (`next-cache-components-*`, `next-dev-loop`) — built for
  **Next.js 16** Cache Components / `/_next/mcp`; the frontend is on **15.5.4**.
  Revisit when the frontend upgrades to Next 16.
- `redis-search`, `redis-clustering`, `redis-semantic-cache`, `iris-development` —
  Learny's vectors live in **pgvector** (ADR-0006), Redis runs single-node as the
  Celery broker, and Iris is a Redis Cloud product.
- Astral `ty`, and Vercel `deploy-to-vercel` / `vercel-cli-with-tokens` /
  `vercel-react-native-skills` / `vercel-optimize` — no type checker in the project;
  Learny deploys via Docker Compose on a VPS (ADR-0008), not Vercel.

Known caveat: the installed backend pins `fastapi==0.128.8`, which **predates** the
package-embedded skill; the vendored `fastapi` skill is fetched from the repo's
current version and references newer APIs (e.g. `app.frontend()`). Bump
`backend/pyproject.toml` to `fastapi>=0.139` to align the code with the skill (and,
once uv is adopted, let `uvx library-skills` manage it from the wheel).

## Learny-authored stack skills (gap-fillers)

Written in-repo because no official skill exists and the topic is core to Learny.
Each encodes the cited ADRs plus official-doc-grounded guidance:

- `epub-ingestion` — structure-preserving EPUB parsing into the canonical corpus
  (ADR-0002, ADR-0011); Docling/ebooklib at the edge behind a Learny port (ADR-0009).
- `celery-workers` — long-running work in separate workers, never in HTTP handlers
  (ADR-0005); Postgres as durable state source of truth (ADR-0014).
- `pgvector-hybrid-search` — pgvector semantic + PostgreSQL **native** full-text
  search with RRF fusion (ADR-0006); embeddings behind a Learny port (ADR-0007).

## Policy

Per `CLAUDE.md`/`SKILLS.md`, stack-specific skills must come from official or
first-party sources and be explicitly reviewed. The vendored skills above are
framework/vendor-authored; the Vercel and Astral ones carry mild vendor framing
that was reviewed as acceptable for Learny's use. The global installs under
`/home/augusto/.codex/skills` remain available, but project work prefers these
local copies.
