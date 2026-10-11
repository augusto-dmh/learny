# pt-br-interface verification

**Verdict**: PASS
**Profile**: standard
**Diff range**: c0dd725..60d8103 (fix range 7cd370f..60d8103)
**Round**: 2 - scoped (batch 1 of 4 scope)
**Verifier**: independent sub-agent (author != verifier)

Scope: batch 1 = slices S1, S2, S3, S10 = checks C1-C27 and C42-C49 (AC 1-25, AC 39-44). C50 is informational: its test exists on this branch and was re-run, but it is not counted against the batch. Out of batch scope, not failures: C28-C41 (S4-S9 surface migration) and C51-C61 (S11 port wiring, S12 golden book).

Round 2 covers the fix diff `7cd370f..60d8103` plus every round-1 verdict that was not PASS. The fix diff touches `frontend/tests/i18n-config.test.ts`, `frontend/tests/errors.test.ts`, `checks.md` and `plan.md`. It changes no production source. All six round-1 gaps are closed (see "Round-1 gaps"). Every batch proof ran again in full at 60d8103: one vitest invocation and one pytest invocation.

## Binding sources

Renumbering note (after this report): the interface-language ADR was verified as `0032-ui-internationalization.md` and landed as `0034-ui-internationalization.md` when rebasing onto `main`, where 0032 and 0033 were already taken. The content is unchanged; references below use the new number.

Carried from 7cd370f. The fix did not touch the interface, so step 1 has nothing new to compare. Profile `standard` has no step 1 anyway. ADR-0034 is the binding decision record.

| Source | Opened | Contradiction | Uncovered |
| --- | --- | --- | --- |
| `docs/adr/0034-ui-internationalization.md` | yes - read in full at 7cd370f (carried from 7cd370f) | none | - |

The round-1 route-name note is resolved, verified at 60d8103. Plan `Choice path`, `Surface`, Landing door 5, AC 15, AC 18, `Assumptions`, `Interface`, and checks C14, C20, the coverage row and the Swept row now all say `GET /api/auth/me`. That matches ADR-0034 and `backend/app/infrastructure/web/auth.py:301`.

## Checks

The proofs were verified at 60d8103.

- **Frontend**: one invocation, `npx vitest run --reporter=verbose` over 12 files: `i18n-config`, `i18n-layout`, `i18n-typed-keys`, `prod-image`, `account-locale`, `use-locale-sync`, `locale-switcher`, `errors.test.ts`, `errors.test.tsx`, `error-display`, `i18n-parity` and `i18n-hardcoded`. Exit 0. 12 files and 57 tests passed, up from 55 because two C23 rows were added. Each named test appears individually in the output as passed.
- **Backend**: one invocation, `uv run pytest -v tests/test_web_locale.py tests/test_locale_preference_repository.py tests/test_locale.py`. Exit 0, 36 passed, and each test appears individually.
- **Build**: `npm run build` exit 0 at 60d8103, 18 routes.

Citation status:

- **Refreshed at 60d8103**: the files the fix touched (`i18n-config.test.ts` for C1-C5 and C8, `errors.test.ts` for C23 and C27), plus C46, whose wording changed.
- **Carried from 7cd370f**: every other citation. Those files are byte-identical in `7cd370f..60d8103`, so their line numbers have not moved.

| Check | Claim | Proof run | Evidence | Result |
| --- | --- | --- | --- | --- |
| C1 | locales exactly `en`, `pt-BR`, fallback `en` | vitest `supports exactly en and pt-BR` passed (verified at 60d8103) | `frontend/tests/i18n-config.test.ts:71` - `expect([...LOCALES]).toEqual(["en", "pt-BR"])`; `:72` `expect(DEFAULT_LOCALE).toBe("en")` | PASS |
| C2 | supported cookie beats Accept-Language | vitest `cookie beats Accept-Language` passed (verified at 60d8103) | pure rule `frontend/tests/i18n-config.test.ts:88` - `resolveLocale({ cookie: "en", acceptLanguage: "pt-BR,pt;q=0.9" })).toBe("en")`; through the real `i18n/request.ts` factory (`next/headers` stubbed at `:19-33`): `:93` `english.locale).toBe("en")`, `:94` `english.messages.common.loading).toBe("Loading…")`, `:96-97` `pt-BR` / `"Carregando…"`, `:99` no cookie -> `"pt-BR"`, `:100` neither -> `"en"` | PASS |
| C3 | pt/pt-* before en by q then position -> pt-BR; `en,pt` stays en | vitest `negotiates pt-BR from Accept-Language by q-value then position` passed (verified at 60d8103) | `frontend/tests/i18n-config.test.ts:83` - `expect(negotiateLocale(header), String(header)).toBe(expected)` over the `NEGOTIATION_VECTORS` table, which holds all 6 named vectors and matches the reworded C3 | PASS |
| C4 | unsupported cookie ignored | vitest `ignores an unsupported cookie` passed (verified at 60d8103) | `frontend/tests/i18n-config.test.ts:105-106` - `resolveLocale({ cookie, acceptLanguage: "pt-BR" })).toBe("pt-BR")` / `"en-US"` -> `"en"` for `fr`, `pt`, `PT-BR`, `""`, `undefined` and `null`; through the request config, `:110` `renderRequest("fr", "en-US")).locale).toBe("en")`, `:111` `("fr","pt-BR")` -> `"pt-BR"`, `:112` `("PT-BR","en")` -> `"en"` | PASS |
| C5 | absent, malformed or unsupported-only -> en | vitest `falls back to en` passed (verified at 60d8103) | `frontend/tests/i18n-config.test.ts:116-119` - `resolveLocale({})).toBe("en")`, and `;;;`, `pt;q=abc` and `fr,de` each `.toBe("en")` | PASS |
| C6 | `<html lang>` follows locale | vitest passed (verified at 60d8103) | `frontend/tests/i18n-layout.test.tsx:28,30` - `props.lang).toBe("en")` / `.toBe("pt-BR")` (citation carried from 7cd370f) | PASS |
| C7 | key missing from en fails tsc | vitest passed (verified at 60d8103) | `frontend/tests/i18n-typed-keys.test.ts:50,52` - `missing.ok).toBe(false)`, output `toContain("thisKeyIsNotInTheCatalog")` (citation carried from 7cd370f) | PASS |
| C8 | catalog files == LOCALES; load by name, no per-locale branch | vitest `catalog files match LOCALES` passed (verified at 60d8103) | `frontend/tests/i18n-config.test.ts:127` - `files).toEqual([...LOCALES].sort())`; `:132` `` toContain("`../messages/${locale}.json`") ``; `:134` `not.toContain(`"${locale}"`)` | PASS |
| C9 | app assembles with next-intl plugin | `npm run build` exit 0 at 60d8103; vitest `prod-image.test.ts` 4/4 passed (verified at 60d8103) | `frontend/next.config.ts:13-15` - `createNextIntlPlugin()` / `withNextIntl(nextConfig)` (unchanged since 7cd370f); `frontend/tests/prod-image.test.ts:15` - `toMatch(/output:\s*["']standalone["']/)` | PASS |
| C10 | PUT 200 `{locale}`, persists, re-PUT replaces leaving one row | pytest `test_put_stores_and_replaces_the_choice` PASSED (verified at 60d8103) | `backend/tests/test_web_locale.py:42-43` - `status_code == 200`, `json() == {"locale": "pt-BR"}`; `:48,51` replaced; `backend/tests/test_locale_preference_repository.py:38` `count == 1` (citations carried from 7cd370f) | PASS |
| C11 | unsupported -> 422, stores nothing | pytest PASSED (verified at 60d8103) | `backend/tests/test_web_locale.py:62` - `refused.status_code == 422`; `:65` prior `row.locale == "pt-BR"` (citations carried from 7cd370f) | PASS |
| C12 | 401 without session, 403 without CSRF, nothing stored | pytest PASSED (verified at 60d8103) | `backend/tests/test_web_locale.py:72-73` `== 401`; `:77-78` `== 403`; `:80` `get_by_user(...) is None` (citations carried from 7cd370f) | PASS |
| C13 | DELETE 204, clears, 204 again | pytest PASSED (verified at 60d8103) | `backend/tests/test_web_locale.py:90` `first.status_code == 204`; `:91` `locale is None`; `:94` `second.status_code == 204` (citations carried from 7cd370f) | PASS |
| C14 | `GET /api/auth/me` locale en / pt-BR / null unset / null unsupported | pytest `test_me_reports_the_stored_locale` PASSED (verified at 60d8103) | `backend/tests/test_web_locale.py:103` `is None`; `:106` `== "en"`; `:108` `== "pt-BR"`; `:112` `is None` after stored `"fr"` (citations carried from 7cd370f). The claim now names `/api/auth/me`, which matches the route the test calls | PASS |
| C15 | per-learner isolation | pytest PASSED (verified at 60d8103) | `backend/tests/test_web_locale.py:133` `survivor.locale == "pt-BR"`; `:134` `get_by_user(second) is None` (citations carried from 7cd370f) | PASS |
| C16 | deleting user deletes locale | pytest PASSED (verified at 60d8103) | `backend/tests/test_locale_preference_repository.py:71` `get_by_user(user_id) is None`; `:76` `remaining == 0` (citations carried from 7cd370f) | PASS |
| C17 | Account PUT with CSRF, cookie only after 200, then refresh | vitest passed (verified at 60d8103) | `frontend/tests/account-locale.test.tsx:94-95` - cookie null and no refresh while the PUT is in flight; `:110` CSRF `"csrf-xyz"`; `:112` cookie `"pt-BR"`; `:113` refresh x1 (citations carried from 7cd370f) | PASS |
| C18 | Automatic -> DELETE, clear cookie, refresh | vitest passed (verified at 60d8103) | `frontend/tests/account-locale.test.tsx:133-136` - `del[0]).toBe("/api/me/locale")`, CSRF, `readLocaleCookie()).toBeNull()`, refresh x1 (citations carried from 7cd370f) | PASS |
| C19 | failed save keeps locale, localized error | vitest passed (verified at 60d8103) | `frontend/tests/account-locale.test.tsx:159-160` - cookie stays `"en"`, no refresh; `:162` alert `textContent).toBe(expected)` in en and pt-BR; `:163` detail absent (citations carried from 7cd370f) | PASS |
| C20 | reconcile from `/api/auth/me` | vitest passed (verified at 60d8103) | `frontend/tests/use-locale-sync.test.tsx:55-58` rewrite and `toHaveBeenCalledTimes(1)`; `:72-73`, `:85-86` and `:92-93` `not.toHaveBeenCalled()` (citations carried from 7cd370f) | PASS |
| C21 | anon switcher cookie shape, no fetch, refresh | vitest passed (verified at 60d8103) | `frontend/tests/locale-switcher.test.tsx:65` - `writes).toEqual(["learny_locale=pt-BR; Path=/; Max-Age=31536000; SameSite=Lax"])`; `:67` refresh x1; `:68` `fetchSpy).not.toHaveBeenCalled()` (citations carried from 7cd370f) | PASS |
| C22 | refresh only, never reload or assign | vitest passed (verified at 60d8103) | `frontend/tests/locale-switcher.test.tsx:106-109` - `reload`, `assign` and `replace` not called, `hrefWrites).toBe(0)`; `:124` static scan (citations carried from 7cd370f) | PASS |
| C23 | every client throws ApiError {operation, status, detail} | vitest `every client throws an ApiError with operation status and detail` passed x15, one per client row incl. `'locale (save)'` and `'locale (reset)'` (verified at 60d8103) | `frontend/tests/errors.test.ts:105` `toBeInstanceOf(ApiError)`, `:107` `operation).toBe(operation)`, `:108` `status).toBe(400)`, `:109` `detail).toBe(DETAIL)`, over `CLIENTS` `:69-96`, now including `:94` `putLocale` -> `"localeSave"` and `:95` `deleteLocale` -> `"localeReset"` | PASS |
| C24 | 401, 429, 5xx -> shared status copy | vitest passed (verified at 60d8103) | `frontend/tests/errors.test.tsx:57` - `toBe(catalog.status[statusClass])`; `:58` not the operation copy (citations carried from 7cd370f) | PASS |
| C25 | 400/404/409/422 -> operation copy | vitest passed (verified at 60d8103) | `frontend/tests/errors.test.tsx:68-70` - `toBe(catalog.operation.notesSave)` (citations carried from 7cd370f) | PASS |
| C26 | pt-BR 500 English detail never on screen | vitest passed (verified at 60d8103) | `frontend/tests/error-display.test.tsx:60` - `toBe(ptBR.errors.status.server)`; `:61` `not.toContain(DETAIL)` (citations carried from 7cd370f) | PASS |
| C27 | legacy typed errors keep kind and status | vitest `legacy typed errors keep their kind and status` passed (verified at 60d8103) | `frontend/tests/errors.test.ts:159` `StreamRequestError).status).toBe(401)`; `:169,173,175` NoteError kinds; `:182` `AiProfileRequestError).status).toBe(422)`; `:192` CardError; `:201` ConversationRequestError `404`; `:206` TutorCardError `409` | PASS |
| C42 | missing key named with locale, both directions | vitest passed (verified at 60d8103) | `frontend/tests/i18n-parity.test.ts:171-172` - `"home.only_en: missing from pt-BR"`, `"home.only_pt: missing from en"` (citations carried from 7cd370f) | PASS |
| C43 | mismatched ICU args named | vitest passed (verified at 60d8103) | `frontend/tests/i18n-parity.test.ts:186` `toMatch(/^k: ICU arguments differ/)`; `:192-193` plural; `:199` select `toHaveLength(1)` (citations carried from 7cd370f; the select case still does not assert the key name - minor, not a gap) | PASS |
| C44 | shipped catalogs in parity | vitest passed (verified at 60d8103) | `frontend/tests/i18n-parity.test.ts:219` - `parityProblems(catalogs)).toEqual([])` (citation carried from 7cd370f) | PASS |
| C45 | JSX text and attribute literals flagged | vitest passed (verified at 60d8103) | `frontend/tests/i18n-hardcoded.test.ts:252-257` - `toEqual([... 4 file:line findings])` (citations carried from 7cd370f) | PASS |
| C46 | copy-bearing literal (letters and whitespace) in any `new …Error(` in app/lib flagged; a camelCase operation key passes | vitest `flags English error literals in lib files` passed (verified at 60d8103) | `frontend/tests/i18n-hardcoded.test.ts:269-272` - `toEqual(['app/lib/sources.ts:1 new Error("Could not load your sources.")', 'app/lib/sources.ts:3 new TutorCardError("Could not save this card.")'])`. Line 2 of the fixture, `new ApiError("sourcesList", ...)`, is absent from the expected list, which proves the operation key passes. The rule is at `:183`: `LETTERS.test(value) && /\s/.test(value.trim())` on `/Error$/` constructors. The reworded claim now matches the rule as built | PASS |
| C47 | clean pending file fails, named | vitest passed (verified at 60d8103) | `frontend/tests/i18n-hardcoded.test.ts:277-278` - `expect(stale, ...).toEqual([])` (citation carried from 7cd370f) | PASS |
| C48 | tree clean outside allowlist and pending | vitest passed (verified at 60d8103) | `frontend/tests/i18n-hardcoded.test.ts:288` - `expect(unexpected, ...).toEqual([])` (citation carried from 7cd370f) | PASS |
| C49 | Limits section in test header and ADR | vitest passed (verified at 60d8103) | `frontend/tests/i18n-hardcoded.test.ts:294,297` - `toMatch(/#+ Limits/)` (citations carried from 7cd370f) | PASS |
| C50 | backend locale rules (informational, outside batch count) | pytest `test_negotiation_vectors` (16 params) and `test_effective_locale_precedence` (7 params) PASSED (verified at 60d8103) | `backend/tests/test_locale.py:48` `negotiate_locale(header) == expected`; `:64` `effective_locale(stored, header) == expected` (citations carried from 7cd370f) | PASS |

## Coverage

Rows the fix touched were recomputed at 60d8103: request clients, legacy typed errors, `GET /api/auth/me` values and startup configuration. All other rows are carried from 7cd370f, because the code that holds their authority did not change in `7cd370f..60d8103`.

| Set (size) | Recomputed from | Member -> proof | Unproven |
| --- | --- | --- | --- |
| supported locales (2) | `frontend/i18n/config.ts:12` `LOCALES` (carried from 7cd370f) | `en`, `pt-BR` C1 `i18n-config.test.ts:71` | - |
| Accept-Language vectors (9) | plan AC 3, AC 5 and claims C3, C5 (carried from 7cd370f) | 6 C3 vectors `i18n-config.test.ts:83`; malformed, unsupported-only and absent C5 `:116-119` | - |
| PUT /api/me/locale statuses (4) | `backend/app/infrastructure/web/locale.py:48-62` (carried from 7cd370f) | 200 `test_web_locale.py:42` · 401 `:72` · 403 `:77` · 422 `:62` | - |
| DELETE /api/me/locale statuses (3) | `backend/app/infrastructure/web/locale.py:65-76` (carried from 7cd370f) | 204 `:90,94` · 401 `:73` · 403 `:78` | - |
| GET /api/auth/me `locale` values (4) | `backend/app/infrastructure/web/dependencies.py` `get_locale_choice`; the checks row is now named `/api/auth/me` (verified at 60d8103) | en `test_web_locale.py:106` · pt-BR `:108` · unset null `:103` · unsupported null `:112` | - |
| request-error classes (status classes + operation fallback + own-status + chat guards) | `frontend/app/lib/errors.ts:112-147` (carried from 7cd370f) | C24 `errors.test.tsx:57`; C25 `:70`; authLogin 401 and chat guards in the same file | - |
| request clients (14) | `frontend/app/lib/*.ts` that call `fetch` and throw on non-OK: auth, sources, ingestion, sections, ai-profiles, quiz, study, reading, notes, conversations, streaming, cards, tutor-card, locale (2 operations). The checks row now says 14 (verified at 60d8103) | 14 clients, 15 rows: C23 `errors.test.ts:105-109` over `CLIENTS` `:69-96`; locale save `:94` and locale reset `:95` | - |
| legacy typed errors (6) | `StreamRequestError`, `NoteError`, `AiProfileRequestError`, `CardError`, `ConversationRequestError`, `TutorCardError`. The checks row now says 6 (verified at 60d8103) | C27 `errors.test.ts:159,169,182,192,201,206` | - |
| sensor rules (5) | `frontend/tests/i18n-hardcoded.test.ts:150-192`, `frontend/tests/i18n-parity.test.ts:140-163` (carried from 7cd370f; C46 re-read at 60d8103) | C42 `:171`; C43 `:186-199`; C45 `:252`; C46 `:269`; C47 `:278` (plus C48 `:288`) | - |
| startup configuration (2 assemblies) | read directly: `frontend/next.config.ts:13-15` (build exit 0 at 60d8103); `frontend/vitest.config.ts` setupFiles -> `tests/setup-intl.ts` (carried from 7cd370f) | production build C9; `frontend/i18n/request.ts:12-21`, which feeds the production assembly, now runs in the test, which calls its factory with `next/headers` stubbed (`i18n-config.test.ts:19-46`) and asserts the locale and the loaded catalog (C2, C4) | - |
| migrated surfaces in pt-BR (11) | checks row (carried from 7cd370f) | in batch: Account C19 `account-locale.test.tsx:162`. The other 10 members are out of batch scope | - |

Level note (verified at 60d8103): the request-config test stubs `getRequestConfig` as identity (`i18n-config.test.ts:34-35`). It therefore exercises Learny's factory body, meaning the cookie and header reads, the negotiation and the catalog import, but not next-intl's own wrapping. The production build (C9) assembles that wrapping. This is adequate for AC 2 and AC 4.

Ratchet consistency (C47/C48) is carried from 7cd370f. No pending-list entry or source file changed. The swept rows that cite existing constraints (C10 upsert on the PK, C16 `ondelete="CASCADE"`, C20 failure leaves the cookie alone) are also carried from 7cd370f, unchanged.

## Test policy rows

Carried from 7cd370f. `checks.md` carries no `Test policy` section, so this step has nothing to judge.

## Faults injected

Verified at 60d8103. All faults were isolated in a `git worktree add --detach` scratch at HEAD under the session scratchpad, with `frontend/node_modules` symlinked in. Each fault was reverted with `git checkout -- .` before the next. Real-tree `git status --porcelain` matched the baseline both after the scratch was removed and after the build. The scratch is gone from `git worktree list`.

Round 2 re-injected faults on the surfaces the fix covers: the request-config cookie and header paths, and the locale client operations.

| Mutation | Location | Killed |
| --- | --- | --- |
| F4 (re-injected; survived in round 1) - request config drops the cookie (`cookie: undefined`) | `frontend/i18n/request.ts:15` | yes - C2 `cookie beats Accept-Language` failed (verified at 60d8103) |
| F6 - request config trusts the raw cookie (`store.get(LOCALE_COOKIE)?.value \|\| resolveLocale(...)`) | `frontend/i18n/request.ts:14` | yes - C4 `ignores an unsupported cookie` failed (verified at 60d8103) |
| F7 - request config ignores `Accept-Language` (`acceptLanguage: null`) | `frontend/i18n/request.ts:16` | yes - C2 and C4 failed (verified at 60d8103) |
| F8 - `putLocale` reports the wrong operation (`localeSave` -> `localeReset`) | `frontend/app/lib/locale.ts:32` | yes - C23 `('locale (save)')` failed (verified at 60d8103) |
| F9 - `deleteLocale` swallows a non-OK response (returns instead of throwing) | `frontend/app/lib/locale.ts:48-50` | yes - C23 `('locale (reset)')` failed (verified at 60d8103) |
| F1 - negotiation ignores q-value | `frontend/i18n/config.ts:46` | yes - C3 failed (carried from 7cd370f) |
| F2 - status 500 dropped from the server class | `frontend/app/lib/errors.ts:115` | yes - C24 failed (carried from 7cd370f) |
| F3 - Account writes the cookie before the PUT confirms | `frontend/app/components/AccountPanel.tsx:167` | yes - C17 failed (carried from 7cd370f) |
| F5 - unsupported stored locale returned instead of null | `backend/app/infrastructure/web/dependencies.py:851` | yes - C14 failed (carried from 7cd370f) |

Observation, not a gap: F4 alone leaves C4's request-level assertions green, because each of them would come out the same with the cookie dropped. C2 is the proof that kills it. Each fault is still killed by at least one proof.

## Gate

Verified at 60d8103.

| Gate | Result |
| --- | --- |
| `make lint` | exit 0. ruff "All checks passed!", 326 files formatted, `tsc --noEmit` clean, architecture boundaries clean |
| `make test-frontend` | exit 0. 88 files and 975 tests passed, 0 failed |
| batch backend proofs | 36 passed, 0 failed. `make test-backend` was not run in full, which is outside the batch brief |
| `cd frontend && npm run build` | exit 0, 18 routes |

## Round-1 gaps

| # | Round-1 gap | Status at 60d8103 |
| --- | --- | --- |
| 1 | F4 survived: `i18n/request.ts` untested | closed. The request factory now runs in C2 and C4, and F4, F6 and F7 are all killed |
| 2 | `locale` client missing from C23 | closed. `CLIENTS` rows at `errors.test.ts:94-95`, and F8 and F9 are killed |
| 3 | C46 overstated the sensor | closed. C46 and AC 42 are reworded to "copy-bearing literal ... any `new …Error(`", and the test proves a camelCase key passes |
| 4 | `GET /api/me` vs `/api/auth/me` | closed. Plan and checks aligned throughout |
| 5 | coverage-row miscounts (12 clients, 3 legacy errors) | closed. Rows now read 14 and 6, with members listed |
| 6 | uncommitted plan/checks edits | closed. Committed in 60d8103, and only `verification.md` and `docker-compose.override.yml` are uncommitted |

## Ranked gaps

None in batch scope.
