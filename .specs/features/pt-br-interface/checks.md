# pt-br-interface checks

Profile: standard
Plan: `.specs/features/pt-br-interface/plan.md`

Commands: frontend `cd frontend && npx vitest run tests/<file> -t "<name>"`; backend `cd backend && uv run pytest tests/<file>::<test>` (run `make infra` first for DB tests); gates `make lint`, `make test-frontend`, `make test-backend`, `cd frontend && npm run build`.

59 checks in 12 slices · 7 one-way doors · 0 open

## Checks

### S1 - The interface renders in the visitor's language · 3 files · 3 KB · ~1k

**C1** - The supported locales are exactly `en` and `pt-BR`, fallback `en` (AC 1)
Proof: `cd frontend && npx vitest run tests/i18n-config.test.ts -t "supports exactly en and pt-BR"`

**C2** - A supported `learny_locale` cookie wins over `Accept-Language` (AC 2)
Proof: `cd frontend && npx vitest run tests/i18n-config.test.ts -t "cookie beats Accept-Language"`

**C3** - Without a valid cookie, `Accept-Language` resolves to `pt-BR` when a `pt`/`pt-*` tag precedes any `en` tag by q-value then position, table-driven over `pt`, `pt-BR`, `pt-PT`, `pt;q=0.9,en;q=0.8`, `en;q=0.5,pt;q=0.9`, while `en,pt` stays `en` (AC 3)
Proof: `cd frontend && npx vitest run tests/i18n-config.test.ts -t "negotiates pt-BR"`

**C4** - A cookie outside `{en, pt-BR}` is ignored and negotiation decides (AC 4)
Proof: `cd frontend && npx vitest run tests/i18n-config.test.ts -t "ignores an unsupported cookie"`

**C5** - An absent, malformed (`;;;`, `q=abc`) or unsupported-only (`fr,de`) `Accept-Language` renders `en` (AC 5)
Proof: `cd frontend && npx vitest run tests/i18n-config.test.ts -t "falls back to en"`

**C6** - The root layout sets `<html lang>` to `en` or `pt-BR` matching the rendered locale (AC 6)
Proof: `cd frontend && npx vitest run tests/i18n-layout.test.tsx -t "html lang follows the locale"`

**C7** - A message key used in code but absent from `en.json` fails `tsc --noEmit` (AC 7)
Proof: `cd frontend && npx vitest run tests/i18n-typed-keys.test.ts -t "tsc rejects a key missing from en"`

**C8** - The set of `messages/*.json` files equals `LOCALES`, and the request config loads a catalog by locale name with no per-locale branch (AC 8)
Proof: `cd frontend && npx vitest run tests/i18n-config.test.ts -t "catalog files match LOCALES"`

**C9** - The app assembles with the next-intl plugin: the production build succeeds and the standalone image test still passes (AC 6, startup configuration)
Proof: `cd frontend && npm run build`
Proof: `cd frontend && npx vitest run tests/prod-image.test.ts`

### S2 - A learner chooses a language and keeps it · 8 files · 143 KB · ~35k

**C10** - `PUT /api/me/locale` with `pt-BR` or `en` returns `200` `{locale}` and persists it, and a second `PUT` replaces the first leaving one row (AC 9, AC 12)
Proof: `cd backend && uv run pytest tests/test_web_locale.py::test_put_stores_and_replaces_the_choice`

**C11** - `PUT /api/me/locale` with an unsupported value (`fr`, `pt`, empty, `PT-BR`) returns `422` and stores nothing (AC 12)
Proof: `cd backend && uv run pytest tests/test_web_locale.py::test_put_rejects_unsupported_locale`

**C12** - `PUT` and `DELETE` return `401` without a session and `403` without a valid CSRF token, storing nothing (AC 13)
Proof: `cd backend && uv run pytest tests/test_web_locale.py::test_mutations_need_session_and_csrf`

**C13** - `DELETE /api/me/locale` returns `204`, clears a stored choice, and returns `204` again when nothing is stored (AC 14)
Proof: `cd backend && uv run pytest tests/test_web_locale.py::test_delete_is_idempotent`

**C14** - `GET /api/auth/me` returns `locale` as `en`, `pt-BR`, `null` when unset, and `null` when the stored value is unsupported (AC 15)
Proof: `cd backend && uv run pytest tests/test_web_locale.py::test_me_reports_the_stored_locale`

**C15** - A learner reads and changes only their own preference; another learner's row is untouched (AC 16)
Proof: `cd backend && uv run pytest tests/test_web_locale.py::test_preferences_are_isolated_per_learner`

**C16** - Deleting the user row deletes the stored locale (AC 17)
Proof: `cd backend && uv run pytest tests/test_locale_preference_repository.py::test_deleting_the_user_removes_the_preference`

**C17** - Picking a locale in Account sends `PUT` with the CSRF token, writes the cookie only after `200`, then calls `router.refresh()` (AC 9)
Proof: `cd frontend && npx vitest run tests/account-locale.test.tsx -t "saves then writes the cookie then refreshes"`

**C18** - Picking "Automatic" sends `DELETE`, clears the cookie and refreshes (AC 10)
Proof: `cd frontend && npx vitest run tests/account-locale.test.tsx -t "automatic clears the choice"`

**C19** - A failed save keeps the previous locale (no cookie write, no refresh) and shows a localized error in Account (AC 11)
Proof: `cd frontend && npx vitest run tests/account-locale.test.tsx -t "failed save keeps the previous locale"`

**C20** - When `/api/auth/me` `locale` differs from the cookie the cookie is rewritten and one refresh happens; when it is `null` or equal there is no refresh; when `/api/auth/me` fails nothing happens (AC 18)
Proof: `cd frontend && npx vitest run tests/use-locale-sync.test.tsx -t "reconciles the cookie from the stored locale"`

**C21** - The anonymous switcher sets `learny_locale` with `Path=/`, `Max-Age=31536000`, `SameSite=Lax`, makes no fetch, and refreshes (AC 19)
Proof: `cd frontend && npx vitest run tests/locale-switcher.test.tsx -t "sets the cookie without an API call"`

**C22** - A locale change re-renders through `router.refresh()` and never calls `location.reload` or assigns `location` (AC 20)
Proof: `cd frontend && npx vitest run tests/locale-switcher.test.tsx -t "never reloads the page"`

### S3 - Failures speak the learner's language · 12 files · 86 KB · ~22k

**C23** - A non-OK response throws an `ApiError` carrying the operation key, the HTTP status and the backend `detail`, from every request client (AC 21)
Proof: `cd frontend && npx vitest run tests/errors.test.ts -t "every client throws an ApiError with operation status and detail"`

**C24** - `401`, `429` and `5xx` (500, 502, 503) show the shared status message in `en` and `pt-BR`, not the operation copy (AC 22)
Proof: `cd frontend && npx vitest run tests/errors.test.tsx -t "status classes use the shared message"`

**C25** - Any other status (400, 404, 409, 422) shows the operation's localized failure copy (AC 23)
Proof: `cd frontend && npx vitest run tests/errors.test.tsx -t "other statuses use the operation copy"`

**C26** - With the locale `pt-BR`, a `500` carrying an English `detail` leaves that `detail` text off the screen (AC 24)
Proof: `cd frontend && npx vitest run tests/error-display.test.tsx -t "backend detail never reaches the learner"`

**C27** - `StreamRequestError.status`, `NoteError` kinds and `AiProfileRequestError.status` still reach their consumers (AC 25)
Proof: `cd frontend && npx vitest run tests/errors.test.ts -t "legacy typed errors keep their kind and status"`

### S4 - Landing, sign-in and the shell in Portuguese · 40 files · 101 KB · ~25k

**C28** - In `pt-BR` landing, login, register, password reset and email verification render from the catalog with no English UI copy (AC 26)
Proof: `cd frontend && npx vitest run tests/landing.test.tsx -t "renders in pt-BR"`
Proof: `cd frontend && npx vitest run tests/auth-screens.test.tsx -t "renders in pt-BR"`

**C29** - In `pt-BR` the sidebar, header, theme toggle, shortcut help, not-found notice and vendored dialog/sheet/sidebar default text render from the catalog (AC 26)
Proof: `cd frontend && npx vitest run tests/app-shell.test.tsx -t "renders in pt-BR"`
Proof: `cd frontend && npx vitest run tests/vendored-primitives.test.tsx -t "default text comes from the catalog"`

**C30** - In `en` the migrated landing, auth and shell screens still pass their existing English assertions, unedited apart from the intl binding (AC 27)
Proof: `cd frontend && npx vitest run tests/landing.test.tsx tests/auth-screens.test.tsx tests/app-shell.test.tsx tests/app-sidebar.test.tsx`

**C31** - `/terms`, `/privacy` and `/copyright` stay English with `lang="en"` on their content wrapper while the locale is `pt-BR` (AC 28)
Proof: `cd frontend && npx vitest run tests/legal-pages.test.tsx -t "stay English under pt-BR"`

### S5 - Home and Library in Portuguese · 7 files · 31 KB · ~8k

**C32** - In `pt-BR` Home, Library, ingestion status and every empty, loading and error state of both render from the catalog (AC 29)
Proof: `cd frontend && npx vitest run tests/library-screen.test.tsx -t "renders in pt-BR"`
Proof: `cd frontend && npx vitest run tests/home-screen.test.tsx -t "renders in pt-BR"`

**C33** - In `pt-BR` a count of 0, 1 and 2 books renders "0 livros", "1 livro", "2 livros", and a date renders in the locale's format (AC 30)
Proof: `cd frontend && npx vitest run tests/library-screen.test.tsx -t "pt-BR plurals and dates"`

**C34** - Book titles, authors and section titles render unchanged in `pt-BR` (AC 31)
Proof: `cd frontend && npx vitest run tests/library-screen.test.tsx -t "book text is never translated"`

### S6 - The reader in Portuguese · 7 files · 78 KB · ~20k

**C35** - In `pt-BR` the reader chrome, table of contents, reading controls, margin rail, progress text, aria labels and keyboard help render from the catalog (AC 32)
Proof: `cd frontend && npx vitest run tests/chapter-reader.test.tsx -t "renders in pt-BR"`
Proof: `cd frontend && npx vitest run tests/reading-controls.test.tsx -t "renders in pt-BR"`

**C36** - Chapter text and citation snippets render unchanged in `pt-BR` (AC 33)
Proof: `cd frontend && npx vitest run tests/chapter-reader.test.tsx -t "book text is never translated"`

### S7 - Chat dock in Portuguese · 18 files · 151 KB · ~38k

**C37** - In `pt-BR` the Ask and Tutor panels, answer phases, the not-found answer, failed turns, conversation list, include-notes toggle, save-to-note and the dock Notes and Review tabs render from the catalog (AC 34)
Proof: `cd frontend && npx vitest run tests/ask-panel.test.tsx -t "renders in pt-BR"`
Proof: `cd frontend && npx vitest run tests/conversation-dock.test.tsx -t "renders in pt-BR"`

**C38** - The `NOT_FOUND_IN_SOURCE` sentinel never appears on screen and is never translated (AC 35)
Proof: `cd frontend && npx vitest run tests/cited-answer.test.tsx -t "sentinel is never rendered"`

### S8 - Review in Portuguese · 3 files · 47 KB · ~12k

**C39** - In `pt-BR` review sessions, rating buttons, FSRS interval labels, empty-deck, done-for-today, quiz progress and the heatmap's month and weekday names and legend render from the catalog and locale date rules (AC 36)
Proof: `cd frontend && npx vitest run tests/review-screen.test.tsx -t "renders in pt-BR"`
Proof: `cd frontend && npx vitest run tests/review-screen.test.tsx -t "heatmap uses locale names"`

### S9 - Notes in Portuguese · 8 files · 43 KB · ~11k

**C40** - In `pt-BR` the notes list, note detail, capture popover, card suggestions and anchor badges render from the catalog (AC 37)
Proof: `cd frontend && npx vitest run tests/notes-screen.test.tsx -t "renders in pt-BR"`
Proof: `cd frontend && npx vitest run tests/note-detail-screen.test.tsx -t "renders in pt-BR"`

**C41** - User-authored note titles and bodies render unchanged in `pt-BR` (AC 38)
Proof: `cd frontend && npx vitest run tests/note-detail-screen.test.tsx -t "user text is never translated"`

### S10 - English strings cannot creep back · 4 files · new · ~10k

**C42** - A key present in one catalog and absent from the other fails the parity test naming the key and the missing locale, in both directions (AC 39)
Proof: `cd frontend && npx vitest run tests/i18n-parity.test.ts -t "reports a key missing from either catalog"`

**C43** - A message with different ICU argument names (plain, `plural`, `select`) in the two catalogs fails the parity test naming the key (AC 40)
Proof: `cd frontend && npx vitest run tests/i18n-parity.test.ts -t "reports mismatched ICU arguments"`

**C44** - The real `en` and `pt-BR` catalogs are in parity (AC 39, AC 40)
Proof: `cd frontend && npx vitest run tests/i18n-parity.test.ts -t "the shipped catalogs are in parity"`

**C45** - A JSX text node of two or more ASCII letters, or a string in `aria-label`, `title`, `placeholder` or `alt`, in a translated file fails the hard-coded test naming file and line, outside the allowlist (AC 41)
Proof: `cd frontend && npx vitest run tests/i18n-hardcoded.test.ts -t "flags English JSX text and attribute literals"`

**C46** - A copy-bearing string literal (letters and whitespace) passed to `new Error(`, `new ApiError(` or any other `new …Error(` in an `app/lib` file, while a camelCase operation key passes, fails the hard-coded test naming file and line (AC 42)
Proof: `cd frontend && npx vitest run tests/i18n-hardcoded.test.ts -t "flags English error literals in lib files"`

**C47** - A file listed as pending migration that is already clean fails the hard-coded test naming it; the list is empty at the last PR (AC 43)
Proof: `cd frontend && npx vitest run tests/i18n-hardcoded.test.ts -t "a clean file cannot stay pending"`

**C48** - The source tree has no findings outside the allowlist and the pending list (AC 41, AC 42)
Proof: `cd frontend && npx vitest run tests/i18n-hardcoded.test.ts -t "the source tree is clean"`

**C49** - The hard-coded test header and ADR-0032 both carry a "Limits" section naming what the heuristic cannot see (AC 44)
Proof: `cd frontend && npx vitest run tests/i18n-hardcoded.test.ts -t "documents its limits"`

### S11 - Ask and tutor answer in the learner's language · 11 files · 196 KB · ~49k

**C50** - Locale rules: `negotiate_locale` over the same vector table as C3, `effective_locale` prefers a supported stored value over the header and treats an unsupported stored value as unset, `response_language_for("en")` is `None` and `("pt-BR")` is `"pt-BR"` (AC 45, AC 46, AC 47)
Proof: `cd backend && uv run pytest tests/test_locale.py::test_negotiation_vectors`
Proof: `cd backend && uv run pytest tests/test_locale.py::test_effective_locale_precedence`

**C51** - For Ask and tutor turns, over both the JSON and the `/stream` route, a recording port receives `pt-BR` for a stored `pt-BR` learner and for an unset learner with a Portuguese `Accept-Language`, and `None` for stored `en`, for unset with an English header and for no header (AC 45, AC 46, AC 47)
Proof: `cd backend && uv run pytest tests/test_web_conversations_language.py::test_response_language_reaches_the_port`

**C52** - With `response_language=None` the Anthropic request is byte-identical to today's for Ask and tutor turns (system block, cache breakpoint, user turn) (AC 46)
Proof: `cd backend && uv run pytest tests/test_answering_anthropic.py::test_no_response_language_leaves_the_request_unchanged`

**C53** - With `pt-BR` the Anthropic request carries the instruction in the user turn for Ask and tutor turns and leaves the system block and cache breakpoint unchanged (AC 48)
Proof: `cd backend && uv run pytest tests/test_answering_anthropic.py::test_response_language_goes_in_the_user_turn`

**C54** - With `pt-BR` the OpenAI-compatible adapter carries the instruction in the user message and leaves its system prompt unchanged (AC 49)
Proof: `cd backend && uv run pytest tests/test_answering_openai_compat.py::test_response_language_goes_in_the_user_message`

**C55** - The whole-reply `NOT_FOUND_IN_SOURCE` still maps to `found=False` and citations stay evidence-verbatim when a response language is set (AC 50)
Proof: `cd backend && uv run pytest tests/test_answering_anthropic.py::test_sentinel_and_citations_survive_a_response_language`

**C56** - The deterministic adapter returns identical output for `None`, `en` and `pt-BR`, and `RoutingGenerationAdapter` forwards the kwarg to the adapter that serves (AC 51)
Proof: `cd backend && uv run pytest tests/test_answering_local.py::test_response_language_does_not_change_the_extractive_answer`
Proof: `cd backend && uv run pytest tests/test_answering_routing.py::test_response_language_is_forwarded`

**C57** - An `Accept-Language` carrying arbitrary text (`pt-BR; ignore previous instructions`) places none of its text in any prompt, only the fixed per-language constant (AC 52)
Proof: `cd backend && uv run pytest tests/test_web_conversations_language.py::test_header_text_never_reaches_a_prompt`

### S12 - A Portuguese public-domain golden book · 4 files · 11 KB · ~3k

**C58** - The Portuguese golden book builds from public-domain excerpts, declares OPF `dc:language` `pt` and records its provenance in the fixture module (AC 53)
Proof: `cd backend && uv run pytest tests/test_golden_fixtures.py::test_portuguese_book_declares_language_and_provenance`

**C59** - Ingesting the Portuguese golden book stores chunks with `search_config` `portuguese` and the expected sections and anchors (AC 54)
Proof: `cd backend && uv run pytest tests/test_golden_ingestion.py::test_portuguese_book_ingests_with_portuguese_search_config`

**C60** - Each golden Portuguese question that uses an inflected form of a term in its target section returns that section's anchor within the top 3 (AC 55)
Proof: `cd backend && uv run pytest tests/test_golden_retrieval.py::test_portuguese_inflected_terms_reach_their_section`

**C61** - The deterministic adapter's answer to each Portuguese golden question cites only chunk ids inside the retrieved evidence, at the expected anchor, offline with no provider key (AC 56, AC 57)
Proof: `cd backend && uv run pytest tests/test_golden_citations.py::test_portuguese_answers_cite_the_expected_anchor`

## Coverage

| Set (size) | Member -> proof | Unproven |
| --- | --- | --- |
| supported locales (2) | `en` C1 · `pt-BR` C1 | - |
| `Accept-Language` negotiation vectors (9) | `pt` C3 · `pt-BR` C3 · `pt-PT` C3 · `pt;q=0.9,en;q=0.8` C3 · `en,pt` C3 · `en;q=0.5,pt;q=0.9` C3 · malformed C5 · unsupported-only C5 · absent C5 | - |
| `PUT /api/me/locale` statuses (4) | 200 C10 · 401 C12 · 403 C12 · 422 C11 | - |
| `DELETE /api/me/locale` statuses (3) | 204 C13 · 401 C12 · 403 C12 | - |
| `GET /api/auth/me` `locale` values (4) | `en` C14 · `pt-BR` C14 · unset `null` C14 · unsupported stored `null` C14 | - |
| request-error classes (4) | `401` C24 · `429` C24 · `5xx` C24 · other C25 | - |
| request clients (14) | `auth` `sources` `ingestion` `sections` `ai-profiles` `quiz` `study` `reading` `notes` `conversations` `streaming` `cards` `tutor-card` `locale` (save and reset): C23, table-driven over all 14 | - |
| legacy typed errors (6) | `StreamRequestError` C27 · `NoteError` C27 · `CardError` C27 · `ConversationRequestError` C27 · `AiProfileRequestError` C27 · `TutorCardError` C27 | - |
| migrated surfaces in `pt-BR` (11) | landing C28 · auth C28 · shell C29 · vendored primitives C29 · Home C32 · Library C32 · reader C35 · Chat dock C37 · review C39 · notes C40 · Account C19 | - |
| surfaces that must stay untranslated (5) | legal pages C31 · book text C34, C36 · citation snippets C36 · note bodies C41 · sentinel C38 | - |
| generation implementers of the new kwarg (5) | Anthropic C53 · OpenAI-compatible C54 · deterministic C56 · routing C56 · test fakes C51 | - |
| conversation routes x origin (4) | Ask JSON C51 · Ask stream C51 · tutor JSON C51 · tutor stream C51 | - |
| sensor rules (5) | parity keys C42 · parity arguments C43 · JSX and attribute literals C45 · lib error literals C46 · stale pending C47 | - |
| startup configuration: next-intl plugin and request config (2 assemblies) | production build C9 · test harness binding C28 | - |
| golden Portuguese cases (4) | language and provenance C58 · ingestion C59 · retrieval C60 · citations C61 | - |

- Claims naming a status code, route or response shape: C10, C11, C12, C13, C14 - each proof crosses the HTTP boundary through the test client
- C30 proves "unchanged English" through the existing test files, so the Verifier checks the diff of those files shows only the intl binding changed
- No other check claims more than the single case its proof exercises

## Swept

- validation: C5, C11
- failure modes: C19, C20, C24
- idempotency: C13
- authorization: C12, C15
- concurrency: C10 - `PUT` upserts on the primary key, so a second write replaces the first and one row remains
- data lifecycle: C16
- dependency failure: C20, C55 - `/api/auth/me` unreachable leaves the render locale untouched; a provider reply of the sentinel still maps to not-found
- state transitions: n/a - a locale has no states, any supported value may follow any other
- observability: n/a - no logging or metrics requirement in this change

## Out of scope

None - see the plan.

## Handoff

Estimate: bytes of the files each slice touches, divided by four (from `wc -c`), ×1 for reading, ×1.5 more for the edits and tests it provokes.

- S1 = ~1k, S2 = ~35k, S3 = ~22k, S10 = ~10k -> 68k × 1.5 = ~100k: the foundation (framework, preference slice, error plumbing, sensors) - all behind a default of `en`
- S4 = ~25k, S5 = ~8k, S6 = ~20k -> 53k × 1.5 = ~80k: landing, shell, Home, Library, reader
- S7 = ~38k, S8 = ~12k, S9 = ~11k -> 61k × 1.5 = ~92k: Chat, review, notes
- S11 = ~49k, S12 = ~3k -> 52k × 1.5 = ~78k: AI output language and the Portuguese fixture
- Total ~350k > 150k budget -> proposed cuts at the surface boundary after S10, after S6, and after S9
- Mechanism: handoff (chosen without asking, owner decision D2): four sequential batches, each its own PR merged before the next batch starts; the Verifier runs scoped to the batch's checks before each PR and over every check before the last
- The hard-coded-string ratchet list is seeded with every unmigrated file in batch 1 and shrinks with each batch; it is empty when batch 3 lands (C47)
