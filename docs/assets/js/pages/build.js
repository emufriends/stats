import {
  cappedNumericRange,
  deltaRangeColor,
  numericRange,
  playrateColor,
} from '../color-scales.js?v=20260704-9';

export const id = 'build';
export const title = 'Build';
export const navLabel = 'Build';

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
const STANDARD_BUCKETS = [['delta_0', '0'], ['delta_1', '1'], ['delta_2', '2'],
  ['delta_3', '3'], ['delta_4', '4'], ['delta_5_plus', '5+']];
const UNIQUE_BUCKETS = [['delta_0', 'No'], ['delta_1', 'Yes'], ['delta_empty', 'Empty']];
const API_URL = 'https://europe-west1-ark-nova-stats-dashboard.cloudfunctions.net/get-card-stats';
const SNAPSHOT_ROOT = 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/build/enclosures';

export const mainHtml = `
  <div class="main-header sponsor-endgames-main-header">
    <div class="table-meta" id="tableMeta"></div>
    <div class="maps-h2h-mode build-mode" role="group" aria-label="Build metric">
      <button type="button" class="active" data-mode="delta" onclick="setBuildMode('delta')">Elo &Delta;</button>
      <button type="button" data-mode="frequency" onclick="setBuildMode('frequency')">Frequency</button>
    </div>
  </div>
  <div class="attributes-bar endgames-tabs-bar">
    <div class="attributes-bar-header endgames-tabs-header">
      <div class="endgames-tabs build-tabs" role="tablist" aria-label="Build views">
        <button class="endgames-tab active" type="button" data-view="enclosures" onclick="setBuildView('enclosures')">Enclosures</button>
        <button class="endgames-tab" type="button" data-view="covered" onclick="setBuildView('covered')">Covered hexes</button>
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
  <div class="filter-group"><div class="toggle-row"><span class="toggle-label">Completed games only</span>
    <label class="toggle"><input type="checkbox" id="endGameToggle" onchange="rememberBuildCompleted()"><span class="toggle-track"></span></label>
  </div></div>
  <hr class="divider" />
  <div class="filter-action-stack"><button class="apply-btn" onclick="applyFiltersFromSidebar()">Apply filters</button></div>`;

let mounted = false;
let token = 0;
let isMW = 1;
let mode = 'delta';
let view = 'enclosures';
let rows = [];
let selectedMaps = MAPS.map(([, full]) => full);
let completedByMode = { delta: false, frequency: true };

export function mount({ dataset = 1 } = {}) {
  mounted = true;
  token += 1;
  isMW = Number(dataset) === 0 ? 0 : 1;
  mode = 'delta';
  view = 'enclosures';
  rows = [];
  selectedMaps = MAPS.map(([, full]) => full);
  completedByMode = { delta: false, frequency: true };
  bindHandlers();
  renderMapChips();
  syncCompleted();
  renderTabs();
  loadData(token);
}

export function unmount() { mounted = false; token += 1; }
export function setDataset(value) {
  isMW = Number(value) === 0 ? 0 : 1;
  loadData(++token);
}

function bindHandlers() {
  Object.assign(window, {
    setBuildMode, setBuildView, rememberBuildCompleted, resetFilters,
    applyFiltersFromSidebar, selectAllMaps, selectNoneMaps, toggleBuildMap,
  });
}

function setBuildMode(next) {
  rememberBuildCompleted();
  mode = next === 'frequency' ? 'frequency' : 'delta';
  document.querySelectorAll('.build-mode button').forEach(button => button.classList.toggle('active', button.dataset.mode === mode));
  syncCompleted();
  if (view === 'enclosures') loadData(++token);
}

function setBuildView(next) {
  view = next === 'covered' ? 'covered' : 'enclosures';
  renderTabs();
  if (view === 'covered') renderCovered();
  else if (rows.length) renderTables();
  else loadData(++token);
}

function renderTabs() {
  document.querySelectorAll('.build-tabs .endgames-tab').forEach(button => button.classList.toggle('active', button.dataset.view === view));
  document.querySelector('.build-mode')?.classList.toggle('is-hidden', view !== 'enclosures');
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
    stats_page: 'build', is_mw: isMW, maps: selectedMaps,
    player_elo_min: value('playerEloMin') === '' ? 0 : Number(value('playerEloMin')),
    player_elo_max: value('playerEloMax') === '' ? null : Number(value('playerEloMax')),
    opponent_elo_min: value('opponentEloMin') === '' ? 0 : Number(value('opponentEloMin')),
    opponent_elo_max: value('opponentEloMax') === '' ? null : Number(value('opponentEloMax')),
    date_from: value('dateFrom') || '2025-01-01', date_to: value('dateTo') || null,
    end_game_triggered: completedByMode[mode] ? true : null,
  };
}

function isDefault(params) {
  return params.player_elo_min === 300 && params.player_elo_max === null &&
    params.opponent_elo_min === 300 && params.opponent_elo_max === null &&
    params.date_from === '2025-01-01' && params.date_to === null &&
    selectedMaps.length === MAPS.length &&
    params.end_game_triggered === (mode === 'frequency' ? true : null);
}

async function loadData(activeToken) {
  renderLoading();
  try {
    const params = getParams();
    let response;
    if (isDefault(params)) {
      try {
        response = await fetch(`${SNAPSHOT_ROOT}/${mode}/default-${isMW ? 'mw' : 'base'}.json`, { cache: 'no-store' });
        if (!response.ok) throw new Error('Snapshot unavailable');
      } catch {
        response = await fetch(API_URL, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(params),
        });
      }
    } else {
      response = await fetch(API_URL, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(params),
      });
    }
    const payload = await response.json();
    if (!response.ok || payload.status !== 'ok') throw new Error(payload.message || `Request failed (${response.status})`);
    if (!mounted || activeToken !== token) return;
    rows = payload.data || [];
    renderTables();
  } catch (error) {
    if (mounted && activeToken === token) renderError(error);
  }
}

function renderTables() {
  if (view !== 'enclosures') return;
  const standard = rows.filter(row => row.category === 'standard');
  const unique = rows.filter(row => row.category === 'unique');
  document.getElementById('tableMeta').innerHTML = `<strong>${rows.length}</strong> enclosure types`;
  const host = document.getElementById('buildContent');
  host.innerHTML = `<div class="build-tables">
    ${tableHtml('Standard enclosures', standard, STANDARD_BUCKETS, false)}
    ${tableHtml('Unique enclosures', unique, UNIQUE_BUCKETS, true)}
  </div>`;
}

function tableHtml(titleText, data, buckets, unique) {
  const ranges = Object.fromEntries(buckets.map(([field]) => [
    field,
    mode === 'delta'
      ? cappedNumericRange(data.filter(row => count(row, field) >= 1000), row => row[field])
      : numericRange(data.filter(row => possible(row, field)), row => frequency(row, field)),
  ]));
  const prefix = mode === 'delta' ? '\u0394' : 'f';
  return `<div class="build-table-panel"><div class="build-table-title">${titleText}</div><div class="table-scroll">
    <table class="sponsor-endgames-table build-table"><thead><tr>
      <th>${unique ? 'Enclosure' : 'Size'}</th>
      ${buckets.map(([, label]) => `<th>${prefix} (${label})</th>`).join('')}
    </tr></thead><tbody>${data.map(row => `<tr><td class="sponsor-name-cell">${row.enclosure}</td>
      ${buckets.map(([field]) => buildCell(row, field, ranges[field])).join('')}</tr>`).join('')}
    </tbody></table></div></div>`;
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

function buildCell(row, field, range) {
  if (!possible(row, field)) return '<td class="unavailable-cell">-</td>';
  const occurrences = count(row, field);
  if (mode === 'frequency') {
    const pct = frequency(row, field);
    if (!Number.isFinite(pct)) return '<td class="unavailable-cell">-</td>';
    const total = denominator(row, field);
    const color = field === 'delta_empty' ? 'rgba(153, 102, 204, .72)' : playrateColor(pct, range.min, range.max);
    return `<td class="build-value-tooltip" data-value-tooltip="${occurrences.toLocaleString('en-US')} / ${total.toLocaleString('en-US')}" style="color:${color}">${pct.toFixed(2)}%</td>`;
  }
  const value = Number(row[field]);
  if (!Number.isFinite(value)) return '<td class="unavailable-cell">-</td>';
  if (occurrences < 1000) return `<td class="delta sponsor-delta-insufficient build-value-tooltip" data-value-tooltip="Insufficient data (fewer than 1,000 observations).">(${signed(value)})</td>`;
  return `<td class="delta delta-ci-cell"
    data-ci-low="${escapeHtml(row[`${field}_ci95_low`] ?? '')}" data-ci-high="${escapeHtml(row[`${field}_ci95_high`] ?? '')}"
    data-ci-n="${escapeHtml(row[`${field}_ci95_n`] ?? '')}" data-ci-color-min="${escapeHtml(range.min ?? '')}"
    data-ci-color-max="${escapeHtml(range.max ?? '')}" style="color:${deltaRangeColor(value, range.min, range.max)}">${signed(value)}</td>`;
}

function renderCovered() {
  document.getElementById('tableMeta').textContent = '';
  document.getElementById('buildContent').innerHTML = '<div class="build-placeholder"><div class="state-title">Covered hexes</div><div class="state-sub">Statistics for this view will be added later.</div></div>';
}
function renderLoading() {
  document.getElementById('buildContent').innerHTML = '<div class="state-overlay"><div class="spinner"></div><div class="state-title">Fetching enclosure statistics...</div></div>';
}
function renderError(error) {
  document.getElementById('buildContent').innerHTML = `<div class="state-overlay"><div class="state-title">Could not load enclosure statistics</div><div class="state-sub">${escapeHtml(error.message || error)}</div></div>`;
}

function renderMapChips() {
  const host = document.getElementById('mapChips');
  if (!host) return;
  host.innerHTML = MAPS.map(([short, full]) => `<button class="chip ${selectedMaps.includes(full) ? 'active' : ''}" data-map="${escapeHtml(full)}" onclick="toggleBuildMap(this.dataset.map)">${short}</button>`).join('');
}
function toggleBuildMap(map) {
  selectedMaps = selectedMaps.includes(map) ? selectedMaps.filter(item => item !== map) : [...selectedMaps, map];
  renderMapChips();
}
function selectAllMaps() { selectedMaps = MAPS.map(([, full]) => full); renderMapChips(); }
function selectNoneMaps() { selectedMaps = []; renderMapChips(); }

function resetFilters() {
  const set = (id, value) => { const element = document.getElementById(id); if (element) element.value = value; };
  set('playerEloMin', '300'); set('playerEloMax', ''); set('opponentEloMin', '300'); set('opponentEloMax', '');
  set('dateFrom', '2025-01-01'); set('dateTo', '');
  selectedMaps = MAPS.map(([, full]) => full);
  completedByMode = { delta: false, frequency: true };
  syncCompleted(); renderMapChips(); loadData(++token);
}
function applyFiltersFromSidebar() {
  rememberBuildCompleted();
  loadData(++token);
  document.getElementById('sidebar')?.classList.remove('open');
  document.getElementById('sidebarOverlay')?.classList.remove('active');
}
function signed(value) { return `${Number(value) >= 0 ? '+' : ''}${Number(value).toFixed(3)}`; }
function escapeHtml(value) {
  return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}

const valueTooltip = document.getElementById('col-tooltip');
document.addEventListener('mouseover', event => {
  if (!mounted || !valueTooltip) return;
  const cell = event.target.closest?.('.build-value-tooltip');
  if (!cell) return;
  valueTooltip.textContent = cell.dataset.valueTooltip || '';
  valueTooltip.style.display = 'block';
});
document.addEventListener('mousemove', event => {
  if (!mounted || !valueTooltip || !event.target.closest?.('.build-value-tooltip')) return;
  valueTooltip.style.left = `${Math.max(8, Math.min(event.clientX + 12, window.innerWidth - valueTooltip.offsetWidth - 8))}px`;
  valueTooltip.style.top = `${event.clientY + 18}px`;
});
document.addEventListener('mouseout', event => {
  if (!mounted || !valueTooltip) return;
  const source = event.target.closest?.('.build-value-tooltip');
  const destination = event.relatedTarget?.closest?.('.build-value-tooltip');
  if (source && destination !== source) valueTooltip.style.display = 'none';
});
