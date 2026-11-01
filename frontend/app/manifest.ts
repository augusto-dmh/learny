import type { MetadataRoute } from "next";

/**
 * The web app manifest (installable row): served at `/manifest.webmanifest` by
 * the framework and linked from the root layout's metadata. The palette matches
 * the Iron Gall brand (`--primary` in `globals.css`); the icons live in
 * `public/icons/` — one `any` set and one `maskable` set, so Android's launcher
 * can mask the full-bleed variant without clipping the wordmark.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Learny",
    short_name: "Learny",
    description:
      "Read your books with structure, cited answers, teaching, and spaced review.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#22557A",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      {
        src: "/icons/icon-maskable-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "maskable",
      },
      {
        src: "/icons/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
