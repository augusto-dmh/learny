// @vitest-environment jsdom

/**
 * T5 gate (component) — post-login and post-register land on /home (HOME-17,
 * AD-150). Each auth page wires `AuthForm`'s `onAuthenticated` to
 * `router.push("/home")`; a successful submit therefore navigates there rather
 * than to the old `/account` logout surface. The router is mocked so the test
 * asserts the navigation target without a real Next.js router.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
}));

import LoginPage from "../app/(auth)/login/page";
import RegisterPage from "../app/(auth)/register/page";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const user = { id: "u1", email: "a@b.c", created_at: "now" };

afterEach(() => {
  cleanup();
  push.mockClear();
  vi.restoreAllMocks();
});

describe("auth redirects (HOME-17)", () => {
  it("redirects to /home after a successful login", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(200, user)));

    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "a@b.c" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "pw" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Log in" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/home"));
  });

  it("redirects to /home after a successful registration", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(201, user));
    vi.stubGlobal("fetch", fetchMock);

    render(<RegisterPage />);
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "a@b.c" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "pw" },
    });
    // A successful registration now includes ToS consent (DOOR-25): the
    // required checkbox gates submit and the consent rides the register body.
    fireEvent.click(screen.getByLabelText(/Terms of Service/));
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/home"));
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string).accepted_tos).toBe(true);
  });
});
