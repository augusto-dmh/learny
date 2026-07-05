---
name: epub-ingestion
description: Structure-preserving EPUB ingestion into Learny's canonical corpus — parse EPUB while preserving headings, sections, reading order, and stable location anchors, then derive Markdown and retrieval chunks from the canonical corpus so citations and teaching reference exact passages. Use when ingesting or parsing an EPUB/e-book, building the canonical document corpus, extracting book metadata / table of contents / chapters / section paths / anchors/hrefs, wiring an ebooklib or Docling ingestion adapter, or feeding S3 source bytes into a Celery ingestion task. Not for PDF or other formats (deferred, ADR-0011), not for flat whole-book chunking (ADR-0002 requires preserved structure); ebooklib and Docling stay behind a Learny ingestion port as edge adapters, never the core framework (ADR-0009).
---

# EPUB Ingestion

Turn an uploaded EPUB into Learny's rich, citable canonical corpus — structured records plus preserved HTML fragments — from which Markdown and retrieval chunks are derived.

## Consistency First

Before applying any generic default, match the patterns already in the Learny backend at `backend/app/` (hexagonal: `domain/` → `application/` → `infrastructure/` → `worker/`). Concretely:

- Ports are `typing.Protocol` + `@runtime_checkable` in `app/domain/ports.py`; domain has **no** outward imports (see `app/domain/entities.py`, `app/domain/ports.py`).
- Persistence is **SQLAlchemy 2.x Core** `Table`/`MetaData` with the shared `NAMING_CONVENTION`, not ORM models (see `app/infrastructure/db/metadata.py`). Repositories take a caller-provided `Connection`; the transaction boundary lives at the composition root (see `app/infrastructure/db/repositories.py`).
- Every module starts with `from __future__ import annotations`; docstrings cite the governing ADR/design section.
- Settings come from `app.core.config.get_settings()` (lru_cache, `env_prefix="LEARNY_"`).
- Ingestion runs in `app/worker/celery_app.py` (Celery `"learny"`, `task_acks_late=True`, prefetch 1) — never in an HTTP handler.
- Source bytes are read through the existing `StoragePort.get_object(key) -> bytes` in `app/domain/ports.py`.

Mirror these exactly; do not introduce a new persistence, config, or wiring style for ingestion.

## Quick Reference

- Parse EPUB behind a Learny-owned ingestion port; ebooklib/Docling are edge adapters in `infrastructure/`, never the core framework, and their types (`EpubBook`, `EpubHtml`, `DoclingDocument`, `ConversionResult`) never cross into `domain/` or `application/` contracts (ADR-0009); see references/ingestion-port-and-worker.md.
- Preserve reading order and structure: drive the canonical build from `book.spine` (ordered) plus `book.toc` for section paths — not the unordered `get_items()` list — and map headings, `section_path`, and anchors/hrefs per passage (ADR-0011); see references/parse-epub.md.
- Restrict Docling to EPUB only with `DocumentConverter(allowed_formats=[InputFormat.EPUB])`; PDF and every other format are deferred (ADR-0011); see references/parse-epub.md.
- Build the **rich canonical corpus first** (structured records + preserved HTML fragments) and **derive** Markdown/retrieval chunks from it; never store flat-chunks-only (ADR-0002/0001); see references/canonical-corpus.md.
- Read source bytes from the existing `StoragePort` (S3) and hand the parser a `BytesIO`-backed `DocumentStream` / file-like object; PostgreSQL owns object keys, ownership, and ingestion status — never a local path or DB blob (ADR-0013); see references/ingestion-port-and-worker.md.
- Carry citation anchors on every derived record: `chunk_id`, `section_path`, source object key, optional snippet, and a **nullable** `page_span` field reserved for future PDF (ADR-0003/0011); see references/citations-and-anchors.md.
- Run ingestion in the Celery worker (`app/worker`), never inside HTTP request handlers, and persist status transitions in Postgres — Postgres is the source of truth, Redis is only transport (ADR-0005); register the task on the existing `celery_app` in `app/worker/celery_app.py`, which is wired but currently has no tasks; see references/ingestion-port-and-worker.md.
- Match Learny conventions before generic defaults: SQLAlchemy Core `Table` metadata with the shared `NAMING_CONVENTION`, `Connection`-per-repository, `Protocol` ports, `get_settings()`, `from __future__ import annotations`, ADR-citing docstrings; see references/canonical-corpus.md.

## When to apply

- Implementing or reviewing EPUB parsing into the canonical corpus.
- Extracting book metadata, table of contents, chapters, headings, section paths, anchors/hrefs, or preserved HTML fragments.
- Wiring an ebooklib or Docling adapter behind a Learny ingestion port.
- Adding the Celery ingestion task or its Postgres status/corpus tables.
- Deriving Markdown or retrieval chunks **from** an already-built canonical corpus.

## When NOT to apply

- PDF, DOCX, HTML, Markdown, scans, or plain-text ingestion — deferred (ADR-0011). Do not add format handling here.
- Building a flat "chunk the whole book" pipeline that skips structure — forbidden (ADR-0002).
- Making ebooklib/Docling/LlamaIndex/LangGraph the core orchestration framework — forbidden (ADR-0009). Edge libraries solve a concrete parsing problem only.
- Downstream retrieval, embedding, or answer generation — this skill ends at a durable, structured, citable corpus (ADR-0001).

## References

- references/parse-epub.md — verified ebooklib and Docling parsing APIs, reading-order + anchor/section-path extraction.
- references/canonical-corpus.md — ADR-0002 canonical schema as SQLAlchemy Core tables; no-flat-chunks rule; schema versioning.
- references/ingestion-port-and-worker.md — the Learny ingestion port, DTOs, edge adapter, StoragePort-fed bytes, Celery task, composition-root wiring.
- references/citations-and-anchors.md — ADR-0003 traceability fields, EPUB href→anchor mapping, golden-fixture regression.

Source: Learny-authored project-local skill encoding ADR-0001, ADR-0002, ADR-0003, ADR-0005, ADR-0009, ADR-0011, ADR-0013 (and ADR-0016 fixtures) plus the official Docling and ebooklib docs. Distinct from vendored official skills (e.g. `fastapi`, `redis-core`).
