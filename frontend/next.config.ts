import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Emit a self-contained server bundle (.next/standalone) for the production
  // Docker image (AD-042): the prod stage runs `node server.js` instead of the
  // Next dev server.
  output: "standalone",
};

export default nextConfig;
