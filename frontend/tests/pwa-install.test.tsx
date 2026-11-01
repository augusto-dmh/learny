// @vitest-environment jsdom

/**
 * The installable row's static surface: the manifest declares the installable
 * shape (name, standalone, 192px/512px icons in both purposes), the document
 * links it, the service worker exists as a static asset and is registered as a
 * module, and the registrar tells the worker who is signed in — and tells it
 * again when the signed-in user changes.
 */

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import manifest from "../app/manifest";
import {
  AUTH_CHANGED_EVENT,
  notifyAuthChanged,
} from "../app/lib/auth-events";
import { ServiceWorkerRegistrar } from "../app/components/service-worker-registrar";

// Vitest starts inside `frontend/`, so the static assets resolve from there.
const ROOT = process.cwd();

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("web app manifest", () => {
  it("manifest declares the installable shape and the document links it", () => {
    const m = manifest() as unknown as Record<string, unknown>;
    expect(m.name).toBe("Learny");
    expect(m.short_name).toBe("Learny");
    expect(m.start_url).toBe("/");
    expect(m.display).toBe("standalone");

    const icons = m.icons as Array<Record<string, string>>;
    const sizes = (purpose: string) =>
      icons
        .filter((icon) => icon.purpose === purpose)
        .map((icon) => icon.sizes)
        .sort();
    expect(sizes("any")).toEqual(["192x192", "512x512"]);
    expect(sizes("maskable")).toEqual(["192x192", "512x512"]);
    for (const icon of icons) {
      expect(icon.type).toBe("image/png");
      expect(existsSync(join(ROOT, "public", icon.src))).toBe(true);
    }

    // The root layout links the manifest so browsers discover it.
    const layout = readFileSync(join(ROOT, "app", "layout.tsx"), "utf8");
    expect(layout).toContain('manifest: "/manifest.webmanifest"');
  });
});

describe("service worker registration", () => {
  it("registers the service worker module at /sw.js", () => {
    expect(existsSync(join(ROOT, "public", "sw.js"))).toBe(true);

    const worker = { postMessage: vi.fn() };
    const registration = {
      active: worker,
      waiting: undefined,
      installing: undefined,
    };
    const register = vi.fn().mockResolvedValue(registration);
    const getRegistration = vi.fn().mockResolvedValue(registration);
    Object.defineProperty(navigator, "serviceWorker", {
      value: { register, getRegistration },
      configurable: true,
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            id: "u1",
            email: "u1@learny.test",
            csrf_token: "c1",
            ai_profile_id: null,
            locale: null,
          }),
          { status: 200 },
        ),
      ),
    );

    render(<ServiceWorkerRegistrar />);

    expect(register).toHaveBeenCalledWith("/sw.js", { type: "module" });
    return waitFor(() => {
      expect(worker.postMessage).toHaveBeenCalledWith({
        type: "learny:sw-user",
        userId: "u1",
      });
    });
  });

  it("posts a null user after the signed-out broadcast so the worker purges", async () => {
    const worker = { postMessage: vi.fn() };
    const registration = { active: worker };
    const register = vi.fn().mockResolvedValue(registration);
    const getRegistration = vi.fn().mockResolvedValue(registration);
    Object.defineProperty(navigator, "serviceWorker", {
      value: { register, getRegistration },
      configurable: true,
    });
    const fetchMock = vi.fn(async () => new Response("", { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);

    render(<ServiceWorkerRegistrar />);
    await waitFor(() => {
      expect(worker.postMessage).toHaveBeenCalledWith({
        type: "learny:sw-user",
        userId: null,
      });
    });

    // A later auth change (logout) re-resolves and re-posts.
    worker.postMessage.mockClear();
    notifyAuthChanged();
    await waitFor(() => {
      expect(worker.postMessage).toHaveBeenCalledWith({
        type: "learny:sw-user",
        userId: null,
      });
    });
    expect(AUTH_CHANGED_EVENT).toBe("learny:auth-changed");
  });
});
