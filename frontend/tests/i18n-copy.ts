/**
 * "No English UI copy" probe for pt-BR render tests.
 *
 * Collects the English phrases a set of catalog namespaces would put on screen
 * — the static text of every `en` message, with ICU arguments and branches cut
 * out and rich-text tags unwrapped — minus the few phrases that are the same in
 * every language (`SHARED_PHRASES`: the brand and the language endonyms). A
 * pt-BR render that still shows one of them is reading copy from somewhere
 * other than the catalog, or from a pt-BR value left in English.
 *
 * It sees rendered text only (`textContent`), so attribute copy (`aria-label`,
 * `title`) is asserted by name in the tests themselves.
 */
import { expect } from "vitest";

import en from "@/messages/en.json";

/**
 * Phrases that read the same in every locale, so finding them in a pt-BR render
 * is not a leak. Deliberately explicit: deriving it from the pt-BR catalog would
 * let a pt-BR value left in English exempt itself.
 */
export const SHARED_PHRASES = new Set(["Learny", "English", "Português (Brasil)"]);

type Catalog = { [key: string]: string | Catalog };

function messagesUnder(catalog: Catalog, namespace: string): string[] {
  const node =
    namespace === ""
      ? catalog
      : namespace
          .split(".")
          .reduce<string | Catalog | undefined>(
            (current, key) =>
              typeof current === "object" ? current[key] : undefined,
            catalog,
          );
  if (node === undefined) {
    throw new Error(`unknown catalog namespace: ${namespace}`);
  }
  if (typeof node === "string") {
    return [node];
  }
  return Object.values(node).flatMap((value) =>
    typeof value === "string" ? [value] : messagesUnder(value, ""),
  );
}

/** Remove balanced `{…}` groups (arguments, plural/select branches). */
function stripArguments(message: string): string {
  let out = "";
  let depth = 0;
  for (const char of message) {
    if (char === "{") {
      depth += 1;
      out += " ";
    } else if (char === "}") {
      depth = Math.max(0, depth - 1);
    } else if (depth === 0) {
      out += char;
    }
  }
  return out;
}

/** The static phrases of a message: argument-free runs of at least two letters. */
function phrases(message: string): string[] {
  return stripArguments(message.replace(/<\/?[A-Za-z]+>/g, ""))
    .split(/\s{2,}|[.?!…]\s*/)
    .map((part) => part.trim())
    .filter((part) => /[A-Za-z]{2,}/.test(part));
}

const rootOf = (catalog: unknown) => catalog as Catalog;

/** English phrases from `namespaces`, minus the ones every locale shares. */
export function englishPhrases(...namespaces: string[]): string[] {
  const found = namespaces
    .flatMap((namespace) => messagesUnder(rootOf(en), namespace))
    .flatMap((message) => phrases(message))
    .filter((phrase) => !SHARED_PHRASES.has(phrase));
  return [...new Set(found)];
}

/** Fail naming every English catalog phrase still present in `text`. */
export function expectNoEnglishCopy(text: string, ...namespaces: string[]): void {
  const leaked = englishPhrases(...namespaces).filter((phrase) =>
    new RegExp(`(^|[^A-Za-z])${escape(phrase)}([^A-Za-z]|$)`).test(text),
  );
  expect(leaked, "English catalog copy rendered under pt-BR").toEqual([]);
}

function escape(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
