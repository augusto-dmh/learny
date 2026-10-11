/**
 * Catalog parity: every locale's catalog holds exactly the same message keys,
 * and each message uses the same ICU arguments (plain, `plural`, `select`,
 * `selectordinal`, and rich-text tags) in every locale. A key present in one
 * catalog and missing from the other, or a placeholder renamed in translation,
 * fails here naming the key — before a learner sees a raw key path or an
 * unfilled `{count}`.
 *
 * `en.json` is also the type source for message keys (`global.d.ts`), so a key
 * used in code but absent from `en` already fails `tsc --noEmit`; this test holds
 * the other catalogs to that key set.
 */
import { describe, expect, it } from "vitest";

import { LOCALES } from "@/i18n/config";
import en from "@/messages/en.json";
import ptBR from "@/messages/pt-BR.json";

type Catalog = { [key: string]: string | Catalog };

/** Flatten a nested catalog to `namespace.key` → message. */
function flatten(catalog: Catalog, prefix = ""): Map<string, string> {
  const out = new Map<string, string>();
  for (const [key, value] of Object.entries(catalog)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === "string") {
      out.set(path, value);
    } else {
      for (const [inner, message] of flatten(value, path)) {
        out.set(inner, message);
      }
    }
  }
  return out;
}

/**
 * The argument names and rich-text tags an ICU message uses, sorted. A small
 * recursive reader rather than a parser dependency: it understands `{name}`,
 * `{name, type, style}`, the branch bodies of `plural`/`select`/`selectordinal`,
 * `<tag>` / `</tag>`, and ICU apostrophe quoting. Unbalanced braces throw.
 */
function icuArguments(message: string): string[] {
  const names = new Set<string>();
  let i = 0;

  const readUntil = (stops: string): string => {
    const start = i;
    while (i < message.length && !stops.includes(message[i])) {
      i++;
    }
    if (i >= message.length) {
      throw new Error(`unclosed argument in: ${message}`);
    }
    return message.slice(start, i).trim();
  };

  const skipSpace = () => {
    while (i < message.length && /\s/.test(message[i])) {
      i++;
    }
  };

  const readText = (insideBranch: boolean): void => {
    while (i < message.length) {
      const ch = message[i];
      if (ch === "'") {
        const next = message[i + 1];
        if (next === "'") {
          i += 2;
        } else if (next !== undefined && "{}#<|".includes(next)) {
          const end = message.indexOf("'", i + 1);
          i = end === -1 ? message.length : end + 1;
        } else {
          i++;
        }
      } else if (ch === "{") {
        i++;
        readArgument();
      } else if (ch === "}") {
        if (insideBranch) {
          i++;
          return;
        }
        throw new Error(`unbalanced "}" in: ${message}`);
      } else if (ch === "<") {
        const tag = /^<\/?([A-Za-z][\w-]*)\s*\/?>/.exec(message.slice(i));
        if (tag) {
          names.add(`<${tag[1]}>`);
          i += tag[0].length;
        } else {
          i++;
        }
      } else {
        i++;
      }
    }
    if (insideBranch) {
      throw new Error(`unclosed branch in: ${message}`);
    }
  };

  const readArgument = (): void => {
    names.add(readUntil(",}"));
    if (message[i] === "}") {
      i++;
      return;
    }
    i++;
    const type = readUntil(",}");
    if (message[i] === "}") {
      i++;
      return;
    }
    i++;
    if (type === "plural" || type === "select" || type === "selectordinal") {
      for (;;) {
        skipSpace();
        if (message[i] === "}") {
          i++;
          return;
        }
        readUntil("{");
        i++;
        readText(true);
      }
    }
    readUntil("}");
    i++;
  };

  readText(false);
  return [...names].sort();
}

/** Every parity problem across the given catalogs, one human-readable line each. */
function parityProblems(catalogs: Record<string, Catalog>): string[] {
  const flat = Object.entries(catalogs).map(
    ([locale, catalog]) => [locale, flatten(catalog)] as const,
  );
  const allKeys = new Set(flat.flatMap(([, messages]) => [...messages.keys()]));
  const problems: string[] = [];
  for (const key of [...allKeys].sort()) {
    const present = flat.filter(([, messages]) => messages.has(key));
    for (const [locale] of flat.filter(([, messages]) => !messages.has(key))) {
      problems.push(`${key}: missing from ${locale}`);
    }
    const signatures = present.map(([locale, messages]) => {
      try {
        return [locale, icuArguments(messages.get(key)!).join(",")] as const;
      } catch (error) {
        return [locale, `unparseable (${(error as Error).message})`] as const;
      }
    });
    const distinct = new Set(signatures.map(([, signature]) => signature));
    if (distinct.size > 1) {
      const detail = signatures.map(([locale, sig]) => `${locale} {${sig}}`).join(" vs ");
      problems.push(`${key}: ICU arguments differ: ${detail}`);
    }
  }
  return problems;
}

describe("catalog parity", () => {
  it("reports a key missing from either catalog", () => {
    const problems = parityProblems({
      en: { home: { title: "Home", only_en: "x" } },
      "pt-BR": { home: { title: "Início", only_pt: "y" } },
    });
    expect(problems).toEqual([
      "home.only_en: missing from pt-BR",
      "home.only_pt: missing from en",
    ]);
    // A whole namespace missing reports every key under it.
    expect(parityProblems({ en: { a: { b: "x" } }, "pt-BR": {} })).toEqual([
      "a.b: missing from pt-BR",
    ]);
  });

  it("reports mismatched ICU arguments", () => {
    const plain = parityProblems({
      en: { k: "Hello {name}" },
      "pt-BR": { k: "Olá {nome}" },
    });
    expect(plain).toHaveLength(1);
    expect(plain[0]).toMatch(/^k: ICU arguments differ/);

    const plural = parityProblems({
      en: { k: "{count, plural, one {# book} other {# books}}" },
      "pt-BR": { k: "{total, plural, one {# livro} other {# livros}}" },
    });
    expect(plural).toHaveLength(1);
    expect(plural[0]).toMatch(/^k: /);

    const select = parityProblems({
      en: { k: "{kind, select, a {A {x}} other {B}}" },
      "pt-BR": { k: "{kind, select, a {A {y}} other {B}}" },
    });
    expect(select).toHaveLength(1);

    const tags = parityProblems({
      en: { k: "Signed in as <strong>{email}</strong>" },
      "pt-BR": { k: "Conectado como {email}" },
    });
    expect(tags).toHaveLength(1);

    // Same arguments in a different order and translated branch text is parity.
    expect(
      parityProblems({
        en: { k: "{a} and {b}, {n, plural, one {# item} other {# items}}" },
        "pt-BR": { k: "{n, plural, one {# item} other {# itens}}: {b} e {a}" },
      }),
    ).toEqual([]);
  });

  it("the shipped catalogs are in parity", () => {
    const catalogs = { en, "pt-BR": ptBR } as Record<string, Catalog>;
    expect(Object.keys(catalogs).sort()).toEqual([...LOCALES].sort());
    expect(parityProblems(catalogs)).toEqual([]);
  });
});
