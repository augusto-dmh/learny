/**
 * The AI-profile client is the browser's whole view of two resources: the
 * deployment's selectable-profile catalog and the caller's stored choice. Every
 * read goes through the same-origin proxy with the session cookie; every write
 * echoes the session-bound CSRF token. Failures are typed so a caller can tell
 * an unauthenticated probe or a refused id from a transient failure, and every
 * non-OK body's readable `detail` survives verbatim.
 */

import { describe, expect, it, vi } from "vitest";

import {
  AiProfileRequestError,
  deleteAiProfileChoice,
  getAiProfileChoice,
  listAiProfiles,
  putAiProfileChoice,
  type LearnerProfile,
} from "../app/lib/ai-profiles";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const catalog: LearnerProfile[] = [
  {
    id: "house-primary",
    display_name: "House standard",
    description: "Grounded answers with verified citations.",
    grounding: "verified-spans",
    ask_enabled: true,
    teach_enabled: true,
  },
  {
    id: "house-economy",
    display_name: "Economy",
    description: "",
    grounding: "prompt-cited",
    ask_enabled: true,
    teach_enabled: false,
  },
];

describe("listAiProfiles", () => {
  it("GETs the catalog through the same-origin proxy and returns it in order", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, catalog));
    const rows = await listAiProfiles(fetchMock as unknown as typeof fetch);

    expect(rows).toHaveLength(2);
    expect(rows.map((row) => row.id)).toEqual(["house-primary", "house-economy"]);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/ai/profiles");
    expect(init.method).toBe("GET");
    expect(init.credentials).toBe("same-origin");
  });

  it("returns an empty catalog untouched (the caller renders no section at all)", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, []));
    await expect(
      listAiProfiles(fetchMock as unknown as typeof fetch),
    ).resolves.toEqual([]);
  });

  it("maps a 401 to the typed error with the fallback copy", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(401, { detail: "Unauthorized" }));
    const err = await listAiProfiles(fetchMock as unknown as typeof fetch).catch(
      (e: unknown) => e,
    );
    expect(err).toBeInstanceOf(AiProfileRequestError);
    expect((err as AiProfileRequestError).status).toBe(401);
    expect((err as AiProfileRequestError).message).toBe("Unauthorized");
  });
});

describe("getAiProfileChoice", () => {
  it("returns the stored id exactly as stored", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { profile_id: "house-economy" }),
    );
    await expect(
      getAiProfileChoice(fetchMock as unknown as typeof fetch),
    ).resolves.toEqual({ profile_id: "house-economy" });
    const [url] = fetchMock.mock.calls[0] as unknown as [string];
    expect(url).toBe("/api/me/ai-profile");
  });

  it("returns null for an unset choice", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, { profile_id: null }));
    await expect(
      getAiProfileChoice(fetchMock as unknown as typeof fetch),
    ).resolves.toEqual({ profile_id: null });
  });
});

describe("putAiProfileChoice", () => {
  it("PUTs the chosen id with the CSRF token and returns the stored choice", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { profile_id: "house-economy" }),
    );
    const stored = await putAiProfileChoice(
      "house-economy",
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    );

    expect(stored).toEqual({ profile_id: "house-economy" });
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/me/ai-profile");
    expect(init.method).toBe("PUT");
    expect(init.credentials).toBe("same-origin");
    expect(JSON.parse(init.body as string)).toEqual({ profile_id: "house-economy" });
    const headers = new Headers(init.headers);
    expect(headers.get("X-CSRF-Token")).toBe("csrf-xyz");
    expect(headers.get("content-type")).toBe("application/json");
  });

  it("surfaces the backend's honest 422 detail verbatim, with the status", async () => {
    const detail =
      "generation profile 'house-economy' is not declared by this deployment; " +
      "choose an id from GET /api/ai/profiles";
    const fetchMock = vi.fn(async () => jsonResponse(422, { detail }));
    const err = await putAiProfileChoice(
      "house-economy",
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    ).catch((e: unknown) => e);

    expect(err).toBeInstanceOf(AiProfileRequestError);
    expect((err as AiProfileRequestError).status).toBe(422);
    expect((err as AiProfileRequestError).message).toBe(detail);
  });

  it("falls back to readable copy when an error body's detail is not a string", async () => {
    // FastAPI validation errors carry `detail` as a list of error objects.
    const fetchMock = vi.fn(async () =>
      jsonResponse(422, { detail: [{ loc: ["body", "profile_id"] }] }),
    );
    const err = await putAiProfileChoice(
      "x",
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    ).catch((e: unknown) => e);

    expect(err).toBeInstanceOf(AiProfileRequestError);
    expect((err as AiProfileRequestError).status).toBe(422);
    expect((err as AiProfileRequestError).message).toBe(
      "Could not save your AI profile choice.",
    );
  });

  it("falls back to readable copy when an error body is not JSON at all", async () => {
    const fetchMock = vi.fn(
      async () => new Response("<html>gateway timeout</html>", { status: 504 }),
    );
    const err = await putAiProfileChoice(
      "x",
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    ).catch((e: unknown) => e);

    expect(err).toBeInstanceOf(AiProfileRequestError);
    expect((err as AiProfileRequestError).status).toBe(504);
    expect((err as AiProfileRequestError).message).toBe(
      "Could not save your AI profile choice.",
    );
  });
});

describe("deleteAiProfileChoice", () => {
  it("DELETEs with the CSRF token and resolves on the idempotent 204", async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    await expect(
      deleteAiProfileChoice("csrf-xyz", fetchMock as unknown as typeof fetch),
    ).resolves.toBeUndefined();

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/me/ai-profile");
    expect(init.method).toBe("DELETE");
    expect(init.credentials).toBe("same-origin");
    const headers = new Headers(init.headers);
    expect(headers.get("X-CSRF-Token")).toBe("csrf-xyz");
  });

  it("maps a failed unset to the typed error with the fallback copy", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(500, { detail: "boom" }));
    const err = await deleteAiProfileChoice(
      "csrf-xyz",
      fetchMock as unknown as typeof fetch,
    ).catch((e: unknown) => e);

    expect(err).toBeInstanceOf(AiProfileRequestError);
    expect((err as AiProfileRequestError).status).toBe(500);
    expect((err as AiProfileRequestError).message).toBe("boom");
  });
});
