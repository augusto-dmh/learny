# Learny Project-Local Skills

Learny keeps project-local skills so future sessions use the same architecture,
artifact, workflow, and stack conventions without depending only on user-global
state. Skills fall into three groups: **workflow/architecture** skills (from the
Tech Leads Club catalog), **vendored official stack skills** (from framework/
vendor sources), and **Learny-authored stack skills** (written in-repo for gaps
that have no official skill).

## Workflow & architecture skills (Tech Leads Club)

Source: `https://github.com/tech-leads-club/agent-skills`

- `modular-design-principles`
- `create-adr`
- `create-rfc`
- `pr-review`
- `learny-finalize` (Learny-specific publishing conventions)
- `tlc-spec-lean` (vendored spec skill — provenance below)

Install notes: the architecture/artifact skills were brought in from the Tech
Leads Club installs used during the first research pass. `tlc-spec-lean` is
vendored into this tree (next section); the vendored spec-driven copy and the
skills no cycle ever loaded were removed on 2026-10-02 (recoverable from git
history).

### Vendored spec skill: `tlc-spec-lean`

Vendored 2026-10-30 into `.claude/skills/tlc-spec-lean/` from the owner's
user-level skills directory (source: `C:\Users\augus\.claude\skills\tlc-spec-lean`,
version `2.1.0`, byte-identical apart from the deviations below plus the Windows
runner fix in `scripts/runners.py` — a launcher `_resolve()` through PATH/PATHEXT
and longer vitest timeouts — ported from the source on 2026-10-30 after it changed
post-vendoring). It replaces the removed driven copy as the feature-cycle skill;
`learny-ship-cycle` Stage 1 and `CLAUDE.md` point at it.

Recorded project deviations (in the vendored `SKILL.md` "Learny deviations"
section):

1. **Per-batch Verifier** — when the build splits over the token budget into
   sequential batches, the Verifier runs scoped to each batch's checks before
   that batch's PR, and over every check before the last batch's PR.
2. **Attribution trailer** — every commit ends with the trailer
   `Assisted-by: Claude Code`, this repo's recorded exception to the skill's
   no-agent-trailer rule; CI's `commits` job enforces it.
3. **Commit contract authority** — the vendored commit gate carries the repo's 11
   commit types (including `revert`) but does not enforce the required trailer,
   the agent-trailer ban or the kebab-case scope rule; where it and CI's
   `commits` job disagree, the repo's checker decides.
4. **Decisions location** — owner decisions live in `.specs/project/STATE.md`
   `## Open decisions` (every row active, no Status column); the vendored plan
   gate's decisions lookup against `.specs/STATE.md` is waived by this deviation.

**Owner action that keeps this the copy that loads:** remove or rename the
user-level `tlc-spec-lean` directory, then confirm from the client's
`Base directory` line for the skill that it resolves under this repo's
`.claude/skills/tlc-spec-lean/` — on this machine the same-named user-level
copy shadowed the project copy (that is how the old vendored driven copy rotted).

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
| `ruff` | `astral-sh/claude-code-plugins` | Astral (ruff author) | Python lint/format |
| `uv` | `astral-sh/claude-code-plugins` | Astral (uv author) | Python package/project manager |
| `vercel-react-best-practices` | `vercel-labs/agent-skills` | Vercel Engineering | React/Next.js App Router performance |
| `vercel-composition-patterns` | `vercel-labs/agent-skills` | Vercel Engineering | React composition/component APIs |
| `web-design-guidelines` | `vercel-labs/agent-skills` | Vercel (Web Interface Guidelines) | UI/accessibility review |

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
