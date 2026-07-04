# Task Design

A Learny task is a thin adapter over an application service, not a place for business logic. Ingestion, corpus generation, embedding, indexing, and evaluation run here — never inside a FastAPI handler (ADR-0005). Handlers only enqueue and read status.

## Thin-adapter pattern

Define tasks under `app.worker` on the existing `celery_app`. A task opens the unit-of-work with `get_engine().begin()` (the same composition pattern the web layer uses), wires the repositories/ports, and calls a framework-free use-case class. Use `bind=True` when you need `self` (task id, `self.retry`).

**Do this** — task composes adapters and delegates to an application service:

```python
"""Ingestion worker tasks (ADR-0005/0014).

Thin Celery adapters: they wire infrastructure adapters and call Learny
application services. No parsing/embedding logic lives here — Docling/embedding
run behind ports (ADR-0009/0007). No FastAPI imports in this module.
"""

from __future__ import annotations

from uuid import UUID

from app.infrastructure.db.engine import get_engine
from app.worker.celery_app import celery_app


@celery_app.task(bind=True, name="ingestion.parse_epub")
def parse_epub(self, ingestion_id: str) -> None:
    with get_engine().begin() as conn:
        # Wire repositories/ports on `conn`, then call the use case.
        service = build_parse_ingestion(conn)  # constructor-injected ports
        service(ingestion_id=UUID(ingestion_id))
```

**Not this** — logic inline in the task (duplicates the domain, unshareable, untestable):

```python
@celery_app.task
def parse_epub(ingestion_id):
    book = epub.read_epub(download_bytes(ingestion_id))  # library + IO in the task
    for chap in book.get_items():                        # business logic in the adapter
        ...
```

Keep edge libraries (Docling for parsing, an embedding SDK, Ragas for evaluation) behind Learny ports in `infrastructure/`, invoked from inside the use case — never imported into `domain/`/`application/` and never into the task body (ADR-0009/0007). See [pipelines.md](pipelines.md).

## Small, serializable arguments only

Pass stable JSON-serializable identifiers; the default `task_serializer`/`result_serializer` is `json` and `accept_content` is `{'json'}`. Load large inputs from storage inside the task via the `StoragePort` (`domain/ports.py`).

**Do this:**

```python
parse_epub.delay(str(ingestion_id))                       # small id
parse_epub.apply_async(args=[str(ingestion_id)], queue="ingest", countdown=5)
```

**Not this** (ADR-0014 explicitly forbids it):

```python
parse_epub.delay(epub_bytes)          # large source file through the broker
parse_epub.delay(orm_user_row)        # ORM row / non-JSON object
parse_epub.delay(openai_client)       # provider SDK object
```

`.delay(*args, **kwargs)` is the shortcut for `.apply_async(args, kwargs)`; use `apply_async` when you need execution options (`queue`, `countdown`, `eta`, `expires`, `link`, `link_error`).

Reference: [Celery — Tasks](https://docs.celeryq.dev/en/stable/userguide/tasks.html), [Celery — Calling tasks](https://docs.celeryq.dev/en/stable/userguide/calling.html)
