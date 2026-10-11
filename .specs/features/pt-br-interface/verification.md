# pt-br-interface verification

**Verdict**: FAIL
**Profile**: standard
**Diff range**: origin/main..c04b2d5 (8c11ad3..c04b2d5, 4 commits: 9eea451, 508c0b7, 43d461c, c04b2d5)
**Round**: 1 - full (batch 2 of 4 scope)
**Verifier**: independent sub-agent (author != verifier)

Scope: batch 2 = slices S4, S5 and S6 = checks C28-C36 (AC 26-33). Checks outside C28-C36 are out of this batch's scope. They are not failures. The batch-1 report is kept unchanged under `## Earlier batches`.

Summary: every named proof ran green at c04b2d5. 15 of 18 injected faults were killed. Three faults survived, and each one survived the whole batch-2 suite plus the hard-coded-string sensor. Each puts English copy back into a state that C32 or C35 says renders from the catalog, using the sensor-blind JS-expression form. The product code is correct today, because every one of those states reads through `t()`. What fails is the proof: C32 ("every empty, loading and error state") and C35 ("reader chrome") are each proven on a sample of their members. Fixing this means adding assertions to tests. It needs no change to production code.

## Binding sources

| Source | Opened | Contradiction | Uncovered |
| --- | --- | --- | --- |
| `docs/adr/0034-ui-internationalization.md` | yes - read in full at c04b2d5 | none. The landing proof under `lang="en"`, the legal pages under `lang="en"` on `<main>`, ICU plurals and select in the catalogs, and `useTranslations` with no provider in server components all match the decision | - |
| `plan.md` `## Assumptions` rows marked "(batch 2)" (8 rows) | yes | none. The rows were judged and not relitigated. None of them contradicts AC 26-33 or ADR-0034. Two need a note. (1) "Surfaces AC 26 names that do not exist": I confirmed there are no frontend password-reset, email-verification or shortcut-help surfaces (`find app -type d \| grep -iE "reset\|verif\|forgot\|password"` finds nothing, and a grep for shortcut-help copy finds nothing). (2) "Counts and dates": the new count and added-date also show in `en` (`1 book`, `Added Jul 19, 2026`). That changes the Library's English, which AC 27 does not cover, because AC 27 is scoped to the AC 26 surfaces | - |

## Checks

Proofs were verified at c04b2d5 in one invocation: `npx vitest run --reporter=verbose` over `landing`, `auth-screens`, `app-shell`, `app-sidebar`, `vendored-primitives`, `legal-pages`, `library-screen`, `home-screen`, `chapter-reader`, `reading-controls`, `i18n-hardcoded` and `i18n-parity`. Exit 0, 12 files and 171 tests passed. Every test that a C28-C36 proof names appears individually as passed. I ran the whole files rather than the `-t` filters, because several tests that carry the claims are not matched by their check's `-t "renders in pt-BR"` filter (see finding F3).

| Check | Claim | Proof run | Evidence | Result |
| --- | --- | --- | --- | --- |
| C28 | landing, login and register render from the catalog with no English UI copy (pt-BR) | `landing` `renders in pt-BR` and `auth-screens` `renders in pt-BR` passed | `frontend/tests/landing.test.tsx:84` tagline; `:88`/`:91` `Criar conta`/`Entrar` hrefs; `:94` `expectNoEnglishCopy(..., "landing", "auth", "common")`. `frontend/tests/auth-screens.test.tsx:171` `Que bom ter você de volta ao Learny.`; `:172` form `formulário de entrada`; `:175` `Entrar`; `:179` `expectNoEnglishCopy(..., "auth")`; `:183-191` the same for register. Password reset and email verification do not exist (plan Assumption, batch 2, checked above) | PASS |
| C29 | sidebar, header, theme toggle, not-found notice and vendored dialog/sheet/sidebar/spinner text come from the catalog (pt-BR) | `app-shell` `renders in pt-BR`, `shows the not-found notice in pt-BR`, and `vendored-primitives` `in pt-BR > default text comes from the catalog` and `names the mobile sidebar sheet` passed | `frontend/tests/app-shell.test.tsx:230-231` nav `Início`/`Biblioteca` (plus `Revisão`/`Notas`); `:238` `Conta`; `:241` `Sair`; `:242` `Alternar tema`; `:244` `Alternar barra lateral`; `:246` `expectNoEnglishCopy(..., "shell")`; `:254`/`:260` both not-found sentences. `frontend/tests/vendored-primitives.test.tsx:94` two `Fechar` (dialog); `:105` sheet `Fechar`; `:109` status `Carregando`; `:121-124` toggle name, rail `aria-label` and `title`; `:141-142` mobile sheet title and description. Shortcut help does not exist | PASS |
| C30 | `en` landing, auth and shell keep their existing English assertions, unedited apart from the intl binding | the four files ran whole: landing, auth-screens, app-shell and app-sidebar all passed | `git diff --numstat origin/main..HEAD` shows 0 deleted lines in `landing.test.tsx` (+31), `auth-screens.test.tsx` (+54) and `app-shell.test.tsx` (+54); `app-sidebar.test.tsx` is untouched. The only non-test addition is the `next/navigation` mock in `auth-screens.test.tsx:19-22` (harness binding). The existing English expectations stand, for example `frontend/tests/app-sidebar.test.tsx:59-62` `Home`/`Library`/`Review`/`Notes` | PASS |
| C31 | `/terms`, `/privacy` and `/copyright` stay English with `lang="en"` on the content wrapper under pt-BR | `legal-pages` `stay English under pt-BR` passed | `frontend/tests/legal-pages.test.tsx:114` - `heading.textContent).toBe(heading)` for all three; `:115` - `getByRole("main").getAttribute("lang")).toBe("en")`. Code: `frontend/app/terms/page.tsx:16`, `privacy/page.tsx:17` and `copyright/page.tsx:20` `<main lang="en"` | PASS |
| C32 | Home, Library, ingestion status and every empty, loading and error state render from the catalog (pt-BR) | `home-screen` and `library-screen` `renders in pt-BR` passed, plus the unselected `renders the empty, done and error states in pt-BR` and `renders the empty and failed list states in pt-BR` | Home is fully proven: `frontend/tests/home-screen.test.tsx:438` `Início`; `:448` `43% lido`; `:451` `Você tem 2 cartões pendentes.`; `:470` empty state; `:472` done state; `:486`/`:488` both error states; `:454`/`:490` `expectNoEnglishCopy`. Library is partly proven: `frontend/tests/library-screen.test.tsx:558` `Carregando…`; `:568-570` statuses `pronto`/`enviado`/`falhou`; `:576` `O processamento falhou.`; `:580` counts; `:602` upload error; `:618` empty; `:631` list error; `:605` `expectNoEnglishCopy`. **No pt-BR proof** covers the Library states at `frontend/app/components/library-screen.tsx:523` (signed-out), `:590` (loading sources), `:581` (sample ready), `:143` (generating), `:243`/`:291`/`:299` and `noneSurvived` at `:263` (quiz error states), the `processing` status, or the pending labels at `:569`/`:648`/`:673`/`:696`. Faults F-13 and F-14 survived | FAIL |
| C33 | pt-BR 0/1/2 books -> `0 livros`/`1 livro`/`2 livros`, and a date in the locale's format | `library-screen` `pt-BR plurals and dates` passed | `frontend/tests/library-screen.test.tsx:639-641` vectors, asserted at `:657` `library-count).textContent).toBe(text)`; `:660` `Adicionado em 19 de jul. de 2026`; `:680-681` the `en` controls `1 book`/`Added Jul 19, 2026` | PASS |
| C34 | book titles, authors and section titles unchanged (pt-BR) | `library-screen` `book text is never translated` passed | `frontend/tests/library-screen.test.tsx:700-701` `The Art of War`/`Dom Casmurro`; section/chapter title on Home `frontend/tests/home-screen.test.tsx:446-447` `Ready Book`/`Chapter One`. Authors: no batch-2 surface renders an author (`grep -n author` over library/home/reader components finds nothing), so that member is vacuous here | PASS |
| C35 | reader chrome, TOC, reading controls, margin rail, progress text, aria labels and keyboard help render from the catalog (pt-BR) | `chapter-reader` and `reading-controls` `renders in pt-BR` passed, plus the unselected `renders the margin rail in pt-BR` and `renders the reader's signed-out and not-found states in pt-BR` | `frontend/tests/chapter-reader.test.tsx:2250-2252` the three chrome buttons; `:2254` progress `/^\d+% lido · faltam \d+ min$/`; `:2257` TOC label; `:2261` `Próximo capítulo →`; `:2264` tabs; `:2267` `Fechar painel`; `:2269` `Painel de notas`; `:2297-2299` margin rail; `:2313`/`:2327`/`:2340` not-found, signed-out and error. `frontend/tests/reading-controls.test.tsx:232-238` labels and segments; `:242` `Tamanho do texto 23`; `:247` `1,8` (decimal comma); `:251` `expectNoEnglishCopy`. **No pt-BR proof** covers the return chip at `frontend/app/components/chapter-reader.tsx:1115`, the stale-capture message at `:611`/`:658`, `← Capítulo anterior` at `frontend/app/components/toc-panel.tsx:173`, the mobile dock sheet title, description and close at `frontend/app/components/reader-panel.tsx:461-469`, or the read-page fallback at `frontend/app/(read)/sources/[id]/read/page.tsx:31`. Fault F-15 survived. Keyboard help does not exist | FAIL |
| C36 | chapter text and citation snippets unchanged (pt-BR) | `chapter-reader` `book text is never translated` passed | `frontend/tests/chapter-reader.test.tsx:2366-2367` section prose; `:2368-2369` headings `Beginnings`/`Mechanism`; `:2370` `Chapter One`; `:2374` the rail quote `toEqual(["Ada Lovelace wrote the first algorithm"])` | PASS |

## Coverage

Recomputed from the code (the authority over which states and elements exist) and, for counts and dates, from the claim's own vectors.

| Set (size) | Recomputed from | Member -> proof | Unproven |
| --- | --- | --- | --- |
| migrated surfaces in pt-BR, batch-2 members (7) | checks.md coverage row and the diff | landing C28 · auth C28 · shell C29 · vendored primitives C29 · Home C32 · Library C32 (partial, see the next row) · reader C35 (partial, see the reader row) | - |
| C32 Library states: empty, loading and error (16) | `frontend/app/components/library-screen.tsx` | auth loading `:558` · empty `:618` · list error `:631` · upload validation `:602` · ingestion failed with no message `:576` · statuses ready/uploaded/failed `:568-570` · quiz counts `:580` | signed-out `:523`; loading sources `:590` (F-14 survived); sample ready `:581`; status `processing`; quiz generating `:143`; quiz noSection `:243`; quiz noneSurvived `:263` (F-13 survived); discardFootnote `:291`; partial `:299` |
| C32 Home states (6) | `frontend/app/components/home-screen.tsx` | hero empty, hero error, due done, due error, due count and percent are all in `home-screen.test.tsx:446-490`. The loading states are text-free skeletons (`frontend/app/components/home-screen.tsx:169`, `:231`) | - |
| C33 count and date vectors (4) | the claim | 0, 1, 2 at `library-screen.test.tsx:639-641`; date at `:660` | - |
| C35 reader chrome and states (17) | the batch-2 reader components | toc toggle · dock toggle · settings trigger · progress · TOC label · chapter nav · next link · tabs · close panel · panel label · margin rail (label, heading, empty) · controls popover · not-found · signed-out · error | return chip `chapter-reader.tsx:1115` (F-15 survived); stale capture `:611`/`:658`; previous link `toc-panel.tsx:173`; mobile dock sheet `reader-panel.tsx:461-469`; read-page fallback `page.tsx:31` |
| untranslated surfaces, batch-2 members (4) | checks.md coverage row | legal pages C31 · book titles C34 · section/chapter text C34, C36 · citation snippet (rail quote) C36. The landing proof keeps `lang="en"` (`landing.test.tsx:102-104`) | - |

## Test policy rows

`checks.md` has no `Test policy` section, so there are no rows to judge. The repo's own conventions decide: component-level Vitest with jsdom, which is what every batch-2 proof uses.

## Faults injected

Each fault was applied in a scratch sparse worktree at c04b2d5 (`frontend/` only, `node_modules` symlinked). For each one I ran the narrowest covering test files. Afterwards I removed the worktree, and the real tree's `git status --porcelain` matched the baseline (only the owner's ` M docker-compose.override.yml`). F-1 to F-6 ran together, then F-7 to F-12 together, then F-16 to F-18. Each failing test is the one its fault targets, so attribution is unambiguous. In the F-13 to F-15 run, the one red test was `i18n-hardcoded > documents its limits`. It is an artifact of the sparse checkout: it reads `docs/adr/0034-...`, which the sparse checkout omits. No batch-2 test failed in that run.

| Mutation | Location | Killed |
| --- | --- | --- |
| F-1 tagline -> English JS-expression literal | `frontend/app/page.tsx:36` | yes - `landing > renders in pt-BR` |
| F-2 login description -> `{"Welcome back to Learny."}` | `frontend/app/(auth)/login/page.tsx:23` | yes - `auth-screens > renders in pt-BR` |
| F-3 nav labels from an English JS map (sensor-blind) | `frontend/app/components/shell/app-sidebar.tsx:52` | yes - `app-shell > renders in pt-BR` |
| F-4 spinner `aria-label="Loading"` | `frontend/components/ui/spinner.tsx:9` | yes - `vendored-primitives > in pt-BR > default text comes from the catalog` |
| F-5 terms `<main>` loses `lang="en"` | `frontend/app/terms/page.tsx:16` | yes - `legal-pages > stay English under pt-BR` |
| F-6 line-spacing `format.number` -> `step.toFixed(1)` | `frontend/app/components/reading-controls.tsx:131` | yes - `reading-controls > renders in pt-BR` |
| F-7 status badge renders the raw `source.status` | `frontend/app/components/library-screen.tsx:609` | yes - `library-screen > renders in pt-BR` |
| F-8 due count -> English template literal | `frontend/app/components/home-screen.tsx:239` | yes - `home-screen > renders in pt-BR` |
| F-9 pt-BR `library.count` loses its `=0` branch | `frontend/messages/pt-BR.json` `library.count` | yes - `library-screen > pt-BR plurals and dates` |
| F-10 title rendered `.toUpperCase()` | `frontend/app/components/library-screen.tsx:604` | yes - `library-screen > book text is never translated` |
| F-11 progress -> English template literal | `frontend/app/components/chapter-reader.tsx:868` | yes - `chapter-reader > renders in pt-BR` |
| F-12 rail quote wrapped in typographic quotes | `frontend/app/components/margin-rail.tsx:125` | yes - `chapter-reader > book text is never translated` |
| F-13 quiz `noneSurvived` -> English template literal | `frontend/app/components/library-screen.tsx:263` | no - survived library-screen, chapter-reader and i18n-hardcoded |
| F-14 `loadingSources` -> `{"Loading your sources…"}` | `frontend/app/components/library-screen.tsx:590` | no - survived the same three files |
| F-15 return chip -> `{"Return to where you were"}` | `frontend/app/components/chapter-reader.tsx:1115` | no - survived the same three files |
| F-16 added date formatted with `"en-US"` | `frontend/app/components/library-screen.tsx:717` `AddedOn` | yes - `library-screen > pt-BR plurals and dates` |
| F-17 `en` catalog `auth.logIn` -> `Sign in` (C30) | `frontend/messages/en.json` | yes - landing `offers a Log in CTA` and `shows a cited-answer proof`, auth-screens `submitting login` and `renders the backend error` |
| F-18 `en` catalog `shell.logOut` -> `Sign out` (C30) | `frontend/messages/en.json` | yes - app-shell `shows the signed-in email plus account, logout, and theme controls` and `logout carries X-CSRF-Token` |

Control: when F-14 is written as JSX text (`<p>Loading your sources…</p>`) instead of a JS expression, `i18n-hardcoded > the source tree is clean` kills it. So the three survivors are exactly the sensor-blind JS-expression class that ADR-0034 `#### Limits` names.

## Gate

- `make lint` - exit 0: ruff check passed; ruff format reports 341 files already formatted; `tsc --noEmit` clean; `check_commits` reports 4 commits in `origin/main..HEAD` OK; architecture boundaries clean.
- `make test-frontend` - exit 0: 90 files and 1002 tests passed. REV-44 did not flake.
- `LEARNY_REQUIRE_DB=1 make test-backend` (`LEARNY_TEST_DATABASE_URL` from `.claude/settings.json`) - 3227 passed, 2 failed, 11 skipped. Both failures are `tests/test_deploy_topology.py::test_dev_merge_publishes_the_app_ports` and `::test_dev_merge_still_publishes_todays_infra_ports` (`assert '8000' in ['${LEARNY_API_HOST_PORT']`). Both come from the owner's uncommitted `docker-compose.override.yml` (env-var host ports). The branch touches no backend file and not the override, so they are not findings. CI is authoritative. No alembic re-stamp was needed.

## Findings

1. **F1 - blocking - C32 coverage gap.** No pt-BR proof covers several Library states that the claim names: signed-out (`frontend/app/components/library-screen.tsx:523`), loading sources (`:590`), sample ready (`:581`), the `processing` status, quiz generating (`:143`), quiz noSection, noneSurvived, discardFootnote and partial (`:243`, `:263`, `:291`, `:299`), and the pending labels (`:569`, `:648`, `:673`, `:696`). F-13 and F-14 survived. Fix: add a pt-BR test to `frontend/tests/library-screen.test.tsx` whose name matches `renders in pt-BR`. It should drive each of these states and assert its Portuguese text (`Carregando seus livros…`, `Você saiu da conta.`, `processando`, `Gerando baralho…`, the `noneSurvived`, `partial` and `noSection` sentences with their pt plurals, and `O livro de exemplo…`). The ICU plural branches of `quiz.partial`, `quiz.noneSurvived` and `quiz.discardFootnote` are pt-BR-only. No test exercises them today.
2. **F2 - blocking - C35 coverage gap.** No pt-BR proof covers the return chip (`frontend/app/components/chapter-reader.tsx:1115`), the stale-capture message (`:611`, `:658`), `← Capítulo anterior` (`frontend/app/components/toc-panel.tsx:173`), the mobile dock sheet title, description and `Fechar` (`frontend/app/components/reader-panel.tsx:461-469`), or the read-page Suspense fallback (`frontend/app/(read)/sources/[id]/read/page.tsx:31`). F-15 survived. Fix: extend the `chapter-reader.test.tsx` pt-BR block. The existing English tests at `:1791` (409 reload prompt) and the return-chip and mobile-dock tests already set these states up, so reuse that setup under `setTestLocale("pt-BR")`.
3. **F3 - non-blocking - proof selectors miss the claim-carrying tests.** The literal proof commands do not select some tests that carry the claims. C29's `-t "renders in pt-BR"` on `app-shell.test.tsx` does not select `shows the not-found notice in pt-BR` (`:249`). C32's filters do not select `renders the empty, done and error states in pt-BR` (`home-screen.test.tsx:457`) or `renders the empty and failed list states in pt-BR` (`library-screen.test.tsx:608`). C35's filter does not select `renders the margin rail in pt-BR` (`chapter-reader.test.tsx:2282`) or `renders the reader's signed-out and not-found states in pt-BR` (`:2302`). Run the commands as written and the not-found notice, the empty and error states and the margin rail go unproven. Fix: rename those tests so that each contains `renders in pt-BR` (for example `renders in pt-BR: empty, done and error states`), because checks.md is frozen.
4. **F4 - non-blocking - pt-BR wording.**
   - `frontend/messages/pt-BR.json:202` `library.row.tutor` = `Tutor`. The link opens `?panel=teach` (`library-screen.tsx:345`), and the batch-1 catalog calls that mode `Ensinar` (`account.aiProfile.*`). Suggest `Ensinar`.
   - `:188` status `failed {falhou}` is a verb on a badge, beside the adjectives `enviado`, `processando` and `pronto`. Suggest `com falha`.
   - `:205` `reconstrói o acervo deste livro`: `acervo` means a collection or holdings, not a processed corpus. Suggest `reconstrói o conteúdo processado deste livro`.
   - `:87`, `:182` and `:229` `Você saiu da conta.` reads "you logged out". The state is also reached by an expired session or a visitor who never signed in. Suggest `Você não está conectado.` for all three (`account` included, batch 1).
   - `:225` `quiz.partial` `# salvos` has no noun. Suggest `{saved, plural, one {# item salvo} other {# itens salvos}}`.

   Everything else reads as natural Brazilian Portuguese and is consistent with batch 1: `Entrar`/`Sair`, `Perguntar`, `processamento`, `baralho`, `Revisão`/`Revisar`, `E-mail`, and `Sumário`.
5. **F5 - non-blocking - date formatter.** `AddedOn` (`frontend/app/components/library-screen.tsx:717`) builds `new Intl.DateTimeFormat(locale, …)`, while `reading-controls.tsx` uses next-intl's `useFormatter()`. The output is correct (F-16 killed), and the component is client-only, so there is no hydration mismatch. `useFormatter().dateTime(added, {dateStyle: "medium"})` would follow the app-wide timeZone and formats config in one place.
6. **Sensor and ratchet check: no finding.** `PENDING_MIGRATION` in `frontend/tests/i18n-hardcoded.test.ts` lists none of the batch-2 files. 19 entries were removed. `app-sidebar.tsx` and `not-found-notice.tsx` were never listed, because their copy was sensor-blind JS. The three legal pages are exempt by path. A grep of every batch-2 file for English JS-expression literals, `title`/`aria-*` literals and template literals finds only book data (`frontend/app/page.tsx:21-23` `PROOF`, held under `lang="en"`) and `new Error("Could not anchor this passage to the book.")` (`frontend/app/components/chapter-reader.tsx:645`). That error never renders: `errorMessageKey` maps a non-`ApiError` to the fallback catalog key (`frontend/app/lib/errors.ts:130-133`). `p. {page}` (`chapter-reader.tsx:1095`) is `aria-hidden` and also correct in Portuguese. Numbers: `lineSpacingStep` uses `{step, number}`, and the segment uses `format.number`, which gives a decimal comma. The `{percent}` and `{minutes}` integers need no grouping.

## Deferred to owner

- `npm run build`. I skipped it for the memory budget. CI runs it.
- A browser or screenshot walk of the batch-2 surfaces in pt-BR, which ADR-0034 `#### Limits` keeps as part of review. Skipped by brief.
- The two local `test_deploy_topology` dev-port failures, which come from the uncommitted override.

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
