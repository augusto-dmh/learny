# Learny current shipped state and recommendation ledger (as of main @ 9b485f2, 2026-09-30)

All paths are relative to `/home/augusto/projects/learny`. Everything below was read from the working tree and git history; no web sources. "Shipped" means merged to `main` and named in `.specs/project/ROADMAP.md` or `docs/rfc/0007-public-launch-roadmap.md` with a PR number. Where I could not confirm from code or docs I say "unverified".

Release ladder (git tags): v0.1.0 MVP → v0.2.0 RFC-002 → v0.3.0 RFC-003 → v0.4.0 RFC-004 → v0.5.0 RFC-006 → v0.6.0 RFC-005 → v0.7.0 RFC-0007 + house profiles (PR #71). PR #72 (portfolio-truthful, merged 2026-09-27, `1d189ac`) is the last merge — [`.specs/project/ROADMAP.md`](.specs/project/ROADMAP.md) lines 148–158; [README.md](README.md) line 218.

---

## KQ1 — Exactly which learner-facing features, AI capabilities, ingestion formats, and deployment shape exist today?

### Takeaway
Learny today is a complete single-loop product: EPUB+PDF ingestion with preserved structure → hybrid pgvector/FTS retrieval bound to reading position → streaming cited Ask and a hint-ladder Tutor in one Chat dock inside a paper-styled reader → highlights/notes that join retrieval → grounded quiz cards on FSRS with undo/flag/bounded session → Anki and Obsidian export → open-registration safety rails (invite, spend cap, quotas, deletion, email) → learner-chosen house AI profiles. It has no i18n, no public hosted instance, no mobile app, no local-model path, no knowledge graph.

### Cited Findings — user-facing surfaces (frontend routes)
- Route inventory: `/` (landing), `/login`, `/register`, `/home`, `/sources` (Library), `/sources/[id]/ask` and `/sources/[id]/teach` (redirect aliases into the reader Chat dock), `/sources/[id]/read` (the reader, own layout group), `/notes`, `/notes/[id]`, `/review`, `/account`, `/dev/evals` (dev-only), `/terms`, `/privacy`, `/copyright`, and the catch-all same-origin proxy `app/api/[...path]/route.ts` — [frontend/app](frontend/app) directory listing (`find frontend/app -name page.tsx`).
- **Landing page**: static, 49 lines, one quote from *The Art of War* with locator, two CTAs (Create account / Log in), no live model call — [frontend/app/page.tsx](frontend/app/page.tsx); spec decision "Signed-out `/` shows a static cited-answer proof … No live model call" — [.specs/features/first-session-converts/spec.md](.specs/features/first-session-converts/spec.md) line 54.
- **Library / upload**: multipart upload through FastAPI (ADR-0018), file picker accepts EPUB and PDF, one **Open** per book plus overflow verbs (Ask, Tutor, Review, Re-ingest, Download notes), ingest-wait copy pointing at the sample; naming pass "Library, Tutor, Download notes" — [.specs/features/first-session-converts/spec.md](.specs/features/first-session-converts/spec.md) lines 12–13, 51–52; [README.md](README.md) line 198.
- **Shared sample book**: one operator-owned, pre-ingested Standard Ebooks *The Art of War* (`is_sample`), embeddings never cloned per user; canned question `What does Sun Tzu mean by "all warfare is based on deception"?`; five starter cards cloned per user with own FSRS rows — [backend/app/application/sample.py](backend/app/application/sample.py) docstring; spec lines 9–11, 42–48; migrations `0022_sample_and_activation.py`, `0023_starter_quiz_origin.py` ([backend/migrations/versions](backend/migrations/versions)).
- **Reader (`/read`)**: chapter flow, paper "Iron Gall" appearance (ADR-0027), figures extracted at ingest to MinIO and served same-origin as WebP `<img>` (never iframed EPUB HTML), immersive chrome with `[`/`]` toggling TOC and dock, 65ch measure preserved, receding top bar, page unit (~275 words) with live progress and resume position — [README.md](README.md) lines 115–117; [.specs/features/reader-people-read-in/spec.md](.specs/features/reader-people-read-in/spec.md) lines 9–11, 38–51; `"[": () => setTocOpen` at [frontend/app/components/chapter-reader.tsx](frontend/app/components/chapter-reader.tsx) line 675.
- **Phone support (responsive web, not native)**: below `lg` the dock is a shadcn `Sheet side="bottom"`, touch capture via `pointerup`/`selectionchange`, 44px targets, no horizontal scroll at 200% zoom — spec lines 11, 46–47; `Sheet` import and "Study surfaces for this book, as a bottom sheet" at [frontend/app/components/reader-panel.tsx](frontend/app/components/reader-panel.tsx) lines 37–42, 454–486. No PWA manifest, no service worker: `frontend/public` does not exist and no `manifest`/`serviceworker` hits in `frontend/app` (grep).
- **Ask (cited Q&A)**: one unified grounded-conversation model (ADR-0029) scoped by a list of section anchors (empty = whole book); streaming via SSE / UI Message Stream; claim-level `CitedSpan` from Anthropic `cited_text` offsets with hover quote and "Show in book"; failed turn persists with retry, conversation never deleted; abstention sentinel `NOT_FOUND_IN_SOURCE`; "Search my notes too" toggle (Ask default on, Teach default off) — [docs/adr/0029-unified-grounded-conversations.md](docs/adr/0029-unified-grounded-conversations.md) lines 38–62; [.specs/features/trustworthy-cited-ask/spec.md](.specs/features/trustworthy-cited-ask/spec.md) lines 11, 35–41; [README.md](README.md) lines 105, 116–118, 201–202. Note: ADR-0029 scope is anchors within **one book**; README line 116 says "a book, a section, or the whole library" but `conversations.py` docstring says "empty means the whole book" ([backend/app/application/conversations.py](backend/app/application/conversations.py) line 4) — whole-library (multi-source) Ask is **unverified / likely not shipped** (rq01 move 10 "Shelf-level Ask" has no code hits).
- **Teach / Tutor**: frozen playbook (pump → hint → prompt → assert), tutor opens the session with section-first retrieval, application-owned `tutor_phase`/`hint_level` on `conversations`, closes after an unaided check and offers exactly one FSRS card (opt-in), "just explain" stays one tap, Ask+Teach merged into one **Chat** dock tab (Answer | Tutor) — [.specs/features/teach-becomes-tutor/spec.md](.specs/features/teach-becomes-tutor/spec.md) lines 9–12, 20, 37–45; migrations `0019_tutor_state.py`, `0020_tutor_cards.py`.
- **Selection Explain**: popover "Explain" turns ride a separate house-routed explain chain (Haiku by profile), origin marker preserved on retry — [backend/app/infrastructure/web/dependencies.py](backend/app/infrastructure/web/dependencies.py) lines 700–706; `generation_explain_profile` in [backend/app/core/config.py](backend/app/core/config.py) line 252; STATE.md handoff for PR #69.
- **Spoiler-safe retrieval**: Ask/Teach/`/retrieve` book arms are bound to the reader's section position; unmatched anchor or position-read failure fails closed — [.specs/project/ROADMAP.md](.specs/project/ROADMAP.md) line 107 (PR #70, merged 2026-09-08).
- **Quiz / Review / spaced repetition**: Celery deck pipeline generates free-recall and single-mask cloze items with citation snapshots and server-side QC (verbatim containment, embedding dedup, formulation gates: one fact, no stopword clozes, no set dumps); **FSRS-6** via `fsrs` lib behind `SchedulingPort`; cross-source due queue; append-only `review_log`; compensating **undo**; bucketed interval labels on grade buttons; learning-step requeue in session; **flag** (`flagged_at`) and content-only **edit** from review; session page of 20 with **Done-for-today**; empty-deck honesty with twelve discard reason codes; Anki `.apkg` export with stable GUIDs — [README.md](README.md) lines 96–98, 203–204; [.specs/features/review-worth-returning/spec.md](.specs/features/review-worth-returning/spec.md) lines 11–14, 44–58; migration `0021_review_quality.py`; STATE.md PR #66 handoff.
- **Progress / study**: Home with two cards, **study heatmap** (`GET /api/study/days`), 14-day adherence window, `GET /api/reading/continue` resume; **no consecutive streak counter** (explicitly excluded) — [README.md](README.md) lines 117, 209; [backend/app/application/study.py](backend/app/application/study.py) lines 33–50; RFC-0007 Exclusions "No gamification: streaks, XP, badges…" ([docs/rfc/0007-public-launch-roadmap.md](docs/rfc/0007-public-launch-roadmap.md) line 219). README line 220 says "Home with streak and heatmap" — the "streak" there is the rolling-adherence figure, not a Duolingo consecutive-day counter (rq08 §1 "Heatmap + rolling adherence (already shipped)").
- **Notes / highlights / second brain**: reader selection → highlight or Markdown note anchored to a corpus anchor and snapshotted; tags; note↔note and note↔section links with backlinks panel; notes join hybrid retrieval as two extra RRF arms (opt-in per conversation); note → review cards via `POST /api/notes/{id}/cards/suggest`; note edits rewrite matched cards in place without touching FSRS; Obsidian vault export `GET /api/export/vault` (deterministic zip, one-way) — [README.md](README.md) lines 100–109, 205–207; [docs/adr/0026-notes-and-second-brain-domain-model.md](docs/adr/0026-notes-and-second-brain-domain-model.md).
- **Onboarding / activation**: server-side once-per-user activation events `account_created`, `sample_opened`, `first_cited_answer`, `first_review` (closed name set, insert-on-conflict-do-nothing, no public GET) — [backend/app/application/activation.py](backend/app/application/activation.py) lines 15–25; spec line 45. No product tour, no guest path (spec line 41: "Authenticated only. Unauthenticated sample GET/Ask remain 401").
- **Account**: email/password (Argon2id, HttpOnly cookie sessions, CSRF), ToS acceptance stamp, email verify + password reset through `EmailPort` (SMTP adapter, log adapter offline), **account deletion** (deletes MinIO objects then cascades Postgres), **AI profile selector** — [README.md](README.md) lines 120, 124–127, 197, 208; migrations `0026_user_tos_stamp.py`, `0027_email_verify_reset.py`, `0029_user_ai_preferences.py`; [frontend/app/components/AccountPanel.tsx](frontend/app/components/AccountPanel.tsx) ("AI profile", "delete").
- **Sharing / export**: export only (Anki `.apkg`, Obsidian vault zip). No share links, no public decks: grep `share_link|/share` in backend/app and frontend/app → 0 hits; RFC-0007 exclusion "No public surface carrying book bytes or book-derived cards" (line 220).
- **Legal pages**: `/terms`, `/privacy`, `/copyright` with DMCA contact — [.specs/features/safe-to-open-the-doors/spec.md](.specs/features/safe-to-open-the-doors/spec.md) line 13; route listing.
- **Languages / i18n**: **none for the UI**. `<html lang="en">` hard-coded ([frontend/app/layout.tsx](frontend/app/layout.tsx) line 33); no `next-intl`/i18n dependency in [frontend/package.json](frontend/package.json); all copy is inline English. **Content-side Portuguese support exists**: stopword language detector for `en` and `pt` ([backend/app/application/language.py](backend/app/application/language.py) lines 1–40); FTS regconfig map `pt → portuguese` plus 14 other snowball languages ([backend/app/application/text_search.py](backend/app/application/text_search.py) lines 18–35); OCR default `pdf_ocr_langs = "en,pt"` ([backend/app/core/config.py](backend/app/core/config.py) line 140); quiz QC stopword list is "Closed English ∪ Portuguese function words (AD-308)" ([backend/app/application/quiz_qc.py](backend/app/application/quiz_qc.py) line 81); normalization comments mention Brazilian/Portuguese ebook filename families ([backend/app/application/normalization.py](backend/app/application/normalization.py) line 80). Latin font subset chosen because it "covers Portuguese diacritics" (layout.tsx line 15).

### Cited Findings — AI capabilities
- **Providers (locked)**: embeddings OpenAI `text-embedding-3-large@1536` behind `EmbeddingPort` with per-chunk model versioning (ADR-0019, Accepted); generation Anthropic Claude behind `GenerationPort` (ADR-0020, Accepted; amended 2026-09-07 "Multi-Profile Generation Routing" and 2026-09 "End-User Choice Among House Profiles") — [docs/adr/0019-…](docs/adr/0019-use-openai-embeddings-with-per-chunk-model-versioning.md) line 4; [docs/adr/0020-…](docs/adr/0020-use-anthropic-claude-for-generation.md) lines 4, 166, 235.
- **Deterministic offline defaults**: `LEARNY_EMBEDDING_PROVIDER=local`, `LEARNY_GENERATION_PROVIDER=local` — [backend/app/core/config.py](backend/app/core/config.py) lines 177, 237; CI runs with no keys ([README.md](README.md) line 150).
- **Model defaults in code**: generation default `claude-sonnet-5` (RFC-005 Cycle C kept it; ROADMAP line 104), judge `claude-opus-4-8` (config line 253; flipped in PR #59, ROADMAP line 103), quiz `claude-haiku-4-5` batched via Message Batches (config line 322).
- **Profile registry + router (Cycle G, PR #69)**: `LEARNY_GENERATION_PROFILES` JSON list; kinds `local | anthropic | openai-compatible`; per-profile effort (`effort_ask`/`effort_teach`), max_tokens, four price fields, `grounding ∈ {verified-spans, prompt-cited, none}`, `ask_enabled`/`teach_enabled`, learner-facing `display_name`/`description` — [backend/app/infrastructure/providers/profiles.py](backend/app/infrastructure/providers/profiles.py) lines 37–100. Routing adapter with Learny error taxonomy, transport fail-over, rate-limit backoff — [backend/app/infrastructure/answering/routing.py](backend/app/infrastructure/answering/routing.py). OpenAI-compatible prompt-cited adapter — [backend/app/infrastructure/answering/openai_compat.py](backend/app/infrastructure/answering/openai_compat.py).
- **Economy profile**: Fireworks-US-hosted GLM-5.3-Flash declared but shipped **inert** ("ask/teach-disabled, commented-out env example") — [.specs/features/cheaper-intelligence/spec.md](.specs/features/cheaper-intelligence/spec.md) lines 21, 51; STATE.md PR #69 handoff; README line 119 "an economy tier stays inert until the nightly judge gate promotes it".
- **House profiles (PR #71)**: one `user_ai_preferences` row per user (`user_id` PK, `profile_id` text) — [backend/app/infrastructure/db/metadata.py](backend/app/infrastructure/db/metadata.py) lines 939–951; chosen profile leads the chain, stale choice falls back to operator default with a warning; covers Ask/Teach only (Explain, quiz, cards stay house-routed); endpoints `GET /api/ai/profiles`, `GET/PUT/DELETE /api/me/ai-profile` — ADR-0020 amendment points 1–9; README line 208.
- **Citations mechanism**: Anthropic Citations API (one plain-text document per evidence chunk, `document_index → chunk_id`) with application-layer grounding that discards cited chunk ids outside retrieved evidence (AD-027/AD-060); claim-level spans from `cited_text` offsets (AD-265/266/269); for non-Anthropic profiles, prompt-cited markers verified by the grounding intersection — STATE.md AD-027, AD-060; profiles.py `GROUNDING_KINDS` comment.
- **Eval gates**: golden fixtures (ADR-0016) run every PR offline; silver tier (git-ignored real books) + anchored rubric (eval-deepening, PR #46); nightly `eval.yml` cron `0 3 * * *` with `LEARNY_EVAL_GATE=1`, thresholds faithfulness ≥ 0.90 / relevancy ≥ 3.1 / `citation_valid` 12/12 under the Opus judge (ADR-0028 decline semantics); candidate-run override input for promoting a profile — [.github/workflows/eval.yml](.github/workflows/eval.yml) lines 16, 21, 99–100; ROADMAP line 103. **The nightly has been red since 2026-07-27** because the Anthropic account behind the CI key has no credit (62 runs; last green 2026-07-26); the workflow now annotates "Anthropic balance exhausted" — eval.yml lines 113–117; STATE.md handoff operator item (2). Last committed result files are dated 2026-07-31 ([backend/evals/results](backend/evals/results)).
- **Budgets / rails (Cycle F, PR #68)**: Redis shared rate limiter keyed on `user_id` for expensive routes and trusted-proxy IP for auth (fail-closed); per-user daily AI spend cap `daily_ai_spend_usd = 0.5` on a Postgres ledger priced at the serving profile's catalog; operator kill switch; source count/byte quotas and in-flight ingestion cap; `invite_required` flag (default false; production example true) with invite codes and disposable-domain deny-list; **no Turnstile** (deferred, AD-325) — [backend/app/core/config.py](backend/app/core/config.py) lines 261–289; [backend/app/infrastructure/web/redis_rate_limit.py](backend/app/infrastructure/web/redis_rate_limit.py); doors spec lines 39–54; migrations `0024_safety_rails.py`, `0025_invite_codes.py`, `0028_quiz_deck_spend_marker.py`.
- **Instrumentation / observability**: request/query/task timings with `Server-Timing`, dev-only `/api/dev/instrument` and `/api/dev/evals`; structured JSON logs with trace ids; `/healthz`, `/readyz` — [README.md](README.md) lines 129–131, 210.

### Cited Findings — ingestion
- **EPUB** via ebooklib and **PDF** via Docling behind one `DocumentParserPort`, selected by content type; PDF runs on an isolated `worker-pdf` service with bounded memory and baked models; shared deterministic normalization pass (title inference, hierarchy re-derivation, trivial-section merge with anchor aliases, Gutenberg marker stripping) — [README.md](README.md) lines 70–82; [docs/adr/0022-…](docs/adr/0022-pdf-ingestion-via-docling-and-corpus-normalization.md) (Accepted 2026-07-17); ROADMAP line 33 (RFC-002 Cycle F, PR #26).
- **Scanned PDFs**: selective OCR with EasyOCR, languages `en,pt` by default, plus localized normalization — [docs/adr/0025-…](docs/adr/0025-selective-ocr-and-localized-normalization.md); ROADMAP line 49 (PR #29); `pdf` optional extra in [backend/pyproject.toml](backend/pyproject.toml) lines 38–42.
- ADR-0011 ("EPUB first", Accepted 2026-06-27) is not superseded in text but its deferral "Defer PDF ingestion until the EPUB-based corpus and tutor path are working" (line 40) has been fulfilled by ADR-0022. The `epub-ingestion` skill description still says "Not for PDF or other formats (deferred, ADR-0011)" — stale relative to the code.
- **Not supported**: DOCX, HTML, Markdown, plain text, URLs, YouTube/RSS (ADR-0011 line 10 lists them as "may eventually"; no parser adapters exist under [backend/app/infrastructure/ingestion](backend/app/infrastructure/ingestion) besides `epub.py` and `docling_pdf.py`).
- **Figures**: raster images extracted at ingest, re-encoded WebP, stored in MinIO, served same-origin; SVG dropped; already-ingested books need re-ingest — reader spec lines 38, 48, 51.

### Cited Findings — deployment and multi-tenancy
- Local: `docker compose up --build`, services `db`, `db-restore`, `redis`, `minio`, `api`, `worker`, `worker-pdf`, `web` — [docker-compose.yml](docker-compose.yml). Production overlay adds `backup`, `monitoring`, `caddy` (only host-exposed service, 80/443) — [docker-compose.prod.yml](docker-compose.prod.yml); ADR-0023, ADR-0024, ADR-0030.
- CI → six GHCR images (`learny-{backend,pdf-worker,web,backup,postgres,minio}`) on every green `main`; SSH deploy to `/opt/learny` only when `VPS_HOST`/`VPS_USER`/`VPS_SSH_KEY` secrets exist, otherwise the deploy job exits green — [.github/workflows/deploy.yml](.github/workflows/deploy.yml) lines 71–122; [README.md](README.md) line 176.
- **No public instance is hosted.** README line 5: "no public instance is hosted yet"; ROADMAP line 157: "no public instance is hosted"; STATE.md handoff operator item (1): "flip the GHCR `learny-minio` package public before any VPS deploy … no public instance is hosted yet". (Earlier handoffs for PR #70 say "the merge auto-deploy (GHCR→VPS) took the RFC-005 rollout", implying a VPS existed at some point in 2026-09; the current README and STATE.md state that none is public today. Treat "was a private VPS ever live" as unverified.)
- MinIO image is now built from the official release binary because quay.io refuses anonymous pulls (ADR-0031, PR #72) — ROADMAP line 157.
- Multi-tenancy readiness: all resources owner-scoped at query level, cross-user → 404; user-keyed limits; spend ledger; quotas; invite gate; deletion; legal pages; ToS stamp; email verify/reset. RFC-0007 Cycle F's stated purpose was exactly "registration is open behind rate, spend, and quota rails" — README lines 5, 120, 126. The remaining gap to a stranger using it is purely operational (a host, a funded key, flipping GHCR packages public, recording the demo).
- What a stranger must do today: clone the repo and run `docker compose up --build` (no keys → deterministic extractive answers, "not the product's answers" per [docs/media/README.md](docs/media/README.md) prerequisites), or additionally supply `secrets/local-ai.env` with Anthropic + OpenAI keys for real generation. Registration on self-host is open by default (`invite_required=false`).

### Inferences
- The five product pillars (read, ask, tutor, review, notes) are all built and the codebase enforces no sixth; every roadmap row is closed, so the next step must be chosen, not continued.
- Portuguese is supported as *content* (detection, FTS stemming, OCR, quiz stopwords) but the *product* is English-only; adding a pt-BR UI would be a new i18n cycle from scratch (no framework in place).
- Phone support is a responsive web layout, not a mobile product; no offline/PWA affordance exists.

### Gaps
- Whether whole-library (multi-book) conversations are possible is unverified; README wording and ADR-0029 conflict.
- Whether a private VPS was ever actually deployed (the PR #70 handoff mentions an auto-deploy rollout) is unverified; current docs say none is hosted.

---

## KQ2 — Which of the seven 09-03 bets and which per-RQ recommendations were delivered vs dropped?

### Takeaway
All seven bets shipped as RFC-0007 Cycles A–G (PRs #63–#69), with the recorded deviations: Cycle G as one cycle instead of the G1/G2 split, the economy profile inert, Turnstile and the opt-in due digest deferred, and the launch motion (Show HN) never executed. Of the broader per-RQ move lists, the "public-launch slice" items shipped; the pedagogy-deepening, growth, and "woven AI" items beyond the bets did not.

### Cited Findings — seven bets (synthesis → RFC-0007 → ROADMAP)
| Bet | Status | Evidence |
|---|---|---|
| 1 Trustworthy cited Ask | **SHIPPED** PR #63 | ROADMAP line 140; RFC-0007 Outcome line 262. The live 400 root cause was **an empty credit balance (`invalid_request_error`), not citations mixed with `output_config.format`** — STATE.md AD-272. |
| 2 A reader people read in | **SHIPPED** PR #64 | ROADMAP line 141; reader spec goals all `[x]`. |
| 3 Teach becomes a tutor | **SHIPPED** PR #65 | ROADMAP line 142; teach spec goals. |
| 4 Review worth returning to | **SHIPPED (one cycle, not 3–4)** PR #66 | ROADMAP line 143; review spec line 42 "This RFC letter is one ship-cycle PR". **Opt-in due digest NOT shipped** (deferred to Cycle F by AD-304, then out of Cycle F by AD-328 "digest is a later small cycle"). |
| 5 First session that converts | **SHIPPED** PR #67 | ROADMAP line 144; spec goals `[x]`. Guest Ask explicitly out (AD-320). Landing is static proof, not a "proof-above-fold marketing page" with demo media. |
| 6 Safe to open the doors | **SHIPPED** PR #68 | ROADMAP line 145. **Turnstile NOT shipped** (AD-325 "Deferred; no siteverify; invite code when the flag is on"). |
| 7 Cheaper intelligence | **SHIPPED (single cycle)** PR #69 | ROADMAP line 146; RFC-0007 Rationale line 268 names the deviation from the G1/G2 split. Economy profile inert; `effort=low` on Ask is "the judge-gated operator flip" not yet done (shipped defaults `medium`/`medium`) — STATE.md PR #69 handoff. |
| Post-arc: house profiles | **SHIPPED** PR #71 | ROADMAP line 156; ADR-0020 second amendment. |
| Launch motion (Show HN + self-host + sample) | **NOT DONE** | RFC-0007 Outcome line 262: "remains an operator action outside any cycle". Demo media not recorded (README line 11; STATE.md operator item 3). |

### Cited Findings — per-RQ cycle-sized moves (status against code/docs)
Legend: S = shipped, P = partial, N = not shipped, D = explicitly deferred with reason.

**rq01 Competitive landscape** ([docs/research/2026-09-03/rq01-competitive-landscape.md](docs/research/2026-09-03/rq01-competitive-landscape.md) lines 261–279):
1. Citation jump + quote hover — **S** (PR #63 `CitedSpan`).
2. Generation failure UX keep thread — **S** (PR #63).
3. Deck honesty — **S** (PR #66 twelve reason codes).
4. Landing + demo book — **P**: static landing shipped (PR #67); screenshots/GIF not recorded (README line 11).
5. Uploader copy + PDF/EPUB chips — **S** (PR #67 "EPUB and PDF upload copy").
6. Review UX "explain from source" opens citation — **P**: cards carry citation + "Open in book" since v2 (AD-079); a NotebookLM-style Explain at review is **N** (rq13 Cycle 4 "Review follow-up" has no code: grep `follow` in reviews → none).
7. Export affordances on Home/after first highlight — **P**: "Download notes" verb in library overflow (PR #67); unverified on Home.
8. Chapter/answer TTS — **N** (grep `speech|tts|SpeechPort` → 0 hits).
9. Teach default-on for a finished chapter — **N** (tutor-opens exists only when learner starts a Tutor session).
10. Shelf-level (multi-book) Ask — **N / unverified** (see KQ1).
11. Responsive review + ask on phone — **S** (PR #64 bottom-sheet dock).
12. Do-not-build list — honored (no mind maps, video, RSS, knowledge graph, outliner).

**rq02 Learning science** ([rq02](docs/research/2026-09-03/rq02-learning-science.md) lines 181–247):
1. Criterion learn-session after a section (successive relearning) — **N** (no `criterion`/`today_session` code; review spec line 30 chose "RFC session cap is the load shape").
2. Retrieval-first Teach hint ladder — **S** (PR #65).
3. Pretest on first open of a section — **N** (grep `pretest` → 0).
4. Rewrite Ask/Explain empty states to retrieve-not-summarize — **unverified** (not in any cycle spec; SUGGESTED_PROMPTS not audited here).
5. Learner-authored questions before AI suggestions — **N**.
6. Interleaved due-queue + contrast items — **P**: cross-source due queue interleaves by `due ASC` (AD-077); contrast items **N**.
7. Predict-then-reveal JOLs + calibration — **N** (grep `JOL` → 0).
8. Example/contrast quiz intents + teach-back — **N**.
9. Restore figures + plate cards — **P**: figures **S** (PR #64); plate/image cards **N**.
Non-recommendations (no MCQ, no second scheduler, no FSRS optimizer yet) — honored.

**rq03 AI tutor pedagogy** ([rq03](docs/research/2026-09-03/rq03-ai-tutor-pedagogy.md) lines 158–205): 1 frozen playbook **S**; 2 tutor-opens + section-first retrieval **S**; 3 application-owned phase + hint level **S** (`tutor_phase`, `hint_level` columns); 4 close → one FSRS card **S**; 5 pedagogy goldens — **unverified** (teach spec has golden transcript-shape ACs per rq03 §1 but I did not read the test files). Parked items (LearnLM/fine-tune, BKT, forbid answers) — honored.

**rq04 Active-recall quality** ([rq04](docs/research/2026-09-03/rq04-active-recall-quality.md) lines 158–230): 1 empty-deck honesty **S**; 2 formulation gates + prompt rewrite **S**; 3 undo + intervals + requeue **S**; 4 flag + edit **S**; 5 auto-deck as preview **N** (review spec line 42 "Preview … are later rows"); 6 highlight-first default **P** (highlight→card path exists since RFC-004 D; default ordering unverified); 7 per-user desired retention **N** (`desired_retention` only in config/FSRS adapter, not per user; review spec line 27 excludes "rq08 Cycle 4"); 8 concept-extract-then-generate **N**; 9 per-user FSRS optimizer **D** (ADR-0021 volume-gated); 10 LLM critique judge **D** (ADR-0021).

**rq08 Motivation & retention** ([rq08](docs/research/2026-09-03/rq08-motivation-retention.md) lines 155–190): Cycle 1 bounded daily review + Done-for-today **S** (PR #66, session page of 20; "new-card hold" **N**); Cycle 2 opt-in due digest **D** ("Deferred to Cycle F with EmailPort" AD-304 → "digest is a later small cycle" AD-328; the RFC-0007 thaw remains authorized but unimplemented); Cycle 3 routine prompt / implementation intention **N**; Cycle 4 workload-aware FSRS (DR setting) **N**. Explicit non-cycles (streaks, badges, leagues, shared decks) — honored.

**rq12 Growth & positioning** ([rq12](docs/research/2026-09-03/rq12-growth-positioning.md) lines 185–236): Move 1 positioning lock + landing v1 with hero demo/unlike table/dual CTA — **P** (dual CTA + one static quote; no demo, no comparison table); Move 2 try-without-signup — **D** (AD-320 "RFC sequences guest Ask after Cycle F"; never scheduled after F); Move 3 README as HN landing + demo media — **P** (README rewritten in PR #72; media "not recorded yet", operator-gated on a funded key); Move 4 staggered launch — **N** (operator action never taken); Move 5 pillar essay + long-tails — **N**; Move 6 export as marketing — **P** (README describes it; no landing mention); Move 7 private share links for notes — **N**; Move 8 hosted paid instance — **N** (no instance, no billing).

**rq13 AI integration patterns** ([rq13](docs/research/2026-09-03/rq13-ai-integration-patterns.md) lines 137–190): Cycle 1 claim-level citations **S**; Cycle 2 fast selection path (Haiku Explain + answer-prompt cache) **S** (PR #69 explain chain; Ask system-prompt cache unverified); Cycle 3 ingest briefs + library blurb **N** (grep `brief` → only an error handler); Cycle 4 review follow-up **N**; Cycle 5 typeahead retrieve **N**. Parked (Audio Overviews, vision, embedding batch) — untouched.

**Synthesis "do-not-build" list** (synthesis line 105) — all honored in code: no podcast/TTS, no YouTube/RSS, no MCQ, no second scheduler, no streaks/XP/badges, no marketplace, no vector DB/LangChain/LlamaIndex/LiteLLM, no CN first-party inference (GLM is via Fireworks-US), no per-user sample clones, no native apps, no multi-color highlights, no raw model picker (house profiles are curated), no pricing.

### Inferences
- Everything the synthesis put inside the seven bets shipped; everything it placed in "later" (digest, guest Ask, Turnstile, preview decks, per-user retention) is still open, and none of it has a roadmap row.
- The launch was built for but never performed: the sequence A → E → F → Show HN stops at F. The blockers are operational (funded key, host, demo media), not product.
- The largest untouched research clusters are rq02's deeper learning-science moves (pretest, JOLs, criterion session, learner-authored questions), rq13's "woven AI" surfaces (ingest briefs, typeahead, review follow-up), and all of rq12's growth motions.

### Gaps
- I did not audit `SUGGESTED_PROMPTS` copy (rq02 move 4) or the Home export affordances (rq01 move 7) in the frontend; status is unverified.
- Pedagogy golden tests (rq03 move 5) exist per spec references but were not read.

---

## KQ3 — Which recommendations were rejected or deferred, and why (quoted)?

### Takeaway
Deferrals are recorded verbatim in specs and ADRs: BYOK (security + pricing-gated), Turnstile (invite XOR captcha; subprocessor), due digest (needs a mail provider, then "a later small cycle"), guest Ask (after Cycle F caps), economy promotion (awaits a green candidate nightly that cannot run without credit), the G1/G2 split (owner chose one cycle), and Bet 4 preview decks (later row). Provider swaps, vector DBs, MCQ, gamification, and subscription-as-API were rejected outright.

### Cited Findings
- **BYOK**: "BYO API keys remain deferred, unchanged from point 11: a pricing-gated roadmap of their own (RQ10), with the research's abuse analysis (a user-supplied endpoint is never a configuration input) standing as written." — [docs/adr/0020-…](docs/adr/0020-use-anthropic-claude-for-generation.md) amendment point 7. Sizing: "Flavor B is a roadmap of its own: crypto + key management + lifecycle + abuse + billing-fairness + degradation UX is three-plus cycles and a security review, and its product value is gated on having a paying tier to sell it to" — [docs/research/2026-09-07/provider-adapter-architecture.md](docs/research/2026-09-07/provider-adapter-architecture.md) §3.3. Also declined earlier: RFC-003 scope choice "BYOK declined" (STATE.md, RFC-003 acceptance entry).
- **Turnstile**: "Deferred; no siteverify; invite code when the flag is on | rq09 XOR; RFC action item; Cloudflare is a US subprocessor | auto (AD-325)" — [.specs/features/safe-to-open-the-doors/spec.md](.specs/features/safe-to-open-the-doors/spec.md) line 39.
- **Opt-in due digest**: "Deferred to Cycle F with `EmailPort`. No preference schema and no sender this PR. | Escalation avoided: a mail provider is Cycle F's lock. The RFC-004 thaw remains authorized; it is not implemented here. | auto (AD-304)" — review spec line 43; then "Due digest | Out of this PR | EmailPort ships; digest is a later small cycle | auto (AD-328)" — doors spec line 42.
- **Guest / try-without-signup**: "Guest Ask / guest upload / try-without-signup | RFC conflict 2: invite-only until Cycle F; no uncapped public Ask" and "Guest path | Authenticated only … RFC sequences guest Ask after Cycle F. | auto (AD-320)" — first-session spec lines 23, 41. Nothing scheduled it after Cycle F.
- **Economy profile promotion**: "OpenAI-compatible prompt-cited adapter + Fireworks-US GLM-5.3-Flash economy profile shipped inert (ask/teach-disabled …). OPERATOR NEXT: trigger a candidate nightly for effort=`low` on Ask and for the economy profile; promotion = registry-reorder commit after a green nightly." — STATE.md PR #69 handoff. Blocked by the unfunded key (nightly red since 2026-07-27).
- **Cycle G split**: "Cycle G shipped as a single cycle (rails + router + first economy profile) rather than the G1/G2 split the 2026-09-07 research offered" — RFC-0007 line 268.
- **Bet 4 sizing**: "This RFC letter is one ship-cycle PR (honesty + gates + undo/session + flag/edit). Preview and the email digest are later rows, not a fourth split of this list." — review spec line 42. Per-user desired retention excluded as "rq08 Cycle 4" (line 27).
- **Subscription-as-API**: "No — the GLM Coding Plan's own terms name 'websites, SaaS products' invocation as prohibited … Anthropic bans OAuth bridges" — [docs/research/2026-09-07/README.md](docs/research/2026-09-07/README.md) table row 3; cheaper-intelligence spec line 33 lists it as out of scope "Prohibited by provider terms".
- **Gemini / DeepSeek / MiniMax profiles**: "The adapter kind + registry make them config-only later; one concrete economy profile this cycle" — cheaper-intelligence spec line 36.
- **Provider locks / rejected alternatives**: Voyage-4 embeddings rejected (dimension migration) — STATE.md AD-052; Opus as generation default rejected twice on evidence ("de-noised STAY on `claude-sonnet-5`") — ROADMAP line 104; Haiku judge → Opus judge flipped (line 103).
- **RFC-0007 binding exclusions** (line 214–223): no checkout/billing; no new provider SDK on the request path; no vector DB/LangChain/LlamaIndex; no gamification; no public book bytes; no per-user sample clones; no CN first-party inference; no sixth pillar.
- **Pricing**: "Pricing decision (Paddle as merchant of record; Polar cannot pay a Brazilian seller) is recorded and deferred — no checkout in this arc" — RFC-0007 finding 11.
- **Retrieval `top_k` raise / reranker**: "Raising `top_k` is a quality cycle owned by rq05 behind its own ruler, allowed only with the ledger showing the delta. Cutting `k` for cost is forbidden without a reranker." — RFC-0007 conflict resolution 7. Not scheduled.
- **RFC-004 dogfood retrospective**: never written — RFC-004 Outcome reads "_To be filled at acceptance and again at the gate retrospective._" ([docs/rfc/0004-student-experience-roadmap.md](docs/rfc/0004-student-experience-roadmap.md) line 107); only v2 and v3 retrospectives exist ([docs/retrospectives](docs/retrospectives)). RFC-005 was accepted retroactively "after the RFC-004 dogfood window it was written into had closed" (RFC-005 line 3).

### Inferences
- The deferred items form a coherent "hosted-launch tail": digest, Turnstile, guest Ask, demo media, promotion of the economy tier. All are small and all wait on operator resources (mail domain, funded key, host).
- The one deferral with real engineering weight is BYOK, and its blockers are unchanged (see KQ6).

### Gaps
- No document records *why* the launch motion was not performed after Cycle F beyond the operator items (key, host, demo); it may simply be unstarted.

---

## KQ4 — Explicit yes/no: Portuguese/i18n, PDF, mobile, offline/local model, notes, highlights, knowledge graph

### Takeaway
PDF yes; notes yes; highlights yes; mobile as responsive web only; Portuguese only at the content layer; UI i18n no; offline/local-model no (the "local" adapters are deterministic test stubs, not local LLMs); knowledge graph no.

### Cited Findings
- **Portuguese / i18n**: UI **NO** (`lang="en"`, no i18n library — [frontend/app/layout.tsx](frontend/app/layout.tsx) line 33, [frontend/package.json](frontend/package.json)). Content **YES** for PT books: language detection en/pt ([backend/app/application/language.py](backend/app/application/language.py)), FTS `portuguese` regconfig ([backend/app/application/text_search.py](backend/app/application/text_search.py) line 23), OCR `en,pt` ([backend/app/core/config.py](backend/app/core/config.py) line 140), PT stopwords in quiz QC ([backend/app/application/quiz_qc.py](backend/app/application/quiz_qc.py) line 81).
- **PDF**: **YES**, including scanned PDFs via selective OCR — ADR-0022, ADR-0025; README lines 70–80; `worker-pdf` compose service.
- **Mobile**: **YES as responsive web** (bottom-sheet dock, touch capture, 44px targets) — reader spec line 11; **NO native app, NO PWA** (no manifest/service worker; RFC-0007 Cycle B "Out: native apps").
- **Offline / local model**: **NO**. `local` provider = "deterministic, network-free adapter" that returns extractive snippets for tests ([backend/app/infrastructure/answering/local.py](backend/app/infrastructure/answering/local.py) line 76; [docs/media/README.md](docs/media/README.md) "The deterministic adapters that CI runs on return extractive snippets, not the product's answers"). No Ollama/llama.cpp/vLLM references anywhere (grep → 0). The `openai-compatible` adapter kind accepts a `base_url`, so an operator *could* point a profile at a self-hosted OpenAI-compatible server, but nothing documents or tests that — unverified as a supported path.
- **Note-taking**: **YES** — Markdown notes with tags, links, backlinks, notes-in-retrieval, note → cards, Obsidian export (ADR-0026; README lines 100–109).
- **Highlights**: **YES** — reader selection → highlight anchored to corpus anchor with snapshot; `POST/GET /api/sources/{id}/highlights`; margin rail — README lines 104, 205; [frontend/app/components/margin-rail.tsx](frontend/app/components/margin-rail.tsx). Single color only (multi-color explicitly out).
- **Knowledge graph / concept map**: **NO** — grep `knowledge graph|graphrag|concept map|mind map` in backend/app and frontend/app → 0; rq01 do-not-build list line 276 includes "auto knowledge graph"; note↔note links + backlinks exist but there is no graph view.

### Inferences
- A Portuguese-speaking learner can already ingest and search PT books correctly; what they cannot do is use a PT interface.

### Gaps
- None.

---

## KQ5 — Deployment/hosting reality: is there a public instance, and what would a stranger need to do?

### Takeaway
There is no public instance. The full production path (CI → GHCR → VPS behind Caddy with backups, PITR, monitoring) is built and exercised in CI, but a stranger today must self-host with Docker Compose and supply their own OpenAI and Anthropic keys to get real answers.

### Cited Findings
- "no public instance is hosted yet" — [README.md](README.md) line 5; "no public instance is hosted" — [.specs/project/ROADMAP.md](.specs/project/ROADMAP.md) line 157; STATE.md handoff operator item (1).
- Self-host path: `git clone … && docker compose up --build`; app at :3000; "No API keys required — the MVP's AI adapters are deterministic and network-free" — README lines 150–161. Real answers require `LEARNY_GENERATION_PROVIDER=anthropic`, `LEARNY_ANTHROPIC_API_KEY`, `LEARNY_EMBEDDING_PROVIDER=openai` in `secrets/local-ai.env` — [docs/media/README.md](docs/media/README.md) prerequisites.
- Production: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d` with `secrets/*.env`; runbook [docs/ops/deploy.md](docs/ops/deploy.md) (DNS A record, SSH key, one-time GHCR package flip to public, six images) — lines 32, 217–258.
- Open operator items: flip `learny-minio` GHCR package public; fund the Anthropic account (nightly red since 2026-07-27); record demo media; rewrite 21 commits authored with a corporate email (declined as destructive) — STATE.md handoff.
- Nothing in the repo is a hosted-service dependency: no ESP SDK, no Turnstile, no analytics SDK, no billing (doors spec line 26; RFC-0007 exclusions).

### Inferences
- The gap between "portfolio showcase" and "someone else can use it" is one afternoon of ops plus money for a key, not code.
- Without a hosted instance, none of the activation events (`first_cited_answer`, D7) that RFC-0007 built its funnel on have ever been observed on a stranger.

### Gaps
- Whether the author's own VPS is currently running (private) is unverified; docs only assert no *public* instance.

---

## KQ6 — Constraints, BYOK blockers, and recorded next-cycle candidates with sizing

### Takeaway
No roadmap row is open. Recorded candidates are: MinIO unprivileged-user follow-up (small), economy-profile promotion (needs a funded key), BYOK (3+ cycles, all three named blockers still present), plus README-level candidates (paragraph-level note chunking; vector DB/reranker only if pgvector stops scaling). ADR-0019/0020 lock OpenAI embeddings and Anthropic-first generation with routing to declared profiles; new provider SDKs need an accepted cycle.

### Cited Findings — recorded candidates
- "NEXT: no Not-started roadmap row remains; the next cycle needs a row authored first. Candidates, in recommended order: (a) **MinIO unprivileged user + volume migration** (ADR-0031 follow-up; small); (b) economy-profile promotion after a green candidate nightly (needs credit); (c) BYO keys (3+ cycles); (d) demo capture is an operator task, not a cycle." — [.specs/project/STATE.md](.specs/project/STATE.md) Handoff, PR #72 entry.
- README "Recorded candidates, not scheduled": economy promotion; BYOK ("three or more cycles … encryption-at-rest and open-relay problems it must solve first"); "Paragraph-level note chunking for retrieval; a dedicated vector database or reranker if PostgreSQL hybrid search stops scaling." — [README.md](README.md) lines 226–230.
- CLAUDE.md: "Current state: no roadmap row is open. The next cycle needs a row authored in `.specs/project/ROADMAP.md` first." — [CLAUDE.md](CLAUDE.md) Current Status.
- Older recorded-but-unscheduled items still on file: retrieval `top_k`/structural-headers quality cycle behind a "retrieval ruler" (RFC-0007 conflict 7; rq05); Gemini/DeepSeek/MiniMax profiles "config-only later" (cheaper-intelligence spec line 36); due digest "a later small cycle" (AD-328); guest Ask after Cycle F (AD-320); auto-deck preview (review spec line 42); ADR-0021 deferrals (FSRS optimizer, LLM card critique); ADR-0026 (no vault sync).

### Cited Findings — provider locks
- ADR-0019: OpenAI `text-embedding-3-large` at 1536 dims, per-chunk `embedding_model` versioning; Voyage rejected; "re-embed rejected as a cost move" (synthesis lock table). Status Accepted, no amendment.
- ADR-0020: Anthropic Claude for cited answers/teaching; amended 2026-09-07 to a settings-declared profile registry with `local | anthropic | openai-compatible` kinds and Learny-owned routing (fallback only on transport errors, never on grounded not-found; Ask never routes to a citation-less profile); amended 2026-09 for learner choice among house profiles; BYOK deferred (point 7); "The port stays frozen" (point 9). — [docs/adr/0020-…](docs/adr/0020-use-anthropic-claude-for-generation.md) lines 166–290.
- CLAUDE.md: "Do not introduce new provider SDKs outside an accepted cycle." RFC-0007 exclusions: "No new provider SDK on the request path (ADR-0007/0009); LiteLLM and OpenRouter stay off it."
- Eval promotion rule: any downgrade must pass the nightly judged eval (faithfulness ≥ 0.90, relevancy ≥ 3.1, `citation_valid` = 100%) before promotion — [docs/research/2026-09-07/README.md](docs/research/2026-09-07/README.md) synthesis point 1; RFC-0007 Cycle G must-be-true.

### Cited Findings — BYOK blockers named 2026-09-07 and their status today
1. **No encryption at rest**: still true. grep `encrypt|fernet|kms|cryptography` in `backend/app` and `backend/pyproject.toml` → only docstrings about encrypted PDFs ([backend/app/application/errors.py](backend/app/application/errors.py) line 104, [backend/app/infrastructure/ingestion/docling_pdf.py](backend/app/infrastructure/ingestion/docling_pdf.py) lines 20, 95); no `cryptography` dependency in [backend/pyproject.toml](backend/pyproject.toml). Profiles carry `api_key_env` (the *name* of an env var, "the value itself is never a setting (NFR-SEC-003)") — [profiles.py](backend/app/infrastructure/providers/profiles.py) line 68–70. **Unaddressed.**
2. **`lru_cache` adapters built once per process**: still true for the operator chains — `@lru_cache def get_generation()`, `get_explain_generation()`, `_declared_profile_ids()` at [backend/app/infrastructure/web/dependencies.py](backend/app/infrastructure/web/dependencies.py) lines 690–711; PR #71 added a per-user *chain reorder* via `get_generation_for_user` reading the preference row per request and a per-user dict cache (`_user_generation_chains`, cleared by `clear_generation_chain_caches`, line 777–790). This resolves the "two-tier lookup" item of Flavor A but **not** per-user SDK clients keyed by user secrets (Flavor B item 3). **Partially addressed (Flavor A only).**
3. **Open-relay risk from a user-supplied `base_url`**: `base_url` exists only on operator-declared profiles ([profiles.py](backend/app/infrastructure/providers/profiles.py) line 79; [openai_compat.py](backend/app/infrastructure/answering/openai_compat.py) lines 310–336); the user-facing endpoint accepts only a `profile_id` bounded to the declared registry ("bound profile ids and share the 422 constant", commit `3227b29`). No user URL input exists, so the risk is **avoided by design, not mitigated by SSRF controls** — exactly what the research recommended ("recommend: never allow one"). **Unchanged posture.**
4. Also still true from §3.1: secrets are env-only by policy; the account page and `MeResponse` seams exist (now used for the profile selector).

### Cited Findings — other hard constraints
- Hexagonal rule enforced by review and an architecture-boundary lint: no SQLAlchemy/Celery/boto3/ebooklib/Docling/OpenAI/Anthropic/FSRS in `domain/` or `application/` — README line 68; `make lint` "architecture boundaries" (CLAUDE.md).
- Retrieval stays one SQL hybrid RRF statement in PostgreSQL; reranker/vector DB are ADR-0006 escape hatches only.
- Notes never enter `corpus_chunks`; export is one-way (ADR-0026).
- FSRS state is never rewritten by content changes (v3 invariant, review spec line 11).
- Repo-wide `ruff format` drift (116/233 backend files) deliberately unfixed; CI lint gate is `ruff check` only — STATE.md Known Issues.
- The nightly eval, the only promotion gate, cannot run until the Anthropic account is funded — eval.yml lines 113–117.

### Inferences
- Any next cycle that touches AI serving must first restore the nightly (fund the key), because both the economy promotion and any `effort=low` flip are gated on it.
- BYOK remains the only recorded candidate with multi-cycle engineering; its three blockers are in the same state the 09-07 research found them, except that the per-user resolution seam now exists.
- The cheapest high-visibility next steps recorded on file are all sub-cycle: MinIO hardening, demo media, digest, Turnstile, economy promotion.

### Gaps
- Sizing for the README's "paragraph-level note chunking" and "vector DB/reranker" candidates is not recorded anywhere I read.
- Whether the owner intends to host publicly at all (vs. keep Learny as a self-host portfolio piece) is not stated in any document; ROADMAP line 157 frames PR #72 around "project purpose: interview-grade showcase".
