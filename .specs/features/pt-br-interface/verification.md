# pt-br-interface verification

**Verdict**: FAIL
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

## Earlier batches

Batch 2 (its report carries batch 1 under its own `## Earlier batches`), moved unchanged:

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
