# ADR-003: Treat Citations And Evaluation As Core Product Requirements

- **Date**: 2026-06-27
- **Status**: Accepted
- **Deciders**: Augusto, Codex
- **Tags**: citations, evaluation, quality, ai, learning

## Context and Problem Statement

A book tutor must teach from the source, not merely produce plausible explanations. Users should be able to ask about specific passages and trust that explanations are grounded in the material.

## Decision Drivers

- Learny must be trustworthy for learning, not only conversationally fluent.
- Users need to inspect where explanations came from.
- Retrieval and generation failures must be diagnosable.
- Model, retrieval, and chunking changes need objective regression checks.

## Considered Options

- Treat citations and evaluation as post-MVP polish.
- Rely on model self-reporting without source-level attribution.
- Make citations and evaluation core architecture requirements from the start.

## Decision Outcome

Chosen option: **Make citations and evaluation core architecture requirements from the start**, because retrofitting them later would affect data models, prompts, retrieval, UI, and QA workflows.

Every generated answer should be traceable to retrieved or supplied source material through:

- chunk ID;
- section path;
- page span when available;
- source file reference;
- short source snippet when useful.

Evaluation should separately measure:

- retrieval recall;
- retrieval precision;
- citation accuracy;
- answer faithfulness;
- teaching usefulness;
- quiz/remediation quality;
- behavior when the answer is not present in the source.

### Positive Consequences

- More reliable learning experience.
- Better debugging when answers are wrong.
- Easier comparison between models, retrievers, and chunking strategies.

### Negative Consequences

- More upfront schema and test design.
- More expensive development loop because answers require source validation.

## Pros and Cons of the Options

### Core citations and evaluation from the start ✅ Chosen

- ✅ Supports trust, debugging, regression testing, and product quality.
- ✅ Makes source grounding a product invariant.
- ❌ Increases initial scope and complexity.

### Citations and evaluation as post-MVP polish

- ✅ Faster initial demo.
- ❌ Likely requires schema and pipeline rework later.
- ❌ Allows unreliable behavior to shape early design choices.

### Model self-reporting without source-level attribution

- ✅ Minimal engineering effort.
- ❌ Not trustworthy enough for a learning product.
- ❌ Hard to debug or compare implementations objectively.

## References

- Anthropic citations: https://docs.anthropic.com/en/docs/build-with-claude/citations
- OpenAI File Search: https://developers.openai.com/api/docs/guides/tools-file-search
- LangSmith RAG evaluation: https://docs.langchain.com/langsmith/evaluate-rag-tutorial
- Ragas available metrics: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/
