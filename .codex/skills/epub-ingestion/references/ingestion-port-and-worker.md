# Ingestion port, DTOs, adapter, and worker (ADR-0009 / ADR-0013 / ADR-0005)

Ingestion orchestration is **Learny-owned**. ebooklib/Docling are edge libraries behind a Learny port/adapter; their types never appear in `domain/` or `application/` contracts (ADR-0009). Do **not** adopt LlamaIndex/LangGraph/LangChain as the ingestion framework.

Layering follows the existing hexagon (`app/domain` → `app/application` → `app/infrastructure` / `app/worker`).

## 1. Domain DTOs (`app/domain/entities.py`) — pure, library-free

Plain frozen dataclasses, like the existing `User`/`Session`. No `EpubBook`, no `DoclingDocument`.

```python
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True)
class CanonicalNode:
    """One ordered structural passage of a parsed book (ADR-0002).

    Library-agnostic: adapters translate ebooklib/Docling output into this.
    ``page_span`` is None for EPUB, reserved for future PDF (ADR-0011).
    """

    position: int
    section_path: tuple[str, ...]
    heading: str | None
    heading_level: int | None
    anchor: str
    html_fragment: str
    page_span: dict[str, object] | None = None
    extraction_confidence: dict[str, object] | None = None


@dataclass(frozen=True)
class ParsedBook:
    """The full structure-preserving parse result (ADR-0002).

    Returned by the ingestion port; the application service persists it as the
    canonical corpus. Contains no edge-library types (ADR-0009).
    """

    title: str | None
    metadata: dict[str, object]
    nodes: tuple[CanonicalNode, ...] = field(default_factory=tuple)
```

## 2. Domain port (`app/domain/ports.py`) — `Protocol`, no outward imports

Add alongside the existing ports, using `typing.Protocol` + `@runtime_checkable` exactly like `StoragePort`.

```python
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.entities import ParsedBook


@runtime_checkable
class EpubParserPort(Protocol):
    """Structure-preserving EPUB parse port (ADR-0002/0009/0011).

    Takes raw EPUB bytes (sourced from object storage) and returns a
    library-agnostic ParsedBook. Concrete adapters (ebooklib/Docling) live in
    ``app.infrastructure`` and never surface their own types here.
    """

    def parse(self, source_bytes: bytes, *, filename: str) -> ParsedBook:
        """Parse EPUB bytes into the canonical ParsedBook. Raises on non-EPUB input."""
        ...
```

The existing `StoragePort.get_object(key) -> bytes` (already in `app/domain/ports.py`) supplies the bytes — no new storage port needed.

## 3. Infrastructure adapter (`app/infrastructure/ingestion/`) — edge library lives here only

```python
"""EPUB parser adapter (ADR-0009 — edge library behind the ingestion port).

Contains the ONLY imports of the edge parsing library in the codebase. Maps its
output into domain DTOs so no ebooklib/Docling type escapes this module.
"""

from __future__ import annotations

from io import BytesIO

from docling.datamodel.base_models import DocumentStream, InputFormat
from docling.document_converter import DocumentConverter

from app.domain.entities import CanonicalNode, ParsedBook


class DoclingEpubParser:
    """``EpubParserPort`` via Docling, whitelisting EPUB only (ADR-0011)."""

    def __init__(self) -> None:
        # allowed_formats=[InputFormat.EPUB] rejects PDF/other formats at the edge.
        self._converter = DocumentConverter(allowed_formats=[InputFormat.EPUB])

    def parse(self, source_bytes: bytes, *, filename: str) -> ParsedBook:
        stream = DocumentStream(name=filename, stream=BytesIO(source_bytes))
        result = self._converter.convert(stream)
        doc = result.document
        structured = doc.export_to_dict()  # translate -> CanonicalNode(...) tuple
        nodes: tuple[CanonicalNode, ...] = _to_nodes(structured)
        return ParsedBook(title=_title_of(structured), metadata=_meta_of(structured), nodes=nodes)
```

An ebooklib-backed adapter (`EbooklibEpubParser`) is interchangeable — same port, spine/TOC-driven mapping (see references/parse-epub.md). The composition root chooses which to wire.

## 4. Application service (`app/application/`) — orchestrates, persists canonical, derives views

```python
def ingest_epub(*, document_id, source_object_key, storage, parser, corpus_repo) -> None:
    """Ingest one uploaded EPUB into the canonical corpus (ADR-0001/0013).

    Reads bytes from object storage, parses to a ParsedBook, persists the RICH
    canonical corpus, then derives Markdown/chunks FROM it. Ends at a citable
    corpus; retrieval is downstream.
    """
    source_bytes = storage.get_object(source_object_key)          # ADR-0013 (S3, not a path)
    parsed = parser.parse(source_bytes, filename=source_object_key)
    corpus_repo.save_canonical(document_id, parsed)               # structure first (ADR-0002)
    corpus_repo.derive_chunks(document_id)                        # derived views (ADR-0001)
```

## 5. Celery worker (`app/worker/`) — never in an HTTP handler (ADR-0005)

Register the task on the existing `celery_app` in `app/worker/celery_app.py` (Celery `"learny"`, `task_acks_late=True`, prefetch 1). The HTTP handler only enqueues; the worker does the long-running parse. Persist status transitions in Postgres (`documents.status`: `pending → processing → ready`/`failed`) — Postgres is the source of truth, Redis is only transport.

```python
from app.worker.celery_app import celery_app


@celery_app.task(name="ingestion.ingest_epub")
def ingest_epub_task(document_id: str, source_object_key: str) -> None:
    """Worker entrypoint for EPUB ingestion (ADR-0005).

    Builds adapters at the composition root, opens the DB transaction here (the
    Connection boundary lives at the root, matching the repository convention),
    and calls the application service.
    """
    ...  # get_settings(); build storage + parser + corpus_repo; run ingest_epub(...)
```

## Composition root wiring

Instantiate `StoragePort`, `EpubParserPort` (Docling or ebooklib), and the corpus repository at the root, open the DB `Connection`/transaction there (matching `app/infrastructure/db/repositories.py`), and pass them into `ingest_epub`. Swapping parser implementations is a one-line change at the root — nothing in `domain`/`application` moves.

Official references: Docling usage https://docling-project.github.io/docling/usage/ ; Docling DocumentConverter https://docling-project.github.io/docling/reference/document_converter/ ; ebooklib tutorial https://docs.sourcefabric.org/projects/ebooklib/en/latest/tutorial.html ; Celery tasks https://docs.celeryq.dev/en/stable/userguide/tasks.html
