/**
 * The offline cache policy, exercised at its own level: the same module the
 * browser wires to real service-worker events (`public/sw.js`), driven with
 * fake caches and fetch. No network, no browser — jsdom-free by design.
 *
 * The invariants under test: only the reader's chapter/structure GETs are
 * cached and only into the reading user's named cache; offline serves the
 * cached chapter and fails honestly with no entry; writes, other `/api/`
 * reads and cross-origin requests pass through untouched; a user change
 * deletes every other learner's reader cache.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  applyUserChange,
  cacheNameForUser,
  isCacheableReaderRequest,
  keysToEvict,
  MAX_READER_ENTRIES,
  READER_CACHE_PREFIX,
  serveReaderRequest,
  userFromCacheName,
} from "../public/sw.js";

const ORIGIN = "https://learny.test";
const SOURCE = "0f0d1a2b-3c4d-5e6f-8a9b-0c1d2e3f4a5b";
const CHAPTER_URL = `${ORIGIN}/api/sources/${SOURCE}/chapter`;
const STRUCTURE_URL = `${ORIGIN}/api/sources/${SOURCE}/structure`;

class FakeCache {
  store = new Map<string, Response>();

  async match(request: Request): Promise<Response | undefined> {
    return this.store.get((request as Request).url);
  }

  async put(request: Request, response: Response): Promise<void> {
    this.store.set(request.url, response);
  }

  async keys(): Promise<Request[]> {
    return [...this.store.keys()].map(
      (url) => new Request(url) as unknown as Request,
    );
  }

  async delete(key: Request | string): Promise<boolean> {
    return this.store.delete(typeof key === "string" ? key : key.url);
  }
}

class FakeCaches {
  byName = new Map<string, FakeCache>();

  async open(name: string): Promise<FakeCache> {
    let cache = this.byName.get(name);
    if (!cache) {
      cache = new FakeCache();
      this.byName.set(name, cache);
    }
    return cache;
  }

  async keys(): Promise<string[]> {
    return [...this.byName.keys()];
  }

  async delete(name: string): Promise<boolean> {
    return this.byName.delete(name);
  }
}

function makeDeps(overrides: { fetch?: typeof fetch } = {}) {
  const caches = new FakeCaches();
  const fetchImpl =
    overrides.fetch ?? vi.fn(async () => new Response("fresh", { status: 200 }));
  return { caches, fetch: fetchImpl, origin: ORIGIN };
}

const request = (url: string, method = "GET") => new Request(url, { method });

describe("reader request matcher", () => {
  it("caches chapter and structure reads, with or without a query", () => {
    expect(isCacheableReaderRequest(request(CHAPTER_URL), ORIGIN)).toBe(true);
    expect(
      isCacheableReaderRequest(request(`${CHAPTER_URL}?anchor=ch1%23s2`), ORIGIN),
    ).toBe(true);
    expect(isCacheableReaderRequest(request(STRUCTURE_URL), ORIGIN)).toBe(true);
  });

  it("never caches writes, other api reads, or cross-origin requests", () => {
    expect(
      isCacheableReaderRequest(request(CHAPTER_URL, "POST"), ORIGIN),
    ).toBe(false);
    expect(
      isCacheableReaderRequest(
        request(`${ORIGIN}/api/sources/${SOURCE}/media/abc123`),
        ORIGIN,
      ),
    ).toBe(false);
    expect(
      isCacheableReaderRequest(request(`${ORIGIN}/api/conversations`), ORIGIN),
    ).toBe(false);
    expect(
      isCacheableReaderRequest(request(`${ORIGIN}/api/auth/me`), ORIGIN),
    ).toBe(false);
    expect(
      isCacheableReaderRequest(request(CHAPTER_URL), "https://other.test"),
    ).toBe(false);
  });

  it("names one reader cache per user id", () => {
    expect(cacheNameForUser("u1")).toBe(`${READER_CACHE_PREFIX}u1`);
    expect(userFromCacheName(cacheNameForUser("u1"))).toBe("u1");
    expect(userFromCacheName("learny-shell")).toBeNull();
    expect(userFromCacheName("other-prefix-u1")).toBeNull();
  });

  it("evicts oldest entries past the cap", () => {
    expect(keysToEvict(["a", "b"], 3)).toEqual([]);
    expect(keysToEvict(["a", "b", "c"], 2)).toEqual(["a"]);
    expect(keysToEvict(Array.from({ length: MAX_READER_ENTRIES + 2 }, (_, i) => `k${i}`))).toEqual([
      "k0",
      "k1",
    ]);
  });
});

describe("serving reads", () => {
  let deps: ReturnType<typeof makeDeps>;

  beforeEach(() => {
    deps = makeDeps();
  });

  it("caches chapter and structure reads in the reading user's cache", async () => {
    for (const url of [CHAPTER_URL, STRUCTURE_URL]) {
      const res = await serveReaderRequest(request(url), "u1", deps);
      expect(await res.text()).toBe("fresh");
    }
    const cache = await deps.caches.open(cacheNameForUser("u1"));
    expect(cache.store.size).toBe(2);
    expect((deps.fetch as ReturnType<typeof vi.fn>).mock.calls.length).toBe(2);
  });

  it("serves the cached chapter when the network is gone and fails honestly without one", async () => {
    const cache = await deps.caches.open(cacheNameForUser("u1"));
    await cache.put(request(CHAPTER_URL), new Response("cached chapter"));

    const offlineFetch = vi.fn(async () => {
      throw new TypeError("network down");
    });
    const served = await serveReaderRequest(request(CHAPTER_URL), "u1", {
      ...deps,
      fetch: offlineFetch as unknown as typeof fetch,
    });
    expect(await served.text()).toBe("cached chapter");

    await expect(
      serveReaderRequest(request(`${CHAPTER_URL}?anchor=ch1%23s9`), "u1", {
        ...deps,
        fetch: offlineFetch as unknown as typeof fetch,
      }),
    ).rejects.toThrow("network down");
  });

  it("caches nothing until it knows the reading user", async () => {
    const res = await serveReaderRequest(request(CHAPTER_URL), null, deps);
    expect(await res.text()).toBe("fresh");
    expect((await deps.caches.keys()).length).toBe(0);
  });

  it("passes a non-cacheable request through uncached", async () => {
    const res = await serveReaderRequest(
      request(CHAPTER_URL, "POST"),
      "u1",
      deps,
    );
    expect(await res.text()).toBe("fresh");
    expect((await deps.caches.keys()).length).toBe(0);
  });

  it("does not cache error responses", async () => {
    const failing = makeDeps({
      fetch: vi.fn(async () => new Response("nope", { status: 500 })),
    });
    await serveReaderRequest(request(CHAPTER_URL), "u1", failing);
    const cache = await failing.caches.open(cacheNameForUser("u1"));
    expect(cache.store.size).toBe(0);
  });

  it("trims the cache to the entry cap", async () => {
    const cache = await deps.caches.open(cacheNameForUser("u1"));
    for (let i = 0; i < MAX_READER_ENTRIES + 1; i += 1) {
      await serveReaderRequest(
        request(`${CHAPTER_URL}?anchor=ch1%23s${i}`),
        "u1",
        deps,
      );
    }
    expect(cache.store.size).toBe(MAX_READER_ENTRIES);
    expect(cache.store.has(`${CHAPTER_URL}?anchor=ch1%23s0`)).toBe(false);
    expect(cache.store.has(`${CHAPTER_URL}?anchor=ch1%23s30`)).toBe(true);
  });
});

describe("user change purge", () => {
  it("purges every other learner's reader cache when the user changes", async () => {
    const caches = new FakeCaches();
    await caches.open(cacheNameForUser("u1"));
    await caches.open(cacheNameForUser("u2"));
    await caches.open("learny-shell");

    const { deleted, currentUserId } = await applyUserChange("u2", caches);
    expect(currentUserId).toBe("u2");
    expect(deleted).toEqual([cacheNameForUser("u1")]);
    expect((await caches.keys()).sort()).toEqual([
      cacheNameForUser("u2"),
      "learny-shell",
    ]);

    // Logging out (null) clears every reader cache; the shell survives.
    const logout = await applyUserChange(null, caches);
    expect(logout.deleted).toEqual([cacheNameForUser("u2")]);
    expect(await caches.keys()).toEqual(["learny-shell"]);
  });

  it("re-posting the same user purges nothing", async () => {
    const caches = new FakeCaches();
    await caches.open(cacheNameForUser("u1"));
    const { deleted } = await applyUserChange("u1", caches);
    expect(deleted).toEqual([]);
    expect(await caches.keys()).toEqual([cacheNameForUser("u1")]);
  });
});
