# Research drop 2026-09-30 — the study-home delta

*Trigger: owner request (2026-09-30) for deep research on competitors (NotebookLM and others), the science of autonomous learning, the Brazilian market, and BYOK/business models, to find what Learny should become after every shipped roadmap. Delta on top of the 2026-09-03 fleet and the 2026-09-07 provider drop; it does not restate RFC-0007. All web sources accessed 2026-09-30.*

| File | Question it answers |
|---|---|
| [synthesis.md](synthesis.md) | Final report: coverage matrix, white space, twelve candidate roadmap rows (paste-ready), do-not-build list |
| [learny-state-and-ledger.md](learny-state-and-ledger.md) | What is shipped today and which prior recommendations were built, deferred, or dropped |
| [notebooklm-and-google.md](notebooklm-and-google.md) | Gemini Notebook (ex-NotebookLM), Guided Learning, study notebooks: features, limits, pricing, gaps |
| [competitor-landscape.md](competitor-landscape.md) | ~40 other study, reading and spaced-repetition tools, incl. open-source |
| [autonomous-learning-science.md](autonomous-learning-science.md) | Self-regulated learning evidence and 2024–2026 AI-tutor trials, mapped to product mechanisms |
| [brazil-market.md](brazil-market.md) | Brazilian segments, prices, AI adoption, payments, LGPD, Portuguese content and channels |
| [byok-and-business-models.md](byok-and-business-models.md) | BYOK key-storage patterns, provider terms, local pt-BR models, OSS business models, Pix billing |
| [handoff.md](handoff.md) | Paste-prompt for a fresh session: ship cycle `pt-br-interface` (v8 row 1) |

## Thesis in one line

Grounded chat over your own books is no longer a moat (Gemini Notebook took EPUB, Play Books and pt-BR); the white space is a study home that remembers the learner for months and measures only unassisted learning.

## Open decisions for the owner

- Whether to author the `v8` rows from `synthesis.md` into `.specs/project/ROADMAP.md`, and in which order.
- BYOK reverses ADR-0020 amendment point 7 and needs a new ADR; local embeddings need an ADR-0019 amendment scoped to self-host.
- Operator prerequisites that are not cycles: fund the CI Anthropic key, choose a host, LGPD legal pass for Brazil.

## Known gaps

Reddit was not crawlable; OpenAI and Perplexity changelogs returned 403; LGPD beyond minors was not researched; Portuguese UI support of competitors was not verified. Each notes file lists its own caveats.

## Sibling drop

[`harness/`](harness/README.md) — same date, separate question: is the delivery harness (`tlc-spec-driven` + `learny-ship-cycle`) right for v8? Read it before starting the first v8 cycle.
