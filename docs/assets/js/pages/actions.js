import {
  cappedNumericRange,
  deltaRangeColor,
  frequencyColor,
  numericRange,
  orangeGreenRangeColor,
  violetRangeColor,
} from '../color-scales.js?v=20260711-1';
import {
  INSUFFICIENT_DATA_TOOLTIP,
  formatSignedDeltaAdaptive,
  formatSignedPercentAdaptive,
  isInsufficientObservationCount,
  mapTooltipLabel,
} from '../table-cells.js?v=20260712-4';
import { loadStats } from '../snapshot-cache.js?v=20260713-1';

export const id = 'actions';
export const title = 'Actions';
export const navLabel = 'Actions';

const API_URL = 'https://europe-west1-ark-nova-stats-dashboard.cloudfunctions.net/get-card-stats';
const SNAPSHOT_ROOT = 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/actions';
const MAPS = [
  ['1a', 'map_1a', 'Map 1a: Observation Tower'], ['2a', 'map_2a', 'Map 2a: Outdoor Areas'],
  ['3a', 'map_3a', 'Map 3a: Silver Lake'], ['4a', 'map_4a', 'Map 4a: Commercial Harbor'],
  ['5a', 'map_5a', 'Map 5a: Park Restaurant'], ['6a', 'map_6a', 'Map 6a: Research Institute'],
  ['7a', 'map_7a', 'Map 7a: Ice Cream Parlors'], ['8a', 'map_8a', 'Map 8a: Hollywood Hills'],
  ['9', 'map_9', 'Map 9: Geographical Zoo'], ['10', 'map_10', 'Map 10: Rescue Station'],
  ['11', 'map_11', 'Map 11: Caves'], ['12', 'map_12', 'Map 12: Artificial Intelligence'],
  ['13', 'map_13', 'Map 13: Drawing Board'], ['14', 'map_14', 'Map 14: Lagoon'],
  ['T1', 'map_t1', 'Map T1: Tournament 1'],
];

export const mainHtml = `
  <div class="main-header sponsor-endgames-main-header actions-main-header">
    <div class="actions-header-left">
      <button type="button" class="actions-transpose-btn is-hidden" id="actionsTransposeBtn"
        onclick="toggleActionsOrderTranspose()" aria-pressed="false"
        aria-label="Swap upgrade-order rows and columns" title="Swap rows and columns">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 7h13m0 0-3-3m3 3-3 3M20 17H7m0 0 3-3m-3 3 3 3"/>
        </svg>
      </button>
      <div class="table-meta" id="tableMeta"></div>
    </div>
    <div class="build-switches">
      <div class="maps-h2h-mode actions-compare-mode" role="group" aria-label="Actions comparison mode">
        <button type="button" class="active" data-compare="raw" onclick="setActionsCompareMode('raw')">Raw</button>
        <button type="button" data-compare="average" onclick="setActionsCompareMode('average')">vs. avg</button>
      </div>
      <div class="maps-h2h-mode actions-mode" role="group" aria-label="Actions metric">
        <button type="button" class="active" data-mode="delta" onclick="setActionsMode('delta')">Elo &Delta;</button>
        <button type="button" data-mode="frequency" onclick="setActionsMode('frequency')">Frequency</button>
      </div>
    </div>
  </div>
  <div class="attributes-bar endgames-tabs-bar">
    <div class="attributes-bar-header endgames-tabs-header">
      <div class="endgames-tabs actions-tabs" role="tablist" aria-label="Actions views">
        <button class="endgames-tab active" data-view="starting_position" onclick="setActionsView('starting_position')">Starting position</button>
        <button class="endgames-tab" data-view="upgrades" onclick="setActionsView('upgrades')">Upgrades</button>
        <button class="endgames-tab" data-view="upgrade_order" onclick="setActionsView('upgrade_order')">Upgrade order</button>
        <button class="endgames-tab" data-view="upgrades_by_map" onclick="setActionsView('upgrades_by_map')">Upgrades by map</button>
      </div>
    </div>
  </div>
  <div id="actionsContent"></div>`;

export const sidebarHtml = `
  <div class="sidebar-header"><span class="sidebar-title">Filters</span><div style="display:flex;align-items:center;gap:6px;">
    <button class="reset-btn" onclick="resetFilters()">Reset</button>
    <button class="sidebar-close-btn" onclick="toggleSidebar()" title="Close filters">x</button>
  </div></div>
  <hr class="divider" />
  <div class="filter-group"><span class="filter-label">Player ELO</span><div class="range-row">
    <input class="range-input" type="number" id="playerEloMin" placeholder="Min" value="300" min="0" />
    <input class="range-input" type="number" id="playerEloMax" placeholder="Max" min="0" />
  </div></div>
  <div class="filter-group"><span class="filter-label">Opponent ELO</span><div class="range-row">
    <input class="range-input" type="number" id="opponentEloMin" placeholder="Min" value="300" min="0" />
    <input class="range-input" type="number" id="opponentEloMax" placeholder="Max" min="0" />
  </div></div>
  <hr class="divider" />
  <div class="filter-group"><div style="display:flex;align-items:baseline;gap:6px;margin-bottom:8px;">
    <span class="filter-label" style="margin-bottom:0">Maps</span>
    <span class="map-select-all-none">(<span class="map-toggle-link" onclick="selectAllMaps()">all</span> / <span class="map-toggle-link" onclick="selectNoneMaps()">none</span>)</span>
  </div><div class="chip-grid" id="mapChips"></div></div>
  <hr class="divider" />
  <div class="filter-group"><span class="filter-label">Date Range</span>
    <input class="date-input" type="text" id="dateFrom" value="2025-01-01" placeholder="yyyy-mm-dd" />
    <input class="date-input" type="text" id="dateTo" placeholder="yyyy-mm-dd" />
  </div>
  <hr class="divider" />
  <div class="filter-action-stack"><button class="apply-btn" onclick="applyFiltersFromSidebar()">Apply filters</button></div>`;

let mounted = false;
let token = 0;
let isMW = 1;
let view = 'starting_position';
let mode = 'delta';
let compareMode = 'raw';
let orderTransposed = false;
let rows = [];
let selectedMaps = MAPS.map(([, , full]) => full);

export function mount({ dataset = 1 } = {}) {
  mounted = true; token += 1; isMW = Number(dataset) === 0 ? 0 : 1;
  view = 'starting_position'; mode = 'delta'; compareMode = 'raw'; orderTransposed = false; rows = [];
  selectedMaps = MAPS.map(([, , full]) => full);
  Object.assign(window, { setActionsView, setActionsMode, setActionsCompareMode, toggleActionsOrderTranspose, resetFilters, applyFiltersFromSidebar, selectAllMaps, selectNoneMaps, toggleActionsMap });
  renderMapChips(); syncControls(); loadData(token);
}
export function unmount() { mounted = false; token += 1; }
export function setDataset(value) { isMW = Number(value) === 0 ? 0 : 1; loadData(++token); }

function setActionsView(next) {
  view = ['starting_position', 'upgrades', 'upgrade_order', 'upgrades_by_map'].includes(next) ? next : 'starting_position';
  mode = 'delta'; compareMode = 'raw'; syncControls(); loadData(++token);
}
function setActionsMode(next) { mode = next === 'frequency' ? 'frequency' : 'delta'; syncControls(); loadData(++token); }
function setActionsCompareMode(next) {
  compareMode = next === 'average' ? 'average' : 'raw';
  syncControls();
  // Comparison is a local transform of the already loaded payload, including
  // Frequency; changing it must never re-query the action statistics.
  if (view === 'upgrades_by_map') renderPerMap();
  else render();
}
function toggleActionsOrderTranspose() {
  if (view !== 'upgrade_order') return;
  orderTransposed = !orderTransposed;
  syncControls();
  render();
}
function syncControls() {
  document.querySelectorAll('.actions-tabs .endgames-tab').forEach(btn => btn.classList.toggle('active', btn.dataset.view === view));
  document.querySelectorAll('.actions-mode button').forEach(btn => btn.classList.toggle('active', btn.dataset.mode === mode));
  document.querySelectorAll('.actions-compare-mode button').forEach(btn => btn.classList.toggle('active', btn.dataset.compare === compareMode));
  document.querySelector('.actions-mode')?.classList.toggle('is-hidden', view === 'starting_position' || view === 'upgrades');
  document.querySelector('.actions-compare-mode')?.classList.toggle('is-hidden', view !== 'upgrades_by_map');
  const transpose = document.getElementById('actionsTransposeBtn');
  transpose?.classList.toggle('is-hidden', view !== 'upgrade_order');
  transpose?.setAttribute('aria-pressed', String(orderTransposed));
  if (transpose) transpose.title = orderTransposed ? 'Restore rows and columns' : 'Swap rows and columns';
}
function params() {
  const v = id => document.getElementById(id)?.value ?? '';
  return {
    stats_page: 'actions', actions_view: view, is_mw: isMW, maps: selectedMaps,
    player_elo_min: v('playerEloMin') === '' ? 0 : Number(v('playerEloMin')),
    player_elo_max: v('playerEloMax') === '' ? null : Number(v('playerEloMax')),
    opponent_elo_min: v('opponentEloMin') === '' ? 0 : Number(v('opponentEloMin')),
    opponent_elo_max: v('opponentEloMax') === '' ? null : Number(v('opponentEloMax')),
    date_from: v('dateFrom') || '2025-01-01', date_to: v('dateTo') || null,
    completed_only: mode === 'frequency' && view !== 'starting_position' ? true : null,
  };
}
function snapshotUrl() {
  const snapshotMode = view === 'starting_position' ? 'delta' : mode;
  return `${SNAPSHOT_ROOT}/${view}/${snapshotMode}/default-${isMW ? 'mw' : 'base'}.json`;
}
function isDefault(p) {
  return p.player_elo_min === 300 && p.player_elo_max === null &&
    p.opponent_elo_min === 300 && p.opponent_elo_max === null &&
    p.date_from === '2025-01-01' && p.date_to === null && selectedMaps.length === MAPS.length;
}
async function loadData(activeToken) {
  renderLoading();
  try {
    const p = params();
    const payload = await loadStats(p, isDefault(p) ? snapshotUrl() : null);
    if (!mounted || activeToken !== token) return;
    rows = payload.data || []; render();
  } catch (error) { if (mounted && activeToken === token) renderError(error); }
}
function render() {
  document.getElementById('tableMeta').textContent = '';
  if (view === 'starting_position') renderStarting();
  else if (view === 'upgrades') renderUpgrades();
  else if (view === 'upgrade_order') renderUpgradeOrder();
  else renderPerMap();
}
function renderStarting() {
  const strength = rows.filter(row => row.section === 'strength');
  const comparison = rows.filter(row => row.section === 'comparison');
  const strengthRange = cappedNumericRange(
    strength.flatMap(row => [2, 3, 4, 5].map(v => ({
      value: row[`delta_${v}`],
      count: observationCount(row, `delta_${v}`, row[`count_${v}`]),
    }))).filter(item => !isInsufficientObservationCount(item.count)),
    item => item.value,
  );
  const compRange = cappedNumericRange(
    comparison.filter(row => !isInsufficientObservationCount(observationCount(row, 'delta_2', row.count_2))),
    row => row.delta_2,
  );
  document.getElementById('actionsContent').innerHTML = `<div class="actions-tables">
    <div class="build-table-panel actions-strength-panel"><div class="table-scroll">
      <table class="sponsor-endgames-table actions-table actions-strength-table"><thead><tr><th style="width:40%">Action</th>${[2,3,4,5].map(v => `<th style="width:15%">\u0394 (${v})<span class="col-tip" data-tip="average elo gain with an initial action strength of ${v}">?</span></th>`).join('')}</tr></thead>
      <tbody>${strength.map(row => `<tr><td class="sponsor-name-cell">${escapeHtml(row.label)}</td>${[2,3,4,5].map(v => deltaCell(row, `delta_${v}`, row[`count_${v}`], strengthRange)).join('')}</tr>`).join('')}</tbody></table>
    </div></div>
    <div class="build-table-panel actions-comparison-panel"><div class="table-scroll">
      <table class="sponsor-endgames-table actions-table actions-comparison-table"><thead><tr><th style="width:75%">Condition</th><th style="width:25%">Elo \u0394</th></tr></thead>
      <tbody>${comparison.map(row => `<tr class="${row.label === 'First player' ? 'actions-double-separator' : ''}"><td class="sponsor-name-cell">${comparisonLabel(row.label)}</td>${deltaCell(row, 'delta_2', row.count_2, compRange)}</tr>`).join('')}</tbody></table>
    </div></div>
  </div>`;
}

function renderUpgrades() {
  const number = rows.filter(row => row.section === 'number');
  const upgrade = rows.filter(row => row.section === 'upgrade');
  document.getElementById('actionsContent').innerHTML = `<div class="build-tables actions-upgrade-tables">
    ${simpleMetricTable('Upgrade count', number)}
    ${simpleMetricTable('Upgrade', upgrade)}
  </div>`;
}
function simpleMetricTable(firstHeader, data) {
  const range = cappedNumericRange(data.filter(row => !isInsufficientObservationCount(row.count)), row => row.delta);
  return `<div class="build-table-panel"><div class="table-scroll">
    <table class="sponsor-endgames-table actions-table actions-upgrades-combined"><thead><tr><th>${firstHeader}</th><th>Elo \u0394</th><th>Frequency</th></tr></thead>
    <tbody>${data.map(row => `<tr><td class="sponsor-name-cell">${escapeHtml(row.label)}</td>${deltaCell(row, 'delta', row.count, range)}${frequencyCell(row, firstHeader === 'Upgrade' ? 100 : 50)}</tr>`).join('')}</tbody></table>
  </div></div>`;
}

function renderUpgradeOrder() {
  const range = mode === 'delta'
    ? cappedNumericRange(
      rows.flatMap(row => [1,2,3,4].map(v => ({
        value: row[`delta_${v}`],
        count: observationCount(row, `delta_${v}`, row[`count_${v}`]),
      }))).filter(item => !isInsufficientObservationCount(item.count)),
      item => item.value,
    )
    : numericRange(rows.flatMap(row => [1,2,3,4].map(v => ({ value: orderFrequency(row, v) }))), item => item.value);
  const prefix = mode === 'delta' ? '\u0394' : 'f';
  if (orderTransposed) {
    document.getElementById('actionsContent').innerHTML = `<div class="table-wrap"><div class="table-scroll">
      <table id="statsTable" class="sponsor-endgames-table actions-table actions-order-transposed"><thead><tr>
        <th>Upgrade timing</th>${rows.map(row => `<th>${prefix} (${escapeHtml(row.label)})</th>`).join('')}
      </tr></thead>
      <tbody>${[1,2,3,4].map(slot => `<tr>
        <td class="sponsor-name-cell">${slot}${ordinal(slot)}</td>
        ${rows.map(row => mode === 'delta'
          ? deltaCell(row, `delta_${slot}`, row[`count_${slot}`], range)
          : transposedOrderFrequencyCell(row, slot)).join('')}
      </tr>`).join('')}</tbody></table>
    </div></div>`;
    return;
  }
  document.getElementById('actionsContent').innerHTML = `<div class="table-wrap"><div class="table-scroll">
    <table id="statsTable" class="sponsor-endgames-table actions-table"><thead><tr><th style="width:50%">Action</th>${[1,2,3,4].map(v => `<th style="width:12.5%">${prefix} (${v}${ordinal(v)})</th>`).join('')}</tr></thead>
    <tbody>${rows.map(row => `<tr><td class="sponsor-name-cell">${row.label}</td>${[1,2,3,4].map(v => mode === 'delta' ? deltaCell(row, `delta_${v}`, row[`count_${v}`], range) : orderFrequencyCell(row, v, range)).join('')}</tr>`).join('')}</tbody></table>
  </div></div>`;
}
function renderPerMap() {
  const mapKeys = MAPS.map(([, key]) => key);
  const mapRange = mode === 'delta'
    ? cappedNumericRange(rows.flatMap(row => mapKeys.map(field => ({ value: displayedMapValue(row, field), count: row[`count_${field}`] }))).filter(item => mode === 'frequency' || !isInsufficientObservationCount(item.count)), item => item.value)
    : numericRange(rows.flatMap(row => mapKeys.map(field => ({ value: displayedMapValue(row, field) }))), item => item.value);
  const avgRange = mode === 'delta' ? numericRange(rows, row => row.avg) : numericRange(rows, row => frequencyFor(row, 'avg'));
  document.getElementById('actionsContent').innerHTML = `<div class="table-wrap build-hexes-wrap"><div class="table-scroll">
    <table id="statsTable" class="maps-table actions-map-table ${mode === 'frequency' ? 'actions-map-frequency' : ''}"><thead><tr><th style="width:10%">Upgrade</th>${MAPS.map(([short,,full]) => `<th class="maps-custom-tip" data-tip="${escapeAttr(mapTooltipLabel(full))}" style="width:5.5%">${short}</th>`).join('')}<th style="width:7.5%">Avg</th></tr></thead>
    <tbody>${rows.map(row => `<tr><td class="sponsor-name-cell">${row.label}</td>${MAPS.map(([, key]) => mapCell(row, key, mapRange)).join('')}${mapAvgCell(row, avgRange)}</tr>`).join('')}</tbody></table>
  </div></div>`;
}
function deltaCell(row, field, count, range) {
  const value = Number(row[field]);
  if (!Number.isFinite(value)) return '<td class="unavailable-cell">-</td>';
  const n = observationCount(row, field, count);
  if (isInsufficientObservationCount(n)) return `<td class="delta sponsor-delta-insufficient build-value-tooltip" data-value-tooltip="${INSUFFICIENT_DATA_TOOLTIP}">${fmtSigned(value)}</td>`;
  const colorRange = normalizedDeltaRange(range, value);
  return `<td class="delta delta-ci-cell" data-ci-low="${escapeAttr(row[`${field}_ci95_low`] ?? '')}" data-ci-high="${escapeAttr(row[`${field}_ci95_high`] ?? '')}" data-ci-n="${escapeAttr(row[`${field}_ci95_n`] ?? '')}" data-ci-color-min="${escapeAttr(colorRange.min ?? '')}" data-ci-color-max="${escapeAttr(colorRange.max ?? '')}" style="color:${deltaRangeColor(value, colorRange.min, colorRange.max)}">${fmtSigned(value)}</td>`;
}
function observationCount(row, field, explicitCount) {
  const direct = Number(explicitCount);
  if (Number.isFinite(direct)) return direct;
  const ciN = Number(row?.[`${field}_ci95_n`]);
  return Number.isFinite(ciN) ? ciN : 0;
}
function normalizedDeltaRange(range, value) {
  if (range && Number.isFinite(Number(range.min)) && Number.isFinite(Number(range.max))) return range;
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return { min: -2, max: 2 };
  return { min: Math.min(-0.001, numeric), max: Math.max(0.001, numeric) };
}
function frequency(row) { return Number(row.denominator) > 0 ? 100 * Number(row.count || 0) / Number(row.denominator) : Number.NaN; }
function frequencyCell(row, cap = 50) {
  const pct = frequency(row);
  if (!Number.isFinite(pct)) return '<td class="unavailable-cell">-</td>';
  return `<td class="build-value-tooltip" data-value-tooltip="${fmtInt(row.count)} / ${fmtInt(row.denominator)}" style="color:${frequencyColor(pct, cap)}">${pct.toFixed(2)}%</td>`;
}
function orderFrequency(row, slot) { return Number(row.denominator) > 0 ? 100 * Number(row[`count_${slot}`] || 0) / Number(row.denominator) : Number.NaN; }
function orderFrequencyCell(row, slot, range) {
  const pct = orderFrequency(row, slot);
  if (!Number.isFinite(pct)) return '<td class="unavailable-cell">-</td>';
  return `<td class="build-value-tooltip" data-value-tooltip="${fmtInt(row[`count_${slot}`])} / ${fmtInt(row.denominator)}" style="color:${frequencyColor(pct)}">${pct.toFixed(2)}%</td>`;
}
function transposedOrderFrequencyCell(row, slot) {
  const denominator = rows.reduce((sum, item) => sum + Number(item[`count_${slot}`] || 0), 0);
  const numerator = Number(row[`count_${slot}`] || 0);
  const pct = denominator > 0 ? 100 * numerator / denominator : Number.NaN;
  if (!Number.isFinite(pct)) return '<td class="unavailable-cell">-</td>';
  return `<td class="build-value-tooltip" data-value-tooltip="${fmtInt(numerator)} / ${fmtInt(denominator)}" style="color:${frequencyColor(pct)}">${pct.toFixed(2)}%</td>`;
}
function frequencyFor(row, field) {
  const denominator = Number(row[`denom_${field}`]);
  const numerator = Number(row[`count_${field}`] || 0);
  return denominator > 0 && Number.isFinite(numerator) ? 100 * numerator / denominator : Number.NaN;
}
function displayedMapValue(row, field) {
  if (mode === 'frequency') {
    const mapPct = frequencyFor(row, field);
    if (compareMode !== 'average') return mapPct;
    const avgPct = frequencyFor(row, 'avg');
    return Number.isFinite(mapPct) && Number.isFinite(avgPct) ? mapPct - avgPct : Number.NaN;
  }
  const raw = Number(row[field]);
  if (!Number.isFinite(raw)) return Number.NaN;
  if (compareMode !== 'average') return raw;
  const avg = Number(row.avg);
  return Number.isFinite(avg) ? raw - avg : Number.NaN;
}
function mapCell(row, field, range) {
  const value = displayedMapValue(row, field);
  if (!Number.isFinite(value)) return '<td class="unavailable-cell">-</td>';
  if (mode === 'frequency') {
    const raw = frequencyFor(row, field);
    const text = compareMode === 'average' ? formatSignedPercentAdaptive(value) : fmtPercentFixed(raw);
    return `<td class="build-value-tooltip" data-value-tooltip="${fmtInt(row[`count_${field}`])} / ${fmtInt(row[`denom_${field}`])}" style="color:${frequencyColor(value)}">${text}</td>`;
  }
  if (compareMode === 'average') return `<td class="delta cp-map-comparison" style="color:${deltaRangeColor(value, range.min, range.max)}">${fmtSigned(value, 3, true)}</td>`;
  return deltaCell(row, field, row[`count_${field}`], range);
}
function mapAvgCell(row, range) {
  if (mode === 'frequency') {
    const pct = frequencyFor(row, 'avg');
    return `<td class="build-value-tooltip" data-value-tooltip="${fmtInt(row.count_avg)} / ${fmtInt(row.denom_avg)}" style="color:${violetRangeColor(pct, range.min, range.max)}">${fmtPercentFixed(pct)}</td>`;
  }
  const value = Number(row.avg);
  return `<td class="delta cp-cell" style="color:${orangeGreenRangeColor(value, range.min, range.max)}">${Number.isFinite(value) ? fmtSigned(value, 3) : '\u2014'}</td>`;
}
function renderLoading() { document.getElementById('actionsContent').innerHTML = '<div class="state-overlay"><div class="spinner"></div><div class="state-title">Fetching action statistics...</div></div>'; }
function renderError(error) { document.getElementById('actionsContent').innerHTML = `<div class="state-overlay"><div class="state-title">Could not load action statistics</div><div class="state-sub">${escapeHtml(error.message || error)}</div></div>`; }
function renderMapChips() { const host = document.getElementById('mapChips'); if (host) host.innerHTML = MAPS.map(([short,,full]) => `<button class="chip ${selectedMaps.includes(full) ? 'active' : ''}" data-map="${escapeAttr(full)}" onclick="toggleActionsMap(this.dataset.map)">${short}</button>`).join(''); }
function toggleActionsMap(map) { selectedMaps = selectedMaps.includes(map) ? selectedMaps.filter(item => item !== map) : [...selectedMaps, map]; renderMapChips(); }
function selectAllMaps() { selectedMaps = MAPS.map(([, , full]) => full); renderMapChips(); }
function selectNoneMaps() { selectedMaps = []; renderMapChips(); }
function resetFilters() { const set = (id, value) => { const el = document.getElementById(id); if (el) el.value = value; }; set('playerEloMin','300'); set('playerEloMax',''); set('opponentEloMin','300'); set('opponentEloMax',''); set('dateFrom','2025-01-01'); set('dateTo',''); selectedMaps = MAPS.map(([, , full]) => full); renderMapChips(); loadData(++token); }
function applyFiltersFromSidebar() { loadData(++token); document.getElementById('sidebar')?.classList.remove('open'); document.getElementById('sidebarOverlay')?.classList.remove('active'); }
function comparisonLabel(label) {
  const text = String(label ?? '');
  if (/^Higher\s+/i.test(text) && !/than opponent/i.test(text)) return `${escapeHtml(text)} than opponent`;
  return escapeHtml(text);
}
function ordinal(value) { return value === 1 ? 'st' : value === 2 ? 'nd' : value === 3 ? 'rd' : 'th'; }
function fmtPercentFixed(value) {
  const n = Number(value);
  return Number.isFinite(n) ? `${n.toFixed(2)}%` : '\u2014';
}
function fmtSigned(value, decimals = 3, plusMinusZero = false) { return formatSignedDeltaAdaptive(value, plusMinusZero); }
function fmtInt(value) { return Number(value || 0).toLocaleString('en-US'); }
function escapeHtml(value) { return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;'); }
const escapeAttr = escapeHtml;

const valueTooltip = document.getElementById('col-tooltip');
function actionsTooltipSource(event) {
  return event.target.closest?.('.build-value-tooltip, .maps-custom-tip')
    || event.target.closest?.('th')?.querySelector('.col-tip');
}
function positionActionsTooltip(event) {
  if (!valueTooltip) return;
  valueTooltip.style.left = `${Math.max(8, Math.min(event.clientX + 12, window.innerWidth - valueTooltip.offsetWidth - 8))}px`;
  valueTooltip.style.top = `${event.clientY + 18}px`;
}
document.addEventListener('mouseover', event => {
  if (!mounted || !valueTooltip) return;
  const source = actionsTooltipSource(event);
  if (!source) return;
  valueTooltip.textContent = source.dataset.valueTooltip || source.dataset.tip || '';
  valueTooltip.style.display = 'block';
  positionActionsTooltip(event);
});
document.addEventListener('mousemove', event => {
  if (!mounted || !valueTooltip || !actionsTooltipSource(event)) return;
  positionActionsTooltip(event);
});
document.addEventListener('mouseout', event => {
  if (!mounted || !valueTooltip) return;
  const source = actionsTooltipSource(event);
  const destination = event.relatedTarget?.closest?.('.build-value-tooltip, .maps-custom-tip')
    || event.relatedTarget?.closest?.('th')?.querySelector?.('.col-tip');
  if (source && destination !== source) valueTooltip.style.display = 'none';
});
