# Learny public-launch research fleet — 2026-09-03

Research fleet on **opening Learny to the public**: making the product more intelligent, more attractive to a general learning audience, and ready for a multi-tenant public instance. Product quality and feature depth over monetization (pricing researched, but secondary). Convention: learny/kappy fleet shape — parallel RQ reports → gap critique → synthesis.

| Report | Question it answers |
|---|---|
| [project-brief.md](project-brief.md) | What Learny is *now* (v0.3.0 walkthrough), goal, constraints |
| [meta-output-conventions.md](meta-output-conventions.md) | How official vendor guidance says research reports should be structured; house-convention audit + template |
| [meta-fleet-process.md](meta-fleet-process.md) | How multi-report research efforts should be organized (decomposition, critique, synthesis); fleet-shape audit |
| [rq01-competitive-landscape.md](rq01-competitive-landscape.md) | Who else does book-grounded AI learning; table stakes vs differentiators |
| [rq02-learning-science.md](rq02-learning-science.md) | Evidence-backed learning principles mapped to concrete Learny features |
| [rq03-ai-tutor-pedagogy.md](rq03-ai-tutor-pedagogy.md) | How teach mode becomes a genuinely good AI tutor |
| [rq04-active-recall-quality.md](rq04-active-recall-quality.md) | Quiz/card generation quality bar and review UX |
| [rq05-retrieval-intelligence.md](rq05-retrieval-intelligence.md) | Smarter answers within the pgvector-first constraint |
| [rq06-reading-experience.md](rq06-reading-experience.md) | Reader UX/typography/annotation benchmark; mobile; accessibility |
| [rq07-onboarding-activation.md](rq07-onboarding-activation.md) | First-session time-to-value for a stranger |
| [rq08-motivation-retention.md](rq08-motivation-retention.md) | Streaks/heatmaps/notifications that work without cheapening the product |
| [rq09-public-launch-readiness.md](rq09-public-launch-readiness.md) | Abuse, cost caps, copyright, privacy, moderation for multi-tenant |
| [rq10-pricing-billing.md](rq10-pricing-billing.md) | Pricing landscape, free tier, AI cost model, billing shape (secondary) |
| [rq11-product-architecture.md](rq11-product-architecture.md) | Is the current IA right; restructure proposals |
| [rq12-growth-positioning.md](rq12-growth-positioning.md) | Positioning vs NotebookLM-class tools; landing; sharing; OSS as channel |
| [rq13-ai-integration-patterns.md](rq13-ai-integration-patterns.md) | Deeper AI integration than a chat box: reference products, unused provider capabilities |
| [rq14-multi-provider-models.md](rq14-multi-provider-models.md) | Multi-provider strategy; GLM/Kimi/DeepSeek/Qwen landscape; citation-faithfulness gating |
| [rq15-ai-cost-optimization.md](rq15-ai-cost-optimization.md) | Engineering AI cost down: prompt caching, batch APIs, model tiering, embedding economics |
| [gap-critique.md](gap-critique.md) | Fleet-level critique: coverage map, claim matrix, conflict log, source spot-checks |
| [synthesis.md](synthesis.md) | Prioritized public-launch arc — seven bets, conflict resolutions (candidate RFC-0007) |
| [handoff.md](handoff.md) | Paste-prompt for a fresh session: ship cycle `trustworthy-cited-ask` (Bet 1) |

## Fleet status

- [x] App walkthrough + project brief
- [x] Meta-research: report structure + fleet process vs official vendor guidance (verdict: keep house shape; compensate at critic + synthesizer, don't rewrite reports)
- [x] RQ researchers in parallel (rq01–rq15) — all fifteen answered
- [x] Gap critique — 15/15 coverage, claim matrix, 9 conflicts logged, 12 URL spot-checks held, **zero follow-up memos needed**
- [x] Synthesis — seven launch bets (trustworthy Ask → reader → tutor → review → first session → safety rails → cost), all nine conflicts resolved, candidate **RFC-0007**
