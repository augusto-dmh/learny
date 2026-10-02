# Handoff — ship cycle: pt-br-interface (row 1 of the v8 candidate arc)

*Paste-prompt for a fresh Claude session in `/home/augusto/projects/learny`. Do not run the cycle from the research chat. Written 2026-10-02; starting state: `main` after the research PR (`docs/research-study-home-delta`) merges, no `.specs/.ship-status` (no cycle to resume). Suggested model: Sonnet 5.5 (scope is mostly mechanical frontend work plus one library decision).*

---

You are starting a Learny ship cycle. Feature slug: **pt-br-interface**.

## Step 0 — precondition

Run `gh pr list --state all --head docs/research-study-home-delta` and confirm the research PR is **merged** and that `.specs/project/ROADMAP.md` on `main` has the `## v8` section with the `pt-br-interface` row. If the PR is still open, stop and ask the user to merge it (do not merge it yourself, and do not branch off the unmerged research branch). Then `git checkout main && git pull`, and verify `git config user.email` is the personal address before the first commit.

Run the cycle end-to-end with the `learny-ship-cycle` skill (plan → build → PR → review → triage → fix → cleanup → gated merge), which drives `tlc-spec-driven` for specify/design/tasks/execute. Auto-select recommended options where the skill offers them. Publish with `learny-finalize` conventions.

## Read first (in order)

1. `.specs/project/ROADMAP.md` — the `v8` section intro and the `pt-br-interface` row (this is the authoritative scope line).
2. `docs/research/2026-09-30/synthesis.md` — sections "Brazil rewards owned-material study…" and the row-detail table entry #1 (goal, non-goals, prerequisites).
3. `docs/research/2026-09-30/learny-state-and-ledger.md` KQ4 — what Portuguese support already exists at the content layer (do not rebuild it).
4. Code: `frontend/app/layout.tsx` (hard-coded `lang="en"` at line 33; Latin font subset already covers Portuguese diacritics), the ~83 `.tsx` files under `frontend/app` and `frontend/components` (all copy is inline English), `frontend/package.json` (Next 15.5, React 19.1, no i18n dependency), the account/preferences surface (`AccountPanel`, the `user_ai_preferences` row from the house-profiles cycle as a pattern for a per-user preference), `backend/app/infrastructure/answering/prompts.py` (where answer/tutor language would be steered), `backend/app/application/language.py`.

## Why this cycle

Brazil is the priority market and 60% of Brazilian internet users are phone-only; the UI is English-only with no i18n framework, so no Portuguese-speaking stranger can use Learny today. Content-side Portuguese (language detection, `portuguese` FTS regconfig, OCR `en,pt`, PT quiz stopwords) already works. Gemini Notebook is fully localized in pt-BR, so an English-only UI loses before the loop is ever seen.

## Scope (must-be-true at merge)

1. **An i18n framework in the frontend with en + pt-BR catalogs.** Pick the library at Design phase and record it in an ADR (a durable frontend decision). The recommended default is `next-intl` (App Router + React Server Components native); reject anything that requires a client-only provider for server-rendered copy. **Locale without URL prefixes** is the recommended routing (cookie + `Accept-Language` negotiation, `en` fallback) so existing routes, redirects and the same-origin proxy stay untouched; justify in the ADR if you choose otherwise.
2. **Every user-facing string goes through the catalog**, including landing, auth, library, reader chrome, Chat dock, review, notes, account, empty/error/loading states, and email-facing copy the frontend renders. Legal pages (`/terms`, `/privacy`, `/copyright`) may stay English-only this cycle if translating them needs legal review; say so in the PR. `<html lang>` follows the active locale.
3. **Locale is a learner choice that persists**: a selector in Account, stored per user (backend-authoritative, same pattern as the house-profile preference), with the cookie for anonymous visitors.
4. **Catalog completeness is enforced by a test**: a sensor that fails when a key exists in `en` but not in `pt-BR` (and vice versa), plus one that fails if a hard-coded English string reappears in a translated component (pick a practical heuristic; document its limits).
5. **AI output language (decide at Tasks phase whether it fits; split into a follow-up row if not).** The tutor and Ask answer in the learner's UI language while quoting citations verbatim in the book's language. If it ships, it is a prompt-level change behind the existing ports, with a deterministic-adapter test; a pt-BR golden fixture from a public-domain Portuguese book goes into the offline eval set. Judged (real-provider) eval of pt-BR is blocked until the operator funds the CI Anthropic key — do not try to work around that.

## Out of scope (do not build)

- Machine translation of book text, citations, or notes.
- Changes to retrieval, FTS language handling, chunking, or embeddings (they already work for Portuguese).
- A pt-BR-specific model or provider; any new provider SDK (ADR-0019/0020 lock).
- Languages beyond en and pt-BR (the framework must make a third locale a catalog-only change, but do not ship one).
- PWA, offline, adult-only gate, Biblioteca Aberta, BYOK — those are later v8 rows.
- URL-prefixed locale routing unless the ADR justifies it.

## Verification

- `make infra` first for DB/golden tests; `make check` (lint + backend + frontend) must be green; CI parity per root `Makefile`. `LEARNY_TEST_DATABASE_URL` comes from `.claude/settings.json`.
- Deterministic adapters stay the CI default; no provider keys needed.
- Manual pass on `docker compose up --build`: switch to pt-BR in Account, walk landing → register → library → reader → Chat → review in Portuguese, and record it in the PR body (learny-finalize style). Screenshots for visible UI changes.
- Sensor discipline: the catalog-parity test and the hard-coded-string test must be shown to fail on a deliberate break before they are trusted.

## Process notes

- `.specs/` stays local-only; PR is small and reviewable (split at spec time if the string migration is too large for one review — e.g. framework + shell + Account selector first, remaining surfaces second); author ≠ verifier inside tlc-spec-driven.
- Docker runs via Docker Desktop's WSL2 integration — if `docker` fails, run `docker info` and ask the user to start Docker Desktop instead of debugging.
- `jq` is not installed; use `python3` for JSON.
- To wait on CI: `gh pr checks <N> --watch` in a background task — never `sleep N && cmd`.
- Any AskUserQuestion must mark a recommended option with why-recommend AND why-not for every option.
- On 2+ consecutive provider 5xx/529 errors (Anthropic, GitHub), check the provider's status page before retrying; on a confirmed outage, park with one long wakeup instead of retry loops. These rules apply to subagents too — include them in delegated briefs.
- Merge is gated on a single user approval at the end of the ship cycle.
