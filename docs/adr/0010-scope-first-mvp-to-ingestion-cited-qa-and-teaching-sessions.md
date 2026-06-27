# ADR-010: Scope The First MVP To Ingestion, Cited Q&A, And Teaching Sessions

- **Date**: 2026-06-27
- **Status**: Accepted
- **Deciders**: Augusto, Codex
- **Tags**: product, mvp, learning, tutor, ingestion, citations

## Context and Problem Statement

Learny is intended to start as a robust book teaching application and may later expand into broader learning and second-brain workflows. The architecture decisions already require a structured canonical corpus, cited answers, evaluation, hybrid retrieval, and long-context fallback.

The MVP scope question is what first version is useful enough to validate the product without overloading the first implementation with quizzes, notes, memory, study plans, and second-brain features.

## Decision Drivers

- The MVP should prove that Learny can ingest source material and teach from it, not only chat over files.
- Citations and source grounding must be visible from the first useful version.
- The first build should stay small enough to design, implement, test, and evaluate well.
- Later learning-loop features should remain compatible with the MVP architecture.
- The MVP should avoid adding notes, memory, quiz remediation, or second-brain workflows before the core tutor experience works.

## Considered Options

- Ingestion plus cited Q&A only.
- Ingestion plus cited Q&A plus teaching sessions.
- Ingestion plus cited Q&A plus teaching sessions plus quizzes.
- Full learning loop with notes, highlights, memory, quizzes, remediation, study plans, and evaluation UI.

## Decision Outcome

Chosen option: **Ingestion plus cited Q&A plus teaching sessions**, because it proves Learny's core promise: the product can process a book, answer from the source with citations, and teach a chapter or passage in context.

The first MVP includes:

1. Upload or register a supported source document.
2. Process the document into the canonical corpus and derived retrieval views.
3. Ask questions against the processed source.
4. Return answers grounded in citations and source evidence.
5. Start a structured teaching session around a chapter, section, or passage.
6. Preserve enough session context to support follow-up explanation inside the teaching flow.

The first MVP excludes:

1. Quiz generation and remediation workflows.
2. User notes, highlights, memory, and second-brain graph features.
3. Study plans beyond what is needed inside a teaching session.
4. Multi-document synthesis unless it is needed for the first ingestion/Q&A/tutor workflow.
5. A full evaluation dashboard, though evaluation hooks and test fixtures remain required by ADR-003.

### Positive Consequences

- The MVP validates both retrieval and teaching, not only document search.
- The product can demonstrate clear value without waiting for notes, quizzes, or memory.
- Implementation stays focused on the foundation: ingestion, corpus, retrieval, citations, answer generation, and tutor flow.
- Later quiz, remediation, notes, and memory features can build on real session and citation data.

### Negative Consequences

- The MVP will not yet provide a complete study loop.
- Quiz/remediation quality will remain unproven until a later feature cycle.
- Notes and second-brain expansion are deferred.
- The teaching session needs enough design to avoid becoming a generic chat interface.

## Pros and Cons of the Options

### Ingestion plus cited Q&A plus teaching sessions ✅ Chosen

- ✅ Proves the core learning product, not only retrieval.
- ✅ Keeps scope smaller than a full learning loop.
- ✅ Forces citations and source grounding into the first user-facing workflow.
- ❌ Requires tutor-session design earlier than a Q&A-only prototype.

### Ingestion plus cited Q&A only

- ✅ Smallest useful technical slice.
- ✅ Good for testing ingestion and retrieval.
- ❌ Does not prove Learny's teaching value.
- ❌ Risks becoming "chat with a book" instead of a learning product.

### Ingestion plus cited Q&A plus teaching sessions plus quizzes

- ✅ More complete learning loop.
- ✅ Starts validating quiz/remediation behavior earlier.
- ❌ Adds significant generation, evaluation, and UI scope before the tutor foundation is proven.

### Full learning loop

- ✅ Strongest product vision.
- ❌ Too broad for the first implementation.
- ❌ Increases risk of weak foundations across ingestion, retrieval, citations, notes, quizzes, and memory.

## References

- [ADR-001: Use Hybrid Structured Corpus, RAG, And Long-Context Fallback](0001-hybrid-book-intelligence-architecture.md)
- [ADR-002: Keep A Rich Canonical Document Format And Derive Markdown](0002-canonical-document-format.md)
- [ADR-003: Treat Citations And Evaluation As Core Product Requirements](0003-citations-and-evaluation-are-core-requirements.md)
- [ADR-005: Run Document Work In Separate Workers Within The Same Codebase](0005-run-document-work-in-separate-workers-same-codebase.md)
- [ADR-006: Use PostgreSQL Hybrid Search With pgvector And Full-Text Search](0006-use-postgresql-hybrid-search-with-pgvector-and-full-text.md)
- [ADR-007: Use Learny-Owned Ports For AI Provider Integration](0007-use-learny-owned-ports-for-ai-provider-integration.md)
