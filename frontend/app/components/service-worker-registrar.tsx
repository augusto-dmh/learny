"use client";

/**
 * Registers the service worker and keeps it told who is signed in.
 *
 * Mounted once from the root layout. Two responsibilities, both private-data
 * safety before convenience:
 *
 * 1. Register `/sw.js` (module type) once per page load.
 * 2. After registering and after every `learny:auth-changed` broadcast, resolve
 *    the auth state and post `learny:sw-user` to the worker with the signed-in
 *    user's id — or null. The worker names each reader cache for exactly one
 *    user and deletes every other reader cache on the message, so a logout or
 *    a different learner on a shared device leaves no cached book data behind.
 *
 * Registration failures are swallowed by design: the app is fully usable
 * without a service worker, and an install-blocked browser must not surface
 * errors into the UI.
 */

import { useEffect } from "react";

import { AUTH_CHANGED_EVENT } from "@/app/lib/auth-events";
import { fetchAuthState } from "@/app/lib/auth";

export function ServiceWorkerRegistrar() {
  useEffect(() => {
    const registration = navigator.serviceWorker;
    if (!registration) {
      return;
    }

    let cancelled = false;

    const postUser = async () => {
      try {
        const state = await fetchAuthState();
        if (cancelled) {
          return;
        }
        const userId = state.authenticated ? state.user.id : null;
        const reg = await registration.getRegistration();
        const worker = reg?.active ?? reg?.waiting ?? reg?.installing;
        // Always posted, never deduped: the worker's own attribution is lost on
        // every service-worker update (its activate wipes what it cannot
        // attribute), so a re-post is the only way it relearns the current user.
        worker?.postMessage({ type: "learny:sw-user", userId });
      } catch {
        // A failed auth probe must never break the page; the worker simply
        // keeps its previous attribution until the next broadcast.
      }
    };

    void registration
      .register("/sw.js", { type: "module" })
      .then(postUser)
      .catch(() => {});

    window.addEventListener(AUTH_CHANGED_EVENT, postUser);
    return () => {
      cancelled = true;
      window.removeEventListener(AUTH_CHANGED_EVENT, postUser);
    };
  }, []);

  return null;
}
