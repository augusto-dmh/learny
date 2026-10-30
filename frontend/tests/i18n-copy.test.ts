/**
 * The pt-BR render probe must be able to fail: it rejects English catalog copy,
 * accepts the Portuguese render of the same messages, and finds phrases in
 * every namespace the render tests hand it — so an empty phrase list cannot
 * turn those assertions into no-ops.
 */
import { describe, expect, it } from "vitest";

import { englishPhrases, expectNoEnglishCopy, SHARED_PHRASES } from "./i18n-copy";

const PROBED_NAMESPACES = [
  "auth",
  "common",
  "home",
  "landing",
  "library",
  "reader",
  "reader.controls",
  "shell",
];

describe("English-copy probe", () => {
  it("rejects English catalog copy in a pt-BR render", () => {
    expect(() => expectNoEnglishCopy("Sair Log out", "shell")).toThrow();
    expect(() =>
      expectNoEnglishCopy("Continue reading agora", "home"),
    ).toThrow();
  });

  it("accepts Portuguese copy and the phrases every locale shares", () => {
    expect(() =>
      expectNoEnglishCopy("Início Biblioteca Revisão Notas Conta Sair Learny", "shell"),
    ).not.toThrow();
    expect(() =>
      expectNoEnglishCopy("Idioma English Português (Brasil)", "common"),
    ).not.toThrow();
  });

  it("finds phrases in every namespace the render tests probe", () => {
    for (const namespace of PROBED_NAMESPACES) {
      expect(englishPhrases(namespace).length, namespace).toBeGreaterThan(0);
    }
  });

  it("never exempts a phrase merely because the pt-BR catalog holds it", () => {
    expect([...SHARED_PHRASES]).toEqual(["Learny", "English", "Português (Brasil)"]);
    expect(englishPhrases("shell")).toContain("Log out");
  });
});
