// @vitest-environment jsdom

/**
 * T11 gate (component) — the shared navigation pending primitives (ANSW-09).
 *
 * A link navigation reports pending through Next's `useLinkStatus`, and a
 * programmatic push reports it through the transition the hook wraps it in.
 * Either way the indicator mounts already invisible and only fades in after the
 * delay, so a cached/instant navigation unmounts it before it paints (AC3).
 *
 * `useLinkStatus` is pending only during a real App Router navigation, which
 * jsdom has none of, so the pending branch is driven by mocking that one export
 * at the `next/link` boundary; a separate test holds the real hook to its
 * contract so the mock can't drift from the installed Next.
 */

import { Suspense, use, useEffect, useState } from "react";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import {
  LinkPendingIndicator,
  PENDING_DELAY_MS,
  PendingIndicator,
  useNavigateWithTransition,
} from "../app/components/nav-pending";

const linkStatus = vi.hoisted(() => ({ pending: false }));
vi.mock("next/link", async (importOriginal) => {
  const actual = await importOriginal<typeof import("next/link")>();
  return { ...actual, useLinkStatus: () => ({ pending: linkStatus.pending }) };
});

const nav = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: nav.push }),
}));

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
    true;
});

afterEach(() => {
  cleanup();
  linkStatus.pending = false;
  nav.push.mockReset();
});

describe("PendingIndicator (ANSW-09 AC3)", () => {
  it("mounts invisible and fades in only after the delay", () => {
    render(<PendingIndicator />);

    const indicator = screen.getByTestId("nav-pending");
    // jsdom runs no CSS animations, so this pins the declared mechanism rather
    // than paint timing: the fade starts one delay late, and `fill-mode-backwards`
    // holds the from-state (`fade-in-0` → opacity 0) until it does. A navigation
    // that resolves inside the delay unmounts the indicator having shown nothing.
    expect(indicator.style.animationDelay).toBe(`${PENDING_DELAY_MS}ms`);
    expect(indicator.className).toContain("fade-in-0");
    expect(indicator.className).toContain("fill-mode-backwards");
  });

  it("is decorative, so it never renames the control it sits in", () => {
    render(<PendingIndicator />);

    expect(screen.getByTestId("nav-pending").getAttribute("aria-hidden")).toBe(
      "true",
    );
    // Hidden from the a11y tree entirely — Next's route announcer covers the
    // navigation itself.
    expect(screen.queryByRole("status")).toBeNull();
  });
});

describe("LinkPendingIndicator (ANSW-09 AC1)", () => {
  it("renders nothing while the link is not navigating", () => {
    const { container } = render(<LinkPendingIndicator />);

    expect(container.innerHTML).toBe("");
  });

  it("shows the delayed indicator while the link navigation is pending", () => {
    linkStatus.pending = true;

    render(<LinkPendingIndicator />);

    expect(screen.getByTestId("nav-pending").style.animationDelay).toBe(
      `${PENDING_DELAY_MS}ms`,
    );
  });

  it("reads the installed Next's link status shape", async () => {
    const actual = await vi.importActual<typeof import("next/link")>("next/link");

    function Probe() {
      const status = actual.useLinkStatus();
      return <span data-testid="status">{String(status.pending)}</span>;
    }

    render(
      <actual.default href="/sources">
        <Probe />
      </actual.default>,
    );

    // The real hook exposes `pending`, and with no navigation in flight it is
    // false — the state the indicator's absent branch depends on.
    expect(screen.getByTestId("status").textContent).toBe("false");
  });
});

/** Suspends forever: stands in for the route the push is loading. */
const NEVER_LOADS = new Promise<void>(() => {});

function RouteLoad() {
  use(NEVER_LOADS);
  return null;
}

function Probe({ routeLoads }: { routeLoads: boolean }) {
  const [navigating, setNavigating] = useState(false);
  const { navigate, isPending } = useNavigateWithTransition();

  // The mocked router stands in for the App Router: a push that has a route to
  // load leaves a suspended update inside the transition, which is what holds
  // the transition pending.
  useEffect(() => {
    nav.push.mockImplementation(() => {
      if (routeLoads) setNavigating(true);
    });
  }, [routeLoads]);

  return (
    <>
      <button type="button" onClick={() => navigate("/sources/s1/read")}>
        Go
      </button>
      {isPending ? <span data-testid="probe-pending" /> : null}
      <Suspense fallback={<span data-testid="probe-fallback" />}>
        {navigating ? <RouteLoad /> : null}
      </Suspense>
    </>
  );
}

describe("useNavigateWithTransition (ANSW-09 AC2)", () => {
  it("keeps the initiating control pending while the navigation is in flight", async () => {
    render(<Probe routeLoads />);

    // Awaited: the click leaves a suspended update parked inside the transition.
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Go" }));
    });

    expect(screen.getByTestId("probe-pending")).toBeTruthy();
    expect(nav.push).toHaveBeenCalledWith("/sources/s1/read");
    // A transition holds the current view instead of blanking it to a fallback.
    expect(screen.queryByTestId("probe-fallback")).toBeNull();
  });

  it("leaves no pending state behind when the navigation resolves at once", async () => {
    render(<Probe routeLoads={false} />);

    fireEvent.click(screen.getByRole("button", { name: "Go" }));

    await waitFor(() => expect(nav.push).toHaveBeenCalledTimes(1));
    expect(screen.queryByTestId("probe-pending")).toBeNull();
  });
});
