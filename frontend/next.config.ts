import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Emit a self-contained server bundle (.next/standalone) for the production
  // Docker image (AD-042): the prod stage runs `node server.js` instead of the
  // Next dev server.
  output: "standalone",
};

// Locale + catalog come from `i18n/request.ts` (cookie → Accept-Language → en).
const withNextIntl = createNextIntlPlugin();

export default withNextIntl(nextConfig);
