# Learny — project brief (public-launch fleet, 2026-09-03)

*Working memory for this research fleet. Distill product conclusions into ADRs/RFCs; keep this folder as evidence.*

## Thesis

**Learny is book intelligence with citations you can trust.** It ingests EPUB and PDF books preserving structure, answers questions with passage-level citations, runs guided teaching sessions anchored to book sections, generates active-recall quizzes scheduled by FSRS, and keeps a second-brain loop: highlights/notes captured in the reader feed cited Q&A, promote to review cards, and export to an Obsidian-compatible vault.

Shipped: v0.3.0 (MVP + RFC-002 v2 + RFC-003 v3, all cycles merged). Stack: FastAPI + Celery + PostgreSQL/pgvector + MinIO behind a Next.js 15 same-origin proxy, deployed CI → GHCR → VPS behind Caddy. 27 ADRs; hexagonal backend with provider adapters (OpenAI embeddings, Anthropic Claude generation) behind Learny-owned ports, deterministic offline adapters as default.

## Goal of this fleet

**Open Learny to the public.** Research what makes the product (a) more intelligent, (b) more attractive to a general learning audience, and (c) operationally/commercially ready for public multi-tenant use — with product quality and feature depth prioritized over monetization. Pricing/billing is researched but explicitly secondary.

## What the app looks like today (walkthrough 2026-09-03, local compose, real provider keys)

- **Landing page** is a bare title + tagline ("Turn your books into cited answers and lasting recall.") with Create account / Log in links. No screenshots, demo, or value explanation.
- **Register** is email + password only, no verification; drops you on **Home**: "Continue reading" card, "Reviews due" card, and a GitHub-style 12-week study-activity heatmap (reviews + pages counted).
- **Bookshelf** (`/sources`): upload form (Title + file picker labeled "EPUB file" even though PDF is supported), source list with status chip. A ready book gets Ask / Teach / Read links + "Generate quiz deck" + "Re-ingest".
- **Reader** (`/read`): TOC sidebar, per-chapter content with stable anchors, reading progress ("0% read · 1 min left"), Aa typography settings, per-chapter highlights list, chapter next/prev navigation. Images are blocked placeholders.
- **Dock panel** in the reader hosts tabs: **Ask / Teach / Notes / Review** — asking happens beside the text. Ask has suggested prompts, conversation list, and a "Search my notes too" toggle (default on) with a clear explanation.
- **Review** (`/review`): cross-source due queue; empty state is "Nothing due right now" + back-to-library link.
- **Observed failure**: with real keys configured, a question produced OpenAI embedding 200 → Anthropic `POST /v1/messages` **400 Bad Request** → red text "Answer generation failed. Please try again", and the conversation was deleted. No error detail, no retry affordance beyond re-typing. (Deterministic adapters presumably still fine; this is the real-provider path on a tiny fixture book.)
- Quiz deck generation on the tiny fixture book "succeeded" in 0.02s with nothing reviewable — no feedback about how many items were created or why none were.

## Known deferred/forward items (recorded, not yet decided)

- Paragraph-level note chunking for retrieval; fuzzy re-anchoring; graph UI; block/outliner editor (ADR-0026 deferrals).
- Notes in *teaching* retrieval default-on; vault import/round-trip sync (export is one-way by design).
- Multi-provider / BYOK generation + embeddings; dedicated vector DB or reranker if pgvector hybrid stops scaling.
- **A publicly hosted multi-tenant instance** — the exact goal this fleet serves; no decision recorded yet.

## Constraints this fleet must respect

- Hexagonal boundaries: provider SDKs stay behind Learny-owned ports; no LangChain/LlamaIndex core (ADR-0007/0009). New provider SDKs only via an accepted cycle (ADR-0019/0020 lock OpenAI embeddings + Anthropic generation).
- Citations and evaluation are core requirements, not polish (ADR-0003); deterministic offline adapters remain the CI default.
- PostgreSQL hybrid search first (ADR-0006); a reranker/vector DB is a recorded escape hatch, not the default recommendation.
- Docker Compose on VPS is the deployment model (ADR-0008/0023); recommendations should scale that model before proposing Kubernetes/PaaS rewrites.
- Recommendations must be shippable as small spec-driven cycles (the repo's working style), not big-bang rewrites.

## Research questions (one report each, `rqNN-<slug>.md`)

1. Competitive landscape: who else does book-grounded AI learning, table stakes vs differentiators.
2. Science of learning: which evidence-backed principles are unexploited, mapped to concrete features.
3. AI tutor pedagogy: how the teach mode becomes a genuinely good tutor, not a Q&A skin.
4. Active-recall quality: card generation and review-experience quality bar.
5. Retrieval intelligence: making answers smarter with the pgvector-first constraint.
6. Reading experience: reader UX/typography/annotation benchmark, mobile and accessibility.
7. Onboarding & activation: first-session time-to-value for a stranger.
8. Motivation & retention: heatmap/streak/notification mechanics that work without cheapening the product.
9. Public-launch readiness: abuse, cost caps, copyright/DMCA, privacy, moderation, email verification.
10. Pricing & billing (secondary): landscape, free-tier shape, AI cost model, Stripe integration shape.
11. Product architecture: is the current IA (Home/Bookshelf/Review/Notes + reader dock) the right shape; restructure proposals.
12. Growth & positioning: value prop vs NotebookLM-class tools, landing page, sharing/community, OSS as channel.
13. Deeper AI integration: patterns from reference products (NotebookLM, Perplexity, Notion AI, Readwise Ghostreader); unused provider capabilities (prompt caching, batch, structured outputs, multimodal, audio).
14. Multi-provider strategy: new model landscape (GLM, Kimi, DeepSeek, Qwen, MiniMax), hosting/privacy trade-offs, citation-faithfulness gating, provider matrix behind the existing ports.
15. AI cost optimization: prompt caching, batch APIs, model tiering, embedding economics, token budgets, per-user cost observability.

## Success for the fleet

A synthesis naming a prioritized public-launch arc (candidate RFC-004) with must-be-true / out-of-scope per cycle, grounded in the RQ evidence — ready to materialize as an RFC in the repo.
