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
import { loadStats } from '../snapshot-cache.js?v=20260712-2';

export const id = 'build';
export const title = 'Build';
export const navLabel = 'Build';

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
const STANDARD_BUCKETS = [['delta_0', '0'], ['delta_1', '1'], ['delta_2', '2'],
  ['delta_3', '3'], ['delta_4', '4'], ['delta_5_plus', '5+']];
const UNIQUE_BUCKETS = [['delta_0', 'No'], ['delta_1', 'Yes'], ['delta_empty', 'Empty']];
const API_URL = 'https://europe-west1-ark-nova-stats-dashboard.cloudfunctions.net/get-card-stats';
const SNAPSHOT_ROOT = 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/build';

export const mainHtml = `
  <div class="main-header sponsor-endgames-main-header build-main-header">
    <div class="table-meta" id="tableMeta"></div>
    <div class="build-switches">
      <div class="maps-h2h-mode build-compare-mode" role="group" aria-label="Build comparison mode">
        <button type="button" class="active" data-compare="raw" onclick="setBuildCompareMode('raw')">Raw</button>
        <button type="button" data-compare="average" onclick="setBuildCompareMode('average')">vs. avg</button>
      </div>
      <div class="maps-h2h-mode build-mode" role="group" aria-label="Build metric">
        <button type="button" class="active" data-mode="delta" onclick="setBuildMode('delta')">Elo &Delta;</button>
        <button type="button" data-mode="frequency" onclick="setBuildMode('frequency')">Frequency</button>
      </div>
    </div>
  </div>
  <div class="attributes-bar endgames-tabs-bar">
    <div class="attributes-bar-header endgames-tabs-header">
      <div class="endgames-tabs build-tabs" role="tablist" aria-label="Build views">
        <button class="endgames-tab active" type="button" data-view="enclosures" onclick="setBuildView('enclosures')">Enclosures</button>
        <button class="endgames-tab" type="button" data-view="hexes" onclick="setBuildView('hexes')">Hexes</button>
      </div>
    </div>
  </div>
  <div id="buildContent"></div>`;

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
  <div class="filter-group" id="completedFilterGroup"><div class="toggle-row"><span class="toggle-label">Completed games only</span>
    <label class="toggle"><input type="checkbox" id="endGameToggle" onchange="rememberBuildCompleted()"><span class="toggle-track"></span></label>
  </div></div>
  <hr class="divider" />
  <div class="filter-action-stack"><button class="apply-btn" onclick="applyFiltersFromSidebar()">Apply filters</button></div>`;

let mounted = false;
let token = 0;
let isMW = 1;
let mode = 'delta';
let view = 'enclosures';
let compareMode = 'raw';
let rows = [];
let expandedRows = [];
let selectedMaps = MAPS.map(([, , full]) => full);
let completedByMode = { delta: false, frequency: true };
let expanded = false;

export function mount({ dataset = 1 } = {}) {
  mounted = true;
  token += 1;
  isMW = Number(dataset) === 0 ? 0 : 1;
  mode = 'delta';
  view = 'enclosures';
  compareMode = 'raw';
  rows = [];
  expandedRows = [];
  selectedMaps = MAPS.map(([, , full]) => full);
  completedByMode = { delta: false, frequency: true };
  expanded = false;
  bindHandlers();
  renderMapChips();
  syncControls();
  loadData(token);
}

export function unmount() { mounted = false; token += 1; }
export function setDataset(value) {
  isMW = Number(value) === 0 ? 0 : 1;
  loadData(++token);
}

function bindHandlers() {
  Object.assign(window, {
    setBuildMode, setBuildView, setBuildCompareMode, toggleBuildExpanded, rememberBuildCompleted, resetFilters,
    applyFiltersFromSidebar, selectAllMaps, selectNoneMaps, toggleBuildMap,
  });
}

function setBuildMode(next) {
  rememberBuildCompleted();
  mode = next === 'frequency' ? 'frequency' : 'delta';
  syncControls();
  loadData(++token);
}
function setBuildView(next) {
  view = next === 'hexes' ? 'hexes' : 'enclosures';
  compareMode = 'raw';
  syncControls();
  loadData(++token);
}
function setBuildCompareMode(next) {
  compareMode = next === 'average' ? 'average' : 'raw';
  syncControls();
  render();
}
function toggleBuildExpanded() {
  if (view !== 'hexes') return;
  expanded = !expanded;
  render();
}
function syncControls() {
  document.querySelectorAll('.build-mode button').forEach(button => button.classList.toggle('active', button.dataset.mode === mode));
  document.querySelectorAll('.build-compare-mode button').forEach(button => button.classList.toggle('active', button.dataset.compare === compareMode));
  document.querySelectorAll('.build-tabs .endgames-tab').forEach(button => button.classList.toggle('active', button.dataset.view === view));
  document.querySelector('.build-compare-mode')?.classList.toggle('is-hidden', view !== 'hexes');
  document.getElementById('completedFilterGroup')?.classList.toggle('is-hidden', view === 'hexes');
  syncCompleted();
}
function syncCompleted() {
  const input = document.getElementById('endGameToggle');
  if (input) input.checked = completedByMode[mode];
}
function rememberBuildCompleted() {
  completedByMode[mode] = Boolean(document.getElementById('endGameToggle')?.checked);
}

function getParams() {
  const value = id => document.getElementById(id)?.value ?? '';
  return {
    stats_page: 'build', build_view: view, is_mw: isMW, maps: selectedMaps,
    player_elo_min: value('playerEloMin') === '' ? 0 : Number(value('playerEloMin')),
    player_elo_max: value('playerEloMax') === '' ? null : Number(value('playerEloMax')),
    opponent_elo_min: value('opponentEloMin') === '' ? 0 : Number(value('opponentEloMin')),
    opponent_elo_max: value('opponentEloMax') === '' ? null : Number(value('opponentEloMax')),
    date_from: value('dateFrom') || '2025-01-01', date_to: value('dateTo') || null,
    completed_only: view === 'hexes' ? null : (completedByMode[mode] ? true : null),
  };
}

function isDefault(params) {
  return params.player_elo_min === 300 && params.player_elo_max === null &&
    params.opponent_elo_min === 300 && params.opponent_elo_max === null &&
    params.date_from === '2025-01-01' && params.date_to === null &&
    selectedMaps.length === MAPS.length &&
    params.completed_only === (view === 'hexes' ? null : (mode === 'frequency' ? true : null));
}

function snapshotUrl() {
  const dataset = isMW ? 'mw' : 'base';
  return `${SNAPSHOT_ROOT}/${view}/${mode}/default-${dataset}.json`;
}

async function loadData(activeToken) {
  renderLoading();
  try {
    const params = getParams();
    const payload = await loadStats(params, isDefault(params) ? snapshotUrl() : null);
    if (!mounted || activeToken !== token) return;
    rows = payload.data || [];
    expandedRows = Array.isArray(payload.expanded_data) ? payload.expanded_data : rows;
    render();
  } catch (error) {
    if (mounted && activeToken === token) renderError(error);
  }
}

function render() {
  if (view === 'hexes') renderHexes();
  else renderEnclosures();
}

function renderEnclosures() {
  const standard = rows.filter(row => row.category === 'standard');
  const unique = rows.filter(row => row.category === 'unique');
  document.getElementById('tableMeta').textContent = '';
  document.getElementById('buildContent').innerHTML = `<div class="build-tables">
    ${enclosureTableHtml('Standard enclosures', standard, STANDARD_BUCKETS, false)}
    ${enclosureTableHtml('Unique enclosures', unique, UNIQUE_BUCKETS, true)}
  </div>`;
}

function enclosureTableHtml(titleText, data, buckets, unique) {
  const usable = data.flatMap(row => buckets.map(([field]) => ({ row, field })))
    .filter(({ row, field }) => possible(row, field));
  const range = mode === 'delta'
    ? cappedNumericRange(usable.filter(({ row, field }) => !isInsufficientObservationCount(count(row, field))), item => item.row[item.field])
    : numericRange(usable.filter(({ field }) => field !== 'delta_empty'), item => frequency(item.row, item.field));
  const prefix = mode === 'delta' ? '\u0394' : 'f';
  const tableClass = unique ? 'build-unique-enclosures-table' : 'build-standard-enclosures-table';
  const colgroup = unique
    ? '<colgroup><col style="width:40%"><col style="width:20%"><col style="width:20%"><col style="width:20%"></colgroup>'
    : '<colgroup><col style="width:10%"><col style="width:15%"><col style="width:15%"><col style="width:15%"><col style="width:15%"><col style="width:15%"><col style="width:15%"></colgroup>';
  void titleText;
  return `<div class="build-table-panel"><div class="table-scroll">
    <table class="sponsor-endgames-table build-table ${tableClass}">${colgroup}<thead><tr>
      <th>${unique ? 'Unique enclosure' : 'Size'}</th>
      ${buckets.map(([, label]) => `<th>${prefix} (${label})</th>`).join('')}
    </tr></thead><tbody>${data.map(row => `<tr><td class="sponsor-name-cell">${enclosureLabel(row, unique)}</td>
      ${buckets.map(([field]) => enclosureCell(row, field, range)).join('')}</tr>`).join('')}
    </tbody></table></div></div>`;
}

function enclosureLabel(row, unique) {
  const label = String(row.enclosure ?? '');
  if (unique) return escapeHtml(label);
  return escapeHtml(label.replace(/\s*-?\s*size$/i, ''));
}

function possible(row, field) {
  if (field === 'delta_empty') return row.enclosure === 'Petting Zoo';
  if (row.category === 'unique') return field === 'delta_0' || field === 'delta_1';
  return true;
}
function count(row, field) { return Number(row[field.replace('delta_', 'count_')]) || 0; }
function denominator(row, field) { return field === 'delta_empty' ? Number(row.empty_denominator) : Number(row.n_total); }
function frequency(row, field) {
  const total = denominator(row, field);
  return total > 0 ? 100 * count(row, field) / total : Number.NaN;
}
function enclosureCell(row, field, range) {
  if (!possible(row, field)) return '<td class="unavailable-cell">-</td>';
  const occurrences = count(row, field);
  if (mode === 'frequency') {
    const pct = frequency(row, field);
    if (!Number.isFinite(pct)) return '<td class="unavailable-cell">-</td>';
    const total = denominator(row, field);
    const color = field === 'delta_empty' ? 'rgba(153, 102, 204, .72)' : frequencyColor(pct);
    return `<td class="build-value-tooltip" data-value-tooltip="${fmtInt(occurrences)} / ${fmtInt(total)}" style="color:${color}">${pct.toFixed(2)}%</td>`;
  }
  return deltaCell(row, field, occurrences, range);
}

function renderHexes() {
  // Hexes is always non-conceded. Both collapsed and exact rows arrive in the
  // same snapshot/API payload, so changing expansion never performs a request.
  document.getElementById('tableMeta').textContent = '';
  const mapFields = MAPS.map(([, key]) => key);
  const displayRows = expanded ? expandedRows : rows;
  const mapValues = displayRows.flatMap(row => mapFields.map(field => ({ value: displayedMapValue(row, field) })));
  const mapRange = mode === 'delta'
    ? cappedNumericRange(mapValues, row => row.value)
    : numericRange(mapValues, row => row.value);
  const avgRange = mode === 'delta'
    ? numericRange(displayRows, row => row.avg)
    : numericRange(displayRows, row => frequencyFor(row, 'avg'));
  document.getElementById('buildContent').innerHTML = `<div class="build-hexes-shell ${expanded ? 'is-expanded' : ''}">
    <div class="table-wrap build-hexes-wrap">
    <div class="table-scroll">
    <table class="maps-table build-hexes-table ${mode === 'frequency' ? 'build-hexes-frequency' : ''}" id="statsTable">
      <thead><tr>
        <th class="build-hexes-bucket-header" style="width:10%">Empty hexes</th>
        ${MAPS.map(([short, , full]) => `<th class="maps-custom-tip" data-tip="${escapeAttr(mapTooltipLabel(full))}" style="width:5.5%;text-align:center">${escapeHtml(short)}</th>`).join('')}
        <th style="width:7.5%">Avg</th>
      </tr></thead>
      <tbody>${displayRows.map(row => `<tr class="${expanded ? 'hexes-expanded-row' : ''}">
        <td class="sponsor-name-cell build-hexes-bucket-cell">${escapeHtml(row.bucket_label)}</td>
        ${MAPS.map(([, key]) => hexesCell(row, key, mapRange)).join('')}
        ${hexesAvgCell(row, avgRange)}
       </tr>`).join('')}</tbody>
    </table>
    </div>
    </div>
  <button type="button" class="build-expand-btn" onclick="toggleBuildExpanded()"
    aria-expanded="${expanded}" aria-label="${expanded ? 'Collapse exact empty-hex values' : 'Expand exact empty-hex values'}"
    title="${expanded ? 'Collapse values' : 'Expand values'}"><span aria-hidden="true">${expanded ? '&#9650;' : '&#9660;'}</span></button>
  </div>`;
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
function frequencyFor(row, field) {
  const total = Number(row[`denom_${field}`]);
  const occurrences = Number(row[`count_${field}`]);
  return total > 0 ? 100 * occurrences / total : Number.NaN;
}
function hexesCell(row, field, range) {
  const value = displayedMapValue(row, field);
  const occurrences = Number(row[`count_${field}`]) || 0;
  if (mode === 'frequency') {
    if (!Number.isFinite(value)) return '<td class="unavailable-cell">-</td>';
    const rawPct = frequencyFor(row, field);
    const total = Number(row[`denom_${field}`]) || 0;
    const text = compareMode === 'average' ? formatSignedPercentAdaptive(value) : `${rawPct.toFixed(2)}%`;
    const tip = `${fmtInt(occurrences)} / ${fmtInt(total)}`;
    const frequencyCap = expanded ? 20 : 50;
    return `<td class="build-value-tooltip" data-value-tooltip="${tip}" style="color:${frequencyColor(value, frequencyCap)}">${text}</td>`;
  }
  const text = compareMode === 'average' ? fmtSigned(value, 3, true) : fmtSigned(value, 3, true);
  if (!Number.isFinite(value)) return '<td class="unavailable-cell">-</td>';
  if (compareMode === 'average') {
    if (isInsufficientObservationCount(occurrences)) {
      return `<td class="delta cp-map-comparison sponsor-delta-insufficient build-value-tooltip" data-value-tooltip="${INSUFFICIENT_DATA_TOOLTIP}">${text}</td>`;
    }
    return `<td class="delta cp-map-comparison" style="color:${deltaRangeColor(value, range.min, range.max)}">${text}</td>`;
  }
  return deltaCell(row, field, occurrences, range, text);
}
function hexesAvgCell(row, range) {
  if (mode === 'frequency') {
    const pct = frequencyFor(row, 'avg');
    if (!Number.isFinite(pct)) return '<td class="unavailable-cell">-</td>';
    return `<td class="build-value-tooltip" data-value-tooltip="${fmtInt(row.count_avg)} / ${fmtInt(row.denom_avg)}" style="color:${violetRangeColor(pct, range.min, range.max)}">${pct.toFixed(2)}%</td>`;
  }
  const value = Number(row.avg);
  if (!Number.isFinite(value)) return '<td class="unavailable-cell">-</td>';
  const ciN = Number(row.avg_ci95_n);
  const displayText = fmtSigned(value, 3, true);
  if (isInsufficientObservationCount(ciN)) {
    return `<td class="delta cp-cell sponsor-delta-insufficient build-value-tooltip" data-value-tooltip="${INSUFFICIENT_DATA_TOOLTIP}">${displayText}</td>`;
  }
  return `<td class="delta cp-cell delta-ci-cell"
    data-ci-low="${escapeAttr(row.avg_ci95_low ?? '')}" data-ci-high="${escapeAttr(row.avg_ci95_high ?? '')}"
    data-ci-n="${escapeAttr(row.avg_ci95_n ?? '')}" data-ci-color-scale="orange-green" data-ci-color-min="${escapeAttr(range.min ?? '')}"
    data-ci-color-max="${escapeAttr(range.max ?? '')}" style="color:${orangeGreenRangeColor(value, range.min, range.max)}">${displayText}</td>`;
}

function deltaCell(row, field, occurrences, range, text = null) {
  const value = Number(row[field]);
  if (!Number.isFinite(value)) return '<td class="unavailable-cell">-</td>';
  const displayText = text ?? fmtSigned(value);
  if (isInsufficientObservationCount(occurrences)) return `<td class="delta sponsor-delta-insufficient build-value-tooltip" data-value-tooltip="${INSUFFICIENT_DATA_TOOLTIP}">${displayText}</td>`;
  return `<td class="delta delta-ci-cell"
    data-ci-low="${escapeAttr(row[`${field}_ci95_low`] ?? '')}" data-ci-high="${escapeAttr(row[`${field}_ci95_high`] ?? '')}"
    data-ci-n="${escapeAttr(row[`${field}_ci95_n`] ?? '')}" data-ci-color-min="${escapeAttr(range.min ?? '')}"
    data-ci-color-max="${escapeAttr(range.max ?? '')}" style="color:${deltaRangeColor(value, range.min, range.max)}">${text ?? fmtSigned(value)}</td>`;
}

function renderLoading() {
  document.getElementById('tableMeta').textContent = '';
  document.getElementById('buildContent').innerHTML = '<div class="state-overlay"><div class="spinner"></div><div class="state-title">Fetching build statistics...</div></div>';
}
function renderError(error) {
  document.getElementById('buildContent').innerHTML = `<div class="state-overlay"><div class="state-title">Could not load build statistics</div><div class="state-sub">${escapeHtml(error.message || error)}</div></div>`;
}

function renderMapChips() {
  const host = document.getElementById('mapChips');
  if (!host) return;
  host.innerHTML = MAPS.map(([short, , full]) => `<button class="chip ${selectedMaps.includes(full) ? 'active' : ''}" data-map="${escapeAttr(full)}" onclick="toggleBuildMap(this.dataset.map)">${short}</button>`).join('');
}
function toggleBuildMap(map) {
  selectedMaps = selectedMaps.includes(map) ? selectedMaps.filter(item => item !== map) : [...selectedMaps, map];
  renderMapChips();
}
function selectAllMaps() { selectedMaps = MAPS.map(([, , full]) => full); renderMapChips(); }
function selectNoneMaps() { selectedMaps = []; renderMapChips(); }

function resetFilters() {
  const set = (id, value) => { const element = document.getElementById(id); if (element) element.value = value; };
  set('playerEloMin', '300'); set('playerEloMax', ''); set('opponentEloMin', '300'); set('opponentEloMax', '');
  set('dateFrom', '2025-01-01'); set('dateTo', '');
  selectedMaps = MAPS.map(([, , full]) => full);
  completedByMode = { delta: false, frequency: true };
  expanded = false;
  expandedRows = [];
  compareMode = 'raw';
  syncControls(); renderMapChips(); loadData(++token);
}
function applyFiltersFromSidebar() {
  rememberBuildCompleted();
  loadData(++token);
  document.getElementById('sidebar')?.classList.remove('open');
  document.getElementById('sidebarOverlay')?.classList.remove('active');
}

function fmtSigned(value, decimals = 3, plusMinusZero = false) {
  return formatSignedDeltaAdaptive(value, plusMinusZero);
}
function fmtInt(value) { return Number(value || 0).toLocaleString('en-US'); }
function escapeHtml(value) {
  return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}
const escapeAttr = escapeHtml;

const valueTooltip = document.getElementById('col-tooltip');
function buildTooltipSource(event) {
  return event.target.closest?.('.build-value-tooltip, .maps-custom-tip');
}
function positionBuildTooltip(event) {
  if (!valueTooltip) return;
  valueTooltip.style.left = `${Math.max(8, Math.min(event.clientX + 12, window.innerWidth - valueTooltip.offsetWidth - 8))}px`;
  valueTooltip.style.top = `${event.clientY + 18}px`;
}
document.addEventListener('mouseover', event => {
  if (!mounted || !valueTooltip) return;
  const source = buildTooltipSource(event);
  if (!source) return;
  valueTooltip.textContent = source.dataset.valueTooltip || source.dataset.tip || '';
  valueTooltip.style.display = 'block';
  positionBuildTooltip(event);
});
document.addEventListener('mousemove', event => {
  if (!mounted || !valueTooltip || !buildTooltipSource(event)) return;
  positionBuildTooltip(event);
});
document.addEventListener('mouseout', event => {
  if (!mounted || !valueTooltip) return;
  const source = buildTooltipSource(event);
  const destination = event.relatedTarget?.closest?.('.build-value-tooltip, .maps-custom-tip');
  if (source && destination !== source) valueTooltip.style.display = 'none';
});
