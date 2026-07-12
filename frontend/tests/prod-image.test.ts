import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

// B2 gate (PROD-06): the frontend ships a production image that serves a built
// Next.js app, not the dev server, and Next emits a standalone bundle.

const root = fileURLToPath(new URL("..", import.meta.url));
const nextConfig = readFileSync(`${root}next.config.ts`, "utf8");
const dockerfile = readFileSync(`${root}Dockerfile`, "utf8");

describe("frontend production image", () => {
  it("configures Next.js standalone output", () => {
    expect(nextConfig).toMatch(/output:\s*["']standalone["']/);
  });

  it("has a build stage that runs the production build", () => {
    expect(dockerfile).toMatch(/AS build/);
    expect(dockerfile).toMatch(/npm run build/);
  });

  it("has a prod stage that runs the standalone server, not the dev server", () => {
    expect(dockerfile).toMatch(/AS prod/);
    expect(dockerfile).toContain('CMD ["node", "server.js"]');
    // The prod stage must not launch the Next dev server.
    const prodStage = dockerfile.slice(dockerfile.indexOf("AS prod"));
    const prodBody = prodStage.slice(0, prodStage.indexOf("AS dev"));
    expect(prodBody).not.toMatch(/next dev|npm run dev/);
  });

  it("runs the prod server as a non-root user", () => {
    expect(dockerfile).toMatch(/USER nextjs/);
  });
});
