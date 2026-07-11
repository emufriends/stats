const COLORS = {
  posStrong: '#4caf72',
  posMid: '#8bc78a',
  posWeak: '#b8dbb5',
  neutral: '#7a9e80',
  negWeak: '#e8b9a0',
  negMid: '#d97c5a',
  negStrong: '#c0432a',
  eloLow: '#2a5a5a',
  eloMid: '#2a8a7a',
  eloHigh: '#4acfb0',
  prLow: '#2a4a6a',
  prMid: '#3a7abf',
  prHigh: '#6bb5f0',
};

function clamp(value, min = 0, max = 1) {
  return Math.max(min, Math.min(max, value));
}

function rgb(hex) {
  const value = hex.replace('#', '');
  return {
    r: parseInt(value.slice(0, 2), 16),
    g: parseInt(value.slice(2, 4), 16),
    b: parseInt(value.slice(4, 6), 16),
  };
}

function mixHex(lowHex, highHex, amount) {
  const low = rgb(lowHex);
  const high = rgb(highHex);
  const t = clamp(amount);
  const channel = key => Math.round(low[key] + (high[key] - low[key]) * t);
  return `rgb(${channel('r')}, ${channel('g')}, ${channel('b')})`;
}

export function colorFromStops(raw, stops, fallback = 'var(--text-muted)') {
  const value = Number(raw);
  if (!Number.isFinite(value) || !Array.isArray(stops) || !stops.length) return fallback;
  if (value <= stops[0][0]) return stops[0][1];
  if (value >= stops.at(-1)[0]) return stops.at(-1)[1];
  for (let index = 1; index < stops.length; index += 1) {
    const [highValue, highColor] = stops[index];
    if (value > highValue) continue;
    const [lowValue, lowColor] = stops[index - 1];
    return mixHex(lowColor, highColor, (value - lowValue) / (highValue - lowValue));
  }
  return stops.at(-1)[1];
}

export function deltaColor(value) {
  return zeroAnchoredDeltaColor(value, -2, 2);
}

export function cappedNumericRange(rows, valueForRow, floor = -2, ceiling = 2) {
  const values = rows
    .map(valueForRow)
    .filter(value => value !== null && value !== undefined && value !== '')
    .map(Number)
    .filter(Number.isFinite)
    .map(value => clamp(value, floor, ceiling));
  return {
    min: values.length ? Math.min(...values) : null,
    max: values.length ? Math.max(...values) : null,
  };
}

export function numericRange(rows, valueForRow) {
  const values = rows
    .map(valueForRow)
    .filter(value => value !== null && value !== undefined && value !== '')
    .map(Number)
    .filter(Number.isFinite);
  return {
    min: values.length ? Math.min(...values) : null,
    max: values.length ? Math.max(...values) : null,
  };
}

export function normalizeToRange(value, min, max) {
  if ([value, min, max].some(item => item === null || item === undefined || item === '')) return null;
  const number = Number(value);
  const low = Number(min);
  const high = Number(max);
  if (![number, low, high].every(Number.isFinite)) return null;
  if (high === low) return 0.5;
  return clamp((number - low) / (high - low));
}

export function playrateColor(value, min, max) {
  const t = normalizeToRange(value, min, max);
  if (t === null) return 'var(--text-muted)';
  return colorFromStops(t, [
    [0, COLORS.prLow],
    [0.5, COLORS.prMid],
    [1, COLORS.prHigh],
  ]);
}

// Frequency cells use a stable 0–50% blue domain so unusually common values
// saturate without changing the meaning of the scale from table to table.
export function frequencyColor(value, cap = 50) {
  return playrateColor(value, 0, cap);
}

export function relativeEloColor(value, min, max) {
  const t = normalizeToRange(value, min, max);
  if (t === null) return 'var(--text-muted)';
  return colorFromStops(t, [
    [0, COLORS.eloLow],
    [0.5, COLORS.eloMid],
    [1, COLORS.eloHigh],
  ]);
}

export function divergingColor(normalized) {
  return colorFromStops(clamp(Number(normalized)), [
    [0, COLORS.negStrong],
    [0.25, COLORS.negMid],
    [0.42, COLORS.negWeak],
    [0.5, COLORS.neutral],
    [0.58, COLORS.posWeak],
    [0.75, COLORS.posMid],
    [1, COLORS.posStrong],
  ], COLORS.neutral);
}

export function divergingRangeColor(value, min, max, lowerIsBetter = false) {
  const normalized = normalizeToRange(value, min, max);
  if (normalized === null) return 'var(--text-muted)';
  return divergingColor(lowerIsBetter ? 1 - normalized : normalized);
}

export function deltaRangeColor(value, min, max) {
  return zeroAnchoredDeltaColor(value, min, max);
}

function zeroAnchoredDeltaColor(value, min, max) {
  if ([value, min, max].some(item => item === null || item === undefined || item === '')) {
    return 'var(--text-muted)';
  }
  const low = clamp(Number(min), -2, 2);
  const high = clamp(Number(max), -2, 2);
  const number = clamp(clamp(Number(value), -2, 2), low, high);
  if (![number, low, high].every(Number.isFinite)) return 'var(--text-muted)';
  if (number === 0 || low === high) return COLORS.neutral;
  if (number < 0) {
    const negativeEnd = Math.min(low, 0);
    if (negativeEnd === 0) return COLORS.neutral;
    return divergingColor(0.5 * ((number - negativeEnd) / -negativeEnd));
  }
  const positiveEnd = Math.max(high, 0);
  if (positiveEnd === 0) return COLORS.neutral;
  return divergingColor(0.5 + 0.5 * (number / positiveEnd));
}

function zeroAnchoredColor(value, min, max, lowColor, zeroColor, highColor) {
  if ([value, min, max].some(item => item === null || item === undefined || item === '')) {
    return 'var(--text-muted)';
  }
  const low = clamp(Number(min), -2, 2);
  const high = clamp(Number(max), -2, 2);
  const number = clamp(clamp(Number(value), -2, 2), low, high);
  if (![number, low, high].every(Number.isFinite)) return 'var(--text-muted)';
  if (number === 0 || low === high) return zeroColor;
  if (number < 0) {
    const negativeEnd = Math.min(low, 0);
    if (negativeEnd === 0) return zeroColor;
    return mixHex(lowColor, zeroColor, (number - negativeEnd) / -negativeEnd);
  }
  const positiveEnd = Math.max(high, 0);
  if (positiveEnd === 0) return zeroColor;
  return mixHex(zeroColor, highColor, number / positiveEnd);
}

export function synergyRangeColor(value, min, max) {
  return zeroAnchoredColor(value, min, max, '#ff6027', '#be8d35', '#7cba43');
}

export function orangeGreenColor(normalized) {
  return mixHex('#ff6027', '#7cba43', clamp(Number(normalized)));
}

export function orangeGreenRangeColor(value, min, max) {
  const t = normalizeToRange(value, min, max);
  return t === null ? 'var(--text-muted)' : orangeGreenColor(t);
}

export function violetRangeColor(value, min, max) {
  const t = normalizeToRange(value, min, max);
  if (t === null) return 'var(--text-muted)';
  return colorFromStops(t, [
    [0, '#6f5aa6'],
    [0.5, '#9b72cf'],
    [1, '#c59af2'],
  ]);
}

export function greenIntensityColor(normalized, withAlpha = false) {
  const t = clamp(Number(normalized));
  const color = mixHex('#628f72', '#78e38f', t);
  if (!withAlpha) return color;
  const channels = color.match(/\d+/g) || [98, 143, 114];
  return `rgba(${channels.join(', ')}, ${(0.78 + t * 0.22).toFixed(3)})`;
}

export function greenIntensityRangeColor(value, min, max, withAlpha = false) {
  const t = normalizeToRange(value, min, max);
  return t === null ? 'var(--text-muted)' : greenIntensityColor(t, withAlpha);
}

export function cssColorRgb(color) {
  const channels = color.match(/\d+/g);
  if (channels?.length >= 3) return channels.slice(0, 3).join(',');
  const parsed = rgb(color);
  return `${parsed.r},${parsed.g},${parsed.b}`;
}
