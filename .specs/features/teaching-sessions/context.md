# Teaching Sessions — Decision Context (Cycle 7)

Auto-decided per learny-ship-cycle Stage 1 (options + recommendation recorded;
no user prompt). Mirrored as AD-030..AD-035 in `.specs/project/STATE.md`.

## D-1 — Target model: one corpus section, by stable anchor (AD-030)

- **Chosen:** `target_anchor` names one `corpus_sections` row of the source; chapters are depth-0 sections, so "chapter or section" is one mechanism. Target snapshot (`anchor`, `section_path`, `title`) is stored on the session.
- **Why:** sections already carry the stable citation identity (`anchor`, `section_path`, AD-018); zero new corpus concepts; the existing structure endpoint (CORP-11) is the picker UI's data source.
- **Why not passage/chunk targets:** no chunk-selection primitive exists in UI or API; chunk ids are deliberately unstable across re-ingestion — anchoring a session to one is a broken-by-design contract.
- **Why not whole-source sessions:** whole-source questioning is Phase-7 Q&A; a session's value is the bounded target. Deferred, not rejected.

## D-2 — Scoped retrieval: anchor-set filter inside the hybrid query (AD-031)

- **Chosen:** the service resolves the target's subtree (target section + descendants, by `section_path` prefix over the structure read model) into a set of section anchors; `RetrievalPort.search` gains an optional `anchors` filter applied in **both** CTE arms (`chunk.anchor = ANY(:anchors)`).
- **Why:** keeps top_k meaningful for narrow targets (the index scans only in-scope chunks); trivial SQL; anchors are already denormalized onto chunks as citation identity.
- **Why not post-filtering whole-source results:** a narrow target would routinely get 0 in-scope rows out of top-k → false not-founds.
- **Why not a jsonb `section_path`-prefix SQL filter:** same semantics, more complex/fragile SQL than `= ANY` over the anchor column.
- **Why not a second retrieval port:** duplicates the RRF query for one optional predicate.

## D-3 — Generation seam: new `TeachingGenerationPort` (AD-032)

- **Chosen:** a dedicated port mirroring AD-024: `model: str` + `generate(*, message, target_section_path, history, evidence) -> GeneratedAnswer`. `history` is a Learny-owned DTO tuple (prior message/response pairs). Default adapter is deterministic (`local-extractive` family), reusing the extractive strategy shared with the Q&A adapter; the cloud LLM adapter remains blocked on the provider ADR.
- **Why:** teaching needs history + target in the contract from day one; retrofitting them onto `AnswerGenerationPort` later would be a breaking port change rippling into Q&A.
- **Why not reusing `AnswerGenerationPort` unchanged:** loses history/target — the defining inputs of a session turn.
- **Why not one merged "generation" port with optional params:** muddies the Q&A contract that already shipped and is verified.

## D-4 — Persistence: sessions + turns + denormalized citation snapshots (AD-033)

- **Chosen:** `teaching_sessions` (id, source_id FK CASCADE, target_anchor, target_section_path jsonb, target_title, created_at, updated_at) → `teaching_turns` (id, session_id FK CASCADE, turn_index, message, answer_status, answer_text, model, evidence_count, created_at; UNIQUE(session_id, turn_index)) → `teaching_turn_citations` (id, turn_id FK CASCADE, rank, chunk_id **plain UUID, no FK**, section_path jsonb, anchor, snippet, score; UNIQUE(turn_id, rank)). Ownership via parent source only (AD-014 pattern). One turn row = message + response. No status column.
- **Why no FK on `chunk_id`:** corpus replace (AD-018) deletes chunk rows on re-ingestion; history citations must survive as snapshots (TDD: historical citations never silently break — TEACH-20).
- **Why one row per exchange (not per-role rows):** matches the API shape exactly; per-role rows buy flexibility (multi-assistant, tool turns) nothing consumes.
- **Why no status column:** no lifecycle op exists this cycle (AD-025 spirit); adding it now is a dead column with an invented vocabulary.

## D-5 — Turn semantics: sync generation, AD-026/027 contract, persist-on-outcome (AD-034)

- **Chosen:** turns generate synchronously in-request (like Q&A). Outcomes: 201 with `answer_status ∈ {answered, not_found_in_source}` (grounding + empty-evidence short-circuit exactly per AD-027, enforced in the application service); 404 missing/non-owned; 409 source-not-ready, target-anchor-unresolvable (post-re-ingest), or turn_index race; 422 bounds; 429 throttle; 502 port failure with **no turn persisted**. `not_found` turns ARE persisted (they're history the user saw). Bounded context: last `LEARNY_TEACHING_HISTORY_TURNS` prior turns.
- **Why:** the whole grounded-answer contract shipped and was verified in Cycle 6 — reusing its semantics verbatim keeps the product consistent and the review surface small.
- **Why not async/queued turns:** a turn is interactive; the ingestion-style job machinery is for batch work (ADR-0014 boundary).
- **Why not dropping not_found turns:** the conversation the user saw must be reconstructable (TEACH-20/state reads).

## D-6 — API surface: TDD trio + additive per-source session list (AD-035)

- **Chosen:** `POST /api/teaching-sessions`, `GET /api/teaching-sessions/{id}`, `POST /api/teaching-sessions/{id}/turns` (TDD contract) **plus** `GET /api/sources/{source_id}/teaching-sessions` (list, newest first, with `turn_count`). Auth on all; CSRF+Origin on POSTs; rate limit on both POSTs reusing the in-process limiter (same KNOWN LIMITATION as questions).
- **Why the additive list:** without it a navigated-away session is unreachable — "session state reads" (TDD Phase 8 goal) is unusable in practice. Additive, owner-scoped through the source parent.
- **Why not localStorage session memory in the frontend:** hides server state, breaks cross-device, unverifiable.

## D-7 — Frontend slice: one Teach screen per source (AD-035)

- **Chosen:** sources list links ready rows to `/sources/{id}/teach`: target picker (from CORP-11 structure endpoint) + previous-sessions list; starting/opening a session shows the conversation view (messages, cited responses with section path + snippet, explicit not-found state, readable 409/422/429/502 states) with a composer. Client module `app/lib/teaching.ts` mirrors `questions.ts`; same-origin proxy unchanged.
- **Why:** restores AD-010 full-slice cadence with the smallest surface that makes sessions real.
- **Why not a global sessions page:** no cross-source consumer story yet.

## Settings introduced

`LEARNY_TEACHING_MESSAGE_MAX_CHARS=2000`, `LEARNY_TEACHING_EVIDENCE_TOP_K=8`,
`LEARNY_TEACHING_HISTORY_TURNS=6` (all server-side; none in the public API).

## Execution notes

- 5 phases > 3 → the tlc per-phase sub-agent offer was auto-accepted (ship-cycle
  Stage 1 auto-decision; same execution model as Cycles 5–6). One worker per
  phase A–E, fresh Verifier after E3.

## Deviations

(none yet)
