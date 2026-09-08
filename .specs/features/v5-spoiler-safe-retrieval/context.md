# Spoiler-Safe Retrieval Context

**Cycle**: `v5-spoiler-safe-retrieval` (RFC-005 Cycle F)
**Decision mode**: ship-cycle auto-decision rule (user unavailable; the AskUserQuestion at
Stage 0 timed out with no answer). Every decision below was auto-decided with the option set,
choice, and rationale recorded here and as an AD row in `.specs/project/STATE.md`.

## D-1 — Filter granularity & predicate (AD-347)

The reading position is stored as `{anchor: canonical section anchor, percent: 0–100}` where
percent = whole-book percent **by section word counts, measured at section entry**
(`percent_at` = `words_before_row / total`, quantized to 2 decimals — `reading.py`). No
in-section offset exists anywhere in the data model.

| Option | Why recommend | Why not |
| --- | --- | --- |
| **A. Section-order comparison** — a chunk is admissible iff its section's document-order index ≤ the bound anchor's section index. Chunks in the bound section itself are always admissible. | **CHOSEN.** Exact and arithmetic-free: the recorded position's native resolution IS the section boundary, so the predicate loses nothing the data knows. Cannot leak via quantization round-trips. One simple predicate in the `scoped` CTE; trivially auditable. | Coarse within the reader's current section: chunks after the reader's in-section eye-line can surface. Unavoidable without new position data (out of scope per spec). |
| B. Word-offset bound reconstructed from percent | Looks finer; reuses the stored percent directly. | The percent was computed at section entry and quantized — reconstructing a word bound from it can only add error in the leak direction; there is no in-section data to gain. More SQL (windowed word sums per chunk) for zero real precision. |
| C. Client-side anchor-list expansion via the existing `anchors` param | Reuses the shipped filter untouched. | Requires enumerating every section up to the position on every retrieval (extra query + hundreds-element arrays); overloads the TEACH-09/AD-031 teaching-scope semantics; muddles "explicit scope" with "derived bound". |

## D-2 — Application scope (AD-348)

| Option | Why recommend | Why not |
| --- | --- | --- |
| **A. Uniform on all three book-retrieval sites** (ask turns, teach turns, `/retrieve` endpoint) whenever a saved position exists; book arms only; notes never filtered. | **CHOSEN.** RFC-005 names ask, teaching, and citation retrieval literally. Uniform = there is no spoiler path through any retrieval surface; one mental model. Quiz/card generation don't use hybrid retrieval (verified in the seam survey), so they're untouched. | A teach conversation scoped to a chapter ahead of the position gets empty evidence — a real UX cost. Accepted: the honest grounded turn exists, and the cost is the RFC's explicit "never surface" promise. Design verifies what tutor-opens scopes to and reports if the product flow contradicts. |
| B. Filter only whole-book retrieval (scope anchors = None); explicit scope overrides the bound | Scoped teach stays useful when the reader deliberately opens an unread chapter. | Scope selection becomes a spoiler bypass — ask with `scope_anchors=[ending-section]` would leak the ending. Contradicts the RFC's "never". |
| C. Filter Ask only; teach/citations opt-in later | Smallest blast radius. | Leaves two of the three RFC-named surfaces leaking; the cycle would not close its own roadmap row. |

## D-3 — Absent / stale position semantics (AD-349)

| Option | Why recommend | Why not |
| --- | --- | --- |
| **A. No saved position → filter inactive; bound anchor unmatched → fail-closed (zero book evidence) + warning log.** | Absent position: a reader who never opened the book has nothing to spoil; filter-everything would brick first-session canned Ask and sample-book ask (shipped activation surfaces). Unmatched anchor: "never surface past" is the promise — an unknown bound must withhold, never silently degrade to unfiltered. | Absent-position-unfiltered reads as lenient, but the product promise is about content past a position the reader *has*; there is no position to violate. Fail-closed can brick Ask for a drifted anchor — accepted: anchors are canonical and stable (ADR-0002/0003), the warning makes it diagnosable, and fail-open would be the exact bug this cycle kills. |
| B. No position → filter everything (strictest) | Literally safest. | Bricks Ask/Teach on unread books — a shipped activation flow (RFC-0007 Bet 5) and the sample book. |
| C. Unmatched anchor → fail-open (unfiltered + warning) | Ask keeps working on drift. | Silently unfiltered retrieval on a broken bound is the spoiler leak with extra steps. |

## Binding prior decisions (must conform)

- **ADR-0006**: hybrid search in one PostgreSQL statement; retrieval stays behind the
  Learny-owned `RetrievalPort` with settings-sourced knobs — the bound is one more in-statement
  filter, not a new component or a post-filter.
- **AD-031 / TEACH-09**: the `anchors` scope filter restricts both book arms via the shared
  `scoped` CTE — the position bound composes with it (AND), never replaces it.
- **ADR-0029 / AD-189 / RFC-0006**: position model (`anchor` + section-entry `percent`) is
  authoritative; this cycle must not change it.
- **Repo idiom**: new capability default-off — every existing caller and eval path is
  behavior-identical unless it explicitly engages the filter (the `cheaper-intelligence`
  "undeclared deployments byte-identical" precedent).
