import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

// Identity foundation gates. jsdom never applies external stylesheets, so the
// theme is verified the same way the prod image is: by reading the committed
// source. The WCAG check is computed, not eyeballed — the palette cannot drift
// below AA without failing this file.

const root = fileURLToPath(new URL("..", import.meta.url));
const css = readFileSync(`${root}app/globals.css`, "utf8");

/** The body of a flat top-level CSS block, e.g. `:root { ... }`. */
function cssBlock(selector: string): string {
  const start = css.indexOf(`${selector} {`);
  expect(start, `block "${selector}" exists`).toBeGreaterThanOrEqual(0);
  return css.slice(start, css.indexOf("}", start));
}

/** The raw value of `--name: value;` inside a block body. */
function token(block: string, name: string): string {
  const match = block.match(new RegExp(`--${name}:\\s*([^;]+);`));
  expect(match, `token --${name} present`).not.toBeNull();
  return (match as RegExpMatchArray)[1].trim().toUpperCase();
}

/** WCAG 2.x relative luminance of a #RRGGBB hex. */
function luminance(hex: string): number {
  const channel = (i: number) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return (
    0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5)
  );
}

/** WCAG contrast ratio between two #RRGGBB hexes. */
function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const light = cssBlock(":root");
const dark = cssBlock(".dark");

// IDF-01 AC1 — the Iron Gall palette, exact values in both modes.
const PINNED: [name: string, lightHex: string, darkHex: string][] = [
  ["background", "#F6F7F6", "#0F161B"],
  ["card", "#FFFFFF", "#172128"],
  ["popover", "#FFFFFF", "#172128"],
  ["foreground", "#1B2733", "#D9E2E8"],
  ["muted-foreground", "#5D6B76", "#7F93A0"],
  ["border", "#DDE2E4", "#263340"],
  ["primary", "#22557A", "#6FA9CC"],
  ["primary-foreground", "#F4F8FA", "#0E1A22"],
  // POL-07 — destructive is identity oxblood, hex so the AA gate can see it.
  ["destructive", "#9E3B34", "#E08D85"],
];

// IDF-03 AC1 — warm marker highlights on the cool field, both modes.
const HIGHLIGHTS: [name: string, lightHex: string, darkHex: string][] = [
  ["highlight-yellow", "#EFE3A0", "#4E4620"],
  ["highlight-cyan", "#C2DEE8", "#1F3F4A"],
  ["highlight-violet", "#D6D0EC", "#37315D"],
  ["highlight-green", "#C9DFCF", "#26412F"],
];

describe("iron gall token sweep", () => {
  it.each(PINNED)("pins --%s in both modes", (name, lightHex, darkHex) => {
    expect(token(light, name)).toBe(lightHex);
    expect(token(dark, name)).toBe(darkHex);
  });

  it("uses the near-square ledger radius", () => {
    expect(token(light, "radius")).toBe("0.25REM");
  });
});

// IDF-01 AC2 — every ink-on-background and fg-on-field pair meets WCAG AA for
// body text (>= 4.5:1) in both modes.
const AA_PAIRS: [fg: string, bg: string][] = [
  ["foreground", "background"],
  ["card-foreground", "card"],
  ["popover-foreground", "popover"],
  ["primary-foreground", "primary"],
  ["secondary-foreground", "secondary"],
  ["accent-foreground", "accent"],
  ["muted-foreground", "background"],
  ["muted-foreground", "muted"],
  // POL-07 — destructive's dominant usage is error text on the field.
  ["destructive", "background"],
  ["sidebar-foreground", "sidebar"],
  ["sidebar-primary-foreground", "sidebar-primary"],
  ["sidebar-accent-foreground", "sidebar-accent"],
];

describe.each([
  ["light", light],
  ["dark", dark],
] as const)("WCAG AA contrast (%s)", (_mode, block) => {
  it.each(AA_PAIRS)("--%s on --%s >= 4.5:1", (fg, bg) => {
    const fgHex = token(block, fg);
    const bgHex = token(block, bg);
    expect(fgHex).toMatch(/^#[0-9A-F]{6}$/);
    expect(bgHex).toMatch(/^#[0-9A-F]{6}$/);
    expect(contrast(fgHex, bgHex)).toBeGreaterThanOrEqual(4.5);
  });
});

// POL-01..03 — the chart tokens are an Iron Gall sequential ramp (the heatmap
// is their consumer), pinned in both modes. Intensity is monotonic in the
// mode-appropriate direction and the ramp top clears the non-text UI contrast
// threshold against the field.
const CHARTS: [name: string, lightHex: string, darkHex: string][] = [
  ["chart-1", "#D7E3EC", "#22384A"],
  ["chart-2", "#B3CCDD", "#2E4C63"],
  ["chart-3", "#82A9C3", "#3F6885"],
  ["chart-4", "#4F7EA3", "#5588AB"],
  ["chart-5", "#22557A", "#6FA9CC"],
];

describe("chart ramp", () => {
  it.each(CHARTS)("pins --%s in both modes", (name, lightHex, darkHex) => {
    expect(token(light, name)).toBe(lightHex);
    expect(token(dark, name)).toBe(darkHex);
  });

  it("tops the ramp at the mode's primary", () => {
    expect(token(light, "chart-5")).toBe(token(light, "primary"));
    expect(token(dark, "chart-5")).toBe(token(dark, "primary"));
  });

  // POL-02 — heatmap levels 1..4 map to --chart-2..5: darker with level in
  // light, lighter with level in dark, strictly monotonic.
  it("darkens strictly with intensity in light mode", () => {
    const ramp = ["chart-2", "chart-3", "chart-4", "chart-5"].map((name) =>
      luminance(token(light, name)),
    );
    for (let i = 1; i < ramp.length; i++) {
      expect(ramp[i]).toBeLessThan(ramp[i - 1]);
    }
  });

  it("lightens strictly with intensity in dark mode", () => {
    const ramp = ["chart-2", "chart-3", "chart-4", "chart-5"].map((name) =>
      luminance(token(dark, name)),
    );
    for (let i = 1; i < ramp.length; i++) {
      expect(ramp[i]).toBeGreaterThan(ramp[i - 1]);
    }
  });

  // POL-03 — WCAG non-text UI component threshold for the strongest cell.
  it.each([
    ["light", light],
    ["dark", dark],
  ] as const)("keeps --chart-5 >= 3:1 against --background (%s)", (_mode, block) => {
    expect(
      contrast(token(block, "chart-5"), token(block, "background")),
    ).toBeGreaterThanOrEqual(3);
  });
});

// IDF-04 — the reading-typography class must actually carry the reading
// values, not merely exist: component tests can only see class presence
// (jsdom applies no stylesheets), so the declarations are pinned here.
describe("prose-reading declarations", () => {
  const prose = cssBlock(".prose-reading");

  it("sets the serif book measure, size and leading driven by reader vars", () => {
    expect(prose).toContain("font-family: var(--font-serif);");
    // Size and leading now read the Aa-popover custom properties, falling back
    // to the pinned reading defaults (19px / 1.6) when unset (RD-06/RD-18).
    expect(prose).toContain("font-size: var(--reading-size, 19px);");
    expect(prose).toContain("line-height: var(--reading-leading, 1.6);");
    expect(prose).toContain("max-width: 65ch;");
  });

  it("keeps ragged right and hyphenation off", () => {
    expect(prose).toContain("text-align: left;");
    expect(prose).toContain("hyphens: none;");
  });
});

// IDF-05 AC1 — the Paper appearance is a reader-scoped token layer: warm
// values live only under the guarded container selector, so app chrome (and
// all of dark mode) never sees them.
describe("paper reading appearance", () => {
  const PAPER_SELECTOR = 'html:not(.dark) [data-appearance="paper"]';
  const PAPER: [name: string, hex: string][] = [
    ["background", "#F4EFE5"],
    ["card", "#FCF9F2"],
    ["popover", "#FCF9F2"],
    ["foreground", "#27211A"],
    ["muted-foreground", "#6F6455"],
    ["border", "#E2DACA"],
  ];

  it("defines the warm surface under the scoped, light-only selector", () => {
    const paper = cssBlock(PAPER_SELECTOR);
    for (const [name, hex] of PAPER) {
      expect(token(paper, name)).toBe(hex);
    }
  });

  it("keeps paper values out of the app-wide token blocks", () => {
    for (const [, hex] of PAPER) {
      expect(light).not.toContain(hex);
      expect(dark).not.toContain(hex);
    }
  });

  // POL-05 — the warm surface is a second reading ground and must hold AA on
  // its own: paper ink on every paper field it can sit on.
  it.each([
    ["foreground", "background"],
    ["foreground", "card"],
    ["foreground", "popover"],
    ["muted-foreground", "background"],
  ])("keeps paper --%s on paper --%s >= 4.5:1", (fg, bg) => {
    const paper = cssBlock(PAPER_SELECTOR);
    expect(contrast(token(paper, fg), token(paper, bg))).toBeGreaterThanOrEqual(
      4.5,
    );
  });
});

// POL-06 — highlight legibility: the inline mark keeps the prose ink
// (`color: inherit`), so the ink of every ground that can render a highlight
// must hold AA over the yellow wash of that ground's mode.
describe("highlight legibility", () => {
  const paper = cssBlock('html:not(.dark) [data-appearance="paper"]');

  it.each([
    ["light foreground", token(light, "foreground"), token(light, "highlight-yellow")],
    ["paper foreground", token(paper, "foreground"), token(light, "highlight-yellow")],
    ["dark foreground", token(dark, "foreground"), token(dark, "highlight-yellow")],
  ])("keeps %s >= 4.5:1 over the highlight wash", (_ground, ink, wash) => {
    expect(contrast(ink, wash)).toBeGreaterThanOrEqual(4.5);
  });
});

// IDF-02 AC1 — the reading serif is bound at build time with Portuguese
// diacritic coverage. RootLayout renders <html>, which Testing Library cannot
// mount, so the binding is asserted over the committed source.
describe("reading serif binding", () => {
  const layout = readFileSync(`${root}app/layout.tsx`, "utf8");

  it("self-hosts Source Serif 4 via next/font with latin coverage", () => {
    expect(layout).toMatch(
      /import \{ Source_Serif_4 \} from "next\/font\/google"/,
    );
    expect(layout).toMatch(/subsets:\s*\[\s*"latin",\s*"latin-ext"\s*\]/);
    expect(layout).toMatch(/variable:\s*"--font-source-serif"/);
  });

  it("exposes --font-serif beside the untouched Geist sans", () => {
    expect(layout).toContain('"--font-serif": "var(--font-source-serif)"');
    expect(layout).toContain('"--font-sans": "var(--font-geist-sans)"');
    expect(layout).toContain("sourceSerif.variable");
    expect(layout).toContain("GeistSans.variable");
  });

  it("bridges --font-serif into the theme so the serif utility exists", () => {
    expect(css).toContain("--font-serif: var(--font-serif);");
  });
});

describe("highlight tokens", () => {
  it.each(HIGHLIGHTS)("defines --%s in both modes", (name, lightHex, darkHex) => {
    expect(token(light, name)).toBe(lightHex);
    expect(token(dark, name)).toBe(darkHex);
  });

  it("bridges highlight tokens into the theme so utilities exist", () => {
    for (const [name] of HIGHLIGHTS) {
      expect(css).toContain(`--color-${name}: var(--${name});`);
    }
  });

  // RD-28 — the inline highlight mark paints with the identity yellow token and
  // never a raw colour, so the marker tracks the palette in both modes. jsdom
  // applies no stylesheets, so the declaration is pinned from the committed CSS.
  it("paints the inline highlight mark from the yellow token", () => {
    const mark = cssBlock(".reader-highlight");
    expect(mark).toContain("background-color: var(--highlight-yellow);");
  });

  it("keeps raw highlight hexes out of every other frontend file", () => {
    const raw = HIGHLIGHTS.flatMap(([, lightHex, darkHex]) => [
      lightHex,
      darkHex,
    ]);
    const offenders: string[] = [];
    const walk = (dir: string) => {
      for (const entry of readdirSync(dir)) {
        const path = join(dir, entry);
        if (statSync(path).isDirectory()) {
          walk(path);
          continue;
        }
        if (path.endsWith(join("app", "globals.css"))) {
          continue;
        }
        if (!/\.(tsx?|css)$/.test(entry)) {
          continue;
        }
        const text = readFileSync(path, "utf8").toUpperCase();
        if (raw.some((hex) => text.includes(hex))) {
          offenders.push(path);
        }
      }
    };
    walk(join(root, "app"));
    walk(join(root, "components"));
    expect(offenders).toEqual([]);
  });
});
