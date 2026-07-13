# Learny v2 planning research — 2026-07-12

Output of a multi-agent research fleet (8 parallel web-research agents + a completeness critic + 3 gap follow-ups) run to map Learny v2. Actionable conclusions are materialized in [RFC-002: Learny v2 Roadmap](../../rfc/0002-learny-v2-roadmap.md); these files are the evidence base.

| Report | Question it answers |
|---|---|
| [comparable-projects.md](comparable-projects.md) | What do similar OSS/commercial projects do; where does Learny differentiate; which repos to imitate for presentation |
| [anthropic-generation.md](anthropic-generation.md) | Citations API shapes, model/cost per workload, prompt caching, Batch API, quiz-JSON strategy |
| [embeddings.md](embeddings.md) | OpenAI text-embedding-3 vs Voyage, dims/column fit, re-embed migration, Portuguese/FTS language |
| [active-recall-srs.md](active-recall-srs.md) | FSRS/py-fsrs integration, learning-science quiz design, QC pipeline, data model, re-ingest survival |
| [frontend-streaming.md](frontend-streaming.md) | AI SDK useChat + UI Message Stream from FastAPI, Tailwind v4/shadcn/AI Elements, proxy verification |
| [pdf-docling-epub.md](pdf-docling-epub.md) | Docling adapter design, PDF anchor stability, EPUB TOC-hardening heuristics, parser comparison |
| [oss-maturity-ci.md](oss-maturity-ci.md) | GitHub Actions design for this stack, Apache-2.0 rationale, hygiene + portfolio checklists |
| [evaluation.md](evaluation.md) | Layered eval architecture with non-deterministic adapters; skip-Ragas verdict; CI wiring; costs |
| [gap-critique.md](gap-critique.md) | The completeness critic's 3 identified gaps (all resolved below) |
| [followup-quiz-item-format.md](followup-quiz-item-format.md) | Resolves quiz-format conflict: free-recall + cloze, no distractors |
| [followup-vps-sizing.md](followup-vps-sizing.md) | VPS sizing (8 GB), GHCR image pipeline, Caddy TLS, secrets handling |
| [followup-eval-embedding-model.md](followup-eval-embedding-model.md) | Eval snapshots pin to `text-embedding-3-large@1536` (production model), never a cheaper stand-in |
