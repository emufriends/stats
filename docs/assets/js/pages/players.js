import { divergingRangeColor } from '../color-scales.js?v=20260711-1';
import { fetchStats, loadSnapshot, loadStats } from '../snapshot-cache.js?v=20260713-4';
import { setFilterButtonDisabled, setTopbarDatasetLock } from '../layout.js?v=20260713-4';

export const id = 'players';
export const title = 'Players';
export const navLabel = 'Players';

const API_ROOT = 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/players';
const API_URL = 'https://europe-west1-ark-nova-stats-dashboard.cloudfunctions.net/get-card-stats';
const INDEX_URL = dataset => `${API_ROOT}/index/default-${dataset ? 'mw' : 'base'}.json`;
const SNAPSHOT_URL = dataset => `${API_ROOT}/general/default-${dataset ? 'mw' : 'base'}.json`;
const ARENA_MANIFEST_URL = `${API_ROOT}/arena/manifest.json`;
const ARENA_BUNDLE_URL = `${API_ROOT}/arena-top-100/all-seasons.json`;
const ARENA_LINE_COLORS = ['#42d392', '#60a5fa', '#f59e0b', '#c084fc', '#fb7185'];
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
const POPULATIONS = ['player', 'all', 'winners', 'experts', 'masters'];
const SPENDING_METRICS = new Set([
  'Money spent (Animals)', 'Money spent (Build)',
  'Money spent (Donations)', 'Money spent (Range)',
]);

export const mainHtml = `
  <div class="main-header players-main-header">
    <div class="table-meta" id="playersMeta"></div>
    <div class="players-arena-day-control is-hidden" id="playersArenaDayControl" aria-label="Arena graph day range">
      <span>Day</span><input id="playersArenaDayStart" type="text" inputmode="numeric" pattern="[0-9]*" oninput="onArenaGraphDayInput(event, 'start')" aria-label="Arena graph start day">
      <span>to Day</span><input id="playersArenaDayEnd" type="text" inputmode="numeric" pattern="[0-9]*" oninput="onArenaGraphDayInput(event, 'end')" aria-label="Arena graph end day">
    </div>
    <div class="players-arena-season-control is-hidden" id="playersArenaSeasonControl">
      <label for="playersArenaSeasonSelect">Season</label>
      <select id="playersArenaSeasonSelect" onchange="setPlayersArenaSeason(this.value)"></select>
    </div>
  </div>
  <div class="attributes-bar endgames-tabs-bar players-tabs-bar">
    <div class="attributes-bar-header endgames-tabs-header">
      <div class="endgames-tabs players-tabs" role="tablist" aria-label="Players views">
        <button class="endgames-tab active" data-view="general" onclick="setPlayersView('general')">General</button>
        <button class="endgames-tab" data-view="comparison" onclick="setPlayersView('comparison')">Comparison</button>
        <button class="endgames-tab players-arena-tab" data-view="arena_top_100" onclick="setPlayersView('arena_top_100')">
          <span>Arena Top 100</span>
          <span class="endgames-graph-toggle" id="playersArenaGraphToggle" role="button" tabindex="0" title="Show graph" aria-label="Show Arena rating graph" onclick="togglePlayersArenaGraph(event)" onkeydown="onPlayersArenaGraphKey(event)">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 19h16"/><path d="M4 5v14"/><path d="M6.5 15.5 10 11l3.5 2.5L18 7"/></svg>
          </span>
        </button>
      </div>
    </div>
  </div>
  <div id="playersContent"></div>`;

export const sidebarHtml = `
  <div class="sidebar-header"><span class="sidebar-title">Filters</span><div style="display:flex;align-items:center;gap:6px;">
    <button class="reset-btn" onclick="resetPlayersFilters()">Reset</button>
    <button class="sidebar-close-btn" onclick="toggleSidebar()" title="Close filters">x</button>
  </div></div>
  <hr class="divider" />
  <div class="filter-group"><span class="filter-label">Opponent ELO</span><div class="range-row">
    <input class="range-input" type="number" id="playersOpponentEloMin" placeholder="Min" min="0" />
    <input class="range-input" type="number" id="playersOpponentEloMax" placeholder="Max" min="0" />
  </div></div>
  <hr class="divider" />
  <div class="filter-group"><div style="display:flex;align-items:baseline;gap:6px;margin-bottom:8px;">
    <span class="filter-label" style="margin-bottom:0">Maps</span>
    <span class="map-select-all-none">(<span class="map-toggle-link" onclick="selectAllPlayersMaps()">all</span> / <span class="map-toggle-link" onclick="selectNonePlayersMaps()">none</span>)</span>
  </div><div class="chip-grid" id="playersMapChips"></div></div>
  <hr class="divider" />
  <div class="filter-group"><span class="filter-label">Date Range</span>
    <input class="date-input" type="text" id="playersDateFrom" placeholder="yyyy-mm-dd" oninput="onPlayersDateInput()" />
    <input class="date-input" type="text" id="playersDateTo" placeholder="yyyy-mm-dd" oninput="onPlayersDateInput()" />
  </div>
  <hr class="divider" />
  <div class="filter-group"><span class="filter-label">Last X games</span>
    <input class="range-input players-last-games-input" type="number" id="playersLastX" min="1" placeholder="e.g. 500" oninput="onPlayersLastInput()" />
  </div>
  <hr class="divider" />
  <div class="filter-group players-arena-filter"><div class="players-arena-season-filter" id="playersArenaSeasonFilter">
    <div class="players-arena-season-heading"><span class="filter-label">Arena Seasons</span><span class="map-select-all-none">(<span class="map-toggle-link" onclick="selectAllPlayersArenaSeasons()">all</span> / <span class="map-toggle-link" onclick="selectNonePlayersArenaSeasons()">none</span>)</span></div>
    <div class="chip-grid players-arena-season-chips" id="playersArenaSeasonChips"></div>
  </div></div>
  <div class="filter-action-stack"><button class="apply-btn" onclick="applyPlayersFilters()">Apply filters</button></div>`;

let mounted = false;
let token = 0;
let isMW = 1;
let view = 'general';
let selectedPlayer = null;
let selectedPlayers = [];
let activeSearchSlot = 0;
let playerNames = [];
let playerIndexState = 'idle';
let playerIndexError = '';
let playerIndexRequest = 0;
let selectedMaps = MAPS.map(([, full]) => full);
let rows = [];
let playerGameCount = 0;
let comparisonCounts = [];
let statsAbortController = null;
let statsLoading = false;
let arenaManifest = null;
let arenaBundle = null;
let arenaLoadState = 'loading';
let arenaLoadError = '';
let selectedArenaSeasons = [];
let selectedTop100Season = null;
let arenaGraphView = false;
let arenaGraphSelected = new Set();
let arenaGraphSearch = '';
let arenaGraphDayStart = 1;
let arenaGraphDayEnd = null;
let arenaGraphHover = null;
let arenaTableSort = { field: 'end', direction: 'desc' };
let arenaAssetRequest = 0;

export function mount({ dataset = 1 } = {}) {
  mounted = true;
  token += 1;
  isMW = Number(dataset) === 0 ? 0 : 1;
  view = 'general';
  selectedPlayer = null;
  selectedPlayers = [];
  playerNames = [];
  playerIndexState = 'idle';
  playerIndexError = '';
  playerGameCount = 0;
  comparisonCounts = [];
  selectedMaps = MAPS.map(([, full]) => full);
  rows = [];
  selectedArenaSeasons = [];
  selectedTop100Season = null;
  arenaGraphView = false;
  arenaGraphSelected = new Set();
  arenaGraphSearch = '';
  arenaGraphDayStart = 1;
  arenaGraphDayEnd = null;
  arenaGraphHover = null;
  arenaTableSort = { field: 'end', direction: 'desc' };
  Object.assign(window, {
    setPlayersView, resetPlayersFilters, applyPlayersFilters,
    selectAllPlayersMaps, selectNonePlayersMaps, togglePlayersMap,
    onPlayersDateInput, onPlayersLastInput, selectPlayer,
    onPlayersSearchInput, clearPlayersSearch, retryPlayersIndex,
    togglePlayersArenaSeason,
    selectAllPlayersArenaSeasons, selectNonePlayersArenaSeasons,
    setPlayersArenaSeason, togglePlayersArenaGraph, onPlayersArenaGraphKey,
    setPlayersArenaGraphSearch, togglePlayersArenaGraphPlayer,
    onPlayersArenaGraphMove, clearPlayersArenaGraphHover, onArenaGraphDayInput,
    selectPlayersArenaTopFive, clearPlayersArenaGraphSelection, selectPlayersArenaRandom,
    sortArenaTable,
  });
  renderMapChips();
  syncTabs();
  syncDateLastControls();
  loadPlayerIndex();
  loadArenaAssets();
  loadData(token);
}

export function unmount() {
  mounted = false;
  token += 1;
  playerIndexRequest += 1;
  statsAbortController?.abort();
  statsAbortController = null;
  hideTooltip();
  closeSuggestions();
  setTopbarDatasetLock(null);
  setFilterButtonDisabled(false);
}

export function setDataset(value) {
  isMW = Number(value) === 0 ? 0 : 1;
  if (view === 'arena_top_100') {
    syncArenaDatasetAndControls();
    renderArenaTop100();
    return;
  }
  selectedPlayer = null;
  selectedPlayers = [];
  comparisonCounts = [];
  playerGameCount = 0;
  playerNames = [];
  playerIndexState = 'idle';
  playerIndexError = '';
  ensureCompatibleArenaSelection();
  renderArenaSeasonFilter();
  loadPlayerIndex();
  loadData(++token);
}

function setPlayersView(next) {
  const previous = view;
  view = ['general', 'comparison', 'arena_top_100'].includes(next) ? next : 'general';
  closeSuggestions();
  syncTabs();
  if (view === 'arena_top_100') {
    enterArenaTop100();
    return;
  }
  if (previous === 'arena_top_100') leaveArenaTop100();
  loadData(++token);
}

function syncTabs() {
  document.querySelectorAll('.players-tabs .endgames-tab').forEach(button => {
    button.classList.toggle('active', button.dataset.view === view);
  });
  const control = document.getElementById('playersArenaSeasonControl');
  control?.classList.toggle('is-hidden', view !== 'arena_top_100');
}

function value(id) { return document.getElementById(id)?.value ?? ''; }

function params() {
  const lastInput = document.getElementById('playersLastX');
  const dateFromInput = document.getElementById('playersDateFrom');
  const dateToInput = document.getElementById('playersDateTo');
  const last = lastInput?.disabled ? '' : value('playersLastX');
  return {
    stats_page: 'players',
    players_view: view,
    is_mw: isMW,
    maps: selectedMaps,
    opponent_elo_min: value('playersOpponentEloMin') === '' ? 0 : Number(value('playersOpponentEloMin')),
    opponent_elo_max: value('playersOpponentEloMax') === '' ? null : Number(value('playersOpponentEloMax')),
    date_from: dateFromInput?.disabled ? null : (value('playersDateFrom') || null),
    date_to: dateToInput?.disabled ? null : (value('playersDateTo') || null),
    players_player: view === 'general' ? selectedPlayer : null,
    players_players: view === 'comparison' ? selectedPlayers : [],
    last_x_games: last === '' ? null : Number(last),
    players_arena_only: selectedArenaSeasons.length > 0,
    players_arena_seasons: selectedArenaSeasons.length > 0 ? [...selectedArenaSeasons] : [],
  };
}

function isDefault(request) {
  return view === 'general' && !selectedPlayer && request.last_x_games === null
    && request.opponent_elo_min === 0 && request.opponent_elo_max === null
    && request.date_from === null && request.date_to === null
    && selectedMaps.length === MAPS.length && !request.players_arena_only;
}

async function loadArenaAssets() {
  const requestId = ++arenaAssetRequest;
  arenaLoadState = 'loading';
  arenaLoadError = '';
  updatePlayersMeta();
  const manifestPromise = loadSnapshot(ARENA_MANIFEST_URL).catch(() => null);
  const bundlePromise = loadSnapshot(ARENA_BUNDLE_URL).catch(() => fetchStats({
    stats_page: 'players', players_view: 'arena_top_100', is_mw: isMW,
  }));
  try {
    const [manifestPayload, bundlePayload] = await Promise.all([manifestPromise, bundlePromise]);
    if (!mounted || requestId !== arenaAssetRequest) return;
    if (!bundlePayload || !Array.isArray(bundlePayload.seasons) || !bundlePayload.data) {
      throw new Error('Arena Top 100 bundle has an invalid response shape.');
    }
    arenaBundle = bundlePayload;
    arenaManifest = manifestPayload?.seasons ? manifestPayload : {
      seasons: bundlePayload.seasons.map(item => ({ ...item, started: true, top_100_available: true })),
      latest_by_mode: {},
      latest_top_100: bundlePayload.latest_season,
    };
    arenaLoadState = 'ready';
    arenaLoadError = '';
    selectedTop100Season ||= arenaBundle.latest_season || arenaBundle.seasons[0]?.season || null;
    renderArenaSeasonFilter();
    syncArenaSeasonSelect();
    if (view === 'arena_top_100') enterArenaTop100();
    else updatePlayersMeta();
  } catch (error) {
    if (!mounted || requestId !== arenaAssetRequest) return;
    arenaLoadState = 'error';
    arenaLoadError = error?.message || String(error);
    renderArenaSeasonFilter();
    if (view === 'arena_top_100') renderArenaTop100();
    else updatePlayersMeta();
  }
}

function startedArenaSeasons() {
  return (arenaManifest?.seasons || [])
    .filter(item => item.started !== false)
    .sort((a, b) => Number(b.number || String(b.season).slice(1)) - Number(a.number || String(a.season).slice(1)));
}

function compatibleArenaSeasons() {
  return startedArenaSeasons().filter(item => Number(item.is_mw) === Number(isMW));
}

function ensureCompatibleArenaSelection() {
  const compatible = new Set(compatibleArenaSeasons().map(item => item.season));
  selectedArenaSeasons = selectedArenaSeasons.filter(item => compatible.has(item));
}

function togglePlayersArenaSeason(season) {
  const item = startedArenaSeasons().find(candidate => candidate.season === season);
  if (!item || Number(item.is_mw) !== Number(isMW)) return;
  selectedArenaSeasons = selectedArenaSeasons.includes(season)
    ? selectedArenaSeasons.filter(value => value !== season)
    : [...selectedArenaSeasons, season];
  renderArenaSeasonFilter();
}

function selectAllPlayersArenaSeasons() {
  selectedArenaSeasons = compatibleArenaSeasons().map(item => item.season);
  renderArenaSeasonFilter();
}

function selectNonePlayersArenaSeasons() {
  selectedArenaSeasons = [];
  renderArenaSeasonFilter();
}

function renderArenaSeasonFilter() {
  const block = document.getElementById('playersArenaSeasonFilter');
  block?.classList.remove('is-hidden');
  const host = document.getElementById('playersArenaSeasonChips');
  if (!host) return;
  if (arenaLoadState === 'loading') {
    host.innerHTML = '<span class="players-arena-filter-state">Loading seasons...</span>';
    return;
  }
  if (arenaLoadState === 'error' || !arenaManifest) {
    host.innerHTML = '<span class="players-arena-filter-state">Season list unavailable</span>';
    return;
  }
  host.innerHTML = startedArenaSeasons().map(item => {
    const compatible = Number(item.is_mw) === Number(isMW);
    return `<button type="button" class="chip ${selectedArenaSeasons.includes(item.season) ? 'active' : ''} ${compatible ? '' : 'arena-season-incompatible'}" data-season="${escapeAttr(item.season)}" onclick="togglePlayersArenaSeason(this.dataset.season)" ${compatible ? '' : 'disabled'}>${escapeHtml(item.season)}</button>`;
  }).join('');
}

async function loadPlayerIndex() {
  const requestId = ++playerIndexRequest;
  const requestedDataset = isMW;
  playerIndexState = 'loading';
  playerIndexError = '';
  updatePlayersMeta();
  updatePlayerSearchState();
  try {
    let payload;
    try {
      payload = await loadSnapshot(INDEX_URL(requestedDataset));
    } catch (snapshotError) {
      payload = await fetchStats({ stats_page: 'players', players_index: true, is_mw: requestedDataset });
    }
    if (!mounted || requestId !== playerIndexRequest || requestedDataset !== isMW) return;
    if (!Array.isArray(payload?.players)) throw new Error('Player index has an invalid response shape.');
    playerNames = payload.players.filter(name => typeof name === 'string' && name.trim() !== '');
    playerIndexState = 'ready';
    playerIndexError = '';
    updatePlayersMeta();
    updatePlayerSearchState();
    renderSuggestions();
  } catch (error) {
    if (!mounted || requestId !== playerIndexRequest || requestedDataset !== isMW) return;
    playerNames = [];
    playerIndexState = 'error';
    playerIndexError = error?.message || String(error);
    updatePlayersMeta();
    updatePlayerSearchState();
    closeSuggestions();
  }
}

function retryPlayersIndex() { loadPlayerIndex(); }

async function loadData(activeToken) {
  if (view === 'arena_top_100') {
    statsAbortController?.abort();
    statsLoading = false;
    renderArenaTop100();
    return;
  }
  if (view === 'comparison' && selectedPlayers.length === 0) {
    renderLoading();
    try {
      const payload = await loadSnapshot(SNAPSHOT_URL(isMW));
      if (!mounted || activeToken !== token) return;
      rows = (payload.data || []).map(row => ({ ...row, values: [] }));
      comparisonCounts = [];
      statsLoading = false;
      renderTable();
    } catch (error) {
      if (mounted && activeToken === token) {
        statsLoading = false;
        renderError(error);
      }
    }
    return;
  }
  renderLoading();
  const request = params();
  statsAbortController?.abort();
  statsAbortController = new AbortController();
  const requestController = statsAbortController;
  try {
    const payload = await loadStats(
      request,
      isDefault(request) ? SNAPSHOT_URL(isMW) : null,
      { signal: requestController.signal },
    );
    if (!mounted || activeToken !== token) return;
    rows = Array.isArray(payload.data) ? payload.data : [];
    if (view === 'comparison') {
      comparisonCounts = Array.isArray(payload.players) ? payload.players : [];
    } else {
      playerGameCount = Number(payload.player_game_count) || 0;
    }
    statsLoading = false;
    renderTable();
  } catch (error) {
    if (error?.name === 'AbortError') return;
    if (mounted && activeToken === token) {
      statsLoading = false;
      if (rows.length) {
        document.querySelector('.players-table-wrap')?.classList.remove('players-updating');
        updatePlayersMeta(error?.message || String(error));
      } else renderError(error);
    }
  } finally {
    if (statsAbortController === requestController) statsAbortController = null;
  }
}

function renderTable() {
  if (view === 'comparison') renderComparisonTable();
  else renderGeneralTable();
}

function renderGeneralTable() {
  const host = document.getElementById('playersContent');
  if (!host) return;
  const searchDisabled = playerIndexState !== 'ready';
  const searchPlaceholder = playerIndexState === 'loading' ? 'Loading players...' : playerIndexState === 'error' ? 'Player list unavailable' : 'Search player';
  const searchAction = playerIndexState === 'error'
    ? '<button type="button" class="players-search-retry" onclick="retryPlayersIndex()" aria-label="Retry loading player list" title="Retry loading player list">&#8635;</button>'
    : '<button type="button" class="players-search-clear" onclick="clearPlayersSearch()" aria-label="Clear player">&times;</button>';
  updatePlayersMeta();
  host.innerHTML = `<div class="table-wrap players-table-wrap"><div class="table-scroll">
    <table class="maps-table players-table"><thead><tr>
      <th>Metric</th>
      <th class="players-player-header"><div class="players-search-wrap"><span class="players-search-icon" aria-hidden="true">&#128269;</span><input id="playersSearch" data-slot="0" type="search" value="${escapeAttr(selectedPlayer || '')}" placeholder="${searchPlaceholder}" oninput="onPlayersSearchInput(event)" autocomplete="off" ${searchDisabled ? 'disabled' : ''}/>${searchAction}</div></th>
      <th>All</th><th>Winners</th><th>Experts</th><th>Masters</th>
    </tr></thead><tbody>${rows.map(row => playerRow(row, selectedPlayer ? 5 : 4)).join('')}</tbody></table>
  </div></div><div id="playersSuggestions" class="players-suggestions" role="listbox" aria-label="Matching players"></div>`;
  renderSuggestions();
}

function renderComparisonTable() {
  const host = document.getElementById('playersContent');
  if (!host) return;
  const searchDisabled = playerIndexState !== 'ready';
  const searchPlaceholder = playerIndexState === 'loading' ? 'Loading players...' : playerIndexState === 'error' ? 'Player list unavailable' : 'Search player';
  updatePlayersMeta();
  const headers = Array.from({ length: 5 }, (_, slot) => {
    const name = selectedPlayers[slot] || '';
    const action = playerIndexState === 'error'
      ? '<button type="button" class="players-search-retry" onclick="retryPlayersIndex()" aria-label="Retry loading player list" title="Retry loading player list">&#8635;</button>'
      : name ? `<button type="button" class="players-search-clear" data-slot="${slot}" onclick="clearPlayersSearch(event)" aria-label="Clear player">&times;</button>` : '';
    return `<th class="players-player-header"><div class="players-search-wrap"><span class="players-search-icon" aria-hidden="true">&#128269;</span><input id="playersSearch${slot}" data-slot="${slot}" type="search" value="${escapeAttr(name)}" placeholder="${searchPlaceholder}" oninput="onPlayersSearchInput(event)" autocomplete="off" ${searchDisabled ? 'disabled' : ''}/>${action}</div></th>`;
  }).join('');
  host.innerHTML = `<div class="table-wrap players-table-wrap"><div class="table-scroll">
    <table class="maps-table players-table"><thead><tr><th>Metric</th>${headers}</tr></thead>
    <tbody>${rows.map(row => comparisonRow(row)).join('')}</tbody></table>
  </div></div><div id="playersSuggestions" class="players-suggestions" role="listbox" aria-label="Matching players"></div>`;
  renderSuggestions();
}

function playerRow(row, columnsWithPlayer) {
  const range = rowRange(row, POPULATIONS);
  return `<tr><td class="maps-metric-cell">${escapeHtml(displayMetricName(row.metric))}${row.tooltip ? ` <span class="col-tip" data-tip="${escapeAttr(row.tooltip)}">?</span>` : ''}</td>${POPULATIONS.map(key => playerValueCell(row, key, range)).join('')}</tr>`;
}

function comparisonRow(row) {
  const values = selectedPlayers.map(name => row.values?.find(item => item.player === name)?.value);
  const range = selectedPlayers.length >= 2 ? rangeForValues(values) : { min: null, max: null };
  const cells = Array.from({ length: 5 }, (_, index) => {
    const name = selectedPlayers[index];
    const item = name ? row.values?.find(value => value.player === name) : null;
    return comparisonValueCell(row, item, range, selectedPlayers.length >= 2);
  }).join('');
  return `<tr><td class="maps-metric-cell">${escapeHtml(displayMetricName(row.metric))}${row.tooltip ? ` <span class="col-tip" data-tip="${escapeAttr(row.tooltip)}">?</span>` : ''}</td>${cells}</tr>`;
}

function playerValueCell(row, key, range) {
  const value = key === 'player' && !selectedPlayer ? Number.NaN : finiteNumber(row[key]);
  const tooltip = SPENDING_METRICS.has(row.metric) ? finiteNumber(row[`tooltip_${key}`]) : Number.NaN;
  return valueCell(value, row, range, tooltip);
}

function comparisonValueCell(row, item, range, colorEnabled) {
  const value = item ? finiteNumber(item.value) : Number.NaN;
  const tooltip = item && SPENDING_METRICS.has(row.metric) ? finiteNumber(item.tooltip_value) : Number.NaN;
  return valueCell(value, row, colorEnabled ? range : { min: null, max: null }, tooltip);
}

function valueCell(value, row, range, tooltipValue) {
  const style = Number.isFinite(value) && range.min !== null ? ` style="color:${divergingRangeColor(value, range.min, range.max, row.lower_is_better === true)}"` : '';
  const tip = Number.isFinite(tooltipValue) ? ` data-tip="${escapeAttr(formatValue(tooltipValue, 'number'))}"` : '';
  return `<td class="players-value-cell"${style}${tip}>${formatValue(value, row.format)}</td>`;
}

function rowRange(row, keys) { return rangeForValues(keys.map(key => row[key])); }
function rangeForValues(values) {
  const finite = values.map(finiteNumber).filter(Number.isFinite);
  return finite.length ? { min: Math.min(...finite), max: Math.max(...finite) } : { min: null, max: null };
}

function renderMapChips() {
  const host = document.getElementById('playersMapChips');
  if (host) host.innerHTML = MAPS.map(([short, full]) => `<button class="chip ${selectedMaps.includes(full) ? 'active' : ''}" data-map="${escapeAttr(full)}" onclick="togglePlayersMap(this.dataset.map)">${short}</button>`).join('');
}

function togglePlayersMap(map) { selectedMaps = selectedMaps.includes(map) ? selectedMaps.filter(item => item !== map) : [...selectedMaps, map]; renderMapChips(); }
function selectAllPlayersMaps() { selectedMaps = MAPS.map(([, full]) => full); renderMapChips(); }
function selectNonePlayersMaps() { selectedMaps = []; renderMapChips(); }

function resetPlayersFilters() {
  const set = (id, next) => { const el = document.getElementById(id); if (el) el.value = next; };
  set('playersOpponentEloMin', ''); set('playersOpponentEloMax', '');
  set('playersDateFrom', ''); set('playersDateTo', ''); set('playersLastX', '');
  selectedArenaSeasons = [];
  selectedMaps = MAPS.map(([, full]) => full);
  renderMapChips(); renderArenaSeasonFilter(); syncDateLastControls(); loadData(++token);
}

function applyPlayersFilters() {
  loadData(++token);
  document.getElementById('sidebar')?.classList.remove('open');
  document.getElementById('sidebarOverlay')?.classList.remove('active');
}

function onPlayersDateInput() { syncDateLastControls(); }
function onPlayersLastInput() { syncDateLastControls(); }
function syncDateLastControls() {
  const dateActive = value('playersDateFrom').trim() !== '' || value('playersDateTo').trim() !== '';
  const lastActive = value('playersLastX') !== '';
  const from = document.getElementById('playersDateFrom');
  const to = document.getElementById('playersDateTo');
  const last = document.getElementById('playersLastX');
  if (lastActive) {
    if (from) from.disabled = true;
    if (to) to.disabled = true;
    if (last) last.disabled = false;
  } else if (dateActive) {
    if (from) from.disabled = false;
    if (to) to.disabled = false;
    if (last) last.disabled = true;
  } else {
    if (from) from.disabled = false;
    if (to) to.disabled = false;
    if (last) last.disabled = false;
  }
}

function onPlayersSearchInput(event) {
  const slot = Number(event.target.dataset.slot || 0);
  activeSearchSlot = Number.isFinite(slot) ? slot : 0;
  if (view === 'general' && selectedPlayer) selectedPlayer = null;
  if (view === 'comparison' && selectedPlayers[slot]) selectedPlayers = selectedPlayers.filter((_, index) => index !== slot);
  updatePlayersMeta();
  renderSuggestions(event.target.value);
}

function renderSuggestions(term = value(view === 'general' ? 'playersSearch' : `playersSearch${activeSearchSlot}`)) {
  const host = document.getElementById('playersSuggestions');
  if (!host) return;
  const normalized = String(term || '').trim().toLocaleLowerCase();
  if (playerIndexState !== 'ready' || normalized.length < 3) { closeSuggestions(); return; }
  // General and Comparison keep independent selections. Duplicate prevention
  // applies only among the five Comparison columns.
  const excluded = new Set(view === 'comparison' ? selectedPlayers.filter(Boolean) : []);
  const matches = playerNames.filter(name => !excluded.has(name) && name.toLocaleLowerCase().includes(normalized)).slice(0, 50);
  host.innerHTML = matches.map(name => `<button type="button" role="option" data-player="${escapeAttr(name)}">${escapeHtml(name)}</button>`).join('');
  host.classList.toggle('open', matches.length > 0);
  if (matches.length > 0) requestAnimationFrame(positionSuggestions);
}

function positionSuggestions() {
  const host = document.getElementById('playersSuggestions');
  const input = document.querySelector(`.players-search-wrap input[data-slot="${activeSearchSlot}"]`) || document.getElementById('playersSearch');
  if (!host?.classList.contains('open') || !input) return;
  const rect = input.getBoundingClientRect();
  const width = Math.min(Math.max(180, rect.width), window.innerWidth - 16);
  const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
  host.style.left = `${left}px`; host.style.width = `${width}px`; host.style.top = `${rect.bottom + 4}px`;
  const listRect = host.getBoundingClientRect();
  if (listRect.bottom > window.innerHeight - 8 && rect.top > listRect.height + 12) host.style.top = `${rect.top - listRect.height - 4}px`;
}

function closeSuggestions() {
  const host = document.getElementById('playersSuggestions');
  if (!host) return;
  host.innerHTML = ''; host.classList.remove('open');
}

function selectPlayer(name, slot = activeSearchSlot) {
  const exact = String(name);
  if (!playerNames.includes(exact)) return;
  if (view === 'general') {
    selectedPlayer = exact;
  } else if (view === 'comparison' && !selectedPlayers.includes(exact)) {
    const next = selectedPlayers.filter(Boolean);
    next.push(exact);
    selectedPlayers = next.slice(0, 5);
  }
  closeSuggestions();
  loadData(++token);
}

function clearPlayersSearch(event) {
  const slot = Number(event?.currentTarget?.dataset?.slot || 0);
  if (view === 'general') selectedPlayer = null;
  else selectedPlayers = selectedPlayers.filter((_, index) => index !== slot);
  closeSuggestions();
  loadData(++token);
}

function updatePlayersMeta(errorMessage = '') {
  const meta = document.getElementById('playersMeta');
  if (!meta) return;
  if (errorMessage) meta.textContent = `Could not update player statistics: ${errorMessage}`;
  else if (view === 'arena_top_100') {
    if (arenaLoadState === 'loading') meta.textContent = 'Loading static Arena season statistics...';
    else if (arenaLoadState === 'error') meta.textContent = `Could not load Arena Top 100${arenaLoadError ? `: ${arenaLoadError}` : ''}`;
    else meta.textContent = '';
  }
  else if (statsLoading) meta.textContent = 'Updating player statistics...';
  else if (playerIndexState === 'loading') meta.textContent = 'Loading player list...';
  else if (playerIndexState === 'error') meta.textContent = `Could not load player list${playerIndexError ? `: ${playerIndexError}` : ''}. Use the retry button in the Player header.`;
  else if (view === 'comparison') meta.textContent = selectedPlayers.length ? `Number of games considered: ${comparisonCounts.map(item => `${item.name} (${item.game_count})`).join(', ')}` : 'Select players to compare.';
  else meta.textContent = selectedPlayer ? `Number of games considered: ${playerGameCount}` : 'Select a player to populate the Player column.';
}

function updatePlayerSearchState() {
  if (rows.length > 0 && document.querySelector('.players-table')) renderTable();
}

function displayMetricName(metric) {
  return String(metric)
    .replaceAll('Money per turn', '$ gained per turn')
    .replaceAll('Points per money', 'Points per $')
    .replaceAll('Money gained', '$ gained')
    .replaceAll('Money spent', '$ spent')
    .replaceAll('Cards drawn from deck', 'Cards drawn (deck)')
    .replaceAll('Cards drawn from range', 'Cards drawn (Range)');
}

function finiteNumber(raw) {
  if (raw === null || raw === undefined || raw === '') return Number.NaN;
  const value = Number(raw);
  return Number.isFinite(value) ? value : Number.NaN;
}

function formatValue(raw, format) {
  const value = finiteNumber(raw);
  if (!Number.isFinite(value)) return '-';
  if (format === 'percent') return `${value.toFixed(1)}%`;
  if (format === 'compact') return value.toLocaleString('en-US');
  return value.toFixed(2);
}

function availableTop100Seasons() {
  return (arenaBundle?.seasons || []).slice().sort((a, b) => Number(b.number) - Number(a.number));
}

function currentArenaSeasonData() {
  return selectedTop100Season ? arenaBundle?.data?.[selectedTop100Season] || null : null;
}

function syncArenaSeasonSelect() {
  const select = document.getElementById('playersArenaSeasonSelect');
  if (!select) return;
  const seasons = availableTop100Seasons();
  if (!selectedTop100Season || !seasons.some(item => item.season === selectedTop100Season)) {
    selectedTop100Season = arenaBundle?.latest_season || seasons[0]?.season || null;
  }
  select.innerHTML = seasons.map(item => `<option value="${escapeAttr(item.season)}" ${item.season === selectedTop100Season ? 'selected' : ''}>${escapeHtml(item.season)}</option>`).join('');
  select.disabled = seasons.length === 0;
}

function syncArenaDatasetAndControls() {
  const metadata = availableTop100Seasons().find(item => item.season === selectedTop100Season);
  if (!metadata) return;
  const required = Number(metadata.is_mw);
  setTopbarDatasetLock(required);
  if (required !== Number(isMW)) {
    window.dispatchEvent(new CustomEvent('arknova:set-dataset', { detail: { value: required } }));
  }
}

function resetArenaGraphSelection() {
  const data = currentArenaSeasonData();
  arenaGraphSelected = new Set((data?.series || [])
    .filter(item => Number(item.rank) <= 5 && (item.ratings || []).length > 0)
    .map(item => item.player));
}

function enterArenaTop100() {
  setFilterButtonDisabled(true);
  const control = document.getElementById('playersArenaSeasonControl');
  control?.classList.remove('is-hidden');
  syncArenaSeasonSelect();
  syncArenaDatasetAndControls();
  if (arenaGraphSelected.size === 0) resetArenaGraphSelection();
  syncPlayersArenaDayControl();
  renderArenaTop100();
}

function leaveArenaTop100() {
  setFilterButtonDisabled(false);
  setTopbarDatasetLock(null);
  document.getElementById('playersArenaSeasonControl')?.classList.add('is-hidden');
  document.getElementById('playersArenaDayControl')?.classList.add('is-hidden');
}

function syncPlayersArenaDayControl() {
  const control = document.getElementById('playersArenaDayControl');
  const data = currentArenaSeasonData();
  if (!control || !data) return;
  syncArenaGraphDayRange(data);
  control.classList.toggle('is-hidden', view !== 'arena_top_100' || !arenaGraphView);
  const start = document.getElementById('playersArenaDayStart');
  const end = document.getElementById('playersArenaDayEnd');
  if (start) start.value = arenaGraphDayStart;
  if (end) end.value = arenaGraphDayEnd;
}

function setPlayersArenaSeason(season) {
  if (!availableTop100Seasons().some(item => item.season === season)) return;
  selectedTop100Season = season;
  arenaGraphSearch = '';
  arenaGraphDayStart = 1;
  arenaGraphDayEnd = null;
  arenaGraphHover = null;
  arenaTableSort = { field: 'end', direction: 'desc' };
  resetArenaGraphSelection();
  syncArenaSeasonSelect();
  syncArenaDatasetAndControls();
  renderArenaTop100();
}

function togglePlayersArenaGraph(event) {
  event?.preventDefault?.();
  event?.stopPropagation?.();
  if (view !== 'arena_top_100') return;
  arenaGraphView = !arenaGraphView;
  if (arenaGraphView && arenaGraphSelected.size === 0) resetArenaGraphSelection();
  syncPlayersArenaDayControl();
  renderArenaTop100();
}

function onPlayersArenaGraphKey(event) {
  if (event.key !== 'Enter' && event.key !== ' ') return;
  togglePlayersArenaGraph(event);
}

function setPlayersArenaGraphSearch(value) {
  arenaGraphSearch = String(value || '');
  renderArenaGraphLegend();
}

function togglePlayersArenaGraphPlayer(player) {
  const series = currentArenaSeasonData()?.series?.find(item => item.player === player);
  if (!series || !(series.ratings || []).length) return;
  if (arenaGraphSelected.has(player)) arenaGraphSelected.delete(player);
  else {
    if (arenaGraphSelected.size >= 5) {
      document.getElementById('arenaGraphLimit')?.classList.add('limit-pulse');
      window.setTimeout(() => document.getElementById('arenaGraphLimit')?.classList.remove('limit-pulse'), 700);
      return;
    }
    arenaGraphSelected.add(player);
  }
  renderArenaGraphCanvas();
  renderArenaGraphLegend();
}

function selectPlayersArenaTopFive() {
  resetArenaGraphSelection();
  renderArenaGraphCanvas();
  renderArenaGraphLegend();
}

function clearPlayersArenaGraphSelection() {
  arenaGraphSelected.clear();
  renderArenaGraphCanvas();
  renderArenaGraphLegend();
}

function selectPlayersArenaRandom() {
  const eligible = (currentArenaSeasonData()?.series || []).filter(item => (item.ratings || []).length > 0);
  for (let index = eligible.length - 1; index > 0; index -= 1) {
    const swap = Math.floor(Math.random() * (index + 1));
    [eligible[index], eligible[swap]] = [eligible[swap], eligible[index]];
  }
  arenaGraphSelected = new Set(eligible.slice(0, 5).map(item => item.player));
  arenaGraphHover = null;
  renderArenaGraphCanvas();
  renderArenaGraphLegend();
}

function renderArenaTop100() {
  if (view !== 'arena_top_100') return;
  const host = document.getElementById('playersContent');
  if (!host) return;
  syncArenaSeasonSelect();
  syncPlayersArenaDayControl();
  const toggle = document.getElementById('playersArenaGraphToggle');
  toggle?.classList.toggle('active', arenaGraphView);
  if (toggle) {
    toggle.title = arenaGraphView ? 'Show table' : 'Show graph';
    toggle.setAttribute('aria-label', arenaGraphView ? 'Show Arena Top 100 table' : 'Show Arena rating graph');
  }
  updatePlayersMeta();
  if (arenaLoadState === 'loading') {
    host.innerHTML = '<div class="state-overlay"><div class="spinner"></div><div class="state-title">Loading Arena Top 100...</div></div>';
    return;
  }
  if (arenaLoadState === 'error' || !arenaBundle) {
    host.innerHTML = `<div class="state-overlay"><div class="state-title">Could not load Arena Top 100</div><div class="state-sub">${escapeHtml(arenaLoadError || 'Static bundle unavailable')}</div><button type="button" class="reset-btn" onclick="location.reload()">Retry</button></div>`;
    return;
  }
  const data = currentArenaSeasonData();
  if (!data) {
    host.innerHTML = '<div class="state-overlay"><div class="state-title">No ranking snapshot is available for this season.</div></div>';
    return;
  }
  if (arenaGraphView) renderArenaGraph(host, data);
  else renderArenaTable(host, data);
}

function wholeOrDash(raw) {
  const value = finiteNumber(raw);
  return Number.isFinite(value) ? Math.round(value).toLocaleString('en-US') : '-';
}

function twoOrDash(raw, suffix = '') {
  const value = finiteNumber(raw);
  return Number.isFinite(value) ? `${value.toFixed(2)}${suffix}` : '-';
}

function renderArenaTable(host, data) {
  const sortedRows = [...(data.rows || [])].sort(compareArenaTableRows);
  const sortArrow = field => arenaTableSort.field === field ? (arenaTableSort.direction === 'asc' ? '↑' : '↓') : '↕';
  const sortHeader = (field, label, tip = '') => `<th class="sortable ${arenaTableSort.field === field ? 'sorted' : ''}" onclick="sortArenaTable('${field}')">${label}${tip ? ` <span class="col-tip" data-tip="${escapeAttr(tip)}">?</span>` : ''}<span class="sort-arrow">${sortArrow(field)}</span></th>`;
  host.innerHTML = `<div class="table-wrap players-arena-table-wrap"><div class="table-scroll"><table class="players-arena-table">
    <colgroup><col style="width:5%"><col style="width:20%">${'<col style="width:9.375%">'.repeat(8)}</colgroup>
    <thead><tr><th>#</th><th>Player</th>${sortHeader('end', 'End')}${sortHeader('peak', 'Peak')}${sortHeader('games', 'Games')}${sortHeader('winrate', 'Winrate')}${sortHeader('opponent_elo', 'Opp. Elo')}${sortHeader('pr', 'PR', 'performance rating')}${sortHeader('turns', 'Turns')}${sortHeader('ppt', 'PPT', 'points per turn')}</tr></thead>
    <tbody>${sortedRows.map(row => `<tr><td class="rank-cell">${wholeOrDash(row.rank)}</td><td class="players-arena-name">${escapeHtml(row.player)}</td><td>${wholeOrDash(row.end)}</td><td>${wholeOrDash(row.peak)}</td><td>${wholeOrDash(row.games)}</td><td>${twoOrDash(row.winrate, '%')}</td><td>${wholeOrDash(row.opponent_elo)}</td><td>${wholeOrDash(row.pr)}</td><td>${twoOrDash(row.turns)}</td><td>${twoOrDash(row.ppt)}</td></tr>`).join('')}</tbody>
  </table></div></div>`;
}

const ARENA_TABLE_SORT_FIELDS = ['end', 'peak', 'games', 'winrate', 'opponent_elo', 'pr', 'turns', 'ppt'];

function compareArenaTableRows(a, b) {
  const av = finiteNumber(a[arenaTableSort.field]);
  const bv = finiteNumber(b[arenaTableSort.field]);
  if (!Number.isFinite(av) && Number.isFinite(bv)) return 1;
  if (Number.isFinite(av) && !Number.isFinite(bv)) return -1;
  let comparison = Number.isFinite(av) && Number.isFinite(bv) ? av - bv : 0;
  if (comparison === 0) comparison = finiteNumber(a.rank) - finiteNumber(b.rank);
  return arenaTableSort.direction === 'asc' ? comparison : -comparison;
}

function sortArenaTable(field) {
  if (!ARENA_TABLE_SORT_FIELDS.includes(field)) return;
  arenaTableSort = arenaTableSort.field === field
    ? { field, direction: arenaTableSort.direction === 'desc' ? 'asc' : 'desc' }
    : { field, direction: 'desc' };
  renderArenaTop100();
}

function renderArenaGraph(host, data) {
  syncArenaGraphDayRange(data);
  host.innerHTML = `<div class="players-arena-graph-shell">
    <div class="players-arena-chart" id="playersArenaChart">
      <div class="players-arena-graph-tooltip" id="playersArenaGraphTooltip" role="status" aria-live="polite"></div>
    </div>
    <aside class="players-arena-legend">
      <input type="search" value="${escapeAttr(arenaGraphSearch)}" placeholder="Search players" oninput="setPlayersArenaGraphSearch(this.value)" aria-label="Search Arena players">
      <div class="players-arena-legend-actions"><button type="button" onclick="selectPlayersArenaTopFive()">Top 5</button><button type="button" onclick="clearPlayersArenaGraphSelection()">None</button><button type="button" onclick="selectPlayersArenaRandom()">Random</button></div>
      <div class="players-arena-limit" id="arenaGraphLimit">Maximum 5 players</div>
      <div class="players-arena-legend-list" id="playersArenaLegendList"></div>
    </aside>
  </div>`;
  renderArenaGraphCanvas();
  renderArenaGraphLegend();
}

function renderArenaGraphCanvas() {
  const host = document.getElementById('playersArenaChart');
  const data = currentArenaSeasonData();
  if (!host || !data) return;
  syncArenaGraphDayRange(data);
  const selected = (data.series || []).filter(item => arenaGraphSelected.has(item.player) && (item.ratings || []).length);
  const width = 900; const height = 470;
  const margin = { left: 62, right: 24, top: 25, bottom: 34 };
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  const seasonStart = Date.parse(data.start_utc); const seasonEnd = Date.parse(data.end_utc);
  const dayMs = 24 * 60 * 60 * 1000;
  const start = seasonStart + (arenaGraphDayStart - 1) * dayMs;
  const end = Math.min(seasonEnd, seasonStart + arenaGraphDayEnd * dayMs);
  const pointsFor = item => (item.timestamps || []).map((timestamp, index) => ({
    time: Date.parse(timestamp), rating: Number(item.ratings?.[index]),
  })).filter(point => Number.isFinite(point.time) && Number.isFinite(point.rating) && point.time >= start && point.time <= end);
  const selectedPoints = selected.map(item => ({ item, points: pointsFor(item) }));
  const ratings = selectedPoints.flatMap(entry => entry.points.map(point => point.rating));
  let yMin = ratings.length ? Math.min(...ratings) : 0;
  let yMax = ratings.length ? Math.max(...ratings) : 100;
  const padding = Math.max(20, (yMax - yMin) * 0.08);
  yMin = Math.floor((yMin - padding) / 50) * 50;
  yMax = Math.ceil((yMax + padding) / 50) * 50;
  if (yMax <= yMin) yMax = yMin + 100;
  const x = time => margin.left + ((time - start) / Math.max(1, end - start)) * innerWidth;
  const y = rating => margin.top + (1 - (rating - yMin) / (yMax - yMin)) * innerHeight;
  const yTicks = Array.from({ length: 6 }, (_, index) => yMin + ((yMax - yMin) * index / 5));
  const xTicks = Array.from({ length: 5 }, (_, index) => start + ((end - start) * index / 4));
  const grid = yTicks.map(value => `<g><line x1="${margin.left}" y1="${y(value)}" x2="${width - margin.right}" y2="${y(value)}"/><text x="${margin.left - 10}" y="${y(value) + 4}" text-anchor="end">${Math.round(value)}</text></g>`).join('');
  const dates = xTicks.map(value => `<g><line x1="${x(value)}" y1="${margin.top}" x2="${x(value)}" y2="${height - margin.bottom}"/><text x="${x(value)}" y="${height - 18}" text-anchor="middle">${new Date(value).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })}</text></g>`).join('');
  const lines = selectedPoints.map(({ item, points }, index) => {
    const path = points.map((point, pointIndex) => `${pointIndex ? 'L' : 'M'} ${x(point.time).toFixed(2)} ${y(point.rating).toFixed(2)}`).join(' ');
    const color = ARENA_LINE_COLORS[index % ARENA_LINE_COLORS.length];
    return path ? `<path class="players-arena-rating-line" d="${path}" stroke="${color}" data-player="${escapeAttr(item.player)}"></path>` : '';
  }).join('');
  host.querySelector('svg')?.remove();
  host.querySelector('.players-arena-empty-chart')?.remove();
  host.insertAdjacentHTML('afterbegin', `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Arena rating progression for selected players" onmousemove="onPlayersArenaGraphMove(event)" onmouseleave="clearPlayersArenaGraphHover()"><g class="players-arena-grid">${grid}${dates}</g><line class="players-arena-axis" x1="${margin.left}" y1="${height - margin.bottom}" x2="${width - margin.right}" y2="${height - margin.bottom}"/><line class="players-arena-axis" x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${height - margin.bottom}"/>${lines}<text class="players-arena-axis-title" transform="translate(15 ${height / 2}) rotate(-90)" text-anchor="middle">Arena rating</text></svg>${selected.length ? '' : '<div class="players-arena-empty-chart">Select up to five players from the legend.</div>'}`);
  const tooltip = document.getElementById('playersArenaGraphTooltip');
  if (tooltip) {
    if (!arenaGraphHover) tooltip.classList.remove('visible');
    else {
      tooltip.textContent = wholeOrDash(arenaGraphHover.rating);
      tooltip.classList.add('visible');
      const chartRect = host.getBoundingClientRect();
      const left = arenaGraphHover.clientX - chartRect.left - (tooltip.offsetWidth / 2);
      const top = arenaGraphHover.clientY - chartRect.top - tooltip.offsetHeight - 8;
      tooltip.style.left = `${Math.max(8, Math.min(chartRect.width - tooltip.offsetWidth - 8, left))}px`;
      tooltip.style.top = `${Math.max(4, top)}px`;
    }
  }
}

function arenaSeasonDayCount(data) {
  const start = Date.parse(data?.start_utc); const end = Date.parse(data?.end_utc);
  return Number.isFinite(start) && Number.isFinite(end) ? Math.max(1, Math.ceil((end - start) / (24 * 60 * 60 * 1000))) : 1;
}

function syncArenaGraphDayRange(data) {
  const maxDay = arenaSeasonDayCount(data);
  if (!Number.isFinite(arenaGraphDayEnd) || arenaGraphDayEnd === null) arenaGraphDayEnd = maxDay;
  if (arenaGraphDayStart < 1 || arenaGraphDayStart >= maxDay) arenaGraphDayStart = 1;
  if (arenaGraphDayEnd > maxDay || arenaGraphDayEnd <= arenaGraphDayStart) arenaGraphDayEnd = maxDay;
}

function onArenaGraphDayInput(event, side) {
  const data = currentArenaSeasonData();
  if (!data) return;
  const input = event.target;
  input.value = String(input.value || '').replace(/\D/g, '');
  const maxDay = arenaSeasonDayCount(data);
  const parsed = Number(input.value);
  if (side === 'start') arenaGraphDayStart = Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
  else arenaGraphDayEnd = Number.isFinite(parsed) && parsed > 0 ? parsed : maxDay;
  syncArenaGraphDayRange(data);
  document.getElementById('playersArenaDayStart').value = arenaGraphDayStart;
  document.getElementById('playersArenaDayEnd').value = arenaGraphDayEnd;
  arenaGraphHover = null;
  renderArenaGraphCanvas();
}

function nearestArenaPoint(item, targetTime) {
  let best = null;
  (item.timestamps || []).forEach((timestamp, index) => {
    const time = Date.parse(timestamp); const rating = Number(item.ratings?.[index]);
    if (!Number.isFinite(time) || !Number.isFinite(rating)) return;
    if (!best || Math.abs(time - targetTime) < Math.abs(best.time - targetTime)) best = { time, rating };
  });
  return best;
}

function onPlayersArenaGraphMove(event) {
  const data = currentArenaSeasonData();
  const svg = event.currentTarget;
  if (!data || !svg) return;
  const rect = svg.getBoundingClientRect();
  const fraction = Math.max(0, Math.min(1, (event.clientX - rect.left) / Math.max(1, rect.width)));
  const maxDay = arenaSeasonDayCount(data); const dayMs = 24 * 60 * 60 * 1000;
  const start = Date.parse(data.start_utc) + (arenaGraphDayStart - 1) * dayMs;
  const end = Math.min(Date.parse(data.end_utc), Date.parse(data.start_utc) + arenaGraphDayEnd * dayMs);
  const targetTime = start + fraction * Math.max(1, end - start);
  const selected = (data.series || []).filter(item => arenaGraphSelected.has(item.player) && (item.ratings || []).length);
  const line = event.target?.closest?.('.players-arena-rating-line');
  if (!line) {
    clearPlayersArenaGraphHover();
    return;
  }
  const item = selected.find(candidate => candidate.player === line.dataset.player);
  const point = item ? nearestArenaPoint(item, targetTime) : null;
  if (!point) return;
  arenaGraphHover = {
    time: point.time,
    rating: point.rating,
    clientX: event.clientX,
    clientY: event.clientY,
  };
  renderArenaGraphCanvas();
}

function clearPlayersArenaGraphHover() {
  if (!arenaGraphHover) return;
  arenaGraphHover = null;
  renderArenaGraphCanvas();
}

function renderArenaGraphLegend() {
  const host = document.getElementById('playersArenaLegendList');
  const data = currentArenaSeasonData();
  if (!host || !data) return;
  const term = arenaGraphSearch.trim().toLocaleLowerCase();
  const selectedOrder = (data.series || []).filter(item => arenaGraphSelected.has(item.player)).map(item => item.player);
  host.innerHTML = (data.series || []).filter(item => !term || item.player.toLocaleLowerCase().includes(term)).map(item => {
    const selected = arenaGraphSelected.has(item.player);
    const disabled = !(item.ratings || []).length;
    const colorIndex = selectedOrder.indexOf(item.player);
    const color = colorIndex >= 0 ? ARENA_LINE_COLORS[colorIndex % ARENA_LINE_COLORS.length] : 'transparent';
    return `<button type="button" class="players-arena-legend-item ${selected ? 'active' : ''}" data-player="${escapeAttr(item.player)}" onclick="togglePlayersArenaGraphPlayer(this.dataset.player)" ${disabled ? 'disabled' : ''}><span class="players-arena-legend-swatch" style="background:${color}"></span><span class="players-arena-legend-rank">${item.rank}</span><span>${escapeHtml(item.player)}</span></button>`;
  }).join('');
}

function renderLoading() {
  statsLoading = true;
  const existing = document.querySelector('.players-table-wrap');
  if (existing && rows.length) {
    existing.classList.add('players-updating');
    updatePlayersMeta();
    return;
  }
  document.getElementById('playersContent').innerHTML = '<div class="state-overlay"><div class="spinner"></div><div class="state-title">Fetching player statistics...</div></div>';
}
function renderError(error) { document.getElementById('playersContent').innerHTML = `<div class="state-overlay"><div class="state-title">Could not load player statistics</div><div class="state-sub">${escapeHtml(error.message || error)}</div></div>`; }
function escapeHtml(value) { return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;'); }
const escapeAttr = escapeHtml;
const tooltip = document.getElementById('col-tooltip');
function hideTooltip() { if (tooltip) tooltip.style.display = 'none'; }
document.addEventListener('mouseover', event => { if (!mounted || !tooltip) return; const source = event.target.closest?.('.players-value-cell, .col-tip'); if (!source || !source.dataset.tip) return; tooltip.textContent = source.dataset.tip; tooltip.style.display = 'block'; tooltip.style.left = `${Math.max(8, Math.min(event.clientX + 12, window.innerWidth - tooltip.offsetWidth - 8))}px`; tooltip.style.top = `${event.clientY + 18}px`; });
document.addEventListener('mouseout', event => { if (mounted && tooltip && event.target.closest?.('.players-value-cell, .col-tip')) tooltip.style.display = 'none'; });
document.addEventListener('click', event => {
  if (!mounted) return;
  const option = event.target.closest?.('.players-suggestions button[data-player]');
  if (option) { selectPlayer(option.dataset.player, activeSearchSlot); return; }
  if (!event.target.closest?.('.players-search-wrap, .players-suggestions')) closeSuggestions();
});
document.addEventListener('scroll', () => { if (mounted) positionSuggestions(); }, true);
window.addEventListener('resize', () => { if (mounted) positionSuggestions(); });
