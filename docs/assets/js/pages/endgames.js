export const id = 'endgames';
import {
  cappedNumericRange,
  deltaRangeColor,
  frequencyColor,
  divergingRangeColor,
  numericRange,
  orangeGreenRangeColor,
  playrateColor,
  relativeEloColor,
} from '../color-scales.js?v=20260710-2';
import { formatSignedDeltaAdaptive, mapTooltipLabel } from '../table-cells.js?v=20260712-4';
import { loadStats } from '../snapshot-cache.js?v=20260711-4';

export const title = 'Endgames';
export const navLabel = 'Endgames';

export const mainHtml = `
  <div class="main-header">
    <div class="table-meta" id="tableMeta"></div>
    <div class="maps-h2h-mode cp-map-mode" id="cpMapMode" style="display:none" role="group" aria-label="CP by map metric">
      <button type="button" class="active" data-mode="raw" onclick="setCpMapMode('raw')">Raw</button>
      <button type="button" data-mode="average" onclick="setCpMapMode('average')">vs. avg</button>
    </div>
  </div>

  <div class="attributes-bar endgames-tabs-bar">
    <div class="attributes-bar-header endgames-tabs-header">
      <div class="endgames-tabs" role="tablist" aria-label="Endgames views">
        <button class="endgames-tab active" type="button" data-view="general" onclick="setEndgamesView('general')">General</button>
        <button class="endgames-tab" type="button" data-view="cp_distribution" onclick="setEndgamesView('cp_distribution')">
          <span>CP distribution</span>
          <span class="endgames-graph-toggle" role="button" tabindex="0" title="Show graph" aria-label="Show CP distribution graph" onclick="setEndgamesGraphView(event)" onkeydown="onEndgamesGraphToggleKey(event)">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M4 19h16" />
              <path d="M4 5v14" />
              <path d="M6.5 15.5 10 11l3.5 2.5L18 7" />
            </svg>
          </span>
        </button>
        <button class="endgames-tab" type="button" data-view="cp_by_map" onclick="setEndgamesView('cp_by_map')">
          <span>CP by map</span>
          <span class="endgames-graph-toggle" role="button" tabindex="0" title="Show graph" aria-label="Show CP by map graph" onclick="setEndgamesMapGraphView(event)" onkeydown="onEndgamesMapGraphToggleKey(event)">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M4 19h16" /><path d="M4 5v14" /><path d="M6.5 15.5 10 11l3.5 2.5L18 7" />
            </svg>
          </span>
        </button>
      </div>
    </div>
  </div>

  <div class="table-wrap">
    <div class="table-scroll">
      <table id="statsTable" class="endgames-table">
        <thead id="tableHead"></thead>
        <tbody id="tableBody">
          <tr><td colspan="9">
            <div class="state-overlay">
              <div class="spinner"></div>
              <div class="state-title">Fetching data...</div>
              <div class="state-sub">Querying the latest endgame statistics.</div>
            </div>
          </td></tr>
        </tbody>
      </table>
    </div>
    <div class="pagination" id="pagination" style="display:none;"></div>
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

  <div class="filter-group" id="mapFilterGroup">
    <div style="display:flex;align-items:baseline;gap:6px;margin-bottom:8px;">
      <span class="filter-label" style="margin-bottom:0">Maps</span>
      <span class="map-select-all-none">
        (<span class="map-toggle-link" onclick="selectAllMaps()">all</span> / <span class="map-toggle-link" onclick="selectNoneMaps()">none</span>)
      </span>
    </div>
    <div class="chip-grid" id="mapChips"></div>
  </div>

  <hr class="divider" id="mapFilterDivider" />

  <div class="filter-group">
    <span class="filter-label">Date Range</span>
    <input class="date-input" type=\"text\" inputmode=\"numeric\" pattern=\"\\\\d{4}-\\\\d{2}-\\\\d{2}\" placeholder=\"yyyy-mm-dd\" id="dateFrom" value="2025-01-01" />
    <input class="date-input" type=\"text\" inputmode=\"numeric\" pattern=\"\\\\d{4}-\\\\d{2}-\\\\d{2}\" placeholder=\"yyyy-mm-dd\" id="dateTo" />
  </div>

  <hr class="divider" />

  <div class="filter-action-stack">
    <button class="apply-btn" id="applyBtn" onclick="applyFiltersFromSidebar()">Apply filters</button>
  </div>`;

const API_URL = 'https://europe-west1-ark-nova-stats-dashboard.cloudfunctions.net/get-card-stats';
const STATS_PAGE = 'endgames';
const ENDGAMES_VIEW_GENERAL = 'general';
const ENDGAMES_VIEW_CP_DISTRIBUTION = 'cp_distribution';
const ENDGAMES_VIEW_CP_DISTRIBUTION_GRAPH = 'cp_distribution_graph';
const ENDGAMES_VIEW_CP_BY_MAP = 'cp_by_map';
const ENDGAMES_VIEW_CP_BY_MAP_GRAPH = 'cp_by_map_graph';
const DEFAULT_SNAPSHOT_URLS = {
  general: {
    1: 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/endgames/default-mw.json',
    0: 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/endgames/default-base.json',
  },
  cp_distribution: {
    1: 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/endgames/cp-distribution/default-mw.json',
    0: 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/endgames/cp-distribution/default-base.json',
  },
  cp_by_map: {
    1: 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/endgames/cp-by-map/default-mw.json',
    0: 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/endgames/cp-by-map/default-base.json',
  },
};
const VALID_MAPS = [
  { short: '1a', full: 'Map 1a: Observation Tower', field: 'map_1a' },
  { short: '2a', full: 'Map 2a: Outdoor Areas', field: 'map_2a' },
  { short: '3a', full: 'Map 3a: Silver Lake', field: 'map_3a' },
  { short: '4a', full: 'Map 4a: Commercial Harbor', field: 'map_4a' },
  { short: '5a', full: 'Map 5a: Park Restaurant', field: 'map_5a' },
  { short: '6a', full: 'Map 6a: Research Institute', field: 'map_6a' },
  { short: '7a', full: 'Map 7a: Ice Cream Parlors', field: 'map_7a' },
  { short: '8a', full: 'Map 8a: Hollywood Hills', field: 'map_8a' },
  { short: '9', full: 'Map 9: Geographical Zoo', field: 'map_9' },
  { short: '10', full: 'Map 10: Rescue Station', field: 'map_10' },
  { short: '11', full: 'Map 11: Caves', field: 'map_11' },
  { short: '12', full: 'Map 12: Artificial Intelligence', field: 'map_12' },
  { short: '13', full: 'Map 13: Drawing Board', field: 'map_13' },
  { short: '14', full: 'Map 14: Lagoon', field: 'map_14' },
  { short: 'T1', full: 'Map T1: Tournament 1', field: 'map_t1' },
];

let isPageMounted = false;
let mountToken = 0;
let isMW = 1;
let activeEndgamesView = ENDGAMES_VIEW_GENERAL;
let allData = [];
let filteredData = [];
let searchQuery = '';
let currentSort = defaultSortForView(activeEndgamesView);
let currentPage = 1;
let rowsPerPage = 9999;
let cpMapMode = 'raw';
let apiWarmupInFlight = false;
let apiWarmupLastAt = 0;
const API_WARMUP_COOLDOWN_MS = 30000;
const defaultSnapshotCache = {};
const CP_VALUES = [0, 1, 2, 3, 4];
const CHART_LINE_COLORS = [
  '#81c784', '#4db6ac', '#64b5f6', '#9575cd', '#f06292', '#ffb74d',
  '#aed581', '#4dd0e1', '#7986cb', '#ba68c8', '#e57373', '#dce775',
  '#80cbc4', '#90caf9', '#ce93d8', '#ffcc80', '#a5d6a7',
];

function isCurrentMount(token) {
  return isPageMounted && token === mountToken;
}

export function mount({ dataset = 1 } = {}) {
  bindWindowHandlers();
  isPageMounted = true;
  mountToken += 1;
  isMW = Number(dataset) === 0 ? 0 : 1;
  activeEndgamesView = ENDGAMES_VIEW_GENERAL;
  allData = [];
  filteredData = [];
  searchQuery = '';
  currentSort = defaultSortForView(activeEndgamesView);
  currentPage = 1;
  rowsPerPage = 9999;

  renderTableHead();
  updateEndgamesTabs();
  updateMapFilterVisibility();
  buildMapChips();
  const searchInput = document.getElementById('searchInput');
  if (searchInput) searchInput.value = '';
  warmApiInBackground();
  applyFilters(mountToken);
}

function defaultSortForView(view) {
  if (view === ENDGAMES_VIEW_GENERAL) return { col: 'delta_played', dir: 'desc' };
  return { col: 'avg_cp', dir: 'desc' };
}

function apiViewForCurrentView() {
  // Graph mode is a client-side rendering of the CP distribution payload.
  if (activeEndgamesView === ENDGAMES_VIEW_CP_DISTRIBUTION_GRAPH) return ENDGAMES_VIEW_CP_DISTRIBUTION;
  if (activeEndgamesView === ENDGAMES_VIEW_CP_BY_MAP_GRAPH) return ENDGAMES_VIEW_CP_BY_MAP;
  return activeEndgamesView;
}

function buildMapChips() {
  const container = document.getElementById('mapChips');
  if (!container) return;
  container.innerHTML = '';
  VALID_MAPS.forEach(map => {
    const btn = document.createElement('button');
    btn.className = 'chip active';
    btn.textContent = map.short;
    btn.dataset.value = map.full;
    btn.title = map.full;
    btn.addEventListener('click', () => toggleChip(btn, 'map'));
    container.appendChild(btn);
  });
}

function toggleChip(btn, group) {
  btn.classList.toggle('active');
}

function setEndgamesView(view) {
  if (![ENDGAMES_VIEW_GENERAL, ENDGAMES_VIEW_CP_DISTRIBUTION, ENDGAMES_VIEW_CP_BY_MAP].includes(view)) return;
  if (activeEndgamesView === view) return;
  activeEndgamesView = view;
  currentSort = defaultSortForView(activeEndgamesView);
  currentPage = 1;
  allData = [];
  filteredData = [];
  renderTableHead();
  updateEndgamesTabs();
  updateMapFilterVisibility();
  applyFilters(mountToken);
}

function setEndgamesGraphView(event) {
  event?.stopPropagation();
  event?.preventDefault();
  activeEndgamesView = activeEndgamesView === ENDGAMES_VIEW_CP_DISTRIBUTION_GRAPH
    ? ENDGAMES_VIEW_CP_DISTRIBUTION
    : ENDGAMES_VIEW_CP_DISTRIBUTION_GRAPH;
  currentSort = defaultSortForView(activeEndgamesView);
  currentPage = 1;
  allData = [];
  filteredData = [];
  renderTableHead();
  updateEndgamesTabs();
  updateMapFilterVisibility();
  applyFilters(mountToken);
}

function onEndgamesGraphToggleKey(event) {
  if (event.key !== 'Enter' && event.key !== ' ') return;
  setEndgamesGraphView(event);
}

function setEndgamesMapGraphView(event) {
  event?.stopPropagation();
  event?.preventDefault();
  activeEndgamesView = activeEndgamesView === ENDGAMES_VIEW_CP_BY_MAP_GRAPH
    ? ENDGAMES_VIEW_CP_BY_MAP
    : ENDGAMES_VIEW_CP_BY_MAP_GRAPH;
  currentSort = defaultSortForView(activeEndgamesView);
  currentPage = 1;
  allData = [];
  filteredData = [];
  renderTableHead();
  updateEndgamesTabs();
  updateMapFilterVisibility();
  applyFilters(mountToken);
}

function onEndgamesMapGraphToggleKey(event) {
  if (event.key !== 'Enter' && event.key !== ' ') return;
  setEndgamesMapGraphView(event);
}

function updateEndgamesTabs() {
  document.querySelectorAll('.endgames-tab').forEach(btn => {
    const tabView = btn.dataset.view;
    const isActive = tabView === activeEndgamesView ||
      (tabView === ENDGAMES_VIEW_CP_DISTRIBUTION && activeEndgamesView === ENDGAMES_VIEW_CP_DISTRIBUTION_GRAPH) ||
      (tabView === ENDGAMES_VIEW_CP_BY_MAP && activeEndgamesView === ENDGAMES_VIEW_CP_BY_MAP_GRAPH);
    btn.classList.toggle('active', isActive);
    btn.classList.toggle('graph-active',
      (tabView === ENDGAMES_VIEW_CP_DISTRIBUTION && activeEndgamesView === ENDGAMES_VIEW_CP_DISTRIBUTION_GRAPH) ||
      (tabView === ENDGAMES_VIEW_CP_BY_MAP && activeEndgamesView === ENDGAMES_VIEW_CP_BY_MAP_GRAPH));
    btn.setAttribute('aria-selected', String(isActive));
  });
  document.querySelectorAll('.endgames-tab').forEach(tab => {
    const toggle = tab.querySelector('.endgames-graph-toggle');
    if (!toggle) return;
    const tabView = tab.dataset.view;
    toggle.classList.toggle('active',
      (tabView === ENDGAMES_VIEW_CP_DISTRIBUTION && activeEndgamesView === ENDGAMES_VIEW_CP_DISTRIBUTION_GRAPH) ||
      (tabView === ENDGAMES_VIEW_CP_BY_MAP && activeEndgamesView === ENDGAMES_VIEW_CP_BY_MAP_GRAPH));
  });
  const modeSwitch = document.getElementById('cpMapMode');
  if (modeSwitch) {
    modeSwitch.style.display = (
      activeEndgamesView === ENDGAMES_VIEW_CP_BY_MAP ||
      activeEndgamesView === ENDGAMES_VIEW_CP_BY_MAP_GRAPH
    ) ? '' : 'none';
  }
}

function setCpMapMode(mode) {
  cpMapMode = mode === 'average' ? 'average' : 'raw';
  document.querySelectorAll('#cpMapMode button').forEach(button => {
    button.classList.toggle('active', button.dataset.mode === cpMapMode);
  });
  applySortAndRender();
}

function updateMapFilterVisibility() {
  const hideMapFilter = activeEndgamesView === ENDGAMES_VIEW_CP_BY_MAP ||
    activeEndgamesView === ENDGAMES_VIEW_CP_BY_MAP_GRAPH;
  document.getElementById('mapFilterGroup')?.classList.toggle('is-hidden', hideMapFilter);
  document.getElementById('mapFilterDivider')?.classList.toggle('is-hidden', hideMapFilter);
}

function resetFilters() {
  document.getElementById('playerEloMin').value = '300';
  document.getElementById('playerEloMax').value = '';
  document.getElementById('opponentEloMin').value = '300';
  document.getElementById('opponentEloMax').value = '';
  document.getElementById('dateFrom').value = '2025-01-01';
  document.getElementById('dateTo').value = '';
  document.querySelectorAll('#mapChips .chip').forEach(c => c.classList.add('active'));
  const searchInput = document.getElementById('searchInput');
  if (searchInput) searchInput.value = '';
  searchQuery = '';
  updateCardSearchIndicator();
  applyFilters(mountToken);
}

function getParams() {
  const selectedMaps = activeEndgamesView === ENDGAMES_VIEW_CP_BY_MAP ||
      activeEndgamesView === ENDGAMES_VIEW_CP_BY_MAP_GRAPH
    ? VALID_MAPS.map(m => m.full)
    : [...document.querySelectorAll('#mapChips .chip.active')].map(c => c.dataset.value);
  const params = {
    is_mw: isMW,
    stats_page: STATS_PAGE,
    endgames_view: apiViewForCurrentView(),
    maps: selectedMaps,
  };

  const pMin = document.getElementById('playerEloMin').value;
  const pMax = document.getElementById('playerEloMax').value;
  const oMin = document.getElementById('opponentEloMin').value;
  const oMax = document.getElementById('opponentEloMax').value;
  const dFrom = document.getElementById('dateFrom').value;
  const dTo = document.getElementById('dateTo').value;

  params.player_elo_min = pMin === '' ? 0 : parseInt(pMin, 10);
  if (pMax) params.player_elo_max = parseInt(pMax, 10);
  params.opponent_elo_min = oMin === '' ? 0 : parseInt(oMin, 10);
  if (oMax) params.opponent_elo_max = parseInt(oMax, 10);
  if (dFrom) params.date_from = dFrom;
  if (dTo) params.date_to = dTo;
  return params;
}

function closeSidebarIfOpen() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  if (!sidebar || !sidebar.classList.contains('open')) return;
  sidebar.classList.remove('open');
  if (overlay) overlay.classList.remove('active');
}

async function applyFiltersFromSidebar() {
  const activeMountToken = mountToken;
  const params = getParams();
  const defaultSnapshotKey = getDefaultSnapshotKey(params);
  if (defaultSnapshotKey !== null) {
    const cachedDefaultSnapshot = defaultSnapshotCache[defaultSnapshotKey];
    if (!isCurrentMount(activeMountToken)) return;
    if (cachedDefaultSnapshot) {
      allData = cachedDefaultSnapshot.data;
      searchQuery = normalizeSearchText(document.getElementById('searchInput')?.value || '');
      updateCardSearchIndicator();
      applySearch();
      closeSidebarIfOpen();
      return;
    }
  }

  closeSidebarIfOpen();
  await applyFilters(activeMountToken);
}

function getDefaultSnapshotKey(params) {
  const selectedMaps = params.maps || [];
  const allMapNames = VALID_MAPS.map(m => m.full);
  const allMapsSelected =
    selectedMaps.length === allMapNames.length &&
    allMapNames.every(mapName => selectedMaps.includes(mapName));

  const playerMinDefault = params.player_elo_min === undefined || Number(params.player_elo_min) === 300;
  const opponentMinDefault = params.opponent_elo_min === undefined || Number(params.opponent_elo_min) === 300;

  const isDefault =
    (params.is_mw === 0 || params.is_mw === 1) &&
    allMapsSelected &&
    playerMinDefault &&
    params.player_elo_max === undefined &&
    opponentMinDefault &&
    params.opponent_elo_max === undefined &&
    (params.date_from === undefined || params.date_from === '2025-01-01') &&
    params.date_to === undefined;

  return isDefault ? `${params.endgames_view}:${params.is_mw}` : null;
}

function snapshotUrlForKey(snapshotKey) {
  const [view, dataset] = snapshotKey.split(':');
  return DEFAULT_SNAPSHOT_URLS[view]?.[dataset];
}

function warmApiInBackground() {
  const now = Date.now();
  if (apiWarmupInFlight || now - apiWarmupLastAt < API_WARMUP_COOLDOWN_MS) return;
  apiWarmupInFlight = true;
  fetch(API_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ warmup: true, stats_page: STATS_PAGE, endgames_view: activeEndgamesView }),
    cache: 'no-store',
    keepalive: true,
  }).catch(() => {}).finally(() => {
    apiWarmupInFlight = false;
    apiWarmupLastAt = Date.now();
  });
}

async function applyFilters(activeMountToken = mountToken) {
  if (!isCurrentMount(activeMountToken)) return;
  const params = getParams();
  if (activeEndgamesView !== ENDGAMES_VIEW_CP_BY_MAP &&
      activeEndgamesView !== ENDGAMES_VIEW_CP_BY_MAP_GRAPH &&
      !(params.maps || []).length) {
    allData = [];
    filteredData = [];
    searchQuery = normalizeSearchText(document.getElementById('searchInput')?.value || '');
    updateCardSearchIndicator();
    applySearch();
    return;
  }

  const btn = document.getElementById('applyBtn');
  if (btn) btn.disabled = true;
  const defaultSnapshotKey = getDefaultSnapshotKey(params);
  const cachedDefaultSnapshot = defaultSnapshotKey === null ? null : defaultSnapshotCache[defaultSnapshotKey];
  if (cachedDefaultSnapshot) {
    allData = cachedDefaultSnapshot.data;
    searchQuery = normalizeSearchText(document.getElementById('searchInput')?.value || '');
    updateCardSearchIndicator();
    applySearch();
    if (btn) btn.disabled = false;
    return;
  }

  showLoading(defaultSnapshotKey === null ? 'query' : 'saved');

  try {
    let json;
    json = await loadStats(
      params,
      defaultSnapshotKey === null ? null : snapshotUrlForKey(defaultSnapshotKey),
    );
    if (!isCurrentMount(activeMountToken)) return;
    if (json.status !== 'ok') throw new Error(json.message || 'Unknown error');
    allData = Array.isArray(json.data) ? json.data : [];
    if (defaultSnapshotKey !== null) {
      defaultSnapshotCache[defaultSnapshotKey] = { data: allData };
    }
    searchQuery = normalizeSearchText(document.getElementById('searchInput')?.value || '');
    updateCardSearchIndicator();
    applySearch();
  } catch (err) {
    if (isCurrentMount(activeMountToken)) showError(err.message);
  } finally {
    if (isCurrentMount(activeMountToken) && btn) {
      btn.disabled = false;
      btn.textContent = 'Apply filters';
    }
  }
}

function normalizeSearchText(value) {
  return String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
}

function onSearch() {
  searchQuery = normalizeSearchText(document.getElementById('searchInput')?.value || '');
  updateCardSearchIndicator();
  currentPage = 1;
  applySearch();
}

function openCardSearch(event) {
  event.stopPropagation();
  document.getElementById('cardHeaderContent')?.classList.add('search-open');
  document.getElementById('cardHeaderSearch')?.classList.add('open');
  setTimeout(() => document.getElementById('searchInput')?.focus(), 0);
}

function closeCardSearch(event) {
  event.stopPropagation();
  const input = document.getElementById('searchInput');
  if (input && input.value) {
    input.value = '';
    onSearch();
  }
  document.getElementById('cardHeaderContent')?.classList.remove('search-open');
  document.getElementById('cardHeaderSearch')?.classList.remove('open');
}

function updateCardSearchIndicator() {
  const btn = document.getElementById('cardSearchBtn');
  if (btn) btn.classList.toggle('active', Boolean(searchQuery));
}

function applySearch() {
  filteredData = allData.filter(row => {
    if (!searchQuery) return true;
    return normalizeSearchText(row.card_name).includes(searchQuery);
  });
  currentPage = 1;
  applySortAndRender();
}

function sortBy(col) {
  if (currentSort.col === col) currentSort.dir = currentSort.dir === 'desc' ? 'asc' : 'desc';
  else currentSort = { col, dir: 'desc' };
  applySortAndRender();
}

function compareRowsForCurrentSort(a, b) {
  const { col, dir } = currentSort;
  const isMapField = VALID_MAPS.some(map => map.field === col);
  const av = isMapField ? cpMapValue(a, col) : a[col];
  const bv = isMapField ? cpMapValue(b, col) : b[col];
  let cmp;
  if (col === 'card_name') cmp = String(av || '').localeCompare(String(bv || ''));
  else {
    const an = av == null ? -Infinity : Number(av);
    const bn = bv == null ? -Infinity : Number(bv);
    cmp = an === bn ? 0 : an < bn ? -1 : 1;
  }
  if (cmp === 0) cmp = String(a.card_name || '').localeCompare(String(b.card_name || ''));
  return dir === 'asc' ? cmp : -cmp;
}

function assignGlobalRanks() {
  const globallySorted = [...allData].sort(compareRowsForCurrentSort);
  globallySorted.forEach((row, index) => { row.global_rank = index + 1; });
}

function applySortAndRender() {
  assignGlobalRanks();
  const { col, dir } = currentSort;
  const sorted = [...filteredData].sort(compareRowsForCurrentSort);
  updateSortIndicator(col, dir);
  renderTable(sorted);
}

function updateSortIndicator(col = currentSort.col, dir = currentSort.dir) {
  document.querySelectorAll('.sort-arrow').forEach(el => { el.textContent = '\u2195'; });
  document.querySelectorAll('th').forEach(th => th.classList.remove('sorted'));
  const arrow = document.getElementById(`sort-${col}`);
  if (arrow) {
    arrow.textContent = dir === 'asc' ? '\u2191' : '\u2193';
    arrow.closest('th')?.classList.add('sorted');
  }
}

function renderTableHead() {
  const thead = document.getElementById('tableHead');
  if (!thead) return;
  updateStatsTableMode();
  if (activeEndgamesView === ENDGAMES_VIEW_CP_DISTRIBUTION_GRAPH ||
      activeEndgamesView === ENDGAMES_VIEW_CP_BY_MAP_GRAPH) {
    thead.innerHTML = '';
  } else if (activeEndgamesView === ENDGAMES_VIEW_CP_DISTRIBUTION) {
    thead.innerHTML = cpDistributionHeadHtml();
  } else if (activeEndgamesView === ENDGAMES_VIEW_CP_BY_MAP) {
    thead.innerHTML = cpByMapHeadHtml();
  } else {
    thead.innerHTML = generalHeadHtml();
  }
}

function updateStatsTableMode() {
  const table = document.getElementById('statsTable');
  if (!table) return;
  table.classList.toggle('cp-by-map-view', activeEndgamesView === ENDGAMES_VIEW_CP_BY_MAP);
  table.classList.toggle('endgames-graph-view',
    activeEndgamesView === ENDGAMES_VIEW_CP_DISTRIBUTION_GRAPH ||
    activeEndgamesView === ENDGAMES_VIEW_CP_BY_MAP_GRAPH);
}

function nameHeaderHtml(width) {
  return `
    <th onclick="sortBy('card_name')" style="width:${width};text-align:center">
      Endgame<span class="sort-arrow" id="sort-card_name">\u2195</span>
    </th>`;
}

function generalHeadHtml() {
  return `
    <tr>
      <th style="width:5%;text-align:center;cursor:default;">#</th>
      ${nameHeaderHtml('20%')}
      <th onclick="sortBy('delta_in_hand')" style="width:12%;text-align:center">&Delta; (scored)<span class="col-tip" data-tip="average elo gain when scored at the end of the game">?</span><span class="sort-arrow" id="sort-delta_in_hand">\u2195</span></th>
      <th onclick="sortBy('delta_played')" style="width:12%;text-align:center">&Delta; (dealt)<span class="col-tip" data-tip="average elo gain when dealt at the start of the game">?</span><span class="sort-arrow" id="sort-delta_played">\u2195</span></th>
      <th onclick="sortBy('avg_elo')" style="width:8%;text-align:center">Elo<span class="col-tip" data-tip="average player elo when scored">?</span><span class="sort-arrow" id="sort-avg_elo">\u2195</span></th>
      <th onclick="sortBy('playrate_pct')" style="width:15%;text-align:center">Keeprate <span class="col-tip" data-tip-fraction>?</span><span class="sort-arrow" id="sort-playrate_pct">\u2195</span></th>
      <th onclick="sortBy('n_played')" style="width:9%;text-align:center">Scored<span class="col-tip" data-tip="n scored">?</span><span class="sort-arrow" id="sort-n_played">\u2195</span></th>
      <th onclick="sortBy('n_seen')" style="width:9%;text-align:center">Dealt<span class="col-tip" data-tip="n dealt">?</span><span class="sort-arrow" id="sort-n_seen">\u2195</span></th>
      <th onclick="sortBy('avg_cp')" style="width:10%;text-align:center">CP<span class="col-tip" data-tip="average conservation points scored">?</span><span class="sort-arrow" id="sort-avg_cp">\u2195</span></th>
    </tr>`;
}

function cpDistributionHeadHtml() {
  return `
    <tr>
      <th style="width:5%;text-align:center;cursor:default;">#</th>
      ${nameHeaderHtml('20%')}
      ${CP_VALUES.map(cp => `<th onclick="sortBy('cp_${cp}_pct')" style="width:13%;text-align:center">${cp}<span class="sort-arrow" id="sort-cp_${cp}_pct">\u2195</span></th>`).join('')}
      <th onclick="sortBy('avg_cp')" style="width:10%;text-align:center">CP<span class="col-tip" data-tip="average conservation points scored">?</span><span class="sort-arrow" id="sort-avg_cp">\u2195</span></th>
    </tr>`;
}

function cpByMapHeadHtml() {
  return `
    <tr>
      <th style="width:4%;text-align:center;cursor:default;">#</th>
      ${nameHeaderHtml('16%')}
      ${VALID_MAPS.map(map => `<th class="maps-custom-tip" onclick="sortBy('${map.field}')" data-tip="${escapeAttr(mapTooltipLabel(map.full))}" style="width:5%;text-align:center">${escapeHtml(map.short)}<span class="sort-arrow" id="sort-${map.field}">\u2195</span></th>`).join('')}
      <th onclick="sortBy('avg_cp')" style="width:5%;text-align:center">CP<span class="col-tip" data-tip="average conservation points scored">?</span><span class="sort-arrow" id="sort-avg_cp">\u2195</span></th>
    </tr>`;
}

function appendCell(rowEl, className, text, color) {
  const cell = document.createElement('td');
  if (className) cell.className = className;
  if (color) cell.style.color = color;
  cell.textContent = text;
  rowEl.appendChild(cell);
  return cell;
}

function appendDeltaCiCell(rowEl, row, prefix, text, range) {
  const color = deltaRangeColor(row[prefix], range.min, range.max);
  const cell = appendCell(rowEl, 'delta delta-ci-cell', text, color);
  cell.dataset.ciLow = row[`${prefix}_ci95_low`] ?? '';
  cell.dataset.ciHigh = row[`${prefix}_ci95_high`] ?? '';
  cell.dataset.ciN = row[`${prefix}_ci95_n`] ?? '';
  cell.dataset.ciColorMin = range.min ?? '';
  cell.dataset.ciColorMax = range.max ?? '';
  return cell;
}

function appendPlayrateCell(rowEl, pr, prVal, barWidth, barColor) {
  const cell = document.createElement('td');
  const wrap = document.createElement('div');
  wrap.className = 'playrate-cell';
  const barWrap = document.createElement('div');
  barWrap.className = 'playrate-bar-wrap';
  const bar = document.createElement('div');
  bar.className = 'playrate-bar';
  bar.style.width = `${barWidth}%`;
  bar.style.background = barColor;
  const value = document.createElement('span');
  value.className = 'playrate-val';
  value.style.color = barColor;
  value.textContent = pr;
  barWrap.appendChild(bar);
  wrap.appendChild(barWrap);
  wrap.appendChild(value);
  cell.appendChild(wrap);
  rowEl.appendChild(cell);
}

function renderTable(data) {
  const tbody = document.getElementById('tableBody');
  const pagination = document.getElementById('pagination');
  const meta = document.getElementById('tableMeta');
  const colCount = columnCountForView();
  updateStatsTableMode();

  if (!data.length) {
    tbody.innerHTML = `<tr><td colspan="${colCount}">
      <div class="state-overlay">
        <div class="error-icon">&#128269;</div>
        <div class="state-title">No endgames found</div>
        <div class="state-sub">Try adjusting your search or filters.</div>
      </div>
    </td></tr>`;
    pagination.style.display = 'none';
    meta.innerHTML = 'No results';
    return;
  }

  if (activeEndgamesView === ENDGAMES_VIEW_CP_DISTRIBUTION_GRAPH) {
    renderCpDistributionGraph(data);
    return;
  }
  if (activeEndgamesView === ENDGAMES_VIEW_CP_BY_MAP_GRAPH) {
    renderCpByMapGraph(data);
    return;
  }

  const rpp = rowsPerPage >= 9999 ? data.length : rowsPerPage;
  const totalPages = Math.ceil(data.length / rpp);
  if (currentPage > totalPages) currentPage = totalPages;
  const start = (currentPage - 1) * rpp;
  const pageData = data.slice(start, start + rpp);
  const colorRanges = buildColorRanges(data);

  tbody.replaceChildren();
  pageData.forEach(row => {
    const tr = document.createElement('tr');
    if (activeEndgamesView === ENDGAMES_VIEW_CP_DISTRIBUTION) renderCpDistributionRow(tr, row, colorRanges);
    else if (activeEndgamesView === ENDGAMES_VIEW_CP_BY_MAP) renderCpByMapRow(tr, row, colorRanges);
    else renderGeneralRow(tr, row, colorRanges);
    tbody.appendChild(tr);
  });

  const from = start + 1;
  const to = Math.min(start + rpp, data.length);
  meta.innerHTML = `<span class="meta-prefix">Showing </span><strong>${from}-${to}</strong> of <strong>${data.length}</strong> endgames`;

  if (totalPages <= 1) pagination.style.display = 'none';
  else {
    pagination.style.display = 'flex';
    pagination.innerHTML = buildPagination(totalPages);
  }
}

function buildColorRanges(data) {
  const ranges = {
    avg_elo: numericRange(data, row => row.avg_elo),
    playrate_pct: numericRange(data, row => row.playrate_pct),
    avg_cp: numericRange(data, row => row.avg_cp),
  };
  if (activeEndgamesView === ENDGAMES_VIEW_CP_DISTRIBUTION) {
    ranges.cp_distribution = numericRange(
      data.flatMap(row => CP_VALUES.map(cp => ({ value: row[`cp_${cp}_pct`] }))),
      row => row.value,
    );
  } else if (activeEndgamesView === ENDGAMES_VIEW_CP_BY_MAP) {
    const mapValues = data.flatMap(row => VALID_MAPS.map(map => ({
      value: cpMapMode === 'average' ? cpMapValue(row, map.field) : row[map.field],
    })));
    ranges.cp_by_map = cpMapMode === 'average'
      ? cappedNumericRange(mapValues, row => row.value)
      : numericRange(mapValues, row => row.value);
  }
  if (activeEndgamesView === ENDGAMES_VIEW_GENERAL) {
    ranges.delta_in_hand = cappedNumericRange(data, row => row.delta_in_hand);
    ranges.delta_played = cappedNumericRange(data, row => row.delta_played);
  }
  return ranges;
}

function renderGeneralRow(tr, row, ranges) {
  const prVal = row.playrate_pct || 0;
  const cpVal = row.avg_cp;
  appendCell(tr, 'rank-cell', row.global_rank ?? '\u2014');
  appendCell(tr, 'card-name', titleCase(row.card_name || ''));
  appendDeltaCiCell(tr, row, 'delta_in_hand', fmtDelta(row.delta_in_hand), ranges.delta_in_hand);
  appendDeltaCiCell(tr, row, 'delta_played', fmtDelta(row.delta_played), ranges.delta_played);
  appendCell(tr, 'n-cell', row.avg_elo != null ? Math.round(row.avg_elo).toLocaleString('en-US') : '\u2014', eloColor(row.avg_elo, ranges.avg_elo.min, ranges.avg_elo.max));
  appendPlayrateCell(
    tr,
    row.playrate_pct != null ? `${row.playrate_pct.toFixed(2)}%` : '\u2014',
    prVal,
    Math.min(Math.max(prVal, 0), 100),
    prColor(prVal, ranges.playrate_pct.min, ranges.playrate_pct.max),
  );
  appendCell(tr, 'n-cell', fmtN(row.n_played));
  appendCell(tr, 'n-cell', fmtN(row.n_seen));
  appendCell(tr, 'delta cp-cell', cpVal != null ? Number(cpVal).toFixed(2) : '\u2014', cpColor(cpVal, ranges.avg_cp));
}

function renderCpDistributionRow(tr, row, ranges) {
  appendCell(tr, 'rank-cell', row.global_rank ?? '\u2014');
  appendCell(tr, 'card-name', titleCase(row.card_name || ''));
  CP_VALUES.forEach(cp => {
    const pct = row[`cp_${cp}_pct`];
    appendCell(tr, 'n-cell cp-pct-cell', fmtPercent(pct), cpPctColor(pct, ranges.cp_distribution));
  });
  appendCell(tr, 'delta cp-cell', row.avg_cp != null ? Number(row.avg_cp).toFixed(2) : '\u2014', cpColor(row.avg_cp, ranges.avg_cp));
}

function renderCpDistributionGraph(data) {
  const tbody = document.getElementById('tableBody');
  const pagination = document.getElementById('pagination');
  const meta = document.getElementById('tableMeta');
  const sortedData = [...data].sort(compareRowsForCurrentSort);
  tbody.innerHTML = `<tr><td colspan="${columnCountForView()}" class="chart-host-cell"></td></tr>`;
  const host = tbody.querySelector('.chart-host-cell');
  host.appendChild(buildCpDistributionChart(sortedData));
  pagination.style.display = 'none';
  meta.innerHTML = '';
}

function buildCpDistributionChart(data) {
  const wrap = document.createElement('div');
  wrap.className = 'cp-dist-chart-wrap';
  const chart = document.createElement('div');
  chart.className = 'cp-dist-chart';
  const legend = document.createElement('div');
  legend.className = 'cp-dist-legend';
  const legendControls = document.createElement('div');
  legendControls.className = 'cp-dist-legend-controls';
  legendControls.innerHTML = `<span>Lines</span><span>(<button type="button" data-action="all">all</button> / <button type="button" data-action="none">none</button>)</span>`;
  const legendList = document.createElement('div');
  legendList.className = 'cp-dist-legend-list';
  const tooltip = document.createElement('div');
  tooltip.className = 'cp-dist-tooltip';
  const selectedIndexes = new Set(data.map((_, index) => index));

  const width = 760;
  const height = 430;
  const margin = { top: 22, right: 28, bottom: 44, left: 54 };
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  const yMax = 60;
  const x = cp => margin.left + (cp / 4) * innerWidth;
  const y = pct => margin.top + innerHeight - (Math.max(0, Math.min(yMax, Number(pct) || 0)) / yMax) * innerHeight;
  const svgNs = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(svgNs, 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', 'CP distribution line chart');

  [0, 15, 30, 45, 60].forEach(tick => {
    const gy = y(tick);
    const grid = document.createElementNS(svgNs, 'line');
    grid.setAttribute('x1', margin.left);
    grid.setAttribute('x2', width - margin.right);
    grid.setAttribute('y1', gy);
    grid.setAttribute('y2', gy);
    grid.setAttribute('class', 'cp-dist-grid');
    svg.appendChild(grid);

    const label = document.createElementNS(svgNs, 'text');
    label.setAttribute('x', margin.left - 12);
    label.setAttribute('y', gy + 4);
    label.setAttribute('text-anchor', 'end');
    label.setAttribute('class', 'cp-dist-axis-label');
    label.textContent = `${tick}%`;
    svg.appendChild(label);
  });

  CP_VALUES.forEach(cp => {
    const gx = x(cp);
    const label = document.createElementNS(svgNs, 'text');
    label.setAttribute('x', gx);
    label.setAttribute('y', height - 14);
    label.setAttribute('text-anchor', 'middle');
    label.setAttribute('class', 'cp-dist-axis-label');
    label.textContent = cp;
    svg.appendChild(label);
  });

  const xAxis = document.createElementNS(svgNs, 'line');
  xAxis.setAttribute('x1', margin.left);
  xAxis.setAttribute('x2', width - margin.right);
  xAxis.setAttribute('y1', margin.top + innerHeight);
  xAxis.setAttribute('y2', margin.top + innerHeight);
  xAxis.setAttribute('class', 'cp-dist-axis');
  svg.appendChild(xAxis);

  const yAxis = document.createElementNS(svgNs, 'line');
  yAxis.setAttribute('x1', margin.left);
  yAxis.setAttribute('x2', margin.left);
  yAxis.setAttribute('y1', margin.top);
  yAxis.setAttribute('y2', margin.top + innerHeight);
  yAxis.setAttribute('class', 'cp-dist-axis');
  svg.appendChild(yAxis);

  const hoverLine = document.createElementNS(svgNs, 'line');
  hoverLine.setAttribute('class', 'cp-dist-hover-line');
  hoverLine.setAttribute('y1', margin.top);
  hoverLine.setAttribute('y2', margin.top + innerHeight);
  hoverLine.style.display = 'none';
  svg.appendChild(hoverLine);

  const isAllSelected = () => selectedIndexes.size === data.length;
  const syncSelection = () => {
    svg.querySelectorAll('.cp-dist-line, .cp-dist-dot').forEach(el => {
      const selected = selectedIndexes.has(Number(el.dataset.index));
      el.classList.toggle('deselected', !selected);
    });
    legendList.querySelectorAll('.cp-dist-legend-item').forEach(item => {
      const selected = selectedIndexes.has(Number(item.dataset.index));
      item.classList.toggle('deselected', !selected);
      item.setAttribute('aria-pressed', String(selected));
    });
  };
  const setHighlight = (index, event) => {
    wrap.dataset.highlight = String(index);
    svg.querySelectorAll('.cp-dist-line').forEach(path => {
      path.classList.toggle('highlighted', Number(path.dataset.index) === index);
      path.classList.toggle('dimmed', Number(path.dataset.index) !== index);
    });
    legendList.querySelectorAll('.cp-dist-legend-item').forEach(item => {
      item.classList.toggle('highlighted', Number(item.dataset.index) === index);
      item.classList.toggle('dimmed', Number(item.dataset.index) !== index);
    });
  };
  const clearHighlight = () => {
    delete wrap.dataset.highlight;
    svg.querySelectorAll('.cp-dist-line').forEach(path => path.classList.remove('highlighted', 'dimmed'));
    legendList.querySelectorAll('.cp-dist-legend-item').forEach(item => item.classList.remove('highlighted', 'dimmed'));
    tooltip.style.display = 'none';
    hoverLine.style.display = 'none';
  };
  const toggleSelection = index => {
    // With all lines selected, one click isolates that line; subsequent clicks toggle normally.
    if (isAllSelected()) {
      selectedIndexes.clear();
      selectedIndexes.add(index);
    } else if (selectedIndexes.has(index)) {
      selectedIndexes.delete(index);
    } else {
      selectedIndexes.add(index);
    }
    syncSelection();
  };
  const toggleSelectionFromGraph = (index, event) => {
    event.stopPropagation();
    toggleSelection(index);
  };
  legendControls.addEventListener('click', event => {
    const action = event.target?.dataset?.action;
    if (!action) return;
    if (action === 'all') {
      data.forEach((_, index) => selectedIndexes.add(index));
    } else if (action === 'none') {
      selectedIndexes.clear();
    }
    syncSelection();
  });

  data.forEach((row, index) => {
    const color = CHART_LINE_COLORS[index % CHART_LINE_COLORS.length];
    const points = CP_VALUES.map(cp => [x(cp), y(row[`cp_${cp}_pct`])]);
    const d = points.map((point, i) => `${i === 0 ? 'M' : 'L'} ${point[0].toFixed(2)} ${point[1].toFixed(2)}`).join(' ');
    const path = document.createElementNS(svgNs, 'path');
    path.setAttribute('d', d);
    path.setAttribute('class', 'cp-dist-line');
    path.setAttribute('stroke', color);
    path.dataset.index = String(index);
    path.addEventListener('click', event => toggleSelectionFromGraph(index, event));
    path.addEventListener('mouseenter', event => setHighlight(index, event));
    path.addEventListener('mousemove', event => {
      const nearestCp = nearestCpFromEvent(event, svg, margin, innerWidth);
      hoverLine.setAttribute('x1', x(nearestCp));
      hoverLine.setAttribute('x2', x(nearestCp));
      hoverLine.style.display = 'block';
      showChartTooltip(row, nearestCp, event, tooltip);
    });
    path.addEventListener('mouseleave', clearHighlight);
    svg.appendChild(path);

    CP_VALUES.forEach(cp => {
      const dot = document.createElementNS(svgNs, 'circle');
      dot.setAttribute('cx', x(cp));
      dot.setAttribute('cy', y(row[`cp_${cp}_pct`]));
      dot.setAttribute('r', '3');
      dot.setAttribute('class', 'cp-dist-dot');
      dot.setAttribute('fill', color);
      dot.dataset.index = String(index);
      dot.addEventListener('click', event => toggleSelectionFromGraph(index, event));
      dot.addEventListener('mouseenter', event => setHighlight(index, event));
      dot.addEventListener('mousemove', event => showChartTooltip(row, cp, event, tooltip));
      dot.addEventListener('mouseleave', clearHighlight);
      svg.appendChild(dot);
    });

    const legendItem = document.createElement('button');
    legendItem.type = 'button';
    legendItem.className = 'cp-dist-legend-item';
    legendItem.dataset.index = String(index);
    legendItem.setAttribute('aria-pressed', 'true');
    legendItem.innerHTML = `<span class="cp-dist-legend-swatch" style="background:${color}"></span><span>${titleCase(row.card_name || '')}</span>`;
    legendItem.addEventListener('click', () => toggleSelection(index));
    legendItem.addEventListener('mouseenter', event => setHighlight(index, event));
    legendItem.addEventListener('mouseleave', clearHighlight);
    legendList.appendChild(legendItem);
  });

  legend.appendChild(legendControls);
  legend.appendChild(legendList);
  syncSelection();
  chart.appendChild(svg);
  chart.appendChild(tooltip);
  wrap.appendChild(chart);
  wrap.appendChild(legend);
  return wrap;
}

function nearestCpFromEvent(event, svg, margin, innerWidth) {
  const rect = svg.getBoundingClientRect();
  const relativeX = Math.max(0, Math.min(innerWidth, event.clientX - rect.left - margin.left));
  return Math.max(0, Math.min(4, Math.round((relativeX / innerWidth) * 4)));
}

function showChartTooltip(row, cp, event, tooltip) {
  tooltip.innerHTML = `<strong>${titleCase(row.card_name || '')}</strong><div><span>${cp}: ${fmtPercent(row[`cp_${cp}_pct`])}</span></div>`;
  tooltip.style.display = 'block';
  const hostRect = tooltip.parentElement.getBoundingClientRect();
  const x = Math.min(event.clientX - hostRect.left + 14, hostRect.width - tooltip.offsetWidth - 8);
  const y = Math.max(8, Math.min(event.clientY - hostRect.top + 14, hostRect.height - tooltip.offsetHeight - 8));
  tooltip.style.left = `${x}px`;
  tooltip.style.top = `${y}px`;
}

function renderCpByMapGraph(data) {
  const tbody = document.getElementById('tableBody');
  const pagination = document.getElementById('pagination');
  const meta = document.getElementById('tableMeta');
  const sortedData = [...data].sort(compareRowsForCurrentSort);
  tbody.innerHTML = `<tr><td colspan="${columnCountForView()}" class="chart-host-cell"></td></tr>`;
  tbody.querySelector('.chart-host-cell').appendChild(buildCpByMapChart(sortedData));
  pagination.style.display = 'none';
  meta.innerHTML = '';
}

function buildCpByMapChart(data) {
  const wrap = document.createElement('div');
  wrap.className = 'cp-dist-chart-wrap';
  const chart = document.createElement('div');
  chart.className = 'cp-dist-chart';
  const legend = document.createElement('div');
  legend.className = 'cp-dist-legend';
  const controls = document.createElement('div');
  controls.className = 'cp-dist-legend-controls';
  controls.innerHTML = '<span>Lines</span><span>(<button type="button" data-action="all">all</button> / <button type="button" data-action="none">none</button>)</span>';
  const legendList = document.createElement('div');
  legendList.className = 'cp-dist-legend-list';
  const tooltip = document.createElement('div');
  tooltip.className = 'cp-dist-tooltip';
  const selected = new Set(data.map((_, index) => index));
  const values = data.flatMap(row => VALID_MAPS.map(map => cpMapValue(row, map.field))).filter(Number.isFinite);
  const observedMin = values.length ? Math.min(0, ...values) : 0;
  const observedMax = values.length ? Math.max(0, ...values) : 1;
  const padding = Math.max(0.1, (observedMax - observedMin) * 0.08);
  const yMin = cpMapMode === 'average' ? Math.floor((observedMin - padding) * 10) / 10 : 0;
  const yMax = Math.max(yMin + 0.5, Math.ceil((observedMax + padding) * 10) / 10);
  const width = 900;
  const height = 430;
  const margin = { top: 22, right: 22, bottom: 48, left: 54 };
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  const x = index => margin.left + (index / (VALID_MAPS.length - 1)) * innerWidth;
  const y = value => margin.top + innerHeight - ((Number(value) - yMin) / (yMax - yMin)) * innerHeight;
  const svgNs = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(svgNs, 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', 'Endgame conservation points by map line chart');
  const svgEl = (tag, attrs) => {
    const element = document.createElementNS(svgNs, tag);
    Object.entries(attrs).forEach(([key, value]) => element.setAttribute(key, value));
    svg.appendChild(element);
    return element;
  };

  for (let index = 0; index <= 4; index += 1) {
    const tick = yMin + (yMax - yMin) * index / 4;
    const gy = y(tick);
    svgEl('line', { x1: margin.left, x2: width - margin.right, y1: gy, y2: gy, class: 'cp-dist-grid' });
    const label = svgEl('text', {
      x: margin.left - 12, y: gy + 4, 'text-anchor': 'end', class: 'cp-dist-axis-label',
    });
    label.textContent = tick.toFixed(tick % 1 ? 1 : 0);
  }
  VALID_MAPS.forEach((map, index) => {
    const label = svgEl('text', {
      x: x(index), y: height - 15, 'text-anchor': 'middle', class: 'cp-dist-axis-label',
    });
    label.textContent = map.short;
  });
  svgEl('line', {
    x1: margin.left, x2: width - margin.right, y1: margin.top + innerHeight,
    y2: margin.top + innerHeight, class: 'cp-dist-axis',
  });
  svgEl('line', {
    x1: margin.left, x2: margin.left, y1: margin.top, y2: margin.top + innerHeight,
    class: 'cp-dist-axis',
  });
  if (cpMapMode === 'average') {
    svgEl('line', {
      x1: margin.left, x2: width - margin.right, y1: y(0), y2: y(0),
      class: 'icons-chart-zero',
    });
  }
  const hoverLine = svgEl('line', {
    class: 'cp-dist-hover-line', y1: margin.top, y2: margin.top + innerHeight,
  });
  hoverLine.style.display = 'none';

  const syncSelection = () => {
    svg.querySelectorAll('.cp-dist-line, .cp-dist-dot').forEach(element => {
      element.classList.toggle('deselected', !selected.has(Number(element.dataset.index)));
    });
    legendList.querySelectorAll('.cp-dist-legend-item').forEach(element => {
      const active = selected.has(Number(element.dataset.index));
      element.classList.toggle('deselected', !active);
      element.setAttribute('aria-pressed', String(active));
    });
  };
  const toggleLine = index => {
    if (selected.size === data.length) {
      selected.clear();
      selected.add(index);
    } else if (selected.has(index)) selected.delete(index);
    else selected.add(index);
    syncSelection();
  };
  const highlight = index => {
    svg.querySelectorAll('.cp-dist-line').forEach(element => {
      element.classList.toggle('highlighted', Number(element.dataset.index) === index);
      element.classList.toggle('dimmed', Number(element.dataset.index) !== index);
    });
    legendList.querySelectorAll('.cp-dist-legend-item').forEach(element => {
      element.classList.toggle('highlighted', Number(element.dataset.index) === index);
      element.classList.toggle('dimmed', Number(element.dataset.index) !== index);
    });
  };
  const clearHighlight = () => {
    svg.querySelectorAll('.cp-dist-line').forEach(element => element.classList.remove('highlighted', 'dimmed'));
    legendList.querySelectorAll('.cp-dist-legend-item').forEach(element => element.classList.remove('highlighted', 'dimmed'));
    hoverLine.style.display = 'none';
    tooltip.style.display = 'none';
  };
  const showPoint = (row, point, event) => {
    const display = cpMapMode === 'average' ? formatCpDifference(point.value) : `${point.value.toFixed(2)} CP`;
    tooltip.innerHTML = `<strong>${titleCase(row.card_name || '')}</strong><div><span>${point.map.short}: ${display}</span></div>`;
    tooltip.style.display = 'block';
    const rect = chart.getBoundingClientRect();
    tooltip.style.left = `${Math.min(event.clientX - rect.left + 14, rect.width - tooltip.offsetWidth - 8)}px`;
    tooltip.style.top = `${Math.max(8, Math.min(event.clientY - rect.top + 14, rect.height - tooltip.offsetHeight - 8))}px`;
  };
  controls.addEventListener('click', event => {
    if (event.target?.dataset?.action === 'all') data.forEach((_, index) => selected.add(index));
    if (event.target?.dataset?.action === 'none') selected.clear();
    syncSelection();
  });

  data.forEach((row, rowIndex) => {
    const color = CHART_LINE_COLORS[rowIndex % CHART_LINE_COLORS.length];
    const points = VALID_MAPS.map((map, mapIndex) => {
      const raw = row[map.field];
      const value = cpMapValue(row, map.field);
      return raw != null && Number.isFinite(value)
        ? { map, mapIndex, value, x: x(mapIndex), y: y(value) }
        : null;
    });
    let pathData = '';
    let segmentOpen = false;
    points.forEach(point => {
      if (!point) { segmentOpen = false; return; }
      pathData += `${segmentOpen ? 'L' : 'M'} ${point.x.toFixed(2)} ${point.y.toFixed(2)} `;
      segmentOpen = true;
    });
    if (pathData) {
      const path = svgEl('path', { d: pathData.trim(), class: 'cp-dist-line', stroke: color });
      path.dataset.index = String(rowIndex);
      path.addEventListener('click', event => { event.stopPropagation(); toggleLine(rowIndex); });
      path.addEventListener('mouseenter', () => highlight(rowIndex));
      path.addEventListener('mousemove', event => {
        const rect = svg.getBoundingClientRect();
        const relativeX = (event.clientX - rect.left) / rect.width * width;
        const nearest = points.filter(Boolean).reduce((best, point) =>
          !best || Math.abs(point.x - relativeX) < Math.abs(best.x - relativeX) ? point : best, null);
        if (!nearest) return;
        hoverLine.setAttribute('x1', nearest.x);
        hoverLine.setAttribute('x2', nearest.x);
        hoverLine.style.display = 'block';
        showPoint(row, nearest, event);
      });
      path.addEventListener('mouseleave', clearHighlight);
    }
    points.filter(Boolean).forEach(point => {
      const dot = svgEl('circle', { cx: point.x, cy: point.y, r: 3, class: 'cp-dist-dot', fill: color });
      dot.dataset.index = String(rowIndex);
      dot.addEventListener('click', event => { event.stopPropagation(); toggleLine(rowIndex); });
      dot.addEventListener('mouseenter', event => { highlight(rowIndex); showPoint(row, point, event); });
      dot.addEventListener('mousemove', event => showPoint(row, point, event));
      dot.addEventListener('mouseleave', clearHighlight);
    });
    const item = document.createElement('button');
    item.type = 'button';
    item.className = 'cp-dist-legend-item';
    item.dataset.index = String(rowIndex);
    item.setAttribute('aria-pressed', 'true');
    item.innerHTML = `<span class="cp-dist-legend-swatch" style="background:${color}"></span><span>${titleCase(row.card_name || '')}</span>`;
    item.addEventListener('click', () => toggleLine(rowIndex));
    item.addEventListener('mouseenter', () => highlight(rowIndex));
    item.addEventListener('mouseleave', clearHighlight);
    legendList.appendChild(item);
  });
  legend.append(controls, legendList);
  chart.append(svg, tooltip);
  wrap.append(chart, legend);
  syncSelection();
  return wrap;
}

function renderCpByMapRow(tr, row, ranges) {
  appendCell(tr, 'rank-cell', row.global_rank ?? '\u2014');
  appendCell(tr, 'card-name', titleCase(row.card_name || ''));
  VALID_MAPS.forEach(map => {
    const val = cpMapValue(row, map.field);
    appendCell(
      tr,
      `n-cell cp-map-cell${cpMapMode === 'average' ? ' cp-map-comparison' : ''}`,
      Number.isFinite(val) ? (cpMapMode === 'average' ? formatCpDifference(val) : val.toFixed(2)) : '\u2014',
      cpMapMode === 'average'
        ? deltaRangeColor(val, ranges.cp_by_map?.min, ranges.cp_by_map?.max)
        : cpMapColor(val, ranges.cp_by_map),
    );
  });
  appendCell(tr, 'delta cp-cell', row.avg_cp != null ? Number(row.avg_cp).toFixed(2) : '\u2014', cpColor(row.avg_cp, ranges.avg_cp));
}

function columnCountForView() {
  if (activeEndgamesView === ENDGAMES_VIEW_CP_DISTRIBUTION) return 8;
  if (activeEndgamesView === ENDGAMES_VIEW_CP_DISTRIBUTION_GRAPH) return 8;
  if (activeEndgamesView === ENDGAMES_VIEW_CP_BY_MAP) return 18;
  if (activeEndgamesView === ENDGAMES_VIEW_CP_BY_MAP_GRAPH) return 18;
  return 9;
}

function buildPagination(totalPages) {
  let html = `<button class="page-btn" onclick="goPage(${currentPage - 1})" ${currentPage === 1 ? 'disabled' : ''}>&lt;</button>`;
  const pages = paginationRange(currentPage, totalPages);
  let prev = null;
  for (const p of pages) {
    if (prev !== null && p - prev > 1) html += `<span class="page-info">...</span>`;
    html += `<button class="page-btn ${p === currentPage ? 'active' : ''}" onclick="goPage(${p})">${p}</button>`;
    prev = p;
  }
  html += `<button class="page-btn" onclick="goPage(${currentPage + 1})" ${currentPage === totalPages ? 'disabled' : ''}>&gt;</button>`;
  return html;
}

function paginationRange(current, total) {
  const delta = 2;
  const range = [];
  for (let i = Math.max(1, current - delta); i <= Math.min(total, current + delta); i++) range.push(i);
  if (!range.includes(1)) range.unshift(1);
  if (!range.includes(total)) range.push(total);
  return range;
}

function goPage(p) {
  const rpp = rowsPerPage >= 9999 ? filteredData.length || 1 : rowsPerPage;
  const totalPages = Math.ceil(filteredData.length / rpp);
  if (p < 1 || p > totalPages) return;
  currentPage = p;
  applySortAndRender();
  document.querySelector('.table-wrap')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function showLoading(mode = 'query') {
  document.querySelectorAll('#statsTable th.sorted').forEach(th => th.classList.remove('sorted'));
  document.querySelectorAll('#statsTable .sort-arrow').forEach(arrow => { arrow.textContent = '\u2195'; });
  const isSavedSnapshot = mode === 'saved';
  const title = isSavedSnapshot ? 'Preparing data...' : 'Fetching data...';
  const sub = isSavedSnapshot
    ? 'Loading the latest available endgame statistics.'
    : 'Querying BigQuery with your current filters.';
  document.getElementById('tableBody').innerHTML = `<tr><td colspan="${columnCountForView()}">
    <div class="state-overlay">
      <div class="spinner"></div>
      <div class="state-title">${title}</div>
      <div class="state-sub">${sub}</div>
    </div>
  </td></tr>`;
  document.getElementById('pagination').style.display = 'none';
  document.getElementById('tableMeta').innerHTML = '';
}

function showError(msg) {
  const tbody = document.getElementById('tableBody');
  tbody.innerHTML = `<tr><td colspan="${columnCountForView()}">
    <div class="state-overlay">
      <div class="error-icon">!</div>
      <div class="state-title">Something went wrong</div>
      <div class="state-sub"></div>
    </div>
  </td></tr>`;
  tbody.querySelector('.state-sub').textContent = msg;
}

function fmtDelta(val) {
  return formatSignedDeltaAdaptive(val);
}

function fmtN(val) {
  if (val == null) return '\u2014';
  return Number(val).toLocaleString('en-US');
}

function fmtPercent(val) {
  if (val == null) return '\u2014';
  return `${Number(val).toFixed(2)}%`;
}

function titleCase(str) {
  const lower = new Set(['on', 'in', 'of', 'the', 'a']);
  return String(str || '').split(' ').map((word, i) => {
    const w = word.toLowerCase();
    if (i > 0 && lower.has(w)) return w;
    return w.replace(/[A-Za-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u00FF]/, ch => ch.toUpperCase());
  }).join(' ');
}

function cpPctColor(val, range) {
  if (val == null) return 'var(--text-muted)';
  return frequencyColor(val);
}

function cpMapValue(row, field) {
  if (row?.[field] == null) return Number.NaN;
  const raw = Number(row[field]);
  if (!Number.isFinite(raw)) return Number.NaN;
  if (cpMapMode !== 'average') return raw;
  const average = Number(row.avg_cp);
  return Number.isFinite(average) ? raw - average : Number.NaN;
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[char]));
}

const escapeAttr = escapeHtml;

function formatCpDifference(value) {
  const number = Math.abs(Number(value)) < 0.005 ? 0 : Number(value);
  if (number === 0) return '\u00b10.00';
  return `${number > 0 ? '+' : '\u2212'}${Math.abs(number).toFixed(2)}`;
}

function cpMapColor(val, range) {
  if (val == null) return 'var(--text-muted)';
  return divergingRangeColor(val, range?.min, range?.max);
}

const prColor = playrateColor;
const eloColor = relativeEloColor;

function cpColor(val, range) {
  if (val == null) return 'var(--text-muted)';
  return orangeGreenRangeColor(val, range?.min, range?.max);
}

const _colTip = document.getElementById('col-tooltip');

function endgamesHeaderTooltipSource(event) {
  const mapTip = event.target.closest?.('.maps-custom-tip');
  if (mapTip) return mapTip;
  const th = event.target.closest?.('th');
  return th?.querySelector('.col-tip') || null;
}

document.addEventListener('mouseover', e => {
  if (!isPageMounted || !_colTip) return;
  const tipEl = endgamesHeaderTooltipSource(e);
  if (!tipEl) return;
  if (tipEl.hasAttribute('data-tip-fraction')) {
    _colTip.innerHTML = `<div class="tip-combo"><div class="tip-fraction"><span class="tip-num">scored</span><span class="tip-den">dealt</span></div><div class="tip-note">(can exceed 100% due to<br>Elephants and Adapt)</div></div>`;
  } else {
    _colTip.textContent = tipEl.dataset.tip || '';
  }
  _colTip.style.display = 'block';
  positionColTip(e);
});

document.addEventListener('mousemove', e => {
  if (!isPageMounted || !_colTip || _colTip.style.display === 'none') return;
  if (e.target.closest('.delta-ci-cell')) return;
  if (!endgamesHeaderTooltipSource(e)) {
    _colTip.style.display = 'none';
    return;
  }
  positionColTip(e);
});

document.addEventListener('mouseout', e => {
  if (!isPageMounted || !_colTip) return;
  if (e.target.closest('.delta-ci-cell') || e.relatedTarget?.closest('.delta-ci-cell')) return;
  const source = endgamesHeaderTooltipSource(e);
  const destination = e.relatedTarget?.closest?.('.maps-custom-tip') || e.relatedTarget?.closest?.('th')?.querySelector('.col-tip');
  if (source && destination !== source) _colTip.style.display = 'none';
});

function positionColTip(e) {
  if (!_colTip) return;
  const tw = _colTip.offsetWidth;
  const th = _colTip.offsetHeight;
  const margin = 8;
  let x = e.clientX - tw / 2;
  let y = e.clientY + 18;
  x = Math.max(margin, Math.min(x, window.innerWidth - tw - margin));
  if (y + th > window.innerHeight - margin) y = e.clientY - th - 10;
  _colTip.style.left = `${x}px`;
  _colTip.style.top = `${y}px`;
}

function selectAllMaps() {
  document.querySelectorAll('#mapChips .chip').forEach(c => c.classList.add('active'));
}

function selectNoneMaps() {
  document.querySelectorAll('#mapChips .chip').forEach(c => c.classList.remove('active'));
}

export function setDataset(value) {
  isMW = Number(value) === 0 ? 0 : 1;
  if (!isPageMounted) return;
  applyFilters(mountToken);
}

export function unmount() {
  isPageMounted = false;
  mountToken += 1;
  const searchInput = document.getElementById('searchInput');
  if (searchInput) searchInput.removeEventListener('input', onSearch);
  if (_colTip) _colTip.style.display = 'none';
}

const PAGE_WINDOW_HANDLERS = {
  sortBy,
  onSearch,
  openCardSearch,
  closeCardSearch,
  resetFilters,
  selectAllMaps,
  selectNoneMaps,
  applyFiltersFromSidebar,
  goPage,
  setEndgamesView,
  setEndgamesGraphView,
  onEndgamesGraphToggleKey,
  setEndgamesMapGraphView,
  onEndgamesMapGraphToggleKey,
  setCpMapMode,
};

function bindWindowHandlers() {
  Object.assign(window, PAGE_WINDOW_HANDLERS);
}
