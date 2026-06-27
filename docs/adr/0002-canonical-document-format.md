# ADR-002: Keep A Rich Canonical Document Format And Derive Markdown

- **Date**: 2026-06-27
- **Status**: Accepted
- **Deciders**: Augusto, Codex
- **Tags**: document-processing, ingestion, markdown, epub, pdf

## Context and Problem Statement

Books can arrive as EPUB, PDF, DOCX, HTML, Markdown, or scans. LLMs can consume Markdown well, but Markdown alone loses or weakens important source structure: exact page spans, layout, tables, figures, footnotes, source offsets, and extraction confidence.

## Decision Drivers

- Preserve source provenance for citations and debugging.
- Support multiple source formats without tying the application to one extractor.
- Allow re-chunking and re-indexing without re-processing original uploads.
- Preserve structured book elements such as sections, tables, figures, examples, notes, exercises, and footnotes.

## Considered Options

- Store Markdown as the canonical corpus.
- Store plain text chunks as the canonical corpus.
- Store source files only and rely on provider file search.
- Store rich structured JSON/JSONL plus preserved HTML fragments, then derive Markdown.

## Decision Outcome

Chosen option: **Rich structured JSON/JSONL plus preserved HTML fragments, with Markdown as a derived LLM-facing view**, because it preserves more source semantics while still producing prompt-friendly content.

Use a rich canonical document representation internally, likely structured JSON/JSONL plus preserved HTML fragments. Generate Markdown as a derived view for prompts, embeddings, and human inspection.

Preferred source order:

```text
EPUB / clean HTML > DOCX > tagged PDF > untagged PDF > scanned PDF > plain text
```

### Positive Consequences

- Better future-proofing for citations, re-chunking, and UI rendering.
- Easier support for page references and structured learning elements.
- Better handling of tables, figures, notes, examples, and exercises.

### Negative Consequences

- More ingestion work upfront.
- Need extraction validation for PDF and OCR sources.
- Need schema/versioning discipline for the canonical corpus.

## Pros and Cons of the Options

### Rich structured JSON/JSONL plus preserved HTML fragments ✅ Chosen

- ✅ Preserves provenance, structure, and extraction metadata.
- ✅ Supports multiple derived views: Markdown, embeddings, UI rendering, source previews.
- ✅ Enables re-processing and re-indexing without losing the original logical structure.
- ❌ Requires a deliberate schema and migration/versioning policy.

### Markdown as canonical corpus

- ✅ Easy for humans and LLMs to read.
- ✅ Simple to generate and inspect.
- ❌ Weak for tables, figures, footnotes, page spans, and complex layout.
- ❌ Markdown dialect differences can create ambiguity.

### Plain text chunks as canonical corpus

- ✅ Simple storage and indexing.
- ❌ Loses too much structure for a serious learning product.
- ❌ Poor citation and source navigation experience.

### Provider file search as canonical source

- ✅ Fastest hosted prototype path.
- ❌ Locks important ingestion behavior inside a provider.
- ❌ Makes citation, re-indexing, and multi-provider support harder.

## References

- W3C EPUB 3.3: https://www.w3.org/TR/epub-33/
- WHATWG HTML: https://html.spec.whatwg.org/
- Pandoc manual: https://pandoc.org/MANUAL.html
- PyMuPDF text extraction notes: https://pymupdf.readthedocs.io/en/latest/recipes-text.html
- PyMuPDF4LLM: https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/
