# Review triage — `v6-page-unit` (PR #51)

Six review lanes posted 12 inline comments and 1 summary comment. One further finding arrived as an
unposted cross-lane note and is triaged here as F14 — it is the most consequential of the set.

Each finding was judged against the code as it exists, not against the reviewer's authority.
Verdicts: **real** (the defect is genuine) / **false** (misreads the code); actions: **fix** /
**won't fix**, with the reason.

| # | Comment | Source | File:line | Verdict | Action |
|---|---|---|---|---|---|
| F1 | 3650605434 | security | `migrations/versions/0016_reading_volume.py:41` | real | fix |
| F2 | 3650607382 | performance | `frontend/app/components/use-section-progress.ts:49` | real | fix |
| F3 | 3650608618 | architecture | `backend/app/application/reading.py:119` | real | fix |
| F4 | 3650608885 | architecture | `frontend/app/components/chapter-reader.tsx:356` | real | fix |
| F5 | 3650608899 | architecture | `backend/app/core/config.py:246` | real | fix (as assertions, not a constraint) |
| F6 | 3650610228 | tests | `frontend/app/lib/pages.ts:25` | real | fix |
| F7 | 3650610251 | tests | `backend/app/application/reading.py:132` | real | fix |
| F8 | 3650610277 | tests | `backend/tests/test_web_reading.py:490` | real | fix |
| F9 | 3650610461 | tests | `frontend/app/components/use-section-progress.ts:28` | real | fix |
| F10 | 3650610481 | tests | `frontend/tests/study-heatmap.test.tsx:363` | real | fix |
| F11 | 3650610496 | tests | `frontend/tests/study-heatmap.test.tsx:149` | **false** | won't fix |
| F12 | 3650612615 | regression | `frontend/app/lib/pages.ts:24` | real | fix (with F3/F6) |
| F13 | 5079421302 | requirements | — | real, not a change request | won't fix in cycle |
| F14 | *unposted* | regression cross-lane | `backend/app/application/reading.py` save path | real | fix |

---

## F14 — Concurrent saves double-credit the day (the most severe finding)

`SaveReadingPosition.__call__` reads the baseline with a plain `self._positions.get(...)`, computes
`advance`, then issues `record(words_advanced=advance)` as an atomic `+=`. Under READ COMMITTED two
concurrent saves of the same `(user, source)` — two tabs, or a scroll-idle save racing a navigation
save — both observe the *same* prior anchor, both compute the same advance, and both add it. The
position upsert is last-write-wins and stays correct; the counter is inflated, permanently, and
nothing recomputes it.

**Verified in the code**, not taken on trust: the read at `reading.py` has no locking clause, and
`record` is an unconditional increment.

This is exactly the failure mode AD-184 exists to prevent — it reached "durable, uncorrectable
inflation" by a route the decision never considered. That the increment is atomic is what makes it
easy to miss: atomicity of the *write* says nothing about staleness of the *read* it was derived
from.

**Fix:** take the baseline read under a row lock on the save path, so concurrent saves of the same
`(user, source)` serialize. Contention is per user per book — negligible. The lock belongs only on
the write path; `ReadChapter`'s read of the stored position must stay unlocked.

**Sensor required:** two overlapping transactions against a real connection, asserting the counter
reflects one advance rather than two.

## F8 — The atomicity invariant was claimed but only half-sensed

The rejected-save test exercises the 404 path, where *neither* write is attempted. It therefore
passes identically whether the credit shares the request transaction, opens its own connection, or
self-commits — it senses "nothing ran", not "both roll back together".

Accepted without reservation: this is a weakness in a sensor I specified and the Verifier accepted.
The invariant I-PU-6 is real and holds in the code, but the test guarding it does not discriminate.

**Fix:** induce a failure *after* both writes are issued and assert neither persisted, against a
second connection.

## F3 · F6 · F7 · F12 — Page derivation is defined twice and enforced nowhere

Four findings from three lanes converge on one hole. `page_at` (backend) has **zero production
callers** — only `pages_from_words` is wired. Every page number a reader sees comes from the
TypeScript `pageAt`. The two are independent hand-written mirrors, and `frontend/app/lib/pages.ts`
has no test file at all, so the client side of the parity is asserted nowhere.

The twelve-case agreement recorded in `validation.md` was a **one-time manual check**, not an
enduring contract — a fact worth stating plainly, because it was reported upstream as reassurance.
F7 sharpens it: the `(-5, 275)` negative-offset case is asserted on neither side, so `page_at`'s
`max(words_before, 0)` clamp is a surviving mutant.

**Fix:** one shared boundary table, asserted by both suites, including the negative and
non-positive-quantum cases. That converts a point-in-time observation into a standing contract and
gives `pageAt`/`countWords` the consumers F12 notes they lack. `page_at` is kept as the definitional
reference rather than deleted — it is what the parity test pins the client against.

## F1 — `words_advanced` is `int4` fed by a caller-influenced magnitude

Unlike its neighbours, which move by `+1`, this counter's addend size is chosen by the caller via
the anchor, on the one mutation deliberately without a rate limiter (AD-124). Alternating anchors
credits roughly half a book per round trip; ~14k requests overflow `int4` on a 300k-word book.
Postgres then raises `22003` on the upsert, aborting the transaction the position write shares with
it — so position saves on that `(user, day)` row fail for the rest of the day.

Self-inflicted only, no cross-user reach. Accepted as hardening because the migration is still
unreleased, so widening costs one word in two places and nothing else.

## F2 · F9 — Scroll measurement runs per event, not per frame

`measure` performs a `getBoundingClientRect()` and a `setState` on every scroll event, and
`sectionFraction` is read at the top of `ChapterFlow`, so the whole reader tree reconciles each
tick. The 0.001 quantum is a weak brake — about 4px of scroll on a 4000px section. The sibling
`use-receding-chrome.ts` already early-returns below an 8px threshold, so the repo has a precedent
this hook did not follow. On the reading surface this cycle exists to improve, that matters.

**Fix:** coalesce to one measurement per animation frame, cancelling on cleanup, and give the hook
its own test (F9) now that it has behaviour worth isolating.

## F4 · F5 — Smaller architectural corrections

F4: book-global word offsets are derived inside the component, next to the pure `lib/pages.ts`
module that exists for exactly this. Moving them makes the logic directly testable.

F5: the "quantum must be positive" invariant is defended in four places and asserted in none.
**Fixed as assertions, not as a `gt=0` constraint** — no setting in `config.py` uses `Field`
constraints, and adding one would change startup behaviour on bad config, a larger decision than a
review finding should carry. The defensive guards are the shipped contract, so the tests pin the
guards.

## F11 — Grid track literals duplicated instead of compared — **rejected**

The suggestion is to assert the grid tracks against the component's own constants rather than
repeating `15px` / `4px`. Rejected: those literals come from the **driver-approved artifact**, which
is the spec. Comparing the component against itself would make the assertion a tautology that
passes no matter what the values become — precisely the "tests must not mirror the implementation"
failure the execution contract forbids. Duplicating the spec's literals is what gives the test its
discriminating power.

## F13 — Shaded day can read "0 reviews · 0 pages" — **not fixed in this cycle**

Real and correctly identified, but not a defect against the spec: shading derives from
`reviews_count + reading_updates` (I-PU-7) while the readout shows reviews and pages, and pages
floor per day. So a day whose only activity was a 200-word read is shaded yet reports zeroes, and
the window totals are a sum-of-floors that can trail the true figure by up to a page per active day.

Deliberately **not** changed here. The tooltip format is part of the approved artifact, and altering
what a shaded day reports is a product decision for the driver, not one to take quietly at triage.
Carried to the ship report and the RFC-006 retrospective.
