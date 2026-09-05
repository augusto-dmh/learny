# first-session-converts Context

**Gathered:** 2026-09-04
**Spec:** `.specs/features/first-session-converts/spec.md`
**Status:** Ready for design

---

## Feature Boundary

RFC-0007 Cycle E / Bet 5 as one ship-cycle PR: one shared pre-ingested Standard Ebooks *The Art of War*; canned cited question; five-card per-user starter clones; ingest-wait copy; library one Open + overflow; naming Library / Tutor / Download notes; signed-out landing proof; server-side activation events including `first_cited_answer`.

Not in this PR: tours, guest Ask/upload, catalog, third-party analytics, invite gate, spend caps, live generation on `/`.

---

## Implementation Decisions

### Sample ACL (RFC OQ2)

- **Chosen:** `sources.is_sample` boolean. Operator `user_id` NOT NULL, no password. `readable_source` = owner OR sample. `authorized_source` unchanged (owner-only).
- **Rejected:** nullable `user_id` (every query must remember NULL-is-public). System-user-as-only-ACL with no flag (invisible in payloads). Per-signup source clones (pays embeddings again; RFC exclusion).

### Guest Ask

- **Chosen:** authenticated only. Matches RFC conflict 2 (guest after Cycle F).
- **Rejected:** rq07 capped guest Ask on the sample this cycle.

### Starter deck

- **Chosen:** five operator templates; `POST .../quiz/starter` clones to the caller with `initial()` FSRS; idempotent. Not on register. Not on GET.
- **Rejected:** shared `quiz_items` (AD-149 / per-user scheduling). Clone-on-register (couples identity to quiz; five rows for users who never review).

### Activation

- **Chosen:** `activation_events` unique `(user_id, name)`; closed server enum; persist-hook for `first_cited_answer` (Ask + answered + ≥1 citation). Also `account_created`, `sample_opened`, `first_review`. No public GET.
- **Rejected:** `InstrumentRecorder` rings; `study_days`; client POSTed event names; firing on teach-answered.

### Canned question

- **Chosen:** frozen Giles maxim question on the sample payload; Ask highlights it.
- **Rejected:** generate-a-question at request time; generic summarize prompt as the highlight.

### Seed

- **Chosen:** committed SE EPUB + idempotent CLI/Make target that enqueue-ingests once. Tests use a synthetic `is_sample` source.
- **Rejected:** API-boot auto-seed (OpenAI/race). Fetch-from-network in CI.

### Library / Home / landing

- **Chosen:** Open → read; overflow Ask/Tutor/Review; Re-ingest hidden on sample; EPUB+PDF accept; wait banner while a non-sample is processing; names Library/Tutor/Download notes; Home Ask-first when due is 0 and nothing to resume; `/` static proof.
- **Rejected:** keep Ask/Teach/Read triad as primaries; “No sources yet” when the sample exists; live Ask widget on `/`.

### Agent's Discretion

- Operator email local-part (no credential).
- Unique index shape that makes overlapping starter POSTs converge on five clones.
- Exact wait-banner string, as long as it names the sample as usable.
- Landing proof uses a static quote from the canned maxim's chapter, not a screenshot PNG requirement.
- Whether `suggested_question` is a column or a setting keyed off `is_sample` (payload shape is fixed).

### Declined / Undiscussed Gray Areas → Assumptions

Ship-cycle auto-decision (Quick pace; user away). Every row in the spec Assumptions table is the signed-off default. Guest Ask was declined as out of RFC letter E, not escalated: Cycle F is the lock for public Ask.

---

## Specific References

- RFC-0007 Cycle E; conflict 2 (guest after F); conflict 6 (Home Ask-first / returning due).
- rq07: SE *The Art of War* (Giles), canned deception question, `first_cited_answer` on success with citations, no tour, no email wall before aha.
- AD-013 no auto-ingest on upload; AD-016 commit-then-enqueue; AD-037 synthetic goldens vs product sample; AD-041 no scrape endpoint; AD-149 quiz `user_id`; `AuthorizeOwnership` owner-only.

---

## Deferred Ideas

- Capped guest Ask (Cycle F+).
- Catalog titles beyond the one sample.
- Activation dashboard / public GET.
- Email verify; invite codes; spend ledger.
- D7 re-weight if `first_review` predicts return better than `first_cited_answer`.
