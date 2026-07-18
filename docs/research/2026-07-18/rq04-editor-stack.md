# RQ04 — Editor Stack for Learny Notes (Next.js 15 / React 19)

- Date: 2026-07-17 (all sources accessed 2026-07-17 unless noted)
- Status: Research complete; recommendation below
- Question: Which editor should power Learny's notes — plain Markdown textarea (+preview), CodeMirror 6, TipTap (ProseMirror), or Lexical — given permissive licensing, no phone-home, React 19 compatibility today, bundle weight, wikilink/autocomplete extensibility, and Learny's vendoring posture (vendor-and-own over depending on churning libraries)?

## Context Constraints (from Learny)

- Frontend: Next.js 15.5.4, React 19.1.2, Tailwind v4, shadcn/ui, vendored AI Elements (`frontend/package.json`).
- Self-hosted, offline-capable, no CDN; provider-neutral; no framework lock-in.
- Already shipped in the frontend: `streamdown` 2.5.0 (Apache-2.0 streaming Markdown renderer used by AI Elements) and `cmdk` 1.1.1 (command/menu primitive usable for autocomplete popovers).
- Notes will interoperate with a Markdown-native pipeline: corpus sections, quiz snapshots, and Anki export all treat Markdown text as the canonical interchange.

## Method

- Versions, publish dates, licenses, and peer-dependency ranges read directly from the npm registry API (`registry.npmjs.org`), accessed 2026-07-17 — primary source for licensing and React-range claims.
- Bundle weights measured locally with esbuild (`--bundle --minify --format=esm`, `react`/`react-dom`/`yjs` externalized) on the latest versions, 2026-07-17 — reproducible primary measurement of realistic setups, not marketing numbers.
- Telemetry check: grepped every URL string out of the published dist bundles of `@tiptap/core`, `@tiptap/react`, `lexical`, `@lexical/react`, `@codemirror/view`, `@codemirror/state`; found only documentation-comment URLs (Unicode spec, MDN, Stack Overflow), no network endpoints. None of these packages phones home at runtime.

## Findings

### Licensing and current versions (npm registry, accessed 2026-07-17)

| Package | Latest | Published | License | React peer range |
|---|---|---|---|---|
| `lexical` | 0.48.0 | 2026-07-16 | MIT | n/a (core) |
| `@lexical/react` | 0.48.0 | 2026-07-16 | MIT | `>=18.x` |
| `@tiptap/core` | 3.28.0 | 2026-07-15 | MIT | n/a (headless core) |
| `@tiptap/react` | 3.28.0 | 2026-07-15 | MIT | `^17.0.0 \|\| ^18.0.0 \|\| ^19.0.0` |
| `@tiptap/markdown` | 3.28.0 | 2026-07-15 | MIT | — (official Markdown parser/serializer) |
| `@tiptap/extension-mention` / `@tiptap/suggestion` | 3.28.0 | 2026-07-15 | MIT | — |
| `codemirror` (meta) | 6.0.2 | 2025-06-19 | MIT | none — framework-agnostic, zero peer deps |
| `@codemirror/view` | 6.43.6 | 2026-07-06 | MIT | none |
| `@codemirror/autocomplete` | 6.20.3 | 2026-06-03 | MIT | none |
| `@codemirror/lang-markdown` | 6.5.1 | 2026-07-15 | MIT | none |
| `streamdown` (already shipped) | 2.5.0 | 2026-03-17 | Apache-2.0 | — |

All four options are permissively licensed and actively maintained (every option published within the last month, except the stable `codemirror` meta-package whose underlying `@codemirror/*` modules update continuously).

TipTap licensing nuance: the editor core and all packages above are MIT, but TipTap is open-core — Pro extensions (comments, AI, collaboration/version history) are paid, delivered via a private npm registry requiring a Tiptap Cloud account (https://tiptap.dev/docs/editor/getting-started/overview, accessed 2026-07-17). Nothing Learny needs is Pro, and the MIT packages contain no telemetry (dist grep above), but the commercial gravity is real: features land on the paid side first.

CodeMirror funding: MIT with a voluntary-funding model, sponsored by (among others) Obsidian, Replit, CodePen (https://codemirror.net/, accessed 2026-07-17). No account, no cloud, no phone-home.

### React 19 compatibility today

- **TipTap**: explicit — `@tiptap/react@3.28.0` declares `react ^19.0.0` in peerDependencies (npm registry, primary source). Tiptap 3.0 went stable 2025-07-12 and its release notes cite React 19 ref-behavior support and a React 19 StrictMode fix (useRef instead of useState for the portal element) (https://tiptap.dev/blog/release-notes/tiptap-3-0-is-stable, https://tiptap.dev/docs/resources/whats-new, accessed 2026-07-17).
- **Lexical**: `@lexical/react@0.48.0` declares `react >=18.x`, which admits React 19; v0.47.0 (2026-07-09) dropped React 17 (peer range moved from `>=17.x` to `>=18.x`, npm registry). The Lexical changelog references added React 19 unit tests (PR #6048) (https://github.com/facebook/lexical/blob/main/CHANGELOG.md — seen via search snippet, not independently re-read: treat the unit-test detail as (unverified); the peer range itself is verified).
- **CodeMirror 6**: framework-agnostic with zero peer dependencies (npm registry) — React version is irrelevant; integration is an owned ~30-line wrapper (ref + `useEffect` mount/destroy). There is no official React binding; community wrappers exist but are unnecessary and would violate Learny's vendoring preference anyway.
- **Plain textarea**: native React 19; nothing to verify.

### Bundle weight (measured with esbuild, 2026-07-17; react/react-dom/yjs external)

| Setup | Minified | Min+gzip |
|---|---|---|
| Plain `<textarea>` + streamdown preview | ~0 KB new | ~0 KB new (streamdown already shipped for Q&A rendering) |
| Lexical: `@lexical/react` rich text + history + markdown shortcuts + typeahead + list + link nodes | 383 KB | **125 KB** |
| TipTap: `@tiptap/react` + StarterKit + `@tiptap/suggestion` (ProseMirror included via `@tiptap/pm`) | 403 KB | **129 KB** |
| CodeMirror 6: view/state/commands + `markdown()` + `autocompletion()` + history | 515 KB | **176 KB** |

Notes:
- Lexical's advertised "22 KB core" is the bare `lexical` package (54 KB gz alone per bundlephobia); a usable rich-text + markdown editor lands at ~125 KB gz.
- The CodeMirror number is inflated by `@codemirror/lang-markdown` transitively pulling HTML/CSS/JS Lezer grammars for fenced-code highlighting; a trimmed config (markdown grammar without nested-language highlighting) would land materially lower (not measured — (unverified)).
- All three libraries are within ~1.4x of each other; the only order-of-magnitude win is the textarea.

### Wikilink `[[...]]` autocomplete extensibility

- **CodeMirror 6**: first-class. `@codemirror/autocomplete` accepts custom `CompletionSource` functions with arbitrary trigger contexts (e.g., match `\[\[[^\]]*` before the cursor), plus decorations for live wikilink styling (https://codemirror.net/docs/ref/#autocomplete, accessed 2026-07-17). **Obsidian — the canonical wikilinks-over-Markdown application — is built on CodeMirror 6** ("Obsidian uses CodeMirror 6 (CM6) to power the Markdown editor", https://docs.obsidian.md/Plugins/Editor/Editor+extensions, accessed 2026-07-17) and sponsors the project. This is the strongest possible existence proof for the exact UX Learny would want.
- **TipTap**: `@tiptap/extension-mention` over `@tiptap/suggestion` (both MIT, 3.28.0) supports configurable trigger characters and popup rendering; `[[` triggers are a supported customization. Official `@tiptap/markdown` (3.28.0, MIT) now handles Markdown parse/serialize, closing v2's biggest gap for a Markdown-canonical app (npm registry, accessed 2026-07-17).
- **Lexical**: `LexicalTypeaheadMenuPlugin` in `@lexical/react` provides trigger-based typeahead (the playground's mentions demo uses it); `@lexical/markdown` (MIT) handles shortcut conversion and import/export.
- **Textarea**: DIY. A raw textarea has no DOM ranges, so anchoring a `cmdk`-style popover to the caret requires the mirror-div measurement trick; insertion/undo handling is manual. Workable (GitHub's comment box is this pattern) but it is bespoke code Learny must own, and there is no inline styling of wikilinks — they only render in the preview.

### Vendoring / churn fit

- **Lexical is still 0.x and ships breaking changes in nearly every monthly release** — v0.44 through v0.48 each carry a Breaking Changes section (removed exports, changed selection semantics, dropped React 17) (https://github.com/facebook/lexical/releases, accessed 2026-07-17). This is exactly the churn profile Learny's vendoring policy exists to avoid; vendoring Lexical wholesale is impractical (large multi-package graph).
- **TipTap 3.x is a stable major** (stable since 2025-07-12) with semver discipline, but it sits on the ProseMirror package family plus ~10 `@tiptap/*` packages — a wide surface to track, governed by a VC-backed open-core vendor.
- **CodeMirror 6 has had a stable 6.x API since 6.0.0 (2022-06-08, npm registry)** — four years of non-breaking evolution, one maintainer with a sponsorship model, no framework coupling. The only integration code (React wrapper, completion source, decorations) is small, Learny-owned, and analogous to how AI Elements are vendored.
- **Textarea**: nothing to vendor; the risk inverts into bespoke caret/popover code Learny owns forever.

## Options Table

| Criterion | Textarea + preview | CodeMirror 6 | TipTap 3 | Lexical |
|---|---|---|---|---|
| License | n/a (streamdown Apache-2.0, shipped) | MIT | MIT core; paid Pro tier | MIT |
| Phone-home | none | none (dist grep clean) | none in MIT pkgs; Pro needs cloud account | none (dist grep clean) |
| React 19 today | native | agnostic, zero peer deps | explicit `^19.0.0` peer | `>=18.x` peer; 0.47 dropped R17 |
| New bundle (min+gz) | ~0 KB | 176 KB (trimmable) | 129 KB | 125 KB |
| Wikilink autocomplete | DIY caret tricks | first-class (`CompletionSource`); Obsidian proof | `Mention`/`Suggestion` (MIT) | `TypeaheadMenuPlugin` |
| Markdown-canonical | trivially (it IS markdown) | native (edits raw MD) | via `@tiptap/markdown` round-trip | via `@lexical/markdown` round-trip |
| API stability | n/a | 6.x stable since 2022 | 3.x stable since 2025-07 | 0.x, monthly breaking changes |
| Vendoring fit | perfect (nothing) | good (thin owned wrapper) | medium (wide pkg surface, open-core vendor) | poor (churn + big graph) |
| WYSIWYG | no | no (styled source) | yes | yes |

## Recommendation

**Recommended: start with the plain Markdown textarea + streamdown preview (Option A), with CodeMirror 6 as the named upgrade path (Option B) once wikilink UX is actually wanted.** Notes stay canonical Markdown in PostgreSQL either way, so the editor is a swappable presentation detail — the upgrade is additive, not a migration.

- **Option A — Markdown textarea + streamdown preview (recommended as smallest-viable)**
  - Why recommend: zero new dependencies — streamdown 2.5.0 already renders Markdown in the shipped Q&A UI, so edit/preview reuses it; zero bundle cost, zero licensing/telemetry surface, native React 19; keeps notes as plain Markdown, which is exactly what the corpus/citation/Anki pipeline speaks; nothing to vendor or track; shippable in a day inside a shadcn form.
  - Why not: no inline wikilink autocomplete without bespoke caret-position code (mirror-div trick) that Learny then owns; no live styling of links/headings while typing; the editing feel is the weakest of the four and will likely be outgrown if notes become a daily-driver second-brain surface.

- **Option B — CodeMirror 6 (recommended upgrade path)**
  - Why recommend: the proven stack for exactly this product shape — Obsidian's wikilinks-over-Markdown editor is CodeMirror 6 (docs.obsidian.md, primary source); MIT, no phone-home, no accounts, funded by sponsorship; zero peer dependencies and framework-agnostic, so the React 19 question does not exist and the entire React integration is a ~30-line wrapper Learny owns — the best possible match for the vendor-and-own posture; `CompletionSource` gives `[[` autocomplete first-class, decorations give live wikilink styling; API stable since 2022; edits raw Markdown so the stored note is always the source of truth (no rich-doc↔Markdown round-trip loss).
  - Why not: heaviest measured bundle of the three libraries (176 KB gz as configured, though trimmable); it is a source editor, not WYSIWYG — users see Markdown syntax (styled), which suits developer-adjacent users but not people expecting a Notion-like surface; no official React binding means Learny writes and maintains the (small) wrapper itself.

- **Option C — TipTap 3 (ProseMirror)**
  - Why recommend: the strongest WYSIWYG option today — explicit React 19 peer support and StrictMode fixes in the stable 3.x line; MIT `Mention`/`Suggestion` extensions make `[[` autocomplete configuration-level work; official MIT `@tiptap/markdown` (new in v3) makes a Markdown-canonical round-trip supportable; mid-pack bundle (129 KB gz); huge ecosystem and battle-tested ProseMirror underneath.
  - Why not: open-core commercial gravity — the vendor's roadmap energy goes to paid Cloud/Pro features, and the free/paid boundary can move; ~10-package surface plus the ProseMirror family is a wide dependency graph to track, at odds with vendoring; WYSIWYG means the stored Markdown is a serialization of a rich document rather than the artifact the user directly edited, adding round-trip edge cases the textarea and CodeMirror options never have.
  - 
- **Option D — Lexical**
  - Why recommend: MIT, Meta-backed, genuinely modern architecture; smallest measured realistic bundle of the three libraries (125 KB gz); `TypeaheadMenuPlugin` and `@lexical/markdown` cover the wikilink and Markdown needs; clean lazy-loadable plugin design.
  - Why not: still 0.x after four years, with breaking changes in nearly every monthly release (v0.44–v0.48 all carry breaking changes; React 17 support dropped mid-cycle in 0.47) — the exact churn profile Learny's vendoring policy exists to avoid, and the multi-package graph is too large to vendor; React peer range (`>=18.x`) admits 19 but React 19 is not explicitly first-class in the peer declaration the way TipTap's is; docs do not state a stability policy.

### Decision rule for triggering the upgrade

Adopt Option B when any of these becomes true: (1) wikilink autocomplete is a committed feature, (2) users ask for live syntax styling while typing, (3) the bespoke caret/popover code for the textarea would exceed roughly the size of the CodeMirror wrapper + completion source. Do not adopt TipTap/Lexical unless a true WYSIWYG requirement appears — and if it does, prefer TipTap 3 over Lexical on stability grounds.

## Open Issues

- Trimmed CodeMirror bundle: how small does the Markdown setup get without nested-language code-block highlighting? (unmeasured)
- Lexical React 19 unit-test claim (#6048) taken from a changelog search snippet, not independently re-read from the changelog file. (unverified)
- Textarea caret-anchored autocomplete effort was estimated from the known mirror-div pattern, not prototyped.
- streamdown editing-preview parity: streamdown targets streaming AI output; confirm it renders user-authored Markdown (tables, footnotes, wikilink syntax post-transform) acceptably before shipping Option A.
- Whether Learny wikilinks should resolve to note slugs, corpus anchors, or both is a product decision that shapes the completion source regardless of editor choice.

## Source Index (accessed 2026-07-17)

- npm registry API: `https://registry.npmjs.org/{lexical, @lexical/react, @tiptap/core, @tiptap/react, @tiptap/markdown, @tiptap/extension-mention, @tiptap/suggestion, codemirror, @codemirror/view, @codemirror/state, @codemirror/autocomplete, @codemirror/lang-markdown, streamdown}` — versions, dates, licenses, peer ranges
- https://codemirror.net/ — license, funding, sponsors
- https://codemirror.net/docs/ref/#autocomplete — CompletionSource API
- https://docs.obsidian.md/Plugins/Editor/Editor+extensions — "Obsidian uses CodeMirror 6 (CM6) to power the Markdown editor"
- https://tiptap.dev/docs/editor/getting-started/overview — open-core model, Pro/Cloud boundary
- https://tiptap.dev/blog/release-notes/tiptap-3-0-is-stable — 3.0 stable 2025-07-12
- https://tiptap.dev/docs/resources/whats-new — React 19 ref/StrictMode fixes
- https://github.com/facebook/lexical/releases — 0.x breaking-change cadence
- https://github.com/facebook/lexical/blob/main/CHANGELOG.md — React 17 drop, React 19 tests (partially unverified, see Open Issues)
- Local esbuild measurements, 2026-07-17 (methodology in Method section)
- `/home/augusto/projects/learny/frontend/package.json` — shipped streamdown/cmdk/React 19.1.2

## Verification corrections

Adversarial verification pass, 2026-07-17 (npm registry API, GitHub releases API, local reproduction of the dist grep and esbuild measurements). One claim was refuted; the correction below supersedes the affected statements.

- **Correction: Lexical v0.48.0 contains no breaking changes.** The report states that "v0.44 through v0.48 each carry a Breaking Changes section" (Vendoring/churn section, also reflected in the Options Table and Option D). This is false for the newest release: the v0.48.0 release notes (published 2026-07-16, https://github.com/facebook/lexical/releases/tag/v0.48.0) describe "a maintenance release focused on bug fixes" and contain no Breaking Changes section and no mention of breaking changes anywhere in the body. The corrected statement is: **v0.44.0 (2026-04-27), v0.45.0 (2026-05-28), v0.46.0 (2026-06-26), and v0.47.0 (2026-07-09) each carry an explicit Breaking Changes section; v0.48.0 (2026-07-16) does not.** Relatedly, the cadence is not strictly monthly — v0.47.0 and v0.48.0 shipped one week apart. The surrounding facts were confirmed: Lexical is still 0.x, and v0.47.0 did drop React 17 (`@lexical/react` peer range moved from `react >=17.x` to `react >=18.x` between 0.46.0 and 0.47.0, npm registry, verified 2026-07-17). The overall churn characterization ("breaking changes in nearly every monthly release") survives, but the universal "each of v0.44–v0.48" claim does not.
