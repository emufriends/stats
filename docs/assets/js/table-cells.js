// Shared presentation rules for bucketed Elo-delta cells.
export const INSUFFICIENT_OBSERVATIONS = 1000;
export const INSUFFICIENT_DATA_TOOLTIP = 'Insufficient data (fewer than 1,000 observations).';

export function isInsufficientObservationCount(count) {
  const n = Number(count);
  return !Number.isFinite(n) || n < INSUFFICIENT_OBSERVATIONS;
}

// Signed percentage-point comparisons stay compact when their integer part
// reaches two digits; raw percentages keep their page-specific formatting.
export function formatSignedPercentAdaptive(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '\u2014';
  const decimals = Math.abs(n) >= 10 ? 1 : 2;
  const rounded = Math.abs(n) < 0.5 * 10 ** -decimals ? 0 : n;
  if (rounded === 0) return `\u00b1${rounded.toFixed(decimals)}%`;
  return `${rounded >= 0 ? '+' : '\u2212'}${Math.abs(rounded).toFixed(decimals)}%`;
}

// Elo-delta cells normally use three decimals. Extreme values are displayed
// with two decimals so the full value remains visible in narrow statistical cells.
export function formatSignedDeltaAdaptive(value, plusMinusZero = false) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '\u2014';
  const decimals = Math.abs(n) >= 10 ? 2 : 3;
  const rounded = Math.abs(n) < 0.5 * 10 ** -decimals ? 0 : n;
  if (rounded === 0 && plusMinusZero) return `\u00b1${rounded.toFixed(decimals)}`;
  return `${rounded >= 0 ? '+' : '\u2212'}${Math.abs(rounded).toFixed(decimals)}`;
}

// Backend filters use "Map 1a: Observation Tower"; dashboard header tooltips
// display the friendlier "Observation Tower (1a)" without changing API values.
export function mapTooltipLabel(fullMapName) {
  const text = String(fullMapName ?? '');
  const match = text.match(/^Map\s+([^:]+):\s*(.+)$/);
  return match ? `${match[2]} (${match[1]})` : text;
}
