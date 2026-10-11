/**
 * Hard-coded-string sensor: English copy cannot creep back into translated code.
 *
 * Parses every `.tsx` under `app/`, `components/` and `hooks/` with the
 * TypeScript compiler API and reports, by file and line:
 *
 * - a JSX text node holding two or more consecutive ASCII letters;
 * - a string literal (plain, or a substitution-free template in `{…}`) in a
 *   user-facing attribute: `aria-label`, `title`, `placeholder`, `alt`;
 * - in `app/lib/**.ts`, a copy-bearing string literal (letters and whitespace,
 *   i.e. a sentence rather than an operation key) passed to `new Error(`,
 *   `new ApiError(` or any other `new …Error(` constructor.
 *
 * Two lists keep it honest:
 *
 * - `ALLOWED_TEXT` / `EXEMPT_PATHS` — copy that is not interface language: the
 *   brand, keyboard key names, the operator-only eval page, and the legal pages
 *   (English with `lang="en"` until the legal pass).
 * - `PENDING_MIGRATION` — the ratchet: files whose surface has not migrated to
 *   the catalogs yet. A listed file that is already clean fails, so the list can
 *   only shrink; it is empty once every surface speaks through the catalogs.
 *
 * ## Limits
 *
 * A practical heuristic, not a proof. It cannot see: strings assembled in
 * JavaScript expressions (`cond ? "Save" : "Saved"`, a `const label = "…"` later
 * rendered), template literals with substitutions, English inside `t()`
 * arguments, copy in non-`.tsx` modules other than the `app/lib` error
 * constructors, text rendered by third-party components, single-letter text, or
 * a user-facing attribute outside the four named above. It does not judge
 * translation quality, and a key whose pt-BR value was left in English passes
 * both this test and the parity test. A manual walk of each surface in pt-BR
 * stays part of review.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

import ts from "typescript";
import { describe, expect, it } from "vitest";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const SCANNED_DIRS = ["app", "components", "hooks"];
const LIB_DIR = "app/lib";

const USER_FACING_ATTRIBUTES = new Set(["aria-label", "title", "placeholder", "alt"]);

/** Text that is not interface language, matched against the trimmed text. */
const ALLOWED_TEXT = new Set([
  // The brand renders the same in every locale.
  "Learny",
  // Keyboard key names shown in shortcut hints.
  "Esc",
  "Enter",
  "Tab",
  "Shift",
  "Ctrl",
  "Alt",
  "Cmd",
  // The reading-settings trigger is a type specimen, not a word.
  "Aa",
]);

/** Path prefixes (relative to `frontend/`, `/`-separated) outside the sensor. */
const EXEMPT_PATHS = [
  // Legal pages stay English (with lang="en") until the LGPD legal pass.
  "app/terms/",
  "app/privacy/",
  "app/copyright/",
  // The operator-only eval dashboard is not a learner surface.
  "app/(app)/dev/evals/",
  "app/components/eval-dashboard.tsx",
];

/**
 * Files not yet migrated to the catalogs. Shrinks with every surface that
 * migrates; a clean file listed here fails the test.
 */
const PENDING_MIGRATION: string[] = [
  "app/(app)/notes/page.tsx",
  "app/components/answer-phase.tsx",
  "app/components/ask-panel.tsx",
  "app/components/citations.tsx",
  "app/components/conversation-list.tsx",
  "app/components/dock-notes-panel.tsx",
  "app/components/dock-review-panel.tsx",
  "app/components/failed-turn.tsx",
  "app/components/include-notes-toggle.tsx",
  "app/components/notes/capture-popover.tsx",
  "app/components/notes/card-suggestions.tsx",
  "app/components/notes/note-card-suggestions.tsx",
  "app/components/notes/note-detail-screen.tsx",
  "app/components/notes/notes-screen.tsx",
  "app/components/save-to-note-action.tsx",
  "app/components/teach-panel.tsx",
  "components/ai-elements/inline-citation.tsx",
  "components/ai-elements/message.tsx",
  "components/ai-elements/prompt-input.tsx",
  "components/ai-elements/sources.tsx",
  "components/ui/carousel.tsx",
];

type Finding = { file: string; line: number; text: string };

const LETTERS = /[A-Za-z]{2,}/;

function looksLikeCopy(text: string): boolean {
  const trimmed = text.trim();
  return LETTERS.test(trimmed) && !ALLOWED_TEXT.has(trimmed);
}

function lineOf(source: ts.SourceFile, node: ts.Node): number {
  return source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
}

function stringValue(node: ts.Node | undefined): string | null {
  if (!node) {
    return null;
  }
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
    return node.text;
  }
  if (ts.isJsxExpression(node)) {
    return stringValue(node.expression);
  }
  return null;
}

/** Findings for a `.tsx` component source: JSX text and user-facing attributes. */
function scanComponent(file: string, code: string): Finding[] {
  const source = ts.createSourceFile(file, code, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const findings: Finding[] = [];
  const visit = (node: ts.Node) => {
    if (ts.isJsxText(node) && looksLikeCopy(node.text)) {
      findings.push({ file, line: lineOf(source, node), text: node.text.trim() });
    } else if (
      ts.isJsxAttribute(node) &&
      USER_FACING_ATTRIBUTES.has(node.name.getText(source))
    ) {
      const value = stringValue(node.initializer);
      if (value !== null && looksLikeCopy(value)) {
        findings.push({ file, line: lineOf(source, node), text: `${node.name.getText(source)}="${value}"` });
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return findings;
}

/** Findings for an `app/lib` module: sentences passed to an error constructor. */
function scanLib(file: string, code: string): Finding[] {
  const source = ts.createSourceFile(file, code, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const findings: Finding[] = [];
  const visit = (node: ts.Node) => {
    if (
      ts.isNewExpression(node) &&
      ts.isIdentifier(node.expression) &&
      /Error$/.test(node.expression.text)
    ) {
      for (const argument of node.arguments ?? []) {
        const value = stringValue(argument);
        if (value !== null && LETTERS.test(value) && /\s/.test(value.trim())) {
          findings.push({ file, line: lineOf(source, argument), text: `new ${node.expression.text}("${value}")` });
        }
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return findings;
}

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

function rel(path: string): string {
  return relative(ROOT, path).split(sep).join("/");
}

function isExempt(file: string): boolean {
  return EXEMPT_PATHS.some((prefix) => file === prefix || file.startsWith(prefix));
}

/** Every finding in the source tree, keyed by file. */
function scanTree(): Map<string, Finding[]> {
  const byFile = new Map<string, Finding[]>();
  const add = (findings: Finding[]) => {
    for (const finding of findings) {
      byFile.set(finding.file, [...(byFile.get(finding.file) ?? []), finding]);
    }
  };
  for (const dir of SCANNED_DIRS) {
    for (const path of walk(join(ROOT, dir))) {
      const file = rel(path);
      if (isExempt(file)) {
        continue;
      }
      if (file.endsWith(".tsx")) {
        add(scanComponent(file, readFileSync(path, "utf8")));
      } else if (file.startsWith(`${LIB_DIR}/`) && file.endsWith(".ts")) {
        add(scanLib(file, readFileSync(path, "utf8")));
      }
    }
  }
  return byFile;
}

function describeFindings(findings: Finding[]): string[] {
  return findings.map(({ file, line, text }) => `${file}:${line} ${text}`);
}

describe("hard-coded strings", () => {
  it("flags English JSX text and attribute literals", () => {
    const code = [
      "export function Panel() {",
      "  return (",
      "    <section aria-label=\"Reading controls\">",
      "      <p>Hello there</p>",
      "      <input placeholder={\"Search books\"} title={`Find`} alt=\"x\" />",
      "      <span>{t(\"greeting\")}</span>",
      "      <kbd>Esc</kbd> <span>Learny</span> <i>3 / 4</i>",
      "      <img alt={label} data-testid=\"cover image\" />",
      "    </section>",
      "  );",
      "}",
    ].join("\n");
    expect(describeFindings(scanComponent("app/components/panel.tsx", code))).toEqual([
      'app/components/panel.tsx:3 aria-label="Reading controls"',
      "app/components/panel.tsx:4 Hello there",
      'app/components/panel.tsx:5 placeholder="Search books"',
      'app/components/panel.tsx:5 title="Find"',
    ]);
  });

  it("flags English error literals in lib files", () => {
    const code = [
      'throw new Error("Could not load your sources.");',
      'throw new ApiError("sourcesList", res.status, detail);',
      'throw new TutorCardError(res.status, "Could not save this card.");',
      "throw new ApiError(`Upload failed for ${name}`, 500);",
      'throw new Error(message);',
      'const text = "Not an error constructor";',
    ].join("\n");
    expect(describeFindings(scanLib("app/lib/sources.ts", code))).toEqual([
      'app/lib/sources.ts:1 new Error("Could not load your sources.")',
      'app/lib/sources.ts:3 new TutorCardError("Could not save this card.")',
    ]);
  });

  it("a clean file cannot stay pending", () => {
    const findings = scanTree();
    const stale = PENDING_MIGRATION.filter((file) => !findings.has(file));
    expect(stale, "pending files that are already clean — remove them from PENDING_MIGRATION").toEqual([]);
    const sorted = [...PENDING_MIGRATION].sort();
    expect(PENDING_MIGRATION, "keep PENDING_MIGRATION sorted and unique").toEqual([...new Set(sorted)]);
  });

  it("the source tree is clean", () => {
    const pending = new Set(PENDING_MIGRATION);
    const unexpected = [...scanTree().entries()]
      .filter(([file]) => !pending.has(file))
      .flatMap(([, findings]) => describeFindings(findings));
    expect(unexpected, "English copy outside the catalogs — move it to messages/*.json").toEqual([]);
  });

  it("documents its limits", () => {
    const self = readFileSync(fileURLToPath(import.meta.url), "utf8");
    const header = self.slice(0, self.indexOf("*/"));
    expect(header).toMatch(/## Limits/);
    expect(header).toMatch(/template literals/);
    const adr = readFileSync(join(ROOT, "..", "docs/adr/0034-ui-internationalization.md"), "utf8");
    expect(adr).toMatch(/#+ Limits/);
    expect(adr).toMatch(/template literals/);
  });
});
