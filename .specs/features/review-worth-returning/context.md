# review-worth-returning Context

**Gathered:** 2026-09-04
**Spec:** `.specs/features/review-worth-returning/spec.md`
**Status:** Ready for design

---

## Feature Boundary

RFC-0007 Cycle D / Bet 4 as one ship-cycle PR: empty-deck honesty with discard reason codes; deterministic formulation gates plus prompt rewrite; review undo as a compensating event; interval labels; in-session learning-step requeue; flag/edit on due cards; bounded today's session with Done-for-today linking to the current book.

Not in this PR: email due digest, auto-deck preview, FSRS optimizer, LLM critique, MCQ, vacation pause, new-card vs review-state hold.

---

## Implementation Decisions

### Cycle sizing (RFC OQ1)

- **Chosen:** one PR for the RFC letter, matching A–C. Remaining Bet 4 attractiveness (preview / highlight-first) and the digest thaw are later rows.
- **Rejected:** four PRs that split undo from formulation (ships unusable cards with no recovery); three PRs that split session UX from undo (both are the same review path).

### Flag vs status

- **Chosen:** `flagged_at` nullable timestamptz, orthogonal to `active|stale|orphaned`.
- **Rejected:** `suspended` status (reconcile owns status; unflag of a drifted card would dump a dead quote into due); reuse `stale` (lies about corpus).

### Undo

- **Chosen:** compensating event on the log row (`undone_at` + previous `SchedulingSnapshot` columns). Caller's globally latest not-undone row. Study-day decrement floored at 0.
- **Rejected:** delete the log row (breaks append-only / ADR-0021); inverse rating (FSRS is not uniquely invertible).

### Formulation

- **Chosen:** hard gates only, in `quiz_qc.py`, generated path only; EN∪PT stopwords; local adapter rewritten to pass the gates; Anthropic section and quote prompts carry the rubric.
- **Rejected:** LLM critique this cycle; English-only stopwords; leaving the local adapter's `generic_stem` fixtures.

### Session and requeue

- **Chosen:** existing due query's `limit` becomes session size (setting, default 20); `total_due` stays uncapped; client reinserts when new due is within 15 minutes; Keep going refetches.
- **Rejected:** a `review_sessions` table; holding New-state cards until reviews clear; email digest.

### Agent's Discretion

- Exact EN/PT stopword membership inside the closed-list idea.
- Bucket boundaries for interval labels (the nine tokens are fixed).
- Flag HTTP shape (`POST /api/quiz-items/{id}/flag` with `{flagged: bool}` is the intended default).
- Undo HTTP shape (`POST /api/reviews/undo` with no body is the intended default).

### Declined / Undiscussed Gray Areas → Assumptions

Ship-cycle auto-decision (Guided pace, no user Discuss). Every row in the spec Assumptions table is the signed-off default. Digest deferred rather than escalated: EmailPort is Cycle F's provider lock and a clear recommendation existed.

---

## Specific References

- RQ04 public-launch slice 1→2→3→4 and the discard-copy table.
- RQ08 Cycle 1 bounded daily review (session cap, Done-for-today, Keep going); Cycle 2 digest parked.
- ADR-0021 content / scheduling / `review_log` split; AD-078 reconcile never touches schedule/log; AD-138 author-edited text not re-gated; AD-149 404 collapse; AD-153 study-day increment in the same transaction as the grade.

---

## Deferred Ideas

- Opt-in due digest (Cycle F / EmailPort).
- Auto-deck as preview (RQ04 move 5).
- Highlight-first default copy (RQ04 move 6).
- Per-user desired retention (rq08 Cycle 4).
- Vacation shift; new-card throttle.
- Soft `needs_review` tags and pair-collision preference.
- Savaal-lite concept extract; LLM critique; optimizer.
