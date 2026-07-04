# Parsing EPUB (edge libraries)

Verified parsing APIs for the two edge libraries Learny may use. Both stay **inside `infrastructure/`** behind the ingestion port (ADR-0009); their types never appear in `domain/` or `application/` signatures.

Neither `docling` nor `ebooklib` is in `backend/pyproject.toml` yet — add the chosen one as a backend dependency with uv before importing it:

```bash
# from backend/
uv add ebooklib      # lower-level structural access
# or
uv add docling       # higher-level parse + Markdown/dict export
```

Ruff config for this repo: line-length 100, target `py313`, rules `E`, `F`, `I`, `UP`, `B`.

## Reading order and structure — the core rule (ADR-0011)

Preserve logical structure; do not flatten. EPUB/clean HTML sits at the top of the preferred source order (ADR-0002), so lean on the package's declared structure:

- **Reading order** comes from the **spine**, which is ordered. Do **not** derive order from the manifest/`get_items()` list, which is unordered.
- **Section paths** come from the **TOC/nav tree**, which maps human chapter/section titles to hrefs.
- **Anchors** come from each document's manifest file name (href) plus in-document `id` fragments (`chapter03.xhtml#sec-2`).

## Option A — ebooklib (lower-level structural access)

Official docs: https://docs.sourcefabric.org/projects/ebooklib/en/latest/tutorial.html — source: https://github.com/aerkalov/ebooklib/blob/master/ebooklib/epub.py

```python
from __future__ import annotations

from io import BytesIO

import ebooklib
from ebooklib import epub

# read_epub accepts a path OR a file-like object, so S3 bytes need no temp file.
# Source: ebooklib tutorial (read_epub).
book = epub.read_epub(BytesIO(source_bytes))

# Book metadata (OPF Dublin Core). get_metadata(namespace, name) -> list.
# Source: ebooklib/epub.py (EpubBook.get_metadata).
title = book.get_metadata("DC", "title")            # e.g. [("A Tale...", {})]
creators = book.get_metadata("DC", "creator")
language = book.get_metadata("DC", "language")

# Table of contents / nav tree -> section paths.
# Source: ebooklib/epub.py (EpubBook.toc).
toc = book.toc                                        # tuple of Link / (Section, [Link...])

# Reading order: iterate the ORDERED spine, resolve each idref to its item.
# Source: ebooklib/epub.py (EpubBook.spine, get_item_with_id).
for idref, _linear in book.spine:
    item = book.get_item_with_id(idref)
    if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
        continue
    href = item.get_name()                            # manifest file name -> anchor base
    fragment_html = item.get_body_content()           # BODY inner HTML -> preserved fragment
    # full_bytes = item.get_content()                 # whole XHTML document if needed
```

Key ebooklib APIs (all confirmed in the source above):

- `epub.read_epub(path_or_filelike)` — parse; accepts a file-like object.
- `book.spine` — **ordered** reading order as `(idref, linear)` pairs.
- `book.toc` — nav/TOC tree for building `section_path`.
- `book.get_item_with_id(idref)` — resolve a spine entry to its manifest item.
- `book.get_items_of_type(ebooklib.ITEM_DOCUMENT)` — filter XHTML chapters (`ITEM_IMAGE` for images); **unordered**, so only use for lookups, not order.
- `item.get_body_content()` — the `<body>` inner HTML: the preserved fragment for ADR-0002.
- `item.get_content()` — the full document bytes.
- `item.get_name()` / `item.get_id()` — manifest file name (anchor basis) / manifest id.

## Option B — Docling (parse + derived views), EPUB-only

Official docs: https://docling-project.github.io/docling/usage/ — API reference: https://docling-project.github.io/docling/reference/document_converter/ — supported formats: https://docling-project.github.io/docling/usage/supported_formats/ (EPUB listed).

```python
from __future__ import annotations

from io import BytesIO

from docling.datamodel.base_models import DocumentStream, InputFormat
from docling.document_converter import DocumentConverter

# Whitelist EPUB only -> enforces ADR-0011 (EPUB-first, others deferred) at the boundary.
# Source: docling reference/document_converter (allowed_formats, InputFormat.EPUB).
converter = DocumentConverter(allowed_formats=[InputFormat.EPUB])

# Feed S3 bytes via a BytesIO-backed DocumentStream — no local filesystem path (ADR-0013).
# Source: docling reference/document_converter (DocumentStream, convert()).
stream = DocumentStream(name="book.epub", stream=BytesIO(source_bytes))
result = converter.convert(stream)                    # -> ConversionResult

doc = result.document                                 # DoclingDocument
structured = doc.export_to_dict()                     # structured record -> canonical corpus
markdown = doc.export_to_markdown()                   # DERIVED view only (ADR-0002)
# result.status / result.errors / result.confidence -> extraction confidence + status
```

Key Docling APIs (all from the reference above):

- `DocumentConverter(allowed_formats=[InputFormat.EPUB], format_options=None)` — constructor; whitelist EPUB.
- `converter.convert(source) -> ConversionResult` — `source` may be `Path | str | DocumentStream | HttpSource`. Use `DocumentStream` for S3 bytes.
- `converter.convert_all(iterable) -> Iterator[ConversionResult]` — batch variant.
- `ConversionResult.document` — the parsed `DoclingDocument`; `.status`, `.errors`, `.confidence`, `.timings` for status/confidence.
- `DoclingDocument.export_to_dict()` — structured dict for the canonical corpus.
- `DoclingDocument.export_to_markdown()` — the derived Markdown view (never canonical).

## Which to use

- Need fine-grained spine/TOC/href control and the raw preserved HTML fragment → ebooklib.
- Want a batteries-included structured export plus a derived Markdown view → Docling with `allowed_formats=[InputFormat.EPUB]`.

Either way, the adapter converts library output into Learny DTOs (see references/ingestion-port-and-worker.md) so `DoclingDocument` / `EpubBook` never leak upward (ADR-0009).
