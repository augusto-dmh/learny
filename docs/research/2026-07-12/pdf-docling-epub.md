# Learny v2 research — pdf-docling-epub

Generated 2026-07-12 by a web-research agent (v2 planning research fleet). Sources/dates inline; verify load-bearing claims before implementation.

---

# Research: PDF ingestion via Docling + EPUB structure hardening
*Research date: 2026-07-12. All version/fact dates noted inline.*

## Actionable conclusions (TL;DR)

1. **Docling remains the right pick for PDF.** MIT license, now Linux Foundation (LF AI & Data)-hosted, actively released (v2.112.0, 2026-07-11), best-in-class table/heading structure on CPU, and its `DoclingDocument` tree maps almost 1:1 onto Learny's `documents → sections → blocks → chunks` model. Alternatives lose on license (marker: GPL code + revenue-capped model weights; PyMuPDF: AGPL) or structure fidelity (PyMuPDF4LLM) — both disqualifying for an OSS-ready portfolio project.
2. **Do NOT use Docling for EPUB.** Its HTML/EPUB backend strips anchor IDs and internal links ([issue #2929](https://github.com/docling-project/docling/issues/2929)) — fatal for Learny's anchor-based citations. Keep ebooklib as the EPUB adapter; harden it with the heuristics below (§4).
3. **PDF anchor scheme: composite anchor = normalized heading path + page span + content hash**, with page number as the human-facing citation and the heading-path+hash pair as the re-ingestion-stable machine key (§3).
4. **Celery fit: yes, with planning.** Standard pipeline runs CPU-only at ~0.8–3 s/page (books = minutes, fine for a worker). Models (~500 MB–1 GB) must be pre-baked into the worker image via `docling-tools models download` / `download_models()`, not fetched at task time. Disable OCR by default (books are born-digital text); it's ~60% of CPU runtime.

---

## 1. Docling state (as of 2026-07)

**Version/license/governance.** v2.112.0 released 2026-07-11, MIT license, Python ≥3.10, Linux/macOS/Windows x86_64+arm64 ([PyPI](https://pypi.org/project/docling/), [GitHub](https://github.com/docling-project/docling)). Originated at IBM Research Zurich; in early 2026 IBM donated it to the Linux Foundation ecosystem (LF AI & Data / AAIF), and released **Granite-Docling-258M** VLM (Apache 2.0, Jan 2026) for the optional VLM pipeline ([docling-project org](https://github.com/docling-project)). Governance risk: low; abandonment risk: low.

**What it extracts from PDFs** ([docs](https://docling-project.github.io/docling/), [technical report arXiv:2408.09869](https://arxiv.org/pdf/2408.09869)):
- **Layout model** (RT-DETR–based): detects Title, Section-header, Text, List-item, Caption, Footnote, Formula, Picture, Table, Page-header/footer ([model catalog](https://docling-project.github.io/docling/usage/model_catalog/)).
- **Reading order** resolution across multi-column layouts.
- **TableFormer**: logical row/column table structure incl. header cells (~2–6 s/table on CPU).
- **Page numbers + bounding boxes** as provenance on every item.
- Furniture separation: running headers/footers isolated from body — free noise removal.

**DoclingDocument model** ([docs](https://docling-project.github.io/docling/concepts/docling_document/)): a typed tree — `body` root (reading order = tree child order) + `furniture` root; item arrays (`texts`, `tables`, `pictures`, groups) cross-referenced by JSON pointers (`#/texts/1`); `SectionHeaderItem` carries a heading **level**, so the heading hierarchy is reconstructable; each item has `prov` entries with `page_no` + bbox. Lossless JSON serialization.

**Chunking** ([docs](https://docling-project.github.io/docling/concepts/chunking/)): `HierarchicalChunker` emits one chunk per document element with the **heading path** attached; `HybridChunker` adds tokenizer-aware split/merge. **Recommendation: don't use Docling chunkers.** Learny already derives chunks from its canonical corpus (heading-path-aware, ~size-bounded); reusing Learny's chunker keeps EPUB and PDF chunking identical and keeps Docling at the edge per ADR-0009. The Docling chunkers validate that the heading-path-per-chunk design is the industry pattern.

**Performance / resources** (technical report, [arXiv:2408.09869v4](https://arxiv.org/html/2408.09869v4); [discussion #306](https://github.com/docling-project/docling/discussions/306)):
- x86 CPU: median ~0.79 s/page (fast path) / ~3.1 s/page avg with default options; M3 Max ~0.3–1.3 s/page; L4 GPU ~114 ms/page median. A 400-page book ≈ 5–20 min on a CPU worker — acceptable for Celery with generous `time_limit` and progress updates.
- **OCR ≈ 13 s/page on x86 CPU and ~60% of runtime — disable by default** (`PdfPipelineOptions(do_ocr=False)`); expose per-source opt-in later for scanned PDFs. Table structure is ~16% of runtime; keep it on.
- **Models**: downloaded to `$HOME/.cache/docling/models` on first use; pre-fetch with `docling.utils.model_downloader.download_models()` in the Dockerfile ([advanced options](https://docling-project.github.io/docling/usage/advanced_options/)). Official images pre-bundle models to kill cold-start ([docling-serve models.md](https://github.com/docling-project/docling-serve/blob/main/docs/models.md)). Budget ~1 GB image growth + ~2–4 GB RAM headroom in the worker; set Celery `worker_max_tasks_per_child` or a dedicated `pdf_ingest` queue with concurrency 1 to bound memory.
- Skip the VLM/Granite-Docling pipeline for v2 — heavier, GPU-oriented, unneeded for born-digital books.

## 2. Docling adapter design sketch (behind Learny's ingestion port)

Same port ebooklib implements today; format dispatch by content type:

```
infrastructure/ingestion/docling_pdf_adapter.py
  class DoclingPdfParser(DocumentParserPort):
      def parse(self, source_bytes: bytes, ...) -> ParsedDocument
```

Mapping `DoclingDocument` → Learny canonical corpus:

| Docling | Learny |
|---|---|
| `DoclingDocument` + metadata (title, origin hash) | `Document` |
| `SectionHeaderItem` (level *n*) opens a section; nesting from levels | `Section` (heading text, depth, heading path) |
| `TextItem`/paragraph, `ListGroup`, `TableItem` (→ Markdown/HTML), `PictureItem` (→ caption block or skipped) | `Block` (typed: paragraph/list/table/figure) |
| `prov[].page_no` per item (min/max over block's items) | `Block.page_span` / rolled up to `Section.page_span` |
| `furniture` tree, Page-header/footer, Footnote items | dropped from body (optionally kept as footnote blocks) |
| item JSON pointer (`#/texts/42`) | stored as `source_ref` for debugging, **not** the stable anchor (index-based, shifts on re-parse) |

Adapter rules:
- Pipeline: `StandardPdfPipeline`, `do_ocr=False`, `do_table_structure=True`; convert from `DocumentStream` (bytes from S3, no temp-file leak).
- Synthesize a root section for preamble text before the first heading (same problem EPUBs have).
- Heading-level normalization: Docling levels can jump (h1→h3); clamp child depth to parent+1 (same normalizer as EPUB — shared corpus-side, not adapter-side).
- Chunking: run Learny's existing corpus→chunk derivation; no Docling chunkers.
- Keep `docling` an optional dependency group (`uv add docling --group ingestion-pdf` or extras) so the API image stays slim; only the worker image installs it + models.

## 3. PDF anchor stability scheme

There is no native stable ID inside a PDF (no hrefs/element IDs as in EPUB). Industry practice for citations that survive re-ingestion is a **layered anchor** (page + structural path + content fingerprint) — see e.g. [Tensorlake on citation-aware RAG](https://www.tensorlake.ai/blog/rag-citations) and [buzzi.ai citation architecture](https://buzzi.ai/insights/ai-document-retrieval-rag-citation-architecture) (both 2025–26).

Proposed anchor for a Learny PDF block:

```
anchor = pdf:{heading_path_slug}/{block_ordinal}   e.g. pdf:part-ii/ch-5/sec-5-2/b014
fields: page_start, page_end        # human-facing citation ("pp. 142–143")
        content_hash = sha256(normalized_block_text)[:16]
        source_file_hash            # ties anchors to the exact uploaded PDF
```

- **Heading path** (normalized heading slugs) is stable across parser upgrades as long as headings are detected; **block ordinal within its section** is far more stable than a document-global index.
- **Page span** is deterministic for a fixed source file — the strongest anchor component; always store it and cite it.
- **Content hash** enables re-ingestion reconciliation: after re-parse, match old→new anchors by (exact hash) → (same heading path + fuzzy text match) → mark orphaned. Citations reference anchor IDs in Learny's DB, so old sessions keep resolving via the reconciliation map even if slugs shift.
- Do not use bboxes or char offsets as primary anchors (parser-version-fragile); optionally store bbox as display metadata for a future PDF viewer highlight.
- Key simplification: since source files are content-addressed in S3, "re-ingestion" of the *same* file with the *same* Docling version is deterministic; the hash-match path only matters on parser upgrades — make reconciliation an explicit migration step, not a runtime concern.

## 4. EPUB hardening heuristics (for the QA findings)

What Calibre/Readium-class tools do, mapped to Learny's issues ([Calibre conversion docs](https://manual.calibre-ebook.com/conversion.html), 9.11.0, 2026):

1. **Flat TOC → infer hierarchy from headings.** When nav/NCX is flat but spine HTML has h1/h2/h3, rebuild section depth from heading levels in reading order, and reconcile: TOC gives titles/entry points, headings give nesting. Calibre's chapter detection defaults to h1/h2 whose text matches `chapter|book|section|part\s+` (case-insensitive) or `@class='chapter'` — adopt this regex family (plus localized variants later) for "is this a real chapter heading?".
2. **Filename-derived titles (`part0034`) → title inference cascade:** (a) TOC label if non-generic; (b) first h1–h3 in the spine item; (c) first `<title>` in the XHTML head; (d) first non-empty paragraph if short (<80 chars) and styled like a heading (centered/bold/all-caps — Calibre's "detect unformatted chapter headings" heuristic); (e) fallback `"Untitled section (p. N)"` — never surface raw filenames. Treat as generic: matches `^(part|split|index|text|ch)?[_-]?\d+$` or equals the file stem.
3. **Content attached to caption-level/mid-file anchors → anchor promotion + section merging.** When a TOC entry points to a fragment ID on a non-heading element (caption, span), snap the section boundary to the nearest enclosing/preceding heading; if none, treat the entry as a link, not a section boundary (Calibre's hyperlink-fallback TOC does the reverse — it only *supplements* with links when detected chapters fall below a threshold, confirming links ≠ structure).
4. **Trivial-section merging.** Merge a section into its successor/parent when it has <N words (e.g. <30) and no heading of its own, or when it contains only an image/caption. Keep original anchors alive by mapping merged sections' anchors to the surviving section (anchor aliasing table) so citations never dangle.
5. **Gutenberg noise stripping.** Delimit body with the standard markers `*** START OF THE PROJECT GUTENBERG EBOOK ... ***` / `*** END OF ... ***`; drop license/boilerplate outside them; also drop spine items whose TOC label matches transcriber/colophon patterns. (Same category as Docling's `furniture` — model "furniture" explicitly in the corpus rather than ad-hoc deletes, flagged not destroyed.)
6. **Heading-level normalization** (shared with PDF): clamp level jumps, demote duplicate consecutive identical headings, renumber (Calibre does "renumbering sequential heading tags" in its heuristic stage).
7. Note: EPUB CFI (Readium/epub.js's precise-location scheme) is the standards answer for *intra-document* positions, but it's brittle under content normalization; Learny's `spine-href + fragment-id + heading path` anchors are the right granularity — don't adopt CFI.

Implement 1–6 as a **format-agnostic corpus normalization pass** (post-parser, pre-persist) so PDF and EPUB share it; only Gutenberg stripping and anchor snapping are EPUB-adapter-specific.

## 5. Alternatives comparison + verdict

| Tool | License | Structure fidelity | CPU fit | Notes (2026) |
|---|---|---|---|---|
| **Docling 2.112** | MIT, LF-hosted | Headings+levels, reading order, tables (97.9% complex-table acc. per [Procycons benchmark](https://procycons.com/en/blogs/pdf-data-extraction-benchmark/)), page prov | Yes (~1–3 s/page) | Typed doc tree; models pre-bakeable |
| [marker](https://github.com/datalab-to/marker) | **GPL-3 code + OpenRAIL-M weights, free only <$2M revenue** ([LICENSE](https://github.com/datalab-to/marker/blob/master/LICENSE)) | Very good; benchmark-competitive (0.861 vs Docling 0.877 on opendataloader-bench per [pdfmux blog](https://pdfmux.com/blog/pdfmux-vs-pymupdf-vs-marker-vs-docling/), vendor-run — treat cautiously) | Wants GPU (5–10x slower CPU) | License poison for an MIT-style OSS repo |
| [unstructured](https://pdfmux.com/blog/pdfmux-vs-llamaparse-vs-docling-vs-unstructured-2026/) | Apache 2.0 (open core) | Element-typed but weaker heading hierarchy; enterprise/many-format focus | Yes | Overkill breadth, weaker doc tree |
| PyMuPDF4LLM | **AGPL-3** ([PyMuPDF](https://github.com/pymupdf/pymupdf)) | Markdown-ish, weak hierarchy/tables; 10–50x faster on native PDFs | Excellent | AGPL + fidelity gap; not worth a second adapter |

**Verdict: Docling stays the pick for PDF** — the only option combining permissive license, CPU viability, a real structured document model with page provenance, and active LF governance. Marker is the quality runner-up but its license is incompatible with Learny's OSS-ready goal. Keep **ebooklib for EPUB** (Docling's EPUB/HTML backend loses anchors — [issue #2929](https://github.com/docling-project/docling/issues/2929)); revisit only if that issue is fixed.

**Uncertainties flagged:** pdfmux benchmark numbers are vendor-published; Docling per-page timings are from its own technical report on papers/Redbooks, not book-length PDFs (expect variance on heavy-layout books); exact RAM ceiling for the standard pipeline in a container is not officially documented (community reports suggest 2–4 GB; validate empirically — cf. pathological cases like [issue #2635](https://github.com/docling-project/docling/issues/2635)).

Sources: [Docling GitHub](https://github.com/docling-project/docling) · [docling PyPI](https://pypi.org/project/docling/) · [DoclingDocument docs](https://docling-project.github.io/docling/concepts/docling_document/) · [Chunking docs](https://docling-project.github.io/docling/concepts/chunking/) · [Model catalog](https://docling-project.github.io/docling/usage/model_catalog/) · [Advanced options](https://docling-project.github.io/docling/usage/advanced_options/) · [Docling technical report](https://arxiv.org/html/2408.09869v4) · [docling-serve models](https://github.com/docling-project/docling-serve/blob/main/docs/models.md) · [Perf discussion #306](https://github.com/docling-project/docling/discussions/306) · [Issue #2929 anchors stripped](https://github.com/docling-project/docling/issues/2929) · [Issue #515 EPUB backend](https://github.com/DS4SD/docling/issues/515) · [Calibre conversion manual](https://manual.calibre-ebook.com/conversion.html) · [marker LICENSE](https://github.com/datalab-to/marker/blob/master/LICENSE) · [marker repo](https://github.com/datalab-to/marker) · [PyMuPDF repo](https://github.com/pymupdf/pymupdf) · [pdfmux 200-PDF benchmark](https://pdfmux.com/blog/pdfmux-vs-pymupdf-vs-marker-vs-docling/) · [pdfmux 2026 comparison](https://pdfmux.com/blog/pdfmux-vs-llamaparse-vs-docling-vs-unstructured-2026/) · [Procycons PDF benchmark](https://procycons.com/en/blogs/pdf-data-extraction-benchmark/) · [Tensorlake citation-aware RAG](https://www.tensorlake.ai/blog/rag-citations) · [buzzi.ai citation architecture](https://buzzi.ai/insights/ai-document-retrieval-rag-citation-architecture)
