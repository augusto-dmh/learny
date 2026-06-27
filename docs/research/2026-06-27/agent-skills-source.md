# Skill Research

Date: 2026-06-27

The user requested research against `https://github.com/tech-leads-club/agent-skills` before creating planning artifacts or ADRs, and requested that installed skills come only from that repository.

## Repository Findings

The repository organizes skills under:

```text
packages/skills-catalog/skills/(category)/skill-name/SKILL.md
```

Relevant categories inspected:

- `(architecture)`
- `(decision-making)`
- `(learning)`
- `(quality)`
- `(tooling)`

## Installed Skills

Installed from `tech-leads-club/agent-skills`:

- `domain-analysis`
- `modular-design-principles`
- `create-adr`
- `create-rfc`
- `create-technical-design-doc`

Initial architecture install command used:

```bash
python3 /home/augusto/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo tech-leads-club/agent-skills \
  --path 'packages/skills-catalog/skills/(architecture)/domain-analysis' \
  'packages/skills-catalog/skills/(architecture)/modular-design-principles'
```

The installer reported:

```text
Installed domain-analysis to /home/augusto/.codex/skills/domain-analysis
Installed modular-design-principles to /home/augusto/.codex/skills/modular-design-principles
```

Artifact skill install command used:

```bash
python3 /home/augusto/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo tech-leads-club/agent-skills \
  --path 'packages/skills-catalog/skills/(creation)/create-adr' \
  'packages/skills-catalog/skills/(creation)/create-rfc' \
  'packages/skills-catalog/skills/(creation)/create-technical-design-doc'
```

The installer reported:

```text
Installed create-adr to /home/augusto/.codex/skills/create-adr
Installed create-rfc to /home/augusto/.codex/skills/create-rfc
Installed create-technical-design-doc to /home/augusto/.codex/skills/create-technical-design-doc
```

Codex should be restarted in a future session to auto-load these skills. For this session, their instructions were inspected directly and applied manually.

## Project-Local Copies

The same skills were also copied into the Learny project so the project does not rely only on global Codex state:

```text
/home/augusto/projects/learny/.codex/skills/domain-analysis
/home/augusto/projects/learny/.codex/skills/modular-design-principles
/home/augusto/projects/learny/.codex/skills/create-adr
/home/augusto/projects/learny/.codex/skills/create-rfc
/home/augusto/projects/learny/.codex/skills/create-technical-design-doc
```

These local copies preserve the exact workflow instructions used for the initial Learny research and documentation artifacts.

## Why These Skills

`domain-analysis` is useful for identifying bounded contexts and separating core, supporting, and generic subdomains. Learny needs this because the product should grow beyond book teaching without becoming a single mixed "AI chat over files" domain.

`modular-design-principles` is useful for technology-agnostic decisions around module boundaries, state ownership, public contracts, failure isolation, and observability. Learny needs this because ingestion, retrieval, tutoring, notes, and evaluation should remain independently understandable and replaceable.

`create-adr` is useful for recording decisions once accepted. The initial durable decisions are now represented as ADRs.

`create-rfc` is useful for open decisions that still need comparison and stakeholder alignment. The technology stack selection should be handled as an RFC before becoming an ADR.

`create-technical-design-doc` is useful after the stack and architecture direction are accepted. It should produce the implementation-level system design, risks, testing strategy, observability, and rollback plan.

## Skills Not Installed Yet

`frontend-blueprint` may be useful once the product UI design phase starts, but it is not needed for the current backend/platform architecture decision.

`decomposition-planning-roadmap` is oriented toward decomposing monoliths and migration roadmaps. Since Learny is greenfield, `modular-design-principles` is the better fit now.

`learning-opportunities` is useful for educational coding sessions, but not necessary for architecture research.
