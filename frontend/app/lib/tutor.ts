/**
 * Frozen tutor strings. Byte-match the backend constants by test, never by
 * importing Python. Trimmed equality is the wire contract (TUTOR-08, TUTOR-18,
 * TUTOR-19).
 */

export const TUTOR_OPENING_MESSAGE = "(session start)";

export function isTutorOpeningMessage(text: string): boolean {
  return text.trim() === TUTOR_OPENING_MESSAGE;
}
