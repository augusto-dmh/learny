/**
 * T4 gate (logic) — study client + client-timezone header (HOME-01/02/09/11).
 *
 * Verifies `clientTimezone` reads the browser's IANA zone from `Intl` and
 * degrades to `undefined` (never the string "undefined") when it cannot be
 * resolved (AD-152); `getContinueReading` GETs `/api/reading/continue` with
 * `credentials: "same-origin"`, parses the hero view on 200, and passes the
 * null empty-shape through as `null` (HOME-02) while throwing a readable error on
 * a non-OK response; and `getStudyDays` GETs `/api/study/days` with the optional
 * `window` query, attaches `X-Client-Timezone` when the zone is available and
 * omits it entirely when it is not (HOME-09), and passes the summary payload
 * (days + `studied_last_14`) through unchanged. No real network — `fetchImpl` is
 * injected.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  clientTimezone,
  getContinueReading,
  getStudyDays,
  type ContinueReadingView,
  type StudySummaryView,
} from "../app/lib/study";

const hero: ContinueReadingView = {
  source_id: "s1",
  source_title: "Ready Book",
  chapter_title: "Chapter One",
  percent: 42.5,
  updated_at: "2026-07-19T00:00:00Z",
};

const summary: StudySummaryView = {
  days: [
    { day: "2026-07-18", reviews_count: 2, reading_updates: 1 },
    { day: "2026-07-19", reviews_count: 0, reading_updates: 3 },
  ],
  studied_last_14: 12,
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function fetchMockFn(
  impl: (...args: [string, RequestInit]) => Promise<Response>,
) {
  return vi.fn<(...args: [string, RequestInit]) => Promise<Response>>(impl);
}

/** Force `Intl.DateTimeFormat` to report a fixed zone for the duration of a test. */
function stubZone(zone: string) {
  vi.spyOn(Intl, "DateTimeFormat").mockImplementation(
    () => ({ resolvedOptions: () => ({ timeZone: zone }) }) as never,
  );
}

/** Force `Intl.DateTimeFormat` to be unusable, exercising the safe fallback. */
function breakIntl() {
  vi.spyOn(Intl, "DateTimeFormat").mockImplementation(() => {
    throw new Error("Intl unavailable");
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("clientTimezone (HOME-09 / AD-152)", () => {
  it("returns the IANA zone the browser reports", () => {
    stubZone("America/Sao_Paulo");
    expect(clientTimezone()).toBe("America/Sao_Paulo");
  });

  it("returns undefined — never the string 'undefined' — when Intl is unavailable", () => {
    breakIntl();
    expect(clientTimezone()).toBeUndefined();
  });

  it("returns undefined when the resolved zone is empty rather than an empty string", () => {
    stubZone("");
    expect(clientTimezone()).toBeUndefined();
  });
});

describe("getContinueReading (HOME-01/02)", () => {
  it("GETs the continue path (no CSRF) and parses the hero view", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(200, hero));

    const result = await getContinueReading(fetchMock as unknown as typeof fetch);

    expect(result).toEqual(hero);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/reading/continue");
    expect(init.method).toBe("GET");
    expect(init.credentials).toBe("same-origin");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBeNull();

    // The fields the hero renders survive the round-trip.
    expect(result?.source_id).toBe("s1");
    expect(result?.chapter_title).toBe("Chapter One");
    expect(result?.percent).toBe(42.5);
  });

  it("passes the null empty-shape through as null (HOME-02)", async () => {
    const fetchMock = fetchMockFn(async () => jsonResponse(200, null));

    const result = await getContinueReading(fetchMock as unknown as typeof fetch);

    expect(result).toBeNull();
  });

  it("throws a readable error when unauthenticated (401)", async () => {
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(401, { detail: "Not authenticated." }),
    );

    await expect(
      getContinueReading(fetchMock as unknown as typeof fetch),
    ).rejects.toThrow("Not authenticated.");
  });
});

describe("getStudyDays (HOME-09/11)", () => {
  it("GETs the study path with the window query and the tz header, and parses the summary", async () => {
    stubZone("America/Sao_Paulo");
    const fetchMock = fetchMockFn(async () => jsonResponse(200, summary));

    const result = await getStudyDays(84, fetchMock as unknown as typeof fetch);

    expect(result).toEqual(summary);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/study/days?window=84");
    expect(init.method).toBe("GET");
    expect(init.credentials).toBe("same-origin");
    expect(new Headers(init.headers).get("X-Client-Timezone")).toBe(
      "America/Sao_Paulo",
    );

    // The read model the stats block renders survives the round-trip.
    expect(result.studied_last_14).toBe(12);
    expect(result.days[0]).toEqual({
      day: "2026-07-18",
      reviews_count: 2,
      reading_updates: 1,
    });
  });

  it("omits the window query when no window is given (server default applies)", async () => {
    stubZone("America/Sao_Paulo");
    const fetchMock = fetchMockFn(async () => jsonResponse(200, summary));

    await getStudyDays(undefined, fetchMock as unknown as typeof fetch);

    expect(fetchMock.mock.calls[0][0]).toBe("/api/study/days");
  });

  it("omits the tz header entirely — never sends 'undefined' — when the zone is unavailable", async () => {
    breakIntl();
    const fetchMock = fetchMockFn(async () => jsonResponse(200, summary));

    await getStudyDays(84, fetchMock as unknown as typeof fetch);

    const headers = new Headers(fetchMock.mock.calls[0][1].headers);
    expect(headers.has("X-Client-Timezone")).toBe(false);
    expect(headers.get("X-Client-Timezone")).not.toBe("undefined");
  });

  it("throws a readable error on a non-OK response", async () => {
    stubZone("America/Sao_Paulo");
    const fetchMock = fetchMockFn(async () =>
      jsonResponse(401, { detail: "Not authenticated." }),
    );

    await expect(
      getStudyDays(84, fetchMock as unknown as typeof fetch),
    ).rejects.toThrow("Not authenticated.");
  });
});
