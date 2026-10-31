"use client";

/**
 * Streamdown for chapter markdown only (READ-07/08/14). Same-origin book
 * figures under `/api/sources/` paint as `<img>`; Ask/Teach `MessageResponse`
 * stays on Streamdown's default harden and must not import this allowlist.
 */

import { cjk } from "@streamdown/cjk";
import { code } from "@streamdown/code";
import { math } from "@streamdown/math";
import { mermaid } from "@streamdown/mermaid";
import { memo } from "react";
import { harden } from "rehype-harden";
import { Streamdown, defaultRehypePlugins, type StreamdownProps } from "streamdown";

import { cn } from "@/lib/utils";

const streamdownPlugins = { cjk, code, math, mermaid };

const CHAPTER_IMAGE_PREFIXES = ["/api/sources/"] as const;

function chapterOrigin(explicit?: string): string {
  if (explicit) {
    return explicit;
  }
  if (typeof window === "undefined") {
    return "http://localhost";
  }
  return window.location.origin;
}

function chapterRehypePlugins(
  defaultOrigin: string,
  dataSaver = false,
): NonNullable<StreamdownProps["rehypePlugins"]> {
  return [
    defaultRehypePlugins.raw,
    defaultRehypePlugins.sanitize,
    [
      harden,
      {
        // Data saver empties the allowlist: no same-origin figure survives the
        // sanitize pass, so the browser never opens a media request.
        allowedImagePrefixes: dataSaver ? [] : [...CHAPTER_IMAGE_PREFIXES],
        allowedLinkPrefixes: ["*"],
        allowedProtocols: ["*"],
        defaultOrigin,
        allowDataImages: false,
      },
    ],
  ];
}

export const ChapterMarkdown = memo(function ChapterMarkdown({
  children,
  className,
  origin,
  dataSaver = false,
}: {
  children: string;
  className?: string;
  origin?: string;
  /**
   * Data saver (low-bandwidth row): an empty image allowlist strips book
   * figures in the sanitize pass, so a metered learner never pays for them.
   * Everything else about the markdown renders identically.
   */
  dataSaver?: boolean;
}) {
  return (
    <Streamdown
      key={dataSaver ? "saver" : "figures"}
      className={cn(
        "size-full [&>*:first-child]:mt-0 [&>*:last-child]:mb-0",
        className,
      )}
      plugins={streamdownPlugins}
      rehypePlugins={chapterRehypePlugins(chapterOrigin(origin), dataSaver)}
    >
      {children}
    </Streamdown>
  );
});
