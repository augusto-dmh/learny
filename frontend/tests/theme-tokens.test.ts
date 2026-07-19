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
  ["foreground", "#1B2733", "#D9E2E8"],
  ["muted-foreground", "#5D6B76", "#7F93A0"],
  ["border", "#DDE2E4", "#263340"],
  ["primary", "#22557A", "#6FA9CC"],
  ["primary-foreground", "#F4F8FA", "#0E1A22"],
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
