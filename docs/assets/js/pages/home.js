export const id = 'home';
export const title = 'Home';
export const navLabel = 'Home';

export const mainHtml = `
  <div class="home-wrap" id="homeGrid"></div>`;

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
      <input class="range-input" type="number" id="playerEloMin" placeholder="Min" min="0" />
      <input class="range-input" type="number" id="playerEloMax" placeholder="Max" min="0" />
    </div>
  </div>

  <div class="filter-group">
    <span class="filter-label">Opponent ELO</span>
    <div class="range-row">
      <input class="range-input" type="number" id="opponentEloMin" placeholder="Min" min="0" />
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
    <input class="date-input" type="text" inputmode="numeric" pattern="\\d{4}-\\d{2}-\\d{2}" placeholder="yyyy-mm-dd" id="dateFrom" />
    <input class="date-input" type="text" inputmode="numeric" pattern="\\d{4}-\\d{2}-\\d{2}" placeholder="yyyy-mm-dd" id="dateTo" />
  </div>

  <hr class="divider" />

  <div class="filter-group">
    <div class="toggle-row">
      <span class="toggle-label">Completed games only</span>
      <label class="toggle">
        <input type="checkbox" id="endGameToggle" />
        <span class="toggle-track"></span>
      </label>
    </div>
  </div>

  <hr class="divider" />

  <div class="filter-action-stack">
    <button class="apply-btn" id="applyBtn" onclick="applyFiltersFromSidebar()">Apply filters</button>
  </div>`;

const API_URL = 'https://europe-west1-ark-nova-stats-dashboard.cloudfunctions.net/get-card-stats';
const DEFAULT_SNAPSHOT_URLS = {
  1: 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/home/default-mw.json',
  0: 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/home/default-base.json',
};
const MAP_GROUPS = [
  {
    id: 'current',
    maps: [
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
    ],
  },
  {
    id: 'original',
    maps: [
      { short: '1', full: 'Map 1: Observation Tower' },
      { short: '2', full: 'Map 2: Outdoor Areas' },
      { short: '3', full: 'Map 3: Silver Lake' },
      { short: '4', full: 'Map 4: Commercial Harbor' },
      { short: '5', full: 'Map 5: Park Restaurant' },
      { short: '6', full: 'Map 6: Research Institute' },
      { short: '7', full: 'Map 7: Ice Cream Parlors' },
      { short: '8', full: 'Map 8: Hollywood Hills' },
    ],
  },
  {
    id: 'beginner',
    maps: [
      { short: 'A', full: 'Map A' },
      { short: '0', full: 'Map 0' },
    ],
  },
];
const ALL_MAPS = MAP_GROUPS.flatMap(group => group.maps);
// Population groups:
// INDEXED: games_indexed + animals_played, sponsors_played, projects_supported,
//          breaks_triggered, x_tokens_gained
// LOGGED:  games_logged + emus_played, two_cp_workers_taken,
//          empty_petting_zoos_played, free_unis_and_partner_zoos, bignose_project_blocks
//
// accent keys map to CSS classes (ht--<accent>)
// Hero tiles use 'idx-hero' / 'log-hero'; stat tiles use idx-a..idx-e / log-a..log-e
const TILE_GROUPS = {
  indexed: {
    hero:  { key: 'games_indexed',             label: ['Games', 'indexed'],          accent: 'idx-hero' },
    stats: [
      { key: 'animals_played',                 label: ['Animals', 'played'],          accent: 'idx-a' },
      { key: 'sponsors_played',                label: ['Sponsors', 'played'],         accent: 'idx-b' },
      { key: 'projects_supported',             label: ['Projects', 'supported'],      accent: 'idx-c' },
      { key: 'breaks_triggered',               label: ['Breaks', 'triggered'],        accent: 'idx-d' },
      { key: 'x_tokens_gained',                label: ['X-tokens', 'gained'],         accent: 'idx-e' },
    ],
  },
  logged: {
    hero:  { key: 'games_logged',              label: ['Games', 'logged'],            accent: 'log-hero' },
    stats: [
      { key: 'emus_played',                    label: ['Emus', 'played'],             accent: 'log-a' },
      { key: 'two_cp_workers_taken',           label: ['2 CP', 'workers taken'],      accent: 'log-b' },
      { key: 'empty_petting_zoos_played',      label: ['Empty', 'Petting Zoos'],      accent: 'log-c' },
      { key: 'free_unis_and_partner_zoos',     label: ['Free Unis &', 'Partner Zoos'],accent: 'log-d' },
      { key: 'bignose_project_blocks',         label: ['Bignose', 'Project Blocks'],  accent: 'log-e' },
    ],
  },
};

let isPageMounted = false;
let mountToken = 0;
let isMW = 1;
let selectedMaps = ALL_MAPS.map(map => map.full);
const defaultSnapshotCache = { 0: null, 1: null };

export function mount({ dataset = 1 } = {}) {
  bindWindowHandlers();
  isPageMounted = true;
  mountToken += 1;
  isMW = Number(dataset) === 0 ? 0 : 1;
  selectedMaps = ALL_MAPS.map(map => map.full);
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
    toggleMapChip,
  });
}

function isCurrentMount(token) {
  return isPageMounted && token === mountToken;
}

function getParams() {
  const val = id => document.getElementById(id)?.value || '';
  return {
    stats_page: 'home',
    is_mw: isMW,
    maps: selectedMaps,
    player_elo_min: val('playerEloMin') ? Number(val('playerEloMin')) : null,
    player_elo_max: val('playerEloMax') ? Number(val('playerEloMax')) : null,
    opponent_elo_min: val('opponentEloMin') ? Number(val('opponentEloMin')) : null,
    opponent_elo_max: val('opponentEloMax') ? Number(val('opponentEloMax')) : null,
    date_from: val('dateFrom') || null,
    date_to: val('dateTo') || null,
    end_game_triggered: document.getElementById('endGameToggle')?.checked ? true : null,
  };
}

function isDefaultParams(params) {
  return params.player_elo_min === null &&
    params.player_elo_max === null &&
    params.opponent_elo_min === null &&
    params.opponent_elo_max === null &&
    params.date_from === null &&
    params.date_to === null &&
    params.end_game_triggered === null &&
    selectedMaps.length === ALL_MAPS.length;
}

async function applyFilters(token = mountToken) {
  const params = getParams();
  const usesDefault = isDefaultParams(params);
  if (usesDefault) {
    const embedded = getEmbeddedDefaultSnapshot(isMW);
    if (embedded) {
      if (isCurrentMount(token)) renderTiles(embedded.data || []);
      return;
    }
  } else {
    renderLoading();
  }
  try {
    let payload;
    if (usesDefault) {
      try {
        payload = await loadDefaultSnapshot(isMW);
      } catch {
        payload = await fetchApi(params);
      }
    } else {
      payload = await fetchApi(params);
    }
    if (!isCurrentMount(token)) return;
    renderTiles(payload.data || []);
  } catch (error) {
    if (!isCurrentMount(token)) return;
    renderError(error);
  }
}

function getEmbeddedDefaultSnapshot(dataset) {
  const snapshots = window.__ARK_NOVA_HOME_DEFAULTS__;
  const payload = snapshots?.[String(Number(dataset) === 0 ? 0 : 1)];
  return payload && Array.isArray(payload.data) ? payload : null;
}

async function loadDefaultSnapshot(dataset) {
  const embedded = getEmbeddedDefaultSnapshot(dataset);
  if (embedded) return embedded;
  if (defaultSnapshotCache[dataset]) return defaultSnapshotCache[dataset];
  const response = await fetch(DEFAULT_SNAPSHOT_URLS[dataset], { cache: 'no-store' });
  if (!response.ok) throw new Error(`Snapshot request failed (${response.status})`);
  const payload = await response.json();
  defaultSnapshotCache[dataset] = payload;
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

function renderTiles(rows) {
  const values = new Map(rows.map(row => [row.metric, Number(row.value || 0)]));
  const grid = document.getElementById('homeGrid');
  if (!grid) return;

  // Build each population row: hero tile (col 1) + 5 stat tiles (cols 2-6)
  const rowHtml = (group) => {
    const { hero, stats } = group;
    const heroHtml = `
      <section class="ht ht--hero ht--${hero.accent}">
        ${renderTileLabel(hero.label)}
        <div class="ht__value">${formatInteger(values.get(hero.key))}</div>
      </section>`;
    const statsHtml = stats.map(s => `
      <section class="ht ht--${s.accent}">
        ${renderTileLabel(s.label)}
        <div class="ht__value">${formatInteger(values.get(s.key))}</div>
      </section>`).join('');
    return heroHtml + statsHtml;
  };

  grid.innerHTML = `
    <div class="home-pop-row home-pop-row--indexed">${rowHtml(TILE_GROUPS.indexed)}</div>
    <div class="home-pop-row home-pop-row--logged">${rowHtml(TILE_GROUPS.logged)}</div>`;
}


function renderTileLabel(label) {
  const lines = Array.isArray(label) ? label : String(label ?? '').split(' / ');
  return `<div class="ht__label">${lines.map(line => `<span>${escapeHtml(line)}</span>`).join('')}</div>`;
}

function renderLoading() {
  const grid = document.getElementById('homeGrid');
  if (!grid) return;
  grid.innerHTML = `<div class="state-overlay home-state">
    <div class="spinner"></div>
    <div class="state-title">Fetching data...</div>
    <div class="state-sub">Loading dashboard facts.</div>
  </div>`;
}

function renderError(error) {
  const grid = document.getElementById('homeGrid');
  if (!grid) return;
  grid.innerHTML = `<div class="state-overlay home-state">
    <div class="state-title">Could not load homepage</div>
    <div class="state-sub">${escapeHtml(error.message || String(error))}</div>
  </div>`;
}

function renderMapChips() {
  const container = document.getElementById('mapChips');
  if (!container) return;
  container.innerHTML = MAP_GROUPS.map(group => `
    <div class="home-map-group home-map-group-${group.id}">
      ${group.maps.map(map => `
        <button class="chip ${selectedMaps.includes(map.full) ? 'active' : ''}" type="button"
                title="${escapeHtml(map.full)}" onclick="toggleMapChip('${escapeAttr(map.full)}')">
          ${escapeHtml(map.short)}
        </button>`).join('')}
    </div>`).join('');
}

function toggleMapChip(mapName) {
  if (selectedMaps.length === ALL_MAPS.length && selectedMaps.includes(mapName)) {
    selectedMaps = [mapName];
    renderMapChips();
    return;
  }
  if (selectedMaps.includes(mapName)) {
    selectedMaps = selectedMaps.filter(map => map !== mapName);
  } else {
    selectedMaps = [...selectedMaps, mapName];
  }
  renderMapChips();
}

function selectAllMaps() {
  selectedMaps = ALL_MAPS.map(map => map.full);
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
  setValue('playerEloMin', '');
  setValue('playerEloMax', '');
  setValue('opponentEloMin', '');
  setValue('opponentEloMax', '');
  setValue('dateFrom', '');
  setValue('dateTo', '');
  const toggle = document.getElementById('endGameToggle');
  if (toggle) toggle.checked = false;
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

function formatInteger(value) {
  if (!Number.isFinite(value)) return '-';
  return Math.round(value).toLocaleString('en-US');
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
