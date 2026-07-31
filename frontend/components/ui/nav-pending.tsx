"use client";

/**
 * Shared pending feedback for navigation (ANSW-09, AD-223).
 *
 * The App Router has no global router events, so pending state is per
 * navigation. Two primitives cover the two ways this app navigates:
 * `LinkPendingIndicator` reads Next's `useLinkStatus` and must therefore be
 * rendered *inside* a `<Link>`; `useNavigateWithTransition` wraps a programmatic
 * `router.push` in a transition and hands back its `isPending` so the initiating
 * control can show the same feedback. Feedback is deliberately per control — no
 * global progress bar.
 *
 * The indicator never flashes on an instant (cached, prefetched) navigation
 * because it mounts already invisible: it fades in from opacity 0
 * (`fill-mode-backwards` holds the animation's from-state during the delay) and
 * the fade only starts after `PENDING_DELAY_MS` — applied inline so that
 * constant stays the single source of truth. A navigation that resolves sooner
 * unmounts the indicator before it has painted anything.
 *
 * The indicator is decorative (`aria-hidden`): Next's route announcer already
 * announces the new page, and hiding it keeps a control's accessible name from
 * changing mid-click.
 */

import { useLinkStatus } from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useTransition } from "react";

import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

/** How long a navigation must stay pending before the indicator becomes visible. */
export const PENDING_DELAY_MS = 150;

/** The delayed-appearance spinner shared by both navigation primitives. */
export function PendingIndicator({ className }: { className?: string }) {
  return (
    <span
      data-testid="nav-pending"
      aria-hidden="true"
      style={{ animationDelay: `${PENDING_DELAY_MS}ms` }}
      className={cn(
        "inline-flex animate-in fade-in-0 fill-mode-backwards",
        className,
      )}
    >
      <Spinner className="size-3.5 text-current" />
    </span>
  );
}

/** Pending feedback for a `<Link>` navigation. Render as a child of the link. */
export function LinkPendingIndicator({ className }: { className?: string }) {
  const { pending } = useLinkStatus();
  return pending ? <PendingIndicator className={className} /> : null;
}

/**
 * Programmatic navigation that reports whether it is still in flight, so the
 * button (or list entry) that started it can show pending state.
 */
export function useNavigateWithTransition() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const navigate = useCallback(
    (href: string) => {
      startTransition(() => {
        router.push(href);
      });
    },
    [router],
  );
  return { navigate, isPending };
}
