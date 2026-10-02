# Learny wins by remembering, not answering

*Research delta as of 2026-09-30, on top of main @ `9b485f2` (v0.7.0 + house profiles + PR #72). It does not restate RFC-0007; everything RFC-0007 shipped is treated as the baseline. Repo paths are relative to `/home/augusto/projects/learny`.*

## Executive summary (two-minute read)

**Grounded chat over your own books is no longer a moat.** Google's Gemini Notebook (NotebookLM until 2026-07-16) has accepted EPUB since March 2026, makes 100,000+ licensed Play Books titles citable since 2026-08-27, ships pt-BR audio and a voice tutor, and is giving students in 140+ markets, Brazil included, a free year of AI Plus if they redeem by 2026-12-31 ([Workspace Updates](https://workspaceupdates.googleblog.com/2026/03/new-ways-to-customize-and-interact-with-your-content-in-NotebookLM.html); [9to5Google](https://9to5google.com/2026/08/27/gemini-notebook-play-books/); [blog.google](https://blog.google/innovation-and-ai/products/gemini-notebook/new-study-tools-september-2026/)). Price and "chat with a PDF" will not win Brazil or anywhere else. **What nobody ships is the loop Learny already has.** That loop runs from a structure-preserving reader to claim-level citations, a hint-first tutor, FSRS review, notes as evidence, and portable export (`README.md`; `docs/adr/0029-unified-grounded-conversations.md`). Gemini Notebook has no reader, no spaced-repetition scheduler, and no learner model that persists across notebooks ([XDA](https://www.xda-developers.com/notebooklm-limitations/); [Medium semester review](https://harsh-gautam.medium.com/i-let-googles-notebooklm-manage-my-studies-for-a-semester-here-are-the-results-ef4e70fa3fc5)). The chat study modes keep no state between sessions. Readwise Reader, the closest shape, has library-wide cited chat and MCP but no tutor ([Readwise](https://readwise.io/reader/update-aug2026)).

**The defensible white space is a study home that remembers the learner for months and measures learning honestly.** Concretely, that means four things, each anchored to passages of the learner's own books:

- **Unassisted checkpoints** that alone grant "mastery".
- **Confidence ratings** with calibration feedback.
- **A plan prompt** at the start of each book.
- **Explain-back** graded against the cited passage.

The 2024–2026 AI-tutor trials say this is where the value is. Answer-giving AI raises scores while it is available and leaves learners flat or worse without it (Bastani et al.: **−17%** on the unassisted exam). Guardrailed tutors remove the harm or beat active-learning classes, at **d = 0.73–1.3** in Kestin et al. ([Stanford SCALE 2026 review](https://scale.stanford.edu/sites/default/files/The%20Evidence%20Base%20on%20AI%20in%20K-12%20Report.pdf); [Kestin et al.](https://www.nature.com/articles/s41598-025-97652-6)). Learny's hint ladder is on the right side of that line. Its progress model, a heatmap plus FSRS state, does not yet distinguish assisted from unassisted success.

**Brazil is a real but specific opportunity.** The adult segments that study from their own PDFs are the targets, and Learny should launch for adults only (18+) to defer the minors regime that the ENEM cohort triggers:

| Segment | Size | Source |
|---|---|---|
| Concurso registrations | ~9M per year | [BNews](https://www.bnews.com.br/noticias/economia-e-mercado/mercado-de-concursos-em-2025-pode-movimentar-mais-de-r-5-bilhoes-entenda.html) |
| Undergraduates in distance learning (EAD) | 5.1M | [INEP](https://www.gov.br/inep/pt-br/centrais-de-conteudo/noticias/censo-da-educacao-superior/inep-divulga-resultado-do-censo-superior-2024) |
| OAB bar-exam candidates | ~150k per sitting | [Damásio](https://blog.damasio.com.br/43-exame-oab-2025) |
| Developers | 6.9M | [Canaltech](https://canaltech.com.br/mercado/brasil-vira-potencia-no-github-com-crescimento-recorde-de-desenvolvedores/) |

The market requires the following, none of which Learny has today:

- **A Portuguese interface.** Learny's UI is English-only, though it already handles Portuguese as content.
- **An installable mobile experience.** 60% of Brazilian internet users are phone-only ([Cetic.br via Abranet](https://abranet.org.br/noticias/tic-domicilios-2024-60-usam-internet-exclusivamente-pelo-smartphone/)).
- **Pix and honest cancellation**, whenever money is involved.

**BYOK-first is compliant and strategically sound.** Anthropic's written policy allows customer-provisioned API keys billed to the key owner and bans subscription or OAuth bridging ([Claude Code legal](https://code.claude.com/docs/en/legal-and-compliance)). The shipped house-profile seam is the natural place for user keys. The rule should be "your key, our curated and eval-gated profiles", with server-side envelope encryption, a fixed provider allow-list, and no user-supplied `base_url` on a hosted instance.

**Recommended next cycles, in order.** Six rows are launch-critical, about 8–10 cycles in total:

1. `pt-br-interface`
2. `byok-secrets-and-chains`
3. `byok-hosted-policy`
4. `local-models-self-host`
5. `installable-and-adult-launch`
6. `section-checkpoint-and-calibration`

These are followed by `honest-mastery-map`, `book-plan-and-digest`, `biblioteca-aberta`, `shelf-ask`, `library-mcp`, and only then `paid-hosted-tier`.

**Two operator actions gate everything and are not cycles.**

- **Fund the CI Anthropic key.** The nightly eval gate has been red since **2026-07-27** because the CI account has no credit (`.github/workflows/eval.yml`).
- **Decide whether and where a public instance will run.** None exists today (`README.md` line 5).

**Do not build:** podcast or video overviews, a licensed-book store, sharing of book files or decks, a raw model picker, user-set `base_url` on a hosted instance, per-user embedding keys, a streak-driven progress model, or essay and exam "grading".

## Gemini Notebook closed the upload gap but left the memory gap open

The 2026-09-03 fleet framed Gemini Notebook as the competitor and the book loop as the wedge (`docs/research/2026-09-03/synthesis.md`). Four weeks later the frame holds, but the ground under it moved. **Gemini Notebook added EPUB for all users in March 2026**, so "you can't upload a book" is no longer an argument ([gHacks](https://www.ghacks.net/2026/03/10/google-adds-epub-support-to-notebooklm-making-it-more-useful-for-students/)). It also turned **Play Books purchases into citable sources** from Bloomsbury, PRH, O'Reilly and others on 2026-08-27, a licensed supply channel no indie app can copy ([Library Journal infoDOCKET](https://www.infodocket.com/2026/08/27/google-announces-launch-of-expert-intelligence-feature-for-gemini-notebook/)). The September release added several student features: real-time voice tutoring in about 100 languages, a lecture recorder, Interactive Learning Overviews with a table of contents and per-section study tools, and short-answer and fill-in-the-blank quizzes ([blog.google](https://blog.google/innovation-and-ai/products/gemini-notebook/new-study-tools-september-2026/)). Google also replaced fixed daily caps with **opaque compute budgets** on 2026-09-02, which Android Police called "more complicated" ([9to5Google](https://9to5google.com/2026/08/28/gemini-notebook-usage-limits/); [Android Police](https://www.androidpolice.com/gemini-notebook-ditching-daily-limits-more-complicated/)).

The gaps are structural, not cosmetic. Citations click through to a highlighted passage in a source pane. That is at parity with Learny on raw verifiability. But they "lack page numbers or paragraph references", and copying or exporting loses them ([XDA](https://www.xda-developers.com/notebooklm-limitations/)). Flashcards save "Got it / Missed it" state per deck but have **no adaptive scheduler**. A student who ran a whole semester on it fell back to manual Day 1/3/7/21 reviews ([Medium](https://harsh-gautam.medium.com/i-let-googles-notebooklm-manage-my-studies-for-a-semester-here-are-the-results-ef4e70fa3fc5)). Notebooks are silos with no cross-notebook search. Google's own answer to "progress" lives in a different product: Gemini-app study notebooks (2026-06-25) offer a diagnostic quiz, 100+ objectives and a Strengths/Focus dashboard, but no spaced review or reminders, and run under a different privacy model ([blog.google](https://blog.google/innovation-and-ai/products/gemini-app/gemini-study-notebooks/); [Smith Stephen, opinion](https://www.smithstephen.com/p/googles-new-notebooks-feature-connects)). Audio and video overviews carry no citations at all and "sound so human, you'll believe the misinformation" ([XDA](https://www.xda-developers.com/notebooklm-audio-overviews-sound-human-believe-misinformation/)). **Google's only learning RCT** is a Guided Learning trial in Sierra Leone classrooms: +0.258 SD in math over 8 weeks, N = 1,763 ([DeepMind](https://deepmind.google/blog/measuring-the-impact-of-learning-with-ai-in-sierra-leone-and-beyond/)). Nothing published tests Notebook's flashcards or study notebooks for retention.

The rest of the field splits along the same seam. **The chat study modes are table stakes:**

- ChatGPT Study Mode, from 2025-07-29.
- Claude Learning mode, for all users from 2025-08-14.
- Perplexity Study Mode, from September 2025.
- Microsoft Copilot "Study and Learn", from 2026-05-13.

They are Socratic per chat, with no book structure, no scheduler, and no published outcome data ([OpenAI](https://openai.com/index/chatgpt-study-mode/); [Engadget](https://www.engadget.com/ai/anthropic-brings-claudes-learning-mode-to-regular-users-and-devs-170018471.html); [Microsoft](https://www.microsoft.com/en-us/education/blog/2026/05/study-and-learn-ai-built-for-your-student/)). The study apps (Turbo AI, Knowt, StudyFetch, Quizlet) compete on the **volume of generated artifacts** from lectures and PDFs. The most visible complaints about them are hallucinated transcripts, ads and auto-renewal ([tl;dv](https://tldv.io/blog/turbo-ai/); [Trustpilot](https://se.trustpilot.com/review/knowt.io); [Dupple](https://dupple.com/reviews/study-fetch)). **Readwise Reader is the nearest single-app rival.** Its 2026-08-06 update shipped "Global Ghostreader" with cited answers across the whole library, an MCP server, EPUB fixes and a bring-your-own OpenAI key for custom prompts. Its learning loop is highlight review, not a tutor ([Readwise](https://readwise.io/reader/update-aug2026)). Kindle's "Ask this Book" proves mainstream demand for in-book, spoiler-aware answers. It is limited to Amazon-sold English titles and drew an Authors Guild protest over the lack of any opt-out ([Kindlepreneur](https://kindlepreneur.com/amazon-ask-this-book/); [Authors Guild](https://authorsguild.org/news/statement-on-amazon-kindle-ask-this-book-ai-feature/)). **Brazilian incumbents** bolt AI onto their own catalogues. Gran's MAIA has produced over 1.2M question explanations. Descomplica has a lesson assistant and an essay corrector. Árvore.ai answers questions over its licensed 30k-book library. None of them lets a learner bring their own book ([Gran](https://grancursosonline.zendesk.com/hc/pt-br/articles/21798168734235-MAIA-a-Intelig%C3%AAncia-Artificial-do-Gran); [Descomplica](https://descomplica.com.br/vestibulares/enem/); [PublishNews](https://www.publishnews.com.br/materias/2023/03/10/arvore-lanca-plataforma-de-ia-para-expandir-experiencia-de-leitura-dos-usuarios)).

### Competitor coverage matrix

Key: ✔ ships · partial · ✘ absent · **?** unverified in this research. "Brazilian incumbents" means Gran, Descomplica, Qconcursos, Estratégia and Árvore taken together.

| Capability | Learny today | Gemini Notebook | ChatGPT / Claude study modes | Readwise Reader | Anki / RemNote / Knowt | Brazilian incumbents |
|---|---|---|---|---|---|---|
| Ingest your own EPUB | ✔ (ebooklib) | ✔ (since Mar 2026) | partial (per-chat uploads; EPUB **?**) | ✔ | ✘ (RemNote: PDF only) | ✘ (catalogue-bound) |
| PDF, including scanned (OCR) | ✔ (Docling + EasyOCR en/pt) | ✔ PDF; OCR **?** | ✔ PDF; OCR **?** | **?** | partial (RemNote PDF) | ✘ |
| Book structure preserved as stable anchors | ✔ | partial (source pane; no page or paragraph refs) | ✘ | ✔ (chapters, print pages, Aug 2026) | ✘ | ✘ |
| Whole-book reading surface | ✔ (paper reader, progress, resume) | ✘ | ✘ | ✔ | ✘ | partial (Árvore reader, own library) |
| Passage-level verifiable citations | ✔ (claim-level spans) | ✔ | ✘ / **?** | ✔ (Global Ghostreader) | ✘ | ✘ / **?** |
| Citations carried into cards and tutoring | ✔ (card citation snapshots; tutor cites) | partial (flashcard "Explain" cites; audio and video do not) | ✘ | partial | ✘ | ✘ |
| Spoiler-safe, position-bound answers | ✔ (PR #70) | ✘ | ✘ | **?** | ✘ | ✘ |
| Cited Ask across the whole library | ✘ (one book per conversation; README conflict, **?**) | partial (within one notebook; no cross-notebook) | partial (projects; no passage citations) | ✔ | ✘ | ✘ |
| Hint-first tutor with app-owned state | ✔ (pump→hint→prompt→assert) | partial (Learning Guide style, voice; no persistent state) | partial (prompted mode; memory only) | ✘ | partial (Knowt AI voice tutor, paid) | partial (Gran MAIA tutor, own catalogue) |
| Scheduled spaced repetition | ✔ (FSRS-6, undo, flag/edit) | ✘ (per-deck state only) | ✘ (session-bound quizzes) | partial (Daily Review, Mastery Cards; algorithm **?**) | ✔ | **?** |
| Grounded card generation with QC gates | ✔ | partial | partial | partial | partial (AI add-ons; RemNote AI cards) | partial (AI question explanations) |
| Persistent learner model or mastery view | partial (FSRS state + heatmap; no per-section mastery) | partial (Gemini-app study notebooks, per goal) | ✘ | ✘ | partial (card stats) | **?** |
| Confidence ratings, calibration, planning prompts | ✘ | partial (diagnostic quiz) | ✘ | ✘ | ✘ | **?** |
| Notes and highlights joined to retrieval | ✔ | partial | ✘ | ✔ | partial (RemNote notes) | ✘ |
| Portable export | ✔ (Anki .apkg, Obsidian vault) | ✘ (no export keeps citations) | partial | ✔ (MCP) | ✔ | ✘ |
| Public API or MCP | ✘ | partial (Enterprise API, preview) | n/a | ✔ (MCP) | partial (Recall MCP; Anki add-ons) | ✘ |
| Portuguese UI | ✘ (`lang="en"`; pt is content-only) | ✔ (pt-BR audio and video) | ✔ **?** | **?** | **?** | ✔ |
| Native app or installable offline | partial (responsive web; no PWA) | ✔ (iOS, Android) | ✔ | ✔ (Readwise 2.0 mobile) | ✔ (AnkiDroid) | **?** |
| Per-user BYOK | ✘ (operator keys only) | ✘ | ✘ | partial (BYO OpenAI key for custom prompts) | partial (Obsidian and Anki add-ons) | ✘ |
| Self-host or local models | partial (self-host ✔; local LLM path undocumented) | ✘ | ✘ | ✘ | partial (Anki open source) | ✘ |
| Typical price in Brazil | free (self-host; no hosted instance) | free; Plus R$24,99; Pro R$96,99; free student year | ChatGPT Go R$39,99, Plus R$99,99; Claude ≈R$129,9 (USD + IOF) | US$9.99/mo annual (BRL **?**) | Anki free; Knowt Ultra US$149.99/yr | R$30–60/mo; premium R$99–229 |

Matrix sources: Learny from the ledger and `README.md`; Gemini from [Google Help](https://support.google.com/notebooklm/answer/16215270?hl=en), [XDA](https://www.xda-developers.com/notebooklm-limitations/) and [gemini.google/br](https://gemini.google/br/subscriptions/?hl=pt-BR); assistants from [Appscribed](https://appscribed.com/chatgpt-study-mode/), [Canaltech](https://canaltech.com.br/apps/chatgpt-plus-fica-mais-barato-no-brasil-com-nova-cobranca-em-real/) and [SSD Nodes](https://www.ssdnodes.com/learn/claude-pro-in-brazil-what-you-pay); Readwise from [readwise.io](https://readwise.io/reader/update-aug2026) and [pricing](https://readwise.io/pricing); Anki-class tools from [Wikipedia](https://en.wikipedia.org/wiki/Anki_(software)), [RemNote](https://www.remnote.com/pricing) and [Knowt](https://knowt.com/plans); Brazilian prices from [Qconcursos](https://www.qconcursos.com/planos-de-assinatura) and [Estratégia](https://www.estrategiaconcursos.com.br/assinaturas/).

**The white space is the intersection, not any single column.** No product combines all five of the following, and no product found does any of them in Portuguese:

1. The learner's **own** books.
2. Structure-preserving reading.
3. Citations that survive into teaching and review.
4. A scheduler.
5. A learner model.

Two risks bound the claim. Readwise could cheaply add a tutor on top of Global Ghostreader. Google could add a scheduler to Notebook flashcards, which was already the 09-03 watch-item. Both would narrow the read-and-ask gap. Neither would touch honest mastery measurement, BYOK and self-host ownership, or Portuguese-first support for owned materials. **Defensibility therefore rests on three things:** pedagogy that measures unassisted learning, fidelity of anchors end-to-end, and ownership. Model quality is not one of them; Google will always out-spend on that.

## Learny already owns five pillars; the gaps are language, access and honest progress

The ledger (`learny_current_state_and_ledger.md`, reconciled against code at `9b485f2`) gives a precise baseline. **Already covered:**

- EPUB and PDF ingestion, with selective OCR in `en,pt`.
- Hybrid pgvector and full-text retrieval bound to reading position.
- Streaming cited Ask with claim-level `CitedSpan` and abstention.
- A frozen hint-ladder tutor that opens sessions and closes with one opt-in FSRS card.
- Grounded cards with formulation gates, FSRS-6, undo, flag/edit, and a bounded 20-card session.
- Notes, tags, backlinks, and notes as retrieval arms.
- Anki and Obsidian export.
- A shared pre-ingested sample book.
- Open-registration rails: limiter, a $0.50 per day spend cap, quotas, invites, deletion, and email verify/reset.
- Learner-chosen house AI profiles.

Sources: `README.md`; `.specs/project/ROADMAP.md`; `docs/adr/0020-use-anthropic-claude-for-generation.md`; `backend/app/core/config.py`.

**Not covered**, each confirmed by the ledger against code:

| Gap | Evidence | Status |
|---|---|---|
| UI i18n | `frontend/app/layout.tsx` line 33 hard-codes `lang="en"`; no i18n dependency | Missing |
| Hosted public instance | `README.md` line 5 | None exists |
| PWA or offline | No manifest or service worker | Missing |
| Per-user BYOK | No encryption anywhere in `backend/app` | Missing |
| Local LLM path | The `local` adapter is a deterministic test stub. The `openai-compatible` kind accepts an operator `base_url`, but that path is untested and undocumented. | Missing |
| Library-wide Ask | ADR-0029 scopes to one book; README wording conflicts | **?** |
| Pretest, judgments of learning, criterion sessions, contrast items, explain-back | rq02 moves 1, 3, 5, 6 and 8 have no code | Missing |
| Per-user desired retention | rq08 Cycle 4 | Missing |
| Opt-in due digest | AD-304 deferred it, then AD-328 deferred it again | Missing |
| Guest Ask | AD-320 | Missing |
| Turnstile | AD-325 | Missing |
| MCP or public API | — | Missing |

The launch motion itself was never performed. The blockers are operational: a funded key, a host and demo media (STATE.md handoff, via the ledger).

**Some gaps are smaller than they look.** Portuguese already works at the content layer:

- Language detection, in `backend/app/application/language.py`.
- The `portuguese` full-text configuration, in `backend/app/application/text_search.py`.
- Portuguese OCR.
- Portuguese stopwords in quiz QC, in `backend/app/application/quiz_qc.py`.

So a pt-BR learner can already ingest and search a Portuguese book correctly. What is missing is the interface, pt-BR tutoring copy, and a Portuguese golden set to prove faithfulness. Likewise, the `openai-compatible` adapter, the profile registry and the per-user chain from PR #71 mean that BYOK and local models plug into seams that already exist. The work is in secrets, policy and evaluation, not in the request path (`backend/app/infrastructure/providers/profiles.py`; `backend/app/infrastructure/web/dependencies.py`).

**Some gaps are larger than they look.** Every BYOK blocker named on 2026-09-07 is in the same state today except one:

- **No encryption at rest:** still true.
- **Process-wide `lru_cache` adapters:** fixed for house-profile reordering, but there are still no per-user clients keyed by user secrets.
- **User-supplied `base_url`:** avoided by design rather than mitigated.

Sources: `docs/research/2026-09-07/README.md`; ledger KQ6. The nightly judge gate, the only promotion mechanism for any new profile, **cannot run until the CI key is funded** (`.github/workflows/eval.yml` lines 113–117). Any cycle that adds model paths, whether BYOK, local or economy, is quality-ungated until that is fixed.

## Learning science says a study home must withhold answers, space retrieval, and count only unassisted wins

The technique evidence is old and stable. **Practice testing and distributed practice** are the only two techniques rated high-utility by Dunlosky et al. (2013). Later meta-analyses put the testing effect at **g = 0.61** overall and g = 0.51 against restudy ([Dunlosky et al.](https://pubmed.ncbi.nlm.nih.gov/26173288/); [Adesope et al. 2017](https://www.researchgate.net/publication/315706448_Rethinking_the_Use_of_Tests_A_Meta-Analysis_of_Practice_Testing)). Several other techniques are well replicated at medium-to-large effects:

| Technique | Effect | Source |
|---|---|---|
| Successive relearning (retrieval to criterion across spaced days) | ≥10% exam gain; >75% recall after one year at 56-day spacing | [Janes et al. 2020](https://onlinelibrary.wiley.com/doi/abs/10.1002/acp.3699) |
| Interleaving | **d = 0.83** at one month, in a 787-student RCT | [Rohrer et al. 2020](https://gwern.net/doc/psychology/spaced-repetition/2019-rohrer.pdf) |
| Prompted self-explanation | g = 0.55 | [Bisra et al. 2018](https://eric.ed.gov/?id=EJ1186664) |
| Teaching, when the learner expects to teach and then does | g = 0.56 | [Kobayashi 2019](https://onlinelibrary.wiley.com/doi/10.1111/jpr.12221) |
| Problem-solving before instruction | g = 0.36–0.58 | [Sinha & Kapur 2021](https://janfasen.nl/wp-content/uploads/2023/05/Sinha-and-Kapur-PS-I.pdf) |

**Highlighting and rereading are low-utility.** They can stay as reader affordances but should never count as study.

**The 2024–2026 AI-tutor trials converge on one rule: the guardrail is the product.**

- **Unrestricted answer-giving AI looks like help and isn't.** In Bastani et al. it produced a **17% drop** on the unassisted exam, while the hint-only GPT Tutor arm eliminated the harm. Chen et al. found homework improved but the exam did not move. Lehmann et al. found unrestricted ChatGPT "harmed student understanding" and widened gaps for students with low prior knowledge. All three are tabulated in the [Stanford SCALE 2026 review](https://scale.stanford.edu/sites/default/files/The%20Evidence%20Base%20on%20AI%20in%20K-12%20Report.pdf).
- **Principled tutor design works.** Kestin et al. reported learning gains more than double those of a best-practice active-learning class ([Scientific Reports](https://www.nature.com/articles/s41598-025-97652-6)).
- **Structured usage protocols matter.** Hou et al. 2026 found **+0.86 SD** for structured AI use versus +0.09 SD unguided, as cited by Contractor & Reyes ([arXiv 2607.08849](https://arxiv.org/abs/2607.08849)). Hou is a secondary citation, not verified against the primary.
- **Writing with an LLM drives "metacognitive laziness".** Fan et al. found that pattern alongside better essays but no knowledge gain ([BJET](https://bera-journals.onlinelibrary.wiley.com/doi/10.1111/bjet.13544)).
- **Engagement, not access, is the binding constraint.** In the two-year Khanmigo RCT, 96% of students tried the tutor. The median student used it on a third of practice days, and it was used in only 17% of error sessions, for **~0.06–0.08 SD per year** ([NBER w35620](https://www.nber.org/papers/w35620)).
- **Learners click through hints.** In older tutor logs, students saw 68% of hint levels for under one second ([Aleven et al.](https://link.springer.com/article/10.1007/s40593-015-0089-1)).

**One caveat matters for Learny specifically.** No RCT tests LLM tutoring for adult independent readers of books outside a course. Every durable-outcome trial is in a school or course setting. The composite loop below is inferred from component effects, which may not add up linearly.

**Honest progress means opportunities and calibration, not streaks.**

- **Practice opportunities.** Across 27 datasets and 1.3M observations, learners needed about **7 quality practice opportunities per knowledge component** to reach 80% accuracy. They varied in prior knowledge but little in learning rate ([Koedinger et al. 2023](https://www.researchgate.net/publication/369381755_An_astonishing_regularity_in_student_learning_rate)). Some critics argue the regularity is partly a modeling artifact.
- **Simple learner models suffice.** Logistic knowledge-tracing models match or beat Bayesian knowledge tracing at moderate data scale ([Gervet et al. 2020](https://files.eric.ed.gov/fulltext/EJ1273917.pdf)).
- **Calibration is trainable.** A meta-analysis of 56 studies found a moderate effect ([Calibrating Calibration](https://www.researchgate.net/publication/349179781_Calibrating_Calibration_A_Meta-Analysis_of_Learning_Strategy_Instruction_Interventions_to_Improve_Metacognitive_Monitoring_Accuracy)). Judgments of learning made after retrieval modestly improve learning ([PMC10607076](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10607076/)).
- **Gamification effects are small.** Reward and status mechanics are the weakest form ([Sailer & Homner 2020](https://link.springer.com/content/pdf/10.1007/s10648-019-09498-w.pdf)).

**Autonomy has a brutal base rate, and cheap scaffolds move it.**

- MOOC completion sits at **3–15%**, and 52% of registrants never start ([Reich & Ruipérez-Valiente 2019](https://www.semanticscholar.org/paper/The-MOOC-pivot-Reich-Ruip%C3%A9rez-Valiente/fdd37727342a0da25294ba57953ea918665a5a2d)).
- Open-ended planning prompts raised completion **29%** ([Yeomans & Reich 2017](https://researchgate.net/publication/314101810_Planning_prompts_increase_and_forecast_course_completion_in_massive_open_online_courses)).
- Implementation intentions have a pooled d = 0.65. The figure comes from a blog summary of Gollwitzer & Sheeran 2006 ([summary](https://goalsandprogress.com/implementation-intentions-gollwitzer-how-to/)).
- Utility-value reflections reach d = 0.24, with larger effects for weaker students ([Hulleman et al.](https://www.researchgate.net/publication/341600326_The_Utility-Value_Intervention)).
- Habits take a median 66 days to form, and a missed day does not reset them ([Lally et al. 2010](https://www.researchgate.net/publication/32898894_How_are_habits_formed_Modeling_habit_formation_in_the_real_world)). Scheduling must forgive rather than punish.

**Translated into Learny's terms:**

- **Already right:** the hint ladder, FSRS, the bounded session, and no streak counter.
- **Partly right:** the mastery signal. FSRS stability exists, but nothing separates a card passed after a tutor hint from an unaided retrieval. The heatmap counts activity, not learning.
- **Missing:**
  1. A per-section **checkpoint**: predict, read, retrieve unaided with a confidence tap, explain back against the cited passage, then schedule.
  2. A **calibration** view of confidence against accuracy.
  3. A **mastery map** per section, computed only from unassisted retrievals and shown as "N of ~7 spaced successes".
  4. A **book plan** at first open: when, where and how long, an if-then cue, and "why does this book matter to you?".
  5. A forgiving weekly re-ask through the already-authorized digest.
  6. **Interleaved contrast items** across chapters and books.

Each item maps to a strong or medium evidence row above. None requires a new scheduler, model or provider.

## Brazil rewards owned-material study in Portuguese, on Android, paid by Pix

**The segments that study from their own files are adult and large.**

| Segment | Volume | What they study from |
|---|---|---|
| Concurseiros | ~9M registrations per year in a >R$5bn market ([BNews](https://www.bnews.com.br/noticias/economia-e-mercado/mercado-de-concursos-em-2025-pode-movimentar-mais-de-r-5-bilhoes-entenda.html)) | Exam notices (*editais*), law texts (*lei seca*), course handouts (*apostilas*), mostly as PDFs |
| Undergraduates | 10.1M, now **50.7% in distance learning (EAD)**, 95.9% of them in private institutions ([INEP](https://www.gov.br/inep/pt-br/centrais-de-conteudo/noticias/censo-da-educacao-superior/inep-divulga-resultado-do-censo-superior-2024)) | Institution PDFs |
| OAB candidates | ~151k per sitting, three sittings a year ([Damásio](https://blog.damasio.com.br/43-exame-oab-2025)) | Law codes (*Vade Mecum*) and doctrine |
| Developers | 6.9M, +28.5% year on year ([Canaltech](https://canaltech.com.br/mercado/brasil-vira-potencia-no-github-com-crescimento-recorde-de-desenvolvedores/)) | English technical books they would rather be taught in Portuguese |

The ENEM is larger, with 5.06M registrations in 2026 ([Poder360](https://www.poder360.com.br/poder-educacao/enem-2026-tem-505-milhoes-de-inscricoes-confirmadas/)). But it skews to 15–17-year-olds, which triggers the ANPD's "best interest of the child" duty ([ANPD](https://www.gov.br/anpd/pt-br/assuntos/noticias/anpd-divulga-enunciado-sobre-o-tratamento-de-dados-pessoais-de-criancas-e-adolescentes)). Google itself launched study notebooks for personal accounts aged 18+. **Recommendation: launch adult-only and add a guardian flow later.** The cost is deferring the largest single cohort. The benefit is avoiding a regulated minors posture before any learner has been observed.

**Brazilians already use AI heavily, without guidance.** Brazil is ChatGPT's **#3 market**, at ~140M messages a day ([Olhar Digital](https://olhardigital.com.br/2025/08/12/pro/top-3-brasil-e-um-dos-paises-que-mais-usa-chatgpt-no-mundo-veja-as-principais-utilidades/)). In TIC Educação 2024, **70% of high-schoolers** used generative AI for school research but only 32% received any guidance ([Cetic.br](https://cetic.br/noticia/sete-em-cada-dez-alunos-do-ensino-medio-usam-ia-generativa-em-pesquisas-escolares-revela-tic-educacao/)). That is exactly the unmediated, answer-getting use the trials warn about. A tool that teaches from the learner's own book, with visible citations, fills both the trust gap and the pedagogy gap.

**The device and payment constraints are hard requirements, not polish.**

- **Mobile.** 60% of internet users are phone-only, 86% in classes D and E, and only 22% have "satisfactory connectivity" ([Abranet](https://abranet.org.br/noticias/tic-domicilios-2024-60-usam-internet-exclusivamente-pelo-smartphone/); [TI Inside](https://tiinside.com.br/31/10/2024/apenas-22-tem-condicoes-satisfatorias-de-conectividade-no-brasil-aponta-tic-domicilios/)). Android holds 75–83% of mobile OS share ([StatCounter](https://gs.statcounter.com/os-market-share/mobile-tablet/brazil)).
- **Payments.** Pix reached ~86% of adults in 2025 ([Diário do Comércio](https://diariodocomercio.com.br/financas/transacoes-pix-crescimento-bc/)). Installment pricing ("12x R$X") and 10% Pix or boleto discounts are the norm ([Estratégia](https://www.estrategiaconcursos.com.br/assinaturas/)).
- **Pricing anchors.** Spotify Premium is R$23,90 and Google AI Plus is R$24,99 ([Oficina da Net](https://www.oficinadanet.com.br/spotify/68836-quanto-custa-spotify); [gemini.google/br](https://gemini.google/br/subscriptions/?hl=pt-BR)). A future paid tier belongs in the **R$19,90–29,90** "cheap utility" band. That band is an inference from these anchors, not a tested price.
- **Billing hygiene is a differentiator.** The loudest Reclame Aqui complaints about Estratégia and Passei Direto concern auto-renewal, refused refunds, and cancellation flows that do not work ([Reclame Aqui](https://www.reclameaqui.com.br/estrategia-concursos/renovacao-automatica-nao-consentida-e-dificuldade-de-cancelamento-da-assinatura-estrategia-concursos_deobhWYyTE4qosEQ/); [Passei Direto](https://www.reclameaqui.com.br/empresa/passei-direto/)).

**Content and legal shape follow from the same facts.**

- **Free first-run content exists.** Portal Domínio Público holds over 123k works, MEC Livros 1,700, and Gutenberg has a Portuguese shelf ([TechTudo](https://www.techtudo.com.br/listas/2026/04/sites-para-ler-livros-gratis-veja-opcoes-seguras-alem-do-mec-livros-edsoftwares.ghtml); [MEC Livros](https://meclivros.app.br/)). These give first-run value with no copyright risk, and Machado de Assis and Alencar sit on ENEM reading lists. How many Domínio Público works are clean EPUB rather than scanned PDF is unverified.
- **Private study fits the copyright exception; sharing does not.** Lei 9.610/98 art. 46, II allows private copying of "pequenos trechos". The term is undefined ([Jusbrasil](https://www.jusbrasil.com.br/topicos/10625543/artigo-46-da-lei-n-9610-de-19-de-fevereiro-de-1998)). The publishers' association ABDR counts R$1.2bn in 2024 piracy losses and already targets file-sharing platforms such as Passei Direto ([PublishNews](https://www.publishnews.com.br/materias/2025/02/12/pirataria-de-livros-gera-prejuizo-de-r-12-bilhao-em-2024-e-abdr-intensifica-acoes)). Learny's no-sharing stance (RFC-0007 exclusion) is therefore load-bearing in Brazil.
- **Regulation favours Learny's use case.** MEC's AI framework rates "organizing materials" as low risk and automatic test grading as high risk ([Jeduca](https://jeduca.org.br/noticia/ia-na-educacao-entenda-o-novo-referencial-do-mec-e-pontos-de-atencao)). The AI bill PL 2338 is still not law ([Teletime](https://teletime.com.br/16/12/2025/pl-de-inteligencia-artificial-fica-para-fevereiro-de-2026/)).
- **Not researched in this fleet:** LGPD obligations beyond minors, such as the controller contact and international transfer of book passages to US providers. **These need a legal pass before a Brazil launch.**
- **Model quality is not a reason to switch providers.** Maritaca's Sabiá-4 preview beats GPT-4.1 on Brazilian law (97.4 vs 80.8) but trails Gemini-3-Pro on most other benchmarks ([Maritaca](https://www.maritaca.ai/post/sabia-4)). ADR-0020's frontier default stands. Sabiá is at most a future curated profile for cost or data residency. No Brazilian benchmark of Claude models on pt-BR exams was found.

## BYOK should plug user keys into curated profiles, never into arbitrary endpoints

**Policy permits it, with sharp edges.**

- **Anthropic** allows customers to provision their own API keys for third-party tools "provided the resulting usage is billed to the key owner". The same page states that developers "may not collect, store, or intermediate Claude.ai credentials or session tokens" ([Claude Code legal](https://code.claude.com/docs/en/legal-and-compliance)).
- **OpenAI** forbids buying, selling or transferring keys. That wording comes from a search snippet because the terms page returned 403, so it needs re-verification before any ADR quotes it. A community moderator wrote that BYOK apps are "not strictly prohibited" but discouraged outside users' own infrastructure ([OpenAI community](https://community.openai.com/t/bring-your-own-key-policy/446168)).
- **Google**'s Gemini API terms have no BYOK clause. Unpaid-tier content **is used to improve Google products, with human review** ([Gemini API Terms](https://ai.google.dev/gemini-api/terms)).
- **Subscription-as-API stays dead**, as the 09-07 research already concluded.

**The architecture is settled by precedent.** Learny's answers are assembled server-side, and embeddings and decks run in Celery workers. Browser-only key storage, the TypingMind and Open WebUI "Direct Connections" pattern, does not fit. **Server-side envelope encryption does**, in the style LibreChat uses with `user_provided` keys under its encryption key. Each key gets its own data key under AES-256-GCM. A key-encryption key from the environment wraps it. The row stores a fingerprint, the last four characters, the provider and a timestamp. A rotation job re-wraps data keys without touching the ciphertext ([Google Cloud KMS](https://docs.cloud.google.com/kms/docs/envelope-encryption); [LibreChat](https://www.librechat.ai/docs/configuration/dotenv)).

**User-supplied base URLs are the documented failure mode.** Lobe Chat's GHSA-p36r-qxgx-jq2v let a user set a base URL and receive the *server's* API key. Open WebUI's CVE-2024-7959 was an SSRF through the same field ([Lobe Chat advisory](https://github.com/lobehub/lobe-chat/security/advisories/GHSA-p36r-qxgx-jq2v); [GHSA-x757-hv69-jr45](https://github.com/advisories/GHSA-x757-hv69-jr45)). Commercial tools restrict to a provider catalogue: Cursor, Raycast and Vercel's gateway all do ([Cursor](https://cursor.com/help/models-and-usage/api-keys); [Vercel](https://vercel.com/docs/ai-gateway/pricing)). For Learny the policy follows directly:

- **Hosted instances:** a fixed host allow-list (Anthropic, OpenAI, and Gemini through its OpenAI-compatible endpoint, per `docs/research/2026-09-07/README.md`) and no user `base_url`.
- **Self-hosted instances:** an operator-level `base_url` for Ollama, LM Studio or vLLM, which the registry already supports.

Two Learny-specific design choices follow from the existing ADR-0020 machinery.

**First, BYOK keys should bind to curated house profiles, not to a raw model picker.** The rule is "your Anthropic key runs the Claude profile; your OpenAI or Gemini key runs a prompt-cited profile". Every profile stays eval-gated, Ask still never routes to a citation-less profile, and the synthesis's "no raw model picker" exclusion survives intact. This reverses ADR-0020 amendment point 7's gating, which made BYOK conditional on a paid tier, so it needs its own ADR. With BYOK users paying their own provider, the 09-07 "billing-fairness" concern shrinks to a soft budget plus cost display. That is why this report sizes BYOK at **two cycles plus a security review**, against the earlier "3+ cycles". The difference is an inference about reduced scope, not a re-estimate from code.

**Second, embeddings stay operator-level.** No surveyed product offers per-user embedding keys. Switching embedding providers forces a full re-embed and creates mismatched vector spaces ([AnythingLLM docs](https://docs.anythingllm.com/setup/embedder-configuration/overview); [issue #2745](https://github.com/Mintplex-Labs/anything-llm/issues/2745)). On a hosted instance the operator therefore keeps paying ingest embeddings under ADR-0019. Existing byte quotas bound that cost. Its size per book has not been measured in this research.

**Local models are cheap to support for self-hosters and unproven for quality.** Ollama and LM Studio both expose OpenAI-compatible endpoints, and LM Studio adds `/v1/embeddings` ([Ollama](https://ollama.com/blog/openai-compatibility); [LM Studio](https://lmstudio.ai/docs/app/api/endpoints/openai)). Learny's `openai-compatible` profile kind can point at them today. Nothing documents or tests that path. Secondary sources suggest **Qwen3 8B** at about 7 GB in Q4 for pt-BR laptops ([promptquorum, secondary](https://www.promptquorum.com/local-llms/best-local-llms-portuguese-language-2026)). **Tucano 2** (0.5–3.7B, USP, March 2026) is post-trained for RAG in Portuguese ([arXiv 2603.03543](https://arxiv.org/abs/2603.03543)). No public benchmark measures *cited* pt-BR answers on small models, so Learny's golden fixtures would be the first such measurement. A fully offline self-host also needs local embeddings. That conflicts with ADR-0019's OpenAI lock and needs an amendment, scoped to self-host only and recorded on the existing per-chunk `embedding_model` column.

**The business model that fits is free self-host and free hosted BYOK first, a paid convenience tier later, and Pix through a merchant of record.**

| Analogue | Model | Outcome | Source |
|---|---|---|---|
| TypingMind | Free BYOK plus one-time licences, later a Teams tier | ~$130–160k per month by Oct 2025; Teams >50% of revenue | [Tony Dinh](https://news.tonydinh.com/p/oct-2025-updates-code-money-and-travel) |
| Raycast, Zed | BYOK added to widen the free tier | Received as goodwill | [Zed](https://zed.dev/docs/account/plans-and-pricing) |
| Cursor | Free-plan BYOK curtailed | Visible backlash | [Cursor forum](https://forum.cursor.com/t/own-api-key-in-free-plan/154357) |
| Khoj Cloud, Omnivore | Hosted second brains | Both shut down | [app.khoj.dev](https://app.khoj.dev/); [molodtsov.me](https://molodtsov.me/2024/10/omnivore-is-dead-where-to-go-next/) |

The lessons are direct. Launching BYOK-first avoids ever having to take a feature away. Self-host-first is the pattern that survives. OSS SaaS conversion runs at 0.5–3% ([Monetizely, secondary](https://www.getmonetizely.com/articles/whats-the-optimal-conversion-rate-from-free-to-paid-in-open-source-saas)), so the free BYOK cohort must cost Learny storage and compute only, never inference.

**For payments, Paddle is the one merchant of record with Pix Automático** for recurring charges as of 2026 ([Paddle](https://developer.paddle.com/changelog/2026/pix-automatico/)). Stripe gives Brazil-registered accounts one-time Pix only ([Stripe](https://docs.stripe.com/payments/pix)). Lemon Squeezy has no Pix. This confirms RFC-0007's recorded Paddle choice.

**On licensing, Learny is Apache-2.0 today (`LICENSE`).** The BYOK researcher recommends AGPL-3.0 to protect a future hosted service. The steelman: Plausible and Immich use AGPL, and it prevents a hosted fork. This report recommends **keeping Apache-2.0** while the owner's stated goal includes an interview-grade showcase (`.specs/project/ROADMAP.md`, `portfolio-truthful` row). Learny's moat is pedagogy, evaluation and operations, not code secrecy. Relicensing later is possible for a sole author, provided no outside contributions have landed. That condition is unverified. An optional Immich-style supporter licence with no paywalled features is compatible with the 09-03 "no lifetime pricing" exclusion, because it sells no plan.

## Candidate roadmap rows, prioritized and sized

The ordering logic follows from the evidence:

1. **Unlock the launch.** Portuguese, BYOK, an installable app and an adult-only posture come first, because no stranger has ever used Learny and RFC-0007's activation funnel has never fired on one.
2. **Deepen the differentiator.** Then the evidence-backed learning loop.
3. **Ecosystem and money last.**

Sizes are in ship-cycles, meaning one PR each, using the repo's own convention. **Operator prerequisites (not cycles):**

- **O1.** Fund the CI Anthropic key so the nightly judge is green again. It gates any new profile, BYOK, local or economy.
- **O2.** Choose a host and flip the GHCR `learny-minio` package public.
- **O3.** Get a short legal pass on LGPD and international transfers for Brazil.
- **O4.** Record the demo media.

### Paste-ready rows for `.specs/project/ROADMAP.md`

```markdown
## v8 (candidate — research 2026-09-30, "study home" delta)

| tlc Cycle | Source | Scope | Status |
|---|---|---|---|
| `pt-br-interface` | Research 2026-09-30 (Brazil priority; ledger KQ4) | UI i18n framework + pt-BR/en catalogs + locale negotiation; tutor/answers speak the learner's language while quoting citations in the book's language; pt-BR golden fixture (public-domain Portuguese book) in the offline eval set | Not started |
| `byok-secrets-and-chains` | Research 2026-09-30 + 2026-09-07 §3.3 Flavor B; ADR-0020 amendment pt. 7 reversal (new ADR) | Envelope-encrypted per-user provider keys (AES-256-GCM, env KEK, rotation job); per-user adapter cache keyed on (provider, model, key fingerprint); workers receive credential row id, never the key; keys bind to curated house profiles only | Not started |
| `byok-hosted-policy` | Research 2026-09-30 (base_url CVEs; provider terms) | Hosted provider allow-list (Anthropic, OpenAI, Gemini-compat), no user base_url; BYOK users exempt from house spend cap but keep rate limits + per-corpus prompt-token ceiling; per-answer token/cost display + soft monthly budget; provider privacy badges (Gemini unpaid trains); disclosure copy; security review checklist | Not started |
| `local-models-self-host` | Research 2026-09-30 (Ollama/LM Studio compat); ADR-0019 amendment (self-host local embeddings) | Documented + tested operator profile for an OpenAI-compatible local runtime; optional local embedding model for self-host with per-corpus model/dimension and forced re-embed on change; golden results recorded for one pt-BR-capable local model | Not started |
| `installable-and-adult-launch` | Research 2026-09-30 (Brazil mobile/LGPD); AD-320/AD-325 deferrals | PWA manifest + service worker; offline cache of the current book's chapters; low-bandwidth budgets; 18+ attestation at signup; pt-BR legal pages; capped guest sample Ask (AD-320 thaw) | Not started |
| `section-checkpoint-and-calibration` | Research 2026-09-30 (rq02 moves 1,3,7; SCALE/Bastani; calibration meta-analysis) | End-of-section checkpoint: prediction prompt → unaided retrieval with one-tap confidence → explain-back judged against the cited passage → FSRS scheduling; review grades also capture confidence; per-book calibration view | Not started |
| `honest-mastery-map` | Research 2026-09-30 (Koedinger 2023; Gervet 2020) | Per-section mastery from unassisted, spaced successes only (assisted/hinted passes recorded but not counted); "N of ~7" display replaces activity-as-progress; per-user desired retention (rq08 Cycle 4) | Not started |
| `book-plan-and-digest` | Research 2026-09-30 (Yeomans & Reich; implementation intentions; utility value); AD-304/AD-328 thaw | First-open plan prompt (when/where/how long + if-then cue + "why this book"); forgiving weekly re-plan; opt-in due digest via EmailPort | Not started |
| `biblioteca-aberta` | Research 2026-09-30 (Domínio Público, MEC Livros, Gutenberg pt) | Operator-curated shelf of pre-ingested public-domain pt-BR books as shared system corpora (the sample pattern, N books), each with starter cards | Not started |
| `shelf-ask` | rq01 move 10; Readwise Global Ghostreader | Cited Ask across a learner-chosen set of their books in one conversation; citations keep book+section anchors | Not started |
| `library-mcp` | Research 2026-09-30 (Readwise/Recall/Lantern MCP) | Per-user, read-only MCP server exposing cited retrieval and due items to external assistants; passage-length caps | Not started |
| `paid-hosted-tier` | RFC-0007 finding 11 (Paddle); research 2026-09-30 (Pix Automático, PPP) | Paddle MoR checkout, BRL + PPP pricing, Pix Automático, one-click cancel, house profiles as the paid convenience | Not started |
```

### Row detail: goal, size, evidence, non-goals, prerequisites

| # | Row | One-line goal | Size | Motivating evidence | Must NOT do | Prerequisites |
|---|---|---|---|---|---|---|
| 1 | `pt-br-interface` | A Brazilian learner uses Learny entirely in Portuguese, and the tutor teaches in pt-BR even from an English book | 1–2 | UI hard-coded `lang="en"` with no i18n library (ledger KQ4). Brazil is the priority market. Developers are an audience for pt-BR teaching from English technical books (Brazil notes, inference). | Machine-translate book text or citations. Change retrieval language handling, which already works. Add a pt-BR-specific model. | O1, so the pt-BR golden can be judged |
| 2 | `byok-secrets-and-chains` | A user's own provider key powers their Ask, Tutor, Explain and decks, stored encrypted and never leaked to logs or payloads | 1 | Anthropic permits customer keys billed to the owner ([legal](https://code.claude.com/docs/en/legal-and-compliance)). The three 09-07 blockers are still open (ledger KQ6). The LibreChat and KMS envelope pattern. | Store plaintext. Put keys in Celery args. Pool or route one user's calls through another's key. Accept Claude.ai or ChatGPT logins. Per-user embedding keys. | New ADR superseding ADR-0020 amendment point 7. O1. |
| 3 | `byok-hosted-policy` | Hosted BYOK is safe against SSRF, server-key exfiltration and bulk book extraction, and its cost is visible | 1 + security review | Lobe Chat GHSA and Open WebUI CVE-2024-7959. Cursor and Vercel allow-lists. Gemini unpaid-tier training clause. | Allow a user `base_url` on a hosted instance. Proxy subscriptions. Apply ZDR promises to BYOK traffic. Add a raw model picker. | Row 2 |
| 4 | `local-models-self-host` | A self-hoster runs Learny with no cloud keys at measured quality | 1 | Ollama and LM Studio OpenAI-compatible endpoints. The `openai-compatible` kind exists but is untested. Indie competitors (Lantern, ReadAny, Obsidian Copilot) advertise local or BYO AI. | Ship local models on the hosted instance. Claim pt-BR quality without golden results. Add a new SDK; it goes through the compat adapter. | ADR-0019 amendment, self-host only |
| 5 | `installable-and-adult-launch` | Learny is installable and readable offline on a mid-range Android phone, open to adults, with a no-account taste of the sample | 1–2 | 60% of Brazilians are phone-only and only 22% are well connected (Cetic.br). The ANPD minors guidance. Gemini study notebooks are 18+. The guest Ask authorized by AD-320 was never scheduled. | Build native apps. Admit minors without a guardian flow. Offer uncapped guest Ask. Ship analytics SDKs. | Rows 1, 3. O2, O3. |
| 6 | `section-checkpoint-and-calibration` | Every finished section ends in an unaided, confidence-rated retrieval and an explain-back checked against the cited passage | 2 | Testing effect g = 0.61. Self-explanation g = 0.55. Explain-back g = 0.56. Attempt-first ordering. Judgments of learning and confidence weighting. The Bastani guardrail. | Give the answer before the attempt. Let a hinted pass count as unaided. Market explain-back as "grading" (MEC high-risk). Add MCQ or a second scheduler. | None hard. A green nightly to judge explain-back prompts. |
| 7 | `honest-mastery-map` | Progress shows what the learner can retrieve unaided, per section, over time | 1 | ~7 opportunities per component (Koedinger). Logistic models suffice (Gervet). Assisted-performance illusion (SCALE). | Add streaks, XP or points. Count reading time or AI-assisted turns as mastery. Add BKT or deep knowledge tracing. | Row 6 |
| 8 | `book-plan-and-digest` | Each book starts with a learner-made plan and a reason, and lapses are met with a gentle re-plan | 1 | Planning prompts +29% completion. Implementation intentions d = 0.65. Utility value d = 0.24. Habits take 66 days. The Khanmigo engagement constraint. | Punish missed days. Send push spam or WhatsApp blasts. Impose a non-learner-chosen schedule. | EmailPort, already shipped. Mail domain (operator). |
| 9 | `biblioteca-aberta` | New Brazilian users open a Portuguese classic in seconds, cited and with cards, no upload needed | 1 | Domínio Público has 123k+ works and MEC Livros 1,700. ENEM reading lists. The shared-sample pattern is proven (PR #67). | Host copyrighted books. Clone embeddings per user. Build a store or catalog marketplace. Ingest HTML law texts; HTML is unsupported (ADR-0011). | Row 1 |
| 10 | `shelf-ask` | Ask one cited question across several of your own books, such as a notice, a law code and a handout | 1 | Readwise Global Ghostreader. Gemini notebook silos. Concurseiros study from multiple PDFs at once. | Cross users or reach into the shared sample's notes. Drop section anchors. Raise `top_k` without the retrieval ruler (RFC-0007 conflict 7). | ADR-0029 amendment (multi-source scope) |
| 11 | `library-mcp` | ChatGPT, Claude and other assistants become clients of the learner's Learny library | 1 | MCP servers from Readwise, Recall and Lantern. Gemini has no consumer API, which HN users cite as a reason to leave. | Return whole chapters (relay risk). Expose other users' data. Allow write tools in v1. | Rows 2–3 for auth patterns |
| 12 | `paid-hosted-tier` | Users who don't want to manage keys pay a fair BRL price via Pix and can cancel in one click | 1–2 | Paddle Pix Automático 2026. PPP ~50% for Brazil (vendor claim). The R$19,90–29,90 band. Reclame Aqui billing complaints. | Paywall FSRS, export or BYOK. Add dark-pattern renewals. Sell lifetime plans. | Hosted traction data. O2. O3. |

**Total:** about 13–16 cycles. Rows 1–5 form the launch slice, rows 6–8 the learning-science slice, and rows 9–12 growth and ecosystem. Rows 6–8 can interleave with rows 2–5 by surface: reader and review versus the provider layer. The `honest-mastery-map` row should not ship before `section-checkpoint-and-calibration`, because it needs the unassisted signal that row creates. The recorded small items stay as they are: the MinIO unprivileged-user follow-up and economy-profile promotion once O1 is done.

### Do-not-build list

| Do not build | Reason |
|---|---|
| Audio or video overviews, podcasts, lecture recorder | Google ships all of them in 80+ languages. They carry no citations, and critics document misinformation risk ([XDA](https://www.xda-developers.com/notebooklm-audio-overviews-sound-human-believe-misinformation/)). They compete on Google's terrain. |
| Licensed-book store or catalog | Google's Play Books integration covers 100k+ titles from major publishers. An indie app cannot license at that scale. |
| Any user-to-user sharing of book files, book-derived decks or passages | Brazilian copyright art. 46 covers private use only, and ABDR already targets file-sharing platforms such as Passei Direto. The RFC-0007 exclusion stands. |
| User-supplied `base_url` on a hosted instance | Documented SSRF and key-exfiltration CVEs. It is also a relay for copyrighted text. |
| Subscription or OAuth "bring your own ChatGPT/Claude plan" | Anthropic prohibits it in writing. The 09-07 research rejected it. |
| Per-user embedding keys | Fragments vector spaces and forces re-embeds. No surveyed product does it. |
| Raw model picker | It breaks the eval gate and Ask's citation guarantee. BYOK binds to curated profiles instead. |
| Streaks, XP, badges or leaderboards as the progress model | Small effects. They reward activity, not unassisted retrieval. |
| Progress metrics computed from AI-assisted turns | They reproduce the assisted-performance illusion (Bastani, Chen, Lehmann). |
| Answer-first tutor default | Unrestricted answer-giving harmed unassisted outcomes. Keep "just explain" one tap away, never the default. |
| Essay or exam "grading" products | MEC rates automatic grading high-risk. Explain-back feedback stays formative and passage-anchored. |
| Native iOS or Android apps, now | A PWA covers phone-only Android users at a fraction of the cost. Revisit after usage data. |
| Generic "PDF → 100 flashcards" volume race | The incumbents' weakness: hallucinations, ads and upsells. Learny's QC gates and empty-deck honesty are the opposite bet. |
| A Brazilian fine-tuned or local-first default model | Frontier models still lead on most pt-BR benchmarks. Sabiá is at most a curated optional profile later. |
| Classroom or LMS integrations, B2B for schools | Google owns Classroom. Minors and B2B contracting come after the consumer loop is proven. |
| Knowledge graph, mind maps, outliner | Still on the 09-03 do-not-build list. No learning evidence ties them to retention. |

## Conclusion

The research changes the thesis from "Learny is the book app that cites" to **"Learny is the study app that knows what you can do without it."** Citations, EPUB and even Socratic tutoring have become table stakes or are on Google's roadmap. Three things have not: honest, unassisted, per-passage measurement of learning; a plan-and-review rhythm that survives months; and full ownership of keys, models, data and export. These are also exactly what the 2024–2026 trials say separates AI that helps from AI that harms. Learny's existing architecture is unusually well placed to add them. It already has application-owned tutor state, FSRS, citation snapshots on cards, a profile router and a per-user seam. They are additions to an existing loop, not a new product.

The binding constraints are not engineering. A red nightly gate, no host and no observed learner mean every claim of "better than NotebookLM" is so far an argument, not a measurement. The first Brazilian, BYOK, Portuguese-speaking learner who completes a section checkpoint unaided will be worth more evidence than this whole report. The roadmap above is ordered to reach that learner first.
