/**
 * `saveAnswerAsNote` turns a completed, cited panel answer into a note. The
 * anchored happy path (RA-20) captures a highlight on the first citation's anchor
 * with the first paragraph of its snippet as the quote, the question (capped at 80
 * chars) as the title, and the answer as the body. The fallback (RA-21) fires on a
 * 409 stale capture OR an empty snippet paragraph — and it still captures, on the
 * same anchor with no quote, so the answer is kept and kept attached to the book
 * (P3 AC 3). Any other capture error propagates. `firstParagraph` is exercised
 * directly for the blank-line/trim/empty rules.
 */

import { describe, expect, it, vi } from "vitest";

import {
  firstParagraph,
  saveAnswerAsNote,
} from "../app/lib/answer-notes";
import { NoteError } from "../app/lib/notes";
import { type Citation } from "../app/lib/citations";

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

    const result = await saveAnswerAsNote({
      sourceId: "s1",
      question: "Who wrote the first algorithm?",
      answerText: "Ada Lovelace wrote the first algorithm.",
      citations: [citation()],
      csrfToken: "csrf-xyz",
      captureImpl,
    });

    expect(result).toEqual({ outcome: "anchored" });
    // The quoted capture bound, so there is no second, quote-less attempt.
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

  it("strips the answer's inline citation markers from the saved body", async () => {
    const captureImpl = vi.fn().mockResolvedValue({});

    await saveAnswerAsNote({
      sourceId: "s1",
      question: "Who wrote the first algorithm?",
      answerText: "Ada Lovelace wrote it.[^1] She worked with Babbage.[^2]",
      citations: [citation()],
      csrfToken: "csrf",
      captureImpl,
    });

    // The markers point at a citation list the note does not carry, so the note
    // keeps the prose and nothing else.
    const [, body] = captureImpl.mock.calls[0];
    expect(body.body_markdown).toBe(
      "Ada Lovelace wrote it. She worked with Babbage.",
    );
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
    });

    const [, body] = captureImpl.mock.calls[0];
    expect(body.title).toBe("Q".repeat(80));
    expect(body.title).toHaveLength(80);
  });
});

describe("saveAnswerAsNote section-level fallback (RA-21, P3 AC 3)", () => {
  it("still saves the answer, on the same anchor with no quote, after a stale capture", async () => {
    const captureImpl = vi
      .fn()
      .mockRejectedValueOnce(new NoteError("stale_capture", 409, "stale"))
      .mockResolvedValue({});

    const result = await saveAnswerAsNote({
      sourceId: "s1",
      question: "A question",
      answerText: "The full answer body.",
      citations: [citation()],
      csrfToken: "csrf",
      captureImpl,
    });

    expect(result).toEqual({ outcome: "section" });
    expect(captureImpl).toHaveBeenCalledTimes(2);

    // The answer is kept, and it is kept attached to where it came from.
    const [sourceIdArg, body, csrfArg] = captureImpl.mock.calls[1];
    expect(sourceIdArg).toBe("s1");
    expect(csrfArg).toBe("csrf");
    expect(body).toEqual({
      anchor: "c1.xhtml#core-idea",
      quote_exact: "",
      title: "A question",
      body_markdown: "The full answer body.",
    });
  });

  it("goes straight to the anchor-only capture when the snippet has no paragraph", async () => {
    const captureImpl = vi.fn().mockResolvedValue({});

    const result = await saveAnswerAsNote({
      sourceId: "s1",
      question: "A question",
      answerText: "The answer.",
      citations: [citation({ snippet: "   \n\n  \n " })],
      csrfToken: "csrf",
      captureImpl,
    });

    expect(result).toEqual({ outcome: "section" });
    // With no quote there is nothing to bind, so the quoted capture is skipped —
    // but the note is still created, and still anchored.
    expect(captureImpl).toHaveBeenCalledTimes(1);
    const [, body] = captureImpl.mock.calls[0];
    expect(body.quote_exact).toBe("");
    expect(body.anchor).toBe("c1.xhtml#core-idea");
    expect(body.body_markdown).toBe("The answer.");
  });
});

describe("saveAnswerAsNote error propagation", () => {
  it("rethrows a non-stale NoteError instead of falling back", async () => {
    const captureImpl = vi
      .fn()
      .mockRejectedValue(new NoteError("body_too_long", 422, "too long"));

    await expect(
      saveAnswerAsNote({
        sourceId: "s1",
        question: "A question",
        answerText: "The answer.",
        citations: [citation()],
        csrfToken: "csrf",
        captureImpl,
      }),
    ).rejects.toBeInstanceOf(NoteError);
    // A failure that is not a stale binding is not retried quote-less.
    expect(captureImpl).toHaveBeenCalledTimes(1);
  });

  it("rethrows a generic error", async () => {
    const captureImpl = vi
      .fn()
      .mockRejectedValue(new Error("network down"));

    await expect(
      saveAnswerAsNote({
        sourceId: "s1",
        question: "A question",
        answerText: "The answer.",
        citations: [citation()],
        csrfToken: "csrf",
        captureImpl,
      }),
    ).rejects.toThrow("network down");
    expect(captureImpl).toHaveBeenCalledTimes(1);
  });
});
