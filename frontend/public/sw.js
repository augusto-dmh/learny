/**
 * Learny service worker: offline reading for the current book (PWA row).
 *
 * One job: keep a signed-in learner's chapter and structure reads available
 * offline. Everything else — every write, every other `/api/` read, every
 * cross-origin request — passes through untouched, so no other learner's data
 * and no sensitive response is ever stored on the device.
 *
 * The cache is per user: each reader cache is named for exactly one user id
 * (`learny-reader-<uid>`), and the app tells this worker who is signed in via a
 * message (`learny:sw-user`). When the signed-in user changes — logout, or a
 * different learner on a shared device — every reader cache that does not
 * belong to the current user is deleted, so cached book data never survives an
 * account switch. Until a user id is known the worker caches nothing and
 * serves nothing from cache: a response it cannot attribute is a response it
 * does not keep.
 *
 * The pure helpers below are imported by `tests/offline-cache-policy.test.ts`
 * and exercised with fake caches/fetch — the same code the browser wires to
 * real events at the bottom of the file, with no build step and no drift.
 */

export const READER_CACHE_PREFIX = "learny-reader-";
export const MAX_READER_ENTRIES = 30;
export const USER_MESSAGE_TYPE = "learny:sw-user";

/** One chapter or structure read: the only URLs this worker caches. */
const READER_PATH = /^\/api\/sources\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/(chapter|structure)$/;

/** The reader cache name for one signed-in user. */
export function cacheNameForUser(userId) {
  return `${READER_CACHE_PREFIX}${userId}`;
}

/** The user id a reader cache name carries, or null when it is not one. */
export function userFromCacheName(name) {
  if (typeof name !== "string" || !name.startsWith(READER_CACHE_PREFIX)) {
    return null;
  }
  return name.slice(READER_CACHE_PREFIX.length);
}

/** Whether this request is one of the reader reads the worker caches. */
export function isCacheableReaderRequest(request, origin) {
  if (request.method !== "GET") {
    return false;
  }
  const url = new URL(request.url);
  if (url.origin !== origin) {
    return false;
  }
  return READER_PATH.test(url.pathname);
}

/** Cache keys beyond the entry cap, oldest first, so reads stay bounded. */
export function keysToEvict(keys, max = MAX_READER_ENTRIES) {
  if (keys.length <= max) {
    return [];
  }
  return keys.slice(0, keys.length - max);
}

/**
 * Network-first for one cacheable reader request: serve fresh and store when
 * online; fall back to the user's cache when the network is gone; with no
 * cached entry, fail with the network error itself — never placeholder text.
 */
export async function serveReaderRequest(request, currentUserId, deps) {
  const { caches, fetch, origin } = deps;
  if (currentUserId === null || !isCacheableReaderRequest(request, origin)) {
    return fetch(request);
  }
  let fresh;
  try {
    fresh = await fetch(request);
  } catch (offline) {
    const cache = await caches.open(cacheNameForUser(currentUserId));
    const cached = await cache.match(request);
    if (cached) {
      return cached;
    }
    throw offline;
  }
  if (fresh.ok) {
    const cache = await caches.open(cacheNameForUser(currentUserId));
    await cache.put(request, fresh.clone());
    await trimReaderCache(cache);
  }
  return fresh;
}

/** Drop the oldest entries past the cap, so one busy book cannot grow forever. */
export async function trimReaderCache(cache) {
  const keys = await cache.keys();
  for (const key of keysToEvict(keys)) {
    await cache.delete(key);
  }
}

/**
 * Apply a `learny:sw-user` message: adopt the user id, then delete every
 * reader cache that does not belong to them. A null user id (signed out)
 * deletes every reader cache. Returns the deleted cache names.
 */
export async function applyUserChange(userId, caches) {
  const keep = userId === null ? null : cacheNameForUser(userId);
  const deleted = [];
  for (const name of await caches.keys()) {
    if (userFromCacheName(name) === null) {
      continue;
    }
    if (name === keep) {
      continue;
    }
    await caches.delete(name);
    deleted.push(name);
  }
  return { deleted, currentUserId: userId };
}

// --- Worker wiring -----------------------------------------------------------
// Skipped everywhere except a real service worker global scope, so the module
// imports cleanly under vitest.

if (
  typeof WorkerGlobalScope !== "undefined" &&
  typeof ServiceWorkerGlobalScope !== "undefined" &&
  self instanceof ServiceWorkerGlobalScope
) {
  let currentUserId = null;

  self.addEventListener("install", () => {
    self.skipWaiting();
  });

  self.addEventListener("activate", (event) => {
    event.waitUntil(
      (async () => {
        // A fresh worker has no user id yet: drop everything it could not
        // have attributed. Caches repopulate on the next read.
        await applyUserChange(null, self.caches);
        await self.clients.claim();
      })(),
    );
  });

  self.addEventListener("message", (event) => {
    const message = event.data;
    if (!message || message.type !== USER_MESSAGE_TYPE) {
      return;
    }
    event.waitUntil(
      applyUserChange(message.userId ?? null, self.caches).then(
        (result) => {
          currentUserId = result.currentUserId;
          event.source?.postMessage({
            type: USER_MESSAGE_TYPE,
            applied: true,
            deleted: result.deleted,
          });
        },
      ),
    );
  });

  self.addEventListener("fetch", (event) => {
    const { request } = event;
    if (!isCacheableReaderRequest(request, self.location.origin)) {
      return; // Default browser fetch: writes and everything else untouched.
    }
    event.respondWith(
      serveReaderRequest(request, currentUserId, {
        caches: self.caches,
        fetch,
        origin: self.location.origin,
      }),
    );
  });
}
