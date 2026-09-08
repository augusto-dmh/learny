# Spoiler-Safe Retrieval Design

**Spec**: `.specs/features/v5-spoiler-safe-retrieval/spec.md`
**Context**: `.specs/features/v5-spoiler-safe-retrieval/context.md` (AD-347..AD-349)
**Status**: Approved (ship-cycle auto-decision rule)

---

## Architecture Overview

One optional bound threads through the existing retrieval seam — port → SQL adapter → service →
the three book-retrieval call sites. No new component (ADR-0006); no frontend change; no
migration (both tables already exist).

```mermaid
graph TD
    subgraph "Composition root (dependencies.py)"
        P["ReadingPositionRepository"] --> R
    end
    ASK["PostConversationTurn._retrieve_evidence<br/>conversations.py:832"] -->|"respect_reading_position=True"| R["RetrieveEvidence<br/>application/retrieval.py:147"]
    EP["POST /api/sources/{id}/retrieve<br/>web/retrieval.py:148"] -->|"respect_reading_position=True"| R
    R -->|"position = repo.get(user, source)<br/>None → not_past_anchor=None"| PORT["RetrievalPort.search(<br/>  …, not_past_anchor: str | None)"]
    PORT --> SQL["SqlAlchemyRetrievalRepository.search<br/>infrastructure/db/retrieval.py:265"]
    SQL -->|"scoped CTE + position bound<br/>(book arms, ALL statement variants)"| DB[("corpus_chunks /<br/>corpus_sections")]
```

## The bound (AD-347)

- **Predicate**: a book chunk is admissible iff `section_order_index(chunk.section) ≤
  section_order_index(section_of(bound_anchor))`. The bound section is always admissible; no
  word-offset arithmetic; the stored `percent` is never read by this filter.
- **In-statement**: implemented inside the shared `scoped` CTE of `_HYBRID_SQL_TEMPLATE`, beside
  the existing `{anchor_filter}` (`AND cc.anchor = ANY(:anchors)`) — a bound-aware filter
  fragment applied only when the parameter is present. It composes with the anchors filter
  (logical AND, SPOILER-07).
- **All statement variants**: the repo selects between whole-source and notes-included variants
  (`retrieval.py` ~:303-308). Every variant's **book arms** get the bound; **note arms never do**
  (SPOILER-11). A variant missed is a spoiler leak only db-gated tests can catch — the phase gate
  must run with `LEARNY_TEST_DATABASE_URL` set.
- **Scores untouched** (SPOILER-04): the bound shrinks the `scoped` candidate pool before the two
  arms and RRF fusion run; admissible rows' scores and ordering are computed exactly as today.
- **Stale-anchor warning** (SPOILER-14): an unmatched bound anchor makes the bound subquery NULL,
  which eliminates all book rows (fail-closed comes free from NULL comparison semantics). To make
  it diagnosable, when a bound is supplied the adapter performs one cheap indexed existence check
  (`corpus_sections` by anchor + source) and logs a warning naming the source and anchor when it
  misses. Notes arms are unaffected in both paths (SPOILER-15).

## Port & service signatures

- `RetrievalPort.search` gains one keyword parameter, appended last:
  `not_past_anchor: str | None = None`. Contract doc: "when present, book-arm evidence is
  restricted to sections at or before this canonical section anchor's section, in document
  order; None = unscoped". Protocol docstring references the SPOILER ACs (code-level IDs are the
  repo convention; commit/PR messages stay ID-free).
- `RetrieveEvidence.__call__` gains `respect_reading_position: bool = False`. When true it reads
  the caller's own position via the newly injected `ReadingPositionRepository` (per
  `(user_id, source_id)` — the port's PK, SPOILER-06) and passes `position.anchor` down; a
  missing row passes `None` (SPOILER-05). When false it must not touch the repository at all
  (SPOILER-13). Composition root wires the repository in `get_retrieve_evidence`
  (`dependencies.py:653`).
- Call sites flip exactly one flag: `PostConversationTurn._retrieve_evidence`
  (`conversations.py:832`, serving both buffered and streaming turn paths and the teach-opening
  turn — SPOILER-09 falls out of the shared path) and the `retrieve` endpoint handler
  (`web/retrieval.py:148`, SPOILER-10). Default-off everywhere else keeps eval and every test
  byte-identical (SPOILER-12).

## Fakes (test doubles must mirror semantics)

`FakeRetrievalPort` / `FakeRetrieveEvidence` (`backend/tests/fakes.py`) gain the same parameters
and reproduce the section-order semantics against `FakeCorpusRepository`'s sections (document
order = the fakes' insertion/section order), including fail-closed on an unmatched anchor, so
service- and conversation-level tests exercise the same contract the SQL adapter implements.
Where a test only asserts propagation (service passed the anchor down), a recording fake is
preferred over re-implementing filtering.

## Zero-evidence turn behavior (SPOILER-08)

The design assumes the existing empty-evidence turn path (grounded honest answer, provider
envelope unchanged) already handles "no evidence" — verified during Phase 2; the worker reports
the observed behavior and the test that pins it. No new envelope, error, or status code is
introduced by this cycle.

## Traps (known landmines for the implementer)

1. **`anchors=None` means WHOLE BOOK** — a bound combined with `None` scope must still bound
   (this is the default ask path); do not let `None` scope short-circuit the bound.
2. **Four statement variants, one predicate** — the bound must reach every variant's book arms;
   notes-included variants must keep their note arms bound-free. Test each variant, not just the
   whole-source one.
3. **NULL comparison semantics are load-bearing** — the fail-closed behavior depends on
   `section_pos <= NULL` eliminating rows; write the SQL so the unmatched-anchor case cannot
   degrade to no-filter (e.g., no `COALESCE` gymnastics).
4. **Section order source** — document order comes from the sections table's order column
   (`corpus_sections`, see `metadata.py`); chunks never cross sections, so chunk-level ordering
   is irrelevant to the predicate. Confirm the exact column name from `metadata.py`, not from
   this document.
5. **Canonical anchors only** — `reading_positions.anchor` is already canonical
   (SaveReadingPosition canonicalizes); match it directly against the sections table. No
   `expand_anchors` in the bound path.
6. **Do not perturb knobs** — arm limits, `rrf_k`, `ef_search`, `top_k` clamps are untouched;
   the bound is the only change to the statement's semantics.

## Test strategy (maps to spec ACs)

| Layer | File | Covers |
| --- | --- | --- |
| SQL adapter (db-gated) | `backend/tests/test_retrieval.py`, `test_retrieval_notes.py` | SPOILER-01, 02, 03, 04, 07, 11, 12, 14, 15 — boundary at section granularity across variants, scores stable, notes free, None-bound parity, stale-anchor fail-closed + warning (caplog) |
| Service | `backend/tests/test_application_retrieval.py` | SPOILER-01 (propagation), 05, 06, 13 — flag reads position, absent → None, flag false never touches repo |
| Web endpoint | endpoint test module (follow existing `/retrieve` tests) | SPOILER-10 |
| Fakes + conversation | `backend/tests/fakes.py` + conversation test module | SPOILER-07, 08, 09 — scoped teach intersection, empty-intersection honest turn, opening turn bound |

**Baselines (must grow, never shrink):** backend 2890 passed / 12 skipped; frontend 902 passed.

**Environment (verified this session):** Postgres via
`docker.exe compose -f docker-compose.yml -f docker-compose.override.yml up -d db minio redis`
(both `-f` flags required — the override publishes 5432); run pytest with
`LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test`.
Offline suite runs without it.
