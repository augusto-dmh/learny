/**
 * Frozen tutor strings. Byte-match the backend constants by test, never by
 * importing Python. Trimmed equality is the wire contract (TUTOR-08, TUTOR-18,
 * TUTOR-19).
 */

export const TUTOR_OPENING_MESSAGE = "(session start)";
export const TUTOR_JUST_EXPLAIN_MESSAGE = "Just explain this.";
export const TUTOR_DONT_KNOW_MESSAGE = "I don't know.";

export function isTutorOpeningMessage(text: string): boolean {
  return text.trim() === TUTOR_OPENING_MESSAGE;
}

export function tutorCardQuestion(title: string): string {
  return `In your own words, what is "${title}" arguing?`;
}
