# pt-br-interface verification - batch 3, rounds 1 and 2

The two FAIL rounds before batch 3's round-3 PASS (see `verification.md`), kept unchanged for the record. Round 2 is first; round 1 is under it.

# pt-br-interface verification

Round verdict (superseded by the round-3 PASS in `verification.md`): FAIL
**Profile**: standard
**Diff range**: origin/main..88beef1 (batch 3: c737b7a..207f75d; round-2 fix range 207f75d..88beef1, 2 commits: ed760ec code and tests, 88beef1 plan rows and the round-1 report)
**Round**: 2 - scoped (batch 3 of 4 scope)
**Verifier**: independent sub-agent (author != verifier)

Scope: batch 3 = checks C37-C41, plus the ratchet checks C44, C47 and C48. Round 2 covers two things:

- **The fix diff `207f75d..88beef1`.** On the component side it touches `cited-answer.tsx`, `dock-review-panel.tsx`, `study-heatmap.tsx` and `components/ui/carousel.tsx`, plus both catalogs. On the test side it touches eight files.
- **Every round-1 verdict that was not PASS.** That is C37, C38, C39, C40 and C47, and the round-1 survivors F4, F6, F7, F8, F9, F12, F13, F14, F18 and F19, plus the English citation mark.

The round-1 report is kept unchanged under `## Earlier batches`, and the batch-2 and batch-1 reports stay nested inside it.

Why FAIL: every round-1 gap is closed. All ten round-1 survivors and the citation-mark English are now killed, and all five reopened checks pass. The FAIL comes from two of the new faults injected on surfaces this fix created, which survive:

- **N3, the dock due count.** It now goes through `Intl.NumberFormat(locale)` (`frontend/app/components/dock-review-panel.tsx:95`), but no test renders a count of 1000 or more, so a raw `{total}` passes.
- **N6, the review page's loading fallback.** The new test is titled `page title and loading fallback: renders in pt-BR` (`frontend/tests/review-screen.test.tsx:1529`), but it never renders the Suspense fallback: `useSearchParams` is mocked and does not suspend. So `{"Loading…"}` at `frontend/app/(app)/review/page.tsx:44` passes.

Both are one-assertion fixes. Neither is a learner-visible leak today.

## Binding sources

Re-checked at 88beef1 against the fix. The three new "(batch 3)" rows in `plan.md` `## Assumptions` are "Batch-3 Verifier round 1", "Proof locations for C37" and "Dock due caption".

| Source | Opened | Contradiction | Uncovered |
| --- | --- | --- | --- |
| `docs/adr/0034-ui-internationalization.md` | yes (carried from 207f75d; the fix does not touch it) | none | - |
| `plan.md` `## Assumptions` rows marked "(batch 3)" (13 rows, 3 new) | yes - read at 88beef1 | none. Each claim in the "Batch-3 Verifier round 1" row is in the code: the mark label (`frontend/app/components/cited-answer.tsx:67`), the carousel roles (`frontend/components/ui/carousel.tsx:127`, `:165`), the `Intl.NumberFormat` totals (`frontend/app/components/study-heatmap.tsx:505`, `frontend/app/components/dock-review-panel.tsx:95`), the batch-2 `=0` branches, the rewording, and the ratchet test (`frontend/tests/i18n-hardcoded.test.ts:197`, `:247`, `:253`). "Proof locations for C37" names `teach-panel` and `ask-panel`, and I ran both by name. "Dock due caption" records round 1's B3-F1 | - |

## Checks

How the proofs ran at 88beef1:

- **One invocation**, `npx vitest run --maxWorkers=2 --minWorkers=1 --reporter=verbose`, over 14 files: `ask-panel`, `teach-panel`, `conversation-dock`, `cited-answer`, `review-screen`, `notes-screen`, `note-detail-screen`, `i18n-hardcoded`, `i18n-parity`, `reader-panel`, `home-screen`, `library-screen`, `vendored-primitives` and `study-heatmap`. Home and Library were added because the fix changed their pt-BR plurals. Exit 0: 14 files and 296 tests passed.
- **Every claim-carrying test appears by name**:
  - `ask-panel`: 7 `renders in pt-BR`, including the new `AskPanel citations in pt-BR > citation marks, note citations and show-in-book` and `vendored chat primitives in pt-BR > default text of the vendored primitives`.
  - `teach-panel`: 2.
  - `conversation-dock`: 4.
  - `review-screen`: 5 `renders in pt-BR`, including the new `page title and loading fallback`, plus `heatmap uses locale names`.
  - `notes-screen`: 3.
  - `note-detail-screen`: 3, plus `user text is never translated`.
  - `cited-answer`: `sentinel is never rendered`.
  - `i18n-hardcoded`: `a clean file cannot stay pending` and `the source tree is clean`.
  - `i18n-parity`: `the shipped catalogs are in parity`.
- **Duplicate-key warning gone**: the round-1 `teach-panel` warning (`two children with the same key`) no longer appears; 0 occurrences.

Citation status:

- **Refreshed at 88beef1**: C37, C38, C39, C40 and C47.
- **Carried from 207f75d**: C41, C44 and C48. They were PASS in round 1 and their proofs passed again here. Their line numbers did not move, except as noted.

| Check | Claim | Proof run | Evidence | Result |
| --- | --- | --- | --- | --- |
| C37 | Ask and Tutor panels, answer phases, not-found answer, failed turns, conversation list, include-notes toggle, save-to-note and the dock Notes/Review tabs render from the catalog (pt-BR) | `ask-panel` 7, `conversation-dock` 4 and `teach-panel` 2 `renders in pt-BR` passed (verified at 88beef1) | Round-1 evidence stands (carried; the lines above `:2100` in `ask-panel.test.tsx` did not move). New: `frontend/tests/ask-panel.test.tsx:2148` `name: "Citação 1"`, `:2156` `Mostrar no livro`, `:2164` `Sua nota — Minha nota`, `:2165` `Abrir nota`, `:2171` `toMatch(/^Sua nota/)`; vendored defaults `:2236` `O que você gostaria de saber?`, `:2241` `Nenhuma fonte usada`, `:2251` `[aria-roledescription="carrossel"]`, `:2270` `Paleta de comandos`; `frontend/tests/conversation-dock.test.tsx:507` `expect(more.textContent).toBe("Carregando…")`. The code: `frontend/app/components/cited-answer.tsx:67` `aria-label={t("mark", { index })}`. Faults F7, F8, F9, F12, F13, F21 and N1 are killed | PASS |
| C38 | the `NOT_FOUND_IN_SOURCE` sentinel never appears and is never translated | `cited-answer` `sentinel is never rendered` passed (verified at 88beef1) | `frontend/tests/cited-answer.test.tsx:368` `const NOT_FOUND_SENTINEL = "NOT_FOUND_IN_SOURCE";` (spelled out); `:375` `not.toContain(NOT_FOUND_SENTINEL)` over both catalogs; `:383` `expect(container.textContent ?? "").not.toContain(NOT_FOUND_SENTINEL)`. F18 is killed | PASS |
| C39 | review sessions, grades, intervals, empty deck, done for today, quiz progress and the heatmap names and legend render from the catalog and locale rules (pt-BR) | `review-screen` 5 `renders in pt-BR` plus `heatmap uses locale names` passed (verified at 88beef1) | All 9 interval buckets: `frontend/tests/review-screen.test.tsx:1385` `["~4 dias", "~2 sem.", "~1 mês", "~4 meses"]`, `:1392` `~1 dia`, and `~1 min`/`~10 min`/`~1 h`/`~1 ano` in the first card. `:1519` `Por hoje é só`. `:1539` page `<h1>` `Revisão`. `:1584` `seg., 13 de jul.: 0 revisões · 0 páginas`. `:1611` `1.234revisões3páginas`. `:1614` `Mostrar estatísticas`. F4, F6 and N2 are killed. The page's loading fallback is not proven (N6 survives, see Ranked gaps) | PASS |
| C40 | notes list, note detail, capture popover, card suggestions and anchor badges render from the catalog (pt-BR) | `notes-screen` 3 and `note-detail-screen` 3 `renders in pt-BR` passed (verified at 88beef1) | `frontend/tests/notes-screen.test.tsx:404` `anchor-status-stale` -> `desatualizado`; `:394` page `<h1>` `Notas`. Round-1 evidence carried. F14 and N5 are killed | PASS |
| C41 | user-authored note titles and bodies unchanged (pt-BR) | `note-detail-screen` `user text is never translated` passed (verified at 88beef1) | `frontend/tests/note-detail-screen.test.tsx:494`, `:496`, `:503` (carried from 207f75d; the one changed line in that file is `:364`, below these) | PASS |
| C44 | shipped catalogs in parity | `i18n-parity` passed (verified at 88beef1) | `frontend/tests/i18n-parity.test.ts:218-219` (carried) | PASS |
| C47 | a stale pending file fails naming it; the list is empty at the last PR | `i18n-hardcoded` `a clean file cannot stay pending` passed (verified at 88beef1) | `frontend/tests/i18n-hardcoded.test.ts:247` `toEqual(["app/components/clean.tsx"])`: the rule is proven on a synthetic list through `stalePending` (`:197`), which the real-tree check also calls. `:253` `expect(PENDING_MIGRATION, …).toEqual([])`; `:80` the list is empty. F19 is killed | PASS |
| C48 | the source tree has no findings outside the allowlist and the pending list | `i18n-hardcoded` `the source tree is clean` passed (verified at 88beef1) | `frontend/tests/i18n-hardcoded.test.ts:263` `expect(unexpected, …).toEqual([])` (moved down by the new helper; unchanged). The fix diff adds no `ALLOWED_TEXT` or `EXEMPT_PATHS` entry | PASS |

## Coverage

These rows were recomputed at 88beef1 because the fix touched their authority. The other rows are carried from 207f75d.

| Set (size) | Recomputed from | Member -> proof | Unproven |
| --- | --- | --- | --- |
| Ask/Tutor citation strings (`chat.citations` 10 keys including the new `mark`) | `frontend/app/components/citations.tsx`, `frontend/app/components/cited-answer.tsx` | regionLabel, sectionChip, closePassage, openInBook (round 1) · mark `ask-panel.test.tsx:2148` · showInBook `:2156` · noteChip `:2164`'s chip · noteTitled `:2164` · openNote `:2165` · note (untitled) `:2171` | - |
| conversation list states (9) | `frontend/app/components/conversation-list.tsx` | round-1 members · loading-older `conversation-dock.test.tsx:507` | - |
| FSRS interval buckets (9) | `frontend/app/components/review-screen.tsx:100-108` | all 9 (`review-screen.test.tsx:1385`, `:1392` and the first card's four) | - |
| study stats card states (shown, hidden, loading, error) | `frontend/app/components/study-heatmap.tsx` | shown `:1611` · hidden `:1614` | loading is a text-free skeleton; error uses the shared `errors` copy, proven in batch 1 (C24) |
| heatmap activity plural vectors (0, 1, n) | `review.heatmap.activity` | 0 `review-screen.test.tsx:1584` · 1 and n `:1548-1551` | - |
| anchor statuses (3) | plan row | active · orphaned · stale `notes-screen.test.tsx:404` | - |
| page headings (2) | the two page files | Revisão `review-screen.test.tsx:1539` · Notas `notes-screen.test.tsx:394` | - |
| vendored chat-primitive defaults | plan "Vendored chat primitives" row | prompt placeholder, upload, empty state, sources 0 and n, branch prev/next/page, carousel prev/next and slide prev/next, carousel and slide roles, command title and description: `ask-panel.test.tsx:2236-2272` | none learner-visible. `promptInput.addAttachments`, `takeScreenshot` and the three file-error messages are not rendered. Their components still have no consumer in the app, so this is a note, not a gap |
| locale-formatted numbers added by the fix (3) | `frontend/app/components/study-heatmap.tsx:505`, `frontend/app/components/dock-review-panel.tsx:95` | study reviews total `review-screen.test.tsx:1611` (`1.234`) | dock due count (N3 survives) · study pages total (same formatter instance as reviews, so it rides on N2's kill) |
| review page states (title, fallback) | `frontend/app/(app)/review/page.tsx` | title `:1539` | loading fallback `frontend/app/(app)/review/page.tsx:44` (N6 survives; the test named for it never renders it) |

## Test policy rows

`checks.md` has no `Test policy` section, so there are no rows to judge.

## Faults injected

Each fault was applied in place, one at a time, by a script that replaces one exact text occurrence, runs only the target file (`--maxWorkers=2 --minWorkers=1`, with the frozen `-t` filter), then restores the file with `git checkout --`. After each group, `git status --porcelain` showed only ` M docker-compose.override.yml`.

| Mutation | Location | Killed |
| --- | --- | --- |
| F4 stats toggle -> `"Show stats"` (round-1 survivor) | `frontend/app/components/study-heatmap.tsx:583` | yes - `review-screen > heatmap uses locale names` (no `Mostrar estatísticas`) |
| F6 pt-BR `review.heatmap.activity` loses its `=0` branches (round-1 survivor) | `frontend/messages/pt-BR.json` | yes - `review-screen > heatmap uses locale names` (no `0 revisões · 0 páginas`) |
| F7 loading-older -> `"Loading…"` (round-1 survivor) | `frontend/app/components/conversation-list.tsx:268` | yes - `conversation-dock > empty list and older pages: renders in pt-BR` |
| F8 `{"Show in book"}` (round-1 survivor) | `frontend/app/components/citations.tsx:259` | yes - `ask-panel > citation marks, note citations and show-in-book: renders in pt-BR` |
| F9 note chip -> `` `Your note: …` `` (round-1 survivor) | `frontend/app/components/citations.tsx:135` | yes - same test |
| F12 `CommandDialog` title default -> `"Command Palette"` (round-1 survivor) | `frontend/components/ui/command.tsx:54` | yes - `ask-panel > default text of the vendored primitives: renders in pt-BR` |
| F13 prompt placeholder default -> English (round-1 survivor) | `frontend/components/ai-elements/prompt-input.tsx:1069` | yes - same test |
| F14 pt-BR `stale {stale}` (round-1 survivor) | `frontend/messages/pt-BR.json` `notes.anchorStatus` | yes - `notes-screen > list, tags, badges and filters: renders in pt-BR` |
| F18 `NOT_FOUND_SENTINEL` -> `"NOT_FOUND"` (round-1 survivor) | `frontend/app/lib/citations.ts:63` | yes - `cited-answer > sentinel is never rendered` |
| F19 stale filter disabled (round-1 survivor) | `frontend/tests/i18n-hardcoded.test.ts:198` (`stalePending`) | yes - `i18n-hardcoded > a clean file cannot stay pending` |
| F21 citation mark back to `` `Citation ${index}` `` (the round-1 English, re-introduced) | `frontend/app/components/cited-answer.tsx:67` | yes - `ask-panel > citation marks, note citations and show-in-book: renders in pt-BR` |
| N1 carousel `aria-roledescription` -> `"carousel"` | `frontend/components/ui/carousel.tsx:127` | yes - `ask-panel > default text of the vendored primitives: renders in pt-BR` |
| N2 study reviews total -> raw `{reviews}` | `frontend/app/components/study-heatmap.tsx:531` | yes - `review-screen > heatmap uses locale names` (`1234` vs `1.234`) |
| N3 dock due count -> raw `{total}` | `frontend/app/components/dock-review-panel.tsx:95` | no - survived `conversation-dock -t "renders in pt-BR"` and `dock-review-tab` run whole; no test uses a count of 1000 or more |
| N5 notes page `<h1>` -> `{"Notes"}` | `frontend/app/(app)/notes/page.tsx:24` | yes - `notes-screen > list, tags, badges and filters: renders in pt-BR` |
| N6 review page Suspense fallback -> `{"Loading…"}` | `frontend/app/(app)/review/page.tsx:44` | no - survived `review-screen -t "renders in pt-BR"`; the fallback never renders under the mocked `useSearchParams` |
| Z1 pt-BR `chat.conversations.turns` loses `=0` | `frontend/messages/pt-BR.json` | yes - `conversation-dock > empty list and older pages` (`(0 interação)`) |
| Z2 pt-BR `chat.elements.usedSources` loses `=0` | `frontend/messages/pt-BR.json` | yes - `ask-panel > default text of the vendored primitives` |
| Z3-Z5 pt-BR `home.due.count`, `library.quiz.noneSurvived`, `library.quiz.discardFootnote` lose their new `=0` | `frontend/messages/pt-BR.json` | n/a - equivalent: count 0 cannot reach these messages (`frontend/app/components/home-screen.tsx:90` makes `job` at least 1 whenever the count renders; `noneSurvived` and the footnote render only when `discarded > 0`, `frontend/app/components/library-screen.tsx:257`, `:286`). Not counted |
| `slideRole` back to `"slide"` | `frontend/components/ui/carousel.tsx:165` | n/a - equivalent: the pt-BR value is also `slide`. Not run |

## Gate

- `npx vitest run --maxWorkers=2 --minWorkers=1` (the whole frontend suite, run once this round) - exit 0: 91 files and 1042 tests passed, 0 failed. The `review-screen` flake did not show up.
- The 14 targeted files (see Checks) - exit 0: 296 passed, 0 failed.
- `npx tsc --noEmit -p .` - exit 0.
- Backend: not run. The fix range touches only `frontend/` and `.specs/`.
- Tree after verification: `git status --porcelain` shows ` M docker-compose.override.yml` (the owner's file, untouched) and this report.

## Ranked gaps

1. **N3 - the dock due count's locale formatting is unproven.** `frontend/app/components/dock-review-panel.tsx:95` formats with `Intl.NumberFormat(locale)`, but every dock test uses a count below 1000, so the raw number passes. Fix: one pt-BR dock test with `total_due` of 1000 or more, asserting `due-count` reads `1.234`. This is the fix for round 1's B3-F2, and its new surface has never been made to fail.
2. **N6 - the review page's loading fallback is unproven, though a test is named for it.** `frontend/tests/review-screen.test.tsx:1529` is titled `page title and loading fallback`, but the mocked `useSearchParams` never suspends, so `frontend/app/(app)/review/page.tsx:44` is never rendered. Fix: either make the mock suspend once and assert `Carregando…`, as batch 2 did for the read-page fallback, or rename the test and record the fallback as unreachable under dynamic rendering. - C39

## Findings

- **B3-R2-F1 - non-blocking - carried.** The review position `{index + 1}/{queue.length}` (`frontend/app/components/review-screen.tsx`, `data-testid="position"`) still renders raw numbers. The round-1 row fixed only the totals and the due count. A 1000-card session is unlikely.
- **B3-R2-F2 - non-blocking - test hygiene.** The vendored-primitives test assigns `globalThis.IntersectionObserver` and never restores it, though it does delete `matchMedia` (`frontend/tests/ask-panel.test.tsx` `:2189`; `matchMedia` is deleted at `:2273`). Later tests in that file inherit the stub.
- **B3-R2-F3 - non-blocking.** pt-BR `library.quiz.partial`'s `failed` plural still has no `=0` branch, but the message renders only when a section failed.
- **Translation quality.** The reworded strings read naturally: "Por hoje é só" and "adicionar o mesmo texto de novo não cria uma cópia". So do the new keys: "Citação {index}", "carrossel", and "slide", which is the usual Brazilian term.

## Deferred to owner

- `npm run build` and the commit and architecture parts of `make lint`. Skipped for memory, and CI runs them. `tsc --noEmit` is in the Gate.
- A browser and screen-reader walk in pt-BR. Skipped by brief.
- Backend tests. The fix changes no backend code.

## Earlier batches

Batch 3 round 1, moved unchanged (the batch 2 and batch 1 reports it carried live in `verification.md`):

# pt-br-interface verification

Round verdict (superseded by the round-3 PASS in `verification.md`): FAIL
**Profile**: standard
**Diff range**: origin/main..207f75d (batch 3: c737b7a review, 57ea5e2 chat, cf016a1 notes, 207f75d specs)
**Round**: 1 - full (batch 3 of 4 scope)
**Verifier**: independent sub-agent (author != verifier)

Scope: batch 3 = slices S7, S8 and S9 = checks C37-C41 (AC 34-38), plus the ratchet checks C44, C47 and C48 because this batch must leave `PENDING_MIGRATION` empty. Checks outside that set are out of this batch's scope. They are not failures. The batch-2 report (which carries the batch-1 report under its own `## Earlier batches`) is moved unchanged under `## Earlier batches` below.

Why FAIL, in one paragraph: every frozen proof is green at 207f75d and `PENDING_MIGRATION` is empty. But one learner-visible English string survives on a C37 surface, in the inline citation mark of every cited Ask and Tutor answer (`frontend/app/components/cited-answer.tsx:65`). Also 9 of 20 injected faults survive: C37 has 3 and C39 has 2, plus one each for C38, C40 and C47, and one for the vendored defaults. Each survivor is a plausible wrong implementation that the pt-BR render tests let through.

## Binding sources

| Source | Opened | Contradiction | Uncovered |
| --- | --- | --- | --- |
| `docs/adr/0034-ui-internationalization.md` | yes - read in full at 207f75d, including `#### Limits` | none. The code follows the ADR: copy comes from `useTranslations`, and the sentinel stays an English machine token. The ADR's Limits section names template literals and `cond ? "x" : t()` as blind spots of the sensor, and the one surviving English string below is exactly such a template literal | `Citation ${index}` aria-label (`frontend/app/components/cited-answer.tsx:65`): an AC 34 element (the Ask/Tutor answer) still English, with no catalog key and no pt-BR assertion |
| `plan.md` `## Assumptions` rows marked "(batch 3)" (10 rows) | yes - read at 207f75d | none between a row and the code. Tutor chips: the wire still sends the sentinel, and the thread maps it to the label (`frontend/app/components/teach-panel.tsx:407-411`). Card offer: `lang="en"` is at `:812`. Ask templates are catalog messages. Backend tokens use `select … other {{x}}` and the raw-bucket fallback (`frontend/app/components/review-screen.tsx:784-786`). Heatmap names come from `Intl.DateTimeFormat(locale, …)` (`frontend/app/components/study-heatmap.tsx:94-100`), and no `timeZone` is configured (`grep -rn timeZone frontend/i18n frontend/app/layout.tsx frontend/tests/setup-intl.ts` finds nothing). The sentinel guard is `frontend/app/components/cited-answer.tsx:126-129`. Turn count: `reader-panel.test.tsx` is the only English assertion changed. Vendored files use `prop ?? t(…)`. The namespace is `review.heatmap`/`review.stats`. The wording rows match the catalog. One unrecorded English change: `chat.dockReview.dueCaption` now reads "card due from this book" for 1 (it used to read "cards" for every count). It is the same kind of fix as the turn-count row, but no row records it | the "Vendored chat primitives" row says those defaults were migrated. No test renders any of them in pt-BR, and none has a learner-visible consumer (see Coverage) |

## Checks

How the proofs ran at 207f75d:

- **Whole files**: one invocation, `npx vitest run --maxWorkers=2 --minWorkers=1 --reporter=verbose`, over 10 files: `ask-panel`, `conversation-dock`, `cited-answer`, `review-screen`, `notes-screen`, `note-detail-screen`, `teach-panel`, `i18n-hardcoded`, `i18n-parity` and `reader-panel`. Exit 0. 10 files and 223 tests passed. Every claim-carrying test appears in the verbose output individually:
  - `ask-panel`: 5 `… renders in pt-BR` tests.
  - `conversation-dock`: 4.
  - `review-screen`: 4 `renders in pt-BR` plus `heatmap uses locale names`.
  - `notes-screen`: 3.
  - `note-detail-screen`: 3, plus `user text is never translated`.
  - `teach-panel`: 2.
  - `cited-answer`: `sentinel is never rendered`.
  - `i18n-parity`: `the shipped catalogs are in parity`.
  - `i18n-hardcoded`: `a clean file cannot stay pending` and `the source tree is clean`.
- **The frozen filters select real tests.** Every `-t` name in C37-C41 matches at least one test in its named file (lines below). The fault-injection runs also re-ran each filter alone with `-t`, and each selected only the named tests (e.g. `review-screen -t "renders in pt-BR"`: 4 run, 37 skipped).
- `npx tsc --noEmit -p .` - exit 0.

| Check | Claim | Proof run | Evidence | Result |
| --- | --- | --- | --- | --- |
| C37 | Ask and Tutor panels, answer phases, not-found answer, failed turns, conversation list, include-notes toggle, save-to-note and the dock Notes/Review tabs render from the catalog (pt-BR) | `ask-panel` 5 and `conversation-dock` 4 `renders in pt-BR` passed (verified at 207f75d) | `frontend/tests/ask-panel.test.tsx:1895`, `:1922`, `:1930`, `:1953`, `:1960`, `:2040` `expectNoEnglishCopy(...CHAT_NAMESPACES)`; `:1939` `name: "Citação: Chapter 1 › Core Idea"`; `:1998` `Tentar novamente`; `:2030` `Isso não aparece neste livro.`; `frontend/tests/conversation-dock.test.tsx:449`, `:473`, `:526`, `:553`, `:580` `expectNoEnglishCopy`; `:456` `(1 interação)`; `:496` `(nenhuma interação)`; `:578` `cartão deste livro para revisar`. Tutor: `frontend/tests/teach-panel.test.tsx:1373`, `:1397`, `:1410`, `:1453`, and `:1444` `[lang="en"]`. But `frontend/app/components/cited-answer.tsx:65` `aria-label={`Citation ${index}`}` is English under pt-BR, and no pt-BR test renders an inline mark (the `streamAnswer` text at `frontend/tests/ask-panel.test.tsx:1533` has no `[^1]`). Faults F7, F8 and F9 survive | FAIL |
| C38 | the `NOT_FOUND_IN_SOURCE` sentinel never appears on screen and is never translated | `cited-answer` `sentinel is never rendered` passed (verified at 207f75d) | `frontend/tests/cited-answer.test.tsx:372` `expect(JSON.stringify(catalog)).not.toContain(NOT_FOUND_SENTINEL)`; `:380` `expect(container.textContent ?? "").not.toContain(NOT_FOUND_SENTINEL)` for `en` and `pt-BR`. The expected token is imported from the code under test, not written at the assertion (`NOT_FOUND_SENTINEL`), and no test anywhere spells `NOT_FOUND_IN_SOURCE` (`grep -rln NOT_FOUND_IN_SOURCE frontend/tests` finds nothing). So F18 (a wrong constant) survives | FAIL |
| C39 | review sessions, grades, FSRS intervals, empty deck, done for today, quiz progress and the heatmap's month/weekday names and legend render from the catalog and locale date rules (pt-BR) | `review-screen` 4 `renders in pt-BR` plus `heatmap uses locale names` passed (verified at 207f75d) | `frontend/tests/review-screen.test.tsx:1294`, `:1302`, `:1308`, `:1361`, `:1389`, `:1433`, `:1459`, `:1477`, `:1513` `expectNoEnglishCopy`; `:1357` `["~1 min", "~10 min", "~1 h", "~1 dia"]`; `:1358` grades `Novamente/Difícil/Bom/Fácil`; `:1384` `3 cartões revisados.`; `:1506` `Pronto por hoje`; `:1528` weekdays `seg.`; `:1537` months `abr.`; `:1548`/`:1551` cell names `seg., 20 de jul.: 7 revisões · 9 páginas`, `ter., 14 de jul.: 1 revisão · 1 página`; `:1557`, `:1579` `expectNoEnglishCopy`. Faults F4 and F6 survive | FAIL |
| C40 | notes list, note detail, capture popover, card suggestions and anchor badges render from the catalog (pt-BR) | `notes-screen` 3 and `note-detail-screen` 3 `renders in pt-BR` passed (verified at 207f75d) | `frontend/tests/notes-screen.test.tsx:395`, `:412`, `:432`, `:455`, `:553` `expectNoEnglishCopy`; `:486` `["Destacar", "Anotar", "Explicar", "Perguntar", "Criar cartão"]`; `:392` `fora do livro`; `frontend/tests/note-detail-screen.test.tsx:343`, `:352`, `:367`, `:374`, `:413`, `:442`, `:456`, `:475` `expectNoEnglishCopy`; `:338` `fora do livro`. The anchor badge `stale` member is never rendered in pt-BR. Fault F14 survives | FAIL |
| C41 | user-authored note titles and bodies render unchanged (pt-BR) | `note-detail-screen` `user text is never translated` passed (verified at 207f75d) | `frontend/tests/note-detail-screen.test.tsx:494` `.toBe("Ada's algorithm")`; `:496` `.toBe("A note about [[Babbage]].")`; `:503` backlink `Babbage engine`. Fault F16b killed | PASS |
| C44 | the real `en` and `pt-BR` catalogs are in parity | `i18n-parity` `the shipped catalogs are in parity` passed (verified at 207f75d) | `frontend/tests/i18n-parity.test.ts:218` `toEqual([...LOCALES].sort())`; `:219` `expect(parityProblems(catalogs)).toEqual([])` | PASS |
| C47 | a stale pending file fails naming it; the list is empty at the last PR | `i18n-hardcoded` `a clean file cannot stay pending` passed (verified at 207f75d) | `frontend/tests/i18n-hardcoded.test.ts:80` `const PENDING_MIGRATION: string[] = [];` (the list is empty); `:236-237` `expect(stale, …).toEqual([])`. With an empty list that assertion is vacuous. F20 (a clean file put back on the list) is killed, which proves the rule works when an entry exists. But F19 (stale detection disabled) survives at HEAD, and nothing asserts that the list is empty | FAIL |
| C48 | the source tree has no findings outside the allowlist and the pending list | `i18n-hardcoded` `the source tree is clean` passed (verified at 207f75d) | `frontend/tests/i18n-hardcoded.test.ts:243-247` `expect(unexpected, …).toEqual([])`. The pending list is empty, so the whole scanned tree is clean. `ALLOWED_TEXT`/`EXEMPT_PATHS` did not grow in this diff: `git diff origin/main..HEAD -- frontend/tests/i18n-hardcoded.test.ts` touches only the `PENDING_MIGRATION` block | PASS |

## Coverage

Recomputed at 207f75d from the component source (the authority over which states and strings exist) and from the plan's batch-3 rows.

| Set (size) | Recomputed from | Member -> proof | Unproven |
| --- | --- | --- | --- |
| migrated surfaces in pt-BR, batch-3 members (3) | checks.md coverage row | Chat dock C37 · review C39 · notes C40 | Chat dock: inline citation mark (`frontend/app/components/cited-answer.tsx:65`, still English) |
| Ask/Tutor answer and citation strings (`chat.citations`, 9 keys, plus the inline mark) | `frontend/app/components/citations.tsx`, `frontend/app/components/cited-answer.tsx` | regionLabel `ask-panel.test.tsx:1941` · sectionChip `:1939` · closePassage `:1945` · openInBook `:1946` | noteChip, noteTitled, note (the note-origin citation, `frontend/app/components/citations.tsx:135`, `:212-213`) · openNote (`:246`) · showInBook (`:259`) · inline mark `Citation N` (`frontend/app/components/cited-answer.tsx:65`) |
| conversation list states (9) | `frontend/app/components/conversation-list.tsx` | heading, loading, new, resume, turns 0/1/2, rename, save/cancel title, delete, show older, empty: `conversation-dock.test.tsx:433-509` | the "loading older" in-flight label (`frontend/app/components/conversation-list.tsx:268`, F7 survives) |
| review states (empty, loading, error, card, reveal, grades, intervals, short-term, summary, done for today, note badge, reset, editor, failed grade) | `frontend/app/components/review-screen.tsx` | `review-screen.test.tsx:1270-1514` | - |
| FSRS interval buckets (9) | backend `INTERVAL_LABELS` via the plan row; `frontend/app/components/review-screen.tsx:100-108` | 8 of 9: `review-screen.test.tsx:1357` (`~1m`/`~10m`/`~1h`/`~1d`) and `:1374` (`~4d`/`~2w`/`~1mo`/`~1y`) | `~4mo` (`fourMonths`) is never rendered in pt-BR. This is minor: it is the same lookup path as the 8 that are proven |
| quiz item kinds (2) | plan row | cloze `lacuna` `review-screen.test.tsx:1351` · free_recall `resposta livre` `:1370` | - |
| study stats card states (loading, error, shown, hidden) | `frontend/app/components/study-heatmap.tsx:547-600` | shown `review-screen.test.tsx:1572-1579` | hidden (`Show stats`, F4 survives) · error (shared `errors` copy; not rendered in pt-BR) |
| heatmap cell activity plural vectors (0, 1, n) | `review.heatmap.activity` | 1 and n `review-screen.test.tsx:1548-1551` | 0. Every empty day's cell label: F6 drops the `=0` branch and survives, rendering `0 revisão · 0 página` |
| anchor statuses (3) | plan row | active `notes-screen.test.tsx:391` · orphaned `:392` | stale (`desatualizado`; F14 survives) |
| page headings (2) | `frontend/app/(app)/review/page.tsx:40`, `frontend/app/(app)/notes/page.tsx:24` | none: no pt-BR test renders either page (`grep -ln "review/page\|notes/page\|ReviewPage\|NotesPage" frontend/tests` finds only `header-rule.test.tsx`, which is English) | `Revisão` and `Notas` page `<h1>`s |
| vendored chat-primitive defaults (`chat.elements` 8, `chat.promptInput` 9, `common.command` 2, carousel 2) | the plan's "Vendored chat primitives" row | Only `promptInput.stop`/`submit` (`ask-panel.test.tsx:1921`, `:1894`) are rendered | all the rest. No learner surface consumes them (`ConversationEmptyState`, `MessageBranch*`, `PromptInputActionAdd*`, `CommandDialog`, `Carousel*`, `SourcesTrigger` have no consumer outside `components/`). F12 and F13 survive. `components/ui/carousel.tsx:126`, `:163` also keep English `aria-roledescription` |
| surfaces that must stay untranslated, batch-3 members (2) | checks.md coverage row | note bodies C41 · sentinel C38 | - (C38's proof is weak, see F18) |

The Tutor panel is part of C37 (AC 34), but its pt-BR proof is in `frontend/tests/teach-panel.test.tsx:1363-1454`, and no C37 proof line names that file. The member is proven, yet running C37's literal commands alone never reaches it. This is the same pattern as batch 2's R2-F2, and `checks.md` is frozen.

## Test policy rows

`checks.md` has no `Test policy` section, so there are no rows to judge.

## Faults injected

Each fault was applied in place, one at a time, by a script that replaces one exact text occurrence, runs only the target test file (`--maxWorkers=1 --minWorkers=1`, usually with the frozen `-t` filter), then restores the file with `git checkout --`. This follows the brief's in-place-and-restore instruction instead of a scratch worktree, because the machine is short on memory. After every group, `git status --porcelain` showed only ` M docker-compose.override.yml`, matching the baseline.

This is more than the five-fault cap, deliberately. The brief asked for the expression-level English that the sensor cannot see to be probed on every migrated surface.

| Mutation | Location | Killed |
| --- | --- | --- |
| F1 editor save -> `{saving ? "Saving…" : t("save")}` | `frontend/app/components/review-screen.tsx:873` | yes - `review-screen > note badge, reset, edit and a failed grade: renders in pt-BR` (no `Salvando…`) |
| F2 interval label -> raw bucket (`~1m`) | `frontend/app/components/review-screen.tsx:786` | yes - `review-screen > card, grades, intervals and summary: renders in pt-BR` |
| F3 month names -> `Intl.DateTimeFormat("en-US", …)` | `frontend/app/components/study-heatmap.tsx:94` | yes - `review-screen > heatmap uses locale names` (`Apr` vs `abr.`) |
| F4 stats toggle -> `{showStats ? t("hide") : "Show stats"}` | `frontend/app/components/study-heatmap.tsx:582` | no - survived `review-screen -t "heatmap uses locale names"`, and survived `home-screen` and `study-heatmap` run whole |
| F5 heatmap group aria-label -> English template literal | `frontend/app/components/study-heatmap.tsx:356` | yes - `review-screen > heatmap uses locale names` |
| F6 pt-BR `review.heatmap.activity` loses both `=0` branches (renders `0 revisão · 0 página`) | `frontend/messages/pt-BR.json` | no - survived `review-screen -t "heatmap uses locale names"` and `study-heatmap` run whole |
| F7 older-page loading -> `{loadingMore ? "Loading…" : t("showOlder")}` | `frontend/app/components/conversation-list.tsx:268` | no - survived `conversation-dock -t "renders in pt-BR"` |
| F8 `{t("showInBook")}` -> `{"Show in book"}` | `frontend/app/components/citations.tsx:259` | no - survived `ask-panel` and `teach-panel` `-t "renders in pt-BR"` |
| F9 note chip -> `` `Your note: ${…}` `` | `frontend/app/components/citations.tsx:135` | no - survived `ask-panel -t "renders in pt-BR"` |
| F10 tutor sentinel turn shows the raw English sentinel | `frontend/app/components/teach-panel.tsx:409` | yes - `teach-panel > start form, composer and tutor chips: renders in pt-BR` |
| F11 card-offer question loses `lang="en"` | `frontend/app/components/teach-panel.tsx:812` | yes - `teach-panel > closed session, card offer and its failure: renders in pt-BR` |
| F12 `CommandDialog` title default -> `"Command Palette"` | `frontend/components/ui/command.tsx:54` | no - survived `vendored-primitives` run whole |
| F13 `PromptInputTextarea` placeholder default -> English | `frontend/components/ai-elements/prompt-input.tsx:1069` | no - survived `ask-panel -t "renders in pt-BR"` |
| F14 pt-BR anchor status `stale {desatualizado}` -> `stale {stale}` | `frontend/messages/pt-BR.json` `notes.anchorStatus` | no - survived `notes-screen` and `note-detail-screen` `-t "renders in pt-BR"` |
| F15 note preview toggle -> `{preview ? t("edit") : "Preview"}` | `frontend/app/components/notes/note-detail-screen.tsx:217` | yes - `note-detail-screen > editor, anchors, backlinks and add-to-review: renders in pt-BR` |
| F16 empty note title falls back to a catalog word | `frontend/app/components/notes/note-detail-screen.tsx:90` | n/a - equivalent for the claim: the fixture title is non-empty and the mutant changes only an empty title. Not counted |
| F16b note body passed through a word substitution (`note` -> `nota`) | `frontend/app/components/notes/note-detail-screen.tsx:91` | yes - `note-detail-screen > user text is never translated` |
| F17 sentinel guard compares the untrimmed text | `frontend/app/components/cited-answer.tsx:127` | yes - `cited-answer > sentinel is never rendered` |
| F18 `NOT_FOUND_SENTINEL` -> `"NOT_FOUND"` (the real token would then render) | `frontend/app/lib/citations.ts:63` | no - survived `cited-answer` run whole. The test imports the constant it should pin |
| F19 stale filter disabled (`.filter(() => false)`) | `frontend/tests/i18n-hardcoded.test.ts:236` | no - survived `i18n-hardcoded -t "a clean file cannot stay pending"`. It is vacuous because the list is empty |
| F20 a clean file put back on `PENDING_MIGRATION` | `frontend/tests/i18n-hardcoded.test.ts:80` | yes - `i18n-hardcoded > a clean file cannot stay pending` names `app/components/review-screen.tsx` |

## Gate

- `npx vitest run --maxWorkers=2 --minWorkers=1` (the whole frontend suite, run once) - exit 0: 91 files and 1039 tests passed, 0 failed. The known `review-screen` flake did not show up in this run.
- The 10 batch-3 files (see Checks) - exit 0: 223 passed, 0 failed.
- `npx tsc --noEmit -p .` - exit 0.
- Backend: not run. This batch changes no backend code (`git diff --stat origin/main..HEAD` touches only `frontend/` and `.specs/`).
- Tree after verification: `git status --porcelain` shows ` M docker-compose.override.yml` (the owner's file, untouched) and this report.

## Ranked gaps

1. **English left on a C37 surface (blocking).** `frontend/app/components/cited-answer.tsx:65` has `aria-label={`Citation ${index}`}`. Every inline citation mark in a cited Ask or Tutor answer is announced as "Citation 1" under pt-BR. There is no catalog key for it. The sensor cannot see a template literal (a limit the ADR documents), and no pt-BR test streams an answer with a `[^n]` marker. Fix: add a `chat.citations` key, and add a pt-BR assertion on the mark's accessible name. - C37
2. **C37 citation members never rendered in pt-BR (blocking).** The note-origin chip and passage title (`frontend/app/components/citations.tsx:135`, `:212-213`), `Open note` (`:246`) and `Show in book` (`:259`) are migrated but unproven, and F8 and F9 survive. The older-page loading label (`frontend/app/components/conversation-list.tsx:268`) is unproven too, and F7 survives. - C37
3. **pt-BR `=0` plural unguarded on a reachable string (blocking).** Each empty heatmap day's accessible name goes through `review.heatmap.activity` at count 0. Dropping the `=0` branches renders `0 revisão · 0 página` and no test notices (F6). The stats card's hidden state (`Show stats`, `frontend/app/components/study-heatmap.tsx:582`) is unproven too (F4). - C39
4. **Anchor badge `stale` unproven (blocking).** `notes.anchorStatus` `stale` is never rendered in pt-BR, so an untranslated value passes (F14). - C40
5. **The sentinel proof pins the code's own constant (blocking).** `frontend/tests/cited-answer.test.tsx:372`, `:378`, `:380` read `NOT_FOUND_SENTINEL` from `app/lib/citations.ts`. A wrong constant renders the real backend token and still passes (F18). The test should spell `"NOT_FOUND_IN_SOURCE"` literally. - C38
6. **The C47 proof is vacuous at HEAD (blocking).** With `PENDING_MIGRATION` empty, the stale-entry assertion cannot fail (F19), and nothing asserts the list is empty. Either test the stale rule over a synthetic pending list and scan result, as C45 and C46 do, or assert `PENDING_MIGRATION` is `[]` for the final batch. - C47
7. **Pages and vendored defaults unproven (non-blocking on its own).** The `review/page.tsx` and `notes/page.tsx` headings, and every vendored chat-primitive default except stop/submit, have no pt-BR render (F12 and F13 survive). The vendored defaults have no learner-visible consumer today. `components/ui/carousel.tsx:126`, `:163` keep English `aria-roledescription` (`carousel`, `slide`). - C37 / plan "Vendored chat primitives" row

## Findings

- **B3-F1 - non-blocking - unrecorded English copy change.** `chat.dockReview.dueCaption` makes the English caption singular for 1 ("card due from this book"); before, it was always "cards due from this book". This is the same kind of fix as the accepted "English turn count" row, but no plan row records it.
- **B3-F2 - non-blocking - numbers outside ICU.** Study totals (`frontend/app/components/study-heatmap.tsx:530`, `:534`), the dock due count (`frontend/app/components/dock-review-panel.tsx:94`) and the review position (`{index + 1}/{queue.length}`) render raw JS numbers, so a pt-BR learner would see `1234` rather than `1.234`. English also shows no separator, so nothing regresses. The ICU-formatted counts (`{x, number}`, `#`) are correct.
- **B3-F3 - non-blocking - test noise.** The `teach-panel` pt-BR tests log `Encountered two children with the same key, m1` (6 times). A fixture reuses a message id across streams.
- **B3-F4 - non-blocking, out of scope (batch 2).** `home.due.count`, `library.quiz.noneSurvived` and `library.quiz.discardFootnote` are pt-BR plurals without an `=0` branch. `home.due.count` would read "0 cartão pendente" if Home ever renders it at 0.
- **B3-F5 - translation quality.** The batch-3 Portuguese is natural Brazilian usage and matches the batch-1/2 voice: `você`, "Tentar novamente", "Ensinar"/"Perguntar", "Conversa"/"Notas"/"Revisão", and "Você não está conectado." Small points, none a defect:
  - "Pronto por hoje" reads a little literal; "Por hoje é só" is the idiomatic Brazilian phrasing.
  - "Esse cartão já está em revisão — promover o mesmo texto de novo nunca o duplica." is a calque of "re-promoting"; "adicionar o mesmo texto de novo não cria duplicata" reads more naturally.
  - Anki's own pt-BR grade label for "Again" is "De novo" rather than "Novamente". The plan row accepted "Novamente", so this is not relitigated.

## Deferred to owner

- `npm run build` and `make lint`'s commit and architecture checks. Skipped for the memory budget, and CI runs them. `tsc --noEmit` ran and is clean.
- A browser walk of the batch-3 surfaces in pt-BR (screen-reader names especially). Skipped by brief.
- Backend tests. This batch changes no backend code.

