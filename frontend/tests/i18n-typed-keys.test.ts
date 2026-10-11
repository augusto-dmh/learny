import { execFileSync } from "node:child_process";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const root = fileURLToPath(new URL("..", import.meta.url));
const scratch = `${root}.typecheck-scratch`;

/** Type-check one snippet against the real project config; returns tsc's output. */
function typecheck(snippet: string): { ok: boolean; output: string } {
  rmSync(scratch, { recursive: true, force: true });
  mkdirSync(scratch, { recursive: true });
  try {
    writeFileSync(`${scratch}/snippet.tsx`, snippet);
    writeFileSync(
      `${scratch}/tsconfig.json`,
      JSON.stringify({
        extends: "../tsconfig.json",
        compilerOptions: { incremental: false, noEmit: true, plugins: [] },
        include: ["../global.d.ts", "../next-env.d.ts", "./snippet.tsx"],
        exclude: ["../node_modules"],
      }),
    );
    execFileSync("npx", ["tsc", "-p", `${scratch}/tsconfig.json`], {
      cwd: root,
      encoding: "utf8",
      stdio: "pipe",
    });
    return { ok: true, output: "" };
  } catch (error) {
    const failure = error as { stdout?: string; stderr?: string };
    return { ok: false, output: `${failure.stdout ?? ""}${failure.stderr ?? ""}` };
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
}

const SNIPPET = (key: string) => `
import { useTranslations } from "next-intl";
export function Probe() {
  const t = useTranslations("account");
  return t(${JSON.stringify(key)});
}
`;

describe("typed message keys", () => {
  it("tsc rejects a key missing from en", () => {
    const missing = typecheck(SNIPPET("thisKeyIsNotInTheCatalog"));
    expect(missing.ok).toBe(false);
    expect(missing.output).toContain("snippet.tsx");
    expect(missing.output).toContain("thisKeyIsNotInTheCatalog");
  }, 120_000);

  it("tsc accepts a key that exists in en", () => {
    const present = typecheck(SNIPPET("logout"));
    expect(present.output).toBe("");
    expect(present.ok).toBe(true);
  }, 120_000);
});
