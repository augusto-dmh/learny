// @vitest-environment jsdom

/**
 * The device-local pointer to the conversation each of a book's surfaces is
 * continuing. It stores an id and nothing else — the turns are always re-read
 * from the server — so the whole contract is: remember the right pointer per
 * (book, surface), and never let stored rubbish or unavailable storage stop a
 * reader from starting a thread. Every failure is a miss, not an error.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ACTIVE_CONVERSATION_KEY,
  readActiveConversation,
  writeActiveConversation,
} from "../app/lib/active-conversation";

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("the active-conversation pointer", () => {
  it("remembers a pointer per book and surface, and clears one on request", () => {
    writeActiveConversation("s1", "ask", "conv1");
    writeActiveConversation("s1", "teach", "conv2");
    writeActiveConversation("s2", "ask", "conv3");

    // The two panels of one book, and two books, never read each other's thread.
    expect(readActiveConversation("s1", "ask")).toBe("conv1");
    expect(readActiveConversation("s1", "teach")).toBe("conv2");
    expect(readActiveConversation("s2", "ask")).toBe("conv3");
    expect(readActiveConversation("s2", "teach")).toBeNull();

    // Clearing one surface leaves the others exactly as they were.
    writeActiveConversation("s1", "ask", null);
    expect(readActiveConversation("s1", "ask")).toBeNull();
    expect(readActiveConversation("s1", "teach")).toBe("conv2");
    expect(readActiveConversation("s2", "ask")).toBe("conv3");
  });

  it("reads a miss when the stored JSON is corrupt", () => {
    localStorage.setItem(ACTIVE_CONVERSATION_KEY, "{not json");

    // A reader whose storage was hand-edited or half-written starts fresh
    // instead of meeting a crash on the first render of the panel.
    expect(readActiveConversation("s1", "ask")).toBeNull();
  });

  it("ignores stored entries that are not a conversation id", () => {
    localStorage.setItem(
      ACTIVE_CONVERSATION_KEY,
      JSON.stringify({
        "s1:ask": 42,
        "s1:teach": "",
        "s2:ask": null,
        "s3:ask": "conv9",
      }),
    );

    // Only a non-empty string can be a pointer; anything else is a miss.
    expect(readActiveConversation("s1", "ask")).toBeNull();
    expect(readActiveConversation("s1", "teach")).toBeNull();
    expect(readActiveConversation("s2", "ask")).toBeNull();
    expect(readActiveConversation("s3", "ask")).toBe("conv9");
  });

  it("keeps a corrupt store from losing the pointers written after it", () => {
    localStorage.setItem(ACTIVE_CONVERSATION_KEY, "{not json");

    writeActiveConversation("s1", "ask", "conv1");
    expect(readActiveConversation("s1", "ask")).toBe("conv1");
  });

  it("drops the write, without throwing, when storage is unavailable", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("QuotaExceededError");
    });

    // Private mode: the pointer is simply not remembered across reloads, which
    // is the state a first visit has anyway.
    expect(() => writeActiveConversation("s1", "ask", "conv1")).not.toThrow();
    expect(readActiveConversation("s1", "ask")).toBeNull();
  });
});
