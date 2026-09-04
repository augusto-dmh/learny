/**
 * The in-thread failure piece: the readable error for a turn that did not land,
 * plus a Retry control that resubmits the same question as a new turn.
 *
 * Ask and Teach compose this into the failed turn rather than growing a boolean
 * `isFailed` mode on the message. The page-level banner may still exist; this is
 * the state that lives on the turn itself.
 */

import { Button } from "@/components/ui/button";

export function FailedTurn({
  error,
  onRetry,
  retryDisabled,
}: {
  error: string;
  onRetry: () => void;
  retryDisabled: boolean;
}) {
  return (
    <div data-testid="failed-turn" className="space-y-2">
      <p className="text-sm text-destructive">{error}</p>
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={retryDisabled}
        onClick={onRetry}
      >
        Retry
      </Button>
    </div>
  );
}
