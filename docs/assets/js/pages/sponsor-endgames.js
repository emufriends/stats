export const id = 'sponsor-endgames';
import {
  cappedNumericRange,
  deltaRangeColor,
  numericRange,
  orangeGreenRangeColor,
  playrateColor,
  relativeEloColor,
} from '../color-scales.js?v=20260704-8';

export const title = 'Sponsor Endgames';
export const navLabel = 'Sponsor Endgames';

export const mainHtml = `
  <div class="main-header sponsor-endgames-main-header">
    <div class="table-meta" id="tableMeta"></div>
    <div class="maps-h2h-mode sponsor-endgames-mode" role="group" aria-label="Sponsor endgames metric">
      <button type="button" class="active" data-mode="delta" onclick="setSponsorEndgamesMode('delta')">Elo &Delta;</button>
      <button type="button" data-mode="frequency" onclick="setSponsorEndgamesMode('frequency')">Frequency</button>
    </div>
  </div>

  <div class="attributes-bar endgames-tabs-bar sponsor-endgames-tabs-bar">
    <div class="attributes-bar-header endgames-tabs-header">
      <div class="endgames-tabs sponsor-endgames-tabs" role="tablist" aria-label="Sponsor endgames views">
        <button class="endgames-tab active" type="button" data-view="cp" onclick="setSponsorEndgamesView('cp')">Conservation Points</button>
        <button class="endgames-tab" type="button" data-view="appeal" onclick="setSponsorEndgamesView('appeal')">Appeal</button>
      </div>
    </div>
  </div>

  <div class="table-wrap">
    <div class="table-scroll">
      <table id="statsTable" class="sponsor-endgames-table">
        <thead id="tableHead"></thead>
        <tbody id="tableBody">
          <tr><td colspan="9">
            <div class="state-overlay">
              <div class="spinner"></div>
              <div class="state-title">Fetching data...</div>
              <div class="state-sub">Querying sponsor endgames.</div>
            </div>
          </td></tr>
        </tbody>
      </table>
    </div>
  </div>`;

export const sidebarHtml = `
  <div class="sidebar-header">
    <span class="sidebar-title">Filters</span>
    <div style="display:flex;align-items:center;gap:6px;">
      <button class="reset-btn" onclick="resetFilters()">Reset</button>
      <button class="sidebar-close-btn" onclick="toggleSidebar()" title="Close filters">x</button>
    </div>
  </div>

  <hr class="divider" />

  <div class="filter-group">
    <span class="filter-label">Player ELO</span>
    <div class="range-row">
      <input class="range-input" type="number" id="playerEloMin" placeholder="Min" value="300" min="0" />
      <input class="range-input" type="number" id="playerEloMax" placeholder="Max" min="0" />
    </div>
  </div>

  <div class="filter-group">
    <span class="filter-label">Opponent ELO</span>
    <div class="range-row">
      <input class="range-input" type="number" id="opponentEloMin" placeholder="Min" value="300" min="0" />
      <input class="range-input" type="number" id="opponentEloMax" placeholder="Max" min="0" />
    </div>
  </div>

  <hr class="divider" />

  <div class="filter-group">
    <div style="display:flex;align-items:baseline;gap:6px;margin-bottom:8px;">
      <span class="filter-label" style="margin-bottom:0">Maps</span>
      <span class="map-select-all-none">
        (<span class="map-toggle-link" onclick="selectAllMaps()">all</span> / <span class="map-toggle-link" onclick="selectNoneMaps()">none</span>)
      </span>
    </div>
    <div class="chip-grid" id="mapChips"></div>
  </div>

  <hr class="divider" />

  <div class="filter-group">
    <span class="filter-label">Date Range</span>
    <input class="date-input" type="text" inputmode="numeric" pattern="\\d{4}-\\d{2}-\\d{2}" placeholder="yyyy-mm-dd" id="dateFrom" value="2025-01-01" />
    <input class="date-input" type="text" inputmode="numeric" pattern="\\d{4}-\\d{2}-\\d{2}" placeholder="yyyy-mm-dd" id="dateTo" />
  </div>

  <hr class="divider" />

  <div class="filter-action-stack">
    <button class="apply-btn" id="applyBtn" onclick="applyFiltersFromSidebar()">Apply filters</button>
  </div>`;

const API_URL = 'https://europe-west1-ark-nova-stats-dashboard.cloudfunctions.net/get-card-stats';
const DEFAULT_SNAPSHOT_URLS = {
  cp: {
    1: 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/sponsor-endgames/cp/default-mw.json?v=20260628-1',
    0: 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/sponsor-endgames/cp/default-base.json?v=20260628-1',
  },
  appeal: {
    1: 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/sponsor-endgames/appeal/default-mw.json?v=20260628-1',
    0: 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/sponsor-endgames/appeal/default-base.json?v=20260628-1',
  },
};
const VALID_MAPS = [
  { short: '1a', full: 'Map 1a: Observation Tower' },
  { short: '2a', full: 'Map 2a: Outdoor Areas' },
  { short: '3a', full: 'Map 3a: Silver Lake' },
  { short: '4a', full: 'Map 4a: Commercial Harbor' },
  { short: '5a', full: 'Map 5a: Park Restaurant' },
  { short: '6a', full: 'Map 6a: Research Institute' },
  { short: '7a', full: 'Map 7a: Ice Cream Parlors' },
  { short: '8a', full: 'Map 8a: Hollywood Hills' },
  { short: '9', full: 'Map 9: Geographical Zoo' },
  { short: '10', full: 'Map 10: Rescue Station' },
  { short: '11', full: 'Map 11: Caves' },
  { short: '12', full: 'Map 12: Artificial Intelligence' },
  { short: '13', full: 'Map 13: Drawing Board' },
  { short: '14', full: 'Map 14: Lagoon' },
  { short: 'T1', full: 'Map T1: Tournament 1' },
];

let isPageMounted = false;
let mountToken = 0;
let isMW = 1;
let activeView = 'cp';
let activeMode = 'delta';
let rows = [];
let selectedMaps = VALID_MAPS.map(map => map.full);
let currentSort = { col: 'avg_cp', dir: 'desc' };
const defaultSnapshotCache = { cp: { 0: null, 1: null }, appeal: { 0: null, 1: null } };
const BASE_ONLY_EXCLUSIONS = {
  cp: new Set([
    'Conference On Europe', 'Excavation Site', 'Expansion Area',
    'Farm Cat', 'Franchise Business',
  ]),
  appeal: new Set([
    'Conference On Australia', 'Reconstruction', 'Underwater Tunnel',
  ]),
};

export function mount({ dataset = 1 } = {}) {
  bindWindowHandlers();
  isPageMounted = true;
  mountToken += 1;
  isMW = Number(dataset) === 0 ? 0 : 1;
  activeView = 'cp';
  activeMode = 'delta';
  currentSort = { col: 'avg_cp', dir: 'desc' };
  selectedMaps = VALID_MAPS.map(map => map.full);
  renderTabs();
  renderMapChips();
  applyFilters(mountToken);
}

export function unmount() {
  isPageMounted = false;
  mountToken += 1;
}

export function setDataset(dataset) {
  isMW = Number(dataset) === 0 ? 0 : 1;
  applyFilters(++mountToken);
}

function bindWindowHandlers() {
  Object.assign(window, {
    applyFiltersFromSidebar,
    resetFilters,
    selectAllMaps,
    selectNoneMaps,
    setSponsorEndgamesView,
    setSponsorEndgamesMode,
    sortSponsorEndgames,
    toggleMapChip,
  });
}

function isCurrentMount(token) {
  return isPageMounted && token === mountToken;
}

function setSponsorEndgamesView(view) {
  activeView = view === 'appeal' ? 'appeal' : 'cp';
  currentSort = {
    col: activeView === 'cp' ? 'avg_cp' : 'avg_appeal',
    dir: 'desc',
  };
  renderTabs();
  applyFilters(++mountToken);
}

function setSponsorEndgamesMode(mode) {
  activeMode = mode === 'frequency' ? 'frequency' : 'delta';
  renderModeSwitch();
  renderTable();
}

function sortSponsorEndgames(col) {
  if (currentSort.col === col) {
    currentSort.dir = currentSort.dir === 'desc' ? 'asc' : 'desc';
  } else {
    currentSort = { col, dir: col === 'sponsor' ? 'asc' : 'desc' };
  }
  renderTable();
}

function renderTabs() {
  document.querySelectorAll('.sponsor-endgames-tabs .endgames-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.view === activeView);
  });
}

function renderModeSwitch() {
  document.querySelectorAll('.sponsor-endgames-mode button').forEach(button => {
    button.classList.toggle('active', button.dataset.mode === activeMode);
  });
}

function getParams() {
  const val = id => document.getElementById(id)?.value || '';
  return {
    stats_page: 'sponsor_endgames',
    sponsor_endgames_view: activeView,
    is_mw: isMW,
    maps: selectedMaps,
    player_elo_min: Number(val('playerEloMin') || 300),
    player_elo_max: val('playerEloMax') ? Number(val('playerEloMax')) : null,
    opponent_elo_min: Number(val('opponentEloMin') || 300),
    opponent_elo_max: val('opponentEloMax') ? Number(val('opponentEloMax')) : null,
    date_from: val('dateFrom') || '2025-01-01',
    date_to: val('dateTo') || null,
  };
}

function isDefaultParams(params) {
  return params.player_elo_min === 300 &&
    params.player_elo_max === null &&
    params.opponent_elo_min === 300 &&
    params.opponent_elo_max === null &&
    params.date_from === '2025-01-01' &&
    params.date_to === null &&
    selectedMaps.length === VALID_MAPS.length;
}

async function applyFilters(token = mountToken) {
  renderLoading();
  const params = getParams();
  if (!selectedMaps.length) {
    rows = [];
    renderTable();
    return;
  }
  try {
    let payload;
    if (isDefaultParams(params)) {
      try {
        payload = await loadDefaultSnapshot(activeView, isMW);
      } catch {
        payload = await fetchApi(params);
      }
    } else {
      payload = await fetchApi(params);
    }
    if (!isCurrentMount(token)) return;
    rows = Array.isArray(payload.data) ? payload.data : [];
    renderTable();
  } catch (error) {
    if (!isCurrentMount(token)) return;
    renderError(error);
  }
}

async function loadDefaultSnapshot(view, dataset) {
  if (defaultSnapshotCache[view]?.[dataset]) return defaultSnapshotCache[view][dataset];
  const response = await fetch(DEFAULT_SNAPSHOT_URLS[view][dataset], { cache: 'no-store' });
  if (!response.ok) throw new Error(`Snapshot request failed (${response.status})`);
  const payload = await response.json();
  defaultSnapshotCache[view][dataset] = payload;
  return payload;
}

async function fetchApi(params) {
  const response = await fetch(API_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  const payload = await response.json();
  if (!response.ok || payload.status !== 'ok') {
    throw new Error(payload.message || `API request failed (${response.status})`);
  }
  return payload;
}

function renderTable() {
  const visibleRows = isMW
    ? rows
    : rows.filter(row => !BASE_ONLY_EXCLUSIONS[activeView].has(row.sponsor));
  const meta = document.getElementById('tableMeta');
  if (meta) {
    meta.classList.remove('is-placeholder');
    meta.innerHTML = `Showing <strong>1-${visibleRows.length}</strong> of <strong>${visibleRows.length}</strong> sponsors`;
  }
  renderTableHead();
  renderModeSwitch();
  const tbody = document.getElementById('tableBody');
  if (!tbody) return;
  const sortedRows = sortRows(visibleRows);
  const averageField = activeView === 'cp' ? 'avg_cp' : 'avg_appeal';
  const scores = sortedRows.map(row => Number(row[averageField])).filter(Number.isFinite);
  const minScore = scores.length ? Math.min(...scores) : null;
  const maxScore = scores.length ? Math.max(...scores) : null;
  const elos = sortedRows.map(row => Number(row.avg_elo)).filter(Number.isFinite);
  const minElo = elos.length ? Math.min(...elos) : null;
  const maxElo = elos.length ? Math.max(...elos) : null;
  const buckets = bucketsForView();
  const frequencyRanges = Object.fromEntries(buckets.map(([field]) => [
    field,
    numericRange(sortedRows, row => frequencyForSort(row, field)),
  ]));
  const deltaRanges = Object.fromEntries(buckets.map(([field]) => [
    field,
    cappedNumericRange(
      sortedRows.filter(row => bucketCount(row, field) >= 1000),
      row => row[field],
    ),
  ]));
  tbody.innerHTML = sortedRows.map((row, index) => rowHtml(
    row, index + 1, minElo, maxElo, minScore, maxScore, frequencyRanges, deltaRanges,
  )).join('');
}

function bucketsForView() {
  return activeView === 'cp'
    ? [['delta_0', 0], ['delta_1', 1], ['delta_2', 2], ['delta_3_plus', 3]]
    : Array.from({ length: 7 }, (_, value) => [`delta_${value}`, value]);
}

function renderTableHead() {
  const thead = document.getElementById('tableHead');
  if (!thead) return;
  const prefix = activeMode === 'frequency' ? 'f' : '\u0394';
  const metricDescription = activeMode === 'frequency' ? 'relative frequency' : 'average elo gain';
  const bucketHeaders = activeView === 'cp'
    ? [['delta_0', `${prefix} (0)`, `${metricDescription} when 0 CP scored`],
      ['delta_1', `${prefix} (1)`, `${metricDescription} when 1 CP scored`],
      ['delta_2', `${prefix} (2)`, `${metricDescription} when 2 CP scored`],
      ['delta_3_plus', `${prefix} (3+)`, `${metricDescription} when 3+ CP scored`]]
    : Array.from({ length: 7 }, (_, value) => [
      `delta_${value}`,
      `${prefix} (${value})`,
      `${metricDescription} when ${value} appeal scored`,
    ]);
  const averageField = activeView === 'cp' ? 'avg_cp' : 'avg_appeal';
  thead.innerHTML = `
    <tr>
      <th style="width:5%;text-align:center;">#</th>
      ${sortableHeader('sponsor', 'Sponsor', '18%')}
      ${sortableHeader(averageField, activeView === 'cp' ? 'CP' : 'Appeal', '10%')}
      ${sortableHeader('avg_elo', 'Elo', '7%')}
      ${bucketHeaders.map(([field, label, tooltip]) => sortableHeader(
        field, label, activeView === 'cp' ? '15%' : '8.5714%', tooltip,
      )).join('')}
    </tr>`;
}

function sortableHeader(field, label, width = '', tooltip = '') {
  const active = currentSort.col === field;
  const arrow = active ? (currentSort.dir === 'desc' ? '\u2193' : '\u2191') : '\u2195';
  const widthStyle = width ? `width:${width};` : '';
  return `<th class="${active ? 'sorted' : ''}" onclick="sortSponsorEndgames('${field}')" style="${widthStyle}text-align:center;">
    ${label}${tooltip ? `<span class="col-tip" data-tip="${escapeAttr(tooltip)}">?</span>` : ''}
    <span class="sort-arrow${active ? ' active' : ''}">${arrow}</span>
  </th>`;
}

function rowHtml(row, rank, minElo, maxElo, minScore, maxScore, frequencyRanges, deltaRanges) {
  const avg = activeView === 'cp' ? row.avg_cp : row.avg_appeal;
  const buckets = bucketsForView();
  return `
    <tr>
      <td class="rank-cell">${rank}</td>
      <td class="sponsor-name-cell">${escapeHtml(row.sponsor)}</td>
      <td class="sponsor-avg-cell" style="color:${scoreColor(avg, minScore, maxScore)}">${formatNumber(avg, 2)}</td>
      <td class="elo-cell" style="color:${eloColor(row.avg_elo, minElo, maxElo)}">${formatNumber(row.avg_elo, 0)}</td>
      ${buckets.map(([field, value]) => bucketCell(
        row, field, value, buckets, frequencyRanges[field], deltaRanges[field],
      )).join('')}
    </tr>`;
}

function bucketCount(row, field) {
  const count = Number(row[field.replace('delta_', 'count_')]);
  return Number.isFinite(count) ? count : 0;
}

function validBucketTotal(row, buckets) {
  return buckets.reduce((total, [field, value]) => {
    const possible = Array.isArray(row.possible_values) && row.possible_values.includes(value);
    return total + (possible ? bucketCount(row, field) : 0);
  }, 0);
}

function bucketCell(row, field, value, buckets, frequencyRange, deltaRange) {
  const possible = Array.isArray(row.possible_values) && row.possible_values.includes(value);
  if (!possible) return '<td class="unavailable-cell">-</td>';
  const occurrences = bucketCount(row, field);
  if (activeMode === 'frequency') {
    const total = validBucketTotal(row, buckets);
    const frequency = total > 0 ? (100 * occurrences) / total : null;
    if (!Number.isFinite(frequency)) return '<td class="unavailable-cell">-</td>';
    const tooltip = `${occurrences.toLocaleString('en-US')} / ${total.toLocaleString('en-US')}`;
    return `<td class="sponsor-frequency-cell sponsor-value-tooltip" data-value-tooltip="${escapeAttr(tooltip)}"
      style="color:${playrateColor(frequency, frequencyRange?.min, frequencyRange?.max)}">${frequency.toFixed(2)}%</td>`;
  }
  const raw = row[field];
  const n = Number(raw);
  if (!Number.isFinite(n)) return '<td class="unavailable-cell">-</td>';
  if (occurrences < 1000) {
    return `<td class="delta sponsor-delta-insufficient sponsor-value-tooltip"
      data-value-tooltip="Insufficient data (fewer than 1,000 observations).">(${formatSigned(n)})</td>`;
  }
  const ciAttrs = ` data-ci-low="${escapeAttr(row[`${field}_ci95_low`] ?? '')}" data-ci-high="${escapeAttr(row[`${field}_ci95_high`] ?? '')}" data-ci-n="${escapeAttr(row[`${field}_ci95_n`] ?? '')}" data-ci-color-min="${escapeAttr(deltaRange?.min ?? '')}" data-ci-color-max="${escapeAttr(deltaRange?.max ?? '')}"`;
  return `<td class="delta delta-ci-cell"${ciAttrs} style="color:${deltaRangeColor(n, deltaRange?.min, deltaRange?.max)}">${formatSigned(n)}</td>`;
}

function sortRows(source) {
  const direction = currentSort.dir === 'asc' ? 1 : -1;
  return [...source].sort((a, b) => {
    const av = activeMode === 'frequency' && currentSort.col.startsWith('delta_')
      ? frequencyForSort(a, currentSort.col)
      : a[currentSort.col];
    const bv = activeMode === 'frequency' && currentSort.col.startsWith('delta_')
      ? frequencyForSort(b, currentSort.col)
      : b[currentSort.col];
    if (currentSort.col === 'sponsor') {
      return String(av || '').localeCompare(String(bv || '')) * direction;
    }
    const an = Number(av);
    const bn = Number(bv);
    if (!Number.isFinite(an) && !Number.isFinite(bn)) return 0;
    if (!Number.isFinite(an)) return 1;
    if (!Number.isFinite(bn)) return -1;
    return (an - bn) * direction;
  });
}

function frequencyForSort(row, field) {
  const buckets = bucketsForView();
  const total = validBucketTotal(row, buckets);
  return total > 0 ? (100 * bucketCount(row, field)) / total : Number.NaN;
}

const eloColor = relativeEloColor;

function scoreColor(raw, minScore, maxScore) {
  const value = Number(raw);
  if (!Number.isFinite(value)) return 'var(--text-muted)';
  if (!Number.isFinite(Number(minScore)) || !Number.isFinite(Number(maxScore))) return 'var(--text-muted)';
  if (maxScore === minScore) return 'var(--neutral)';
  return orangeGreenRangeColor(value, minScore, maxScore);
}

function renderMetaPlaceholder() {
  const meta = document.getElementById('tableMeta');
  if (!meta) return;
  meta.classList.add('is-placeholder');
  meta.innerHTML = 'Showing <strong>0-0</strong> of <strong>0</strong> sponsors';
}

function renderLoading() {
  renderMetaPlaceholder();
  renderTableHead();
  document.querySelectorAll('#statsTable th.sorted').forEach(th => th.classList.remove('sorted'));
  document.querySelectorAll('#statsTable .sort-arrow').forEach(arrow => {
    arrow.classList.remove('active');
    arrow.textContent = '\u2195';
  });
  const tbody = document.getElementById('tableBody');
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="${activeView === 'cp' ? 8 : 11}">
    <div class="state-overlay">
      <div class="spinner"></div>
      <div class="state-title">Fetching data...</div>
      <div class="state-sub">Querying sponsor endgames.</div>
    </div>
  </td></tr>`;
}

function renderError(error) {
  renderMetaPlaceholder();
  const tbody = document.getElementById('tableBody');
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="${activeView === 'cp' ? 8 : 11}">
    <div class="state-overlay">
      <div class="state-title">Could not load sponsor endgames</div>
      <div class="state-sub">${escapeHtml(error.message || String(error))}</div>
    </div>
  </td></tr>`;
}

function renderMapChips() {
  const container = document.getElementById('mapChips');
  if (!container) return;
  container.innerHTML = VALID_MAPS.map(map => `
    <button class="chip ${selectedMaps.includes(map.full) ? 'active' : ''}" type="button"
            title="${escapeHtml(map.full)}" onclick="toggleMapChip('${escapeAttr(map.full)}')">
      ${escapeHtml(map.short)}
    </button>`).join('');
}

function toggleMapChip(mapName) {
  if (selectedMaps.includes(mapName)) {
    selectedMaps = selectedMaps.filter(map => map !== mapName);
  } else {
    selectedMaps = [...selectedMaps, mapName];
  }
  renderMapChips();
}

function selectAllMaps() {
  selectedMaps = VALID_MAPS.map(map => map.full);
  renderMapChips();
}

function selectNoneMaps() {
  selectedMaps = [];
  renderMapChips();
}

function resetFilters() {
  const setValue = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.value = value;
  };
  setValue('playerEloMin', '300');
  setValue('playerEloMax', '');
  setValue('opponentEloMin', '300');
  setValue('opponentEloMax', '');
  setValue('dateFrom', '2025-01-01');
  setValue('dateTo', '');
  selectAllMaps();
  applyFilters(++mountToken);
}

function applyFiltersFromSidebar() {
  applyFilters(++mountToken);
  closeSidebarIfOpen();
}

function closeSidebarIfOpen() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  if (!sidebar || !sidebar.classList.contains('open')) return;
  sidebar.classList.remove('open');
  if (overlay) overlay.classList.remove('active');
}

function formatNumber(raw, decimals) {
  const value = Number(raw);
  if (!Number.isFinite(value)) return '-';
  return value.toFixed(decimals);
}

function formatSigned(raw) {
  const value = Number(raw);
  if (!Number.isFinite(value)) return '-';
  return `${value >= 0 ? '+' : ''}${value.toFixed(3)}`;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function escapeAttr(value) {
  return escapeHtml(value);
}

const _colTip = document.getElementById('col-tooltip');

document.addEventListener('mouseover', event => {
  if (!isPageMounted || !_colTip) return;
  const tipEl = event.target.closest('th')?.querySelector('.col-tip');
  if (!tipEl) return;
  _colTip.textContent = tipEl.dataset.tip || '';
  _colTip.style.display = 'block';
  positionColTip(event);
});

document.addEventListener('mouseover', event => {
  if (!isPageMounted || !_colTip) return;
  const cell = event.target.closest('.sponsor-value-tooltip');
  if (!cell) return;
  _colTip.textContent = cell.dataset.valueTooltip || '';
  _colTip.style.display = 'block';
  positionColTip(event);
});

document.addEventListener('mousemove', event => {
  if (!isPageMounted || !_colTip || _colTip.style.display === 'none') return;
  if (event.target.closest('.delta-ci-cell, .sponsor-value-tooltip')) return;
  const hasTip = event.target.closest('th')?.querySelector('.col-tip');
  if (!hasTip) {
    _colTip.style.display = 'none';
    return;
  }
  positionColTip(event);
});

document.addEventListener('mouseout', event => {
  if (!isPageMounted || !_colTip) return;
  if (event.target.closest('.delta-ci-cell, .sponsor-value-tooltip')
      || event.relatedTarget?.closest('.delta-ci-cell, .sponsor-value-tooltip')) return;
  const source = event.target.closest('th');
  const destination = event.relatedTarget?.closest('th');
  if (!source || destination !== source) {
    _colTip.style.display = 'none';
  }
});

document.addEventListener('mousemove', event => {
  if (!isPageMounted || !_colTip) return;
  const cell = event.target.closest('.sponsor-value-tooltip');
  if (!cell) return;
  positionColTip(event);
});

document.addEventListener('mouseout', event => {
  if (!isPageMounted || !_colTip) return;
  const source = event.target.closest('.sponsor-value-tooltip');
  const destination = event.relatedTarget?.closest('.sponsor-value-tooltip');
  if (source && destination !== source) _colTip.style.display = 'none';
});

function positionColTip(event) {
  const margin = 8;
  const width = _colTip.offsetWidth;
  const height = _colTip.offsetHeight;
  let left = event.clientX - width / 2;
  let top = event.clientY + 18;
  left = Math.max(margin, Math.min(left, window.innerWidth - width - margin));
  if (top + height > window.innerHeight - margin) top = event.clientY - height - 10;
  _colTip.style.left = `${left}px`;
  _colTip.style.top = `${top}px`;
}
