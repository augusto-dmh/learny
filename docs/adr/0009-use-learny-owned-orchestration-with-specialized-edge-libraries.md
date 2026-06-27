# ADR-009: Use Learny-Owned Orchestration With Specialized Edge Libraries

- **Date**: 2026-06-27
- **Status**: Accepted
- **Deciders**: Augusto, Codex
- **Tags**: architecture, ai, rag, orchestration, document-processing, evaluation

## Context and Problem Statement

Learny needs document parsing, corpus generation, retrieval, answer generation, and evaluation. The Python ecosystem offers broad RAG/orchestration frameworks such as LlamaIndex and LangGraph/LangChain, as well as more specialized libraries such as Docling for document conversion and Ragas for RAG evaluation.

The question is whether Learny should adopt a broad AI framework as the core application architecture, keep orchestration Learny-owned, or use specialized libraries only at clear boundaries.

## Decision Drivers

- Learny's core model should be its own Library, Corpus, Retrieval, Tutor, Notes/Memory, and Evaluation concepts.
- Framework abstractions should not replace Learny's domain contracts.
- Specialized libraries should be adopted where they clearly reduce implementation risk or improve quality.
- The architecture should allow comparison and replacement of parsing, retrieval, generation, and evaluation approaches.
- Official or first-party documentation should be the basis for project-local implementation skills where practical.

## Considered Options

- Minimal custom orchestration first.
- LlamaIndex-first as the main RAG/document framework.
- LangGraph/LangChain-first as the main orchestration framework.
- Learny-owned orchestration with specialized edge libraries.

## Decision Outcome

Chosen option: **Learny-owned orchestration with specialized edge libraries**, because Learny needs strong control over corpus, citations, evaluation, and product semantics while still benefiting from targeted Python ecosystem tools.

The implementation direction is:

1. Keep ingestion, retrieval, tutoring, and evaluation workflows expressed in Learny-owned application services and ports.
2. Use specialized libraries at the edges when they solve a concrete problem better than custom code.
3. Treat Docling as a candidate document parsing/conversion library, especially for PDF and multi-format extraction.
4. Treat Ragas as a candidate evaluation library for RAG metrics such as faithfulness, context precision, context recall, and answer relevance.
5. Do not adopt LlamaIndex or LangGraph/LangChain as the core architecture by default.
6. Allow LlamaIndex, LangGraph, LangChain, or other orchestration frameworks inside adapters, experiments, or bounded workflow implementations only after a specific need is documented.
7. Keep framework-specific types out of core domain models and public application contracts.

### Positive Consequences

- Learny keeps control over source provenance, citations, corpus schema, retrieval behavior, and evaluation semantics.
- The project can use strong specialized libraries without inheriting an entire framework architecture.
- Parsing and evaluation tools can be swapped or compared through Learny-owned contracts.
- The architecture stays aligned with ADR-007's provider-port boundary.
- Broad frameworks remain available later if agentic workflows or complex RAG graphs become real needs.

### Negative Consequences

- Learny must design its own orchestration and application service boundaries.
- The project will not get the fastest possible framework-provided RAG prototype.
- More glue code is needed around parsing, retrieval, evaluation, and provider adapters.
- Library adoption decisions still need implementation-level validation and tests.

## Pros and Cons of the Options

### Learny-owned orchestration with specialized edge libraries ✅ Chosen

- ✅ Preserves Learny's domain model and contracts.
- ✅ Allows targeted use of Docling, Ragas, and similar tools.
- ✅ Reduces risk of framework lock-in.
- ❌ Requires more application design and integration work.

### Minimal custom orchestration first

- ✅ Maximum control and smallest dependency surface.
- ✅ Avoids framework coupling.
- ❌ Risks rebuilding parsing/evaluation capabilities that mature libraries already provide.
- ❌ Could slow implementation if taken too literally.

### LlamaIndex-first

- ✅ Strong document ingestion, indexing, retrieval, and RAG abstractions.
- ✅ Can accelerate early RAG workflows.
- ❌ Risks making LlamaIndex concepts the product architecture.
- ❌ May conflict with Learny-owned corpus, citation, and evaluation contracts if adopted too centrally.

### LangGraph/LangChain-first

- ✅ Strong fit for graph workflows, tools, long-running agentic flows, and orchestration.
- ✅ Useful if Learny later needs stateful agent workflows.
- ❌ Too much framework surface before Learny has proven agentic workflow needs.
- ❌ Risks coupling product logic to graph/agent abstractions too early.

## References

- [ADR-001: Use Hybrid Structured Corpus, RAG, And Long-Context Fallback](0001-hybrid-book-intelligence-architecture.md)
- [ADR-002: Keep A Rich Canonical Document Format And Derive Markdown](0002-canonical-document-format.md)
- [ADR-003: Treat Citations And Evaluation As Core Product Requirements](0003-citations-and-evaluation-are-core-requirements.md)
- [ADR-005: Run Document Work In Separate Workers Within The Same Codebase](0005-run-document-work-in-separate-workers-same-codebase.md)
- [ADR-007: Use Learny-Owned Ports For AI Provider Integration](0007-use-learny-owned-ports-for-ai-provider-integration.md)
- Docling official documentation via Context7: `/docling-project/docling`
- Ragas official documentation via Context7: `/websites/ragas_io_en_stable`
- LlamaIndex official documentation via Context7: `/websites/developers_llamaindex_ai`
- LangGraph official documentation via Context7: `/websites/langchain_oss_python_langgraph`
