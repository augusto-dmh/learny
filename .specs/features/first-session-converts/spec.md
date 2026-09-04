# first-session-converts Specification (RFC-0007 Cycle E / Bet 5)

## Problem Statement

A stranger who creates an account lands on an empty library, waits on ingest with no other book, and never reaches a cited answer. Learny has no shared sample, no canned first question, no starter cards, a three-verb bookshelf, and a nine-line signed-out page. RFC-0007 Cycle E is the first session that converts: one system copy of *The Art of War*, proof on the landing page, and a server-stamped aha.

## Goals

- [ ] Every authenticated user can open one shared, already-ready Standard Ebooks *The Art of War* without cloning embeddings.
- [ ] The sample Ask surface highlights one canned cited question; a successful cited Ask stamps `first_cited_answer` on the server.
- [ ] Five starter cards exist as per-user clones with their own FSRS rows; the template is not a shared schedule.
- [ ] Library shows one Open, overflow verbs, EPUB and PDF upload copy, and ingest-wait honesty that points at the sample.
- [ ] Product names are Library, Tutor, and Download notes.
- [ ] Signed-out `/` shows proof above the fold. Home is Ask-first until due cards exist.

---

## Out of Scope

| Feature | Reason |
|---|---|
| Product tours | RFC Cycle E out |
| Guest Ask / guest upload / try-without-signup | RFC conflict 2: invite-only until Cycle F; no uncapped public Ask |
| Extra catalog titles (Russell, Meditations, …) | RFC Cycle E out: a catalog |
| Third-party analytics SDKs | RFC Cycle E out; events are first-party rows |
| Email verification wall before the aha | rq07; EmailPort is Cycle F |
| Per-user clones of sample embeddings | RFC exclusion; embeddings paid once |
| Invite gate, Turnstile, ToS, account deletion | Cycle F |
| Spend cap / Redis limiter | Cycle F |
| Live generation on the signed-out landing page | That is guest Ask |
| Opt-in due digest | Cycle F / EmailPort (AD-304) |

---

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
|---|---|---|---|
| Sample ownership (RFC OQ2) | `sources.is_sample BOOLEAN NOT NULL DEFAULT false` on one row whose `user_id` is a seed operator with **no password**. Reads: owner OR `is_sample`. Writes (delete, re-ingest, generate deck, upload-as-sample) stay owner-only. | Keeps `user_id` NOT NULL and CASCADE. Nullable owner punches a hole in every query. A second identity model (system user as the only ACL) hides the flag. Per-user source clones pay embeddings again. | auto (AD-316) |
| Read vs write authorize | New `readable_source`: sample OR owner, else `SourceNotFound`. Existing `authorized_source` / `AuthorizeOwnership` stay owner-only. | Widening `AuthorizeOwnership` would let a caller of `StartIngestion` mutate the system book. | auto (AD-317) |
| Guest path | Authenticated only. Unauthenticated sample GET/Ask remain 401. | RFC sequences guest Ask after Cycle F. | auto (AD-320) |
| Starter deck | Five template `quiz_items` owned by the operator. `EnsureStarterDeck` clones content to the caller (`user_id` = caller, new ids, `initial()` FSRS). Idempotent. Scheduling and `review_log` are never shared. | AD-149 requires `quiz_items.user_id`. Shared due rows would mix FSRS across accounts. | auto (AD-318) |
| When to clone | Idempotent `POST /api/sources/{id}/quiz/starter` (sample only). Review and Home call it before showing due. Register does **not** clone. | Avoids coupling identity to quiz and avoids five rows for users who never review. POST-not-GET so a read cannot mint cards. | auto |
| Canned question | Frozen string: `What does Sun Tzu mean by “all warfare is based on deception”?` on the sample source payload (`suggested_question`). Ask highlights it. Not generated at request time. | rq07; generic “summarize this book” is a weak wow. | auto (AD-321) |
| Activation store | Table `activation_events (user_id, name, occurred_at)` UNIQUE `(user_id, name)`. Insert-on-conflict-do-nothing. No public GET. Structured log on first insert. | Not `InstrumentRecorder` (ops). Not `study_days` (adherence). First-* events are once-per-user. | auto (AD-319) |
| `first_cited_answer` | Fire only after a persisted Ask turn with `answer_status=answered` and at least one citation. Teach, failed Ask, not-found, and empty-citation answers do not fire. Stream and JSON share the persist hook. | RFC: server-side, success only. Teach may be answered with no citations. | auto (AD-319) |
| Other events this PR | `account_created` on `RegisterUser`; `sample_opened` on first successful `readable_source` of an `is_sample` source; `first_review` on first successful `SubmitReview`. | Closed set for D7 later. No client-fired names. | auto |
| Sample file | Commit the Standard Ebooks EPUB under `backend/data/samples/`. Idempotent seed command creates the operator, stores the object, inserts the source, enqueues ingestion. Tests use a synthetic `is_sample` source; they do not ingest the 24k-word book. | AD-037 forbids third-party binaries in **goldens**. The product sample is the RFC title. CI stays offline. | auto |
| Seed trigger | Makefile / documented CLI (`seed-sample`). Not API process boot. | Boot-time ingest races workers and can call OpenAI. Ops runs it once per environment. | auto |
| Ingest wait | WHILE the caller has a non-sample source in `processing`, the library SHALL show that the sample is ready to use. Sample still appears in the list when nothing is processing. | RFC: “use the sample while you wait”. Upload still does not auto-start ingest (AD-013). | auto |
| Library honesty | One **Open** (to `/read`). Overflow: Ask, Tutor, Review, Re-ingest (hidden on sample), Download notes. File picker accepts EPUB and PDF. Empty copy is not “No sources yet” when the sample exists. | RFC naming + honesty; PDF already valid on the API. | auto |
| Naming | Sidebar and `/sources` heading: Library. Chat Teach tab: Tutor. Notes export: Download notes. Routes stay `/sources`, `/home`. | RFC naming pass. URLs are not a product name. | auto |
| Home weighting | WHILE `total_due == 0` and there is no continue-reading position, Home SHALL offer Ask on the sample (canned question). WHEN `total_due > 0`, Home SHALL lead with due cards (existing). | RFC conflict 6. | auto |
| Landing | Signed-out `/` shows a static cited-answer proof (quote + locator + *The Art of War*) above the fold, then Create account / Log in. No live model call. | RFC-006 thaw; guest Ask is out. | auto |
| Rate limit / auth | Sample reads use existing source/conversation/quiz auth, CSRF, origin, and limiters. Missing/non-readable → 404, no disclosure. Starter POST on a non-sample owned book → 404. | Same collapse as `GetSource`. | auto |
| Observability | First insert of each event name logs at INFO with `user_id` and `name`. No scrape endpoint. | AD-041 | auto |
| Input bounds | Starter POST has empty body. Event names are a closed server enum, never taken from the client. Suggested question max 500 characters in settings/seed. | Injection/auth dimension | auto |
| Concurrency | Two concurrent `EnsureStarterDeck` calls SHALL leave exactly five cloned items for that user+sample (unique on `(user_id, source_id, content_key)` for cloned origin or an application lock). Two concurrent activation inserts SHALL leave one row. | Unique indexes, not app luck. | auto |
| Lifecycle | Deleting the caller does not delete the sample source (operator-owned). Caller clones CASCADE with the user. Sample delete is operator-only and out of the product UI. | Data lifecycle | auto |
| External seed failure | IF MinIO or enqueue fails THEN the seed command SHALL exit non-zero and SHALL NOT leave a half-ready `is_sample` row marked `ready`. | External-dependency | auto |
| Partial ingest | WHILE the sample source is not `ready`, Ask/Teach/Review on it SHALL 409 like any other unreadied book; the library SHALL still list it with its status. | Failure / state-transition | auto |

**Open questions:** none — all resolved or logged above.

---

## User Stories

### P1: Shared sample book ⭐ MVP

**User Story**: As a new learner, I want a ready copy of *The Art of War* in my library without uploading, so I can reach a cited answer before my own ingest finishes.

**Why P1**: RFC Cycle E first bullet. Removes the empty-library cold start.

**Acceptance Criteria**:

1. (FS-01) The system SHALL store at most one `sources` row with `is_sample = true`.
2. (FS-02) WHEN an authenticated user lists sources THEN the system SHALL include the sample source in addition to that user's own sources.
3. (FS-03) WHEN an authenticated non-owner GET/read/Ask/Teach the sample THEN the system SHALL treat it as readable (not 404) while the source is `ready`.
4. (FS-04) IF a non-owner tries to delete, re-ingest, or start deck generation on the sample THEN the system SHALL respond 404 with no disclosure.
5. (FS-05) IF an unauthenticated caller requests the sample THEN the system SHALL respond 401.
6. (FS-06) The system SHALL NOT insert a per-user copy of the sample's corpus chunks or embeddings.
7. (FS-07) WHEN `GetSource` or list returns the sample THEN the payload SHALL include `is_sample: true` and `suggested_question` equal to the canned string.

**Independent Test**: Two users list sources; both see one shared sample id; embeddings row count for that source_id stays constant after the second user appears.

---

### P1: Canned cited Ask and aha event ⭐ MVP

**User Story**: As a new learner, I want one highlighted question that yields a cited answer, so the first session has a wow that is not “summarize this book”.

**Why P1**: Provisional aha. Server-side `first_cited_answer` is the RFC event.

**Acceptance Criteria**:

1. (FS-08) WHEN the sample Ask surface renders THEN it SHALL highlight the canned suggested question.
2. (FS-09) WHEN an Ask turn persists with `answer_status=answered` and `citations.length >= 1` THEN the system SHALL insert `activation_events` name `first_cited_answer` for that user if absent.
3. (FS-10) IF the persisted Ask turn is failed, not-found, or has zero citations THEN the system SHALL NOT insert `first_cited_answer`.
4. (FS-11) IF the persisted turn mode is teach THEN the system SHALL NOT insert `first_cited_answer`.
5. (FS-12) WHEN `first_cited_answer` is inserted THEN the system SHALL log it once at INFO; a second successful cited Ask SHALL NOT insert a second row.
6. (FS-13) The system SHALL stamp `first_cited_answer` from the persist path shared by JSON and stream completion, never from the browser.

**Independent Test**: Post a cited Ask on the sample; one event row; repeat; still one row. Teach-answered with empty citations: zero `first_cited_answer`.

---

### P1: Five-card starter deck ⭐ MVP

**User Story**: As a new learner, I want five reviewable cards on the sample that are mine to grade, so Review is not an empty queue on day one.

**Why P1**: RFC starter deck. Scheduling must not be shared.

**Acceptance Criteria**:

1. (FS-14) WHEN the caller POSTs starter on the sample and has no clones yet THEN the system SHALL insert exactly five active items owned by the caller with `initial()` scheduling.
2. (FS-15) WHEN the caller POSTs starter again THEN the system SHALL leave the item count and each item's scheduling unchanged.
3. (FS-16) The system SHALL copy question, answer, and content_key from the operator templates and SHALL mint new item ids.
4. (FS-17) IF starter is POSTed for a non-sample source THEN the system SHALL respond 404.
5. (FS-18) Grading a clone SHALL NOT change the operator template's scheduling row.

**Independent Test**: Two users ensure starter; ten items total, five each; grade user A; user B's due and the templates are untouched.

---

### P1: Library honesty, naming, ingest wait ⭐ MVP

**User Story**: As a learner waiting on my upload, I want one Open per book, EPUB and PDF in the picker, and a pointer to the sample, so the shelf does not pretend I have nothing.

**Why P1**: RFC library honesty + naming + ingest-stage transparency.

**Acceptance Criteria**:

1. (FS-19) WHEN a library row is `ready` THEN the primary control SHALL be Open and SHALL navigate to `/sources/{id}/read`.
2. (FS-20) WHEN overflow opens THEN it SHALL offer Ask, Tutor, and Review, and SHALL offer Re-ingest only when `is_sample` is false and the caller is the owner.
3. (FS-21) The library file picker SHALL accept `.epub` and `.pdf`.
4. (FS-22) WHILE a non-sample source is `processing` THEN the library SHALL show copy that the sample can be used while waiting.
5. (FS-23) WHEN the sample is in the list THEN the library SHALL NOT show “No sources yet.”
6. (FS-24) The sidebar and the `/sources` heading SHALL read Library.
7. (FS-25) The Chat mode that was labeled Teach SHALL read Tutor.
8. (FS-26) The notes vault control SHALL read Download notes.

**Independent Test**: Render library with sample + processing upload; Open present; wait copy present; picker accept includes pdf; Teach string absent from the chat tab.

---

### P1: Landing proof and Home Ask-first ⭐ MVP

**User Story**: As a stranger on `/`, I want proof of a cited answer before I register, and as a new account I want Home to send me to Ask on the sample until I have due cards.

**Why P1**: RFC landing thaw + Home weighting.

**Acceptance Criteria**:

1. (FS-27) WHEN an unauthenticated visitor opens `/` THEN the page SHALL show a cited-answer proof (passage quote, citation locator, *The Art of War*) above Create account and Log in, without calling a generation provider.
2. (FS-28) WHEN `RegisterUser` succeeds THEN the system SHALL insert `activation_events` name `account_created` for that user if absent.
3. (FS-29) WHEN an authenticated user first successfully reads the sample via `readable_source` THEN the system SHALL insert `sample_opened` if absent.
4. (FS-30) WHILE Home has `total_due = 0` and no continue-reading position THEN Home SHALL offer Ask on the sample (not only “Pick a book”).
5. (FS-31) WHEN Home has `total_due > 0` THEN Home SHALL lead with the due-session card (existing behavior).
6. (FS-32) WHEN `SubmitReview` succeeds for the first time THEN the system SHALL insert `first_review` if absent.

**Independent Test**: Render `/` signed-out with the proof strings. Home with sample and zero due shows Ask; Home with due > 0 still shows the due card.

---

## Edge Cases

- IF two `EnsureStarterDeck` requests overlap THEN the system SHALL still end with five clones (unique constraint or equivalent), not ten.
- IF the sample source exists but status is not `ready` THEN Ask/Teach/Review SHALL 409 and the library SHALL show the status badge.
- IF seed enqueue fails THEN no `is_sample` row SHALL be `ready`.
- IF a client sends an activation name in a body THEN the system SHALL ignore it (no such route).
- WHEN the operator user is listed in `users` THEN login with that email SHALL fail like any unknown password (no credential).

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
|---|---|---|---|
| FS-01 | P1: Shared sample | T1, T2 | Implemented |
| FS-02 | P1: Shared sample | T3 | Implemented |
| FS-03 | P1: Shared sample | T4 | Implemented |
| FS-04 | P1: Shared sample | T4 | Implemented |
| FS-05 | P1: Shared sample | T5 | Implemented |
| FS-06 | P1: Shared sample | T10 | In Tasks |
| FS-07 | P1: Shared sample | T5 | Implemented |
| FS-08 | P1: Canned Ask | T15 | In Tasks |
| FS-09 | P1: Canned Ask | T9 | In Tasks |
| FS-10 | P1: Canned Ask | T9 | In Tasks |
| FS-11 | P1: Canned Ask | T9 | In Tasks |
| FS-12 | P1: Canned Ask | T1, T3, T9 | In Tasks |
| FS-13 | P1: Canned Ask | T9 | In Tasks |
| FS-14 | P1: Starter deck | T6 | In Tasks |
| FS-15 | P1: Starter deck | T6 | In Tasks |
| FS-16 | P1: Starter deck | T6 | In Tasks |
| FS-17 | P1: Starter deck | T7 | In Tasks |
| FS-18 | P1: Starter deck | T6 | In Tasks |
| FS-19 | P1: Library | T11 | In Tasks |
| FS-20 | P1: Library | T11 | In Tasks |
| FS-21 | P1: Library | T11 | In Tasks |
| FS-22 | P1: Library | T11 | In Tasks |
| FS-23 | P1: Library | T11 | In Tasks |
| FS-24 | P1: Library | T12 | In Tasks |
| FS-25 | P1: Library | T11 | In Tasks |
| FS-26 | P1: Library | T13 | In Tasks |
| FS-27 | P1: Landing / Home | T16 | In Tasks |
| FS-28 | P1: Landing / Home | T8 | In Tasks |
| FS-29 | P1: Landing / Home | T4 | Implemented |
| FS-30 | P1: Landing / Home | T14 | In Tasks |
| FS-31 | P1: Landing / Home | T14 | In Tasks |
| FS-32 | P1: Landing / Home | T10 | In Tasks |

**Coverage:** 32 total, 32 mapped to tasks, 0 unmapped.

---

## Success Criteria

- [ ] Two accounts see one sample `source_id`; chunk embeddings are not duplicated.
- [ ] A cited sample Ask writes exactly one `first_cited_answer`; a failed Ask writes none.
- [ ] Starter POST is idempotent; grades are per-user.
- [ ] Library Open / overflow / PDF / wait copy / Library-Tutor-Download notes pass in vitest.
- [ ] Signed-out `/` shows proof with no provider call; Home Ask-first when due is 0.
