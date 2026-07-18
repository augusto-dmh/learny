# RQ-01 — Reading Surfaces: How the Best Reading Apps Structure the Reading Screen

- **Status:** Complete
- **Date:** 2026-07-18 (all sources accessed 2026-07-18)
- **Question:** How do the best reading apps structure the reading surface itself — and what should Learny's rebuilt Reader adopt?

## Method

Surveyed the reading screens of Readwise Reader, Kindle (app + Kindle for Web), Apple Books (iOS + Mac), LingQ, Matter, and Foliate (chosen open-source EPUB reader). For each: reading-pane layout (measure, margins, pagination vs scroll), user-exposed typography controls, chapter/TOC navigation, reading-position and progress presentation, annotation entry points, and theming. Primary sources (official docs and help centers) were fetched where available; paywalled or app-only UI details sourced from reviews are marked **(unverified)**. Typography-defaults findings draw on readability literature and the Literata specimen. Learny's current reader (`frontend/app/components/section-reader.tsx`) was read before writing implications.

## Per-Product Findings

### Readwise Reader — the desktop-web benchmark for Learny

- **Layout:** Continuous scroll by default; optional "vertical paged scroll" (tap page margins to page) and "horizontal pagination" (two side-by-side columns, tablets in landscape only). A **line width** control (web only) caps the measure — "the maximum width of the document content. Defaults to medium," adjustable via `Shift + ,` / `Shift + .` ([Appearance docs](https://docs.readwise.io/reader/docs/faqs/appearance), accessed 2026-07-18).
- **Typography controls:** Serif and sans typefaces including Atkinson Hyperlegible and OpenDyslexic; font size default **20px**, range 14–80px (`Shift + -` / `Shift + =`); line spacing default **1.4** (same docs).
- **Chrome behavior:** A dedicated "Long-form reading view" — **enabled by default for EPUBs** — hides the action-heavy bottom bar and elevates reading progress and appearance settings. All appearance settings live behind a single `Aa` icon.
- **Progress:** Reading progress surfaced in the long-form view chrome; position syncs across devices.
- **Annotation entry:** Select text → highlight; keyboard `H` highlights the entire focused paragraph, `N` highlights and opens a note, double-tap on mobile; `Shift + N` opens a document-level note. Keyboard highlighting is paragraph-granular by design ([Highlights, Tags, and Notes](https://docs.readwise.io/reader/docs/faqs/highlights-tags-notes), accessed 2026-07-18). Ghostreader (AI define/simplify/Q&A) hangs off the same selection/paragraph context — AI actions are an *inline reading mode*, not a separate page.
- **Theming:** Light, dark, and "auto" following the OS theme (`Cmd/Ctrl + Option + T`). No sepia documented.

### Kindle (app + Kindle for Web) — richest progress model, theme-as-preset

- **Layout:** Paginated by default; optional "Continuous Scrolling" toggle in the `Aa` → Layout menu on iOS/Android (KFX-format books only; not universal across builds — [Apple discussions](https://discussions.apple.com/thread/251718919), [MobileRead](https://www.mobileread.com/forums/showthread.php?t=335927), accessed 2026-07-18, secondary). Margins narrow/medium/wide; one or two columns ([Customize Kindle for Web](https://www.amazon.com/gp/help/customer/display.html?nodeId=TT200NNkr2BE4Jnsy9), [Customize Your Kindle E-Reader Text Display](https://www.amazon.com/gp/help/customer/display.html?nodeId=T5Y94BzSCGwm0vd75W), accessed 2026-07-18).
- **Typography controls:** Fonts include **Bookerly** (Amazon's commissioned long-form serif, the default), Amazon Ember, and OpenDyslexic; 14 font sizes on web; line, paragraph, word, and character spacing controls; bold-text toggle.
- **Themes as presets:** A "theme" saves a *bundle* of settings (size, font, boldness, margins, spacing). Presets: Compact, Standard, Large, Low Vision; users can save named custom themes, and Kindle for Web syncs them across browsers.
- **Progress — the standout:** Reading Progress setting chooses among **time left in chapter, page in book, time left in book**; tapping the lower-left corner cycles the metric in place. "Time left in chapter" is the motivational unit for session pacing.
- **Annotation entry:** Long-press + drag selection → popover with highlight colors, note, and share (widely documented app behavior; specifics via secondary sources, unverified detail).
- **Theming:** Page color white, **sepia**, light green, black.

### Apple Books — themes with personality, page-turn choice

- **Layout:** Page-turn styles **Curl, Fast Fade, or Scroll** (vertical scrolling is a first-class page style); on Mac, window width determines one- vs two-page spread; "Allow Multiple Columns" toggle; justification and **auto-hyphenation** toggles ([Change a book's appearance on Mac](https://support.apple.com/guide/books/change-a-books-appearance-ibks8923126d/mac), [Read books on iPhone](https://support.apple.com/guide/iphone/iphc1af7c57/ios), accessed 2026-07-18).
- **Typography controls:** Font size A/A buttons, font choice, bold text, line-spacing slider.
- **Theming:** Six named themes on iOS — **Original, Quiet, Paper, Bold, Calm, Focus** — each a curated font+spacing+surface personality, individually customizable; background is a separate axis: **Light, Dark, or Automatic**. Theme (personality) and background (light/dark) being orthogonal is a distinctive, copyable idea.
- **Annotation entry:** Touch-and-hold a word, adjust grab points, tap Highlight; tapping highlighted text again offers color change/underline/Remove; Add Note from the same menu. All highlights and notes are listed under a "Bookmarks & Highlights" panel per book ([Annotate books on iPhone](https://support.apple.com/guide/iphone/annotate-books-iph17bf340c1/ios), accessed 2026-07-18).
- **Chrome:** Menu button position configurable (left/right); chrome hidden until tap.

### LingQ — progress as a game mechanic, paging as commitment

- **Layout:** Reader 4.0 deliberately moved from a long scroll to a **paged interface** because "it became difficult to track your location especially if you did the lesson in stages" — pages segment the text into completable units ([Announcing the New LingQ Reader](https://medium.com/the-linguist-on-language/announcing-the-new-lingq-reader-b42468a48726), accessed 2026-07-18).
- **Progress:** A progress bar doubles as navigation (jump back to completed pages). Turning a page is a *commitment*: remaining blue (unknown) words on the page are marked known. Streak indicators sit alongside the reader.
- **Interaction model:** Words carry state rendered inline (blue = unknown, yellow = learning, white = known, orange = phrases); clicking a word opens its definition pane. **Sentence Mode** drills into one sentence at a time with audio and translation ([LingQ forum: Sentence Mode](https://forum.lingq.com/t/sentence-mode-how-why-to-use-it/8735), accessed 2026-07-18).
- **Typography/theming:** Appearance controls (font size, dark mode) exist in-app but are thin in primary documentation (unverified detail).
- **Relevance:** LingQ is the strongest example of a reading surface where *study state is painted onto the text itself* — the direct analogue of Learny painting highlights, note-anchors, and card-anchors onto corpus blocks.

### Matter — frictionless capture, restrained palette

- **Typography controls:** Eight font sizes, six fonts, three line-spacing options, direct brightness access; four themes for each of light and dark system modes, including a serif-forward "Paper" theme ([MacStories review](https://www.macstories.net/reviews/matter-a-fresh-take-on-read-later-apps/), accessed 2026-07-18, secondary; [getmatter.com](https://www.getmatter.com/), accessed 2026-07-18).
- **Annotation entry:** The reviewed differentiator: "no multi-step highlighting flows that take you out of reading flow — you simply long press and drag." Single **neutral yellow** highlight color chosen explicitly so marks don't distract during reading (MacStories, secondary).
- **Audio:** TTS with word-synced text highlighting; auto language detection across 15 languages.
- **Progress:** Standard percent-based article progress (unverified detail).

### Foliate — the open-source floor, and a kindred storage model

- **Layout:** Paginated **or** scrolled mode (`Ctrl + M` toggles); single/double page adapts to window size ([foliate homepage](https://johnfactotum.github.io/foliate/), [OMG! Ubuntu on the GTK4 port](https://www.omgubuntu.co.uk/2023/11/foliate-ebook-app-major-update), accessed 2026-07-18).
- **Typography controls:** Font, spacing, margins, zoom; **auto-hyphenation**; handles RTL and vertical writing.
- **Navigation:** One sidebar hosting TOC, bookmarks, annotations, and find-in-book; a reading **progress slider plus navigation history** (back-forward after jumping via TOC/search — directly relevant to citation jumps).
- **Theming:** Light, sepia, dark, invert, plus custom themes.
- **Annotation storage:** Bookmarks/annotations in **plain JSON, one file per book**, "so you can export or sync them easily" — the FOSS analogue of Learny's corpus-anchored, exportable notes.

## Cross-Product Patterns That Matter

1. **One `Aa` affordance, disappearing chrome.** Every product funnels all appearance settings through a single icon, and every book-length reader hides its action chrome during reading (Reader's long-form view, Kindle/Books tap-to-reveal). The reading pane is visually silent; tools appear on demand.
2. **Scroll is the desktop-web default; pagination is an option, not the base.** Reader (web) scrolls by default; Kindle's continuous-scroll is opt-in and mobile; Apple Books offers Scroll as a page style; Foliate toggles freely. Only LingQ mandates pages — and for a study-mechanic reason (completable units), not a rendering one.
3. **Measure is controlled.** Reader exposes line width directly; Kindle exposes margins + columns; readability literature converges on **50–75 characters per line (~66 ideal), line-height ~1.5, WCAG 1.4.8 caps at 80** ([Butterick](https://practicaltypography.com/line-length.html), [UXPin](https://www.uxpin.com/studio/blog/optimal-line-length-for-readability/), [Wikipedia: Line length](https://en.wikipedia.org/wiki/Line_length), accessed 2026-07-18).
4. **Book defaults are serif, ~19–20px, spacing ≥1.4.** Kindle defaults to Bookerly (a commissioned screen serif); Google Play Books commissioned Literata; Reader defaults to 20px/1.4. Sans stays in the chrome.
5. **Progress is multi-granular and glanceable:** percent/position in book, position in chapter, and *time left in chapter* (Kindle's cycle-on-tap). LingQ adds progress-as-mechanic and streaks. Position always persists and resumes.
6. **Highlighting starts from selection and completes in one gesture.** Select → small popover (never a modal, never a page change). Matter's single neutral color and Reader's `H`/`N` paragraph shortcuts mark the two poles: minimal friction, keyboard acceleration. Notes attach from the same popover. A per-book list view of all highlights/notes (Apple Books' Bookmarks & Highlights) is table stakes.
7. **Theming = light/sepia/dark (+auto).** Sepia/paper warm surfaces appear in Kindle, Apple Books, Matter, Foliate. Apple Books' separation of *theme personality* (fonts+spacing bundle) from *light-dark axis* is the cleanest model.
8. **TOC lives in a togglable sidebar with position context** (Foliate's TOC+progress slider+navigation history; Reader's document nav). After a jump (citation, search), a "back to where I was" affordance is expected.

## Typography Defaults for Long-Session Reading (incl. Portuguese)

- **Face:** **Literata** is the strongest candidate for Learny's serif reading face: commissioned by Google Play Books specifically for long-form e-reading on varied screens, SIL OFL (free to self-host — fits Learny's no-external-hosts constraint), variable (two files cover all weights/opticals), with **Pan-European Latin Extended coverage** — all Portuguese diacritics (ã, õ, ç, á, à, â, ê, ô, í, ó, ú) fully supported ([Google Fonts specimen](https://fonts.google.com/specimen/Literata), [googlefonts/literata](https://github.com/googlefonts/literata), [TypeTogether Literata 3](https://www.type-together.com/literata-3), accessed 2026-07-18). Bookerly is proprietary; Atkinson Hyperlegible/OpenDyslexic are accessibility alternates, not defaults.
- **Size/leading:** 19–20px body, line-height 1.55–1.6 for a serif at reading distance (Reader ships 20px/1.4; literature says ~1.5).
- **Measure:** ~65–70ch → roughly a 34–38rem column at 19px Literata. Learny's current `max-w-2xl` (42rem) is close but paired with 14px text, which stretches lines past 90 characters.
- **Portuguese specifics:** Portuguese words run long; if text is justified, hyphenation is mandatory to avoid rivers. Set `lang="pt"` (or per-book language) on the reading container and use `hyphens: auto` — browser hyphenation dictionaries are language-attribute-driven. Safest default: **ragged-right with hyphenation off**, offering justified+hyphenated as a setting (Apple Books exposes exactly these two toggles).

## Current State of Learny's Reader (`frontend/app/components/section-reader.tsx`)

- Renders **one section at a time** from `?anchor=`; no next/previous flow, no chapter-level continuity — reading a book means clicking every section in the sidebar tree.
- Prose is `prose prose-sm` (**14px**) in a `max-w-2xl` column: too small for book sessions and an overlong measure at that size; no typography controls, no reading themes (only app light/dark), sans-serif only.
- No reading-position persistence, no progress display of any kind, no time-left, no per-chapter state.
- Load path is a client-side waterfall (auth fetch → section fetch) with a bare "Loading…" string.
- What already works and must be preserved: citation deep-link lands on the section with scroll-into-view + transient heading highlight; mouseup selection → `CapturePopover` with Highlight / Highlight+note resolving against served Markdown (not DOM), with stale-capture handling. This is exactly the industry-standard entry point — it needs extension (Ask/card actions), not replacement.

## Implications for Learny

1. **The unit of reading must become the chapter, not the section.** Every surveyed reader presents a continuous text flow; only Learny makes the user manually click through structural fragments. Learny's structured corpus is an advantage here: render a chapter as one scrollable flow of its sections/blocks, each block carrying its stable anchor as a DOM id, so citations deep-link to a position *within* the flow instead of an isolated fragment. This single change does more for "reading-first" than any styling work.
2. **Scroll, don't paginate.** Learny is desktop-web, single-user. The desktop-web precedents (Reader, Kindle for Web, Foliate) all treat scroll as the base. Pagination adds engineering cost (column layout, reflow on resize) for no persona benefit. LingQ's paged-commitment mechanic is interesting but belongs to Review/quizzes, not the reader.
3. **The bookish identity is mostly typography defaults, not controls.** Ship Literata at ~19px/1.6 on a ~65ch warm-surface column and Learny immediately reads as a book product. User controls can be minimal (size, spacing, theme) — far fewer than Kindle's — because there is one known user.
4. **Progress is the bridge to the Home surface and the 14-day gate.** Per-book percent feeds Home's resume card; in-reader per-chapter position plus "min left in chapter" (word count ÷ ~200 wpm, tunable) gives session pacing, the metric Kindle treats as primary. Reading position + per-book progress is exactly the "student-workflow-shaped state" the backend boundary permits.
5. **The capture popover is the hub for all inline modes.** The locked IA puts Ask, Teach, note capture, and card creation *inside* the reader. Reader/Ghostreader and Matter show the pattern: every AI/study action starts from a selection or paragraph context in a small popover. Learny's existing popover should grow "Ask about this" and "Make a card" beside Highlight / Highlight+note — one entry point, four modes.
6. **After a citation jump, provide a way back.** Foliate's navigation history and Reader's document nav set the expectation; a citation that teleports the reader mid-chapter needs a "return to previous position" affordance or reading flow breaks.
7. **Theme model:** adopt Apple Books' two-axis scheme scoped to the reader surface: light / sepia / dark backgrounds (warm, not pure white/black) on top of the existing shadcn tokens — an evolution, not a rip-out, matching the locked visual direction.

## Recommendations

1. **Rebuild the reader around a chapter-flow view:** fetch and render all sections of the current chapter as one continuous article; each section heading and block keeps its stable anchor as `id`; `?anchor=` scrolls within the flow (preserving the existing transient highlight); sticky prev/next-chapter controls at the flow boundaries.
2. **Set reading typography defaults:** self-hosted Literata variable (SIL OFL) for body/headings of book text; Geist Sans stays for chrome; 19px body (user-adjustable ~16–24px in 5 steps), line-height 1.6, measure `max-width: 65ch`, ragged-right, `lang` attribute set from book language with `hyphens: auto` available behind the justify setting.
3. **Add a single `Aa` popover in the reader chrome:** font size stepper, line-spacing (3 steps), theme (light / sepia / dark / auto). Persist choices (localStorage is sufficient for single-user; backend optional). No font-family picker in v1.
4. **Persist reading position and progress server-side:** on scroll-idle, record deepest-visible block anchor per book; expose per-book percent (blocks read / total) and per-chapter position; render "~N min left in chapter" from corpus word counts. Feed Home's "resume reading" card from the same state.
5. **Extend the capture popover to the four inline modes:** Highlight, Highlight + note (existing), **Ask about this passage** (pre-seeds Ask with the anchor + quote), **Create card** (pre-seeds quiz-item creation with the anchored quote). Keep a single neutral highlight color (Matter's restraint); skip multi-color in v1.
6. **Render existing highlights inline** in the chapter flow (anchored spans with the neutral highlight tint), with a per-book "Highlights & notes" panel (Apple Books' Bookmarks & Highlights pattern) listing them with jump-to-location.
7. **Make reader chrome recede:** minimal top bar (book title, chapter breadcrumb, progress, `Aa`, TOC toggle) that hides on scroll-down and returns on scroll-up — Reader's long-form-view behavior.
8. **Keep the TOC sidebar but add position context:** current-chapter/section indicator, per-chapter read-state ticks, and a back-to-previous-position button after any citation/TOC jump (Foliate's navigation history).
9. **Fix the load path:** prefetch or server-render chapter content to eliminate the auth→section client waterfall; replace "Loading…" with a text-shaped skeleton so the reading surface never flashes empty.
10. **Defer:** pagination modes, two-column layouts, per-word study states (LingQ-style), TTS, and font pickers — none are needed for the 14-day daily-study gate, and each is separable later work.

## Open Issues

- LingQ's and Matter's exact appearance controls (dark mode specifics, font lists) come from thin or secondary sources (unverified); neither gap affects the recommendations.
- Kindle's continuous-scrolling availability is inconsistent across app builds and formats (secondary sources); cited only as evidence that scroll is optional, not the base, on Kindle.
- Kindle highlight-popover details (colors, note flow) are widely documented behavior but were not verified against a primary Amazon help page in this pass (unverified detail).
- "~200 wpm" for time-left estimates is a placeholder; with a single known user, the constant can be calibrated from actual reading-position telemetry after a week of use.
