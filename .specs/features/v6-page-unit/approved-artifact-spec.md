# Approved artifact specs — RFC-006 Cycle B (`v6-page-unit`)

Extracted verbatim from the two artifacts the driver approved. These are the **accepted spec**;
where they conflict with RFC-006's cycle text, RFC-006 wins (noted inline).

---

## A. Study-activity heatmap
Source: study-activity artifact (APPROVED). Target file per its own footer:
`frontend/app/components/study-heatmap.tsx` — **presentational only**, Iron Gall tokens, no new colours.

### The defect being fixed
`grid-flow-col` declares seven rows and **no column track**, so implicit `auto` columns stretch
to fill the card. Fix = fixed-width implicit columns + start alignment.

### Tokens (all already in `globals.css`; do not invent colours)
Light: `--lv0:#EDF0F1 --lv1:#B3CCDD --lv2:#82A9C3 --lv3:#4F7EA3 --lv4:#22557A`
Dark:  `--lv0:#1C2830 --lv1:#2E4C63 --lv2:#3F6885 --lv3:#5588AB --lv4:#6FA9CC`
Also: `--cell-edge` (light `rgb(27 39 51 / 0.055)`, dark `rgb(217 226 232 / 0.05)`),
`--ring` (light `rgb(34 85 122 / 0.55)`, dark `rgb(111 169 204 / 0.6)`),
`--tip-bg`/`--tip-fg` (light `#1B2733`/`#F4F8FA`, dark `#D9E2E8`/`#0E1A22`).
Sizing: `--cell: 15px; --gap: 4px;` (was 12px cells).

### Grid structure
```
.graph   { display:grid; grid-template-columns:auto auto; grid-template-rows:auto auto;
           gap:6px; justify-content:start; }
           /* cell 1 = empty spacer, 2 = .months, 3 = .weekdays, 4 = .cells */
.months  { display:grid; grid-auto-flow:column; grid-auto-columns:var(--cell);
           gap:var(--gap); justify-content:start; height:14px; }
.months span { font-family:var(--font-mono); font-size:10.5px; letter-spacing:0.04em;
           color:var(--fg-muted); white-space:nowrap; align-self:end; }
.weekdays{ display:grid; grid-template-rows:repeat(7,var(--cell)); gap:var(--gap);
           padding-right:4px; }
.weekdays span { font-family:var(--font-mono); font-size:10.5px; color:var(--fg-muted);
           line-height:var(--cell); text-align:right; }
.cells   { display:grid; grid-auto-flow:column; grid-template-rows:repeat(7,var(--cell));
           grid-auto-columns:var(--cell); gap:var(--gap); justify-content:start; }  /* THE FIX */
.cell    { width:var(--cell); height:var(--cell); border-radius:3px; background:var(--lv0);
           box-shadow:inset 0 0 0 1px var(--cell-edge); }
.cell[data-level="1".."4"] { background:var(--lv1..4); }
.cell[data-active="true"]:hover, :focus-visible { outline:2px solid var(--ring); outline-offset:1px; }
.cell[data-today="true"] { box-shadow:inset 0 0 0 1px var(--cell-edge), 0 0 0 1px var(--fg-muted); }
.cell[data-placeholder="true"] { background:transparent; box-shadow:none; }
```
Weekday column markup (7 spans, `aria-hidden="true"` on the wrapper), labels only on rows 2/4/6:
`<span></span><span>Mon</span><span></span><span>Wed</span><span></span><span>Fri</span><span></span>`

Graph wrapper: `.graph-scroll { overflow-x:auto; padding-bottom:2px; }` around `.graph`.
`.graph` carries `role="img"` + `aria-label="study activity heatmap, last 12 weeks"`.

### Month labels
A month label sits over the column where that month's **first non-placeholder day** lands:
iterate columns, take the first non-placeholder cell, and if its month differs from the last
labelled month **and `c < columns - 1`**, emit `<span style="grid-column: c+1">MMM</span>`.
`MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]`.

### Legend + footer
```
.graph-foot { display:flex; align-items:center; justify-content:space-between; gap:18px;
              font-family:var(--font-mono); font-size:10.5px; letter-spacing:0.04em;
              color:var(--fg-muted); }
.legend i   { width:11px; height:11px; border-radius:2px; background:var(--lv0);
              box-shadow:inset 0 0 0 1px var(--cell-edge); }   /* + data-level 1..4 */
```
Left text: `Last 12 weeks`. Right: `Less` + five swatches (lv0..lv4) + `More`.

### Tooltip
```
#tip { position:fixed; z-index:20; pointer-events:none; opacity:0;
       transform:translate(-50%,-100%); background:var(--tip-bg); color:var(--tip-fg);
       border-radius:4px; padding:6px 9px; font-family:var(--font-mono); font-size:11.5px;
       line-height:1.45; white-space:nowrap;
       box-shadow:0 6px 20px -10px rgb(0 0 0 / 0.5); transition:opacity 90ms ease-out; }
#tip[data-show="true"] { opacity:1; }
#tip .tip-day { opacity:0.68; }
@media (prefers-reduced-motion: reduce) { #tip { transition:none; } }
```
Content, two lines: `"7 reviews · 9 pages"` then `<span class="tip-day">Tue, Jul 21</span>`.
Pluralize: `n + " " + word + (n === 1 ? "" : "s")`. Weekday `["Sun".."Sat"]`, then `MMM D`.
Shown on **mouseenter and focus**, hidden on **mouseleave, blur, and window scroll**.
Positioned at `rect.left + rect.width/2` (left) and `rect.top - 8` (top).
**Only cells with `total > 0` are interactive** (`data-active="true"`, `tabIndex=0`).
Empty days: no tooltip, no `title`, not focusable — silent grace.

### Level ramp (unchanged formula)
`total = reviews_count + reading_updates`; `level = total<=0?0 : <=1?1 : <=3?2 : <=6?3 : 4`.

### Readout
```html
<p class="adherence" data-testid="streak-line">Studied <span class="figure">11</span>
  of the last <span class="figure-sm">14</span> days</p>
<div class="totals">
  <span class="total"><span class="n">318</span><span class="k">reviews</span></span>
  <span class="total"><span class="n">412</span><span class="k">pages</span></span>  <!-- CONDITIONAL -->
</div>
```
```
.adherence { color:var(--fg-muted); font-size:14px; line-height:1.35; max-width:22ch; }
.figure    { font-family:var(--font-mono); font-variant-numeric:tabular-nums; font-size:34px;
             font-weight:500; letter-spacing:-0.03em; color:var(--fg); line-height:1; }
.figure-sm { font-family:var(--font-mono); font-variant-numeric:tabular-nums; font-size:15px;
             color:var(--fg); }
.totals    { display:flex; gap:26px; padding-top:16px; border-top:1px solid var(--border-soft); }
.total .n  { font-family:var(--font-mono); font-variant-numeric:tabular-nums; font-size:17px;
             color:var(--fg); line-height:1.1; }
.total .k  { font-family:var(--font-mono); font-size:10.5px; letter-spacing:0.07em;
             text-transform:uppercase; color:var(--fg-muted); }
```

### Invariants the artifact states explicitly (all bind)
1. **The adherence number stays the server's** — `studied_last_14` rendered verbatim, nothing recomputed client-side (I-4).
2. **The sentence stays byte-identical** — wrapping digits in spans must leave `textContent`
   as `Studied N of the last 14 days`, so the existing assertion passes **unedited**.
3. **Silent grace (I-7)** — zero-activity days get no tooltip, no `title`, no warning copy,
   no badge, no celebration; no "missed / broken / lost" language anywhere in the markup.
4. **Test hooks survive** — `data-testid`, `data-day`, `data-level`, `data-placeholder`, the
   84-cell count, and the hide toggle + its localStorage behaviour are unchanged.

### The "pages" figure — conditional, per RFC-006
The artifact's own §"The one dependency": position saves record no ground covered, so
"pages read today" needs a per-day counter fed by words advanced. RFC-006 Cycle B:
**ship the pages figure only if that counter lands in this cycle**; otherwise the readout is
the adherence sentence + reviews total alone, and the figure defers to a follow-up.
Either way invariants 1–4 hold.

---

## B. Reading column + live progress
Source: book-workspace artifact. **Only the reading column, page rule, and topbar percentage are
in Cycle B scope** — the contents rail, four-tab dock, and route redirects are Cycle D.

### Reading surface tokens (already in `globals.css` as `[data-appearance="paper"]`)
Light: `--paper:#F4EFE5 --paper-card:#FCF9F2 --paper-ink:#27211A --paper-muted:#6F6455 --paper-rule:#E2DACA`
Dark:  `--paper:#131C22 --paper-card:#172128 --paper-ink:#D9E2E8 --paper-muted:#7F93A0 --paper-rule:#263340`
`--font-book: "Source Serif 4", "Iowan Old Style", Charter, Georgia, serif`

### The column
```
.reading { background:var(--paper); color:var(--paper-ink); overflow-y:auto; min-height:0;
           position:relative; scroll-behavior:smooth; }
@media (prefers-reduced-motion: reduce) { .reading { scroll-behavior:auto; } }

.column  { max-width:65ch; margin:0 auto; padding:40px 32px 200px; position:relative; }

.chapter-title { font-family:var(--font-book); font-size:15px; font-weight:600;
                 letter-spacing:0.06em; text-transform:uppercase; color:var(--paper-muted);
                 margin:0 0 28px; }

.column p { font-family:var(--font-book); font-size:18.5px; line-height:1.62;
            margin:0 0 1.15em; hyphens:none; }
.column p + p { text-indent:0; }
```
The generous `padding-bottom: 200px` is what stops the last paragraph sitting against the
viewport floor; the sticky-header clipping fix belongs with the scroll container, not the prose.

### Page rule (the unit made visible)
```
.page-break { display:flex; align-items:center; gap:12px; margin:2em 0 2.2em; user-select:none; }
.page-break::before, .page-break::after { content:""; flex:1; height:1px; background:var(--paper-rule); }
.page-break span { font-family:var(--font-mono); font-size:10px; letter-spacing:0.1em;
                   color:var(--paper-muted); white-space:nowrap; }
```
Markup: `<div class="page-break" aria-hidden="true"><span>p. 59</span></div>`, inserted
**after a paragraph**, never mid-paragraph. Artifact's insertion algorithm:
```js
const WORDS_PER_PAGE = 275;
let running = 0, page = FIRST_PAGE;
paragraphs.forEach((p, i) => {
  running += p.textContent.trim().split(/\s+/).length;
  if (running >= WORDS_PER_PAGE && i < paragraphs.length - 1) {
    running -= WORDS_PER_PAGE; page += 1;  /* emit rule after p */
  }
});
```
Note the carry (`running -= WORDS_PER_PAGE`, not `running = 0`) and the guard against a rule
after the final paragraph.

### Topbar live progress
```
.topbar-right { font-family:var(--font-mono); font-size:11.5px; color:var(--fg-muted); }
.pct          { color:var(--fg); font-variant-numeric:tabular-nums; }
.progress     { height:2px; background:var(--border-soft); flex:none; }
.progress i   { display:block; height:100%; background:var(--primary); transition:width 60ms linear; }
@media (prefers-reduced-motion: reduce) { .progress i { transition:none; } }
```
Artifact interpolation:
```js
const scrollable = Math.max(1, reading.scrollHeight - reading.clientHeight);
const through    = Math.min(1, reading.scrollTop / scrollable);
const wordsRead  = WORDS_BEFORE_CHAPTER + CHAPTER_WORDS * through;
const percent    = Math.round((wordsRead / TOTAL_WORDS) * 1000) / 10;
```

> **RFC-006 OVERRIDES THE ARTIFACT HERE.** The artifact renders `percent.toFixed(1)` and adds a
> "N min left" figure. RFC-006 Cycle B says **display format unchanged** — keep whatever format
> the app renders today; this cycle only makes the number track scroll continuously instead of
> jumping on save. Do not add the minutes-left figure (not in Cycle B scope).

### The authority rule (I-4-style, binding)
Client-side interpolation is **presentation only and is never persisted**. The server-computed
percent returned on position save stays authoritative: a save must not be derived from the
interpolated number, and the interpolated number must not be written anywhere durable.
