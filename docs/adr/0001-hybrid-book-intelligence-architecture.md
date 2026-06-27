# ADR-001: Use Hybrid Structured Corpus, RAG, And Long-Context Fallback

- **Date**: 2026-06-27
- **Status**: Accepted
- **Deciders**: Augusto, Codex
- **Tags**: architecture, ai, rag, document-processing, learning

## Context and Problem Statement

Learny needs to support repeated daily use by multiple people. The first use case is robust book teaching, but the architecture should be able to expand into broader learning, notes, and second-brain workflows.

The core question is whether a book should be embedded directly for RAG, converted into logical Markdown chunks by an LLM, or read directly by long-context models.

## Decision Drivers

- Answers must be grounded in source material with reliable citations.
- The application must support repeated daily usage without sending entire books to a model every time.
- The source corpus must survive model, embedding, vector store, and chunking changes.
- The architecture should support both precise passage-level questions and broad teaching/synthesis questions.

## Considered Options

- RAG over directly embedded source files.
- Long-context reading of whole books or chapters.
- LLM-created Markdown segmentation only.
- Hybrid structured corpus plus RAG plus long-context fallback.

## Decision Outcome

Chosen option: **Hybrid structured corpus plus RAG plus long-context fallback**, because it preserves source structure, supports cost-effective daily retrieval, and still allows broad synthesis when retrieval alone is too narrow.

The approach is:

1. Convert source materials into a canonical structured corpus.
2. Generate LLM-friendly Markdown/chunk views from that corpus.
3. Use RAG as the default question-answering path.
4. Use long-context reading as a fallback for broad synthesis, teaching plans, chapter-level explanation, and low-confidence retrieval.

### Positive Consequences

- Better citation quality.
- Better retrieval and study-session performance over repeated use.
- Easier to re-index when chunking or embedding models change.
- Provider-independent corpus representation.

### Negative Consequences

- Ingestion becomes more complex.
- The application needs asynchronous processing and status tracking.
- Evaluation must test both retrieval and generated answers.

## Pros and Cons of the Options

### Hybrid structured corpus plus RAG plus long-context fallback ✅ Chosen

- ✅ Balances cost, reliability, citation quality, and broad reasoning.
- ✅ Keeps document structure durable outside any single LLM provider.
- ✅ Allows routing based on query type.
- ❌ Requires more initial ingestion and orchestration work.

### RAG over directly embedded source files

- ✅ Fastest path to a prototype.
- ✅ Works well for simple factual lookup.
- ❌ Weak if source parsing, chunking, or metadata are poor.
- ❌ Harder to support rich teaching workflows and source navigation.

### Long-context reading of whole books or chapters

- ✅ Useful for broad synthesis and one-off deep analysis.
- ✅ Reduces retrieval miss risk for some questions.
- ❌ Higher repeated cost and latency.
- ❌ Still does not guarantee reliable use of all evidence in context.

### LLM-created Markdown segmentation only

- ✅ Improves readability and chunking compared with raw PDFs.
- ✅ Useful as a derived view.
- ❌ Not sufficient as a product architecture because it lacks retrieval, indexing, evaluation, and durable provenance by itself.

## References

- OpenAI File Search: https://developers.openai.com/api/docs/guides/tools-file-search
- Anthropic citations: https://docs.anthropic.com/en/docs/build-with-claude/citations
- Ragas metrics: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/
- "Retrieval Augmented Generation or Long-Context LLMs?": https://arxiv.org/abs/2407.16833
