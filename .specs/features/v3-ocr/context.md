# v3-ocr — Decision Context

Auto-decided per learny-ship-cycle rules. Mirrored as AD-103..AD-108 in `.specs/project/STATE.md`.

## D-0 — Cycle order: C before B (AD-103, user-confirmed)

Cycle B (eval maturity) requires real provider keys; none exist (no repo secrets, no local env, nightly eval green-skips, no `eval-results` history). **User chose (2026-07-17): run key-free Cycle C now; B follows once keys are provided.** Alternatives — provide keys immediately (blocks on user provisioning) or hold the pipeline — declined by the user.

## D-1 — OCR trigger (AD-104)

- **Automatic retry (CHOSEN)**: fast path `do_ocr=False`; if no extractable text, retry once with OCR; still empty → terminal error. Why: targets exactly the current failure point (`_has_text` guard), zero schema/API/frontend change, born-digital PDFs pay nothing, scanned PDFs pay one extra conversion on a concurrency-1 queue. Why not: a fully scanned book converts twice (accepted at author scale); mixed text/scanned PDFs take the fast path and skip OCR (accepted, recorded in ADR).
- Per-upload flag: user must know their PDF is scanned; needs a sources options column + Form field + frontend — large blast radius for worse UX.
- Always-on OCR: multiplies cost for every born-digital PDF for zero benefit.

## D-2 — OCR engine (AD-105)

- **EasyOCR via Docling (CHOSEN)**, models baked at build (`with_easyocr=True`), languages from `LEARNY_PDF_OCR_LANGS` default `en,pt`. Why: Docling's default engine; torch — its heavy dependency — is already in the pdf-worker image (the CUDA stack recorded in ADR-0024), so the increment is model files only; Portuguese supported. Why not: adds ~100–200 MB of models to an already-large image (accepted; image never in default `up`).
- RapidOCR: lighter runtime but adds an onnxruntime dependency chain docling doesn't pull by default here — new third-party surface for no capability gain.
- Tesseract: system package + traineddata management inside the image; more moving parts than reusing the torch already present.
- Kill-switch `LEARNY_PDF_OCR_ENABLED=true`: operational escape hatch (e.g. an environment whose image lacks baked models); disabled reproduces today's behavior exactly, keeping a clean rollback semantic.

## D-3 — PDF language detection (AD-106)

- **Pure stopword-ratio detector, en/pt tables, confidence-gated, fills `ParsedBook.language` only when None (CHOSEN)**. Why: PDFs never carry a language today, so they get `simple` FTS (a real retrieval loss the language-aware trigger from the embeddings cycle was built to fix) AND would be excluded from localized normalization — detection unlocks both consumers with ~40 lines of pure code and zero dependencies. EPUB OPF language is never overridden. Why not: stopword detection is crude for short books — mitigated by a minimum-sample and confidence threshold that fall back to None (today's behavior).
- A language-detection library (langdetect/lingua): a new runtime dependency for a two-language problem; rejected per the edges-only dependency policy.
- No detection (thread language only where present): leaves every PDF locale-blind — defeats the cycle's normalization goal for the author's main format.

## D-4 — Localization mechanism (AD-107)

- **Per-language heuristics table consulted by `normalize_book` via `book.language` (CHOSEN)** — `en`/`pt` entries + neutral fallback covering today's constants; module stays pure (no I/O, no settings), languages are additive data. Why not considered-alternatives: a Settings-driven table breaks the module's purity contract and makes tests environment-dependent; subclassed per-language normalizers are structure for two data tables.

## D-5 — Scanned-fixture realization (AD-108)

- **Live-gated end-to-end synthetic scanned PDF + CI-safe stubbed-converter unit tests (CHOSEN)**; `GOLDEN_FIXTURES` (CI, docling-free) unchanged. Why: goldens run in docling-free CI where OCR cannot execute; the no-binary-fixtures convention means the scanned PDF is generated in code (image-only pages) inside the `importorskip("docling")` suite, matching how live PDF tests already work. The OCR retry logic itself is CI-tested through the stubbed `_convert` seam. Why not: a committed scanned-PDF binary would break the generated-fixtures convention; putting OCR in `GOLDEN_FIXTURES` would silently skip in CI and rot.
