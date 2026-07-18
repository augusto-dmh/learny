# RQ07 — Export and portability: Obsidian-compatible Markdown vault export for Learny notes + highlights

- Date: 2026-07-18 (sources accessed 2026-07-17)
- Status: Research complete; feeds a future notes/highlights feature cycle (feature itself is not yet designed or shipped)
- Related: ADR-0021 (Anki export via genanki — the "export is a projection" precedent), ADR-0002 (canonical corpus with stable anchors), ADR-0003 (citations are core)

## Research question

What should an Obsidian-compatible Markdown export of Learny notes and highlights look like (frontmatter, wikilinks, folder layout, citation serialization), what must Learny store to make the export lossless, and is export a projection (like the genanki Anki export) or a sync?

## Method note

Web search tooling was intermittently unavailable during this session; all findings below were verified by fetching primary sources directly (Obsidian's official help site, Readwise's official docs, plugin repositories). Claims that could not be pinned to a primary source are marked (unverified).

---

## Findings

### 1. An Obsidian "vault" is just a folder of plain Markdown files — there is no import format to target

Obsidian stores notes as "Markdown-formatted plain text files in a vault," which is "a folder on your local file system, including any subfolders"; vault-specific configuration lives in a `.obsidian` directory and everything else is open plain text, explicitly editable by other tools ([https://obsidian.md/help/data-storage](https://obsidian.md/help/data-storage), accessed 2026-07-17). Consequence for Learny: "Obsidian export" means producing a well-formed folder of `.md` files (deliverable as a zip or written to a directory). There is no manifest, no registration step, no API — compatibility is purely a matter of following Obsidian's Markdown dialect and conventions.

### 2. Frontmatter: Obsidian Properties spec

From the official Properties documentation ([https://obsidian.md/help/properties](https://obsidian.md/help/properties), accessed 2026-07-17):

- YAML between `---` delimiters, positioned at the very beginning of the file; `name: value` with a space after the colon; property names must be unique within a note.
- Supported types: text, list, number, checkbox (`true`/`false`), date (`YYYY-MM-DD`), date & time (`YYYY-MM-DDTHH:MM:SS`), and the specialized tags list.
- Default properties Obsidian understands natively: `tags`, `aliases`, `cssclasses` (all lists).
- Internal links inside property values must be written as quoted `"[[Link]]"` strings; Markdown in property values is intentionally not rendered; nested properties are unsupported.
- Frontmatter tags "should always be formatted as a list"; tag characters are limited to letters, numbers, `_`, `-`, `/` (nested), and common Unicode; at least one non-numeric character; case-insensitive ([https://obsidian.md/help/tags](https://obsidian.md/help/tags), accessed 2026-07-17).

Custom keys (e.g. `learny-source-id`) are permitted — properties are arbitrary — they simply render as text/list properties.

### 3. Wikilinks, heading links, and block references

From the official links documentation ([https://obsidian.md/help/links](https://obsidian.md/help/links), accessed 2026-07-17):

- Wikilink: `[[Note Name]]`, folder-qualified `[[Folder/Note Name]]` (forward slashes on all platforms), display text via pipe: `[[Target|Display]]`.
- Heading links: `[[Note#Heading]]`, nested `[[Note#Heading#Subheading]]`.
- **Block references**: `[[Note#^block-id]]` targets a block marked with `^block-id` at the end of a paragraph line (or on its own line after structured blocks). Block identifiers may use Latin letters, numbers, and dashes. This is the key primitive for making individual highlights addressable from anywhere in the user's vault.
- Characters that "may not work as a link" (i.e. must not appear in exported note names): `# | ^ : %% [[ ]]`.
- Obsidian rewrites links on rename inside the app, but an external exporter gets no such help — exported filenames must be deterministic and stable across exports or cross-file links break.

### 4. Obsidian Flavored Markdown extensions relevant to highlights

From [https://obsidian.md/help/obsidian-flavored-markdown](https://obsidian.md/help/obsidian-flavored-markdown) (accessed 2026-07-17): Obsidian builds on CommonMark + GFM and adds wikilinks, embeds `![[...]]`, block IDs `^id`, callouts `> [!type]`, comments `%%...%%`, and `==highlight==` marks, while "striv[ing] for maximum capability without breaking any existing formats." Callouts include a `quote` type with alias `cite`, custom titles, and folding ([https://obsidian.md/help/callouts](https://obsidian.md/help/callouts), accessed 2026-07-17). A `> [!quote]` callout is therefore a native, semantically-labeled container for a cited book passage — and degrades to a plain blockquote in any other Markdown renderer.

### 5. Readwise's official Obsidian export — the dominant importer convention

From Readwise's official docs ([https://docs.readwise.io/readwise/docs/exporting-highlights/obsidian](https://docs.readwise.io/readwise/docs/exporting-highlights/obsidian), accessed 2026-07-17; plugin repo [https://github.com/readwiseio/obsidian-readwise](https://github.com/readwiseio/obsidian-readwise), accessed 2026-07-17):

- **Layout**: one file per book/article, in a configurable base folder, optionally grouped in category subfolders (Books/Articles/...). Filename defaults to the document title (templatable via Jinja2).
- **Frontmatter**: off by default; offered as an optional, user-configurable Properties template (i.e. Readwise treats frontmatter as a customization surface, not a fixed schema).
- **Body**: metadata block (cover image, wiki-linked author, title, category hashtag, tags, URL), then a `## Highlights` section. Each highlight is a bullet: highlight text, then a parenthesized location link `([location](url))`, with tags and the user's note as nested sub-bullets.
- **Sync semantics**: explicitly **one-way** ("bidirectional sync… At the moment, no") and **append-only** — "nothing in Obsidian will ever be overwritten"; new highlights are appended under timestamped `## New highlights added <date>` headers, and user edits to the file are never touched. Known cost of this model: renaming/moving a file causes the plugin to recreate it at the original path when new highlights arrive, producing duplicates; recovery is delete-and-resync.

The community Kindle plugin ([https://github.com/hadynz/obsidian-kindle-plugin](https://github.com/hadynz/obsidian-kindle-plugin), accessed 2026-07-17) follows the same broad shape — one file per book, native frontmatter, Nunjucks templates — but uses an "intelligent diff" resync that merges new highlights without disturbing user edits, showing that merge-on-resync is possible but is real complexity that only pays off when the target is a *live* vault the user co-edits.

### 6. Learny's own precedent: export is a projection

ADR-0021 (`docs/adr/0021-active-recall-design.md`) fixed the pattern for Anki: genanki `.apkg` export with note GUIDs derived from `(source_id, content_key)`, so **re-export + re-import updates in place instead of duplicating**; the database remains the sole source of truth and the export artifact is disposable and regenerable. Quiz items deliberately have no corpus FK — they snapshot citation text + anchor and reconcile on re-ingest. The same identity-and-snapshot discipline transfers directly: a Markdown vault export is a *projection* of DB state with stable identities embedded (filenames, block IDs), never a second store of truth and never a sync target.

---

## What Learny must store for the export to be lossless

"Lossless" here means: the exported vault is a pure function of database state — it can be regenerated byte-identically at any time, and nothing the export contains exists only in the exported files. That requires the (future) notes/highlights model to store:

| Stored field | Why the export needs it |
|---|---|
| Stable per-highlight/per-note ID minted at creation (content-key style, e.g. short hash) | Becomes the Obsidian block ID `^lh-<id>` and the reconciliation identity across re-ingests (mirrors quiz `(source_id, content_key)`); must survive corpus replacement |
| Verbatim snapshot of the highlighted text | Highlights must render even if re-ingest changed the corpus (no corpus FK, same rule as quiz items); also enables relocate/stale reconciliation |
| Anchor + section path + page span snapshot | Serializes the human-readable citation line and the deep link back into Learny; anchors are already stable per ADR-0002 (EPUB href-based, PDF `pdf:{slug-path}/b{ordinal}-{sha256[:16]}`) |
| User note body (Markdown), tags, color, created/updated timestamps | Direct payload; timestamps map to Obsidian `date`/`datetime` property types (`YYYY-MM-DD`, `YYYY-MM-DDTHH:MM:SS`) |
| Per-source deterministic filename slug, stored (not re-derived from title each export) | Exported wikilinks/block links break if the filename drifts; slug must exclude `# | ^ : %% [[ ]]` and filesystem-reserved characters, and be collision-free per user |
| Book metadata: title, author(s), language, source ID | Frontmatter (`title` via filename/`aliases`, `author`, `learny-source-id`) and the metadata block |
| Highlight status after reconciliation (active/stale/relocated/orphaned) | Lets the export annotate detached highlights instead of silently dropping them (same choice ADR-0021 made for stale quiz items) |

Everything above except the stored slug and the highlight entity itself already has a proven pattern in the shipped quiz subsystem.

---

## Options

### A. Export semantics

| Option | Why recommend | Why not |
|---|---|---|
| **A1. One-way projection: regenerate the entire Learny-owned folder on each export (zip download or target directory) — RECOMMENDED** | Matches the shipped genanki precedent and re-ingest-replaces-corpus semantics; deterministic and trivially testable with golden fixtures (ADR-0016 pattern); zero merge logic; stable filenames + block IDs mean the user's *own* vault notes that link into Learny files survive regeneration; honest about where truth lives (Learny DB) | Clobbers any edits the user made *inside* the exported files; users who annotate in Obsidian rather than Learny will lose those edits on re-export (must be documented loudly; mitigated by putting exports in a clearly Learny-owned folder) |
| A2. Readwise-style append-only writes into a live vault | Never destroys user edits (Readwise's explicit guarantee); proven UX for the highlight-sync category | Requires a resident agent/plugin watching a vault path — Learny is a self-hosted web app with no desktop presence; append-only accretes duplicate/`New highlights added` sections and cannot propagate edits or deletions; Readwise's own docs show the failure mode (renamed files get recreated as duplicates); no longer a pure projection, so goldens and idempotence are lost |
| A3. Bidirectional sync (parse user edits back into Learny) | The only option that lets users edit in either tool | Readwise — with far more resources — explicitly declines it as too complex; requires parsing arbitrary human-edited Markdown back into structured rows, conflict resolution, and a change-tracking protocol; violates the projection principle and the "PostgreSQL is source of truth" constraint; wildly out of scope for a single-user self-hosted app |

### B. File granularity and layout

| Option | Why recommend | Why not |
|---|---|---|
| **B1. One file per book, highlights as block-ID'd entries in section order — RECOMMENDED** | The convention every major importer converged on (Readwise, Kindle plugin: "one file per book"); reading order + section headings reconstruct the book's shape, which is Learny's core differentiator (structure-preserving corpus); block IDs `^lh-<id>` make each highlight individually linkable (`[[Book#^lh-abc123]]`) so per-highlight granularity is not lost; small file count keeps vault tidy | A heavily-highlighted book yields one long file; per-highlight backlinks require block-reference literacy from the user |
| B2. One file per highlight (atomic/Zettelkasten notes) | Maximum linkability; each highlight is a first-class graph node | Explodes file count (hundreds of files per book); no importer convention works this way by default; citation context (section, neighbors) is lost per file; filename stability problem multiplies by highlight count |
| B3. Single monolithic export file per user | Simplest possible writer | Ignores the file-per-book convention; unusable graph/backlink experience; giant file defeats Obsidian's linking model |

---

## Recommended export shape (concrete)

Delivered as a zip (or written to a directory) containing a self-contained folder the user drops into their vault:

```
Learny/
  Books/
    <stored-slug>.md          # one per source with ≥1 highlight/note
  Learny Index.md             # optional: wikilinked list of exported books
```

Per-book file:

```markdown
---
aliases:
  - <Full Book Title>
author:
  - <Author>
tags:
  - learny
learny-source-id: <source uuid>
learny-export-version: 1
exported: 2026-07-18T09:00:00
---

# <Full Book Title>

## <Section path, in reading order>

> [!quote] <section path › page(s) N–M>
> <verbatim highlight snapshot>

- Note: <user note markdown, if any>
- Tags: #learny/<tag> ...

^lh-<stable-highlight-id>
```

Key rules:

- **Block ID per highlight** (`^lh-<id>`, letters/digits/dashes only) on its own line after the callout (the documented placement for structured blocks), minted from the stored highlight ID — never re-derived from content, so re-exports keep identity like genanki GUIDs.
- **Citation line inside the callout title**: section path + page span from the snapshot, matching Learny's existing citation surface; optionally append a plain link back to the app (`http://<host>/sources/<id>?anchor=...`) — a projection may reference its origin.
- **Filenames from a stored slug**, sanitized against `# | ^ : %% [[ ]]` + filesystem-reserved characters, stable for the life of the source; full title lives in `aliases` so `[[Full Book Title]]` still resolves.
- **Frontmatter uses only default-typed properties** (`aliases`, `tags`, text, datetime) plus namespaced `learny-*` keys; no Markdown in property values; internal links in properties quoted if ever used.
- **Stale/orphaned highlights are exported too**, footnoted with their status (ADR-0021's choice for quiz items) — silently dropping them would make the export lossy.
- **Re-export replaces the `Learny/` folder wholesale.** Documented as: "This folder is generated by Learny; edits made here are overwritten on the next export. Link *to* these notes from your own notes — those links survive."

## Recommendation

Ship Obsidian export as a **one-way, deterministic projection** (A1 + B1): a regenerable `Learny/` folder with one Markdown file per book, Obsidian Properties frontmatter carrying `learny-source-id` and export metadata, highlights serialized as `[!quote]` callouts in section order with citation (section path + page span) in the callout title and a stable `^lh-<id>` block ID per highlight, user notes and tags nested beneath. This is the genanki pattern transplanted: stable identity embedded in the artifact, database as sole source of truth, no sync ambitions — Readwise's own refusal of bidirectional sync and its append-only duplicate pathology are the strongest external evidence that projection is the right ceiling for a project of Learny's size. The binding prerequisite is that the future notes/highlights data model mints a stable content-key-style ID and snapshots text + anchor + section path + page span at highlight time, exactly as quiz items already do.

## Open issues

1. The notes/highlights feature itself has no ADR or cycle yet; this research constrains its data model (stable ID + snapshot fields must exist from day one) and should be an input to that cycle's design.
2. Filename slug lifecycle: store at source level vs. at first export; behavior if a user re-uploads a retitled edition of the same book.
3. Whether to offer a Readwise-style optional "full section text" companion export — useful for context, but exporting large verbatim book text raises copyright questions for shared vaults. Deferred.
4. If users demand live-vault workflows later, the Kindle plugin's "intelligent diff" merge is the proven middle ground between projection and sync — a possible future mode, explicitly out of scope now.
5. (unverified) Prevalence of other importer conventions beyond Readwise/Kindle (e.g. Omnivore, Zotero integrations) was not surveyed because web search was unavailable; the two verified importers already agree on file-per-book, so additional survey is unlikely to change the recommendation.
