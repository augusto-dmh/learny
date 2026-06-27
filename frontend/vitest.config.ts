import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Default test environment is `node` (proxy/transport tests). Component/logic
// tests that need a DOM opt in per file via a `// @vitest-environment jsdom`
// docblock. The React plugin enables JSX/TSX transform for those tests.
export default defineConfig({
  plugins: [react()],
  resolve: {
    // Mirror the tsconfig `@/*` path alias so component imports resolve in tests.
    alias: {
      "@": fileURLToPath(new URL("./", import.meta.url)),
    },
  },
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"],
  },
});
