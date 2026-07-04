# Citations and stable anchors (ADR-0003 / ADR-0011 / ADR-0016)

Citations are a **core invariant, not late polish** (ADR-0003). Every canonical and derived record must be traceable back to an exact passage, so parsing must retain stable per-passage location anchors from the start.

## Required traceability fields per record

Carry these on every `corpus_node` and every derived `corpus_chunk`:

- `chunk_id` / node id — stable primary key (UUID) for the passage.
- `section_path` — the TOC-derived path (e.g. `["Part I", "Chapter 3", "3.2 Foo"]`), so a citation can name where in the book the passage lives.
- `anchor` — the stable in-book location: manifest href plus optional in-document fragment, e.g. `chapter03.xhtml#sec-3-2`.
- `source_object_key` (via the parent `documents` row) — the S3 key of the original EPUB (ADR-0013), so a citation can point back to the exact source file.
- `snippet` — optional short source excerpt for display/verification.
- `page_span` — **nullable**, `NULL` for EPUB. Reserved so future PDF ingestion can attach page ranges without a schema break (ADR-0011).

A citation is only valid if it can be reconstructed from these fields alone. If a derived chunk drops `section_path`/`anchor`, the citation chain breaks — copy them down from the node when deriving chunks.

## Mapping EPUB structure to stable anchors

EPUB gives natural, durable anchors — use them rather than inventing offsets:

- **File-level anchor:** each spine/manifest document has a file name from `item.get_name()` (ebooklib) — e.g. `OEBPS/chapter03.xhtml`. Normalize it once and reuse it as the anchor base.
- **Fragment-level anchor:** in-document `id` attributes on headings/sections (`<h2 id="sec-3-2">`) give sub-passage precision — combine as `href#fragment`.
- **Section path:** walk `book.toc` (ebooklib), a nested tree of `epub.Link` and `epub.Section` nodes (title + href), and map each into the human-readable `section_path`. Match a node's href/fragment against TOC entries to assign its path.
- **Reading order:** the integer `position` comes from the ordered `book.spine`, giving a total order for stitching passages and rendering "next/previous" in teaching.

Keep anchors **stable across re-ingestion**: derive them from the EPUB's own hrefs/ids, not from run-specific counters, so re-processing the same file yields the same anchors and existing citations keep resolving.

## Nullable page-span, concretely

```python
# EPUB path — no pages:
page_span = None

# Future PDF path (NOT implemented here — reserved shape only):
# page_span = {"start_page": 42, "end_page": 43}
```

The column is `JSONB NULL` on both `corpus_nodes` and `corpus_chunks` (see references/canonical-corpus.md). EPUB ingestion always writes `NULL`; do not add PDF page logic in this skill (ADR-0011 defers it).

## Golden fixtures for citation regression (ADR-0016)

MVP evaluation uses **golden fixtures** before adding Ragas or a dashboard. For ingestion, keep a small committed EPUB fixture plus an expected-output snapshot and assert that ingestion reproduces it:

- Expected `section_path`, `anchor`, `position`, and `page_span == None` for a known set of passages.
- A checked-in golden file (JSON/JSONL) that a test diffs the parse against, so structural or anchor regressions fail loudly.
- Run it in CI so a parser or schema change that silently breaks citations is caught before merge.

This makes citation traceability a tested invariant, matching ADR-0003's "citations are core, not polish".

Official references: W3C EPUB 3.3 (package/nav/spine) https://www.w3.org/TR/epub-33/ ; ebooklib tutorial (toc, spine, get_name) https://docs.sourcefabric.org/projects/ebooklib/en/latest/tutorial.html
