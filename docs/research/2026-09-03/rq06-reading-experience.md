# RQ06 — Reading experience

*Date: 2026-09-03. Question: what reader UX would make people **want** to read inside Learny instead of Kindle, Apple Books, or Readwise Reader?*

Grounded in the current chapter-flow reader (`frontend/app/components/chapter-reader.tsx` and siblings), the 2026-09-03 walkthrough, RFC-004 / ADR-027 (already shipped), and a 2026-07-18 precursor (`docs/research/2026-07-18/student-experience/rq01-reading-surfaces.md`). That earlier report asked how to *structure* a reading screen; this one asks what is still missing for a stranger to *prefer* Learny as the place they actually finish a book.

## TL;DR

Learny already has the study-reader skeleton peers pay for: chapter-flow scroll, 19px/1.6/65ch serif, `Aa` + Paper, resume + minutes-left, receding chrome, five-verb selection, Ask/Teach/Notes/Review dock, inline highlights, jump-back. **That is not enough to beat Kindle or Apple Books at reading.** Those products win on images, hours-long visual quiet, phone-in-bed, font/theme personality, and “I always land exactly where I stopped.” Readwise Reader wins on keyboard-first capture and a Chat sidebar that never leaves the page — and *loses* on clutter, price, and a week-long learning curve.

The public-launch bar is not “more Kindle.” It is: **the book column is as comfortable as Matter/Kindle, and the AI dock is as close as Ghostreader, with Learny’s cited answers as the reason you stay.** Until figures render, chrome recedes to a true long-form view, and a phone can actually read, strangers will upload a book, ask one question, and go back to Kindle for the remaining 280 pages.

Do **not** copy Readwise’s dense power-user chrome, Kindle’s uncited Ask-This-Book, NotebookLM’s chat-first three-pane (document as a viewer), or multi-color highlight systems. Do copy: Matter’s one-gesture yellow mark, Readwise’s `[` `]` panel collapse and `G`→sidebar Chat, Kindle’s cycle-able time-left, Apple Books’ theme-vs-light/dark axes (already in ADR-027), Hypothesis’s “one color + semantics elsewhere,” and Acrobat/NotebookLM’s click-citation → scroll-and-flash (already in the dock).

## Benchmark evidence

### Readwise Reader — closest peer, and the clutter trap

Official: [Appearance](https://docs.readwise.io/reader/docs/faqs/appearance), [Highlights / tags / notes](https://docs.readwise.io/reader/docs/faqs/highlights-tags-notes), [Navigation](https://docs.readwise.io/reader/docs/faqs/navigation), [Ghostreader](https://docs.readwise.io/reader/guides/ghostreader/overview).

- **Long-form view** is on by default for EPUBs: hides the action-heavy bottom bar, elevates progress + `Aa`. Side panels collapse with `[` / `]` and can default hidden. Line width is a first-class web control (`Shift+,` / `Shift+.`). Fonts include Atkinson Hyperlegible and OpenDyslexic; default 20px / 1.4 leading.
- **Keyboard reading:** arrows move a paragraph focus; `H` highlights the focused paragraph; `N` notes; `T` tags; `G` / `Shift+G` invoke Ghostreader. Image highlights are first-class (`H` on a focused figure). **No multi-color highlights** — tags carry semantics instead.
- **Ghostreader converged on:** selection in the text as trigger, **Chat tab of the right sidebar as the answer surface**. Presets adapt to selection length (1–3 words = define/lookup; longer = explain/expand). Expand-passage can save as a note on the highlight. Ghostreader answers are **not** passage-cited back into the book.
- **Pagination:** they rejected horizontal page-flip because it breaks cross-page selection and swipe-to-open-panels; shipped **vertical paged scroll** + tap margins instead. Two-column only on tablet landscape.
- **Praise:** one inbox for articles/EPUBs/PDFs; one-keystroke capture; Daily Review + Obsidian export; “thinking with” the library ([Asian Efficiency 2026](https://www.asianefficiency.com/productivity/readwise-reader-review/), [The Unhacked](https://theunhacked.com/readwise-reader-review-knowledge-management/)). Post-Pocket (sunset 2025-07-08) it is the default serious read-later.
- **Complaints:** ~$10/month, no free tier; dense UI and a week to find a workflow; Android feels borrowed from iOS; search is weak; crashes ([ProdApps](https://productivity-apps.com/apps/readwise-reader), ~3.64/5 recent). Switchers to Matter cite **cleaner reading**, not missing AI.

### Kindle (app + [Kindle for Web](https://www.amazon.com/gp/help/customer/display.html?nodeId=TT200NNkr2BE4Jnsy9))

- `Aa`: Bookerly / Ember / OpenDyslexic; 14 sizes; margins; 1–2 columns; page color white / sepia / light green / black. Themes save *bundles*. [Accessible reading options](https://www.amazon.com.au/gp/help/customer/display.html?nodeId=TABlJ4ot69emTO8jJG).
- **Progress is the gold standard:** cycle time-left-in-chapter / page-in-book / time-left-in-book. Time-left-in-chapter is the session-pacing unit.
- **Whispersync** ([Amazon help](https://www.amazon.com/gp/help/customer/display.html?nodeId=GGFEXXS8Z7DPJSTN)): last page, notes, and highlights across every device, on by default. Conflicts offer “furthest page.” This is why people trust Kindle with a 400-page book.
- **Ask This Book:** highlight → Ask in the selection menu, overlay chat, spoiler-scoped to current position — and **no citations, no jump-back** ([Kindlepreneur](https://kindlepreneur.com/amazon-ask-this-book/), secondary). Right invocation, wrong grounding. Learny already inverts this correctly.

### Apple Books

- [Annotate on iPhone](https://support.apple.com/guide/iphone/annotate-books-iph17bf340c1/ios), [highlights on Mac](https://support.apple.com/guide/books/highlight-book-passages-and-add-notes-ibks3975f128/mac), [themes](https://www.idownloadblog.com/2022/09/21/how-to-use-themes-in-books-app-on-ipad-iphone/).
- Six named themes (Original / Quiet / Paper / Bold / Calm / Focus) **orthogonal** to Light / Dark / Automatic. Curl / Fast Fade / **Scroll**. Bookmarks & Highlights panel per book. Multi-color + underline. iCloud resume. This is the “it just feels like a book” bar; AI is absent.

### Matter

- [MacStories](https://www.macstories.net/reviews/matter-a-fresh-take-on-read-later-apps/), [Sweet Setup vs Reader](https://thesweetsetup.com/is-matter-or-readwise-reader-the-read-later-app-for-you/), [Breen 2025](https://robertbreen.com/2025/02/27/elevate-your-online-reading-with-matter/).
- One **neutral yellow**; long-press-and-drag highlights with **no popover** until you tap the mark. Paper theme. Queue shows time-to-read, % done, annotation count. AI Co-Reader: tap paragraph → suggested questions (Perplexity-grounded, *not* the article). Complaints: Apple-only, parsing glitches, highlight search, $60/year after locking highlights behind Premium.

### Zotero 7 PDF/EPUB reader

- [Rice LibGuide](https://libguides.rice.edu/c.php?g=1001613&p=9660073), [Harvard](https://guides.library.harvard.edu/c.php?g=1245347&p=9207882), [note templates](https://www.zotero.org/support/note_templates).
- Eight colors; sticky notes vs quote-anchored highlights vs area snapshots (figures/charts). Left annotation pane auto-collects quotes. Color-conditional export templates (red → heading, blue → blockquote). Scholarly color *is* a workflow — and it fights accessibility (see Hypothesis). Learny’s tags + note titles are the cleaner semantic layer; area-snapshot for figures is the missing verb once images exist.

### Hypothesis

- [Accessibility](https://web.hypothes.is/accessibility/) (WCAG 2.1 AA), [multi-color backlog](https://github.com/hypothesis/product-backlog/issues/198), [client discussion](https://github.com/hypothesis/browser-extension/issues/1514).
- One highlight wash; notes in a **bucketed right sidebar**; orphans kept with quote snapshots (Learny already does this, ADR-0026). They still have not shipped user colors: semantics collide with color-blind users in a shared context. Private color palettes mapped to tags is the only design that survives WCAG 1.4.1.

### Typography for long-form

- Measure: Butterick [45–90 characters](https://practicaltypography.com/line-length.html); Bringhurst/Baymard ~50–75, ~66 ideal; [WCAG 1.4.8 Visual Presentation (AAA)](https://www.w3.org/WAI/WCAG21/Understanding/visual-presentation.html): ≤80 chars (40 CJK), not justified, leading ≥1.5, user-selectable fg/bg, 200% resize without horizontal scroll. Learny’s `max-width: 65ch` + ragged-right + `hyphens: none` is the right default.
- Dyslexia: BDA-style advice is short lines, 1.5 leading, off-white grounds, left-align — **not a magic font**. Rello & Baeza-Yates (ASSETS 2013) and Wery & Diliberto (*Annals of Dyslexia*) found **OpenDyslexic did not improve rate/accuracy**; readers preferred Verdana/Helvetica. Ship Atkinson Hyperlegible + a clean sans as *options*; do not brand a “dyslexia mode.” Paper (already shipped) is the glare valve.
- Dark: cool off-black ink on a night ground (ADR-027 already). Avoid pure `#000`/`#fff`. Sepia/Paper in *light* is table stakes; Apple/Kindle keep dark as a separate axis — Learny already does this.

### Images, security, why it matters

EPUB/XHTML can carry scripts. Foliate-js: **do not render book HTML without CSP**; `sandbox` + `allow-scripts` + `allow-same-origin` is equivalent to no sandbox ([foliate-js README](https://github.com/johnfactotum/foliate-js), [Grimmory XSS advisory](https://github.com/grimmory-tools/grimmory/security/advisories/GHSA-frv6-5wq5-9p24)). Apple’s iBooks model: no network, no persistence from the book.

Learny does not iframe EPUB HTML. It derives Markdown (`markup._image` → `![alt](src)` with the EPUB’s **relative** `src`) and renders via Streamdown. Streamdown’s `rehype-harden` defaults `allowedImagePrefixes: []`, so every figure becomes **`[Image blocked: …]`** — exactly the walkthrough. The block is a correct security default aimed at LLM markdown, applied to *the book*. Relative `OEBPS/images/fig1.png` is not a Learny origin, so harden is right to refuse it. The product gap is: **binaries are never extracted to MinIO**, so there is nothing safe to allowlist.

### Accessibility standards for book readers

- [EPUB Accessibility 1.1](https://www.w3.org/TR/epub-a11y-11/) maps WCAG to publications; [EPUB a11y techniques](https://www.w3.org/TR/epub-a11y-tech/) + [DPUB-ARIA](https://www.w3.org/TR/dpub-aria-1.0/) (`doc-chapter`, `doc-pagebreak`, `doc-toc`, `doc-footnote`). Reading systems must expose structure to the platform a11y API.
- WCAG 2.2 AA for the *app chrome*; 1.4.12 Text Spacing; 2.4.11 Focus Not Obscured (dock + sticky bar); 2.5.8 Target Size. Page lists / skip-to-TOC are expected in a reading system, not optional polish.
- European Accessibility Act 2025 is now in force for ebooks in the EU; a public web reader that cannot reflow, resize, or expose a TOC to AT is a compliance problem, not a nice-to-have.

### Reading + AI side-panel — the converged layout

| Product | Document | AI | Citation jump |
|---|---|---|---|
| Readwise Ghostreader | Full-width column; panels optional | Right Chat tab | Weak / undocumented |
| Kindle Ask This Book | Full page | Overlay chat | None |
| NotebookLM / Gemini Notebook | Left sources *viewer* | Center chat | Hover quote, click → highlight in viewer |
| Acrobat AI Assistant | PDF canvas | Right chat | Numbered cite → scroll + highlight |
| ChatGPT Canvas | Separate workspace | Chat + doc | N/A (generated doc) |
| Matter Co-Reader | Full article | Inline on paragraph | Web footnotes, not the article |
| **Learny today** | Chapter column | Right dock Ask/Teach/Notes/Review | Show-in-book + heading flash |

Consensus for a *reading* product (not a notebook): **text stays the primary column; conversation is a non-modal right dock; selection verbs open the dock, never a new page.** NotebookLM is the anti-pattern if Learny wants people to *finish* books. Composite’s 2026 note is useful: a persistent ~400px sidebar is right for multi-turn work and wrong when it permanently starves the measure — which is why Readwise lets you hide it and Learny already closes the dock by dropping `?panel=`.

## Critique of Learny’s current reader

Walkthrough (2026-09-03): TOC sidebar, progress `N% read · M min left`, `Aa`, per-chapter highlights, next/prev chapter, dock Ask/Teach/Notes/Review, **images as `[Image blocked]`**.

What RFC-004 already got right (do not rebuild):

- Chapter-flow article, section `id={anchor}`, `?anchor=` + resume from `GET /chapter` without a query (`chapter-reader.tsx`, `lib/reading.ts`).
- Device-local `learny.reading.v1`: size 17/19/21/23, leading 1.5/1.6/1.8, Default/Paper; theme via next-themes (`use-reading-settings.ts`, `reading-controls.tsx`). Source Serif 4, `65ch`, Iron Gall dark (`globals.css`, ADR-027).
- Scroll-idle position write (2s), IntersectionObserver on **section** wrappers (`use-scroll-position.ts`); 220 wpm minutes-left; ink-line fill; Return chip after TOC/citation jumps.
- Capture against **served Markdown**, not DOM (`deriveCaptureSelection`); five verbs; `h`/`c` only while the popover is up (`use-key-shortcuts.ts`).
- Dock is URL state (`?panel=`), 26rem, citations `onShowInBook`. Margin rail yields to the dock (AD-139). Receding top bar with `motion-reduce`.

Why a stranger still will not *read* here:

1. **Figures are gone.** Ingestion keeps `img` blocks and even merges image-only sections (`normalization.py` `_IMAGE_BLOCK_TYPES`), then serializes `![alt](epub-relative-src)`. The reader’s Streamdown/rehype-harden allowlists nothing. Textbooks, O’Reilly-style diagrams, illustrated history, and most PDFs-with-figures become a wall of placeholders. Kindle/Books/Reader all show the picture. This is the single largest “I cannot study here” defect.

2. **The surface is still an app, not a book.** `(app)/layout.tsx` wraps *every* authenticated route — including `/read` — in `AppSidebar` + `AuthHeader`. Plus TOC (`lg` column) plus optional 26rem dock plus margin rail. Readwise’s long-form view exists specifically to hide this class of chrome. On a 1440px laptop the measure survives; on a 13" or a tablet it does not. The sticky chapter bar recedes; the **product nav does not**.

3. **Desktop-web, mouse-only.** Capture is `onMouseUp` on the section. No touch handles, no long-press, no `selectionchange`. RFC-004 locked “desktop-web first but responsive; native apps out.” Below `lg`, TOC collapses (good) and the rail stacks under the article (good), but the dock is still `w-[26rem]` and the five-verb popover is a desktop control. Public launch without a phone-readable column means Learny loses every commute/bed session to Kindle and Apple Books.

4. **Resume is section-granular.** Position is the topmost **section** anchor, not a scroll offset or CFI. A 4,000-word section always reopens at its heading. Kindle’s “exact page” is why people trust it overnight. The Return chip helps citation jumps, not “I stopped mid-paragraph.”

5. **Typography is one face, one measure, one language.** `html lang="en"` is hardcoded (`layout.tsx`) even though corpus language is detected and stored (ADR-0025, `pt` heuristics in normalization). Hyphenation is off with no opt-in. No line-width control (Readwise), no OpenDyslexic/Atkinson, no Literata-on-Paper (ADR-027 allowed it; Paper today is palette-only). Size tops out at 23px (Kindle has 14 steps; Reader to 80px). Low-vision and Portuguese long-word books are under-served.

6. **Keyboard is not a reading mode.** Bindings exist only for `h`/`c` while the popover is visible. No paragraph focus, no `[` `]` for TOC/dock, no `j`/`k` chapter, no `?` cheatsheet, no `G` for Explain. Power users coming from Reader will feel trapped in the mouse.

7. **Capture is study-first.** Five verbs on every selection is RFC-004’s hub — and it is heavier than Matter (mark first, menu on tap) and Kindle (color chips). Auto-highlight is correctly default-off in RFC-004 Cycle D; for *reading flow* the popover still asks you to decide Highlight vs Note vs Explain vs Ask vs Create card before you have finished the sentence. Cross-block selections silently produce no popover (`deriveCaptureSelection` requires a verbatim Markdown substring).

   | Product | Gesture | Immediate result | Later |
   |---|---|---|---|
   | Matter | Drag | Yellow mark | Tap mark → note / share / delete |
   | Readwise | `H` or select | Highlight (optional auto) | `N`/`T`/`G`; margin notes |
   | Kindle / Books | Select → color | Colored mark | Note / share from same menu |
   | Zotero | Tool then drag | Color + left-pane quote | Sticky / area snapshot |
   | Hypothesis | Select → Annotate | One wash + sidebar card | Reply / tag / orphan |
   | **Learny** | Mouse-up → 5 buttons | Nothing until a verb | Dock Explain/Ask; card chips |

   The winning public default is Matter’s: **the mark is instant; AI verbs are one extra tap, not five choices in the way of the highlighter.** Keep Explain/Ask/Create card — put them on the mark, not on the virgin selection.

8. **Book a11y semantics are thin.** Page rules are `aria-hidden` + `data-reader-scaffold` (correct — they must not shift highlight offsets). The article is not a DPUB landmark; TOC is an `aside` not `doc-toc`; no skip-to-prose; progress is a visual ink-line + text, not a live region. Screen-reader users get a web article with extra headings, not a reading system.

9. **PDF vs EPUB is one Markdown river.** Docling figures suffer the same blocked-image fate. Area-snapshot (Zotero) does not exist, so even after images ship, PDF diagrams without extractable `alt` need a crop verb.

## Prioritized UX recommendations

**P0 — must be true to prefer Learny for a whole book**

1. **Safe figures.** Extract image bytes at ingest into owner-scoped MinIO keys; rewrite Markdown `src` to an authenticated same-origin URL; allowlist that prefix in Streamdown harden; `<img alt>` from EPUB/PDF; CSP `img-src 'self'`. Never iframe book HTML, never `allow-scripts`+`allow-same-origin`, never `javascript:`/`data:` except tightly sized raster if Docling emits it (prefer re-encode to WebP/AVIF on ingest). Decorative empty-alt images can stay collapsed; content images must not say `[Image blocked]`.
2. **Immersive reading chrome.** A long-form mode (default on `/read`): hide app sidebar + auth header; TOC and dock remain toggles (`[` / `]`). Preserve 65ch when the dock opens by collapsing the rail (already) and, on `<xl`, overlaying the dock instead of shrinking the column to death.
3. **Phone-usable web reader.** Reflow the column to the viewport; bottom sheet for the dock; touch selection → compact verb bar (Highlight / Ask overflow); 44px targets; no horizontal scroll at 200% zoom. Native apps stay out of scope (RFC-004).

**P1 — makes daily reading feel owned**

4. **Typography pack:** book `lang` on the article (hyphens optional); measure stepper; size range ~16–32px; Atkinson Hyperlegible + a grotesque as reading-face options; keep Source Serif 4 default; do not advertise OpenDyslexic as clinically superior. Cycle-able progress (percent / min left in chapter / min left in book).
5. **Keyboard reading:** paragraph (or section) focus, `H`/`N`/`G`, `[` `]` `?`, chapter `j`/`k`. Guard typing targets as today.
6. **Finer resume:** persist scroll offset *within* the current section (or a word-index) alongside the anchor; last-write-wins already exists.
7. **Capture friction:** keep five verbs, but Highlight on pointer-up can be a one-tap default with the rest in overflow/`…`; optional auto-highlight, default off. Image highlight once figures exist.

**P2 — after the book is pleasant**

8. Do **not** ship 8-color highlighters in v1 of public; tags + note titles already encode meaning. If colors arrive, they are user-private labels, never the only signal (WCAG 1.4.1).
9. Vertical paged-scroll (Readwise’s compromise) only if dogfood shows chapter-scroll losing the place; RFC-004 correctly deferred pagination.
10. DPUB-ARIA landmarks, skip link, progress as `aria-live="polite"` on pause, focus return from dock/citation popover (citation Escape already exists).
11. Figure crop / PDF area snapshot (Zotero) once bytes exist.

## Cycle-sized moves

### Cycle: Safe figures (extract → MinIO → allowlisted `<img>`)

- **Why recommend:** The walkthrough’s `[Image blocked]` is rehype-harden doing its job on EPUB-relative URLs that were never promoted to Learny resources. Without pictures, Learny cannot be the reader for the books that most need cited teaching (diagrams, plates, UI screenshots). Staying on derived Markdown + owner-scoped GET + harden allowlist matches ADR-0002/0013 and avoids the EPUB-XSS class that bites iframe readers. Concrete shape: during `ingestion.run`, walk ebooklib image items (and Docling picture bytes); store under `sources/{user}/{source}/media/{hash}.{ext}` in MinIO; rewrite `![alt](../images/x.png)` to `![alt](/api/sources/{id}/media/{hash})`; Streamdown `allowedImagePrefixes: ['/api/sources/']` with `defaultOrigin` the app origin; GET is cookie-auth + owner 404. Re-encode to a cap (e.g. 1600px / 1.5MB) so a malicious EPUB cannot become a zip-bomb in the chapter. `paintHighlights` must skip `img` the way it already skips `[data-reader-scaffold]`.
- **Why-not:** Ingest gets heavier (bytes, re-encode, alt fallbacks, PDF figure quality). Malicious EPUBs could try huge images even with caps. SVG-from-EPUB is a script vehicle — rasterize or strip, do not serve raw SVG. A thin “show alt only” toggle is cheaper — and keeps Learny unusable for illustrated books.

### Cycle: Immersive `/read` chrome (long-form layout)

- **Why recommend:** Every serious reader hides utility chrome during the session (Reader long-form, Kindle/Books tap-to-reveal). Learny currently paints Home/Bookshelf/Review/Notes + email header *on top of* TOC + dock. This is the cheapest way to feel like a book without touching ingestion. `[` `]` matching Readwise is copyable and testable.
- **Why-not:** Route-level layout exceptions are fiddly (`(app)/layout.tsx` is global). Users may not discover TOC/dock if both start closed. Overlay-dock on small screens needs focus-trap work (WCAG 2.4.11). Doing this *before* figures still leaves textbooks broken.

### Cycle: Responsive web reader (touch + stacking)

- **Why recommend:** Public users will open Learny on a phone. RFC-004 forbade native apps, not a usable viewport. Matter/Kindle/Books *are* the bed/commute devices. A bottom-sheet dock + touch capture is the difference between “desktop study tool” and “place I read.”
- **Why-not:** Touch selection APIs are messy; five verbs will not fit a 320px popover without overflow. QA matrix explodes. A PWA/installable later can wait. Shipping “responsive” that still requires hover will fail in dogfood on a real phone.

### Cycle: Typography + a11y pack

- **Why recommend:** Table stakes vs Kindle `Aa` (OpenDyslexic, many sizes, sepia) and Reader (Atkinson, line width). Book `lang` is already in the corpus and unused on the article — a one-cycle win for Portuguese hyphenation and AT. WCAG 1.4.8 knobs (measure, leading already, fg/bg via Paper/dark) are the honest dyslexia/low-vision story, not a novelty font.
- **Why-not:** Extra self-hosted faces bloat the reader chunk (mitigate: `next/font` + `Aa`-gated load). OpenDyslexic-as-default would fight ADR-027’s scholarly identity and the Rello evidence. Do not stall public launch on a 14-step size slider.

### Cycle: Keyboard reading mode + lower-friction highlight

- **Why recommend:** Reader’s `H`/`G`/`[` `]` is the power-user reason people stay in a web reader. Learny already has a guarded shortcut hook and Explain/Ask verbs — they are just mouse-only. Pairing with optional auto-highlight (default off, already an RFC-004 exclusion-as-toggle) closes the Matter/Reader gap without new domain model.
- **Why-not:** Paragraph-granular keyboard highlight (Reader) fights Learny’s Markdown-verbatim capture (cross-element selections fail). Implementing a fake paragraph focus that does not match served Markdown will create ghost highlights. Customizable keymaps (Reader) is a trap for a small team; ship a `?` overlay of defaults only.

### Cycle: Intra-section resume

- **Why recommend:** Whispersync’s whole value is *exact* place. Section-level resume is a noticeable regression on long chapters and is the first thing a Kindle switcher will ding.
- **Why-not:** Offset-in-pixels breaks across font-size changes; a word-offset or `%` of section height is more stable but is new backend shape. Citation jumps and the Return chip already cover the *study* path. Do this after immersive chrome; wrong resume in a noisy layout is still wrong.

### Explicitly not a near cycle

- **Multi-color highlights.** Zotero needs them for literature review; Hypothesis still refuses them for a11y; Reader replaced them with tags; Matter chose one yellow on purpose. Learny’s notes/tags/cards are the semantic system. Colors later, private, never sole meaning.
- **Native iOS/Android readers.** RFC-004 out of scope; Whispersync-class multi-device is a later platform decision, not a reader-UX cycle.
- **Horizontal page-turn / two-column spreads.** Readwise documented why they hurt selection; RFC-004 locked scroll.
- **NotebookLM three-pane as default.** Chat-first kills long-form. Keep the book as the home column.
- **Uncited overlay chat (Kindle Ask This Book).** Learny’s dock + Show-in-book is already the better pattern; do not regress it.

## What “want to read here” would feel like (session test)

A stranger on a phone at 22:30: opens Home → Continue reading lands **inside the paragraph**, not the chapter heading; chrome is a thin progress + `Aa`; they highlight with a drag and keep going; a diagram of a lock protocol is actually there; they tap Ask on a sentence and the dock sheets up with a cited answer they can Show-in-book without losing the page. They put the phone down. Next morning on a laptop, `[` hides TOC, the dock is still that thread, Whispersync-class resume is exact. That session is currently impossible: images blocked, mouse-only capture, app chrome, section-granular resume, dock too wide for a phone.

If that session works, Kindle remains better at bookstore + e-ink, Apple Books at “it feels like a book,” Readwise at inbox-of-everything. Learny wins the **book you are trying to understand**, which is the product thesis. If that session fails, public launch will convert uploaders, not readers.

## Open issues / evidence gaps

- Kindle highlight-popover color UX: widely described, not re-verified here against a live `read.amazon.com` session.
- Matter Co-Reader mechanics: App Store + hands-on blogs; getmatter.com still thin.
- Exact Streamdown default harden config is in `node_modules` (indicator policy → `[Image blocked: alt]`); a future cycle should pin `allowedImagePrefixes` in *Learny* code, not rely on library defaults.
- Intra-section resume encoding (word index vs `%` of section vs CFI-like) needs a small spike before the cycle is specced; do not guess a CFI implementation.
- No Granola meeting context was available this pass (namespace unauthenticated).
