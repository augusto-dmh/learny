# Spoiler-Safe Retrieval Validation

**Date**: 2026-09-08
**Spec**: `.specs/features/v5-spoiler-safe-retrieval/spec.md`
**Diff range**: `7063a7d9^..c1eaa1b0` (7063a7d9 adapter, 04c002f1 service+fakes, c1eaa1b0 call sites; docs commit judged out of scope)
**Verifier**: independent sub-agent (author ≠ verifier)

---

## Verdict: PASS ✅

15/15 ACs matched spec-defined outcomes · 5/5 sensor mutants killed · gates green (one known pre-existing failure, not attributable to this feature). Two Minor edge-case coverage notes flagged (see Ranked Gap List) — they do not block the verdict.

---

## Task Completion

| Task | Status  | Notes |
| ---- | ------- | ----- |
| T1   | ✅ Done | Port param + bound in shared scoped CTE, all 8 statement variants, fail-closed warning |
| T2   | ✅ Done | Service resolves position per (user, source); fakes mirror section-order semantics incl. fail-closed |
| T3   | ✅ Done | Turn path (buffered/streamed/opening) + `/retrieve` endpoint request position-respecting retrieval |

---

## Spec-Anchored Acceptance Criteria

Evidence paths relative to `backend/`.

### P1: Ask is spoiler-safe

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| SPOILER-01: turn retrieval with a saved position restricts book-arm evidence to sections at or before the anchor's section, enforced inside the single retrieval statement (scoped CTE), not post-filtering | Bounded query on 3-section corpus with bound in section 2 returns only sections 1–2; identical unbounded query returns the section-3 chunk | `tests/test_retrieval.py:470` — `assert {e.anchor for e in bounded} == {"bio.xhtml#p", "geo.xhtml#o"}`; `tests/test_retrieval.py:471` — `assert "phys.xhtml#q" in {e.anchor for e in unbounded}` (db-gated: the only machinery between call and result is the statement; adapter has no post-filter — `retrieval.py:397-398` maps rows verbatim). Flag engaged on ask turns: `tests/test_application_conversations.py:3667` / `:3686` — `assert retrieve.respect_position_calls == [True]`. Propagation: `tests/test_application_retrieval.py:461-462` — `positions.get_calls == [(owner.id, source.id)]`, `not_past_calls == ["geo.xhtml"]` | ✅ PASS |
| SPOILER-02: bound section + earlier admissible; later inadmissible | Bound at geo → {bio, geo}; bound at first → first only | `tests/test_retrieval.py:470` (see above); `tests/test_retrieval.py:484` — `assert {e.anchor for e in results} == {"bio.xhtml#p"}`; fake mirror `tests/test_application_retrieval.py:604-606` | ✅ PASS |
| SPOILER-03: PDF source takes the same section-order bound; `page_span` plays no part | Seeded page spans OPPOSITE section order: only a section-order predicate admits p1 while excluding p2 | `tests/test_retrieval.py:565-566` — `assert {e.anchor for e in bounded} == {"p1.xhtml"}` / `assert {e.anchor for e in unbounded} == {"p1.xhtml", "p2.xhtml"}` | ✅ PASS |
| SPOILER-04: admissible rows carry unchanged scores and ordering | Both-arm rank-1 hit scores exactly `1/(k+1) + 1/(k+1)`; whole-book-admissible bound yields identical (chunk_id, score) sequence to unbounded | `tests/test_retrieval.py:585` — `assert top.score == pytest.approx(expected)` with `expected = 1.0/(_K+1) + 1.0/(_K+1)`; `tests/test_retrieval.py:500` — `assert [(e.chunk_id, e.score) for e in bounded] == [(e.chunk_id, e.score) for e in baseline]` | ✅ PASS |
| SPOILER-05: no saved position → retrieval exactly as today | Service passes `None` (unfiltered, never empty); explicit `None` ≡ omitted param on real SQL | `tests/test_application_retrieval.py:487` — `assert retrieval.not_past_calls == [None]` with `result is expected`; `tests/test_retrieval.py:651-653` — `assert [(e.chunk_id, e.score, e.anchor) for e in explicit] == [(...) for e in omitted]`; endpoint unbounded: `tests/test_web_retrieval.py:419` | ✅ PASS |
| SPOILER-06: bound derived only from the calling user's own `(user_id, source_id)` row | Another user's row for the same source is never read, never bounds | `tests/test_application_retrieval.py:509-510` — `assert positions.get_calls == [(owner.id, source.id)]`, `assert retrieval.not_past_calls == [None]` (only `other` has a row); per-source SQL: `tests/test_retrieval.py:690-694` — `foreign_anchor == []`, own anchor serves only B's rows | ✅ PASS |

### P1: Teach is spoiler-safe

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| SPOILER-07: scope anchors AND position bound compose (logical AND) | Scope past bound → empty; scope inside bound → exact intersection, via both statement variants and the real service | `tests/test_retrieval.py:612-613` — `assert past_bound == []`, `assert {e.anchor for e in within} == {"bio.xhtml#p"}`; anchored+notes variant `tests/test_retrieval_notes.py:413-414`, `:425-426`; real-service teach turn `tests/test_application_conversations.py:3822-3823` — `port.not_past_calls == ["ch2.xhtml"]` | ✅ PASS |
| SPOILER-08: empty intersection → existing zero-evidence outcome, no bypass | Observed existing outcome: `answer_status="not_found_in_scope"`, empty text/citations/0 evidence, generation never invoked, bound still applied | `tests/test_application_conversations.py:3860-3861` — `assert turn.answer_status == "not_found_in_scope"`, `assert (turn.answer_text, turn.citations, turn.evidence_count) == ("", (), 0)`; `:3863` — `assert generation.calls == []`; `:3867-3868` — `positions.get_calls == [(user.id, source.id)]`, `port.not_past_calls == ["ch2.xhtml"]` (bound genuinely applied, not skipped) | ✅ PASS |
| SPOILER-09: teach-opening turn (query = target title) takes the same bound | Opening turn requests position-respecting retrieval and its query is the target title | `tests/test_application_conversations.py:3711-3712` — `assert retrieve.respect_position_calls == [True]`, `assert retrieve.calls[0]["query"] == conversation.target_title`; real-service opening turn `:3822-3823` | ✅ PASS |

### P1: Citation retrieval is spoiler-safe

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| SPOILER-10: `POST /api/sources/{id}/retrieve` applies the same bound with the same semantics | Same user/query: last-section chunk surfaced before position saved, gone after; bound section + earlier stay reachable; endpoint always requests position-respecting retrieval | `tests/test_web_retrieval.py:432` — `assert {r["anchor"] for r in bounded.json()["results"]} == {"bio.xhtml#p", "geo.xhtml#o"}`; `:419` — `assert "phys.xhtml#q" in {r["anchor"] for r in unbounded.json()["results"]}`; `:392` — `assert position_flags == [True, True]` | ✅ PASS |

### P1: Notes and no-position behavior unchanged

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| SPOILER-11: note arms never restricted by the bound | Notes-included variants: book side bounded, note fuses in regardless | `tests/test_retrieval_notes.py:383-384` — `assert {e.anchor for e in book} == {"bio.xhtml"}`, `assert any(e.origin == "note" and e.note_id == note_id for e in results)`; anchored+notes `:413-414` / `:425-426`; fake mirror `tests/test_application_retrieval.py:633` — `assert bounded == [note]` | ✅ PASS |
| SPOILER-12: `not_past_anchor` absent/None → behaves byte-identically to pre-cycle | Explicit None ≡ omitted on real SQL (identical chunk_id+score+anchor sequences); unbounded statements spliced with `bound_filter=""`; all pre-cycle adapter/service suites untouched and green | `tests/test_retrieval.py:651-653`; construction `app/infrastructure/db/retrieval.py:137-146, 286-297` (unbounded variants format with `bound_filter=""`); pre-cycle suites pass unmodified in the gate run | ✅ PASS |
| SPOILER-13: `respect_reading_position` false → position repo never read | Recording fake proves zero `get` calls even with a saved position; no bound reaches the port | `tests/test_application_retrieval.py:428-429` — `assert positions.get_calls == []`, `assert retrieval.not_past_calls == [None]` | ✅ PASS |

### P2: Stale bound degrades closed

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| SPOILER-14: unmatched bound anchor → empty book evidence + warning naming source and anchor | `results == []`, warning `retrieval.position_bound_unmatched` with `source_id` and `anchor` fields | `tests/test_retrieval.py:634-638` — `assert results == []`; `assert records`; `assert records[0].source_id == str(source.id)`; `assert records[0].anchor == "ghost.xhtml#missing"`; fake mirror `tests/test_application_retrieval.py:615` — `assert _port_search(...) == []` | ✅ PASS |
| SPOILER-15: warning condition fires → note arms unaffected | Under a stale bound all results are note-origin and the note is present | `tests/test_retrieval_notes.py:448-453` — `assert records`; `assert records[0].source_id == str(source.id)`; `assert records[0].anchor == "ghost.xhtml#missing"`; `assert all(e.origin == "note" for e in results)`; `assert any(e.note_id == note_id for e in results)` | ✅ PASS |

**Status**: ✅ 15/15 ACs covered with precise assertions. No AC relies on a vague assertion.

---

## Reverse Check (scope creep)

Every new/modified test maps to a spec AC, listed edge case, or a tasks.md Done-when criterion:

- 27 new test functions → SPOILER-01..15 (table above).
- Fake double tests (`test_fake_retrieval_port_*`, `tests/test_application_retrieval.py:587-633`) → T2 Done-when "fakes reproduce section-order semantics incl. fail-closed" (design.md §Fakes).
- `test_retrieve_evidence_ownership_precedes_any_position_read` (`tests/test_application_retrieval.py:513-539`) → spec Implicit-Requirement sweep, "Auth boundaries" (ownership precedes the position read).
- `tests/eval_runner.py`, `tests/test_application_budget.py` changes are constructor/signature compatibility, not new tests. **0 tests deleted** (diff count: 27 added / 0 removed).

---

## Discrimination Sensor

All mutations injected in scratch state (working tree, never committed), each restored via `git checkout --` before the next; `.specs/` untouched. Sensor depth: P0-grade manual injection (5 mutants — spoiler-safety is a data-integrity path).

| # | Mutation | File:line | Expected killer | Killed? |
| - | -------- | --------- | --------------- | ------- |
| a | Invert bound comparison `cs.position <=` → `cs.position >` | `app/infrastructure/db/retrieval.py:126` (`_POSITION_BOUND_FILTER`) | Boundary tests (SPOILER-02/03/04) | ✅ Killed — 10 failed incl. `test_position_bound_excludes_later_sections`, `test_bound_at_first_section_admits_only_first_section`, `test_pdf_source_bound_uses_section_order_not_page_span`, notes-variant tests |
| b | Drop the bound from ONE notes-included statement variant (`_HYBRID_SQL_ANCHORED_WITH_NOTES_BOUND` formatted with `bound_filter=""`) | `app/infrastructure/db/retrieval.py:293-297` | Variant-matrix test (SPOILER-07/11 anchored+notes) | ✅ Killed — exactly `test_anchored_notes_variant_applies_bound_to_book_arms_only` failed (1 failed, 11 passed) |
| c | Unmatched bound degrades to unfiltered: `COALESCE((subquery), 2147483647)` | `app/infrastructure/db/retrieval.py:125-131` | Fail-closed tests (SPOILER-14/15) | ✅ Killed — `test_unmatched_bound_anchor_yields_zero_book_evidence_and_warns`, `test_stale_bound_leaves_note_arms_unaffected`, `test_bound_resolves_within_the_queried_source` failed |
| d | Service ignores resolved position (`not_past_anchor = None` always, flag branch kept) | `app/application/retrieval.py:186-189` | Service propagation + conversation tests (SPOILER-01/07/08) | ✅ Killed — `test_retrieve_evidence_respects_position_by_forwarding_the_saved_anchor`, `test_teach_scope_at_the_position_still_retrieves_and_answers`, `test_teach_scope_past_the_position_takes_the_honest_not_found_turn` failed |
| e | Endpoint handler omits `respect_reading_position=True` | `app/infrastructure/web/retrieval.py:163-170` | Endpoint tests (SPOILER-10) | ✅ Killed — `test_retrieve_defaults_include_notes_false_and_forwards_explicit_choice` (spy) and `test_retrieve_with_a_saved_position_excludes_later_sections` (outcome) failed |

**Result**: 5/5 killed — the tests discriminate for every invariant they claim to guard. **PASS ✅**

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| Minimum code | ✅ one keyword through one seam; 8 statement constants from 2 templates × 2 filter slots |
| Surgical changes | ✅ app diff limited to ports, SQL adapter, service, composition root, two call sites |
| No scope creep | ✅ eval/quiz paths untouched (eval_runner.py is composition-root wiring only); 0 deleted tests |
| Matches patterns | ✅ recording-fake idiom, db-gated `db_conn` fixture, SPOILER IDs in code comments per repo convention |
| Spec-anchored outcome check | ✅ 15/15 (table above) |
| Per-layer coverage expectation | ✅ adapter 1:1 to SQL ACs incl. every variant; routes happy+edge via endpoint tests; service unit per matrix |
| Every test maps to a requirement | ✅ reverse check above |
| Documented guidelines | ✅ `ruff check` + `ruff format --check` + `check_boundaries.py` clean |

---

## Edge Cases (spec list)

- [x] Anchor = first section → only first-section chunks: `tests/test_retrieval.py:474-484`
- [x] Anchor = last section → whole book admissible, scores/order identical: `tests/test_retrieval.py:487-500`
- [x] Single-section book, bound present → all chunks: `tests/test_retrieval.py:503-514`
- [x] Bound per `(user_id, source_id)`; source A's anchor never bounds source B: `tests/test_retrieval.py:656-694`, `tests/test_application_retrieval.py:490-510`
- [ ] Source with no sections/chunks → **no dedicated test** (Minor note). Behaviorally subsumed: a sectionless source cannot match any anchor, which is the tested unmatched-anchor fail-closed path (`tests/test_retrieval.py:616`), and today's unbounded behavior on a sectionless source is also empty evidence.
- [ ] percent `0.00` → anchor, not percent, defines the bound: **no explicit percent=0.00 test** (Minor note). Structurally guaranteed — the filter reads only the anchor string (`app/application/retrieval.py:186-189` passes `position.anchor`; the SQL never touches `reading_positions`).

---

## Gate Check

- **Backend suite** (DSN `postgresql+psycopg://learny:learny@localhost:5432/learny_test`): **1 failed, 2916 passed, 12 skipped** in 96.75s.
  - Failure: `tests/test_eval_retrieval_metrics.py::TestDeterministicRetrievalMetrics::test_metrics_meet_thresholds` — **known pre-existing** (local recall drift, proven failing on baseline; neither the test nor its subject module is touched by this range — only `tests/eval_runner.py` composition wiring changed). Not attributable to this feature; not a gap.
  - 12 skips: live-provider tiers (OpenAI/Anthropic/docling keys unset) + snapshot-coverage skips — all pre-existing, environmental.
- **`uv run ruff check .`** (backend): All checks passed.
- **`uv run ruff format --check .`** (backend): 314 files already formatted.
- **Frontend type check** (`node_modules/.bin/tsc --noEmit` with nvm node; plain `npx` resolves to the Windows shim in this WSL env): OK.
- **`python3 backend/scripts/check_boundaries.py`**: architecture boundaries clean.
- **Test integrity**: baseline (design doc) 2890 passed / 12 skipped → now 2916 passed / 12 skipped. 27 test functions added, 0 removed, no assertions weakened (the one modified pre-existing test — the endpoint spy — was strengthened with `position_flags == [True, True]`). The +26 vs +27 delta is a ±1 bookkeeping offset in the design-time baseline figure, not a deletion.

---

## Fix Plans

None required — no surviving mutants, no failed ACs, no SPEC_DEVIATION.

---

## Requirement Traceability Update

| Requirement | Previous Status | New Status |
| ----------- | --------------- | ---------- |
| SPOILER-01..06 | Implementing | ✅ Verified |
| SPOILER-07..09 | Implementing | ✅ Verified |
| SPOILER-10 | Implementing | ✅ Verified |
| SPOILER-11..13 | Implementing | ✅ Verified |
| SPOILER-14..15 | Implementing | ✅ Verified |

---

## Ranked Gap List (non-blocking notes)

1. **Minor** — Edge case "source has no sections/chunks" (spec Edge Cases) has no dedicated test. Suggested fix: one db-gated test asserting a bound on a sectionless source returns `[]` (and logs the unmatched-anchor warning). Behaviorally subsumed today by `tests/test_retrieval.py:616`.
2. **Minor** — Edge case "percent reads 0.00 → anchor defines the bound" has no explicit `percent=0.00` fixture. Suggested fix: save a position with `percent=Decimal("0.00")` in an existing bound test. Structurally guaranteed today — the SQL never reads `reading_positions`.

---

## Summary

**Overall**: ✅ Ready

**Spec-anchored check**: 15/15 ACs matched spec outcome · 2 minor edge-case notes flagged
**Sensor**: 5/5 mutations killed
**Gate**: 2916 passed / 12 skipped / 1 known pre-existing failure; ruff check+format, tsc, boundaries all green

**What works**: the section-order bound is enforced inside the shared scoped CTE of every statement variant, composes with teach scope as AND, never touches notes, is resolved only from the calling user's own position row, fails closed on stale anchors with a diagnosable warning, and is inert (byte-identical statements) for every pre-cycle caller. Ask turns (buffered/streamed), the teach-opening turn, and the citation endpoint all request it.

**Next steps**: proceed to the ship-cycle merge gate (rollout decision per AD-346). The two Minor edge-case notes may be folded into a future housekeeping cycle; they do not block.
