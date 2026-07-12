import { cappedNumericRange, deltaRangeColor, frequencyColor } from '../color-scales.js?v=20260711-1';
import {
  INSUFFICIENT_DATA_TOOLTIP,
  formatSignedDeltaAdaptive,
  isInsufficientObservationCount,
} from '../table-cells.js?v=20260712-4';
import { loadStats } from '../snapshot-cache.js?v=20260712-1';

export const id = 'predictors';
export const title = 'Predictors';
export const navLabel = 'Predictors';

const API_URL = 'https://europe-west1-ark-nova-stats-dashboard.cloudfunctions.net/get-card-stats';
const SNAPSHOT_ROOT = 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/predictors';
const MAPS = [
  ['1a', 'Map 1a: Observation Tower'], ['2a', 'Map 2a: Outdoor Areas'],
  ['3a', 'Map 3a: Silver Lake'], ['4a', 'Map 4a: Commercial Harbor'],
  ['5a', 'Map 5a: Park Restaurant'], ['6a', 'Map 6a: Research Institute'],
  ['7a', 'Map 7a: Ice Cream Parlors'], ['8a', 'Map 8a: Hollywood Hills'],
  ['9', 'Map 9: Geographical Zoo'], ['10', 'Map 10: Rescue Station'],
  ['11', 'Map 11: Caves'], ['12', 'Map 12: Artificial Intelligence'],
  ['13', 'Map 13: Drawing Board'], ['14', 'Map 14: Lagoon'],
  ['T1', 'Map T1: Tournament 1'],
];
export const mainHtml = `
  <div class="main-header sponsor-endgames-main-header">
    <div class="table-meta" id="tableMeta"></div>
    <div class="maps-h2h-mode predictors-mode is-hidden" role="group" aria-label="Specific predictor metric">
      <button type="button" class="active" data-mode="delta" onclick="setPredictorsMode('delta')">Elo &Delta;</button>
      <button type="button" data-mode="frequency" onclick="setPredictorsMode('frequency')">Frequency</button>
    </div>
  </div>
  <div class="attributes-bar endgames-tabs-bar">
    <div class="attributes-bar-header endgames-tabs-header">
      <div class="endgames-tabs predictors-tabs" role="tablist" aria-label="Predictors views">
        <button class="endgames-tab active" data-view="general" onclick="setPredictorsView('general')">General</button>
        <button class="endgames-tab" data-view="icon" onclick="setPredictorsView('icon')">Icon</button>
        <button class="endgames-tab" data-view="specific" onclick="setPredictorsView('specific')">Specific</button>
      </div>
    </div>
  </div>
  <div class="table-wrap"><div class="table-scroll">
    <table id="statsTable" class="sponsor-endgames-table predictors-table">
      <thead id="tableHead"></thead><tbody id="tableBody"></tbody>
    </table>
  </div></div>`;

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
  <div id="predictorsCompletedBlock">
    <hr class="divider" />
    <div class="filter-group"><div class="toggle-row"><span class="toggle-label">Completed games only</span>
      <label class="toggle"><input type="checkbox" id="endGameToggle"><span class="toggle-track"></span></label>
    </div></div>
  </div>
  <hr class="divider" />
  <div class="filter-action-stack"><button class="apply-btn" onclick="applyFiltersFromSidebar()">Apply filters</button></div>`;

let mounted = false;
let token = 0;
let isMW = 1;
let activeView = 'general';
let mode = 'delta';
let rows = [];
let currentSort = { col: 'condition', dir: 'asc' };
let selectedMaps = MAPS.map(([, full]) => full);

export function mount({ dataset = 1 } = {}) {
  mounted = true; token += 1; isMW = Number(dataset) === 0 ? 0 : 1;
  activeView = 'general'; mode = 'delta'; rows = []; currentSort = { col: 'condition', dir: 'asc' };
  selectedMaps = MAPS.map(([, full]) => full);
  Object.assign(window, { setPredictorsView, setPredictorsMode, sortPredictors, resetFilters, applyFiltersFromSidebar, selectAllMaps, selectNoneMaps, togglePredictorMap });
  renderMapChips(); syncTabs(); loadData(token);
}
export function unmount() { mounted = false; token += 1; }
export function setDataset(value) { isMW = Number(value) === 0 ? 0 : 1; loadData(++token); }

function setPredictorsView(view) {
  activeView = ['general', 'icon', 'specific'].includes(view) ? view : 'general';
  mode = 'delta';
  currentSort = { col: 'condition', dir: 'asc' };
  syncTabs(); loadData(++token);
}
function setPredictorsMode(next) {
  if (activeView !== 'specific') return;
  mode = next === 'frequency' ? 'frequency' : 'delta';
  currentSort = { col: 'condition', dir: 'asc' };
  syncTabs(); render();
}
function syncTabs() {
  document.querySelectorAll('.predictors-tabs .endgames-tab').forEach(btn => btn.classList.toggle('active', btn.dataset.view === activeView));
  document.getElementById('predictorsCompletedBlock')?.classList.toggle('is-hidden', activeView !== 'specific');
  document.querySelector('.predictors-mode')?.classList.toggle('is-hidden', activeView !== 'specific');
  document.querySelectorAll('.predictors-mode button').forEach(button => button.classList.toggle('active', button.dataset.mode === mode));
}
function params() {
  const v = id => document.getElementById(id)?.value ?? '';
  return {
    stats_page: 'predictors', predictors_view: activeView, is_mw: isMW, maps: selectedMaps,
    player_elo_min: v('playerEloMin') === '' ? 0 : Number(v('playerEloMin')),
    player_elo_max: v('playerEloMax') === '' ? null : Number(v('playerEloMax')),
    opponent_elo_min: v('opponentEloMin') === '' ? 0 : Number(v('opponentEloMin')),
    opponent_elo_max: v('opponentEloMax') === '' ? null : Number(v('opponentEloMax')),
    date_from: v('dateFrom') || '2025-01-01', date_to: v('dateTo') || null,
    completed_only: activeView === 'specific' && document.getElementById('endGameToggle')?.checked ? true : null,
  };
}
function isDefault(p) {
  return p.player_elo_min === 300 && p.player_elo_max === null &&
    p.opponent_elo_min === 300 && p.opponent_elo_max === null &&
    p.date_from === '2025-01-01' && p.date_to === null && p.completed_only === null &&
    selectedMaps.length === MAPS.length;
}
async function loadData(activeToken) {
  renderLoading();
  try {
    const p = params();
    const payload = await loadStats(
      p,
      isDefault(p) ? `${SNAPSHOT_ROOT}/${activeView}/default-${isMW ? 'mw' : 'base'}.json` : null,
    );
    if (!mounted || activeToken !== token) return;
    rows = payload.data || []; render();
  } catch (error) { if (mounted && activeToken === token) renderError(error); }
}
function renderHead() {
  const metric = mode === 'frequency' && activeView === 'specific' ? 'frequency' : 'delta';
  const metricHeader = metric === 'frequency'
    ? 'Frequency<span class="col-tip" data-tip="percentage of filtered player observations where this condition is true">?</span>'
    : 'Elo &Delta;<span class="col-tip" data-tip="average Elo delta when this condition is true">?</span>';
  document.getElementById('tableHead').innerHTML = `<tr>
    <th class="${headerSortedClass('condition')}" onclick="sortPredictors('condition')" style="width:80%;text-align:center;">Condition<span class="${arrowClass('condition')}">${arrow('condition')}</span></th>
    <th class="${headerSortedClass(metric)}" onclick="sortPredictors('${metric}')" style="width:20%;text-align:center;">${metricHeader}<span class="${arrowClass(metric)}">${arrow(metric)}</span></th>
  </tr>`;
}
function render() {
  renderHead();
  const range = cappedNumericRange(rows.filter(row => !isInsufficientObservationCount(row.count)), row => row.delta);
  const sorted = [...rows].sort(compareRows);
  document.getElementById('tableMeta').innerHTML = `<strong>${rows.length}</strong> predictors`;
  document.getElementById('tableBody').innerHTML = sorted.map(row => `<tr>
    <td class="sponsor-name-cell">${escapeHtml(row.condition)}</td>${mode === 'frequency' && activeView === 'specific' ? frequencyCell(row) : deltaCell(row, range)}
  </tr>`).join('');
}
function compareRows(a, b) {
  const direction = currentSort.dir === 'asc' ? 1 : -1;
  if (currentSort.col === 'condition') return (a.sort_order - b.sort_order) * direction;
  const av = currentSort.col === 'frequency' ? frequency(a) : Number(a.delta);
  const bv = currentSort.col === 'frequency' ? frequency(b) : Number(b.delta);
  if (!Number.isFinite(av) && !Number.isFinite(bv)) return a.sort_order - b.sort_order;
  if (!Number.isFinite(av)) return 1;
  if (!Number.isFinite(bv)) return -1;
  return (av - bv) * direction || a.sort_order - b.sort_order;
}
function sortPredictors(col) {
  if (currentSort.col === col) currentSort.dir = currentSort.dir === 'asc' ? 'desc' : 'asc';
  else currentSort = { col, dir: col === 'condition' ? 'asc' : 'desc' };
  render();
}
function deltaCell(row, range) {
  const value = Number(row.delta);
  if (!Number.isFinite(value)) return '<td class="unavailable-cell">-</td>';
  if (isInsufficientObservationCount(row.count)) return `<td class="delta sponsor-delta-insufficient build-value-tooltip" data-value-tooltip="${INSUFFICIENT_DATA_TOOLTIP}">${fmtSigned(value)}</td>`;
  return `<td class="delta delta-ci-cell" data-ci-low="${escapeAttr(row.delta_ci95_low ?? '')}" data-ci-high="${escapeAttr(row.delta_ci95_high ?? '')}" data-ci-n="${escapeAttr(row.delta_ci95_n ?? '')}" data-ci-color-min="${escapeAttr(range.min ?? '')}" data-ci-color-max="${escapeAttr(range.max ?? '')}" style="color:${deltaRangeColor(value, range.min, range.max)}">${fmtSigned(value)}</td>`;
}
function frequency(row) {
  const denominator = Number(row.denominator);
  return denominator > 0 ? 100 * Number(row.count || 0) / denominator : Number.NaN;
}
function frequencyCell(row) {
  const value = frequency(row);
  if (!Number.isFinite(value)) return '<td class="unavailable-cell">-</td>';
  return `<td class="build-value-tooltip" data-value-tooltip="${fmtInt(row.count)} / ${fmtInt(row.denominator)}" style="color:${frequencyColor(value)}">${value.toFixed(2)}%</td>`;
}
function arrow(col) { return currentSort.col === col ? (currentSort.dir === 'desc' ? '\u2193' : '\u2191') : '\u2195'; }
function headerSortedClass(col) { return currentSort.col === col ? 'sorted' : ''; }
function arrowClass(col) { return currentSort.col === col ? 'sort-arrow active' : 'sort-arrow'; }
function renderLoading() { renderHead(); document.getElementById('tableBody').innerHTML = '<tr><td colspan="2"><div class="state-overlay"><div class="spinner"></div><div class="state-title">Fetching predictors...</div></div></td></tr>'; }
function renderError(error) { document.getElementById('tableBody').innerHTML = `<tr><td colspan="2"><div class="state-overlay"><div class="state-title">Could not load predictors</div><div class="state-sub">${escapeHtml(error.message || error)}</div></div></td></tr>`; }
function renderMapChips() {
  const host = document.getElementById('mapChips'); if (!host) return;
  host.innerHTML = MAPS.map(([short, full]) => `<button class="chip ${selectedMaps.includes(full) ? 'active' : ''}" data-map="${escapeAttr(full)}" onclick="togglePredictorMap(this.dataset.map)">${short}</button>`).join('');
}
function togglePredictorMap(map) { selectedMaps = selectedMaps.includes(map) ? selectedMaps.filter(item => item !== map) : [...selectedMaps, map]; renderMapChips(); }
function selectAllMaps() { selectedMaps = MAPS.map(([, full]) => full); renderMapChips(); }
function selectNoneMaps() { selectedMaps = []; renderMapChips(); }
function resetFilters() {
  const set = (id, value) => { const el = document.getElementById(id); if (el) el.value = value; };
  set('playerEloMin', '300'); set('playerEloMax', ''); set('opponentEloMin', '300'); set('opponentEloMax', '');
  set('dateFrom', '2025-01-01'); set('dateTo', '');
  const completed = document.getElementById('endGameToggle'); if (completed) completed.checked = false;
  selectedMaps = MAPS.map(([, full]) => full); renderMapChips(); loadData(++token);
}
function applyFiltersFromSidebar() {
  loadData(++token); document.getElementById('sidebar')?.classList.remove('open'); document.getElementById('sidebarOverlay')?.classList.remove('active');
}
function fmtSigned(value) { return formatSignedDeltaAdaptive(value); }
function fmtInt(value) { return Number(value || 0).toLocaleString('en-US'); }
function escapeHtml(value) { return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;'); }
const escapeAttr = escapeHtml;

// Predictors uses the shared tooltip element, but its insufficient/frequency
// cells are not CI cells and therefore need their own delegated value path.
const predictorTooltip = document.getElementById('col-tooltip');
function predictorTooltipSource(event) {
  return event.target.closest?.('.build-value-tooltip, .predictors-table .col-tip');
}
function positionPredictorTooltip(event) {
  if (!predictorTooltip) return;
  predictorTooltip.style.left = `${Math.max(8, Math.min(event.clientX + 12, window.innerWidth - predictorTooltip.offsetWidth - 8))}px`;
  predictorTooltip.style.top = `${event.clientY + 18}px`;
}
document.addEventListener('mouseover', event => {
  if (!mounted || !predictorTooltip) return;
  const source = predictorTooltipSource(event);
  if (!source) return;
  predictorTooltip.textContent = source.dataset.valueTooltip || source.dataset.tip || '';
  predictorTooltip.style.display = 'block';
  positionPredictorTooltip(event);
});
document.addEventListener('mousemove', event => {
  if (!mounted || !predictorTooltip || !predictorTooltipSource(event)) return;
  positionPredictorTooltip(event);
});
document.addEventListener('mouseout', event => {
  if (!mounted || !predictorTooltip) return;
  const source = predictorTooltipSource(event);
  if (source && !source.contains(event.relatedTarget)) predictorTooltip.style.display = 'none';
});
