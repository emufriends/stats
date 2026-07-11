// Shared presentation rules for bucketed Elo-delta cells.
export const INSUFFICIENT_OBSERVATIONS = 1000;
export const INSUFFICIENT_DATA_TOOLTIP = 'Insufficient data (fewer than 1,000 observations).';

export function isInsufficientObservationCount(count) {
  const n = Number(count);
  return !Number.isFinite(n) || n < INSUFFICIENT_OBSERVATIONS;
}
