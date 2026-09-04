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
): NonNullable<StreamdownProps["rehypePlugins"]> {
  return [
    defaultRehypePlugins.raw,
    defaultRehypePlugins.sanitize,
    [
      harden,
      {
        allowedImagePrefixes: [...CHAPTER_IMAGE_PREFIXES],
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
}: {
  children: string;
  className?: string;
  origin?: string;
}) {
  return (
    <Streamdown
      className={cn(
        "size-full [&>*:first-child]:mt-0 [&>*:last-child]:mb-0",
        className,
      )}
      plugins={streamdownPlugins}
      rehypePlugins={chapterRehypePlugins(chapterOrigin(origin))}
    >
      {children}
    </Streamdown>
  );
});
