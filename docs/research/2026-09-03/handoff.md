# Handoff — ship cycle: trustworthy-cited-ask (Bet 1 of RFC-0007 arc)

*Paste-prompt for a fresh Claude session in `/home/augusto/projects/learny`. Do not run the cycle from the research chat. Written 2026-09-03; starting state: clean `main` at `4529a9bd`, no `.specs/.ship-status` (no cycle to resume), tlc-spec-driven refreshed at v3.3.0.*

---

You are starting a Learny ship cycle on a clean `main`. Feature slug: **trustworthy-cited-ask**.

Run it end-to-end with the `learny-ship-cycle` skill (plan → build → PR → review → triage → fix → cleanup → gated merge), which drives `tlc-spec-driven` for the specify/design/tasks/execute phases. Auto-select recommended options where the skill offers them. Publish with `learny-finalize` conventions.

## Read first (in order)

1. `docs/research/2026-09-03/synthesis.md` — Bet 1 row, its must-be-true / out-of-scope block, and conflict resolution #1 (cost canonicalization does not apply here, but #5/#9 name what this cycle must NOT touch).
2. `docs/research/2026-09-03/rq13-ai-integration-patterns.md` — §2 capability inventory (the two mutually exclusive Anthropic request shapes; the dropped `cited_text` / char spans) and §4 Cycle 1.
3. `docs/research/2026-09-03/rq01-competitive-landscape.md` §8 items 1 and 4 (table-stakes trust UX), `rq07-onboarding-activation.md` Move 1 (why this blocks activation), `rq05-retrieval-intelligence.md` §10 (abstention context — do not build the autorater this cycle).
4. Code: `backend/app/infrastructure/answering/anthropic.py` (`_build_request`, `_log_call`, stream path), `backend/app/infrastructure/answering/prompts.py`, the conversation-turn service in `backend/app/application/` (find the delete-on-failure path), `frontend/app/components/` ask panel + `citations.tsx` (and the unused `frontend/components/ai-elements/inline-citation.tsx`).

## Why this cycle

Observed 2026-09-03 on the local stack with real provider keys: Ask → OpenAI embeddings 200 → Anthropic `POST /v1/messages` **400 Bad Request** → UI shows generic "Answer generation failed. Please try again." → **the conversation is deleted**. Six research reports flag this as the public-launch blocker; the activation event (`first_cited_answer`) cannot exist while first questions can vaporize. rq13's hypothesis (unconfirmed): request-shape fragility between the citations-enabled shape and thinking/effort config — reproduce with a real request dump before trusting it.

## Scope (must-be-true at merge)

1. **Never lose the thread.** A failed generation turn leaves the conversation and the user's message intact, surfaces the error state in the thread with a retry affordance, and logs enough (request shape, status, `request_id` — never prompt bodies beyond existing redaction) to diagnose provider 4xx. Remove/guard the delete-on-failure behavior.
2. **Root-cause and fix the real-provider 400.** Reproduce with the local stack + real keys (keys are already configured in this environment's compose overrides; a tiny fixture EPUB via `backend/tests/fixtures_epub.py:valid_book` reproduces the walkthrough). Add shape tests that pin BOTH Anthropic request forms (citations-enabled documents vs structured-output JSON) so this regression class fails CI on the deterministic path.
3. **Claim-level citation spans** (may split into a follow-up cycle if 1+2 fill this one — decide at Tasks phase): stop discarding `cited_text` / char offsets from the Citations API. Extend the domain DTO with a Learny-owned `CitedSpan` (adapter maps provider JSON; `document_index` never leaks into domain — ADR-0020). UI: hover on `[^n]` shows the quoted sentence; "Show in book" highlights the exact span. Offsets must be byte-identical to the snippet sent as the Citations `document` body — golden tests assert offset identity.

## Out of scope (do not build)

- Model/provider changes, fallback adapters, Haiku routing (Bet 7; needs its own RFC + ADR-0020 amendment).
- Sufficient-context autorater, retrieval changes, evidence `top_k`, embed headers (rq05 cycles — and if headers ever ship, they stay OUT of Citations document bodies).
- Streaming redesign; teach playbook changes; UI redesign beyond the error state + citation hover.
- Retry loops against Anthropic: on 2+ consecutive provider 5xx/529, check the status page, don't loop (house rule).

## Verification

- `make infra` first for DB/golden tests; `make check` (lint + backend + frontend) must be green; CI parity per root `Makefile`. `LEARNY_TEST_DATABASE_URL` comes from `.claude/settings.json`.
- Deterministic adapters stay the CI default — the 400 fix is verified by shape tests offline plus one manual real-provider pass on the compose stack (document it in the PR body, learny-finalize style).
- Sensor discipline: at least one test that fails if delete-on-failure comes back, and one that fails if `CitedSpan` offsets drift from the document body.

## Process notes

- `.specs/` stays local-only; PR is small and reviewable; author ≠ verifier inside tlc-spec-driven.
- To wait on CI: `gh pr checks <N> --watch` in a background task — never `sleep N && cmd`.
- Any AskUserQuestion must mark a recommended option with why-recommend AND why-not for every option.
- Merge is gated on a single user approval at the end of the ship cycle.
