# `v6-workspace-notes` — Tasks

One atomic commit per task. Tests derive from the spec's acceptance criteria and assert
spec-defined outcomes, never the implementation's shape. Gate green before a task is
done. Invariant IDs (I-1…I-10) and traps are in `design.md`.

Gate scoping: run the affected test module per task commit; run the full suite once at
each phase boundary.

---

## Phase A — Provenance (backend)

| # | Task | Satisfies | Sensor must show |
| --- | --- | --- | --- |
| A1 | `quote_exact` becomes optional on the highlight capture (request model + `CaptureHighlight`); with no quote, block binding is skipped and the anchor is section-level | WSN-08, I-2 | An anchor-only capture creates note **and** anchor atomically; a quoted capture is behaviourally unchanged, including its 409 on stale evidence (trap 1: `quote_exact` is NOT NULL — store `""`) |
| A2 | Delete `POST /api/notes` and the now-unreferenced rootless create service | WSN-08, I-1 | No route accepts an anchorless note create; the remaining creation path still works |
| A3 | Pin that pre-existing anchorless notes survive the change | WSN-09, I-3, I-16 | A note with zero anchors still lists, opens, edits, and deletes |

Phase boundary: full backend suite against the recorded baseline.

---

## Phase B — Notes read model (backend)

| # | Task | Satisfies | Sensor must show |
| --- | --- | --- | --- |
| B1 | `list_summaries` accepts `source_id`, returning only notes anchored to it, each with its representative (earliest-created on that source) anchor | WSN-01, WSN-03, I-4, I-7 | A twice-anchored note appears exactly once; order stays `updated_at DESC, id`; the filter composes with `tag` (trap 3: keep the post-select `IN`-query shape, do not join row-per-anchor) |
| B2 | The list service authorizes the source and derives each row's page | WSN-02, WSN-10, WSN-13, WSN-15, I-5, I-6, I-8 | Unowned/unknown `source_id` → 404, indistinguishable; page comes from `page_at`/`words_before_row`; an orphaned anchor yields a row with its quote and **no** page, still present |
| B3 | The endpoint exposes `source_id` and the widened summary on the wire | WSN-01, WSN-02, WSN-11 | The response carries section title, page, quote, and status; unfiltered `/api/notes` is unchanged |

Phase boundary: full backend suite.

---

## Phase C — The dock (frontend)

| # | Task | Satisfies | Sensor must show |
| --- | --- | --- | --- |
| C1 | Introduce `DockTab`, widen the tab strip to four, gate the conversation list to conversation tabs, and accept all four in `?panel=` | I-9 | Switching to Notes/Review leaves ask/teach conversation state untouched; an unknown `?panel=` value falls back exactly as today (trap 4) |
| C2 | The Notes tab lists this book's notes with their passages, its count, and its empty state | WSN-01…WSN-05 | Rows show title, section, page, quote; a twice-anchored note appears once; the empty state renders the spec's verbatim copy; zero renders no badge |
| C3 | The Review tab renders the shipped `ReviewScreen` scoped to the book, with its count and empty state | WSN-06, WSN-07, I-10 | The due count and caption render; a card is gradable with the reader still mounted; zero due shows the empty state and no action; no streak/badge copy anywhere (trap 5: reuse the component, do not fork it) |

Phase boundary: full frontend suite.

---

## Phase D — `/notes` re-scope and retirement (frontend)

| # | Task | Satisfies | Sensor must show |
| --- | --- | --- | --- |
| D1 | `/notes` gains a book filter over the same endpoint; unfiltered stays cross-book | P4 AC 1–3, WSN-10 | Unfiltered lists across books; filtered lists one book's; clearing restores the cross-book list |
| D2 | Retire the title-only creation control and the rootless client function it used; re-point the answer-save fallback onto the anchor-only capture | WSN-08, P3 AC 5 | No title-only control exists; saving an answer whose citation has no quote still produces a note, now anchored (trap 2: re-point the fallback, never delete it — keep the `stale_capture` kind) |

Phase boundary: full frontend suite, then the fresh Opus Verifier.

---

## Coverage

All 16 requirements map to a task: WSN-01/02 (B1–B3, C2), WSN-03 (B1, C2), WSN-04/05 (C2),
WSN-06/07 (C3), WSN-08 (A1, A2, D2), WSN-09 (A3), WSN-10 (B2, D1), WSN-11 (B3),
WSN-12 (A1), WSN-13 (B2), WSN-14 (B1), WSN-15 (B2), WSN-16 (A3).
