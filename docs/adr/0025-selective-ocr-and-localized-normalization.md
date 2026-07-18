# ADR-025: Selective OCR For Scanned PDFs And Localized Corpus Normalization

- **Date**: 2026-07-17
- **Status**: Accepted
- **Deciders**: Augusto, Claude
- **Tags**: ingestion, pdf, ocr, docling, normalization, language, portuguese

## Context and Problem Statement

The Docling PDF adapter (ADR-0022) ran with OCR hard-off: a scanned or image-only
PDF produced no extractable text and failed ingestion terminally. Separately, the
corpus normalization pass was locale-blind — its generic-title patterns and
structure heuristics were English-centric module constants — and PDFs never
carried a language at all (the parser sets none), which also left every PDF
corpus on the `simple` full-text-search configuration despite the language-aware
FTS layer added with the real-embeddings work. For a library that is largely
Portuguese, both gaps land on the same books.

This cycle ran before the eval-maturity cycle by explicit reorder: eval maturity
needs provider keys that do not exist yet, while this work is entirely key-free.

## Decision Drivers

- Scanned books must ingest without the user knowing or declaring that their PDF
  is scanned; born-digital PDFs must not pay an OCR tax.
- No schema, API, or frontend change for an ingestion-quality concern.
- CI stays docling-free and offline; live proofs live in the gated suite.
- Provider/dependency discipline: no new runtime dependencies for language
  detection; OCR reuses what the pdf-worker image already carries.
- Localization must be additive data, not forked code paths, and must leave
  existing (English/neutral) corpora byte-identical.

## Considered Options

### OCR trigger

1. **Automatic single retry** — chosen. Fast path with OCR off; only a
   successful-but-textless conversion retries once with OCR; still textless is
   terminal. Conversion *errors* never retry.
2. Per-upload flag — needs a sources column, API field, and frontend control,
   and asks the user to know their file's internals.
3. Always-on OCR — multiplies conversion cost for every born-digital PDF.

### OCR engine

1. **EasyOCR via Docling** — chosen. Its heavy dependencies (torch/torchvision)
   are already in the pdf-worker image via docling's own chain, and its
   Portuguese support is explicit (`lang=["en","pt"]`). Build reality found
   during the cycle: our docling version does not bundle EasyOCR, so it is an
   explicit `pdf`-extra dependency (`easyocr>=1.7,<2` — additive lock change
   only), and its opencv chain needs `libgl1`/`libglib2.0-0`/`libxcb1` in the
   image; models are baked at build like layout/tableformer (no runtime
   downloads, verified). Languages configurable (`LEARNY_PDF_OCR_LANGS`).
2. RapidOCR — ships with docling (zero dependency delta) but selects models by
   script rather than an explicit language list; Portuguese coverage is the
   uncertainty this decision refuses to take on.
3. Tesseract — a system package plus traineddata lifecycle inside the image.

### PDF language

1. **Pure stopword-ratio detector** (en/pt tables, minimum sample, hit-density
   and winner-ratio gates, `None` on ambiguity) — chosen; runs in the corpus
   build only when the parser declared no language, so EPUB OPF metadata always
   wins.
2. A detection library — a new runtime dependency for a two-language problem.
3. No detection — leaves every PDF locale-blind and on `simple` FTS.

### Localization mechanism

1. **A per-language heuristics table** consulted by the normalization pass via
   the book's own language tag — chosen. The neutral row *is* the historical
   constant set (and the `en` row equals it, since those constants were always
   the English family); the `pt` row adds filename-stem patterns
   (`capitulo0003`-style) and part/chapter/front-matter keywords that drive a
   keyword fallback for flat-TOC hierarchy inference. New languages are new
   rows.
2. Settings-driven knobs — makes corpus output environment-dependent and breaks
   the pass's purity contract.

## Decision Outcome

`DoclingPdfParser` now takes `ocr_enabled`/`ocr_langs` from settings
(`LEARNY_PDF_OCR_ENABLED` default true — the kill-switch reproduces the pre-OCR
behavior exactly, for images without baked OCR models — and
`LEARNY_PDF_OCR_LANGS`). The retry constructs
`PdfPipelineOptions(do_ocr=True, ocr_options=EasyOcrOptions(lang=…))` — API
verified against the pinned docling v2.112.0 source. The pdf-worker image bakes
the EasyOCR models alongside layout/tableformer (`with_easyocr=True`).

`BuildCorpus` fills a missing language by detection over a bounded opening
sample; the tag flows into the existing corpus `language` column, whose trigger
already maps `pt` to the `portuguese` FTS configuration — scanned or born-digital
Portuguese PDFs now get stemmed lexical retrieval and localized normalization
from the same forty-line pure module. Mixed, short, or foreign samples stay
`None`, which downstream treats exactly as before.

Coverage: the retry policy, option payloads, detection gates, and PT heuristics
are all CI-tested (docling-free, via faked docling modules and pure fixtures);
the end-to-end scanned proof is a code-generated image-only PDF (a hand-rolled
bitmap-font raster — no binary fixtures, no new dependencies) in the
docling-gated live suite, paired with a kill-switch case proving the same bytes
fail without OCR. The proof was executed for real in the built pdf-worker image
under the compose 4 GiB memory cap: the scanned page ingested through the OCR
retry in ~48 s (cold engine init included; the recognized text contained the
rendered word), the kill-switch case and the blank page both stayed terminal,
and every model loaded from the baked cache with no network egress. The built
image is ~7.0 GB (the pre-existing torch/CUDA weight plus OCR models — the
size follow-up recorded in ADR-0024 stands unchanged).

Known accepted limits: a mixed PDF (some text pages, some scanned) takes the
fast path — its scanned pages stay unread until a page-level heuristic is ever
justified; OCR quality tuning, further languages, and scanned-page detection
finer than "no text at all" are out of scope.

## Consequences

- Positive: scanned Portuguese books — the main personal-library format this
  project exists for — ingest, retrieve with proper stemming, and normalize with
  native structure keywords; no user-facing surface changed; CI stays offline.
- Negative: the pdf-worker image grows by the EasyOCR models; a fully scanned
  book converts twice (once to discover it needs OCR); detection is deliberately
  crude and abstains rather than guesses.
- Follow-ups: none required; revisit OCR-language coverage and mixed-PDF
  page-level OCR only when a real book hits the limit.
