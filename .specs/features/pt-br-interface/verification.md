# pt-br-interface verification

**Verdict**: PASS
**Profile**: standard
**Diff range**: 8d568be..845ecc1 (the whole feature, batches 1-4; batch 4 = b888243..845ecc1, 2 commits: 4da8c99 S11, 845ecc1 S12)
**Round**: 1 - full (batch 4 of 4, every check C1-C61)
**Verifier**: independent sub-agent (author != verifier)

Scope: this is the final round. It covers all 61 checks in `checks.md`, not only batch 4's C50-C61. Every proof ran again at 845ecc1. Every citation was re-read at 845ecc1 with `rg -n`/`grep -n`.

The range also contains 290975b, a PR-review fix merged after the batch-3 verification. It changed `reader-panel.tsx`, `review-screen.tsx` and `app/lib/quiz.ts`, and no Verifier had read it. This round puts it under fault injection (G1, G2).

The batch-3 report and the batches before it are kept unchanged under `## Earlier batches`.

## Binding sources

| Source | Opened | Contradiction | Uncovered |
| --- | --- | --- | --- |
| `docs/adr/0034-ui-internationalization.md` ("AI output language", line 38; "Watch", line 57) | yes - re-read at 845ecc1 | none. The ADR fixes three things. Precedence is stored, else `Accept-Language`, else `en`: `backend/app/infrastructure/web/dependencies.py:976-987`. The note is fixed, per language and in the user turn: `backend/app/infrastructure/answering/prompts.py:64-78`, `anthropic.py:581-583`, `:615`, `openai_compat.py:125-127`. `en` sends nothing: `domain/locale.py` `response_language_for`. The sentinel stays English and whole-reply | - |
| `plan.md` `## Assumptions` rows marked "(batch 4)" (6 rows) | yes - read in the working tree (they are uncommitted, see V4-F6) | none. "Response-language note" matches `prompts.py:64-78`. "Cookie-only learner" matches `get_response_language`, which reads no cookie. "Proof files for C54/C56": both files exist at the frozen paths and import the `tests/infrastructure/` doubles. "Every generation caller": a grep of `backend/app` for `.generate(` and `.generate_stream(` call sites finds only `conversations.py:997` and `:1017`, plus the router's own forwarding. "Portuguese golden book" matches `backend/tests/golden_corpus_pt.py:1-29`. "Discriminating C60/C61" matches `test_golden_retrieval.py:79-86` and `test_golden_citations.py:135` | - |

Profile `standard` does not run step 1's design enumeration. Batch 4 changes no screen (`git diff --stat b888243..HEAD -- frontend` is empty).

## Checks

How the proofs ran at 845ecc1:

- **Backend**: one invocation, `LEARNY_REQUIRE_DB=1 uv run pytest -v -p no:randomly` (the whole suite, no `-n`). It ran 3300 passed, 2 failed and 11 skipped. Each named backend proof appears individually as PASSED: C10-C16 one each; C50 `test_negotiation_vectors` x26 and `test_effective_locale_precedence` x7; C51 x24; C52 x4; C53 x4; C54 x4; C55 x2; C56 local x2 and routing x4; C57 x8; C58 x1; C59 x1; C60 x3; C61 x3.
- **The 2 failures are not from the feature.** They are `test_deploy_topology.py::test_dev_merge_publishes_the_app_ports` and `::test_dev_merge_still_publishes_todays_infra_ports`, and the owner's uncommitted `docker-compose.override.yml` causes them (`${LEARNY_DB_HOST_PORT:-5432}` host ports). In a scratch worktree of clean 845ecc1 the same file ran 29 passed.
- **The 11 skips** are the live and paid tiers that skip without keys or flags. No feature proof was skipped.
- **Frontend**: one invocation, `npx vitest run --maxWorkers=2 --minWorkers=1 --reporter=verbose` (the whole suite). Exit 0: 91 files and 1043 tests passed. Each frozen `-t` name appears with a check mark: C1-C8, C17-C27 and C38-C49 one each, C23 x15. The `renders in pt-BR` counts are C28 1+1, C29 2+2, C32 5+2, C35 6+1+1 (`read-page`), C37 7+4+2 (`teach-panel`), C39 6 plus the heatmap test, and C40 3+3. C30's four files ran whole: 6+10+9+6. The `review-screen` flake did not show up.
- **C9**: `npm run build` ran alone, last. Exit 0, "Compiled successfully". `prod-image.test.ts` passed 4/4.
- **The new proof files are new code.** Every batch-4 proof is a test added in b888243..845ecc1. `test_answering_anthropic.py` (+162/-0) and `test_answering_local.py` (+22/-0) only gain tests, so every earlier English request-shape assertion in them still runs unedited.

| Check | Claim | Proof run | Evidence | Result |
| --- | --- | --- | --- | --- |
| C1 | locales exactly `en`, `pt-BR`, fallback `en` | vitest passed at 845ecc1 | `frontend/tests/i18n-config.test.ts:58` `expect([...LOCALES]).toEqual(["en", "pt-BR"])`; `:59` `DEFAULT_LOCALE).toBe("en")` | PASS |
| C2 | supported cookie beats `Accept-Language` | vitest passed | `frontend/tests/i18n-config.test.ts:76` `resolveLocale({ cookie: "en", acceptLanguage: "pt-BR,pt;q=0.9" })).toBe("en")`; `:81` `english.locale).toBe("en")` through the real request config | PASS |
| C3 | pt/pt-* before en by q then position -> pt-BR; `en,pt` stays en | vitest passed | `frontend/tests/i18n-config.test.ts:71` `negotiateLocale(header), String(header)).toBe(expected)` over the shared table `backend/tests/locale_negotiation_vectors.json:4-9` (`pt`, `pt-PT`, `pt;q=0.9,en;q=0.8`, `en,pt`->`en`, `en;q=0.5,pt;q=0.9`) | PASS |
| C4 | unsupported cookie ignored | vitest passed | `frontend/tests/i18n-config.test.ts:93` `resolveLocale({ cookie, acceptLanguage: "pt-BR" }), String(cookie)).toBe("pt-BR")` | PASS |
| C5 | absent, malformed, unsupported-only -> en | vitest passed | `frontend/tests/i18n-config.test.ts:104` `resolveLocale({})).toBe("en")`; `:107` `"fr,de"` -> `"en"`; vectors `;;;` and `null` at `backend/tests/locale_negotiation_vectors.json:16`, `:18` | PASS |
| C6 | `<html lang>` follows the locale | vitest passed | `frontend/tests/i18n-layout.test.tsx:30` `props.lang).toBe("pt-BR")` (and `:28` `"en"`) | PASS |
| C7 | key missing from en fails tsc | vitest passed | `frontend/tests/i18n-typed-keys.test.ts:50` `missing.ok).toBe(false)` | PASS |
| C8 | catalog files == LOCALES, no per-locale branch | vitest passed | `frontend/tests/i18n-config.test.ts:115` `files).toEqual([...LOCALES].sort())`; `:122` `request).not.toContain(`"${locale}"`)` | PASS |
| C9 | app assembles with the next-intl plugin | `npm run build` exit 0 at 845ecc1; `prod-image` 4/4 | `frontend/next.config.ts:13` `createNextIntlPlugin()`; `frontend/tests/prod-image.test.ts:15` `toMatch(/output:\s*["']standalone["']/)` | PASS |
| C10 | PUT 200 `{locale}`, persists, re-PUT replaces leaving one row | pytest PASSED | `backend/tests/test_web_locale.py:43` `stored.json() == {"locale": "pt-BR"}`; `backend/tests/test_locale_preference_repository.py:38` `count == 1` | PASS |
| C11 | unsupported -> 422, stores nothing | pytest PASSED | `backend/tests/test_web_locale.py:62` `refused.status_code == 422`; `:65` the prior row is still `pt-BR` | PASS |
| C12 | 401 without session, 403 without CSRF, nothing stored | pytest PASSED | `backend/tests/test_web_locale.py:72-73` `== 401`; `:77-78` `== 403` | PASS |
| C13 | DELETE 204, clears, 204 again | pytest PASSED | `backend/tests/test_web_locale.py:94` `second.status_code == 204` | PASS |
| C14 | `/api/auth/me` locale en / pt-BR / null / null-for-unsupported | pytest PASSED | `backend/tests/test_web_locale.py:108` `["locale"] == "pt-BR"` (the `None`/`en`/unsupported asserts sit beside it in the same test) | PASS |
| C15 | per-learner isolation | pytest PASSED | `backend/tests/test_web_locale.py:133` `survivor.locale == "pt-BR"` | PASS |
| C16 | deleting the user deletes the locale | pytest PASSED | `backend/tests/test_locale_preference_repository.py:76` `remaining == 0` | PASS |
| C17 | Account PUT with CSRF, cookie after 200, then refresh | vitest passed | `frontend/tests/account-locale.test.tsx:110` CSRF `toBe("csrf-xyz")`; `:113` `refresh).toHaveBeenCalledTimes(1)` | PASS |
| C18 | Automatic -> DELETE, clear cookie, refresh | vitest passed | `frontend/tests/account-locale.test.tsx:133` `del[0]).toBe("/api/me/locale")`; `:136` refresh x1 | PASS |
| C19 | failed save keeps the locale, localized error | vitest passed | `frontend/tests/account-locale.test.tsx:162` `getByRole("alert").textContent).toBe(expected)` | PASS |
| C20 | reconcile from `/api/auth/me` | vitest passed | `frontend/tests/use-locale-sync.test.tsx:56` refresh x1; `:73`, `:86`, `:93` `not.toHaveBeenCalled()` | PASS |
| C21 | anonymous switcher cookie shape, no fetch, refresh | vitest passed | `frontend/tests/locale-switcher.test.tsx:65` `writes).toEqual(["learny_locale=pt-BR; Path=/; Max-Age=31536000; SameSite=Lax"])`; `:68` `fetchSpy).not.toHaveBeenCalled()` | PASS |
| C22 | refresh only, never reload or assign | vitest passed | `frontend/tests/locale-switcher.test.tsx:109` `hrefWrites).toBe(0)` | PASS |
| C23 | every client throws ApiError {operation, status, detail} | vitest passed x15 | `frontend/tests/errors.test.ts:105` `toBeInstanceOf(ApiError)`; `:107` `operation).toBe(operation)` | PASS |
| C24 | 401, 429, 5xx -> shared status copy | vitest passed | `frontend/tests/errors.test.tsx:57` `toBe(catalog.status[statusClass])` | PASS |
| C25 | other statuses -> operation copy | vitest passed | `frontend/tests/errors.test.tsx:70` `toBe(catalog.operation.notesSave)` | PASS |
| C26 | pt-BR 500 detail never on screen | vitest passed | `frontend/tests/error-display.test.tsx:61` `not.toContain(DETAIL)` | PASS |
| C27 | legacy typed errors keep kind and status | vitest passed | `frontend/tests/errors.test.ts:159` `StreamRequestError).status).toBe(401)`; `:182` `AiProfileRequestError).status).toBe(422)` | PASS |
| C28 | landing, login, register from the catalog (pt-BR) | vitest passed | `frontend/tests/landing.test.tsx:94` `expectNoEnglishCopy(..., "landing", "auth", "common")`; `frontend/tests/auth-screens.test.tsx:171-179`, `:191`. Reset and verify screens do not exist (plan Assumption, batch 2) | PASS |
| C29 | shell and vendored default text from the catalog (pt-BR) | vitest passed | `frontend/tests/app-shell.test.tsx:241-246` (`Sair`, `Alternar tema`, `expectNoEnglishCopy(..., "shell")`); `frontend/tests/vendored-primitives.test.tsx:94` `{ name: copy.close }` | PASS |
| C30 | en screens keep their English assertions, unedited apart from the binding | four files ran whole (31 tests) | `git diff --numstat 8d568be..845ecc1` shows 0 deleted lines in `landing.test.tsx` (+36), `auth-screens.test.tsx` (+71) and `app-shell.test.tsx` (+54); `app-sidebar.test.tsx` is unchanged. Evidence line: `frontend/tests/app-shell.test.tsx:246` | PASS |
| C31 | legal pages stay English with `lang="en"` | vitest passed | `frontend/tests/legal-pages.test.tsx:115` `getAttribute("lang")).toBe("en")` | PASS |
| C32 | Home and Library states from the catalog (pt-BR) | vitest passed (5+2) | `frontend/tests/library-screen.test.tsx:570` `toBe("com falha")`; `frontend/tests/home-screen.test.tsx:457` (the states test) | PASS |
| C33 | pt-BR 0/1/2 books and the locale date | vitest passed | `frontend/tests/library-screen.test.tsx:641` `[2, "2 livros"]`; `:660` `"Adicionado em 19 de jul. de 2026"` | PASS |
| C34 | book text unchanged (pt-BR) | vitest passed | `frontend/tests/library-screen.test.tsx:700-701` `findByText("The Art of War")`, `getByText("Dom Casmurro")` | PASS |
| C35 | reader chrome and controls from the catalog (pt-BR) | vitest passed (6+1+1) | `frontend/tests/chapter-reader.test.tsx:2239` and the five pt-BR tests after it; `frontend/tests/reading-controls.test.tsx:213` | PASS |
| C36 | chapter text and citation snippets unchanged (pt-BR) | vitest passed | `frontend/tests/chapter-reader.test.tsx:2456-2464` (carried; the file is unchanged since 736c2c3 except the new tests above it, and those were re-read at 845ecc1) | PASS |
| C37 | Chat dock surfaces from the catalog (pt-BR) | vitest passed (7+4+2) | `frontend/tests/conversation-dock.test.tsx:613` `toBe("1.234")`; `:619` tab `"Revisão1.234"` (added by 290975b, made to fail by G1); `frontend/tests/ask-panel.test.tsx:1901`, `:1939`, `:2004`, `:2052` | PASS |
| C38 | sentinel never shown or translated | vitest passed | `frontend/tests/cited-answer.test.tsx:375` `JSON.stringify(catalog)).not.toContain(NOT_FOUND_SENTINEL)`; `:383` `textContent).not.toContain(NOT_FOUND_SENTINEL)` | PASS |
| C39 | review surfaces and heatmap from the catalog and locale (pt-BR) | vitest passed (6 + heatmap) | `frontend/tests/review-screen.test.tsx:1583` `findByText("Carregando…")`; `:1524` `grade-interval-1` stays `"~3w"` (unknown bucket, 290975b, made to fail by G2); `:1590` the heatmap test | PASS |
| C40 | notes surfaces from the catalog (pt-BR) | vitest passed (3+3) | `frontend/tests/notes-screen.test.tsx:377`, `:432`, `:485`; `frontend/tests/note-detail-screen.test.tsx:306`, `:383`, `:416` | PASS |
| C41 | user note text unchanged (pt-BR) | vitest passed | `frontend/tests/note-detail-screen.test.tsx:501` `body()).toContain("Ada wrote the first algorithm")`; `:503` | PASS |
| C42 | missing key named with locale, both directions | vitest passed | `frontend/tests/i18n-parity.test.ts:171` `"home.only_en: missing from pt-BR"`; `:172` `"home.only_pt: missing from en"` | PASS |
| C43 | mismatched ICU arguments named | vitest passed | `frontend/tests/i18n-parity.test.ts:186` `toMatch(/^k: ICU arguments differ/)` | PASS |
| C44 | shipped catalogs in parity | vitest passed | `frontend/tests/i18n-parity.test.ts:219` `parityProblems(catalogs)).toEqual([])` | PASS |
| C45 | JSX text and attribute literals flagged | vitest passed | `frontend/tests/i18n-hardcoded.test.ts:216-221` `toEqual([... aria-label, Hello there, placeholder, title ...])` | PASS |
| C46 | copy-bearing literal in any `new …Error(` flagged | vitest passed | `frontend/tests/i18n-hardcoded.test.ts:234` `'app/lib/sources.ts:1 new Error("Could not load your sources.")'` | PASS |
| C47 | a clean pending file fails; the list is empty | vitest passed | `frontend/tests/i18n-hardcoded.test.ts:247` the synthetic stale entry; `:251` `stale ...).toEqual([])` | PASS |
| C48 | source tree clean | vitest passed | `frontend/tests/i18n-hardcoded.test.ts:263` `unexpected ...).toEqual([])` | PASS |
| C49 | Limits documented in the test header and the ADR | vitest passed | `frontend/tests/i18n-hardcoded.test.ts:269` `header).toMatch(/## Limits/)`; `:272` `adr).toMatch(/#+ Limits/)`; `docs/adr/0034-ui-internationalization.md:45` | PASS |
| C50 | backend locale rules | pytest PASSED (26 + 7) | `backend/tests/test_locale.py:44` `negotiate_locale(header) == expected`; `:60` `effective_locale(stored, header) == expected`; `:64` `response_language_for("en") is None`; `:65` `response_language_for("pt-BR") == "pt-BR"` | PASS |
| C51 | the port receives pt-BR / None over JSON and stream, Ask and tutor | pytest PASSED x24 (2 modes x 2 routes x 6 cases) | `backend/tests/test_web_conversations_language.py:141` `port.response_languages == [expected]`; `:139-140` the route's own path was used; cases at `:62-67` (stored pt-BR, stored pt-BR over an en header, unset with a pt header, stored en over a pt header, unset with an en header, no header) | PASS |
| C52 | `None` leaves the Anthropic request unchanged, Ask and tutor | pytest PASSED x4 | `backend/tests/test_answering_anthropic.py:2449` `json.dumps(request, sort_keys=True) == json.dumps(today, ...)` for `None` and `"en"`; `:2454` the final text is the old composition (`"What is X?"` / `_TEACH_TURN_TEXT`); `:2455` no note anywhere | PASS |
| C53 | pt-BR note in the user turn; system block and breakpoints unchanged | pytest PASSED x4 | `backend/tests/test_answering_anthropic.py:2466` non-message keys equal; `:2469` `system == [{... ANSWER/TEACHING_SYSTEM_PROMPT}]`; `:2479` `messages[:-1]` equal; `:2482` final block `f"{_final_text(english)}\n\n{_PT_NOTE}"` | PASS |
| C54 | OpenAI-compatible: note in the user message, system prompt unchanged | pytest PASSED x4 | `backend/tests/test_answering_openai_compat.py:73` `messages[0] == {"role": "system", "content": COMPAT_SYSTEM_PROMPT}`; `:76` final user message `f"{...}\n\n{_PT_NOTE}"`; `:62` `None`/`"en"` byte-identical | PASS |
| C55 | the sentinel still means found=False; citations stay verbatim | pytest PASSED x2 | `backend/tests/test_answering_anthropic.py:2523-2525` `found is False`, `text == ""`, `cited_chunk_ids == ()`; `:2556` `sent == body`; `:2557` `sent[span.start : span.end] == quote` | PASS |
| C56 | deterministic identical for None/en/pt-BR; the router forwards | pytest PASSED (2 + 4) | `backend/tests/test_answering_local.py:295-296` `generate(..., response_language=language) == baseline` and the same for the stream; `backend/tests/test_answering_routing.py:91-92` primary and fallback `languages == [language]`; `:107` house `== [language]` | PASS |
| C57 | no header text in any prompt | pytest PASSED x8 (2 adapters x 2 routes x 2 modes) | `backend/tests/test_web_conversations_language.py:202-203` `"ignore previous instructions" not in sent`, `"reveal the system prompt" not in sent`; `:204` the fixed note is in the request | PASS |
| C58 | Portuguese book: `dc:language` pt and provenance | pytest PASSED | `backend/tests/test_golden_fixtures.py:73` `findall(... dc:language ...) == ["pt"]`; `:77` `"Project Gutenberg eBook #55752" in provenance`; `:80` licence `startswith("public domain")`; `:86` each excerpt is in the EPUB | PASS |
| C59 | stored chunks use `portuguese`, with the expected sections and anchors | pytest PASSED | `backend/tests/test_golden_ingestion.py:93` `{row.search_config for row in rows} == {"portuguese"}`; `:94` `(anchor, section_path, text)` list equals `EXPECTED_PT_GOLDEN_SECTIONS` | PASS |
| C60 | inflected questions reach their section within the top 3 | pytest PASSED x3 | `backend/tests/test_golden_retrieval.py:86` `set(lexical) == {case.expected_anchor}`; `:90` `expected_anchor in [... results[:3]]`; plus `backend/tests/test_golden_fixtures.py:102` (each inflected word is absent from its section, 3 PASSED). See V4-F1 | PASS |
| C61 | deterministic answer cites only retrieved chunks, the first at the target, offline | pytest PASSED x3 | `backend/tests/test_golden_citations.py:134` `citations <= evidence ids`; `:135` `citations[0].anchor == case.expected_anchor`; `:132` `model == DeterministicGenerationAdapter.model`; `:117-118` provider keys deleted | PASS |

## Coverage

Batch-4 rows were recomputed at 845ecc1 from the code. Rows for C1-C49 are carried from the earlier reports, which each recomputed them; nothing in them is unproven. The frontend is byte-identical between b888243 and 845ecc1. 290975b, the one frontend change after the batch-3 report, touches the sets in the last row, which was recomputed.

| Set (size) | Recomputed from | Member -> proof | Unproven |
| --- | --- | --- | --- |
| generation implementers of the kwarg (4 production + 1 fake) | a grep of `backend/app` for `def generate(` and `def generate_stream`: `anthropic.py:625`, `:666`; `openai_compat.py:376`, `:411`; `local.py:89`, `:104`; `routing.py:247`, `:292`; plus `tests/fakes.py:802`, `:829` | Anthropic C53, C52 · OpenAI-compatible C54 · deterministic C56 (`test_answering_local.py:295`) · routing C56 (`test_answering_routing.py:91`) · fake C51 (`test_web_conversations_language.py:141`). The merged tree with origin/main adds no implementer (V4-F7) | - |
| port callers (2) | `backend/app/application/conversations.py:997` `generation.generate(`, `:1017` `generation.generate_stream(`, both passing `response_language` | buffered C51 json cases · streamed C51 stream cases | - |
| routes x mode (4) | `backend/app/infrastructure/web/conversations.py:492`, `:530` (`Depends(get_response_language)`) x {answer, teach} | Ask JSON · Ask stream · tutor JSON · tutor stream: C51 and C57 are parametrized over both (`test_web_conversations_language.py:105-107`, `:169-173`) | - |
| effective-locale sources (stored supported, stored unsupported, header pt, header en, none) | `backend/app/domain/locale.py` `effective_locale` and `backend/app/infrastructure/web/dependencies.py:966-972` (`get_locale_choice` maps unsupported to `None` at `:971`) | C50 `test_locale.py:60` x7 · C51 `:62-67` x6 per route and mode · stored unsupported -> unset: C14 `test_web_locale.py:112` plus C50 | - |
| response-language values at the adapters (None, en, pt-BR, unknown) | `backend/app/infrastructure/answering/prompts.py:74-78` | None and en C52 `:2449` and C54 `:62` · pt-BR C53, C54 · unknown: `test_answering_anthropic.py:2497` and `test_answering_openai_compat.py:88` (both PASSED, not frozen proofs) · deterministic over all three C56 | - |
| adapter path x mode (Anthropic and compat: buffered and stream x answer and teach = 8) | the adapters' `generate`/`generate_stream` and the `mode == MODE_TEACH` branch | C52, C53 and C54 are each parametrized over `stream` x `mode` (4 PASSED each) | - |
| router serving paths (primary, fail-over, house) x buffered and stream | `backend/app/infrastructure/answering/routing.py:268-285`, `:323-340` | `test_answering_routing.py:91-92` (primary and fail-over), `:107` (house); 4 params | - |
| golden Portuguese cases (3 questions x retrieval, citation, stemmer need) | `backend/tests/golden_expected.py` `PORTUGUESE_CASES` | C60 x3 · C61 x3 · `test_golden_fixtures.py:102` x3 | - |
| post-review fix 290975b members (dock tab count, interval buckets 9, unknown bucket) | `frontend/app/components/reader-panel.tsx:184`, `frontend/app/lib/quiz.ts:132-142`, `frontend/app/components/review-screen.tsx:791-793` | tab count `conversation-dock.test.tsx:619` (G1) · all nine buckets across the pt-BR cards at `review-screen.test.tsx:1344-1358` · unknown bucket `:1524` (G2) | - |
| C1-C49 sets (supported locales, negotiation vectors, PUT/DELETE statuses, `/api/auth/me` values, error classes, 14 clients, 6 legacy errors, migrated surfaces, untranslated surfaces, sensor rules, startup assemblies) | carried from the batch 1-3 reports below; C9's build assembly re-proven by `npm run build` at 845ecc1 | as in `checks.md` `## Coverage` | - |

## Test policy rows

`checks.md` has no `Test policy` section, so there are no rows to judge.

## Swept rows re-read

- **C10 concurrency** (upsert on the primary key): `test_locale_preference_repository.py:38` `count == 1`.
- **C55 dependency failure** (a sentinel reply still maps to not-found with a response language): `test_answering_anthropic.py:2523`.
- **C20 dependency failure** (`/api/auth/me` unreachable leaves the locale alone): `use-locale-sync.test.tsx:93`.
- The `n/a` rows are policy the owner approved.

## Faults injected

Backend faults ran through a script. Each one replaced one exact occurrence and asserted the occurrence count. It then ran only the named proofs (`LEARNY_REQUIRE_DB=1`, no `-n`). It restored the file with `git checkout --` and compared `git status --porcelain` with the recorded baseline (` M plan.md`, ` M docker-compose.override.yml`); every run matched. Frontend faults ran the same way, over one test file with `--maxWorkers=2 --minWorkers=1`.

This deviates from verify.md, which asks for a scratch worktree. The orchestrator's brief allows in-place mutation, and the earlier batches did the same.

Eight faults is over verify.md's cap of five, for two reasons:

- **F6** probes pre-existing retrieval code that C60 and C61 claim to guard.
- **G1 and G2** cover 290975b, a merged fix that no Verifier had made to fail.

| Mutation | Location | Killed |
| --- | --- | --- |
| F1 dependency passes the raw `Accept-Language` through when nothing is stored (header text as the response language) | `backend/app/infrastructure/web/dependencies.py:987` | yes - C51 (8 unset-header cases) and C57 (all 8 cases: the note is gone) |
| F2 Anthropic Ask: note moved from the user turn into the system block (the rejected door-7 alternative) | `backend/app/infrastructure/answering/anthropic.py:615-616` | yes - C53 `answer-buffered`, `answer-stream` |
| F3 OpenAI-compatible: note also appended to the system prompt | `backend/app/infrastructure/answering/openai_compat.py:143` | yes - C54, all 4 |
| F4 router stream path drops `response_language` from its kwargs | `backend/app/infrastructure/answering/routing.py:323` | yes - C56 routing `stream-pt-BR`, `stream-None` |
| F5 ingestion maps `pt` to `simple` instead of `portuguese` | `backend/app/application/text_search.py:23` | yes - C59; C60 all 3; C61 `cap2`, `cap3` |
| F6 production hybrid query's lexical arm uses `'simple'` instead of the stored config (pre-existing code) | `backend/app/infrastructure/db/retrieval.py:81-87` | yes - C61 `cap2`, `cap3`; C60 passed all 3 cases under it (V4-F1) |
| G1 dock Review tab badge rendered raw instead of locale-formatted (290975b) | `frontend/app/components/reader-panel.tsx:184` | yes - `conversation-dock > Review tab, due and nothing due: renders in pt-BR` |
| G2 review grade interval rendered as the raw bucket, never the catalog label (290975b) | `frontend/app/components/review-screen.tsx:791-793` | yes - `review-screen > card, grades, intervals and summary: renders in pt-BR` and `unknown backend tokens show as sent: renders in pt-BR` |

C52, C55 and C58 were not made to fail this round, because the cap had been reached. Each passes on assertions that pin literal values (`:2454`, `:2523-2525`, `:73`) rather than values derived from the code under test.

## Gate

- `make lint` - exit 0. That is backend `ruff check` "All checks passed!", `ruff format --check` "345 files already formatted", frontend `tsc --noEmit` clean, `check_commits.py origin/main..HEAD` "2 commit(s) ... OK", and `check_boundaries.py` "architecture boundaries clean".
- Backend: `LEARNY_REQUIRE_DB=1 uv run pytest -v` - 3300 passed, 2 failed, 11 skipped. The 2 failures come from the owner's uncommitted `docker-compose.override.yml`, not the feature; `tests/test_deploy_topology.py` passes 29/29 on a clean 845ecc1 worktree.
- Frontend: `npx vitest run --maxWorkers=2 --minWorkers=1` - 91 files, 1043 passed, 0 failed.
- `npm run build` - exit 0, run alone and last. `.next` was already present, and `git status --porcelain` was unchanged afterwards.
- Tree after verification: ` M .specs/features/pt-br-interface/plan.md` and ` M docker-compose.override.yml` (both were there before this round), plus this report.

## Findings

- **V4-F1 - low - C60 cannot catch a regression in the production lexical arm.** `backend/tests/test_golden_retrieval.py:79-86` re-implements the lexical match in test SQL. It does not exercise `SqlAlchemyRetrievalRepository`'s lexical arm. The only assertion on production retrieval, `:90` "within the top 3", cannot fail on a three-chapter book.
  - Under F6 (the production query stems with `simple`), all three C60 cases passed. C61 killed the fault (`cap2`, `cap3`), so the feature's proofs as a whole do catch it.
  - Suggested fix: assert `results[0].anchor == case.expected_anchor` on the production `retrieve`, or drive the repository's lexical arm rather than a copy of its SQL.
- **V4-F2 - low - the note's wording is never asserted.** `RESPONSE_LANGUAGE_NOTES["pt-BR"]` (`backend/app/infrastructure/answering/prompts.py:65-71`) asks for Brazilian Portuguese, keeps quotations verbatim and restates the sentinel. Every test compares the request against the constant itself.
  - So a note that asked for another language, or dropped the sentinel restatement the plan relies on, passes every test.
  - Suggested fix: one unit test that the note contains `SENTINEL` and "Brazilian Portuguese".
- **V4-F3 - info - the selection-Explain origin with pt-BR has no test.** It goes through the same `_generate`/`_generate_stream` call (`backend/app/application/conversations.py:645-652`, `:997-1006`). Only the `GenerationPort` instance differs, so it is not counted as unproven.
- **V4-F4 - info - only one tutor chip is exercised.** The chip test (`backend/tests/test_web_conversations_language.py:223-237`) sends `TUTOR_DONT_KNOW_MESSAGE` and asserts the hint escalates. `TUTOR_JUST_EXPLAIN_MESSAGE` reaches the same unmodified message path, because the note is adapter-side, but it is not exercised.
- **V4-F5 - cosmetic - checks.md's header miscounts.** It says "59 checks in 12 slices", but it defines 61 (C1-C61). The file is frozen; this is noted, not fixed.
- **V4-F6 - process - the batch-4 plan rows are uncommitted, and one line now renders wrongly.** The six "(batch 4)" `## Assumptions` rows in `plan.md` are uncommitted, and the edit removed the blank line between the table and `**Open questions:**` (`.specs/features/pt-br-interface/plan.md:272`). GitHub-flavoured Markdown now renders that line as a table row. Suggested fix: restore the blank line and commit the rows with the batch.
- **V4-F7 - process - the branch is behind origin/main.** It is 21 commits behind (PR #80, BYOK key routes, bb63126).
  - `git merge-tree --write-tree origin/main HEAD` merges with no conflict, and the merged tree has no new `GenerationPort` implementer.
  - This round verified 845ecc1, not the merge result. The PR's CI on its merge ref is the check for that.
- **Carried, non-blocking:**
  - B3-R3-F1 (the raw dock tab badge) is now fixed by 290975b and proven by G1.
  - B3-R2-F1 (the raw review position `{index + 1}/{queue.length}`) is still open.

## Deferred to owner

- Confirm CI on the PR, including the merge with origin/main (V4-F7).
- A browser and screen-reader walk of the pt-BR surfaces, and one real-provider pt-BR answer. That needs a funded key, which the eval workflow lacks by owner decision.
- Follow-up candidates recorded in the plan: reading the `learny_locale` cookie for answer language, and a locale on the tutor-card accept route.

## Earlier batches

The batch-3 report (round 3, PASS) is kept unchanged below. It carries batch 2 and batch 1 under its own `## Earlier batches`. Batch 3's failed rounds 1 and 2 stay in `verification-batch3-rounds.md`.

# pt-br-interface verification

**Verdict**: PASS
**Profile**: standard
**Diff range**: origin/main..c12ddeb (batch 3: c737b7a..207f75d; round-2 fixes 207f75d..88beef1; round-3 fix range 88beef1..c12ddeb, 2 commits: aa0abca tests only, c12ddeb the round-2 report)
**Round**: 3 - scoped (batch 3 of 4 scope)
**Verifier**: independent sub-agent (author != verifier)

Scope: batch 3 = checks C37-C41, plus the ratchet checks C44, C47 and C48. Round 3 covers two things:

- **The fix diff `88beef1..c12ddeb`.** It changes three test files, `conversation-dock`, `review-screen` and `ask-panel`, and no component source.
- **Every round-2 verdict that was not PASS.** That is the two surviving faults: N3, the dock due count's locale formatting, and N6, the review page's Suspense fallback.

Both are now killed, and so are three adjacent faults on the new assertion surfaces. The round-2 report is kept unchanged under `## Earlier batches`, with round 1, batch 2 and batch 1 nested inside it.

## Binding sources

Carried from 88beef1. The fix touches neither the ADR nor `plan.md`, nor any component, so step 1 has nothing new to compare.

| Source | Opened | Contradiction | Uncovered |
| --- | --- | --- | --- |
| `docs/adr/0034-ui-internationalization.md` | yes (carried from 88beef1) | none | - |
| `plan.md` `## Assumptions` rows marked "(batch 3)" | yes (carried from 88beef1; `git diff 88beef1..c12ddeb -- .specs/features/pt-br-interface/plan.md` is empty) | none | - |

## Checks

How the proofs ran at c12ddeb:

- **One invocation**, `npx vitest run --maxWorkers=2 --minWorkers=1 --reporter=verbose`, over the three changed files: `conversation-dock`, `review-screen` and `ask-panel`. Exit 0: 3 files and 111 tests passed.
- **Every claim-carrying test in these files appears by name**: `ask-panel` 7 `renders in pt-BR`, `conversation-dock` 4, and `review-screen` 5 plus `heatmap uses locale names`. The `review-screen` flake did not show up.
- **The `stubDock` helper change** (`Math.min(due, 3)` queue items) is covered by `conversation-dock` running whole.
- `npx tsc --noEmit -p .` - exit 0.

Citation status:

- **Refreshed at c12ddeb**: C37 (the dock Review tab member) and C39 (the review-page fallback member).
- **Carried from 88beef1**: every other row. Their files are untouched, or the new lines sit below the cited ones (`conversation-dock` adds from `:604`, `review-screen` from `:1549` apart from the mock at `:30-40`). Their proofs passed again in this run where they live in the three files above. C38, C40, C41, C44, C47 and C48 have files the fix does not touch, so they carry their 88beef1 run.

| Check | Claim | Proof run | Evidence | Result |
| --- | --- | --- | --- | --- |
| C37 | Ask and Tutor panels, answer phases, not-found answer, failed turns, conversation list, include-notes toggle, save-to-note and the dock Notes/Review tabs render from the catalog (pt-BR) | `ask-panel` 7 and `conversation-dock` 4 `renders in pt-BR` passed (verified at c12ddeb); `teach-panel` 2 carried from 88beef1 | New: `frontend/tests/conversation-dock.test.tsx:613` `expect((await screen.findByTestId("due-count")).textContent).toBe("1.234")`; `:615` `"cartões deste livro para revisar"` (the 1234 caption takes the `other` branch). The round-2 evidence stands (carried from 88beef1) | PASS |
| C38 | sentinel never shown or translated | carried from 88beef1 (`cited-answer` untouched) | `frontend/tests/cited-answer.test.tsx:368`, `:375`, `:383` (carried) | PASS |
| C39 | review sessions, grades, intervals, empty deck, done for today, quiz progress and the heatmap render from the catalog and locale rules (pt-BR) | `review-screen` 5 `renders in pt-BR` plus `heatmap uses locale names` passed (verified at c12ddeb) | New: `frontend/tests/review-screen.test.tsx:1552` `nav.suspend = true` (the mock at `:36` throws a pending promise, so the page's Suspense boundary shows its fallback); `:1555` `expect(await screen.findByText("Carregando…")).toBeTruthy()`. The rest is carried from 88beef1 (`:1385`, `:1392`, `:1519`, `:1539`, `:1584`, `:1611`, `:1614`) | PASS |
| C40 | notes list, detail, capture popover, card suggestions and anchor badges render from the catalog (pt-BR) | carried from 88beef1 (files untouched) | `frontend/tests/notes-screen.test.tsx:394`, `:404` (carried) | PASS |
| C41 | user-authored note text unchanged (pt-BR) | carried from 88beef1 | `frontend/tests/note-detail-screen.test.tsx:494`, `:496`, `:503` (carried) | PASS |
| C44 | shipped catalogs in parity | carried from 88beef1 (no catalog change) | `frontend/tests/i18n-parity.test.ts:218-219` (carried) | PASS |
| C47 | stale pending entry fails; the list is empty | carried from 88beef1 | `frontend/tests/i18n-hardcoded.test.ts:247`, `:253`, `:80` (carried) | PASS |
| C48 | source tree clean | carried from 88beef1 (no component change) | `frontend/tests/i18n-hardcoded.test.ts:263` (carried) | PASS |

## Coverage

These two rows were recomputed at c12ddeb, because the round-2 report left them `Unproven`. The other rows are carried from 88beef1 with nothing unproven.

| Set (size) | Recomputed from | Member -> proof | Unproven |
| --- | --- | --- | --- |
| locale-formatted numbers added in round 2 (3) | `frontend/app/components/study-heatmap.tsx:505`, `frontend/app/components/dock-review-panel.tsx:95` | study reviews total `review-screen.test.tsx:1611` · study pages total (same formatter instance) · dock due count `conversation-dock.test.tsx:613` | - |
| review page states (title, fallback) | `frontend/app/(app)/review/page.tsx` | title `review-screen.test.tsx:1539` · fallback `:1555` | - |

## Test policy rows

`checks.md` has no `Test policy` section, so there are no rows to judge.

## Faults injected

Each fault was applied in place, one at a time, by a script that replaces one exact text occurrence, runs only the target file with the frozen `-t "renders in pt-BR"` filter (`--maxWorkers=2 --minWorkers=1`), then restores the file with `git checkout --`. Afterwards `git status --porcelain` showed only ` M docker-compose.override.yml`.

| Mutation | Location | Killed |
| --- | --- | --- |
| N3 dock due count -> raw `{total}` (round-2 survivor) | `frontend/app/components/dock-review-panel.tsx:95` | yes - `conversation-dock > Review tab, due and nothing due: renders in pt-BR` (`1234` vs `1.234`) |
| N3b dock due count formatted with `"en-US"` instead of the locale | `frontend/app/components/dock-review-panel.tsx:95` | yes - same test (`1,234` vs `1.234`) |
| N3c pt-BR `dueCaption` `other` branch collapsed to the singular | `frontend/messages/pt-BR.json:218` | yes - same test (`cartão deste livro` for 1234) |
| N6 review page fallback -> `{"Loading…"}` (round-2 survivor) | `frontend/app/(app)/review/page.tsx:44` | yes - `review-screen > page title and loading fallback: renders in pt-BR` |
| N6b review page fallback removed (`fallback={null}`) | `frontend/app/(app)/review/page.tsx:44` | yes - same test |

## Gate

- The three changed test files - exit 0: 111 passed, 0 failed.
- `npx tsc --noEmit -p .` - exit 0.
- Full frontend suite: not re-run this round. The fix changes only three test files. Their one shared-helper change is local to `conversation-dock`, and that file ran whole. The last full run, at 88beef1, was 91 files and 1042 passed.
- Backend: not run (no backend change).
- Tree after verification: `git status --porcelain` shows ` M docker-compose.override.yml` (the owner's file, untouched) and this report.

## Findings

- **B3-R3-F1 - non-blocking - one raw number left on the same screen.** The dock's Review tab badge (`TabCount`, `frontend/app/components/reader-panel.tsx:183`) still renders `{value}` raw. In the N3c run the panel read `Revisão1234` in the tab next to `1.234` in the panel body. This file belongs to batch 2's reader surface, and number grouping is not part of any catalog check, but it is the same fix as `dock-review-panel.tsx:95`.
- **B3-R2-F1 (carried) - non-blocking.** The review position `{index + 1}/{queue.length}` is still raw.
- **The round-2 test-hygiene finding is closed.** `IntersectionObserver` is now restored (`frontend/tests/ask-panel.test.tsx:2189`, `:2275`).
- **Note on the N6 proof.** The suspending mock throws a promise that never resolves (`frontend/tests/review-screen.test.tsx:36`). It is harmless here because `cleanup` unmounts the tree, and `nav.suspend` is reset in a `finally` block.

## Deferred to owner

- `npm run build` and the commit and architecture parts of `make lint`. CI runs them.
- A browser and screen-reader walk of the batch-3 surfaces in pt-BR.
- `tests/review-screen.test.tsx`'s known flake under memory pressure. It did not reproduce in this round.

## Earlier batches

Batch 3's failed rounds 1 and 2 are kept unchanged in `verification-batch3-rounds.md`, so this file holds one verdict per batch. Batch 2 (its report carries batch 1 under its own `## Earlier batches`), moved unchanged:

# pt-br-interface verification

**Verdict**: PASS
**Profile**: standard
**Diff range**: origin/main..736c2c3 (batch 2: 8c11ad3..c04b2d5; round-2 fix range 860b949..736c2c3, 3 commits: a795693, 946afda, 736c2c3)
**Round**: 2 - scoped (batch 2 of 4 scope)
**Verifier**: independent sub-agent (author != verifier)

Scope: batch 2 = slices S4, S5 and S6 = checks C28-C36 (AC 26-33). Checks outside C28-C36 are out of this batch's scope. They are not failures. The batch-1 report is kept unchanged under `## Earlier batches`.

Round 2 covers two things:

- **The fix diff `860b949..736c2c3`.** It changes `frontend/messages/pt-BR.json` (wording only), five test files (`library-screen`, `chapter-reader`, `read-page`, `app-shell`, `home-screen`) and `plan.md`. It changes no component source.
- **Every round-1 verdict that was not PASS.** That is C32, C35, the three surviving faults F-13, F-14 and F-15, and findings F3 and F4.

All three round-1 survivors are now killed. Five new faults on the new assertion surfaces are killed too. Every batch-2 proof ran again in full at 736c2c3.

## Binding sources

Carried from c04b2d5, re-checked against the fix. The fix touches no component source, so step 1 has nothing new to compare on the interface.

| Source | Opened | Contradiction | Uncovered |
| --- | --- | --- | --- |
| `docs/adr/0034-ui-internationalization.md` | yes - read in full at c04b2d5 (carried from c04b2d5) | none | - |
| `plan.md` `## Assumptions` rows marked "(batch 2)" | yes - re-read at 736c2c3, including the extended "Counts and dates" row and the new "Batch-2 review of the Portuguese" row | none. The F5 rejection holds: no next-intl `timeZone` is configured anywhere (`grep -n timeZone frontend/i18n frontend/app/layout.tsx frontend/tests/setup-intl.ts` finds nothing), and the test formatter fails on any error (`frontend/tests/setup-intl.ts:40,45` `onError: failOnError`). So `useFormatter().dateTime` would report the environment fallback | - |

## Checks

Proofs verified at 736c2c3:

- **Whole files**: one invocation, `npx vitest run --reporter=verbose` over 13 files: `landing`, `auth-screens`, `app-shell`, `app-sidebar`, `vendored-primitives`, `legal-pages`, `library-screen`, `home-screen`, `chapter-reader`, `reading-controls`, `read-page`, `i18n-hardcoded` and `i18n-parity`. Exit 0. 13 files and 181 tests passed.
- **The frozen filter**: a second invocation, `-t "renders in pt-BR"` over `app-shell`, `library-screen`, `home-screen`, `chapter-reader`, `reading-controls` and `read-page`. 17 passed and 125 were skipped. It selects every claim-carrying pt-BR test, each listed individually: `not-found notice: renders in pt-BR`, `empty, done and error states: renders in pt-BR`, `empty and failed list states: renders in pt-BR`, `signed-out, loading, sample and processing: renders in pt-BR`, `every quiz-deck state renders in pt-BR`, `in-flight button labels: renders in pt-BR`, and the reader's `margin rail`, `signed-out, not-found and failed states`, `previous chapter and return chip`, `stale-capture prompt` and `mobile dock sheet` tests, plus `read page loading fallback > renders in pt-BR`. F3 is closed.

Citation status:

- **Refreshed at 736c2c3**: C32, C35 and C36. C36's lines moved +90 because new tests were inserted above it.
- **Carried from c04b2d5**: C28-C31, C33 and C34. Their files are untouched, or changed only by in-place 1:1 line edits (a test rename, `falhou` -> `com falha`, `Tutor` -> `Ensinar`), so the cited line numbers have not moved.

| Check | Claim | Proof run | Evidence | Result |
| --- | --- | --- | --- | --- |
| C28 | landing, login and register render from the catalog with no English UI copy (pt-BR) | `landing` and `auth-screens` `renders in pt-BR` passed (verified at 736c2c3) | `frontend/tests/landing.test.tsx:84`, `:88`, `:91`, `:94` `expectNoEnglishCopy`; `frontend/tests/auth-screens.test.tsx:171-191` (citations carried from c04b2d5). Password reset and email verification do not exist (plan Assumption, batch 2) | PASS |
| C29 | sidebar, header, theme toggle, not-found notice and vendored dialog/sheet/sidebar/spinner text come from the catalog (pt-BR) | `app-shell` `renders in pt-BR` and `not-found notice: renders in pt-BR`, and `vendored-primitives` `in pt-BR` passed (verified at 736c2c3) | `frontend/tests/app-shell.test.tsx:230-246`, `:254`/`:260` (the not-found test is now selected by the frozen filter, `:249`); `frontend/tests/vendored-primitives.test.tsx:94-142` (citations carried from c04b2d5) | PASS |
| C30 | `en` landing, auth and shell keep their existing English assertions, unedited apart from the intl binding | the four files ran whole and passed (verified at 736c2c3) | `git diff --numstat origin/main..736c2c3` shows 0 deleted lines in `landing.test.tsx` (+31), `auth-screens.test.tsx` (+54) and `app-shell.test.tsx` (+54). The round-2 rename touched only a test added in batch 2. `app-sidebar.test.tsx` is untouched. `frontend/tests/app-sidebar.test.tsx:59-62` is unchanged | PASS |
| C31 | `/terms`, `/privacy` and `/copyright` stay English with `lang="en"` on the content wrapper under pt-BR | `legal-pages` `stay English under pt-BR` passed (verified at 736c2c3) | `frontend/tests/legal-pages.test.tsx:114-115` (citations carried from c04b2d5) | PASS |
| C32 | Home, Library, ingestion status and every empty, loading and error state render from the catalog (pt-BR) | the six `home-screen`/`library-screen` tests matching `renders in pt-BR` passed (verified at 736c2c3) | Home: `frontend/tests/home-screen.test.tsx:438-490` (carried; only the title at `:457` was renamed). Library: `frontend/tests/library-screen.test.tsx:558`, `:568-570` (`com falha`), `:576`, `:580`, `:602`, `:618`, `:631`. New: `:732` `Você não está conectado.`; `:745` `Carregando seus livros…`; `:752` sample ready; `:753` `processando`; `:762` `Gerando baralho…`; `:779` noSection; `:790` noneSurvived `(3 descartados)`; `:805` `1 descartado durante a geração.`; `:807` `2 itens salvos. 1 seção falhou.`; `:844` generate failure; `:864`/`:881`/`:900`/`:925` `Enviando…`/`Iniciando…`/`Reiniciando…`/`Reprocessando…`; `:918` the re-ingest warning | PASS |
| C33 | pt-BR 0/1/2 books -> `0 livros`/`1 livro`/`2 livros`, and a date in the locale's format | `library-screen` `pt-BR plurals and dates` passed (verified at 736c2c3) | `frontend/tests/library-screen.test.tsx:639-641`, `:657` `toBe(text)`, `:660` `Adicionado em 19 de jul. de 2026`, `:680` `1 book` (citations carried from c04b2d5) | PASS |
| C34 | book titles, authors and section titles unchanged (pt-BR) | `library-screen` `book text is never translated` passed (verified at 736c2c3) | `frontend/tests/library-screen.test.tsx:700-701`; `frontend/tests/home-screen.test.tsx:446-447` (carried). No batch-2 surface renders an author | PASS |
| C35 | reader chrome, TOC, reading controls, margin rail, progress text, aria labels and keyboard help render from the catalog (pt-BR) | the six `chapter-reader` tests and the `reading-controls` test matching `renders in pt-BR` passed; `read-page` `renders in pt-BR` passed (verified at 736c2c3) | `frontend/tests/chapter-reader.test.tsx:2250-2269` chrome, TOC, tabs and panel; `:2297-2299` margin rail; `:2313`/`:2327`/`:2340` not-found, `Você não está conectado.` and error. New: `:2366` `Voltar para onde você estava`; `:2368` `← Capítulo anterior`; `:2396` the stale-capture prompt via the `h` shortcut; `:2423` dialog `Painel de notas`; `:2426` the sheet description; `:2428` `Fechar`. `frontend/tests/reading-controls.test.tsx:232-251` (carried). `frontend/tests/read-page.test.tsx:98` `Carregando…`. Keyboard help does not exist | PASS |
| C36 | chapter text and citation snippets unchanged (pt-BR) | `chapter-reader` `book text is never translated` passed (verified at 736c2c3) | `frontend/tests/chapter-reader.test.tsx:2456-2457` section prose; `:2458-2459` headings `Beginnings`/`Mechanism`; `:2460` `Chapter One`; `:2464` `toEqual(["Ada Lovelace wrote the first algorithm"])` (refreshed, +90) | PASS |

## Coverage

Recomputed at 736c2c3 for the rows the fix touched (the C32 Library states and the C35 reader members). The other rows are carried from c04b2d5: their authority, the component source, did not change.

| Set (size) | Recomputed from | Member -> proof | Unproven |
| --- | --- | --- | --- |
| migrated surfaces in pt-BR, batch-2 members (7) | checks.md coverage row and the diff (carried from c04b2d5) | landing C28 · auth C28 · shell C29 · vendored primitives C29 · Home C32 · Library C32 · reader C35 | - |
| C32 Library states: empty, loading and error (16) | `frontend/app/components/library-screen.tsx` (verified at 736c2c3) | auth loading `:558` · signed-out `:732` · loading sources `:745` · sample ready `:752` · empty `:618` · list error `:631` · upload validation `:602` · ingestion failed `:576` · statuses ready/uploaded/failed/processing `:568-570`, `:753` · quiz generating `:762` · quiz failed job (backend error under `lang="en"`, with the Portuguese generate button) in `every quiz-deck state renders in pt-BR` · noSection `:779` · noneSurvived `:790` · discardFootnote `:805` · partial `:807` · generate failure `:844` · pending labels `:864`/`:881`/`:900`/`:925` | - |
| C32 Home states (6) | `frontend/app/components/home-screen.tsx` (carried from c04b2d5) | `home-screen.test.tsx:446-490`. The loading states are text-free skeletons (`frontend/app/components/home-screen.tsx:169`, `:231`) | - |
| C33 count and date vectors (4) | the claim (carried from c04b2d5) | `library-screen.test.tsx:639-641`, `:660` | - |
| C35 reader chrome and states (17) | the batch-2 reader components (verified at 736c2c3) | toc toggle · dock toggle · settings trigger · progress · TOC label · chapter nav · next link `chapter-reader.test.tsx:2250-2269` · previous link `:2368` · tabs · close panel · panel label · margin rail `:2297-2299` · controls popover `reading-controls.test.tsx:232-251` · return chip `:2366` · stale capture `:2396` · mobile dock sheet `:2423-2428` · not-found, signed-out and error `:2313-2340` · read-page fallback `read-page.test.tsx:98` | - |
| untranslated surfaces, batch-2 members (4) | checks.md coverage row (carried from c04b2d5) | legal pages C31 · book titles C34 · section/chapter text C34, C36 · rail citation snippet C36 | - |

Note: the read-page fallback is proven in `frontend/tests/read-page.test.tsx`. C35's proof lines name only `chapter-reader` and `reading-controls`. The member is proven, but a run of C35's literal commands alone would not reach it. The plan records this, and `checks.md` is frozen.

## Test policy rows

`checks.md` has no `Test policy` section, so there are no rows to judge (carried from c04b2d5).

## Faults injected

Round-2 faults were applied in a scratch sparse worktree at 736c2c3 (`frontend/` and `docs/adr/`, `node_modules` symlinked). `docs/adr` was included this time so that `i18n-hardcoded > documents its limits` runs in its real state. The run order was F-13 to F-15 together, then F-19 to F-23 together. Each failing test is the one its fault targets. Afterwards I removed the worktree, and the real tree's `git status --porcelain` matched the baseline (only ` M docker-compose.override.yml`). F-1 to F-12 and F-16 to F-18 are carried from c04b2d5: their mutated source and covering tests did not change, apart from the 1:1 renames, and the full proofs re-ran green.

| Mutation | Location | Killed |
| --- | --- | --- |
| F-1 to F-12, F-16 to F-18 (round 1, see the round-1 list in commit 860b949) | as recorded at c04b2d5 | yes (carried from c04b2d5) |
| F-13 quiz `noneSurvived` -> English template literal (round-1 survivor) | `frontend/app/components/library-screen.tsx:263` | yes - `library-screen > every quiz-deck state renders in pt-BR` |
| F-14 `loadingSources` -> `{"Loading your sources…"}` (round-1 survivor) | `frontend/app/components/library-screen.tsx:590` | yes - `library-screen > signed-out, loading, sample and processing: renders in pt-BR` |
| F-15 return chip -> `{"Return to where you were"}` (round-1 survivor) | `frontend/app/components/chapter-reader.tsx:1115` | yes - `chapter-reader > previous chapter and return chip: renders in pt-BR` |
| F-19 `row.starting` -> `"Starting…"` in the ternary | `frontend/app/components/library-screen.tsx:673` | yes - `library-screen > in-flight button labels: renders in pt-BR` |
| F-20 stale-capture message -> English literal passed to `captureMessage` | `frontend/app/components/chapter-reader.tsx:611` | yes - `chapter-reader > stale-capture prompt: renders in pt-BR` |
| F-21 mobile sheet description -> English JS literal | `frontend/app/components/reader-panel.tsx:462` | yes - `chapter-reader > mobile dock sheet: renders in pt-BR` |
| F-22 read-page fallback -> `{"Loading…"}` | `frontend/app/(read)/sources/[id]/read/page.tsx:31` | yes - `read-page > read page loading fallback > renders in pt-BR` |
| F-23 pt-BR `quiz.partial` loses its noun (`# salvo`/`# salvos`) | `frontend/messages/pt-BR.json` `library.quiz.partial` | yes - `library-screen > every quiz-deck state renders in pt-BR` |

## Gate

- `make lint` - exit 0: ruff check passed; ruff format reports 341 files already formatted; `tsc --noEmit` clean; `check_commits` reports 8 commits in `origin/main..HEAD` OK; architecture boundaries clean.
- `make test-frontend` - two runs, each 1008 passed and 1 failed out of 1009 (90 files, 1 failed file). The failure was in `tests/review-screen.test.tsx`, and it was a different test each time: run 1 `REV-44 still reveals on Space` timed out at 5 s; run 2 `ReviewScreen session flow (E2) > grades each card` could not find the `Again` button. Neither the test file nor `frontend/app/components/review-screen.tsx` is touched by `origin/main..HEAD`. The same file run alone at 736c2c3 failed 1 of 2 times (`reveals the answer on the space bar`, 5 s timeout). At `origin/main`, in a scratch worktree, it failed 1 of 3 times, on the same `grades each card` test. So this is an existing timing flake under this machine's memory pressure (swap full), not a branch regression. CI is authoritative. See finding R2-F1.
- `LEARNY_REQUIRE_DB=1 make test-backend` - 3227 passed, 2 failed, 11 skipped. The two failures are `test_deploy_topology` `test_dev_merge_publishes_the_app_ports` and `test_dev_merge_still_publishes_todays_infra_ports`. Both come from the owner's uncommitted `docker-compose.override.yml`, so they are not findings.

## Round-1 gaps

| Round-1 finding | Status at 736c2c3 |
| --- | --- |
| F1 (blocking, C32 Library states) | closed - all 16 members proven (see Coverage); F-13 and F-14 killed |
| F2 (blocking, C35 reader members) | closed - previous link, return chip, stale capture, mobile sheet and read-page fallback proven; F-15 killed |
| F3 (selectors missed claim-carrying tests) | closed - every pt-BR test is renamed to contain `renders in pt-BR`, and the frozen filter selects 17 tests (listed above) |
| F4 (pt-BR wording) | closed - `frontend/messages/pt-BR.json` now reads `Ensinar` (library teach link), `com falha`, `refaz o processamento deste livro`, `Você não está conectado.` for all three signed-out keys, and `# item salvo`/`# itens salvos`. Each reads naturally, and the batch-1 terms are kept. No test anywhere still expects `Você saiu da conta.` (`grep -rn` over `frontend/` finds nothing) |
| F5 (date formatter) | rejected by the author with a sound reason, recorded in the plan: no `timeZone` is configured, and the test binding fails on the environment fallback. Accepted |

## Findings

- **R2-F1 - non-blocking - flaky test, not on this branch.** `frontend/tests/review-screen.test.tsx` flakes on this machine at both `origin/main` and HEAD: 5 s timeouts and a missing `Again` button under memory pressure. This is outside batch-2 scope; batch 3 migrates `review-screen.tsx`. Suggestion: when batch 3 touches the file, check the waits in `grading shortcuts` and `session flow (E2)`, using `findBy*` instead of a sync `getBy*` after grading.
- **R2-F2 - non-blocking - proof sits outside C35's named files.** C35's read-page fallback member is proven only in `frontend/tests/read-page.test.tsx`, which no C35 proof line names. The plan records why.

## Deferred to owner

- `npm run build`. Skipped for the memory budget. CI runs it.
- A browser or screenshot walk of the batch-2 surfaces in pt-BR. Skipped by brief.
- The two local `test_deploy_topology` dev-port failures, which come from the uncommitted override.
- A green full `make test-frontend` run. Locally the review-screen flake blocked it (R2-F1). CI is authoritative.

## Earlier batches


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
