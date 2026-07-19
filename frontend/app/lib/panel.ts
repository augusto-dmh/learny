/**
 * Shared reader side-panel contracts.
 *
 * A selection verb the reader hands to the Ask panel: a one-tap `explain` (the
 * panel auto-submits a fixed template around the quote) or an `ask` (the quote
 * attaches as context that rides along with the next typed question). Homed in
 * `lib` so the panel, its shell, and the chapter reader share the type without
 * coupling to any one component's module.
 */
export type PendingPanelRequest = {
  kind: "explain" | "ask";
  quote: string;
  anchor: string;
};
