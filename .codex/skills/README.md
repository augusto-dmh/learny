# Learny Project-Local Skills

Learny keeps project-local Codex skills so future sessions can use the same architecture, artifact, and workflow conventions without depending only on user-global state.

Source repository:

```text
https://github.com/tech-leads-club/agent-skills
```

Project-local copies:

- `domain-analysis`
- `modular-design-principles`
- `create-adr`
- `create-rfc`
- `create-technical-design-doc`
- `tlc-spec-driven`
- `skill-architect`

Install notes:

- `domain-analysis`, `modular-design-principles`, `create-adr`, `create-rfc`, and `create-technical-design-doc` were brought into the project from the existing Tech Leads Club installs used during the first research pass.
- `tlc-spec-driven` and `skill-architect` were installed project-locally from the latest Tech Leads Club catalog with `npx @tech-leads-club/agent-skills install --skill tlc-spec-driven skill-architect --agent codex --force`.

The global installs remain available under `/home/augusto/.codex/skills`, but project work should prefer these local copies when available.
