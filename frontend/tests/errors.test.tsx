// @vitest-environment jsdom

/**
 * What a failed request reads as, in each locale.
 *
 * `useErrorMessage` picks the sentence from the error's operation and status:
 * `401`, `429`, any `5xx` and an unreachable server share one message per status
 * class whatever was being done; any other status reads as the operation's own
 * failure copy. The backend `detail` never takes part.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { useErrorMessage } from "../app/components/use-error-message";
import { ApiError, type ApiErrorStatus, type ErrorFallback } from "../app/lib/errors";
import { StreamRequestError } from "../app/lib/streaming";
import type { AppLocale } from "../i18n/config";
import en from "../messages/en.json";
import ptBR from "../messages/pt-BR.json";
import { setTestLocale } from "./setup-intl";

const CATALOGS = { en: en.errors, "pt-BR": ptBR.errors } as const;
const LOCALES: AppLocale[] = ["en", "pt-BR"];
const DETAIL = "Source not found.";

afterEach(() => {
  cleanup();
});

function Probe({ error, fallback }: { error: unknown; fallback: ErrorFallback }) {
  const errorMessage = useErrorMessage();
  return <p data-testid="message">{errorMessage(error, fallback)}</p>;
}

function shown(error: unknown, fallback: ErrorFallback = "generic"): string {
  render(<Probe error={error} fallback={fallback} />);
  const text = screen.getByTestId("message").textContent ?? "";
  cleanup();
  return text;
}

describe("useErrorMessage", () => {
  it("status classes use the shared message", () => {
    const cases: [ApiErrorStatus, keyof typeof en.errors.status][] = [
      [401, "unauthorized"],
      [429, "rateLimited"],
      [500, "server"],
      [502, "server"],
      [503, "server"],
      ["network", "network"],
    ];
    for (const locale of LOCALES) {
      setTestLocale(locale);
      const catalog = CATALOGS[locale];
      for (const [status, statusClass] of cases) {
        const text = shown(new ApiError("sourcesList", status, DETAIL));
        expect(text, `${locale} ${status}`).toBe(catalog.status[statusClass]);
        expect(text).not.toBe(catalog.operation.sourcesList);
        expect(text).not.toContain(DETAIL);
      }
    }
  });

  it("other statuses use the operation copy", () => {
    for (const locale of LOCALES) {
      setTestLocale(locale);
      const catalog = CATALOGS[locale];
      for (const status of [400, 404, 409, 422]) {
        const text = shown(new ApiError("notesSave", status, DETAIL));
        expect(text, `${locale} ${status}`).toBe(catalog.operation.notesSave);
        expect(text).not.toContain(DETAIL);
      }
    }
  });

  it("reads a value that is not an ApiError as the fallback", () => {
    setTestLocale("pt-BR");
    expect(shown(new Error("Failed to fetch"), "notesList")).toBe(
      ptBR.errors.operation.notesList,
    );
    expect(shown("boom", "generic")).toBe(ptBR.errors.generic);
    expect(shown(new Error("Answer generation failed."), "stream.generationFailed")).toBe(
      ptBR.errors.stream.generationFailed,
    );
  });

  it("an error's own operation wins over the surface's fallback", () => {
    expect(shown(new ApiError("quizUndo", 409, "Nothing to undo."), "quizDue")).toBe(
      en.errors.operation.quizUndo,
    );
  });

  it("a failed login reads as bad credentials, not an expired session", () => {
    for (const locale of LOCALES) {
      setTestLocale(locale);
      expect(shown(new ApiError("authLogin", 401, "Invalid credentials."))).toBe(
        CATALOGS[locale].operation.authLogin,
      );
      // Rate limiting on the login form still reads as the shared copy.
      expect(shown(new ApiError("authLogin", 429))).toBe(
        CATALOGS[locale].status.rateLimited,
      );
    }
  });

  it("chat guards keep their status-specific copy", () => {
    const cases: [number, keyof typeof en.errors.stream][] = [
      [403, "forbidden"],
      [404, "notFound"],
      [409, "notReady"],
      [422, "unprocessable"],
    ];
    for (const locale of LOCALES) {
      setTestLocale(locale);
      for (const [status, copy] of cases) {
        expect(shown(new StreamRequestError(status))).toBe(CATALOGS[locale].stream[copy]);
        expect(shown(new StreamRequestError(status, "conversationsStart"))).toBe(
          CATALOGS[locale].stream[copy],
        );
      }
      expect(shown(new StreamRequestError(502))).toBe(CATALOGS[locale].status.server);
    }
  });
});
