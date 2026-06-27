# ADR-016: Use Golden Fixtures For MVP Evaluation

- **Date**: 2026-06-27
- **Status**: Accepted
- **Deciders**: Augusto, Codex
- **Tags**: architecture, evaluation, testing, rag, citations, mvp

## Context and Problem Statement

ADR-003 established that citations and evaluation are core product requirements. The MVP scope includes EPUB ingestion, cited Q&A, and teaching sessions. The project needs repeatable evaluation from the first implementation, but a full evaluation platform or automated model-judge pipeline would add significant complexity before the basic product path exists.

The evaluation question is whether the MVP should rely on manual QA, golden fixtures, automated RAG evaluation libraries such as Ragas from day one, or a full evaluation dashboard.

## Decision Drivers

- Evaluation must exist from the first implementation because source grounding is a product invariant.
- Tests should verify ingestion structure, retrieval behavior, and citation correctness before broad model evaluation.
- The MVP should keep cost and implementation complexity under control.
- Evaluation artifacts should be deterministic enough to run in local development and CI.
- The design should leave room for Ragas or other evaluation libraries later.

## Considered Options

- Manual QA only.
- Golden test fixtures for ingestion, retrieval, and citations.
- Automated RAG evaluation with Ragas from day one.
- Full evaluation dashboard.

## Decision Outcome

Chosen option: **Golden test fixtures for ingestion, retrieval, and citations**, because it makes evaluation concrete and repeatable without overbuilding the MVP.

The MVP evaluation direction is:

1. Include one or more small fixture EPUBs suitable for automated tests.
2. Define expected ingestion outputs, such as metadata, table of contents, sections, stable block identifiers, and derived chunks.
3. Define expected retrieval behavior for selected questions or queries.
4. Define expected citation/evidence behavior, including allowed source chunks, section paths, and snippets.
5. Test generated-answer grounding through deterministic checks where possible and bounded model-dependent checks where necessary.
6. Defer Ragas integration and a full evaluation dashboard until retrieval and answer-generation behavior need broader measurement.

### Positive Consequences

- Evaluation becomes part of the first implementation, not post-MVP polish.
- Ingestion, retrieval, and citation regressions can be caught early.
- Tests remain small enough for local development and CI.
- The project builds an evidence corpus that can later feed Ragas or other evaluation tools.
- MVP work stays focused on product foundations rather than an evaluation platform.

### Negative Consequences

- Golden fixtures do not fully measure teaching usefulness or model answer quality.
- Some answer-generation behavior may still require manual review or model-assisted evaluation later.
- Fixture coverage can create false confidence if it is too narrow.
- Ragas and broader evaluation metrics are deferred.

## Pros and Cons of the Options

### Golden fixtures for ingestion, retrieval, and citations ✅ Chosen

- ✅ Repeatable and implementation-friendly.
- ✅ Directly tests the highest-risk source-grounding path.
- ✅ Lowers cost compared with model-heavy evaluation from day one.
- ❌ Does not fully evaluate open-ended teaching quality.

### Manual QA only

- ✅ Fastest to start.
- ✅ Useful for early product feel.
- ❌ Conflicts with the accepted evaluation-first architecture.
- ❌ Not enough to catch retrieval and citation regressions.

### Automated RAG evaluation with Ragas from day one

- ✅ Stronger model and retrieval evaluation coverage.
- ✅ Aligns with future evaluation goals.
- ❌ More setup, cost, and moving parts before MVP behavior exists.
- ❌ Needs stable datasets and application outputs first.

### Full evaluation dashboard

- ✅ Strong product-quality visibility.
- ❌ Too much scope for the MVP.
- ❌ Risks delaying ingestion, retrieval, and tutor implementation.

## References

- [ADR-003: Treat Citations And Evaluation As Core Product Requirements](0003-citations-and-evaluation-are-core-requirements.md)
- [ADR-010: Scope The First MVP To Ingestion, Cited Q&A, And Teaching Sessions](0010-scope-first-mvp-to-ingestion-cited-qa-and-teaching-sessions.md)
- [ADR-011: Support EPUB First For Initial Ingestion](0011-support-epub-first-for-initial-ingestion.md)
- [ADR-009: Use Learny-Owned Orchestration With Specialized Edge Libraries](0009-use-learny-owned-orchestration-with-specialized-edge-libraries.md)
