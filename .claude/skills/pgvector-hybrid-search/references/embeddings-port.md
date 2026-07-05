# Embeddings Behind a Learny Port

The embedding provider SDK (OpenAI/Anthropic/etc.) MUST sit behind a Learny-owned `EmbeddingPort` (ADR-0007). Query and repository code receive a plain `list[float]` and **never** import or reference a provider SDK, a model name, or an SDK object. pgvector and Postgres FTS are Learny-owned infrastructure at the edge; no broad orchestration framework (LlamaIndex/LangGraph) owns the retrieval path (ADR-0007, ADR-0009).

Source: <https://github.com/pgvector/pgvector-python>

## The port (domain)

Add alongside the existing `StoragePort` / `PasswordHasher` ports in `app/domain/ports.py`. It is a `typing.Protocol`, `@runtime_checkable`, with **no** FastAPI/SQLAlchemy/SDK imports:

```python
# app/domain/ports.py
from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingPort(Protocol):
    """Turns text into vectors. The provider SDK and model name live only in the
    adapter; callers receive plain float vectors (ADR-0007)."""

    def embed_query(self, text: str) -> list[float]:
        """Embed a single search query."""
        ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of chunks for indexing."""
        ...
```

Retrieval callers depend on this port: they get a `list[float]` and bind it into the semantic arm (`:query_vec` / `chunks.c.embedding.cosine_distance(vec)`), so no SQL file imports a provider SDK. See [hybrid-rrf-query.md](hybrid-rrf-query.md).

## The adapter (infrastructure)

A thin adapter in `app/infrastructure` holds the SDK and the **model id from settings** (`LEARNY_`-prefixed, via `get_settings()`), never hard-coded in query code. The model name never crosses into the domain or the SQL layer — because embeddings are derived and re-indexable (ADR-0001), swapping the model is an adapter+re-index change, not a domain change.

```python
# app/infrastructure/embeddings/openai_adapter.py  (provider is an example, kept at the edge)
from app.core.config import get_settings


class OpenAIEmbeddingAdapter:
    """EmbeddingPort implementation. The only place the SDK/model id appears."""

    def __init__(self, client, model: str | None = None) -> None:
        self._client = client
        self._model = model or get_settings().embedding_model  # e.g. LEARNY_EMBEDDING_MODEL

    def embed_query(self, text: str) -> list[float]:
        resp = self._client.embeddings.create(model=self._model, input=text)
        return resp.data[0].embedding

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.embeddings.create(model=self._model, input=texts)
        return [d.embedding for d in resp.data]
```

Add the knob to `Settings` (do not hard-code it in the adapter body or the SQL):

```python
# app/core/config.py — Settings
embedding_model: str = "text-embedding-3-small"   # LEARNY_EMBEDDING_MODEL
```

The embedding dimension the model produces must match the pgvector column type/dims (`vector(N)` vs `halfvec(N)`); see [pgvector-columns-and-indexes.md](pgvector-columns-and-indexes.md).

## Wiring `register_vector` (psycopg3)

psycopg3 needs `register_vector` so Python lists adapt to the `vector` type on the wire. Wire it once in the infrastructure DB layer (`app/infrastructure/db/engine.py`), which already builds the sync psycopg engine via `@lru_cache get_engine()`. Register it on every new DBAPI connection with a SQLAlchemy `connect` event:

```python
# app/infrastructure/db/engine.py
from functools import lru_cache

from pgvector.psycopg import register_vector
from sqlalchemy import Engine, create_engine, event

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)

    @event.listens_for(engine, "connect")
    def _register_vector(dbapi_conn, _record):  # noqa: ANN001
        register_vector(dbapi_conn)

    return engine
```

If you build a raw psycopg connection pool instead of using the SQLAlchemy engine, register via the pool's `configure` callback:

```python
from pgvector.psycopg import register_vector

def configure(conn):
    register_vector(conn)

# pool = ConnectionPool(..., configure=configure)
```

Sources: pgvector-python README (`from pgvector.psycopg import register_vector`, pool `configure` callback) — <https://github.com/pgvector/pgvector-python>
