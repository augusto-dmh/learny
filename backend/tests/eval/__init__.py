"""Generation evaluation harness (RFC-002 Cycle C, design §8).

Port-level replay for the generation adapters: hand-authored golden-book Q&A
cases (``cases.yaml``), committed response snapshots (``snapshots/*.json``), a
snapshot loader, and a ``--record-generation`` path that rewrites the snapshots
from the live provider. The deterministic citation invariants
(``tests/test_generation_invariants.py``) and the LLM judge (``app.eval``) both
draw their cases from here. No snapshots are committed this cycle, so the
snapshot-driven checks skip with an explicit reason (AD-056 precedent).
"""
