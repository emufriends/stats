import {
  cappedNumericRange,
  deltaRangeColor,
  numericRange,
  orangeGreenRangeColor,
  playrateColor,
} from '../color-scales.js?v=20260704-8';

export const id = 'icons';
export const title = 'Icons';
export const navLabel = 'Icons';

const ICONS = [
  'Birds', 'Herbivores', 'Predators', 'Primates', 'Reptiles', 'Sea Animals',
  'Bears', 'Petting Zoo Animals', 'Africa', 'Americas', 'Asia', 'Australia',
  'Europe', 'Rock', 'Water', 'Science',
];
const BUCKETS = [
  ['delta_0', '0'], ['delta_1', '1'], ['delta_2', '2'], ['delta_3', '3'],
  ['delta_4', '4'], ['delta_5', '5'], ['delta_6', '6'], ['delta_7_plus', '7+'],
];
const VALID_MAPS = [
  ['1a', 'Map 1a: Observation Tower'], ['2a', 'Map 2a: Outdoor Areas'],
  ['3a', 'Map 3a: Silver Lake'], ['4a', 'Map 4a: Commercial Harbor'],
  ['5a', 'Map 5a: Park Restaurant'], ['6a', 'Map 6a: Research Institute'],
  ['7a', 'Map 7a: Ice Cream Parlors'], ['8a', 'Map 8a: Hollywood Hills'],
  ['9', 'Map 9: Geographical Zoo'], ['10', 'Map 10: Rescue Station'],
  ['11', 'Map 11: Caves'], ['12', 'Map 12: Artificial Intelligence'],
  ['13', 'Map 13: Drawing Board'], ['14', 'Map 14: Lagoon'],
  ['T1', 'Map T1: Tournament 1'],
];
const API_URL = 'https://europe-west1-ark-nova-stats-dashboard.cloudfunctions.net/get-card-stats';
const SNAPSHOTS = {
  1: 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/icons/default-mw.json?v=20260704-1',
  0: 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/icons/default-base.json?v=20260704-1',
};

export const mainHtml = `
  <div class="main-header sponsor-endgames-main-header">
    <div class="table-meta" id="tableMeta"></div>
    <div class="maps-h2h-mode sponsor-endgames-mode icons-mode" role="group" aria-label="Icons metric">
      <button type="button" class="active" data-mode="delta" onclick="setIconsMode('delta')">Elo &Delta;</button>
      <button type="button" data-mode="frequency" onclick="setIconsMode('frequency')">Frequency</button>
    </div>
  </div>
  <div class="attributes-bar endgames-tabs-bar icons-filter-bar">
    <div class="icons-filter-heading">
      <span>Icons</span>
      <span class="map-select-all-none">(<span class="map-toggle-link" onclick="selectAllIcons()">all</span> / <span class="map-toggle-link" onclick="selectNoneIcons()">none</span>)</span>
    </div>
    <div class="icons-filter-scroll"><div class="icons-filter-chips" id="iconFilterChips"></div></div>
  </div>
  <div class="table-wrap">
    <div class="table-scroll">
      <table id="statsTable" class="sponsor-endgames-table icons-table">
        <thead id="tableHead"></thead>
        <tbody id="tableBody"><tr><td colspan="11"><div class="state-overlay">
          <div class="spinner"></div><div class="state-title">Fetching data...</div>
          <div class="state-sub">Querying icon statistics.</div>
        </div></td></tr></tbody>
      </table>
    </div>
  </div>`;

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
    <input class="date-input" type="text" inputmode="numeric" pattern="\\d{4}-\\d{2}-\\d{2}" placeholder="yyyy-mm-dd" id="dateFrom" value="2025-01-01" />
    <input class="date-input" type="text" inputmode="numeric" pattern="\\d{4}-\\d{2}-\\d{2}" placeholder="yyyy-mm-dd" id="dateTo" />
  </div>
  <hr class="divider" />
  <div class="filter-action-stack"><button class="apply-btn" id="applyBtn" onclick="applyFiltersFromSidebar()">Apply filters</button></div>`;

let mounted = false;
let token = 0;
let isMW = 1;
let mode = 'delta';
let rows = [];
let selectedIcons = new Set(ICONS);
let selectedMaps = VALID_MAPS.map(([, full]) => full);
let sort = { col: 'amount', dir: 'desc' };
const snapshotCache = { 0: null, 1: null };

export function mount({ dataset = 1 } = {}) {
  mounted = true;
  token += 1;
  isMW = Number(dataset) === 0 ? 0 : 1;
  mode = 'delta';
  selectedIcons = new Set(ICONS);
  selectedMaps = VALID_MAPS.map(([, full]) => full);
  sort = { col: 'amount', dir: 'desc' };
  bindHandlers();
  renderIconChips();
  renderMapChips();
  applyFilters(token);
}

export function unmount() {
  mounted = false;
  token += 1;
}

export function setDataset(dataset) {
  isMW = Number(dataset) === 0 ? 0 : 1;
  applyFilters(++token);
}

function bindHandlers() {
  Object.assign(window, {
    applyFiltersFromSidebar,
    resetFilters,
    selectAllIcons,
    selectNoneIcons,
    selectAllMaps,
    selectNoneMaps,
    setIconsMode,
    sortIcons,
    toggleIconChip,
    toggleMapChip,
  });
}

function setIconsMode(next) {
  mode = next === 'frequency' ? 'frequency' : 'delta';
  document.querySelectorAll('.icons-mode button').forEach(button => {
    button.classList.toggle('active', button.dataset.mode === mode);
  });
  renderTable();
}

function sortIcons(col) {
  sort = sort.col === col
    ? { col, dir: sort.dir === 'desc' ? 'asc' : 'desc' }
    : { col, dir: col === 'icon' ? 'asc' : 'desc' };
  renderTable();
}

function params() {
  const value = id => document.getElementById(id)?.value || '';
  return {
    stats_page: 'icons',
    is_mw: isMW,
    maps: selectedMaps,
    player_elo_min: Number(value('playerEloMin') || 300),
    player_elo_max: value('playerEloMax') ? Number(value('playerEloMax')) : null,
    opponent_elo_min: Number(value('opponentEloMin') || 300),
    opponent_elo_max: value('opponentEloMax') ? Number(value('opponentEloMax')) : null,
    date_from: value('dateFrom') || '2025-01-01',
    date_to: value('dateTo') || null,
  };
}

function isDefault(p) {
  return p.player_elo_min === 300 && p.player_elo_max === null &&
    p.opponent_elo_min === 300 && p.opponent_elo_max === null &&
    p.date_from === '2025-01-01' && p.date_to === null &&
    selectedMaps.length === VALID_MAPS.length;
}

async function applyFilters(activeToken = token) {
  renderLoading();
  if (!selectedMaps.length) {
    rows = [];
    renderTable();
    return;
  }
  try {
    const p = params();
    let payload;
    if (isDefault(p)) {
      try {
        payload = snapshotCache[isMW] || await fetchJson(SNAPSHOTS[isMW]);
        snapshotCache[isMW] = payload;
      } catch {
        payload = await fetchApi(p);
      }
    } else {
      payload = await fetchApi(p);
    }
    if (!mounted || activeToken !== token) return;
    rows = Array.isArray(payload.data) ? payload.data : [];
    assignRanks();
    renderTable();
  } catch (error) {
    if (mounted && activeToken === token) renderError(error);
  }
}

async function fetchJson(url) {
  const response = await fetch(url, { cache: 'no-store' });
  if (!response.ok) throw new Error(`Snapshot request failed (${response.status})`);
  return response.json();
}

async function fetchApi(p) {
  const response = await fetch(API_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(p),
  });
  const payload = await response.json();
  if (!response.ok || payload.status !== 'ok') throw new Error(payload.message || `API request failed (${response.status})`);
  return payload;
}

function assignRanks() {
  [...rows].sort((a, b) => compareValues(b.amount, a.amount) || String(a.icon).localeCompare(String(b.icon)))
    .forEach((row, index) => { row.global_rank = index + 1; });
}

function visibleRows() {
  return rows.filter(row => selectedIcons.has(row.icon));
}

function sortedRows(data) {
  const direction = sort.dir === 'desc' ? -1 : 1;
  return [...data].sort((a, b) => {
    let av = sort.col === 'icon' ? a.icon : sortValue(a, sort.col);
    let bv = sort.col === 'icon' ? b.icon : sortValue(b, sort.col);
    if (typeof av === 'string' || typeof bv === 'string') return String(av).localeCompare(String(bv)) * direction;
    return compareValues(av, bv) * direction || String(a.icon).localeCompare(String(b.icon));
  });
}

function sortValue(row, field) {
  if (mode === 'frequency' && field.startsWith('delta_')) return frequency(row, field);
  return row[field];
}

function compareValues(a, b) {
  const an = Number(a);
  const bn = Number(b);
  if (!Number.isFinite(an) && !Number.isFinite(bn)) return 0;
  if (!Number.isFinite(an)) return -1;
  if (!Number.isFinite(bn)) return 1;
  return an - bn;
}

function renderTable() {
  renderHead();
  const data = sortedRows(visibleRows());
  const meta = document.getElementById('tableMeta');
  if (meta) meta.innerHTML = `Showing <strong>${data.length}</strong> of <strong>${rows.length}</strong> icons`;
  const body = document.getElementById('tableBody');
  if (!body) return;
  if (!data.length) {
    body.innerHTML = '<tr><td colspan="11"><div class="state-overlay"><div class="state-title">No icons selected</div><div class="state-sub">Enable at least one icon above the table.</div></div></td></tr>';
    return;
  }
  const amountRange = numericRange(rows, row => row.amount);
  const deltaRanges = Object.fromEntries(BUCKETS.map(([field]) => [
    field, cappedNumericRange(rows.filter(row => count(row, field) >= 1000), row => row[field]),
  ]));
  const frequencyRanges = Object.fromEntries(BUCKETS.map(([field]) => [
    field, numericRange(rows, row => frequency(row, field)),
  ]));
  body.innerHTML = data.map(row => `
    <tr>
      <td class="rank-cell">${row.global_rank ?? '-'}</td>
      <td class="sponsor-name-cell">${escapeHtml(row.icon)}</td>
      <td class="sponsor-avg-cell" style="color:${orangeGreenRangeColor(row.amount, amountRange.min, amountRange.max)}">${format(row.amount, 2)}</td>
      ${BUCKETS.map(([field]) => bucketCell(row, field, deltaRanges[field], frequencyRanges[field])).join('')}
    </tr>`).join('');
}

function renderHead() {
  const head = document.getElementById('tableHead');
  if (!head) return;
  const prefix = mode === 'frequency' ? 'f' : '\u0394';
  head.innerHTML = `<tr>
    <th style="width:5%;text-align:center;">#</th>
    ${header('icon', 'Icon', '18%')}
    ${header('amount', 'Amount', '10%')}
    ${BUCKETS.map(([field, label]) => header(field, `${prefix} (${label})`, '8.375%')).join('')}
  </tr>`;
}

function header(field, label, width) {
  const active = sort.col === field;
  const arrow = active ? (sort.dir === 'desc' ? '\u2193' : '\u2191') : '\u2195';
  return `<th class="${active ? 'sorted' : ''}" onclick="sortIcons('${field}')" style="width:${width};text-align:center;">
    ${label}<span class="sort-arrow${active ? ' active' : ''}">${arrow}</span></th>`;
}

function bucketCell(row, field, deltaRange, frequencyRange) {
  const occurrences = count(row, field);
  if (mode === 'frequency') {
    const pct = frequency(row, field);
    if (!Number.isFinite(pct)) return '<td class="unavailable-cell">-</td>';
    const tip = `${occurrences.toLocaleString('en-US')} / ${Number(row.n_total || 0).toLocaleString('en-US')}`;
    return `<td class="sponsor-frequency-cell icons-value-tooltip" data-value-tooltip="${escapeAttr(tip)}"
      style="color:${playrateColor(pct, frequencyRange.min, frequencyRange.max)}">${pct.toFixed(2)}%</td>`;
  }
  const value = Number(row[field]);
  if (!Number.isFinite(value)) return '<td class="unavailable-cell">-</td>';
  if (occurrences < 1000) {
    return `<td class="delta sponsor-delta-insufficient icons-value-tooltip"
      data-value-tooltip="Insufficient data (fewer than 1,000 observations).">(${signed(value)})</td>`;
  }
  return `<td class="delta delta-ci-cell"
    data-ci-low="${escapeAttr(row[`${field}_ci95_low`] ?? '')}"
    data-ci-high="${escapeAttr(row[`${field}_ci95_high`] ?? '')}"
    data-ci-n="${escapeAttr(row[`${field}_ci95_n`] ?? '')}"
    data-ci-color-min="${escapeAttr(deltaRange.min ?? '')}"
    data-ci-color-max="${escapeAttr(deltaRange.max ?? '')}"
    style="color:${deltaRangeColor(value, deltaRange.min, deltaRange.max)}">${signed(value)}</td>`;
}

function count(row, field) {
  const value = Number(row[field.replace('delta_', 'count_')]);
  return Number.isFinite(value) ? value : 0;
}

function frequency(row, field) {
  const total = Number(row.n_total);
  return total > 0 ? 100 * count(row, field) / total : Number.NaN;
}

function renderIconChips() {
  const container = document.getElementById('iconFilterChips');
  if (!container) return;
  container.innerHTML = ICONS.map(icon => `<button class="chip ${selectedIcons.has(icon) ? 'active' : ''}"
    onclick="toggleIconChip('${escapeAttr(icon)}')">${escapeHtml(icon)}</button>`).join('');
}

function toggleIconChip(icon) {
  if (selectedIcons.has(icon)) selectedIcons.delete(icon);
  else selectedIcons.add(icon);
  renderIconChips();
  renderTable();
}

function selectAllIcons() {
  selectedIcons = new Set(ICONS);
  renderIconChips();
  renderTable();
}

function selectNoneIcons() {
  selectedIcons.clear();
  renderIconChips();
  renderTable();
}

function renderMapChips() {
  const container = document.getElementById('mapChips');
  if (!container) return;
  container.innerHTML = VALID_MAPS.map(([short, full]) => `<button class="chip ${selectedMaps.includes(full) ? 'active' : ''}"
    data-map="${escapeAttr(full)}" title="${escapeAttr(full)}" onclick="toggleMapChip(this.dataset.map)">${short}</button>`).join('');
}

function toggleMapChip(map) {
  if (selectedMaps.includes(map)) selectedMaps = selectedMaps.filter(value => value !== map);
  else selectedMaps.push(map);
  renderMapChips();
}

function selectAllMaps() {
  selectedMaps = VALID_MAPS.map(([, full]) => full);
  renderMapChips();
}

function selectNoneMaps() {
  selectedMaps = [];
  renderMapChips();
}

function resetFilters() {
  const set = (id, value) => { const element = document.getElementById(id); if (element) element.value = value; };
  set('playerEloMin', '300'); set('playerEloMax', '');
  set('opponentEloMin', '300'); set('opponentEloMax', '');
  set('dateFrom', '2025-01-01'); set('dateTo', '');
  selectedMaps = VALID_MAPS.map(([, full]) => full);
  renderMapChips();
}

function applyFiltersFromSidebar() {
  applyFilters(++token);
  window.toggleSidebar?.();
}

function renderLoading() {
  renderHead();
  const body = document.getElementById('tableBody');
  if (body) body.innerHTML = '<tr><td colspan="11"><div class="state-overlay"><div class="spinner"></div><div class="state-title">Fetching data...</div><div class="state-sub">Querying icon statistics.</div></div></td></tr>';
}

function renderError(error) {
  const body = document.getElementById('tableBody');
  if (body) body.innerHTML = `<tr><td colspan="11"><div class="state-overlay"><div class="state-title">Could not load icon statistics</div><div class="state-sub">${escapeHtml(error.message || error)}</div></div></td></tr>`;
}

function format(value, decimals) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(decimals) : '-';
}

function signed(value) {
  return `${value >= 0 ? '+' : ''}${Number(value).toFixed(3)}`;
}

function escapeHtml(value) {
  return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}
const escapeAttr = escapeHtml;

const tooltip = document.getElementById('col-tooltip');
document.addEventListener('mouseover', event => {
  if (!mounted || !tooltip) return;
  const cell = event.target.closest?.('.icons-value-tooltip');
  if (!cell) return;
  tooltip.textContent = cell.dataset.valueTooltip || '';
  tooltip.style.display = 'block';
});
document.addEventListener('mousemove', event => {
  if (!mounted || !tooltip) return;
  const cell = event.target.closest?.('.icons-value-tooltip');
  if (!cell) return;
  tooltip.style.left = `${Math.max(8, Math.min(event.clientX + 12, window.innerWidth - tooltip.offsetWidth - 8))}px`;
  tooltip.style.top = `${event.clientY + 18}px`;
});
document.addEventListener('mouseout', event => {
  if (!mounted || !tooltip) return;
  const source = event.target.closest?.('.icons-value-tooltip');
  const destination = event.relatedTarget?.closest?.('.icons-value-tooltip');
  if (source && destination !== source) tooltip.style.display = 'none';
});
