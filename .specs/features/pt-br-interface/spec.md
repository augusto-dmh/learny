# pt-br-interface Specification

## Problem Statement

Learny's interface is English-only: `frontend/app/layout.tsx` hard-codes `lang="en"`, there is no i18n framework, and every string is an inline literal in ~59 client and ~24 server components plus the `app/lib` request clients. Brazil is the priority market and most of its learners are phone-first, so a Portuguese-speaking stranger cannot use Learny today, even though the content layer (language detection, the `portuguese` FTS regconfig, OCR, Portuguese quiz stopwords) already handles Portuguese books. This cycle makes the whole interface available in pt-BR, makes the locale a persistent learner choice, and makes the tutor and Ask answer in the learner's language while citations stay verbatim in the book's language.

## Goals

- [ ] A learner can use landing, auth, library, reader, Chat dock, review, notes and account entirely in pt-BR; every non-legal user-facing string comes from a catalog.
- [ ] The locale is a per-user, backend-stored choice (Account selector) with a cookie for anonymous visitors, and `<html lang>` follows it.
- [ ] Two sensors keep it true: catalog parity (keys and placeholders) and hard-coded-string detection, each shown failing on a deliberate break.
- [ ] A pt-BR learner's Ask and tutor answers are written in Portuguese from an English book, citations unchanged; a Portuguese public-domain golden fixture is in the offline eval set.

## Out of Scope

| Feature | Reason |
|---|---|
| Machine translation of book text, citations, notes or user content | Citations stay verbatim in the book's language; user content is the user's. |
| Retrieval, FTS language handling, chunking, embeddings | Already correct for Portuguese (ledger KQ4); no change. |
| A pt-BR-specific model or provider; new provider SDKs | ADR-0019/0020 lock. |
| Locales beyond `en` and `pt-BR` | A third locale must be a catalog-only change; none ships. |
| URL-prefixed locale routing | Cookie + `Accept-Language` keeps routes, redirects and the same-origin proxy untouched (ADR). |
| Translating `/terms`, `/privacy`, `/copyright` | Legal text needs the LGPD legal pass (operator prerequisite); they stay English with `lang="en"` on their content. Called out in the PR. |
| Localizing backend-sent emails (verify, reset) | Needs a locale argument on `EmailPort` and register/reset flows; recorded as a follow-up row, not this cycle. |
| Localizing quiz/card generation prompts and the eval judge prompts | Cards are generated from the book's language; only Ask and tutor answers speak the UI language. |
| PWA, offline, adult gate, public-domain shelf, BYOK | Later v8 rows. |
| Judged real-provider pt-BR eval | Blocked on the operator funding the CI Anthropic key; not worked around. |
| Operator-configured copy (`LearnerProfile.display_name`/`description`) | Operator-authored settings text; rendered as given. |

---

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
|---|---|---|---|
| i18n library | `next-intl` (v4), no-routing setup, RSC-native | Matches the recommended default; server components translate without a client provider; ADR-0032 records it. | y (handoff) |
| Routing | No URL prefix; cookie `learny_locale` then `Accept-Language`, fallback `en` | Existing routes/redirects/proxy stay untouched. | y (handoff) |
| Where the locale preference lives | New table `user_locale_preferences` (PK `user_id`), port/repo/entity, `PUT`/`DELETE /api/me/locale`, `locale` on `GET /api/me` | Mirrors the house-profile pattern; keeps `user_ai_preferences` single-purpose. | n (agent) |
| How the server renders without a per-request backend call | The cookie is the render-time cache of the choice; the logged-in client syncs the cookie from `GET /api/me` `locale` (backend wins on conflict) and refreshes | Avoids an API round-trip in the root layout; backend stays authoritative. | n (agent) |
| Anonymous switcher | A compact language switcher on landing and auth screens sets the cookie only | Account is unreachable to anonymous visitors. | n (agent) |
| Supported-locale values | `en`, `pt-BR` (BCP 47, case-exact); any `pt`, `pt-PT` negotiated Accept-Language maps to `pt-BR`; cookie/API values outside the set are rejected | One Portuguese catalog; invalid values never reach rendering. | n (agent) |
| Tests keep asserting English | Vitest setup binds `next-intl` to the real `use-intl` translator over the `en` catalog; a helper renders in `pt-BR` | Real ICU formatting without wrapping ~77 test files in providers. | n (agent) |
| Lib request clients stop owning copy | Clients throw errors carrying `operation` key + `status` (+ `detail`); components render localized text from the catalog by operation/status; backend `detail` stays on the error object but is not shown to the learner | `detail` is English API text; showing it would leak English into pt-BR. | n (agent) |
| Answer language rule | The instruction is added only for non-`en` locales (pt-BR now); `en` sends no instruction so existing prompts, snapshots and the cacheable system prefix are unchanged | Preserves current behavior and byte-stable frozen prompts. | n (agent) |
| Answer-language source | Stored locale when set, else the request's `Accept-Language` negotiation, else `en` | A pt-BR browser user who never opens Account still gets Portuguese answers; the proxy already forwards headers. | n (agent) |
| Where the language instruction goes | In the user-turn envelope (tutor) / question turn (Ask), never the frozen system prompts | Keeps `ANSWER_SYSTEM_PROMPT`/`TEACHING_SYSTEM_PROMPT` byte-stable for caching. | n (agent) |
| pt-BR golden source | An excerpt of a public-domain Portuguese work (Machado de Assis, d. 1908) built into a synthetic-style EPUB in code, plus authored cases | Public domain in Brazil and worldwide; matches the in-code golden pattern (no committed EPUB binary). | n (agent) |
| Dates, numbers, relative times | Formatted with `Intl` through next-intl formatters keyed by the active locale | There is no existing formatter to preserve. | n (agent) |

**Open questions:** none - all resolved or logged above.

---

## User Stories

### P1: The framework, negotiation and `<html lang>` ⭐ MVP

**User Story**: As a visitor whose browser prefers Portuguese, I want Learny to render in pt-BR without any setup so that I can use it immediately.

**Why P1**: Nothing else works without a catalog pipeline and a deterministic locale decision.

**Acceptance Criteria**:

1. The system SHALL support exactly the locales `en` and `pt-BR`, with `en` as the fallback.  <!-- ubiquitous -->
2. WHEN a request carries a `learny_locale` cookie with a supported value THEN the system SHALL render that locale regardless of `Accept-Language`.  <!-- event-driven -->
3. WHEN no valid `learny_locale` cookie is present and `Accept-Language` lists a `pt` or `pt-*` tag before any `en` tag THEN the system SHALL render `pt-BR`.  <!-- event-driven -->
4. IF the `learny_locale` cookie holds a value outside `{en, pt-BR}` THEN the system SHALL ignore it and negotiate from `Accept-Language`.  <!-- unwanted-behavior -->
5. IF neither the cookie nor `Accept-Language` yields a supported locale THEN the system SHALL render `en`.  <!-- unwanted-behavior -->
6. The system SHALL set `<html lang>` to `en` or `pt-BR` matching the rendered locale.  <!-- ubiquitous -->
7. The system SHALL resolve translations for server components on the server without requiring a client-only provider for server-rendered copy.  <!-- ubiquitous -->
8. WHERE a third locale catalog and its entry in the supported-locale list are added THE system SHALL render it with no change to routing, middleware or components.  <!-- optional-feature -->

**Independent Test**: Request `/` with `Accept-Language: pt-BR,pt;q=0.9,en;q=0.8` and no cookie, and observe `<html lang="pt-BR">` and Portuguese copy; add `learny_locale=en` and observe English.

---

### P1: Every user-facing surface comes from the catalog ⭐ MVP

**User Story**: As a pt-BR learner, I want landing, sign-in, library, reader, Chat, review, notes and account in Portuguese so that I never hit an English screen.

**Why P1**: A half-translated interface still loses to Gemini Notebook.

**Acceptance Criteria**:

1. WHILE the locale is `pt-BR` the system SHALL render landing, login, register, password-reset and email-verification screens, app shell (sidebar, header, theme toggle, shortcuts), Home, Library, reader chrome, Chat dock (Ask, Tutor, Notes, Review tabs), review sessions, notes screens, account, and every empty, error and loading state from the pt-BR catalog.  <!-- state-driven -->
2. WHEN a request client (`app/lib/*`) receives a non-OK response THEN the system SHALL show the learner copy chosen from the catalog by the failed operation and HTTP status, in the active locale.  <!-- event-driven -->
3. IF an operation fails with HTTP 401, 429 or a 5xx status THEN the system SHALL show the shared localized message for that status class rather than the operation's generic failure copy.  <!-- unwanted-behavior -->
4. The system SHALL NOT display a backend-sent English `detail` string to the learner.  <!-- ubiquitous -->
5. WHILE the locale is `pt-BR` the system SHALL format dates, times, numbers and plural-dependent counts with that locale's rules via the i18n formatters (e.g. "1 cartão" / "2 cartões").  <!-- state-driven -->
6. The system SHALL keep the legal pages `/terms`, `/privacy` and `/copyright` in English in every locale, with `lang="en"` on their content wrapper.  <!-- ubiquitous -->
7. The system SHALL keep book text, citation snippets, section titles and user-authored notes unchanged in every locale.  <!-- ubiquitous -->
8. WHEN the English locale is active THEN the system SHALL render the same English copy the interface shows today for every migrated string, except the error copy changed by criteria 2-4.  <!-- event-driven -->

**Independent Test**: With `learny_locale=pt-BR`, walk landing → register → library → reader → Chat → review and see no English UI copy outside the legal pages and book content.

---

### P1: Locale is a learner choice that persists ⭐ MVP

**User Story**: As a learner, I want to choose my language in Account and have it follow me across devices so that I never have to re-select it.

**Why P1**: Negotiation guesses; the learner decides, and the choice must survive a new device.

**Acceptance Criteria**:

1. WHEN an authenticated learner chooses a locale in Account THEN the system SHALL persist it through `PUT /api/me/locale` and re-render the interface in that locale.  <!-- event-driven -->
2. WHEN an authenticated learner chooses "Automatic" in Account THEN the system SHALL clear the stored choice through `DELETE /api/me/locale` (204, idempotent) and fall back to negotiation.  <!-- event-driven -->
3. The system SHALL return the stored locale (or `null`) as `locale` on `GET /api/me`.  <!-- ubiquitous -->
4. IF `PUT /api/me/locale` receives a value outside `{en, pt-BR}` THEN the system SHALL respond 422 and store nothing.  <!-- unwanted-behavior -->
5. IF `PUT /api/me/locale` lacks a valid CSRF token or session THEN the system SHALL respond 403 or 401 respectively and store nothing.  <!-- unwanted-behavior -->
6. WHEN an authenticated page loads and `GET /api/me` returns a `locale` that differs from the `learny_locale` cookie THEN the system SHALL set the cookie to the stored value and refresh the rendered locale.  <!-- event-driven -->
7. WHEN an anonymous visitor picks a language on the landing or auth switcher THEN the system SHALL set the `learny_locale` cookie (path `/`, one year, `SameSite=Lax`) and re-render, without any API call.  <!-- event-driven -->
8. IF saving the choice fails THEN the system SHALL keep the previous locale and show a localized error in Account.  <!-- unwanted-behavior -->
9. WHEN a learner's account is deleted or the user row is removed THEN the system SHALL remove the stored locale with it (FK cascade).  <!-- event-driven -->

**Independent Test**: Choose pt-BR in Account, clear cookies, sign in again, and the interface renders in pt-BR.

---

### P1: Catalog completeness is enforced by tests ⭐ MVP

**User Story**: As a maintainer, I want CI to fail when a catalog drifts or an English literal reappears so that translation stays true after this cycle.

**Why P1**: A migration without a sensor decays on the next feature.

**Acceptance Criteria**:

1. IF a message key exists in one catalog and not the other THEN the parity test SHALL fail and name the key and the missing locale.  <!-- unwanted-behavior -->
2. IF a message exists in both catalogs but uses different ICU argument names THEN the parity test SHALL fail and name the key.  <!-- unwanted-behavior -->
3. IF a translated component contains a JSX text node or a user-facing attribute literal (`aria-label`, `title`, `placeholder`, `alt`) holding English-looking words outside the documented allowlist THEN the hard-coded-string test SHALL fail and name file and line.  <!-- unwanted-behavior -->
4. The system SHALL document the hard-coded-string heuristic's limits (what it scans, what it cannot see) in the test file header and in the ADR.  <!-- ubiquitous -->
5. IF a catalog key referenced by a component does not exist in `en` THEN `tsc --noEmit` SHALL fail through typed message keys.  <!-- unwanted-behavior -->

**Independent Test**: Delete one key from `pt-BR.json`, add `<p>Hello there</p>` to a component, run `make test-frontend`, and see each sensor fail.

---

### P2: Tutor and Ask answer in the learner's language

**User Story**: As a Brazilian learner reading an English book, I want the tutor and Ask answers in Portuguese with citations in the book's own words so that I can learn in my language without losing the source.

**Why P2**: The second half of the goal, but separable if it does not fit (Tasks decision).

**Acceptance Criteria**:

1. WHEN an Ask or tutor turn is posted and the effective locale is `pt-BR` THEN the system SHALL pass `pt-BR` to the generation port as the response language.  <!-- event-driven -->
2. WHEN the effective locale is `en` THEN the system SHALL pass no response language, leaving prompts and cache prefixes byte-identical to today.  <!-- event-driven -->
3. The system SHALL derive the effective locale from the stored locale, else the request `Accept-Language` negotiation, else `en`.  <!-- ubiquitous -->
4. WHEN the Anthropic adapter builds a request with a response language THEN the system SHALL carry the instruction in the user turn and leave the system prompt unchanged.  <!-- event-driven -->
5. WHEN the OpenAI-compatible adapter builds a request with a response language THEN the system SHALL carry the instruction in the user turn.  <!-- event-driven -->
6. The system SHALL keep the whole-reply not-found sentinel `NOT_FOUND_IN_SOURCE` unlocalized and keep citation snippets verbatim from the evidence.  <!-- ubiquitous -->
7. The deterministic adapter SHALL accept the response language and return identical output for every language value.  <!-- ubiquitous -->
8. IF a generation adapter does not support a response language THEN the system SHALL answer exactly as it does without one.  <!-- unwanted-behavior -->

**Independent Test**: A recording fake adapter shows the pt-BR value reaches the port for a pt-BR user and none for an `en` user; the Anthropic adapter's built request shows the instruction in the user turn only.

---

### P2: A Portuguese public-domain golden fixture

**User Story**: As a maintainer, I want a Portuguese book in the offline eval set so that Portuguese ingestion, retrieval and citation behavior is proved without a provider key.

**Why P2**: The Portuguese content path is claimed but unproven by a fixture.

**Acceptance Criteria**:

1. The system SHALL include a Portuguese golden book (OPF `dc:language` `pt`) built in code from a public-domain Portuguese source, with its provenance recorded in the fixture module.  <!-- ubiquitous -->
2. WHEN the Portuguese golden book is ingested THEN the system SHALL store its chunks with `search_config` `portuguese` and match the expected section/anchor structure.  <!-- event-driven -->
3. WHEN a golden Portuguese question uses an inflected form of a term in the target section THEN retrieval SHALL return that section's anchor within the top 3 results.  <!-- event-driven -->
4. WHEN the deterministic adapter answers a Portuguese golden question THEN every cited chunk id SHALL belong to the retrieved evidence and cite the expected anchor.  <!-- event-driven -->
5. The system SHALL keep the Portuguese fixture runnable offline with the deterministic adapters and no provider key.  <!-- ubiquitous -->

**Independent Test**: `make test-backend` runs the Portuguese golden retrieval and citation checks with `LEARNY_TEST_DATABASE_URL` and no network.

---

## Edge Cases

- IF the `Accept-Language` header is absent or malformed THEN the system SHALL render `en`.
- IF a stored locale is later removed from the supported set THEN the system SHALL treat it as unset (negotiate) and not error.
- WHEN a catalog string contains an ICU plural and the count is zero THEN the system SHALL render the locale's zero/other form without throwing.
- IF the cookie names `pt-BR` and the stored locale is `en` after login THEN the stored `en` SHALL win and the cookie SHALL be rewritten.
- WHILE the locale refresh is in flight the system SHALL NOT drop unsent Chat input or reader position (refresh re-renders; it does not reload the page).

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
|---|---|---|---|
| I18N-01 | P1: Framework, negotiation, `<html lang>` (criteria 1-8) | Design | Pending |
| I18N-02 | P1: Every surface from the catalog (criteria 1, 5-8) | Design | Pending |
| I18N-03 | P1: Error copy from catalog, never backend `detail` (criteria 2-4) | Design | Pending |
| I18N-04 | P1: Locale persists, backend-authoritative (criteria 1-5, 8-9) | Design | Pending |
| I18N-05 | P1: Cookie sync and anonymous switcher (criteria 6-7) | Design | Pending |
| I18N-06 | P1: Parity sensor (criteria 1-2, 5) | Design | Pending |
| I18N-07 | P1: Hard-coded-string sensor (criteria 3-4) | Design | Pending |
| I18N-08 | P2: Response language reaches ports and adapters (criteria 1-8) | Design | Pending |
| I18N-09 | P2: Portuguese golden fixture (criteria 1-5) | Design | Pending |

**Coverage:** 9 total, 0 mapped to tasks, 9 unmapped ⚠️

---

## Success Criteria

- [ ] A pt-BR learner completes landing → register → library → reader → Chat → review with no English UI copy outside the legal pages.
- [ ] `make check` is green; the parity and hard-coded-string sensors each fail on a deliberate break shown in the PR.
- [ ] A pt-BR user's Ask answer on an English book is requested in Portuguese while citations stay verbatim (verified offline at the port/adapter level; judged quality is blocked on the funded CI key).
- [ ] Adding a third locale needs only a catalog file and one list entry.
