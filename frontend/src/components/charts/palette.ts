// Chart color roles - see the dataviz skill (references/palette.md and
// color-formula.md). Every breakdown in this dashboard colors by message
// status (zone x status, channel x status, gender x status, ...) - status
// is STATE, not identity, so it reuses this app's existing status
// vocabulary (Badge.tsx's success/warning/danger/neutral tones expressed
// as hex) rather than a categorical ramp; there's no chart here where the
// color-coded dimension is itself an open set of identities, so no
// separate categorical palette is needed.

export const STATUS_COLORS: Record<string, string> = {
  SENT: "#93bf28", // lime-500 - success
  QUEUED: "#8b9997", // ink-faint - neutral/in-progress
  CREATED: "#8b9997",
  SUBMITTING: "#8b9997",
  RETRYING: "#d97706", // amber-600 - warning
  DEAD: "#dc2626", // red-600 - critical
  FAILED_UNCONFIRMED: "#dc2626",
  FAILED: "#dc2626",
  CANCELLED: "#5b6b68", // ink-muted - neutral/terminal
};

export function statusColor(status: string): string {
  return STATUS_COLORS[status] ?? "#8b9997";
}

// Single series (e.g. a days-active histogram) - one repeated hue, no
// legend needed (see marks-and-anatomy.md: "a single series needs no
// legend box"). Brand teal at a chart-legible step (the UI-chrome step,
// #0f3f43, fails the categorical chroma floor, but a lone repeated hue
// only needs surface contrast, which this clears easily).
export const SINGLE_SERIES_HUE = "#1f6b6b";
