# Pipelines: Learny-Owned Orchestration with Celery Canvas

Multi-step document pipelines (ingest → corpus → embed → index → evaluate) are Learny-owned. Compose them with Celery canvas primitives driving Learny application services. Do NOT adopt LlamaIndex/LangGraph/LangChain as the orchestration framework (ADR-0009).

## Compose with canvas primitives

- `signature()` / `.s(*args)` — a partial task invocation you can pass around.
- `.si(*args)` — **immutable** signature; ignores the previous task's return value. Prefer this when steps communicate through DB state (they usually do here) rather than by return value.
- `chain(a, b, c)` or `a | b | c` — run sequentially, each result feeding the next.
- `group(a, b, c)` — run in parallel (e.g. embed many chunk batches).
- `chord(group(...), callback)` — run a group, then a callback once all finish (e.g. index after all batches embed).

**Do this** — a Learny-owned chain of thin tasks, each delegating to a use case, passing only the `ingestion_id` and relying on DB state between steps:

```python
from celery import chain, chord, group

def enqueue_ingestion(ingestion_id: str) -> None:
    workflow = chain(
        parse_epub.si(ingestion_id),
        generate_corpus.si(ingestion_id),
        chord(
            group(embed_batch.si(ingestion_id, b) for b in range(n_batches)),
            build_index.si(ingestion_id),
        ),
        evaluate_retrieval.si(ingestion_id),
    )
    workflow.apply_async()
```

Use `apply_async(link=..., link_error=...)` when you need explicit success/failure callbacks (e.g. mark the ingestion `failed` if any step errors) beyond in-task status writes.

**Not this** — a broad framework owning the pipeline (ADR-0009 forbids it):

```python
from llama_index import IngestionPipeline   # framework becomes the orchestrator
pipeline = IngestionPipeline(transformations=[...])
```

## Edge libraries stay behind ports

Docling (parsing) and Ragas (evaluation) are specialized edge libraries. They sit behind Learny ports (`domain/ports.py`) with adapters in `infrastructure/`, invoked from inside the use case a task calls — never imported into `domain/`/`application/`, and their types never leak into domain models or public application contracts (ADR-0009, aligned with the provider-port boundary of ADR-0007). The canvas wires Learny tasks; each task calls a Learny service; the service calls a port; the adapter wraps the library.

Reference: [Celery — Canvas: designing workflows](https://docs.celeryq.dev/en/stable/userguide/canvas.html), [Celery — Calling tasks](https://docs.celeryq.dev/en/stable/userguide/calling.html)
