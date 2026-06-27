# ADR-007: Use Learny-Owned Ports For AI Provider Integration

- **Date**: 2026-06-27
- **Status**: Accepted
- **Deciders**: Augusto, Codex
- **Tags**: architecture, ai, providers, openai, anthropic, ports, adapters

## Context and Problem Statement

Learny must use LLMs, embeddings, citations, and long-context fallback while preserving a provider-independent product architecture. OpenAI, Anthropic, and future providers expose different SDKs, model APIs, citation formats, tool-use behavior, and operational constraints.

The question is whether Learny should call provider SDKs directly from product/application code, build around one orchestration framework, use managed provider-native retrieval as the main abstraction, or define Learny-owned ports with provider-specific adapters behind them.

## Decision Drivers

- Core product domains should use Learny concepts, not provider-specific SDK objects.
- Provider, model, embedding, and retrieval implementation choices should be replaceable.
- Citation and evaluation behavior must be inspectable and testable across providers.
- The architecture should allow official provider SDKs without coupling the domain model to them.
- AI orchestration frameworks may be useful later, but should not become the product domain model by default.

## Considered Options

- Call provider SDKs directly from product/application code.
- Use thin provider adapters behind Learny-owned ports.
- Use one AI orchestration framework as the core abstraction.
- Use managed provider-native retrieval/citation as the main abstraction.

## Decision Outcome

Chosen option: **Use thin provider adapters behind Learny-owned ports**, because it lets Learny use official provider SDKs while keeping product logic, evaluation, citations, retrieval, and fallback routing under Learny's control.

The integration model is:

1. Define Learny-owned ports for capabilities such as answer generation, embeddings, long-context reading, structured output, citation-aware generation, and provider health/capability checks.
2. Implement provider adapters for OpenAI, Anthropic, and later providers behind those ports.
3. Keep provider request/response objects, SDK clients, model names, tool schemas, and citation formats out of core domain logic.
4. Normalize provider outputs into Learny-owned result types that preserve evidence, citations, usage, latency, model identity, and failure information.
5. Allow AI orchestration frameworks inside adapters or application services only when they do not replace Learny's domain contracts.
6. Do not use managed provider file/search systems as Learny's canonical retrieval or corpus abstraction.

### Positive Consequences

- Learny can switch or compare providers without rewriting the product domain.
- Evaluation can compare provider behavior through consistent Learny-owned result types.
- Citation handling remains aligned with Learny's canonical corpus and evidence model.
- Official provider SDKs can still be used where they are strongest.
- The architecture can adopt orchestration libraries later without making them permanent boundaries.

### Negative Consequences

- More initial design work is required for ports, adapter contracts, and normalized result types.
- Provider-specific capabilities may be harder to expose cleanly if the common abstraction is too generic.
- Tests must cover both provider-independent behavior and provider-adapter mapping.
- Some provider-native features may need explicit product decisions before being exposed.

## Pros and Cons of the Options

### Thin provider adapters behind Learny-owned ports ✅ Chosen

- ✅ Keeps provider SDK details out of core product logic.
- ✅ Supports provider comparison, fallback, and later replacement.
- ✅ Preserves Learny-owned citation and evaluation semantics.
- ❌ Requires careful contract design and adapter tests.

### Provider SDKs directly in product/application code

- ✅ Fastest initial integration.
- ✅ Minimal abstraction upfront.
- ❌ Couples Tutor, Retrieval, Evaluation, and Corpus logic to provider details.
- ❌ Makes provider replacement and comparative evaluation harder.

### One AI orchestration framework as the core abstraction

- ✅ Can accelerate complex RAG, agents, graph workflows, and evaluations.
- ✅ May provide useful tracing and integration primitives.
- ❌ Risks making framework concepts the domain model.
- ❌ Can make provider and retrieval behavior harder to reason about if adopted too early.

### Managed provider-native retrieval/citation as the main abstraction

- ✅ Fastest way to use hosted provider retrieval features.
- ❌ Conflicts with Learny's canonical corpus and evaluation-first architecture.
- ❌ Gives less control over chunking, metadata, retrieval behavior, citations, and debugging.

## References

- [ADR-001: Use Hybrid Structured Corpus, RAG, And Long-Context Fallback](0001-hybrid-book-intelligence-architecture.md)
- [ADR-002: Keep A Rich Canonical Document Format And Derive Markdown](0002-canonical-document-format.md)
- [ADR-003: Treat Citations And Evaluation As Core Product Requirements](0003-citations-and-evaluation-are-core-requirements.md)
- [ADR-004: Use Python, FastAPI, React, Next.js, And PostgreSQL For The Initial Stack](0004-python-fastapi-react-nextjs-postgresql-stack.md)
- [ADR-006: Use PostgreSQL Hybrid Search With pgvector And Full-Text Search](0006-use-postgresql-hybrid-search-with-pgvector-and-full-text.md)
- OpenAI API overview: https://developers.openai.com/api/reference/overview/
- OpenAI Responses API overview: https://developers.openai.com/api/reference/responses/overview/
- OpenAI embeddings guide: https://developers.openai.com/api/docs/guides/embeddings
- Anthropic Messages API: https://docs.anthropic.com/en/api/messages
- Anthropic citations: https://docs.anthropic.com/en/docs/build-with-claude/citations
- Anthropic search results for RAG citations: https://docs.anthropic.com/en/docs/build-with-claude/search-results
