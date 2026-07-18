# RQ-05 — Visual Identity: Four Concrete Directions for a Reading-First Learny

- **Status:** Complete
- **Date:** 2026-07-18 (all sources accessed 2026-07-18)
- **Question:** What concrete visual identity should Learny adopt — proposed as 3-4 distinct, fully-specified directions the author can choose between?

## Method

Audited the current frontend base first: `frontend/app/globals.css` (stock shadcn neutral theme — every color token is zero-chroma `oklch`, i.e. pure grayscale; Tailwind v4 `@theme inline` token bridge; `--radius: 0.625rem`), `frontend/app/layout.tsx` (Geist Sans bound to `--font-sans` via `next/font`-style variable; next-themes class-based dark mode), and two representative components (`citations.tsx` — citation chips + popover styled entirely from `secondary`/`muted`/`primary` tokens; `section-reader.tsx` — reader prose currently rendered by the same Streamdown `MessageResponse` used for chat, in the default sans).

Then surveyed reading-centric products and type sources on the current web: iA Writer's typography essays and font repo ([ia.net "A Typographic Christmas"](https://ia.net/topics/a-typographic-christmas), [ia.net "In Search of the Perfect Writing Font"](https://ia.net/topics/in-search-of-the-perfect-writing-font), [github.com/iaolo/iA-Fonts](https://github.com/iaolo/iA-Fonts)); Readwise Reader's appearance docs and design writeups ([docs.readwise.io appearance FAQ](https://docs.readwise.io/reader/docs/faqs/appearance), [blakecrosley.com Reader design guide](https://blakecrosley.com/guides/design/readwise-reader) — secondary); Standard Ebooks' typography manual and site typography ([standardebooks.org/manual — Typography section](https://standardebooks.org/manual/1.8.7), site heading face League Spartan confirmed via a mirror of their web fonts — secondary, [github.com/PyroLagus/standardebooks-web](https://github.com/PyroLagus/standardebooks-web/blob/master/www/fonts/league-spartan-bold.woff2)); e-reader serif provenance ([TypeTogether on Literata](https://www.type-together.com/literata-book), [Fast Company on Literata's design goals](https://www.fastcompany.com/3046511/how-google-made-an-e-book-font-designed-for-any-screen), [Google Fonts Literata specimen](https://fonts.google.com/specimen/Literata)); and editorial-web inspiration ([Awwwards typography collection](https://www.awwwards.com/websites/typography/), [Creative Boom editorial typefaces](https://www.creativeboom.com/resources/8-remarkable-typefaces-that-will-instantly-elevate-your-editorial-designs/)).

All four directions were then designed inside the locked envelope (bookish-scholarly, typography-led, serif reading face + sans chrome, evolved from the shadcn base) and checked against the hard guard: no cream-`#F4F1EA`/Georgia-Playfair/terracotta default, no purple-gradient SaaS, at least one cooler/inkier direction.

## Findings — what the exemplars actually do

### The current base is a blank slate, which is the real problem

Learny today is the un-themed shadcn neutral: grayscale-only tokens, Geist everywhere (including book prose), default radius, no serif anywhere, no highlight color vocabulary. Two consequences matter for RQ-05:

1. **The reader has no typographic distinction from the chrome.** Book text renders in the same Geist Sans as buttons and nav (`section-reader.tsx` reuses the chat `MessageResponse` renderer). A reading-first app whose reading surface looks like its settings page has no identity, no matter what accent color is applied.
2. **The token system makes retheming cheap.** Every surveyed component styles itself exclusively through semantic tokens (`bg-secondary`, `text-muted-foreground`, `border-muted`). A direction is therefore implementable almost entirely as a `:root`/`.dark` variable swap plus one new `--font-serif` binding and a reader prose class — the "evolved, not rip-out" constraint is structurally easy to honor.

### What reading-first products converge on

- **A screen-tuned book serif for content, a quiet sans for chrome.** Google commissioned Literata specifically because a book app needed "an outstanding reading experience on a whole range of devices" and a recognizable identity distinct from other e-readers ([TypeTogether](https://www.type-together.com/literata-book), [Fast Company](https://www.fastcompany.com/3046511/how-google-made-an-e-book-font-designed-for-any-screen)). Standard Ebooks pairs classic book-serif text faces with a geometric sans (League Spartan) for site chrome — serif = the book's voice, sans = the publisher's voice. This two-voice split is the core move Learny is missing.
- **Reading comfort is measurable, not vibes.** Readwise Reader defaults to 20px body text, 1.4 line spacing, adjustable measure ([Readwise appearance docs](https://docs.readwise.io/reader/docs/faqs/appearance)). E-book typography convention (Literata's brief, Standard Ebooks' manual) points to ~18-20px serif at a 60-70ch measure with 1.5-1.6 leading for book prose on desktop.
- **Highlights read as physical markers, not UI states.** Reader's highlight palette — soft yellow `#FBDA83`, coral `#E4938E`, blue `#8DBBFF` — is deliberately "actual highlighter markers on paper, not digital overlays" ([blakecrosley.com](https://blakecrosley.com/guides/design/readwise-reader), secondary/unverified hexes). Implication: highlight colors should be a *separate warm-tinted token set*, not reuses of `--accent`, and should survive palette-direction changes.
- **Micro-typography is identity.** Standard Ebooks' manual treats curly quotes, real ellipses, en/em dash discipline, and small-caps usage as the product ([SE manual §8 Typography](https://standardebooks.org/manual/1.0.0/8-typography)). For a corpus-owning app, getting `“ ” ‘ ’ — …` and hanging punctuation right in the reader is cheap and signals "book people made this."
- **A single, ownable signature beats broad decoration.** iA Writer's identity is essentially one idea — writing-tool typography (duospace fonts derived from IBM Plex, free to self-host, attribution requested; license file in repo, Plex is SIL OFL) plus a single blue accent ([iA-Fonts repo](https://github.com/iaolo/iA-Fonts), [ia.net](https://ia.net/topics/in-search-of-the-perfect-writing-font)). Each direction below therefore carries exactly one signature element.

### Typeface availability (all self-hostable; Google Fonts unless noted)

| Face | Role | Source/license | Notes |
|---|---|---|---|
| Literata | reading serif | Google Fonts, OFL | Commissioned for Google Play Books; variable, optical-size + weight axes (axis detail per TypeTogether/GF specimen, unverified in detail); broad Latin incl. Portuguese |
| Source Serif 4 | reading serif | Google Fonts, OFL | Adobe's screen serif; variable opsz + wght; cooler, more rational than Literata |
| Alegreya + Alegreya Sans | reading serif + matched sans superfamily | Google Fonts, OFL | Calligraphic book face designed in Latin America (Juan Pablo del Peral); strong for Portuguese-language texture |
| Newsreader | reading serif | Google Fonts, OFL | Production Type; designed for on-screen editorial reading, opsz axis |
| iA Writer Quattro | utility/metadata face | GitHub (iaolo/iA-Fonts), free, IBM Plex derivative (Plex is OFL; repo asks to read license file + credit iA) | Duospace "working text" voice; not on Google Fonts — self-host woff2 |
| Geist Sans | UI sans (incumbent) | Vercel, OFL | Already wired via `--font-sans`; keeping it makes any direction "evolved, not rip-out" |

`next/font/google` self-hosts Google Fonts at build time (no runtime Google requests) — consistent with Learny's self-hosted stance.

## The Four Directions

All directions share these invariants (they are the reading-first floor, not differentiators): serif book prose at 18-20px / 60-70ch / 1.55-1.65 leading in the reader; sans chrome; highlight colors as dedicated `--highlight-*` tokens rendered as background washes on prose spans; citations always resolving to the reader (existing chip → popover → "Open in book" flow restyled, never replaced by raw snippets); light + dark fully specified; WCAG-AA ink-on-background contrast in both modes.

---

### Direction A — "Marginalia" (warm scholarly, library green)

**Mood:** a well-lit university library carrel — aged paper, dark warm ink, bottle-green accents; the warmest direction, but built from Literata + green so it cannot be mistaken for the cream/Playfair/terracotta AI default.

**Type:** Literata (reading serif; variable opsz so headings/captions get proper optical sizes) + Geist Sans (UI chrome, unchanged). Section headings in the reader: Literata SemiBold; running heads and breadcrumbs in Geist small-caps-styled (letterspaced uppercase, 11px).

**Palette:**

| Token (semantic) | Light | Dark ("reading lamp") |
|---|---|---|
| background | `#F4EFE5` | `#211C15` |
| surface / card | `#FCF9F2` | `#2B251C` |
| ink (foreground) | `#27211A` | `#EAE2D2` |
| muted ink | `#6F6455` | `#9C9180` |
| border | `#E2DACA` | `#3B342A` |
| accent (primary) | `#2E6B4F` library green | `#85BE9F` |
| accent foreground | `#F7F4EC` | `#1B241F` |

**Highlights:** yellow `#F2DF9C` / `#57491D` (dark), green `#CBE0BE` / `#33482C`, blue `#C4D8EC` / `#2A3D51`, rose `#EEC9C0` / `#4E332E`.

**Annotation & citation treatment:** a highlight is a soft marker wash with a 2px bottom border in a deeper cut of the same hue (pen pressure at the baseline). A note marker is a small green fleuron (❧) in the reader margin, aligned to the anchored line; hover draws a hairline from fleuron to passage. A citation chip is a green-tinted pill with an old-style Literata numeral; its popover is styled as an index card — `surface` background, breadcrumb in letterspaced caps, snippet set in Literata italic, "Open in book" as a green small-caps link.

**Signature element:** the running head — a persistent, hairline-ruled strip above the reader showing `Book · Chapter › Section` in letterspaced caps with a thin green reading-progress tick underneath, echoing a printed book's header + drop folio.

**shadcn token overrides:** all color tokens in `:root`/`.dark` (`--background --foreground --card --card-foreground --popover* --primary* --secondary* --muted* --accent* --border --input --ring --sidebar-*`), `--radius: 0.5rem`; add `--font-serif` (layout.tsx + `@theme inline`), new `--highlight-{yellow,green,blue,rose}`; new `.prose-reading` class; running-head component. No UI font change.

---

### Direction B — "Iron Gall" (cool, inky, scholarly-press) — satisfies the cooler/inkier guard

**Mood:** iron-gall ink on cool rag paper — the blue-black of a fountain pen and the hairline rules of a ledger; a university-press book, not a lifestyle app. Deliberately the anti-cream direction.

**Type:** Source Serif 4 (reading serif; rational, cool, superb at text opsz) + Geist Sans (UI chrome, unchanged; its coolness finally becomes an asset). Alternate reading serif if a more classical scholarly voice is wanted: STIX Two Text.

**Palette:**

| Token (semantic) | Light | Dark |
|---|---|---|
| background | `#F6F7F6` | `#0F161B` |
| surface / card | `#FFFFFF` | `#172128` |
| ink (foreground) | `#1B2733` iron-gall blue-black | `#D9E2E8` |
| muted ink | `#5D6B76` | `#7F93A0` |
| border | `#DDE2E4` | `#263340` |
| accent (primary) | `#22557A` Prussian blue | `#6FA9CC` |
| accent foreground | `#F4F8FA` | `#0E1A22` |

**Highlights** (kept deliberately warm against the cool field so they read as marker, per the Readwise finding): yellow `#EFE3A0` / `#4E4620` (dark), cyan `#C2DEE8` / `#1F3F4A`, violet `#D6D0EC` / `#37315D`, green `#C9DFCF` / `#26412F`.

**Annotation & citation treatment:** a highlight is a flat tint capped by a 1px ink underline — restrained, print-like. A note marker is a pilcrow (¶) in the gutter in Prussian blue, visible on hover of any annotated paragraph, persistent where a note exists. A citation is a bracketed numeral `[1]` in Prussian blue; the chip is a sharp-cornered outline pill (no fill), and the popover is a hairline-bordered card with the snippet set as a real block quotation (indented Source Serif italic with a 2px Prussian left rule) — the citation apparatus of a scholarly edition.

**Signature element:** the ink line — one continuous 1.5px blue-black horizontal rule system: under the app header, under reader section headings, and as the reading-progress indicator (the rule "fills" with Prussian blue as you move through a chapter). Everything ruled, nothing boxed.

**shadcn token overrides:** same full color-token sweep as A; `--radius: 0.25rem` (near-square, ledger feel); `--font-serif` binding; `--highlight-*` tokens; hairline utilities. No UI font change — lowest-effort direction alongside D.

---

### Direction C — "Tipografia" (Iberian humanist, oxblood & limestone)

**Mood:** a Lisbon or São Paulo antiquarian press — limestone surfaces, oxblood leather, gilded fleurons; honors the persona's Portuguese-language reading with a Latin-American-designed superfamily. The most characterful, highest-risk direction.

**Type:** Alegreya (reading serif — calligraphic, energetic, designed for literature) + Alegreya Sans (UI chrome — replaces Geist; the only direction that swaps the UI face, keeping one designer's voice across book and chrome). Alegreya SC (small caps) for chip numerals and running heads.

**Palette:**

| Token (semantic) | Light | Dark |
|---|---|---|
| background | `#F1EDE6` limestone | `#231E1B` |
| surface / card | `#FAF7F1` | `#2D2723` |
| ink (foreground) | `#2A231E` | `#EEE7DD` |
| muted ink | `#7C7166` | `#A39584` |
| border | `#DFD8CC` | `#453D36` |
| accent (primary) | `#802F2F` oxblood | `#B96A6A` |
| secondary accent (ornament only) | `#A8823C` old gold | `#CBA85E` |

**Highlights:** gold `#E9D8A4` / `#55471F` (dark), olive `#D5DBAE` / `#454A24`, rose `#EBC7C1` / `#4C3230`, blue `#C6D6E4` / `#2C3E4E`.

**Annotation & citation treatment:** a highlight is a warm wash with rounded end-caps (border-radius on first/last span fragment) so it reads as a physical marker stroke. A note marker is a manicule (☞) in oxblood in the margin — the oldest annotation glyph there is. A citation chip is an oxblood-outlined pill with an Alegreya SC numeral; the popover snippet opens with the source's chapter ornament and sets the breadcrumb in gold small caps; "Open in book" is an oxblood link with a gold hover underline.

**Signature element:** chapter typography — a two-line Alegreya drop cap on the first paragraph of every chapter/section opened in the reader, and a centered fleuron (❦) divider between major sections. No other product in the RQ-01 survey has real book-opening typography; this is instantly ownable.

**shadcn token overrides:** full color-token sweep; `--radius: 0.375rem`; **`--font-sans` rebinding in `layout.tsx`** (Alegreya Sans via `next/font/google`, replacing Geist) plus `--font-serif`; `--highlight-*`; drop-cap and ornament CSS (`::first-letter` styling scoped to chapter-opening prose). Highest effort: UI font swap forces a visual QA pass over every screen (sans metrics differ from Geist), and drop caps need edge-case handling (blockquote-first sections, RTL-safe none needed, poetry).

---

### Direction D — "Typescript" (studio minimal, working-notes graphite + azure)

**Mood:** iA Writer's discipline applied to studying — near-monochrome graphite, one azure accent, and a duospace "typescript" voice for everything the *student* produces (notes, anchors, card metadata); the book stays a book, your work-in-progress looks like work in progress ([iA's stated rationale for non-proportional writing faces](https://ia.net/topics/in-search-of-the-perfect-writing-font)). Second cool direction; the most restrained.

**Type:** Newsreader (reading serif — on-screen editorial face with opsz axis) + Geist Sans (UI chrome, unchanged) + iA Writer Quattro as a third *utility* face for student-generated metadata only: anchor labels, section-path breadcrumbs, FSRS due counts, note timestamps, card fronts in edit mode (self-hosted woff2 from the iA repo; free, credit iA, license file in repo — Plex derivative, Plex is OFL).

**Palette:**

| Token (semantic) | Light | Dark |
|---|---|---|
| background | `#FAFAF9` | `#141414` |
| surface / card | `#FFFFFF` | `#1D1D1D` |
| ink (foreground) | `#191919` | `#ECECEA` |
| muted ink | `#6E6E6A` | `#909089` |
| border | `#E5E5E2` | `#2C2C2A` |
| accent (primary) | `#1170CE` azure (iA-caret blue) | `#52A8FF` |

**Highlights:** yellow `#FBE27B` / `#574E1C` (dark), blue `#BED9F8` / `#1F3A57`, pink `#F6CCDB` / `#4E2B3B` — the only strong color on the page, exactly like markers on typescript.

**Annotation & citation treatment:** a highlight is a flat, squared marker wash (no border, no radius). A note marker is a Quattro-set tag in the margin — `n.12` — azure on hover; clicking opens the note inline. A citation is a Quattro-set `[3]` chip, graphite at rest, azure on hover/focus; the popover is a plain white/graphite card whose snippet is set in Newsreader with the breadcrumb in Quattro — the visual seam between "the book's voice" (serif) and "the apparatus" (duospace) *is* the citation treatment.

**Signature element:** the two-voice page — serif for everything from the book, duospace for everything from the student/AI apparatus, azure caret motif on streaming Ask/Teach answers (a blinking block caret at the stream head, iA-style). The identity is typographic contrast, not color.

**shadcn token overrides:** smallest sweep — the base is already neutral, so only `--primary`/`--ring`/`--accent` family + slight background/border warm-graphite shifts; keep `--radius`; add `--font-serif` and `--font-mono`-style `--font-utility` binding (self-hosted Quattro `@font-face`); `--highlight-*`. Lowest color effort, but touches more components (every metadata surface opts into the utility face).

---

## Comparison

| | A — Marginalia | B — Iron Gall | C — Tipografia | D — Typescript |
|---|---|---|---|---|
| Temperature | warm | **cool/inky** | warm | **cool/neutral** |
| Reading serif | Literata | Source Serif 4 | Alegreya | Newsreader |
| UI sans | Geist (kept) | Geist (kept) | Alegreya Sans (swap) | Geist (kept) + Quattro utility |
| Accent | library green `#2E6B4F` | Prussian blue `#22557A` | oxblood `#802F2F` + gold | azure `#1170CE` |
| Signature | running head + progress tick | the ink-line rule system | drop caps + fleurons | two-voice type (serif vs duospace) + caret |
| Radius | 0.5rem | 0.25rem | 0.375rem | keep 0.625rem |
| Effort | medium (tokens + reader + running head) | medium-low (tokens + reader + rules) | high (UI font swap + drop-cap edge cases) | medium (small token delta, many metadata touchpoints) |
| Risk of reading "AI-default" | moderate (warm paper adjacency — mitigated by green + Literata) | low | low (but risks "themed"/costume if ornaments overused) | low (but risks anonymous minimal if signature under-executed) |
| Dark-mode strength | good (lamp-warm) | **excellent** (native to the ink metaphor) | good | excellent |
| Portuguese-corpus resonance | neutral | neutral | **strong** | neutral |

## Implications for Learny

1. **The serif is the identity decision, the palette is secondary.** The single highest-leverage change in any direction is a screen-tuned book serif on the reader (and inside citation popovers), because today book prose is indistinguishable from chrome. This should land in the first styling PR regardless of which direction wins.
2. **Highlight colors must be direction-independent tokens.** ADR-0026's highlight anchoring will put colored washes into the reader; making `--highlight-*` first-class tokens now means annotation data never encodes a theme, and warm marker hues can ride on a cool palette (the Readwise lesson).
3. **The token audit shows the swap is cheap** — every surveyed component styles via semantic tokens, so A/B/D are ~a `globals.css` rewrite + one `layout.tsx` font binding + a reader prose class + one signature component. Only C has a genuinely larger blast radius (UI font metrics change everywhere).
4. **Citations already resolve to the reader (locked); each direction only restyles the chip/popover** — the `citations.tsx` popover is the one component every direction touches, so it should be the shared test bed when prototyping directions.
5. **Micro-typography is a free differentiator** for a corpus-owning app: enforce curly quotes/em-dash/ellipsis discipline in corpus-derived Markdown rendering (Standard Ebooks' manual as the reference), whatever direction is chosen.
6. **Self-hosting constraint is satisfied by all directions:** every face is OFL/free and served via `next/font/google` build-time self-hosting or vendored woff2 (Quattro) — no runtime third-party font requests.

## Recommendations

1. **Adopt Direction B — "Iron Gall" — as the primary identity.** Reasoning: (a) it is the direction furthest from the AI-default cream-and-terracotta cluster while staying fully inside the bookish-scholarly envelope — scholarly-press, not scrapbook; (b) it keeps Geist, giving the smallest implementation delta of the two strongest candidates ("evolved, not rip-out" honored literally); (c) its dark mode is the strongest of the four, and a daily-study app used at night lives in dark mode (the 14-day gate is won in evening sessions); (d) Source Serif 4's optical-size axis gives genuinely book-grade text rendering with zero licensing friction; (e) the ink-line signature doubles as the reading-progress affordance the Home/Reader IA already needs, so the signature element is functional, not decorative.
2. **Steal one element each from A and D into B:** keep the warm marker highlight set (already specified in B, per the Readwise "markers on paper" finding) and adopt D's streaming caret for Ask/Teach answers — a one-component flourish that makes the AI surface feel native to the identity.
3. **If the author wants more warmth or Portuguese resonance than B offers, choose A (Marginalia) as the runner-up** — it is the best warm direction that survives the AI-default guard — and treat C's drop caps as a later, optional chapter-opening enhancement rather than a full identity (C's UI font swap is the highest cost for the most taste-dependent payoff).
4. **Sequence the implementation as three PRs:** (1) tokens + fonts (`globals.css` rewrite, `--font-serif` binding, `--highlight-*`, `.prose-reading` on the section reader and citation popovers); (2) the signature system (ink-line rules + running head/progress); (3) annotation/citation restyle (chip, popover, margin markers) landing with the highlight-anchoring UI. Each PR is independently shippable and reversible.
5. **Prototype gate before committing:** render one real Portuguese-language chapter and one citation popover in B and A side by side (a single throwaway route with both token sets) and let the author pick against real corpus text — book serifs behave differently under Portuguese diacritics and long paragraphs, and the choice should be made on the actual corpus, not on lorem ipsum.
6. **Codify the chosen direction as a short ADR** (palette table, type roles, token names, signature rules) so future UI work — and any AI-generated components — inherit the identity instead of regressing to shadcn neutral.

## Open Issues

- Readwise Reader highlight hex values come from a secondary design writeup ([blakecrosley.com](https://blakecrosley.com/guides/design/readwise-reader)), not Readwise's own docs (unverified).
- Literata's exact variable axes (opsz range) were not verifiable from the Google Fonts specimen fetch; axis presence is per TypeTogether/specimen metadata (unverified in detail — confirm at font-integration time).
- iA Writer Quattro's license file must be read before vendoring (repo states Plex derivation and requests credit; Plex itself is SIL OFL) — confirm redistribution terms if Direction D's utility face is adopted.
- Standard Ebooks' site heading face (League Spartan) was confirmed via a repo mirror of their web fonts, not a primary statement (secondary).
- All hex palettes are specified for contrast plausibility but have not been run through a WCAG checker against every token pairing; run one before the tokens PR (ink-on-background pairs were chosen at ≥ ~10:1, accents at ≥ ~4.5:1 on their fields, but verify).
