# v4-capture-pipeline — Review Triage

PR #39. Six review lanes (Security, Requirements, Test Coverage, Architecture, Regression,
Performance) produced **10 findings**: 9 inline + 1 PR-level requirements report.

Verdict counts: **8 real / 2 known-and-recorded**, of which **8 fixed**, **2 won't-fix with
rationale**. No finding was rejected as false — this review found real defects, including two
that the Verifier's mutation sensor structurally could not reach (both live on branches no test
executes, so there was nothing to mutate).

| # | Lane | Location | Finding | Verdict | Action |
|---|---|---|---|---|---|
| 1 | regression + tests | `application/cards.py:279,284` | `AcceptCard`: when `upsert` returns `False` and the re-read returns `None`, control falls through to `create_scheduling(item.id)` for a row never inserted — FK violation → 500, and returns `created=True` (201) for a card that does not exist | **REAL — the worst finding** | FIXED |
| 2 | architecture | `application/cards.py:338` | `UpdateCard` recomputes `content_key` with no guard against `uq_quiz_items_highlight_anchor_key`; rewording one card into a sibling's exact text raises an unhandled `IntegrityError` → 500 instead of the documented contract | **REAL** | FIXED |
| 3 | regression | `components/chapter-reader.tsx:495` | `handleCapture` ignores `cardAnchorId`, so Create card followed by Highlight (or bare `h`) persists a second note + anchor for the identical passage | **REAL** | FIXED |
| 4 | performance | `web/dependencies.py:701` | `get_suggest_cards`/`get_accept_card` build a fresh Anthropic/OpenAI client per request — new httpx pool + TLS handshake on the latency-critical popover path, and a leaked pool. `get_answer_generation` in the same file already solves this with `@lru_cache` | **REAL** | FIXED |
| 5 | architecture | `infrastructure/quiz/anthropic.py:214` | The foreground `messages.create` runs on the shared threadpool over a client with no `timeout=`/`max_retries=` → SDK default 600 s. `rate_limit_quiz` caps rate, not concurrency | **REAL** | FIXED |
| 6 | tests | `components/chapter-reader.tsx:428` | Nothing proves a new selection resets `cardAnchorId`/`suggestions`; deleting the reset would silently generate cards for the previous passage | **REAL (missing sensor)** | FIXED |
| 7 | tests | `db/repositories.py:1214` | The third `upsert` branch (highlight row with a null anchor → plain insert) is documented but has no DB-level test | **REAL (missing sensor)** | FIXED |
| 8 | requirements | `spec.md`, `tasks.md` | Traceability table ships stale — all 36 rows `Pending`, "0 mapped to tasks yet", goals unchecked, contradicting `validation.md` in the same diff; `tasks.md` D1 still specifies the dropped `updateCard` | **REAL** | FIXED |
| 9 | requirements | CAP-21 | Jump lands at *section* granularity, so two highlights in one section scroll identically | **REAL but recorded** | WON'T FIX |
| 10 | requirements + architecture | CAP-18 / `web/cards.py:243` | The rail sources only anchored highlights, so an unanchored note never appears; and `PATCH /api/quiz-items/{id}` ships with no consumer | **REAL but recorded** | WON'T FIX |

## Why the two won't-fixes are not evasions

**#9 (section-granular jump).** CAP-21 says "scroll to it and flash it", and the shipped
behaviour scrolls to the containing section. For a chapter with two highlights in one section
those two jumps are indistinguishable. Fixing it properly means anchoring on the painted
`<mark>` node rather than the section id, which is a change to the shared `handleShowInBook`
path that citations also use — a behaviour change to a surface verified in the previous cycle,
made late in this one, with no way to sense the visual result in jsdom. The test is honestly
titled "scrolls to and flashes **the section**" rather than overclaiming. Recorded for the
polish cycle, where the reader is being re-examined anyway.

**#10 (rail scope + unconsumed route).** Two halves of one accepted decision. CAP-A7 scoped the
rail to the loaded chapter's *annotations on the page*, and every rail entry needs an anchor to
be jumpable — an unanchored note has no position in the text to sit beside. Including them
would mean inventing a placement rule this cycle did not design. The `PATCH` route is CAP-A11:
its browser client was deliberately deleted as dead code, the route stays as the contract the
next cycle consumes, and finding #2 above hardens it rather than leaving it soft. Both are
recorded in the spec rather than silently dropped.

## What this review caught that verification could not

Findings #1 and #2 are both unhandled paths created by the same design decision — the second
partial unique index (`uq_quiz_items_highlight_anchor_key`) introduced for idempotent
re-accept. The index was right; only one of the two write paths that can violate it was
defended. A discrimination sensor mutates code that tests already execute, so neither branch
was reachable by it: one needs a lost write race, the other a sibling-text collision, and no
test drove either. Two independent lanes each found one half by reading for consequences rather
than by running anything.

The honest lesson: mutation testing proves the tests you have are sensitive. It says nothing
about the branches you never wrote a test for. Those need someone reasoning about what the code
can do, not what it currently does.
