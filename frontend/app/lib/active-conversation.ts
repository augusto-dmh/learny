/**
 * Which conversation a book's dock is currently continuing, per surface.
 *
 * The *turns* of a thread always come from the server — this module stores only
 * the pointer, so a reload knows which conversation to re-read rather than
 * replaying anything the client remembered. That makes it a device-local reader
 * preference like the reading settings (AD-125), so it lives in versioned
 * `localStorage` under `learny.active-conversation.v1`.
 *
 * The pointer is kept per (book, surface) because the dock's list is
 * mode-agnostic while the two panels are not: a whole-book Ask thread and a
 * section-scoped Teach thread can both be open in the same book, and neither
 * should be resumed into the other's panel.
 *
 * When storage is unavailable (private mode) every read is a miss and every
 * write is dropped: the reader simply starts each visit with a fresh thread,
 * which is the same state a first visit has.
 */

/** Versioned key so a future shape change can migrate forward cheaply. */
export const ACTIVE_CONVERSATION_KEY = "learny.active-conversation.v1";

type StoredPointers = Record<string, string>;

function pointerKey(sourceId: string, surface: string): string {
  return `${sourceId}:${surface}`;
}

function loadPointers(): StoredPointers {
  try {
    const raw = localStorage.getItem(ACTIVE_CONVERSATION_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const pointers: StoredPointers = {};
    for (const [key, value] of Object.entries(parsed)) {
      if (typeof value === "string" && value !== "") {
        pointers[key] = value;
      }
    }
    return pointers;
  } catch {
    return {};
  }
}

/** The conversation this book's surface is continuing, or `null` for a new one. */
export function readActiveConversation(
  sourceId: string,
  surface: string,
): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return loadPointers()[pointerKey(sourceId, surface)] ?? null;
}

/** Point a book's surface at a conversation, or clear it with `null`. */
export function writeActiveConversation(
  sourceId: string,
  surface: string,
  conversationId: string | null,
): void {
  if (typeof window === "undefined") {
    return;
  }
  const pointers = loadPointers();
  if (conversationId) {
    pointers[pointerKey(sourceId, surface)] = conversationId;
  } else {
    delete pointers[pointerKey(sourceId, surface)];
  }
  try {
    localStorage.setItem(ACTIVE_CONVERSATION_KEY, JSON.stringify(pointers));
  } catch {
    // Private mode: the pointer is simply not remembered across reloads.
  }
}
