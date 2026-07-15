# Learny v2 research — gap-critique

Generated 2026-07-12 by a web-research agent (v2 planning research fleet). Sources/dates inline; verify load-bearing claims before implementation.

---

GAP: Is the flagship quiz item format free-recall/cloze without distractors (active-recall-srs's evidence-based MVP) or MCQ with options/correct_index/distractors (the request schema in anthropic-generation and the duplicate-option/distractor-sanity checks in evaluation)?
WHY: Three reports design the flagship feature around contradictory item formats, and the choice drives the generation schema, data model, judge pipeline, and review UI.

GAP: What does the personal VPS deployment concretely require — total resource sizing (Docling worker alone needs ~1 GB extra image + 2–4 GB RAM on top of Postgres/Redis/MinIO/API/Next), image delivery pipeline (registry vs build-on-VPS, CI deploy job), and secrets/TLS handling?
WHY: "Personal VPS deploy" is a locked v2 decision but no report covers deployment mechanics or whether the target VPS can even fit the Docling-era stack, which could force queue/host changes in the roadmap.

GAP: Which embedding model do the retrieval eval snapshots and recall@k thresholds run against — the evaluation report baselines everything on text-embedding-3-small ($0.02/M) while the embeddings report locks production to text-embedding-3-large@1536?
WHY: Eval geometry must match the production model or the committed snapshots, nightly drift checks, and recall@10 gates validate a model Learny doesn't ship.
