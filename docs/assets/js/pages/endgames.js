export const id = 'endgames';
export const title = 'Endgames';
export const navLabel = 'Endgames';

export const mainHtml = `
  <div class="main-header">
    <div class="table-meta" id="tableMeta"></div>
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
        <button class="endgames-tab" type="button" data-view="cp_by_map" onclick="setEndgamesView('cp_by_map')">CP by map</button>
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
let apiWarmupInFlight = false;
let apiWarmupLastAt = 0;
const API_WARMUP_COOLDOWN_MS = 30000;
const defaultSnapshotCache = {};
const CP_VALUES = [0, 1, 2, 3, 4];
const CP_PCT_COLOR_MAX = 50;
const CP_MAP_COLOR_MIN = 1.5;
const CP_MAP_COLOR_MAX = 4;
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
  if (group === 'map' && isAllSelectedChipClick(btn, '#mapChips .chip')) return;
  btn.classList.toggle('active');
}

function isAllSelectedChipClick(btn, selector) {
  const chips = [...document.querySelectorAll(selector)];
  if (!chips.length || chips.some(c => !c.classList.contains('active'))) return false;
  chips.forEach(c => c.classList.toggle('active', c === btn));
  return true;
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

function updateEndgamesTabs() {
  document.querySelectorAll('.endgames-tab').forEach(btn => {
    const tabView = btn.dataset.view;
    const isActive = tabView === activeEndgamesView ||
      (tabView === ENDGAMES_VIEW_CP_DISTRIBUTION && activeEndgamesView === ENDGAMES_VIEW_CP_DISTRIBUTION_GRAPH);
    btn.classList.toggle('active', isActive);
    btn.classList.toggle('graph-active', tabView === ENDGAMES_VIEW_CP_DISTRIBUTION && activeEndgamesView === ENDGAMES_VIEW_CP_DISTRIBUTION_GRAPH);
    btn.setAttribute('aria-selected', String(isActive));
  });
  document.querySelectorAll('.endgames-graph-toggle').forEach(btn => {
    btn.classList.toggle('active', activeEndgamesView === ENDGAMES_VIEW_CP_DISTRIBUTION_GRAPH);
  });
}

function updateMapFilterVisibility() {
  const hideMapFilter = activeEndgamesView === ENDGAMES_VIEW_CP_BY_MAP;
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
  const selectedMaps = activeEndgamesView === ENDGAMES_VIEW_CP_BY_MAP
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

  if (pMin) params.player_elo_min = parseInt(pMin, 10);
  if (pMax) params.player_elo_max = parseInt(pMax, 10);
  if (oMin) params.opponent_elo_min = parseInt(oMin, 10);
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
  if (activeEndgamesView !== ENDGAMES_VIEW_CP_BY_MAP && !(params.maps || []).length) {
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
    if (defaultSnapshotKey !== null) {
      try {
        const snapshotRes = await fetch(snapshotUrlForKey(defaultSnapshotKey), { cache: 'no-cache' });
        if (!snapshotRes.ok) throw new Error(`Snapshot HTTP ${snapshotRes.status}`);
        json = await snapshotRes.json();
      } catch (snapshotErr) {
        const res = await fetch(API_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(params),
        });
        json = await res.json();
      }
    } else {
      const res = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
        cache: 'no-store',
      });
      json = await res.json();
    }
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
  const av = a[col];
  const bv = b[col];
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
  if (activeEndgamesView === ENDGAMES_VIEW_CP_DISTRIBUTION_GRAPH) {
    // Preserve the table header footprint so graph/table switching does not shift the page.
    thead.innerHTML = cpDistributionHeadHtml();
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
  table.classList.toggle('cp-distribution-graph-view', activeEndgamesView === ENDGAMES_VIEW_CP_DISTRIBUTION_GRAPH);
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
      <th onclick="sortBy('playrate_pct')" style="width:13%;text-align:center">Keeprate <span class="col-tip" data-tip-fraction>?</span><span class="sort-arrow" id="sort-playrate_pct">\u2195</span></th>
      <th onclick="sortBy('n_played')" style="width:10%;text-align:center">Scored<span class="col-tip" data-tip="n scored">?</span><span class="sort-arrow" id="sort-n_played">\u2195</span></th>
      <th onclick="sortBy('n_seen')" style="width:10%;text-align:center">Dealt<span class="col-tip" data-tip="n dealt">?</span><span class="sort-arrow" id="sort-n_seen">\u2195</span></th>
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
      ${VALID_MAPS.map(map => `<th onclick="sortBy('${map.field}')" title="${map.full}" style="width:5%;text-align:center">${map.short}<span class="sort-arrow" id="sort-${map.field}">\u2195</span></th>`).join('')}
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

function appendDeltaCiCell(rowEl, row, prefix, text, color) {
  const cell = appendCell(rowEl, 'delta delta-ci-cell', text, color);
  cell.dataset.ciLow = row[`${prefix}_ci95_low`] ?? '';
  cell.dataset.ciHigh = row[`${prefix}_ci95_high`] ?? '';
  cell.dataset.ciN = row[`${prefix}_ci95_n`] ?? '';
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

  const rpp = rowsPerPage >= 9999 ? data.length : rowsPerPage;
  const totalPages = Math.ceil(data.length / rpp);
  if (currentPage > totalPages) currentPage = totalPages;
  const start = (currentPage - 1) * rpp;
  const pageData = data.slice(start, start + rpp);
  const eloVals = data.map(r => r.avg_elo).filter(v => v != null);
  const minElo = eloVals.length ? Math.min(...eloVals) : 0;
  const maxElo = eloVals.length ? Math.max(...eloVals) : 0;

  tbody.replaceChildren();
  pageData.forEach(row => {
    const tr = document.createElement('tr');
    if (activeEndgamesView === ENDGAMES_VIEW_CP_DISTRIBUTION) renderCpDistributionRow(tr, row);
    else if (activeEndgamesView === ENDGAMES_VIEW_CP_BY_MAP) renderCpByMapRow(tr, row);
    else renderGeneralRow(tr, row, minElo, maxElo);
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

function renderGeneralRow(tr, row, minElo, maxElo) {
  const prVal = row.playrate_pct || 0;
  const cpVal = row.avg_cp;
  appendCell(tr, 'rank-cell', row.global_rank ?? '\u2014');
  appendCell(tr, 'card-name', titleCase(row.card_name || ''));
  appendDeltaCiCell(tr, row, 'delta_in_hand', fmtDelta(row.delta_in_hand), deltaColor(row.delta_in_hand));
  appendDeltaCiCell(tr, row, 'delta_played', fmtDelta(row.delta_played), deltaColor(row.delta_played));
  appendCell(tr, 'n-cell', row.avg_elo != null ? Math.round(row.avg_elo).toLocaleString('en-US') : '\u2014', eloColor(row.avg_elo, minElo, maxElo));
  appendPlayrateCell(
    tr,
    row.playrate_pct != null ? `${row.playrate_pct.toFixed(2)}%` : '\u2014',
    prVal,
    Math.min(Math.max(prVal, 0), 100),
    prColor(prVal),
  );
  appendCell(tr, 'n-cell', fmtN(row.n_played));
  appendCell(tr, 'n-cell', fmtN(row.n_seen));
  appendCell(tr, 'delta cp-cell', cpVal != null ? Number(cpVal).toFixed(2) : '\u2014', cpColor(cpVal));
}

function renderCpDistributionRow(tr, row) {
  appendCell(tr, 'rank-cell', row.global_rank ?? '\u2014');
  appendCell(tr, 'card-name', titleCase(row.card_name || ''));
  CP_VALUES.forEach(cp => {
    const pct = row[`cp_${cp}_pct`];
    appendCell(tr, 'n-cell cp-pct-cell', fmtPercent(pct), cpPctColor(pct));
  });
  appendCell(tr, 'delta cp-cell', row.avg_cp != null ? Number(row.avg_cp).toFixed(2) : '\u2014', cpColor(row.avg_cp));
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
    if (event) showChartTooltip(data[index], event, tooltip);
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
      showChartTooltip(row, event, tooltip);
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
      dot.addEventListener('mousemove', event => showChartTooltip(row, event, tooltip));
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
    legendItem.addEventListener('mousemove', event => showChartTooltip(row, event, tooltip));
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

function showChartTooltip(row, event, tooltip) {
  const values = CP_VALUES.map(cp => `<span>${cp}: ${fmtPercent(row[`cp_${cp}_pct`])}</span>`).join('');
  tooltip.innerHTML = `<strong>${titleCase(row.card_name || '')}</strong><div>${values}</div>`;
  tooltip.style.display = 'block';
  const hostRect = tooltip.parentElement.getBoundingClientRect();
  const x = Math.min(event.clientX - hostRect.left + 14, hostRect.width - tooltip.offsetWidth - 8);
  const y = Math.max(8, Math.min(event.clientY - hostRect.top + 14, hostRect.height - tooltip.offsetHeight - 8));
  tooltip.style.left = `${x}px`;
  tooltip.style.top = `${y}px`;
}

function renderCpByMapRow(tr, row) {
  appendCell(tr, 'rank-cell', row.global_rank ?? '\u2014');
  appendCell(tr, 'card-name', titleCase(row.card_name || ''));
  VALID_MAPS.forEach(map => {
    const val = row[map.field];
    appendCell(tr, 'n-cell cp-map-cell', val != null ? Number(val).toFixed(2) : '\u2014', cpMapColor(val));
  });
  appendCell(tr, 'delta cp-cell', row.avg_cp != null ? Number(row.avg_cp).toFixed(2) : '\u2014', cpColor(row.avg_cp));
}

function columnCountForView() {
  if (activeEndgamesView === ENDGAMES_VIEW_CP_DISTRIBUTION) return 8;
  if (activeEndgamesView === ENDGAMES_VIEW_CP_DISTRIBUTION_GRAPH) return 8;
  if (activeEndgamesView === ENDGAMES_VIEW_CP_BY_MAP) return 18;
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
  if (val == null) return '\u2014';
  const sign = val >= 0 ? '+' : '';
  return `${sign}${Number(val).toFixed(3)}`;
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

function deltaColor(val) {
  if (val == null) return 'var(--text-muted)';
  if (val >= 0.6) return 'var(--pos-strong)';
  if (val >= 0.3) return 'var(--pos-mid)';
  if (val >= 0.05) return 'var(--pos-weak)';
  if (val >= -0.05) return 'var(--neutral)';
  if (val >= -0.3) return 'var(--neg-weak)';
  if (val >= -0.6) return 'var(--neg-mid)';
  return 'var(--neg-strong)';
}

function cpPctColor(val) {
  if (val == null) return 'var(--text-muted)';
  const t = Math.max(0, Math.min(1, Number(val) / CP_PCT_COLOR_MAX));
  const low = { r: 0x62, g: 0x8f, b: 0x72 };
  const high = { r: 0x78, g: 0xe3, b: 0x8f };
  const mix = key => Math.round(low[key] + (high[key] - low[key]) * t);
  return `rgba(${mix('r')}, ${mix('g')}, ${mix('b')}, ${0.78 + t * 0.22})`;
}

function cpMapColor(val) {
  if (val == null) return 'var(--text-muted)';
  const t = Math.max(0, Math.min(1, (Number(val) - CP_MAP_COLOR_MIN) / (CP_MAP_COLOR_MAX - CP_MAP_COLOR_MIN)));
  if (t >= 0.86) return 'var(--pos-strong)';
  if (t >= 0.68) return 'var(--pos-mid)';
  if (t >= 0.52) return 'var(--pos-weak)';
  if (t >= 0.42) return 'var(--neutral)';
  if (t >= 0.24) return 'var(--neg-weak)';
  if (t >= 0.12) return 'var(--neg-mid)';
  return 'var(--neg-strong)';
}

function prColor(val) {
  if (val >= 50) return 'var(--pr-high)';
  if (val >= 30) return 'var(--pr-mid)';
  return 'var(--pr-low)';
}

function eloColor(val, minElo, maxElo) {
  if (val == null) return 'var(--text-muted)';
  if (maxElo === minElo) return 'var(--elo-mid)';
  const t = (val - minElo) / (maxElo - minElo);
  if (t >= 0.66) return 'var(--elo-high)';
  if (t >= 0.33) return 'var(--elo-mid)';
  return 'var(--elo-low)';
}

function cpColor(val) {
  if (val == null) return 'var(--text-muted)';
  const t = Math.max(0, Math.min(1, Number(val) / 4));
  const low = { r: 0xFF, g: 0x60, b: 0x27 };
  const high = { r: 0x7C, g: 0xBA, b: 0x43 };
  const mix = key => Math.round(low[key] + (high[key] - low[key]) * t);
  return `rgb(${mix('r')}, ${mix('g')}, ${mix('b')})`;
}

const _colTip = document.getElementById('col-tooltip');

document.addEventListener('mouseover', e => {
  if (!isPageMounted || !_colTip) return;
  const th = e.target.closest('th');
  if (!th) return;
  const tipEl = th.querySelector('.col-tip');
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
  const th = e.target.closest('th');
  if (!th || !th.querySelector('.col-tip')) {
    _colTip.style.display = 'none';
    return;
  }
  positionColTip(e);
});

document.addEventListener('mouseout', e => {
  if (!isPageMounted || !_colTip) return;
  if (e.target.closest('.delta-ci-cell') || e.relatedTarget?.closest('.delta-ci-cell')) return;
  const th = e.target.closest('th');
  if (!th || !e.relatedTarget?.closest('th') || e.relatedTarget.closest('th') !== th) {
    _colTip.style.display = 'none';
  }
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
};

function bindWindowHandlers() {
  Object.assign(window, PAGE_WINDOW_HANDLERS);
}
