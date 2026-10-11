# ADR-034: Interface Language With next-intl, No URL Prefix

- **Date**: 2026-10-02
- **Status**: Accepted (2026-10-02, rides the implementing cycle's merge gate)
- **Deciders**: Augusto, Claude
- **Tags**: frontend, i18n, brazil, preferences

## Context and Problem Statement

Learny's interface was English-only: `<html lang="en">` was hard-coded, there was no i18n dependency, and every learner-facing string was an inline literal across ~80 components and the request clients. Brazil is the priority market, Gemini Notebook is fully localized in pt-BR, and the content layer already handles Portuguese books (language detection, the `portuguese` FTS configuration, Portuguese quiz stopwords). A Portuguese-speaking stranger could ingest and search a Portuguese book but could not read the product around it.

The interface needs a catalog framework, a rule for choosing the locale per request, a persistent learner choice, and a way to keep the catalogs honest after this cycle.

## Decision Drivers

- Server-rendered copy must not need a client-only provider.
- Existing routes, redirects, the `(app)`/`(auth)`/`(read)` route groups and the same-origin `/api/[...path]` proxy stay untouched.
- Browser authentication stays backend-owned; the locale is a preference, not a secret.
- A third locale must be a catalog-only change.
- Catalog completeness and "no English literal in a translated component" must be enforced by a test, not by review.

## Considered Options

1. **`next-intl` v4 with no URL prefix; locale from a cookie, then `Accept-Language`, then `en`.** ⭐
2. `next-intl` with `/[locale]` routing — URL per language, canonical for public marketing sites.
3. `react-i18next` — mature, client-first.
4. A hand-rolled dictionary and context.

## Decision Outcome

Option 1.

- **Library**: `next-intl` `^4`. Server components read copy with `getTranslations`/`useTranslations` and no provider; the root layout hands the active catalog to `NextIntlClientProvider` for client components. Message keys are typed from `messages/en.json` through `AppConfig`, so a key used in code and absent from `en` fails `tsc --noEmit`.
- **Routing**: none. `i18n/request.ts` picks the locale from the `learny_locale` cookie, then from `Accept-Language` (ordered by q-value then position; any `pt` or `pt-*` maps to `pt-BR`), then `en`. There is no middleware and no `/[locale]` segment. Option 2 was rejected because it moves every route and redirect and puts the proxy catch-all under a dynamic segment, for a product that is a signed-in app with a single public page.
- **Catalogs**: `frontend/messages/{en,pt-BR}.json`, ICU MessageFormat, namespaced by surface. Option 3 was rejected because server-rendered copy would need a client provider, the criterion this decision was held to; option 4 because it reimplements ICU plurals, formatting and typed keys.
- **The choice**: a per-user row in `user_locale_preferences` (one row per user, deleted with the account, no CHECK constraint because the supported set lives in code), written by `PUT`/`DELETE /api/me/locale` and read back as `locale` on `GET /api/auth/me`. The cookie is the render-time cache of that choice: the root layout reads only the cookie (no backend call per render), and the signed-in client reconciles the cookie from `/api/auth/me` with the backend winning. Anonymous visitors switch with the cookie alone. The cookie is client-writable, so it is trusted for rendering only and is validated against the two-value set on every read.
- **Errors**: request clients throw `ApiError {operation, status, detail}`. The learner sees catalog copy chosen by operation and status; the backend's English `detail` stays on the object for logs and is never rendered. Backend error codes were rejected as a cross-cutting contract change with no learner-visible gain this cycle. Two refinements keep the copy honest: an operation may own a status (a `401` from login means wrong credentials, not an expired session), and the chat operations keep their status-specific copy for the pre-stream guards (`403`, `404`, `409`, `422`).
- **AI output language**: the effective locale (stored choice, else `Accept-Language`, else `en`) becomes an optional `response_language` on `GenerationPort`. It is a fixed per-language note appended to the user turn; the frozen system prompts, and so the cacheable prefixes and replay snapshots, are untouched, and `en` sends nothing. The not-found sentinel stays the English whole-reply token and citations stay evidence-verbatim.
- **Legal pages** (`/terms`, `/privacy`, `/copyright`) stay English with `lang="en"` on their content until the LGPD legal pass; backend-sent emails and quiz/card generation prompts stay English and are a recorded follow-up.

### Catalog completeness and the hard-coded-string sensor

Two tests keep the catalogs true. The parity test fails when a key exists in one catalog and not the other, or when a message's ICU argument names differ. The hard-coded-string test parses every `.tsx` under `app/`, `components/` and `hooks/` with the TypeScript compiler API and fails on a JSX text node or user-facing attribute literal (`aria-label`, `title`, `placeholder`, `alt`) holding English-looking words, and on a copy-bearing string literal (letters and whitespace — a sentence, not an operation key) passed to `new Error(`, `new ApiError(` or any other `…Error` constructor in `app/lib`. A documented allowlist covers brand and keyboard tokens, the operator-only eval page and the legal pages; a ratchet list of not-yet-migrated files shrinks to empty as the surfaces migrate and fails on a stale entry.

#### Limits

The sensor is a practical heuristic, not a proof. It cannot see: strings assembled in JavaScript expressions (`cond ? "Save" : "Saved"`), template literals, English words inside `t()` arguments, copy in non-`.tsx` modules other than the `app/lib` error constructors, text rendered by third-party components, or strings that happen to look like code. It does not judge translation quality or tone, and a key that exists in both catalogs with an untranslated value passes parity. A manual walk of each surface in pt-BR remains part of review.

### Consequences

- Good: Portuguese learners get the whole product in pt-BR from the first request; adding a locale is one catalog file and one `LOCALES` entry; existing routes, redirects and the proxy are unchanged.
- Good: server copy needs no provider; keys are type-checked; drift is a failing test.
- Bad: the root layout reads `cookies()` and `headers()`, so every page, including the landing, renders per request instead of statically. The pages were already per-request in practice (auth-driven, a `force-dynamic` proxy).
- Bad: the full catalog for the active locale ships to the client provider (tens of KB).
- Bad: a first paint on a new device can show the negotiated locale before the stored one applies (one refresh).
- Bad: informative English `detail` text from the backend (for example password rules) no longer reaches the learner; backend error codes are the follow-up if that proves costly.
- Watch: a third locale needs a translator, the parity test, and a new `response_language` note constant only if answers should follow it.
