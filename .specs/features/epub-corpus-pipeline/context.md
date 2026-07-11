# Context — epub-corpus-pipeline (Cycle 4, TDD Phase 5)

User decisions captured during Specify/Discuss. These are inputs to design.md and are
not re-opened there.

| ID | Gray area | Decision | Rationale |
|---|---|---|---|
| D-1 | EPUB parsing library | **ebooklib** behind the Learny ingestion port; Docling deferred as a possible second adapter when PDF arrives (ADR-0011). | Citation anchors (`href#fragment`), spine order, and TOC come straight from the source file with no mediating document model; pure-Python, deterministic for golden fixtures; ADR-0002's "preserved HTML fragment" is literally `item.get_body_content()`. Cost accepted: we own the TOC walk, block extraction, and Markdown derivation. |
| D-2 | Frontend vertical slice (AD-010) | **Book structure view**: after ingestion succeeds, the sources screen can show book metadata (title, authors) and the TOC as a nested section tree read from the corpus. | Keeps the vertical-slice cadence; a visible TOC is the end-to-end proof that structure preservation worked. |
| D-3 | Re-ingestion semantics | **Atomic replace**: one current corpus per source; each successful run rebuilds and swaps it in a single transaction. A failed rebuild rolls back and leaves the previous corpus intact. No corpus versioning this cycle. | Simplest model satisfying Phase 5; stable IDs come from deterministic anchors, not row identity; nothing references corpus rows yet (Phase 6 rebuilds embeddings on re-ingest anyway). Versioning becomes a future ADR if citation pinning needs it. |
| D-4 | Chunk derivation | **Structure-first chunking**: chunks never cross section boundaries; blocks are packed toward a size cap, splitting only at block boundaries; an oversized single block splits at sentence boundaries. Every chunk carries `section_path` + anchor. | Honors ADR-0002's no-flat-chunks rule; keeps each chunk citable to exactly one section. Accepted cost: variable chunk sizes. |
| D-5 | Test fixtures | **Synthetic minimal EPUBs** committed under `backend/tests/fixtures/`: one well-formed book (nested TOC, anchors, images, footnotes) plus malformed variants (missing TOC, broken spine ref, non-EPUB bytes). Real published books arrive with Phase 9 golden fixtures. | Deterministic, minimal, each fixture isolates one behavior; keeps git light. |
