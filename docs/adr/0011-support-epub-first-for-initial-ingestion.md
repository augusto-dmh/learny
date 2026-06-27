# ADR-011: Support EPUB First For Initial Ingestion

- **Date**: 2026-06-27
- **Status**: Accepted
- **Deciders**: Augusto, Codex
- **Tags**: architecture, ingestion, epub, document-processing, corpus

## Context and Problem Statement

Learny's first MVP needs document ingestion, cited Q&A, and teaching sessions. Source materials may eventually arrive as EPUB, PDF, DOCX, HTML, Markdown, scans, or plain text, but supporting all formats in the first ingestion implementation would spread effort across parsing problems before the canonical corpus and tutor workflows are proven.

ADR-002 established that Learny should keep a rich canonical document format and derive Markdown from it. The next question is which source format should be supported first.

## Decision Drivers

- The first format should preserve logical book structure well.
- The ingestion implementation should validate the canonical corpus model without immediately fighting the hardest extraction edge cases.
- Chapters, headings, anchors, metadata, and HTML content should be available early.
- The first implementation should keep a path open for PDF support and page-based citations later.
- MVP scope should stay focused on proving ingestion, cited Q&A, and teaching sessions.

## Considered Options

- EPUB first.
- PDF first.
- Markdown/HTML first.
- EPUB plus PDF from day one.

## Decision Outcome

Chosen option: **EPUB first**, because EPUB usually preserves book structure better than PDF and is a stronger starting point for building Learny's canonical corpus, section paths, derived Markdown, retrieval chunks, and teaching flows.

The ingestion direction is:

1. Implement EPUB ingestion first.
2. Extract book metadata, table of contents, chapters, headings, section paths, anchors/hrefs, and HTML fragments where available.
3. Convert EPUB content into Learny's rich canonical corpus representation.
4. Derive Markdown and retrieval chunks from the canonical corpus.
5. Keep source-location fields flexible enough to support future PDF page spans and offsets.
6. Defer PDF ingestion until the EPUB-based corpus and tutor path are working.

### Positive Consequences

- Initial ingestion can focus on logical document structure rather than PDF layout recovery.
- The canonical corpus model can be validated against real book structure.
- Teaching sessions can naturally target chapters, sections, and passages.
- Derived Markdown and retrieval chunks should be easier to generate consistently.
- Future PDF support can reuse the same canonical corpus target.

### Negative Consequences

- Users with only PDF books are not supported in the first ingestion implementation.
- Page-based citation behavior may need additional design once PDF support is added.
- EPUB files can still vary in quality, structure, and metadata consistency.
- The parser must handle EPUB's HTML/CSS/content packaging details.

## Pros and Cons of the Options

### EPUB first ✅ Chosen

- ✅ Best fit for logical book structure among common user book formats.
- ✅ Supports chapters, headings, anchors, metadata, and HTML-derived content.
- ✅ Lets Learny validate the corpus model before tackling PDF extraction complexity.
- ❌ Does not satisfy PDF-first user expectations immediately.

### PDF first

- ✅ Common user expectation.
- ✅ Page references are useful for citations.
- ❌ Harder extraction: reading order, headers, footnotes, tables, multi-column layout, and OCR can be unreliable.
- ❌ Risks spending the first implementation on layout recovery instead of product behavior.

### Markdown/HTML first

- ✅ Easiest technical ingestion path.
- ✅ Useful for testing corpus and retrieval pipelines.
- ❌ Less representative of real book uploads.
- ❌ May avoid important source-packaging and metadata problems the product must eventually solve.

### EPUB plus PDF from day one

- ✅ More useful format coverage immediately.
- ✅ Exercises both logical and page-oriented citation paths.
- ❌ Too much ingestion complexity for the first implementation.
- ❌ Makes it harder to isolate corpus-model issues from extractor-specific issues.

## References

- [ADR-002: Keep A Rich Canonical Document Format And Derive Markdown](0002-canonical-document-format.md)
- [ADR-010: Scope The First MVP To Ingestion, Cited Q&A, And Teaching Sessions](0010-scope-first-mvp-to-ingestion-cited-qa-and-teaching-sessions.md)
- [Learny Research Notes: Preferred Ingestion Direction](../research/2026-06-27/book-intelligence-architecture.md)
