# ADR-006: Use PostgreSQL Hybrid Search With pgvector And Full-Text Search

- **Date**: 2026-06-27
- **Status**: Accepted
- **Deciders**: Augusto, Codex
- **Tags**: architecture, retrieval, search, postgresql, pgvector, rag, citations

## Context and Problem Statement

Learny needs retrieval that supports both semantic questions and citation-sensitive lookup. Pure vector search can work for broad semantic similarity, but learning workflows also need exact terms, section titles, definitions, names, page references, glossary-like lookup, and source-grounded citations.

ADR-004 selected PostgreSQL as the primary system of record and pgvector as the initial vector capability. The remaining question is whether initial retrieval should use pure vector search, PostgreSQL-native hybrid search, or a dedicated search/vector engine.

## Decision Drivers

- Retrieval must support cited answers, not only plausible semantic matches.
- Exact terms, phrases, section names, and source metadata should influence retrieval.
- Initial operations should stay simple while the product and corpus model are still forming.
- The canonical corpus, chunks, embeddings, and citation metadata should remain queryable together.
- A later dedicated vector/search engine should remain possible if scale or quality requires it.

## Considered Options

- Pure pgvector semantic search.
- PostgreSQL hybrid search using pgvector plus PostgreSQL full-text search.
- Dedicated search/vector engine from the start.
- Managed provider file/search system from the start.

## Decision Outcome

Chosen option: **PostgreSQL hybrid search using pgvector plus PostgreSQL full-text search**, because it keeps retrieval operationally simple while improving recall and precision for learning-specific, citation-sensitive queries.

The initial retrieval direction is:

1. Store canonical corpus metadata, chunks, citations, and embeddings in PostgreSQL.
2. Use pgvector for semantic similarity search over embeddings.
3. Use PostgreSQL full-text search for keyword, term, section-title, and exact-ish lexical matching.
4. Combine semantic and lexical candidates before answer generation.
5. Add reranking only when the first implementation needs it; do not choose a reranker in this ADR.
6. Defer dedicated vector/search infrastructure until there is measured retrieval pain, scale pressure, or feature need.

### Positive Consequences

- Improves retrieval for both semantic questions and exact source lookup.
- Keeps corpus metadata, citations, relational filters, lexical search, and vector search in one database.
- Avoids early operational overhead from Qdrant, Weaviate, Elasticsearch/OpenSearch, or managed vector providers.
- Supports evaluation of retrieval quality before adding more infrastructure.
- Preserves a clear path to a dedicated search/vector system later if PostgreSQL becomes insufficient.

### Negative Consequences

- Retrieval implementation is more involved than pure vector search.
- Hybrid scoring, candidate merging, and thresholding need explicit design and tests.
- PostgreSQL may eventually be insufficient for large-scale search workloads or advanced ranking features.
- The team must avoid treating database-level retrieval details as permanent domain concepts.

## Pros and Cons of the Options

### PostgreSQL hybrid search with pgvector and full-text search ✅ Chosen

- ✅ Handles semantic similarity and lexical/exact lookup.
- ✅ Keeps operations simple for the first production-oriented version.
- ✅ Works well with citation metadata, relational filters, and corpus ownership.
- ❌ Requires candidate merging and ranking design.

### Pure pgvector semantic search

- ✅ Simplest retrieval implementation.
- ✅ Good fit for broad semantic questions.
- ❌ Weak for exact terms, titles, names, page references, and citation-sensitive lookup.
- ❌ Increases risk that embedding misses become answer-quality failures.

### Dedicated search/vector engine from the start

- ✅ More specialized retrieval and scaling capabilities.
- ✅ May support advanced search/ranking needs later.
- ❌ Adds infrastructure and operational complexity too early.
- ❌ Risks shaping the domain model around a specific search product before product needs are proven.

### Managed provider file/search system from the start

- ✅ Fast prototype path.
- ❌ Conflicts with Learny's canonical corpus and evaluation-first decisions.
- ❌ Reduces control over parsing, chunking, metadata, retrieval behavior, and citation debugging.

## References

- [ADR-001: Use Hybrid Structured Corpus, RAG, And Long-Context Fallback](0001-hybrid-book-intelligence-architecture.md)
- [ADR-002: Keep A Rich Canonical Document Format And Derive Markdown](0002-canonical-document-format.md)
- [ADR-003: Treat Citations And Evaluation As Core Product Requirements](0003-citations-and-evaluation-are-core-requirements.md)
- [ADR-004: Use Python, FastAPI, React, Next.js, And PostgreSQL For The Initial Stack](0004-python-fastapi-react-nextjs-postgresql-stack.md)
- PostgreSQL official documentation via Context7: `/websites/postgresql_current`
- pgvector official documentation via Context7: `/pgvector/pgvector`
