# pt-br-interface — Decision Context

Auto-decided per the ship-cycle protocol (options weighed, recommended picked, recorded here + STATE.md). None met the escalation bar: the roadmap row and the 2026-09-30 handoff fix the scope, the library and routing defaults are the handoff's own recommendations, and no new provider SDK enters (ADR-0019/0020 lock).

## D-1 — i18n library and routing (AD-363, ADR-0032)

**Options:**
- **(a) `next-intl` v4, no URL prefix, cookie + `Accept-Language` negotiation — CHOSEN.** Why: RSC-native (`getTranslations`/`useTranslations` work in server components with no client provider for server copy), ICU plurals/dates/numbers built in, typed message keys through `AppConfig`, `use-intl` exposes `createTranslator` for provider-free tests. No prefix keeps routes, redirects, the `(app)/(auth)/(read)` groups and the catch-all `/api/[...path]` proxy untouched. Why not: ships the full catalog to the client provider (tens of KB per locale); a prefix-less setup has no built-in `Accept-Language` negotiation, so Learny owns ~20 lines of it.
- (b) `next-intl` with `/[locale]` routing. Why: canonical for SEO and shareable per-language URLs. Why not: moves every route under `[locale]`, rewrites redirects and links, risks the proxy catch-all and the auth flow, and the product is a signed-in app with no SEO surface beyond the landing.
- (c) `react-i18next`/`i18next`. Why: mature, large ecosystem. Why not: client-first; server components need extra wiring, and server-rendered copy would need a provider — the handoff's explicit rejection criterion.
- (d) Hand-rolled dictionary + context. Why: no dependency. Why not: reimplements ICU plurals and formatting, no typed keys, more code to own than the library.

## D-2 — Where the preference lives (AD-364)

**Options:**
- **(a) New table `user_locale_preferences` (`user_id` PK/FK cascade, `locale text NOT NULL`, timestamps), its own port/repository/entity, `PUT`/`DELETE /api/me/locale`, `locale` on `GET /api/me` — CHOSEN.** Why: mirrors the house-profile pattern the handoff names; keeps `user_ai_preferences` single-purpose (a profile row means "chose a profile"); absent row = automatic. Why not: one more small table and repository for a single column.
- (b) Add a nullable `locale` column to `user_ai_preferences`. Why: no new table. Why not: the row's existing semantics (deleted when the profile resets) would couple two unrelated choices, and `profile_id` is `NOT NULL`.
- (c) Add a column to `users`. Why: one fewer join; `/me` already loads the user. Why not: `User` is wired through identity, verification and reset paths and the sample-owner logic; widening it for a preference is a wider blast radius than a dedicated row.

No `GET /api/me/locale`: `GET /api/me` already carries it (a second read endpoint would be unconsumed surface).

## D-3 — Cookie as render-time cache, backend authoritative (AD-365)

**Options:**
- **(a) Cookie `learny_locale` is what server rendering reads; the logged-in client reconciles it from `/api/me` `locale` (backend wins) and refreshes — CHOSEN.** Why: the root layout needs the locale before any client code runs and must not add a backend call to every render; reconciliation is one cheap compare on a request the shell already makes. Why not: a first paint on a new device can flash the negotiated locale before the stored one applies (one refresh); the cookie is client-writable, so it cannot be trusted for anything but rendering (it is only ever validated against the two-value set).
- (b) Root layout fetches `/api/me` server-side with the session cookie. Why: no flash, no sync code. Why not: adds a backend round-trip and an auth dependency to every server render, including the public landing, and couples layout rendering to API availability.
- (c) Backend sets the cookie. Why: no client sync code. Why not: the Next.js proxy would have to rewrite `Set-Cookie` on `PUT /api/me/locale` and on login; the proxy deliberately forwards bodies and cookies unchanged.

## D-4 — Locale change mechanics (AD-366)

Client sets `document.cookie` (`learny_locale=<v>; path=/; max-age=31536000; samesite=lax`, `Secure` when served over https) and calls `router.refresh()`; no server action, no route handler (a `/api/locale` route would be shadowed by the `/api/[...path]` proxy catch-all). `refresh()` re-renders server components with the new cookie and keeps client state (Chat input, scroll), satisfying the no-reload edge case. The stored choice is written first; the cookie changes only after the PUT succeeds, so a failure leaves the previous locale.

## D-5 — Error copy: operation key + status, never backend `detail` (AD-367)

**Options:**
- **(a) Lib clients throw `ApiError {operation, status, detail}`; components render `errors.operation.<op>` / `errors.status.<class>` from the catalog; `detail` stays on the object for logs — CHOSEN.** Why: backend `detail` is English API text (`error_handlers.py`, `application/errors.py`); showing it leaks English into pt-BR, and the lib fallbacks are English literals the sensor could not otherwise catch. Why not: drops some informative English detail (e.g. 422 bounds) from the English UI too; one coordinated refactor across 11 lib modules and their consumers.
- (b) Backend returns error codes, frontend maps codes. Why: precise copy. Why not: a cross-cutting API contract change across dozens of error sites for no learner-visible gain this cycle; operation+status is enough.
- (c) Keep showing `detail`, translate only fallbacks. Why: minimal change. Why not: leaves English in pt-BR whenever the backend explains the failure — the common case.

## D-6 — Test strategy for the existing English suite (AD-368)

**Options:**
- **(a) Vitest `setupFiles` mocks `next-intl` / `next-intl/server` onto `use-intl`'s real `createTranslator`/`createFormatter` over the `en` catalog, with a `setTestLocale()` helper for pt-BR — CHOSEN.** Why: real ICU behavior, no provider wrapping in ~77 test files, existing English assertions keep working where copy is unchanged. Why not: the mock is a seam that could drift from the real provider wiring; one layout-level test renders the real `NextIntlClientProvider` to cover it.
- (b) Wrap every `render` in `NextIntlClientProvider` via a helper. Why: closest to production. Why not: edits every test file, hundreds of lines of churn that hide real changes in review.

## D-7 — Hard-coded-string sensor shape (AD-369)

A vitest test parses every `.tsx` under `app/`, `components/` with the TypeScript compiler API (already a devDependency) and flags (1) JSX text nodes with ≥2 ASCII letters, (2) string-literal values of `aria-label`, `title`, `placeholder`, `alt`, `aria-description`, `label` JSX attributes, and (3) in `app/lib/*.ts`, a string-literal argument to `new Error(`/`new ApiError(`. A small allowlist covers non-copy tokens (brand "Learny", keyboard glyphs, code identifiers) and operator-only surfaces (`dev/evals`), each with a reason. Legal pages are excluded by path. **Ratchet:** a `PENDING_FILES` list starts with every not-yet-migrated file and each migration task removes its files; the list must be empty at merge, and the test fails if a listed file is already clean (so the list cannot rot). **Limits (documented in the test header and ADR):** it cannot see strings built in JS expressions (`const label = cond ? "Save" : "Saved"`), template literals, strings in non-`.tsx` modules other than `app/lib` error constructors, or English words inside `t()` arguments; it does not judge translation quality; and it is blind to text rendered by third-party components. Catalog parity is a separate, stricter sensor (D-8).

## D-8 — Catalog completeness (AD-370)

Typed keys: `AppConfig.Messages = typeof en`, so a key used in code but missing in `en` fails `tsc --noEmit` (already a `make lint` gate). Parity test: flatten both catalogs, assert identical key sets and identical ICU argument-name sets per key (parsed from `{name}`, `{n, plural, …}` headers) — it names the key and the missing locale. A deliberate break of each sensor is shown failing in the PR.

## D-9 — AI output language scope and mechanics (AD-371)

Fits this cycle (Tasks decision): the change is a single optional `response_language` kwarg threaded through one port, one use case, two prompt-building adapters and the router; no schema change. **Options for the instruction site:** (a) user turn only, leaving `ANSWER_SYSTEM_PROMPT`/`TEACHING_SYSTEM_PROMPT` frozen — CHOSEN (they are byte-stable cacheable prefixes; the cache breakpoint sits on the last document/system block, so a user-turn suffix does not invalidate it); (b) per-language system-prompt constants — rejected: doubles the cached prefixes and the frozen-prompt tests; (c) a post-hoc translation call — rejected: a second provider call that can alter citations, against "no machine translation".
**Rules:** the instruction is added only for non-`en` locales (`en` leaves every prompt and snapshot byte-identical); effective locale = stored → `Accept-Language` negotiation → `en`; the not-found sentinel stays the English whole-reply token; citation text is evidence-verbatim (provider-native citations on Anthropic, `[^n]` markers on compat). The deterministic adapter accepts and ignores the language (it returns book text). Quiz/card prompts are untouched (out of scope).

## D-9b — pt-BR golden fixture source (AD-372)

A synthetic-style EPUB built in code (`tests/golden_pt_corpus.py`, mirroring `golden_corpus.py` and AD-037) from short excerpts of one public-domain Machado de Assis work, with Project Gutenberg provenance in the module docstring. Public domain worldwide (author d. 1908). Excerpt text is fetched from the source, never reconstructed from memory.

## D-10 — One PR (AD-373)

~20 tasks, mostly mechanical string migration. Kept as one PR with phase-ordered commits (backend preference → framework → shared client plumbing → surface migrations → AI language → fixture) so a reviewer can read it phase by phase; the ratchet sensor keeps every intermediate commit green. Splitting was considered (framework+shell first) and rejected: two ship cycles for one roadmap row and a half-translated main between them. Revisit only if the diff exceeds what review can bear; the phase order makes a cut point at "after surface migration" free.
