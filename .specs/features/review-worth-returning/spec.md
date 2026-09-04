# review-worth-returning Specification (RFC-0007 Cycle D / Bet 4)

## Problem Statement

Review is a correct 4-button FSRS grader, but generation can "succeed" with zero cards and no copy, QC accepts stopword clozes and Dead Sea answers, a mis-tap of Again is durable, learning steps never reappear in the session, and a bad auto-card has no flag. A stranger who opens Review today cannot finish a bounded day's work or recover from a wrong grade. RFC-0007 Cycle D is the quality bar people feel on day one.

## Goals

- [ ] Empty or thin decks explain themselves with discard reason codes; succeeded-empty is not silent.
- [ ] Every generated candidate passes deterministic formulation gates (one fact, no stopword clozes, no set dumps) and the deck prompt asks for that bar.
- [ ] Undo is a compensating event; content edits never rewrite scheduling or `review_log`.
- [ ] Grade buttons show bucketed next intervals; FSRS 1m/10m learning steps re-enter the session.
- [ ] Flag hides a card from due without touching schedule; edit from review is content-only.
- [ ] Today's session is bounded; Done-for-today links back into the current book.

---

## Out of Scope

| Feature | Reason |
|---|---|
| MCQ / a second scheduler | ADR-0021; RFC Cycle D out |
| Per-user FSRS optimizer | Volume-gated per ADR-0021; rq08 Cycle 4 |
| LLM card-critique pass | ADR-0021; Memory Machines T1/T2 failure |
| Auto-deck preview before schedule | RQ04 move 5 attractiveness bar; not this letter-cycle |
| Highlight-first as the only door | RQ04 move 6; Generate stays |
| Per-user desired retention slider | rq08 Cycle 4 |
| Opt-in email due digest | Needs `EmailPort` (RFC Cycle F); thaw stays on the record |
| Vacation / pause-for-N-days | rq08 extra; RFC listed bounded session, not vacation |
| New-card throttle vs review-state hold | RFC session cap is the load shape this cycle |
| Concept-extract-then-generate (Savaal-lite) | RQ04 move 8; after gates have a leftover-failure rate |
| Soft `needs_review` tags / pair-collision preference | RQ04 soft gates; hard gates only |
| Changing the 1–4 FSRS scale | Keep the training distribution |
| Typed-answer auto-grade | Self-grade is accepted in ADR-0021 |

---

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
|---|---|---|---|
| Bet 4 cycle count (RFC OQ1) | This RFC letter is **one** ship-cycle PR (honesty + gates + undo/session + flag/edit). Preview and the email digest are later rows, not a fourth split of this list. | Matches Cycles A–C (one RFC letter = one PR). The 3–4 estimate in the RFC is the bet across the arc, not this PR. Undo stays in-cycle because splitting it would ship formulation with no recovery. | auto (AD-303) |
| Email due digest | **Deferred** to Cycle F with `EmailPort`. No preference schema and no sender this PR. | Escalation avoided: a mail provider is Cycle F's lock. The RFC-004 thaw remains authorized; it is not implemented here. | auto (AD-304) |
| Flag representation | `quiz_items.flagged_at TIMESTAMPTZ NULL`, not a `suspended` status. Due = `active AND flagged_at IS NULL AND due <= now`. | Status is owned by corpus reconcile (`active`/`stale`/`orphaned`). A fourth status would fight re-ingest (flagged card flipped back to active, or unflag of an orphaned card dumped into due). Orthogonal flag keeps AD-078. | auto (AD-305) |
| Undo shape | Append-only `review_log` gains `undone_at` plus a **previous scheduling snapshot** on the row. Undo restores that snapshot and stamps `undone_at`. Rows are never deleted. Pre-cycle rows with a NULL snapshot cannot be undone (409). | FSRS is not invertible from the rating alone. Anki-shaped last-grade undo. Matches RFC "compensating event". | auto (AD-306) |
| What "last grade" means | The caller's most recent `review_log` row with `undone_at IS NULL`, across items. | Session Ctrl+Z, not per-card. A later grade on another card is what undoes first. | auto |
| Study-day on undo | Decrement `reviews_count` on the credited local day, floored at 0. Never insert a new `study_days` row from undo. | Heatmap stays honest; AD-153 increment gets a compensating decrement. | auto (AD-307) |
| Formulation language | Cloze stopwords are the **union** of a closed English list and a closed Portuguese list, plus any 1–2 letter answer. | Corpus is EN/PT (ADR-0025). Language-blind English-only QC is the RQ04 caveat; a union is conservative. | auto (AD-308) |
| Where gates apply | Generated candidates only (deck `_ground`, highlight `suggest`, note `suggest`). Author-edited text is not re-gated (AD-138). | Same invariant as note-card accepts. | auto |
| Local adapter | Rewritten to emit formulation-legal fixtures (one-word answer / non-stopword cloze). Offline decks must still produce reviewable items. | Current free-recall is `generic_stem` + `answer_too_long` by construction; leaving it would zero the deterministic suite. | auto (AD-309) |
| Session bound | `LEARNY_REVIEW_SESSION_SIZE` default 20, hard cap 100 (existing `MAX_DUE_LIMIT`). `total_due` remains the uncapped overdue count; the returned `items` page is the session. | rq08 default 20–40; existing due limit is already 20. "Keep going" fetches the next page. No new session table. | auto (AD-310) |
| Requeue window | After a grade, if the new `due` is within `LEARNY_REVIEW_REQUEUE_MINUTES` (default 15) of now, the client inserts the card into the remaining session queue. | Covers FSRS-6 default 1m and 10m steps. Longer dues stay out. | auto (AD-311) |
| Interval labels | Server-computed buckets from a **non-persisted** preview with fuzzing off: `~1m` / `~10m` / `~1h` / `~1d` / `~4d` / `~2w` / `~1mo` / `~4mo` / `~1y`. | Fuzzing makes exact minutes a lie; Anki users grade against a bucket. | auto (AD-312) |
| Space after reveal | Space grades **Good** (3) once the answer is visible. Reveal remains Space before that. | Anki muscle memory; one-line on the existing shortcut hook. | auto |
| New-card hold / vacation | Out. Session cap is the load shape. | RFC Cycle D names a bounded session, not Anki's new/review split. | auto |
| Rate limit / auth | `rate_limit_quiz` + origin + CSRF on undo, flag, and existing review/edit. Missing/non-owned → 404, no disclosure (AD-149). | Same surfaces as grade and `UpdateCard`. | auto |
| Observability | Discard reasons live on the job row the UI already fetches. No new scrape endpoint. | AD-041 | auto |
| Anki export | Flagged cards are omitted the same way non-`active` cards already are. | Export is the learner's chosen deck, not a dump of hidden cards. | auto |

**Open questions:** none — all resolved or logged above.

---

## User Stories

### P1: Empty-deck honesty ⭐ MVP

**User Story**: As a learner, I want a succeeded deck with nothing to review to tell me why, so generation is not a spinner that vanishes.

**Why P1**: The walkthrough already failed this. RFC Cycle D's first bullet. Unblocks seeing filter yield.

**Acceptance Criteria**:

1. (REV-01) WHEN a deck job succeeds THEN the system SHALL persist `discard_reasons` as a JSON object of reason-code → count whose values sum to `discarded_count`.
2. (REV-02) The system SHALL classify each discarded generated candidate with exactly one of: `ungrounded`, `duplicate`, `empty`, `answer_in_question`, `yes_no`, `cloze_stopword`, `cloze_too_wide`, `answer_too_long`, `question_too_long`, `set_dump`, `generic_stem`, `other`.
3. (REV-03) WHEN `generated_count` is 0 and `discarded_count` is 0 and `failed_sections` is 0 THEN the library deck controls SHALL show that the book has no section long enough to quiz (leaf chapter about 200+ characters) and SHALL offer highlighting a passage as the alternative.
4. (REV-04) WHEN `generated_count` is 0 and `discarded_count` is greater than 0 THEN the library deck controls SHALL show that drafts were written but none survived quality checks, including the discarded count.
5. (REV-05) WHEN `generated_count` is at least 1 THEN the library deck controls SHALL show item and due counts, and WHEN `discarded_count` is greater than 0 THEN they SHALL also show a quiet footnote with that discarded count.
6. (REV-06) WHEN `failed_sections` is greater than 0 and `generated_count` is at least 1 THEN the library deck controls SHALL mention the saved count and the failed-section count.
7. (REV-07) The system SHALL keep empty success as job status `succeeded` (no new "empty" status).
8. (REV-08) IF a candidate is discarded THEN the system SHALL NOT persist its question or answer text.

**Independent Test**: succeed a job with each count triple; assert JSONB + library copy; a discarded candidate never appears in `quiz_items`.

### P1: Deterministic formulation gates

**User Story**: As a learner, I want generated cards to be one fact with a short, effortful answer, so the deck is not grounded-looking trivia.

**Why P1**: SuperMemo/Matuschak cheap failures are structural. Same module for every adapter.

**Acceptance Criteria**:

1. (REV-09) WHEN a generated candidate fails a formulation gate THEN the system SHALL discard it with that gate's reason code and SHALL NOT persist it.
2. (REV-10) IF a free-recall candidate's normalized answer is a substring of its question THEN the system SHALL discard it as `answer_in_question`.
3. (REV-11) IF a question matches `^(is|are|do|does|did|can|was|were)\b` or ends in a binary choice THEN the system SHALL discard it as `yes_no`.
4. (REV-12) IF a cloze answer is in the closed EN∪PT function-word list or is 1–2 letters THEN the system SHALL discard it as `cloze_stopword`.
5. (REV-13) IF a cloze answer is more than 8 words or at least 60 percent of the question's words THEN the system SHALL discard it as `cloze_too_wide`.
6. (REV-14) IF a free-recall answer is more than 12 words or more than 120 characters THEN the system SHALL discard it as `answer_too_long`.
7. (REV-15) IF a free-recall question is more than 280 characters, or a cloze question is more than 400, THEN the system SHALL discard it as `question_too_long`.
8. (REV-16) IF an answer has at least 4 comma- or slash- or semicolon-separated items THEN the system SHALL discard it as `set_dump`.
9. (REV-17) IF a free-recall question matches "what does (the )?(passage|section|note|text)" THEN the system SHALL discard it as `generic_stem`.
10. (REV-18) Existing grounding, emptiness, cloze-blank, and embedding-duplicate checks SHALL still run and map to `ungrounded`, `empty`, or `duplicate`.
11. (REV-19) WHERE the text is author-edited (`UpdateCard` or accept-after-edit) the system SHALL NOT apply formulation gates.
12. (REV-20) WHEN the Anthropic section or quote prompt is built THEN it SHALL instruct: one fact per card, short answer, blank the key term not a function word, no lists, no yes/no, answerable without opening the book.
13. (REV-21) The local deterministic adapter SHALL emit only candidates that pass the formulation gates.

**Independent Test**: golden rejects in `quiz_qc`; deck finalize increments the matching reason; local adapter fixtures persist; a PATCHed too-long answer stays.

### P1: Review undo as a compensating event

**User Story**: As a learner, I want to undo the last grade so a mis-tap of Again vs Easy is not a durable stability hit.

**Why P1**: RFC must-be-true: content edits never rewrite scheduling or `review_log`. Undo is the invariant-risk piece.

**Acceptance Criteria**:

1. (REV-22) WHEN the learner undoes the last grade THEN the system SHALL restore that item's scheduling to the snapshot stored on that log row, SHALL set `undone_at` on that row, and SHALL NOT delete the row.
2. (REV-23) IF the caller has no not-yet-undone review, or the latest not-undone row has a NULL previous snapshot, THEN undo SHALL return 409.
3. (REV-24) The system SHALL undo only the caller's most recent not-yet-undone `review_log` row.
4. (REV-25) WHEN undo succeeds THEN the system SHALL decrement `study_days.reviews_count` for the local day that review credited, floored at 0, and SHALL NOT insert a new study-day row.
5. (REV-26) The system SHALL leave `quiz_items` content columns untouched on undo.
6. (REV-27) IF the item is missing or not owned THEN undo SHALL return 404 indistinguishable from not found (AD-149).
7. (REV-28) WHEN a grade is submitted THEN the system SHALL store the pre-grade scheduling snapshot on the new `review_log` row.

**Independent Test**: grade then undo restores due/stability/step byte-identical to pre-grade; log row remains with `undone_at`; second undo 409; heatmap reviews_count drops by one.

### P1: Interval labels and in-session learning-step requeue

**User Story**: As a learner, I want to see the next interval on each grade button and meet the 1-minute and 10-minute learning steps in this sitting, so FSRS behaves as documented.

**Why P1**: A snapshot queue that never re-inserts silently disables FSRS learning.

**Acceptance Criteria**:

1. (REV-29) WHEN a due card is shown THEN each grade button SHALL display a bucketed next-interval label for ratings 1–4 from a server preview that is not persisted.
2. (REV-30) Interval preview SHALL run with FSRS fuzzing off and SHALL bucket to exactly one of `~1m`, `~10m`, `~1h`, `~1d`, `~4d`, `~2w`, `~1mo`, `~4mo`, `~1y`.
3. (REV-31) WHEN a grade's new `due` is within `LEARNY_REVIEW_REQUEUE_MINUTES` (default 15) of now THEN the review UI SHALL insert that card into the remaining session queue with fresh interval labels.
4. (REV-32) WHILE requeued learning-step cards remain in the session the review screen SHALL NOT show Done-for-today; it SHALL say how many cards are still in short-term review.
5. (REV-33) The system SHALL NOT write scheduling or `review_log` for interval preview.

**Independent Test**: queue payload carries four labels; preview does not add log rows; an Again that schedules ~1m reappears before session end; a 4-day due does not.

### P1: Flag and edit on due cards

**User Story**: As a learner, I want to flag a bad card out of the due queue and edit its wording without resetting its schedule, so a leech has an escape.

**Why P1**: Without this, a bad auto-card can only be suffered. RFC content/schedule split.

**Acceptance Criteria**:

1. (REV-34) WHEN the learner flags an owned card THEN the system SHALL set `flagged_at` and SHALL leave scheduling and `review_log` untouched.
2. (REV-35) WHILE `flagged_at` is set the card SHALL be absent from the due queue even if `status` is `active` and `due` is past.
3. (REV-36) WHEN the learner unflags the card THEN the system SHALL clear `flagged_at`; due membership SHALL follow the existing status and due predicates.
4. (REV-37) WHEN the learner edits question and answer from review THEN the system SHALL persist through the existing content-only `UpdateCard` path (id, scheduling, and `review_log` unchanged).
5. (REV-38) IF the item is missing or not owned THEN flag and unflag SHALL return 404 indistinguishable from not found.
6. (REV-39) Anki export SHALL omit flagged cards.

**Independent Test**: flag removes from `GET /reviews/due` with byte-identical scheduling; unflag restores; PATCH text leaves `review_log` count and due unchanged; export GUID list excludes the flagged id.

### P1: Bounded today's session

**User Story**: As a learner, I want a finishable today's session and a Done-for-today that sends me back to the book, so the overdue pile is not the day's job.

**Why P1**: rq08 load shaping; RFC Cycle D third bullet. Home already has a due===0 calm state; it must tell the truth when the session is done but overdue remains.

**Acceptance Criteria**:

1. (REV-40) The due-queue response SHALL include `total_due` as the full overdue active unflagged count and SHALL return at most `LEARNY_REVIEW_SESSION_SIZE` items (default 20, cap 100).
2. (REV-41) WHILE `total_due` is greater than 0, Home SHALL present today's session count (`min(session size, total_due)`) as the Reviews job, not the uncapped pile as the only figure.
3. (REV-42) WHEN the session page is exhausted and `total_due` is still greater than 0 THEN Review SHALL show Done-for-today, a Keep going action that loads the next session page, and a link to the continue-reading book when that target exists.
4. (REV-43) WHEN `total_due` is 0 THEN Home and Review SHALL show the existing all-caught-up copy and SHALL NOT offer Keep going.
5. (REV-44) WHILE the answer is revealed, WHEN the learner presses Space THEN the system SHALL grade Good (rating 3).
6. (REV-45) WHEN a grade from this session can be undone THEN Ctrl/Cmd+Z and `u` SHALL trigger undo; `f` SHALL flag the current card; `e` SHALL open content edit.

**Independent Test**: 25 due → first page 20, Home says 20, after 20 grades Done-for-today with Keep going; after Keep going the next 5; zero due hides Keep going; continue link uses `/api/reading/continue`.

---

## Edge Cases

- IF two tabs grade the same item THEN undo SHALL restore the snapshot on the latest not-undone log row (last writer of the log).
- IF undo races with a second grade on another item THEN the globally latest not-undone row is the one undone.
- IF `study_days.reviews_count` is already 0 THEN undo SHALL leave it at 0.
- IF the continue-reading target is null THEN Done-for-today SHALL omit the book link rather than invent one.
- IF a flagged card is later reconciled to `stale` or `orphaned` THEN it SHALL stay flagged and stay out of due; unflag SHALL not force `active`.
- IF the local adapter's section has no non-stopword maskable term THEN it SHALL emit zero candidates for that section (honest empty), not a stopword cloze.
- WHEN session size is 1 and the graded card requeues THEN the session SHALL continue with that one card rather than show Done-for-today.

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
|---|---|---|---|
| REV-01 | P1: Empty-deck honesty | 2 | In Tasks |
| REV-02 | P1: Empty-deck honesty | 1 | In Tasks |
| REV-03 | P1: Empty-deck honesty | 4 | In Tasks |
| REV-04 | P1: Empty-deck honesty | 4 | In Tasks |
| REV-05 | P1: Empty-deck honesty | 4 | In Tasks |
| REV-06 | P1: Empty-deck honesty | 4 | In Tasks |
| REV-07 | P1: Empty-deck honesty | 2 | In Tasks |
| REV-08 | P1: Empty-deck honesty | 1 | In Tasks |
| REV-09 | P1: Formulation gates | 1 | In Tasks |
| REV-10 | P1: Formulation gates | 1 | In Tasks |
| REV-11 | P1: Formulation gates | 1 | In Tasks |
| REV-12 | P1: Formulation gates | 1 | In Tasks |
| REV-13 | P1: Formulation gates | 1 | In Tasks |
| REV-14 | P1: Formulation gates | 1 | In Tasks |
| REV-15 | P1: Formulation gates | 1 | In Tasks |
| REV-16 | P1: Formulation gates | 1 | In Tasks |
| REV-17 | P1: Formulation gates | 1 | In Tasks |
| REV-18 | P1: Formulation gates | 1 | In Tasks |
| REV-19 | P1: Formulation gates | 2 | In Tasks |
| REV-20 | P1: Formulation gates | 1 | In Tasks |
| REV-21 | P1: Formulation gates | 1 | In Tasks |
| REV-22 | P1: Review undo | 2 | In Tasks |
| REV-23 | P1: Review undo | 2 | In Tasks |
| REV-24 | P1: Review undo | 2 | In Tasks |
| REV-25 | P1: Review undo | 2 | In Tasks |
| REV-26 | P1: Review undo | 2 | In Tasks |
| REV-27 | P1: Review undo | 2 | In Tasks |
| REV-28 | P1: Review undo | 2 | In Tasks |
| REV-29 | P1: Intervals and requeue | 3 | In Tasks |
| REV-30 | P1: Intervals and requeue | 3 | In Tasks |
| REV-31 | P1: Intervals and requeue | 3 | In Tasks |
| REV-32 | P1: Intervals and requeue | 4 | In Tasks |
| REV-33 | P1: Intervals and requeue | 3 | In Tasks |
| REV-34 | P1: Flag and edit | 2 | In Tasks |
| REV-35 | P1: Flag and edit | 2 | In Tasks |
| REV-36 | P1: Flag and edit | 2 | In Tasks |
| REV-37 | P1: Flag and edit | 4 | In Tasks |
| REV-38 | P1: Flag and edit | 2 | In Tasks |
| REV-39 | P1: Flag and edit | 2 | In Tasks |
| REV-40 | P1: Bounded session | 3 | In Tasks |
| REV-41 | P1: Bounded session | 4 | In Tasks |
| REV-42 | P1: Bounded session | 4 | In Tasks |
| REV-43 | P1: Bounded session | 4 | In Tasks |
| REV-44 | P1: Bounded session | 4 | In Tasks |
| REV-45 | P1: Bounded session | 4 | In Tasks |

**Coverage:** 45 total, 45 mapped to tasks, 0 unmapped

---

## Success Criteria

- [ ] A succeeded empty deck states a cause in the library row.
- [ ] A stopword cloze, yes/no, set dump, and generic local-adapter stem never persist from generation.
- [ ] Undo restores pre-grade scheduling and keeps the log row.
- [ ] Editing a card from review does not change `due` or `review_log` length.
- [ ] Flagged cards disappear from due and from Anki export.
- [ ] A 25-card overdue pile presents a 20-card session and a Keep going / back-to-book done state.
