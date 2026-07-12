import {
  cappedNumericRange,
  deltaRangeColor,
  frequencyColor,
  numericRange,
  orangeGreenRangeColor,
  workerAverageColor,
  workerAverageDeltaColor,
  workerAverageVioletColor,
  violetRangeColor,
} from '../color-scales.js?v=20260712-3';
import {
  INSUFFICIENT_DATA_TOOLTIP,
  formatSignedDeltaAdaptive,
  formatSignedPercentAdaptive,
  isInsufficientObservationCount,
  mapTooltipLabel,
} from '../table-cells.js?v=20260712-4';
import { loadStats } from '../snapshot-cache.js?v=20260712-1';

export const id = 'workers';
export const title = 'Workers';
export const navLabel = 'Workers';

const API_ROOT = 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/workers';
const VIEWS = { general: 'general', two_cp_worker: 'two-cp-worker' };
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
  <div class="main-header sponsor-endgames-main-header actions-main-header workers-main-header">
    <div class="table-meta" id="workersMeta"><span class="workers-last-worker">Last worker: 0 CP - <u>1 CP</u> - <u class="workers-double-underline">2 CP</u></span></div>
    <div class="build-switches workers-switches">
      <div class="maps-h2h-mode workers-compare" role="group" aria-label="Workers comparison mode">
        <button type="button" class="active" data-compare="raw" onclick="setWorkersCompare('raw')">Raw</button>
        <button type="button" data-compare="average" onclick="setWorkersCompare('average')">vs. avg</button>
      </div>
      <div class="maps-h2h-mode workers-mode" role="group" aria-label="Workers metric">
        <button type="button" class="active" data-mode="delta" onclick="setWorkersMode('delta')">Elo &Delta;</button>
        <button type="button" data-mode="frequency" onclick="setWorkersMode('frequency')">Frequency</button>
      </div>
    </div>
  </div>
  <div class="attributes-bar endgames-tabs-bar">
    <div class="attributes-bar-header endgames-tabs-header">
      <div class="endgames-tabs workers-tabs" role="tablist" aria-label="Workers views">
        <button class="endgames-tab active" data-view="general" onclick="setWorkersView('general')">General</button>
        <button class="endgames-tab" data-view="two_cp_worker" onclick="setWorkersView('two_cp_worker')">2 CP Worker</button>
      </div>
    </div>
  </div>
  <div id="workersContent"></div>`;

export const sidebarHtml = `
  <div class="sidebar-header"><span class="sidebar-title">Filters</span><div style="display:flex;align-items:center;gap:6px;">
    <button class="reset-btn" onclick="resetWorkersFilters()">Reset</button>
    <button class="sidebar-close-btn" onclick="toggleSidebar()" title="Close filters">x</button>
  </div></div>
  <hr class="divider" />
  <div class="filter-group"><span class="filter-label">Player ELO</span><div class="range-row">
    <input class="range-input" type="number" id="workersPlayerEloMin" placeholder="Min" value="300" min="0" />
    <input class="range-input" type="number" id="workersPlayerEloMax" placeholder="Max" min="0" />
  </div></div>
  <div class="filter-group"><span class="filter-label">Opponent ELO</span><div class="range-row">
    <input class="range-input" type="number" id="workersOpponentEloMin" placeholder="Min" value="300" min="0" />
    <input class="range-input" type="number" id="workersOpponentEloMax" placeholder="Max" min="0" />
  </div></div>
  <hr class="divider" />
  <div class="filter-group"><span class="filter-label">Date Range</span>
    <input class="date-input" type="text" id="workersDateFrom" value="2025-01-01" placeholder="yyyy-mm-dd" />
    <input class="date-input" type="text" id="workersDateTo" placeholder="yyyy-mm-dd" />
  </div>
  <div id="workersCompletedSection" class="filter-group is-hidden"><hr class="divider" />
    <div class="toggle-row"><span class="toggle-label">Completed games only</span><label class="toggle">
      <input type="checkbox" id="workersCompletedToggle" /><span class="toggle-track"></span>
    </label></div>
  </div>
  <div class="filter-action-stack"><button class="apply-btn" onclick="applyWorkersFilters()">Apply filters</button></div>`;

let mounted = false;
let token = 0;
let isMW = 1;
let view = 'general';
let mode = 'delta';
let compare = 'raw';
let rows = [];

export function mount({ dataset = 1 } = {}) {
  mounted = true;
  token += 1;
  isMW = Number(dataset) === 0 ? 0 : 1;
  view = 'general';
  mode = 'delta';
  compare = 'raw';
  rows = [];
  Object.assign(window, {
    setWorkersView, setWorkersMode, setWorkersCompare,
    resetWorkersFilters, applyWorkersFilters,
  });
  syncControls();
  loadData(token);
}

export function unmount() { mounted = false; token += 1; hideTooltip(); }
export function setDataset(value) { isMW = Number(value) === 0 ? 0 : 1; loadData(++token); }

function setWorkersView(next) {
  view = Object.hasOwn(VIEWS, next) ? next : 'general';
  mode = 'delta';
  compare = 'raw';
  syncControls();
  loadData(++token);
}
function setWorkersMode(next) { mode = next === 'frequency' ? 'frequency' : 'delta'; syncControls(); render(); }
function setWorkersCompare(next) { compare = next === 'average' ? 'average' : 'raw'; syncControls(); render(); }

function syncControls() {
  document.querySelectorAll('.workers-tabs .endgames-tab').forEach(btn => btn.classList.toggle('active', btn.dataset.view === view));
  document.querySelectorAll('.workers-mode button').forEach(btn => btn.classList.toggle('active', btn.dataset.mode === mode));
  document.querySelectorAll('.workers-compare button').forEach(btn => btn.classList.toggle('active', btn.dataset.compare === compare));
  document.getElementById('workersCompletedSection')?.classList.toggle('is-hidden', view !== 'two_cp_worker');
}

function value(id) { return document.getElementById(id)?.value ?? ''; }
function params() {
  return {
    stats_page: 'workers', workers_view: view, is_mw: isMW,
    maps: MAPS.map(([, , full]) => full),
    player_elo_min: value('workersPlayerEloMin') === '' ? 0 : Number(value('workersPlayerEloMin')),
    player_elo_max: value('workersPlayerEloMax') === '' ? null : Number(value('workersPlayerEloMax')),
    opponent_elo_min: value('workersOpponentEloMin') === '' ? 0 : Number(value('workersOpponentEloMin')),
    opponent_elo_max: value('workersOpponentEloMax') === '' ? null : Number(value('workersOpponentEloMax')),
    date_from: value('workersDateFrom') || '2025-01-01',
    date_to: value('workersDateTo') || null,
    completed_only: view === 'two_cp_worker' && document.getElementById('workersCompletedToggle')?.checked ? true : null,
  };
}
function isDefault(p) {
  return p.player_elo_min === 300 && p.player_elo_max === null
    && p.opponent_elo_min === 300 && p.opponent_elo_max === null
    && p.date_from === '2025-01-01' && p.date_to === null
    && p.completed_only === null;
}
function snapshotUrl() { return `${API_ROOT}/${VIEWS[view]}/default-${isMW ? 'mw' : 'base'}.json`; }

async function loadData(activeToken) {
  renderLoading();
  try {
    const p = params();
    const payload = await loadStats(p, isDefault(p) ? snapshotUrl() : null);
    if (!mounted || activeToken !== token) return;
    rows = Array.isArray(payload.data) ? payload.data : [];
    render();
  } catch (error) {
    if (mounted && activeToken === token) renderError(error);
  }
}

function render() {
  document.getElementById('workersMeta').innerHTML = '<span class="workers-last-worker">Last worker: 0 CP - <u>1 CP</u> - <u class="workers-double-underline">2 CP</u></span>';
  const mapKeys = MAPS.map(([, key]) => key);
  const mapValues = rows.flatMap(row => mapKeys.map(field => ({
    value: displayedValue(row, field),
    count: row[`count_${field}`],
  })));
  const mapRange = mode === 'delta'
    ? cappedNumericRange(mapValues.filter(item => !isInsufficientObservationCount(item.count)), item => item.value)
    : numericRange(mapValues, item => item.value);
  const avgRange = mode === 'delta'
    ? numericRange(rows, row => row.avg)
    : numericRange(rows, row => frequencyFor(row, 'avg'));
  const frequencyTableClass = mode === 'frequency' ? ' workers-frequency-table' : '';
  const averageRow = view === 'general' && mode === 'frequency' ? workerAverageRow(mapKeys) : '';
  document.getElementById('workersContent').innerHTML = `<div class="table-wrap build-hexes-wrap"><div class="table-scroll">
    <table class="maps-table actions-map-table workers-map-table${frequencyTableClass}"><thead><tr>
      <th style="width:10%">${view === 'general' ? 'Count' : '2 CP'}</th>
      ${MAPS.map(([short,,full]) => `<th class="maps-custom-tip" data-tip="${escapeAttr(mapTooltipLabel(full))}" style="width:5.5%">${workerHeaderLabel(short)}</th>`).join('')}
      <th style="width:7.5%">Avg</th>
    </tr></thead><tbody>${rows.map(row => `<tr>
      <td class="sponsor-name-cell">${escapeHtml(row.label)}</td>
      ${mapKeys.map(field => mapCell(row, field, mapRange)).join('')}
      ${avgCell(row, avgRange)}
    </tr>`).join('')}${averageRow}</tbody></table>
  </div></div>`;
}

function workerHeaderLabel(code) {
  const double = new Set(['6a', '7a', '10']);
  const single = new Set(['2a', '4a', '5a', '8a', '11', '12', '14', 'T1']);
  if (double.has(code)) return `<span class="workers-header-double">${code}</span>`;
  if (single.has(code)) return `<span class="workers-header-single">${code}</span>`;
  return code;
}

function workerAverageRow(mapKeys) {
  const overall = number(rows[0]?.worker_avg_avg);
  const values = mapKeys.map(field => number(rows[0]?.[`worker_avg_${field}`]));
  const deltas = values.map(value => Number.isFinite(value) && Number.isFinite(overall) ? value - overall : Number.NaN);
  const range = numericRange(deltas, value => value);
  const cells = mapKeys.map((field, index) => {
    const raw = values[index];
    if (!Number.isFinite(raw)) return unavailableTd();
    if (compare === 'average') {
      const delta = deltas[index];
      return `<td class="worker-average-cell" style="color:${workerAverageDeltaColor(delta, range.min, range.max)}">${fmtSigned(delta)}</td>`;
    }
    return `<td class="worker-average-cell" style="color:${workerAverageColor(raw)}">${raw.toFixed(2)}</td>`;
  }).join('');
  if (!Number.isFinite(overall)) return `<tr class="workers-average-row"><td class="sponsor-name-cell">n (Avg)</td>${cells}<td class="worker-average-cell worker-average-avg">-</td></tr>`;
  return `<tr class="workers-average-row"><td class="sponsor-name-cell">n (Avg)</td>${cells}<td class="worker-average-cell worker-average-avg" style="color:${workerAverageVioletColor(overall)}">${overall.toFixed(2)}</td></tr>`;
}

function displayedValue(row, field) {
  const raw = mode === 'frequency' ? frequencyFor(row, field) : number(row[field]);
  if (compare === 'raw') return raw;
  const avg = mode === 'frequency' ? frequencyFor(row, 'avg') : number(row.avg);
  return Number.isFinite(raw) && Number.isFinite(avg) ? raw - avg : Number.NaN;
}
function frequencyFor(row, field) {
  const denominator = number(row[`denom_${field}`]);
  return denominator > 0 ? 100 * number(row[`count_${field}`] || 0) / denominator : Number.NaN;
}
function mapCell(row, field, range) {
  const value = displayedValue(row, field);
  if (!Number.isFinite(value)) return unavailableTd();
  if (mode === 'frequency') {
    const raw = frequencyFor(row, field);
    const text = compare === 'average' ? formatSignedPercentAdaptive(value) : fmtPct(raw);
    return `<td class="build-value-tooltip" data-value-tooltip="${fmtInt(row[`count_${field}`])} / ${fmtInt(row[`denom_${field}`])}" style="color:${frequencyColor(value)}">${text}</td>`;
  }
  if (compare === 'average') return `<td class="delta cp-map-comparison" style="color:${deltaRangeColor(value, range.min, range.max)}">${fmtSigned(value, 3, true)}</td>`;
  return deltaCell(row, field, row[`count_${field}`], range);
}
function avgCell(row, range) {
  if (mode === 'frequency') {
    const pct = frequencyFor(row, 'avg');
    if (!Number.isFinite(pct)) return unavailableTd();
    return `<td class="build-value-tooltip" data-value-tooltip="${fmtInt(row.count_avg)} / ${fmtInt(row.denom_avg)}" style="color:${violetRangeColor(pct, range.min, range.max)}">${fmtPct(pct)}</td>`;
  }
  const value = number(row.avg);
  if (!Number.isFinite(value)) return unavailableTd();
  const n = Number(row.avg_ci95_n ?? row.count_avg);
  const display = fmtSigned(value, 3, true);
  if (isInsufficientObservationCount(n)) return `<td class="delta cp-cell sponsor-delta-insufficient build-value-tooltip" data-value-tooltip="${INSUFFICIENT_DATA_TOOLTIP}">${display}</td>`;
  return `<td class="delta cp-cell delta-ci-cell" data-ci-low="${escapeAttr(row.avg_ci95_low ?? '')}" data-ci-high="${escapeAttr(row.avg_ci95_high ?? '')}" data-ci-n="${escapeAttr(row.avg_ci95_n ?? '')}" data-ci-color-scale="orange-green" data-ci-color-min="${escapeAttr(range.min ?? '')}" data-ci-color-max="${escapeAttr(range.max ?? '')}" style="color:${orangeGreenRangeColor(value, range.min, range.max)}">${display}</td>`;
}
function deltaCell(row, field, count, range) {
  const value = number(row[field]);
  if (!Number.isFinite(value)) return unavailableTd();
  if (isInsufficientObservationCount(count)) return `<td class="delta sponsor-delta-insufficient build-value-tooltip" data-value-tooltip="${INSUFFICIENT_DATA_TOOLTIP}">${fmtSigned(value)}</td>`;
  return `<td class="delta delta-ci-cell" data-ci-low="${escapeAttr(row[`${field}_ci95_low`] ?? '')}" data-ci-high="${escapeAttr(row[`${field}_ci95_high`] ?? '')}" data-ci-n="${escapeAttr(row[`${field}_ci95_n`] ?? '')}" data-ci-color-min="${escapeAttr(range.min ?? '')}" data-ci-color-max="${escapeAttr(range.max ?? '')}" style="color:${deltaRangeColor(value, range.min, range.max)}">${fmtSigned(value)}</td>`;
}
function resetWorkersFilters() {
  const set = (id, value) => { const el = document.getElementById(id); if (el) el.value = value; };
  set('workersPlayerEloMin', '300'); set('workersPlayerEloMax', '');
  set('workersOpponentEloMin', '300'); set('workersOpponentEloMax', '');
  set('workersDateFrom', '2025-01-01'); set('workersDateTo', '');
  const completed = document.getElementById('workersCompletedToggle');
  if (completed) completed.checked = false;
  loadData(++token);
}
function applyWorkersFilters() {
  loadData(++token);
  document.getElementById('sidebar')?.classList.remove('open');
  document.getElementById('sidebarOverlay')?.classList.remove('active');
}
function renderLoading() { document.getElementById('workersContent').innerHTML = '<div class="state-overlay"><div class="spinner"></div><div class="state-title">Fetching worker statistics...</div></div>'; }
function renderError(error) { document.getElementById('workersContent').innerHTML = `<div class="state-overlay"><div class="state-title">Could not load worker statistics</div><div class="state-sub">${escapeHtml(error.message || error)}</div></div>`; }
function unavailableTd() { return '<td class="unavailable-cell">-</td>'; }
function number(value) { const n = Number(value); return Number.isFinite(n) ? n : Number.NaN; }
function fmtInt(value) { return Number(value || 0).toLocaleString('en-US'); }
function fmtPct(value) { return Number.isFinite(number(value)) ? `${number(value).toFixed(2)}%` : '-'; }
function fmtSigned(value, decimals = 3, plusMinusZero = false) { return formatSignedDeltaAdaptive(value, plusMinusZero); }
function escapeHtml(value) { return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;'); }
const escapeAttr = escapeHtml;

const tooltip = document.getElementById('col-tooltip');
function workersTooltipSource(event) {
  return event.target.closest?.('.build-value-tooltip, .maps-custom-tip')
    || event.target.closest?.('th')?.querySelector('.col-tip');
}
function positionTooltip(event) {
  if (!tooltip) return;
  tooltip.style.left = `${Math.max(8, Math.min(event.clientX + 12, window.innerWidth - tooltip.offsetWidth - 8))}px`;
  tooltip.style.top = `${event.clientY + 18}px`;
}
function hideTooltip() { if (tooltip) tooltip.style.display = 'none'; }
document.addEventListener('mouseover', event => {
  if (!mounted || !tooltip) return;
  const source = workersTooltipSource(event);
  if (!source) return;
  tooltip.textContent = source.dataset.valueTooltip || source.dataset.tip || '';
  tooltip.style.display = 'block';
  positionTooltip(event);
});
document.addEventListener('mousemove', event => {
  if (mounted && tooltip && workersTooltipSource(event)) positionTooltip(event);
});
document.addEventListener('mouseout', event => {
  if (!mounted || !tooltip) return;
  const source = workersTooltipSource(event);
  const destination = event.relatedTarget ? workersTooltipSource({ target: event.relatedTarget }) : null;
  if (source && destination !== source) hideTooltip();
});
