"""Learny-owned generation evaluation harness (ADR-0016, RFC-002 Cycle C).

A ~200-line LLM-as-judge over Learny's own generation output — no Ragas, no eval
framework (research §2/§4): faithfulness (claims labeled SUPPORTED/UNSUPPORTED)
and answer relevancy (1-5), scored by ``judge_model`` via structured outputs,
with versioned prompt files and committed JSONL results. The Anthropic SDK is
imported lazily inside the judge only, so importing this package needs no key or
network (mirrors the answer/embedding adapters).
"""
