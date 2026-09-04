// @vitest-environment jsdom

/**
 * Chapter Streamdown harden (READ-07/08/11): rewritten figure markdown paints
 * as a same-origin `<img>`; hostile http(s)/data/EPUB-relative srcs are not
 * fetched; the renderer never iframes book HTML.
 */

import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ChapterMarkdown } from "../app/components/chapter-markdown";

afterEach(() => {
  cleanup();
});

const ORIGIN = "https://learny.test";
const MEDIA_SRC =
  "/api/sources/s1/media/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

function figureSrcs(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll("img")).map(
    (img) => img.getAttribute("src") ?? "",
  );
}

describe("ChapterMarkdown figures (READ-07)", () => {
  it("paints rewritten figure markdown as a same-origin img", async () => {
    const { container } = render(
      <ChapterMarkdown origin={ORIGIN}>
        {`A plate.\n\n![Engine diagram](${MEDIA_SRC})`}
      </ChapterMarkdown>,
    );

    const img = await waitFor(() => {
      const found = container.querySelector("img");
      expect(found).not.toBeNull();
      return found!;
    });

    expect(img.getAttribute("src")?.startsWith("/api/sources/")).toBe(true);
    expect(img.getAttribute("src")).toBe(MEDIA_SRC);
    expect(img.getAttribute("alt")).toBe("Engine diagram");
    expect(container.textContent).not.toContain("[Image blocked");
  });
});

describe("ChapterMarkdown blocked srcs (READ-08)", () => {
  it.each([
    ["https", "https://evil.example/x.png"],
    ["http", "http://evil.example/x.png"],
    ["data", "data:image/png;base64,iVBORw0KGgo="],
    ["EPUB-relative", "OEBPS/images/fig1.png"],
  ])("does not fetch a %s image src", async (_kind, src) => {
    const { container } = render(
      <ChapterMarkdown origin={ORIGIN}>{`![hostile](${src})`}</ChapterMarkdown>,
    );

    await waitFor(() => {
      expect(container.textContent).toContain("[Image blocked: hostile]");
    });

    expect(figureSrcs(container).some((value) => value === src)).toBe(false);
    expect(
      figureSrcs(container).some(
        (value) =>
          value.startsWith("https://evil.example") ||
          value.startsWith("http://evil.example") ||
          value.startsWith("data:"),
      ),
    ).toBe(false);
  });

  it("does not set allowDataImages on the chapter renderer", async () => {
    const { container } = render(
      <ChapterMarkdown origin={ORIGIN}>
        {"![pixel](data:image/png;base64,iVBORw0KGgo=)"}
      </ChapterMarkdown>,
    );

    await waitFor(() => {
      expect(container.querySelector("img[src^='data:']")).toBeNull();
    });
  });
});

describe("ChapterMarkdown isolation (READ-11)", () => {
  it("does not iframe book HTML and does not grant a script sandbox", async () => {
    const { container } = render(
      <ChapterMarkdown origin={ORIGIN}>
        {`<iframe src="OEBPS/chapter.xhtml" sandbox="allow-scripts allow-same-origin"></iframe>`}
      </ChapterMarkdown>,
    );

    await waitFor(() => {
      expect(container.querySelector("iframe")).toBeNull();
    });
    expect(container.querySelector("[sandbox]")).toBeNull();
  });
});
