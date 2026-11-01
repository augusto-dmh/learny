/**
 * The one window event auth mutations broadcast (`learny:auth-changed`).
 *
 * A tiny module of its own so the auth client and the service-worker registrar
 * can both import it without a cycle: the registrar listens for the event to
 * re-resolve who is signed in and tell the worker (which then purges every
 * reader cache that does not belong to the current user); the auth client
 * dispatches it whenever the signed-in user changes on this device.
 */

export const AUTH_CHANGED_EVENT = "learny:auth-changed";

/** Broadcast that the signed-in user changed. No-op outside a browser. */
export function notifyAuthChanged(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(AUTH_CHANGED_EVENT));
  }
}
