# Learny Research Notes

Date: 2026-06-27

Learny starts as a robust book teaching application and should remain open to adjacent learning and second-brain workflows. The core technical direction is to treat books and learning materials as structured, citeable knowledge sources, not just uploaded files sent directly to a model.

## Current Working Thesis

Use a hybrid architecture:

```text
source file -> canonical structured corpus -> derived markdown/chunks -> retrieval -> cited teaching response
                                                       \-> long-context fallback
```

The durable corpus comes first. RAG is the default query path. Long-context model calls are reserved for chapter-level teaching, synthesis, comparison, study plans, and low-confidence retrieval cases.

## Why Not Only RAG

RAG is strong for repeated daily use because it is cheaper, faster, easier to cite, and easier to update than repeatedly sending the whole book to a model. It is also a better fit for precise questions about specific sections.

The weakness is retrieval recall. If chunking is poor, metadata is weak, or the question spans multiple chapters, the answer can miss important context. This is why ingestion quality, hierarchical retrieval, reranking, and fallback routing matter.

## Why Not Only Long Context

Long-context models are useful for whole-chapter or whole-book reasoning, but they are not a complete replacement for retrieval in a product:

- cost and latency rise with repeated daily use;
- citation control is harder unless the platform supports native citations;
- relevant information can still be missed in long contexts;
- users need stable references back to pages, chapters, and sections.

Research such as "Lost in the Middle" and later long-context evaluations shows that simply placing more tokens in context does not guarantee reliable use of all evidence.

## Why Structured Markdown Is Necessary But Not Sufficient

Markdown is useful as an LLM-facing view, but it should not be the only source of truth. A robust system should keep richer canonical data behind it:

- stable block IDs;
- chapter and section hierarchy;
- source page spans;
- source file offsets or EPUB hrefs;
- content type, such as definition, example, exercise, figure, table, note;
- extracted HTML for tables and structured content.

Markdown should be generated from that canonical representation for prompting, review, and embeddings.

## Preferred Ingestion Direction

Prefer source files in this order:

```text
EPUB / clean HTML > DOCX > tagged PDF > untagged PDF > scanned PDF > plain text
```

EPUB and HTML preserve logical structure more reliably than PDF. PDF remains important as a page-reference authority, but PDF text extraction must be validated because reading order, tables, headers, footnotes, and multi-column layouts can be unreliable.

## Product Requirements Implied By Research

- Every answer should be traceable to source chunks, pages, or section paths.
- The application should separate ingestion/indexing from answering.
- The ingestion pipeline should be asynchronous and observable.
- Users should be able to ask local factual questions, broad teaching questions, and follow-up questions in context.
- The system should support multi-format sources and preserve provenance.
- Evaluation should be designed from the start, not added after the model feels plausible.

## Initial Architecture Concepts

Core domains:

- Library: uploaded sources, editions, ownership, collections.
- Corpus: canonical document structure, blocks, sections, chunks, metadata.
- Retrieval: embeddings, keyword search, reranking, source selection.
- Tutor: teaching sessions, explanations, quizzes, remediation.
- Notes/Memory: user highlights, notes, summaries, later second-brain graph.
- Evaluation: retrieval tests, citation checks, answer faithfulness checks.

Boundary principle: keep AI provider implementation details outside the core domains. The application should be able to change OpenAI, Anthropic, local embeddings, or vector stores without rewriting the learning product.

## Developer Documentation Tooling

Context7 MCP is worth using during implementation and architecture research because Learny will depend on fast-moving APIs: Laravel AI SDK, OpenAI Responses/File Search, Anthropic citations, LangGraph, LlamaIndex, vector stores, and document parsing libraries.

Treat Context7 as a development-time MCP/docs tool, not as part of the Learny runtime architecture. It helps agents fetch current, version-specific framework documentation and examples, reducing hallucinated or outdated API usage. The product should not depend on Context7 to answer end-user learning questions.

Context7's own documentation describes two modes:

- CLI + Skills: fetch docs through `ctx7` commands without MCP.
- MCP: register a Context7 MCP server so agents can call documentation tools natively.

For this project, MCP is the better fit if Codex can connect to it, because the agent can request library docs directly during implementation.

Configured locally in `/home/augusto/.codex/config.toml`:

```toml
[mcp_servers.context7]
url = "https://mcp.context7.com/mcp"
```

No `CONTEXT7_API_KEY` is configured yet. Add one later if higher Context7 rate limits are needed.

## References

- OpenAI File Search: https://developers.openai.com/api/docs/guides/tools-file-search
- Anthropic citations: https://docs.anthropic.com/en/docs/build-with-claude/citations
- LangGraph agentic RAG: https://docs.langchain.com/oss/python/langgraph/agentic-rag
- LlamaIndex ingestion pipelines: https://developers.llamaindex.ai/python/framework/module_guides/loading/ingestion_pipeline/
- W3C EPUB 3.3: https://www.w3.org/TR/epub-33/
- PyMuPDF text extraction notes: https://pymupdf.readthedocs.io/en/latest/recipes-text.html
- Ragas metrics: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/
- "Lost in the Middle": https://arxiv.org/abs/2307.03172
- "Retrieval Augmented Generation or Long-Context LLMs?": https://arxiv.org/abs/2407.16833
- Context7 GitHub repository: https://github.com/upstash/context7
- Context7 docs page: https://context7.com/upstash/context7
