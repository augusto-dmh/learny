/**
 * D1 (unit) — `saveAnswerAsNote` turns a completed, cited panel answer into a
 * note. The anchored happy path (RA-20) captures a highlight on the first
 * citation's anchor with the first paragraph of its snippet as the quote, the
 * question (capped at 80 chars) as the title, and the answer as the body. The
 * fallback (RA-21) fires on a 409 stale capture OR an empty snippet paragraph:
 * it creates a plain note whose body carries the answer plus a jump-back link to
 * the anchor. Any other capture error propagates. `firstParagraph` is exercised
 * directly for the blank-line/trim/empty rules.
 */

import { describe, expect, it, vi } from "vitest";

import {
  firstParagraph,
  saveAnswerAsNote,
} from "../app/lib/answer-notes";
import { NoteError } from "../app/lib/notes";
import { type Citation } from "../app/lib/questions";

function citation(overrides: Partial<Citation> = {}): Citation {
  return {
    chunk_id: "c1",
    source_id: "s1",
    section_path: ["Chapter 1", "Core Idea"],
    anchor: "c1.xhtml#core-idea",
    page_span: null,
    snippet: "The first paragraph.\n\nA second paragraph.",
    score: 0.03,
    ...overrides,
  };
}

describe("firstParagraph", () => {
  it("returns the first paragraph split on a blank line", () => {
    expect(firstParagraph("First.\n\nSecond.")).toBe("First.");
  });

  it("skips leading blank paragraphs and trims the result", () => {
    expect(firstParagraph("  \n\n   Real content   \n\nmore")).toBe(
      "Real content",
    );
  });

  it("treats a whitespace-only line as a blank-line separator", () => {
    expect(firstParagraph("First.\n \t \nSecond.")).toBe("First.");
  });

  it("returns the whole text when there is no blank line", () => {
    expect(firstParagraph("Just one paragraph")).toBe("Just one paragraph");
  });

  it("returns null for empty text", () => {
    expect(firstParagraph("")).toBeNull();
  });

  it("returns null when the text is only whitespace and blank lines", () => {
    expect(firstParagraph("   \n\n  \t \n ")).toBeNull();
  });
});

describe("saveAnswerAsNote anchored capture (RA-20)", () => {
  it("captures a highlight on the first citation with the exact payload", async () => {
    const captureImpl = vi.fn().mockResolvedValue({});
    const createImpl = vi.fn();

    const result = await saveAnswerAsNote({
      sourceId: "s1",
      question: "Who wrote the first algorithm?",
      answerText: "Ada Lovelace wrote the first algorithm.",
      citations: [citation()],
      csrfToken: "csrf-xyz",
      captureImpl,
      createImpl,
    });

    expect(result).toEqual({ outcome: "anchored" });
    expect(createImpl).not.toHaveBeenCalled();
    expect(captureImpl).toHaveBeenCalledTimes(1);

    const [sourceIdArg, body, csrfArg] = captureImpl.mock.calls[0];
    expect(sourceIdArg).toBe("s1");
    expect(csrfArg).toBe("csrf-xyz");
    expect(body).toEqual({
      anchor: "c1.xhtml#core-idea",
      quote_exact: "The first paragraph.",
      title: "Who wrote the first algorithm?",
      body_markdown: "Ada Lovelace wrote the first algorithm.",
    });
  });

  it("truncates the note title to 80 characters", async () => {
    const captureImpl = vi.fn().mockResolvedValue({});
    const longQuestion = "Q".repeat(200);

    await saveAnswerAsNote({
      sourceId: "s1",
      question: longQuestion,
      answerText: "An answer.",
      citations: [citation()],
      csrfToken: "csrf",
      captureImpl,
      createImpl: vi.fn(),
    });

    const [, body] = captureImpl.mock.calls[0];
    expect(body.title).toBe("Q".repeat(80));
    expect(body.title).toHaveLength(80);
  });
});

describe("saveAnswerAsNote plain-note fallback (RA-21)", () => {
  it("falls back to a plain note with a jump-back link on a stale capture", async () => {
    const captureImpl = vi
      .fn()
      .mockRejectedValue(new NoteError("stale_capture", 409, "stale"));
    const createImpl = vi.fn().mockResolvedValue({});

    const result = await saveAnswerAsNote({
      sourceId: "s1",
      question: "A question",
      answerText: "The full answer body.",
      citations: [citation()],
      csrfToken: "csrf",
      captureImpl,
      createImpl,
    });

    expect(result).toEqual({ outcome: "plain" });
    expect(captureImpl).toHaveBeenCalledTimes(1);
    expect(createImpl).toHaveBeenCalledTimes(1);

    const [body, csrfArg] = createImpl.mock.calls[0];
    expect(csrfArg).toBe("csrf");
    expect(body.title).toBe("A question");
    expect(body.body_markdown).toBe(
      "The full answer body.\n\n[Open in book](/sources/s1/read?anchor=c1.xhtml%23core-idea)",
    );
  });

  it("goes straight to the fallback when the snippet has no non-empty paragraph", async () => {
    const captureImpl = vi.fn();
    const createImpl = vi.fn().mockResolvedValue({});

    const result = await saveAnswerAsNote({
      sourceId: "s1",
      question: "A question",
      answerText: "The answer.",
      citations: [citation({ snippet: "   \n\n  \n " })],
      csrfToken: "csrf",
      captureImpl,
      createImpl,
    });

    expect(result).toEqual({ outcome: "plain" });
    // With no quote there is nothing to bind, so capture is never attempted.
    expect(captureImpl).not.toHaveBeenCalled();
    const [body] = createImpl.mock.calls[0];
    expect(body.body_markdown).toBe(
      "The answer.\n\n[Open in book](/sources/s1/read?anchor=c1.xhtml%23core-idea)",
    );
  });
});

describe("saveAnswerAsNote error propagation", () => {
  it("rethrows a non-stale NoteError instead of falling back", async () => {
    const captureImpl = vi
      .fn()
      .mockRejectedValue(new NoteError("body_too_long", 422, "too long"));
    const createImpl = vi.fn();

    await expect(
      saveAnswerAsNote({
        sourceId: "s1",
        question: "A question",
        answerText: "The answer.",
        citations: [citation()],
        csrfToken: "csrf",
        captureImpl,
        createImpl,
      }),
    ).rejects.toBeInstanceOf(NoteError);
    expect(createImpl).not.toHaveBeenCalled();
  });

  it("rethrows a generic error", async () => {
    const captureImpl = vi
      .fn()
      .mockRejectedValue(new Error("network down"));
    const createImpl = vi.fn();

    await expect(
      saveAnswerAsNote({
        sourceId: "s1",
        question: "A question",
        answerText: "The answer.",
        citations: [citation()],
        csrfToken: "csrf",
        captureImpl,
        createImpl,
      }),
    ).rejects.toThrow("network down");
    expect(createImpl).not.toHaveBeenCalled();
  });
});
