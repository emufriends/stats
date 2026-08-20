import { deltaRangeColor, divergingRangeColor } from '../color-scales.js?v=20260711-2';
import { formatSignedDeltaAdaptive, mapTooltipLabel } from '../table-cells.js?v=20260712-5';
import { fetchStats, loadSnapshot, loadStats } from '../snapshot-cache.js?v=20260819-3';
import { setFilterButtonDisabled } from '../layout.js?v=20260801-2';

export const id = 'players';
export const title = 'Players';
export const navLabel = 'Players';

const API_ROOT = 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/players';
const API_URL = 'https://europe-west1-ark-nova-stats-dashboard.cloudfunctions.net/get-card-stats';
const INDEX_URL = dataset => `${API_ROOT}/index/default-${dataset ? 'mw' : 'base'}.json`;
const SNAPSHOT_URL = dataset => `${API_ROOT}/general/default-${dataset ? 'mw' : 'base'}.json`;
const ARENA_MANIFEST_URL = `${API_ROOT}/arena/manifest.json`;
// General metric colors are assigned by the metric's fixed position inside its
// compatibility group. The longest group contains all 16 icon metrics, so a
// 16-color palette prevents colors from changing or repeating as lines are
// selected and deselected.
const HISTORY_LINE_COLORS = [
  '#42d392', '#60a5fa', '#f59e0b', '#c084fc',
  '#fb7185', '#22d3ee', '#f97316', '#a3e635',
  '#e879f9', '#facc15', '#38bdf8', '#fb923c',
  '#a78bfa', '#2dd4bf', '#f43f5e', '#84cc16',
];
// Comparison uses the history palette for player lines. Keep the selected
// metric marker outside that palette so it can never imply that the metric
// belongs to one particular player.
const HISTORY_COMPARISON_METRIC_COLOR = '#d9f99d';
const PLAYER_GRAPH_MIN_GAMES = 250;
// The aggregate table intentionally keeps its compact display shape. This map
// connects those existing labels to the prepared-table keys used by history.
const HISTORY_METRIC_KEYS = new Map([
  ['Turns', 'turns'], ['Breaks triggered', 'breaks_triggered'], ['Break%', 'break_pct'],
  ['Points per turn', 'points_per_turn'], ['Points per money', 'points_per_money'],
  ['$ gained per turn', 'money_per_turn'], ['Money per turn', 'money_per_turn'],
  ['Score', 'score'], ['Appeal', 'appeal'], ['Conservation', 'conservation'],
  ['Reputation', 'reputation'], ['Projects', 'projects'], ['Upgrades', 'upgrades'],
  ['Workers', 'workers'], ['Cover%', 'cover_pct'], ['Fill%', 'fill_pct'],
  ['Animals%', 'animals_pct'], ['Association%', 'association_pct'], ['Build%', 'build_pct'],
  ['Cards%', 'cards_pct'], ['Sponsors%', 'sponsors_pct'], ['Determinations', 'determinations'],
  ['Animals actions', 'animals_actions'], ['Association actions', 'association_actions'],
  ['Build actions', 'build_actions'], ['Cards actions', 'cards_actions'],
  ['Sponsors actions', 'sponsors_actions'], ['Universities', 'universities'],
  ['Partner zoos', 'partner_zoos'], ['X-token gained', 'x_tokens_gained'],
  ['X-token spent', 'x_tokens_spent'], ['X-backs', 'x_backs'],
  ['Money gained', 'money_gained'], ['$ gained', 'money_gained'],
  ['Money gained (income)', 'money_gained_income'], ['$ gained (income)', 'money_gained_income'],
  ['Money spent (Animals)', 'money_spent_animals_pct'], ['$ spent (Animals)', 'money_spent_animals_pct'],
  ['Money spent (Build)', 'money_spent_build_pct'], ['$ spent (Build)', 'money_spent_build_pct'],
  ['Money spent (Donations)', 'money_spent_donations_pct'], ['$ spent (Donations)', 'money_spent_donations_pct'],
  ['Money spent (Range)', 'money_spent_range_pct'], ['$ spent (Range)', 'money_spent_range_pct'],
  ['Cards drawn (deck)', 'cards_drawn_deck'], ['Cards drawn from deck', 'cards_drawn_deck'],
  ['Cards drawn (Range)', 'cards_drawn_range'], ['Cards drawn from range', 'cards_drawn_range'],
  ['Cards snapped', 'cards_snapped'], ['Cards discarded', 'cards_discarded'],
  ['Enclosures', 'enclosures'], ['Kiosks', 'kiosks'], ['Pavilions', 'pavilions'],
  ['Unique buildings', 'unique_buildings'], ['Animals played', 'animals_played'],
  ['Animals released', 'animals_released'], ['Sponsors played', 'sponsors_played'],
  ['Bird icons', 'bird_icons'], ['Herbivore icons', 'herbivore_icons'],
  ['Predator icons', 'predator_icons'], ['Primate icons', 'primate_icons'],
  ['Reptile icons', 'reptile_icons'], ['Sea Animal icons', 'sea_animal_icons'],
  ['Bear icons', 'bear_icons'], ['Petting zoo icons', 'petting_zoo_icons'],
  ['Africa icons', 'africa_icons'], ['America icons', 'america_icons'],
  ['Asia icons', 'asia_icons'], ['Australia icons', 'australia_icons'],
  ['Europe icons', 'europe_icons'], ['Rock icons', 'rock_icons'],
  ['Water icons', 'water_icons'], ['Science icons', 'science_icons'],
]);
const HISTORY_GROUPS = new Map();
[
  ['upgrade_percentages', ['animals_pct', 'association_pct', 'build_pct', 'cards_pct', 'sponsors_pct']],
  ['action_counts', ['animals_actions', 'association_actions', 'build_actions', 'cards_actions', 'sponsors_actions']],
  ['association_bonuses', ['universities', 'partner_zoos']],
  ['x_tokens', ['x_tokens_gained', 'x_tokens_spent']],
  ['small_buildings', ['kiosks', 'pavilions']],
  ['icons', ['bird_icons', 'herbivore_icons', 'predator_icons', 'primate_icons', 'reptile_icons', 'sea_animal_icons', 'bear_icons', 'petting_zoo_icons', 'africa_icons', 'america_icons', 'asia_icons', 'australia_icons', 'europe_icons', 'rock_icons', 'water_icons', 'science_icons']],
].forEach(([group, keys]) => keys.forEach(key => HISTORY_GROUPS.set(key, group)));
const STANDARD_MAPS = [
  ['1a', 'Map 1a: Observation Tower'], ['2a', 'Map 2a: Outdoor Areas'],
  ['3a', 'Map 3a: Silver Lake'], ['4a', 'Map 4a: Commercial Harbor'],
  ['5a', 'Map 5a: Park Restaurant'], ['6a', 'Map 6a: Research Institute'],
  ['7a', 'Map 7a: Ice Cream Parlors'], ['8a', 'Map 8a: Hollywood Hills'],
  ['9', 'Map 9: Geographical Zoo'], ['10', 'Map 10: Rescue Station'],
  ['11', 'Map 11: Caves'], ['12', 'Map 12: Artificial Intelligence'],
  ['13', 'Map 13: Drawing Board'], ['14', 'Map 14: Lagoon'],
  ['T1', 'Map T1: Tournament 1'],
];
const LEGACY_MAPS = [
  ['1', 'Map 1: Observation Tower'], ['2', 'Map 2: Outdoor Areas'],
  ['3', 'Map 3: Silver Lake'], ['4', 'Map 4: Commercial Harbor'],
  ['5', 'Map 5: Park Restaurant'], ['6', 'Map 6: Research Institute'],
  ['7', 'Map 7: Ice Cream Parlors'], ['8', 'Map 8: Hollywood Hills'],
];
const BEGINNER_MAPS = [['A', 'Map A'], ['0', 'Map 0']];
const MAP_GROUPS = [
  ['standard', 'Standard Maps', STANDARD_MAPS],
  ['legacy', 'Legacy Maps', LEGACY_MAPS],
  ['beginner', 'Beginner Maps', BEGINNER_MAPS],
];
const MAPS = MAP_GROUPS.flatMap(([, , maps]) => maps);
const PERFORMANCE_MAPS = MAPS.map(([code, full]) => ({
  code,
  full,
  key: `map_${String(code).toLowerCase()}`,
}));
const PERFORMANCE_MAP_GROUPS = {
  mapPack1: new Set(['9', '10']),
  mapPack2: new Set(['11', '12', '13', '14', 'T1']),
  legacy: new Set(['1', '2', '3', '4', '5', '6', '7', '8']),
  beginner: new Set(['A', '0']),
};
const POPULATIONS = ['player', 'all', 'winners', 'experts', 'masters'];
const SPENDING_METRICS = new Set([
  'Money spent (Animals)', 'Money spent (Build)',
  'Money spent (Donations)', 'Money spent (Range)',
]);

export const mainHtml = `
  <div class="main-header players-main-header">
    <div class="table-meta" id="playersMeta"></div>
    <div class="table-meta players-performance-map-controls" id="playersPerformanceMapControls"></div>
  </div>
  <div class="attributes-bar endgames-tabs-bar players-tabs-bar">
    <div class="attributes-bar-header endgames-tabs-header">
      <div class="endgames-tabs players-tabs" role="tablist" aria-label="Players views">
        <button class="endgames-tab players-history-tab active" data-view="general" onclick="setPlayersView('general')"><span>General</span><span class="endgames-graph-toggle" id="playersGeneralGraphToggle" role="button" tabindex="0" title="Show graph" aria-label="Show General history graph" onclick="togglePlayersHistoryGraph(event, 'general')" onkeydown="onPlayersHistoryGraphKey(event, 'general')"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 19h16"/><path d="M4 5v14"/><path d="M6.5 15.5 10 11l3.5 2.5L18 7"/></svg></span></button>
        <button class="endgames-tab players-history-tab" data-view="comparison" onclick="setPlayersView('comparison')"><span>Comparison</span><span class="endgames-graph-toggle" id="playersComparisonGraphToggle" role="button" tabindex="0" title="Show graph" aria-label="Show Comparison history graph" onclick="togglePlayersHistoryGraph(event, 'comparison')" onkeydown="onPlayersHistoryGraphKey(event, 'comparison')"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 19h16"/><path d="M4 5v14"/><path d="M6.5 15.5 10 11l3.5 2.5L18 7"/></svg></span></button>
        <button class="endgames-tab" data-view="performance_by_map" onclick="setPlayersView('performance_by_map')"><span>Performance by map</span></button>
      </div>
    </div>
  </div>
  <div id="playersContent"></div>
  <div class="players-history-modal" id="playersHistoryModal" role="dialog" aria-modal="true" aria-labelledby="playersHistoryModalMessage" hidden>
    <div class="players-history-modal-card"><div id="playersHistoryModalMessage"></div><button type="button" id="playersHistoryModalOk" onclick="closePlayersHistoryModal()">OK</button></div>
  </div>`;

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
  <div class="filter-group records-map-filter" id="playersMapFilter"></div>
  <hr class="divider" id="playersMapFilterTrailingDivider" />
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
  </div>
  <hr class="divider players-performance-mode-divider is-hidden" id="playersPerformanceModeDivider" />
  <div class="filter-group players-performance-completed is-hidden" id="playersPerformanceCompleted">
    <div class="toggle-row"><span class="toggle-label">Completed games only</span><label class="toggle"><input type="checkbox" id="playersCompletedOnly" /><span class="toggle-track"></span></label></div>
  </div></div>
  <div class="filter-action-stack"><button class="apply-btn" onclick="applyPlayersFilters()">Apply filters</button></div>`;

let mounted = false;
let token = 0;
let isMW = 1;
let view = 'general';
let selectedPlayer = null;
let selectedPlayers = [];
let performancePlayers = [];
let activeSearchSlot = 0;
let playerNames = [];
let playerIndexState = 'idle';
let playerIndexError = '';
let playerIndexRequest = 0;
let suggestionsOpen = false;
let comparisonSearchTimer = null;
let comparisonSearchController = null;
let comparisonSearchRequest = 0;
let comparisonMatches = [];
let selectedMaps = MAPS.map(([, full]) => full);
let performanceMapModes = { mapPack1: 'include', mapPack2: 'include', legacy: 'exclude', beginner: 'exclude' };
let rows = [];
let playerGameCount = 0;
let playerSelectedGameCount = 0;
let playerAssociatedGameCount = 0;
let playerIsMerged = false;
let comparisonCounts = [];
let statsAbortController = null;
let statsLoading = false;
let arenaManifest = null;
let arenaLoadState = 'loading';
let arenaLoadError = '';
let selectedArenaSeasons = [];
let arenaAssetRequest = 0;
let historyGraphView = { general: false, comparison: false };
let historySelectedMetrics = { general: new Set(), comparison: new Set() };
let historyAxisMode = { general: 'count', comparison: 'count' };
let historyPayload = { general: null, comparison: null };
let historyPayloadKey = { general: '', comparison: '' };
const HISTORY_REQUEST_TIMEOUT_MS = 15000;
function freshHistoryRequestState() {
  return {
    loading: false,
    error: '',
    controller: null,
    requestId: 0,
    pendingKey: '',
    pendingPromise: null,
    timeoutId: null,
    timedOut: false,
  };
}
let historyRequests = {
  general: freshHistoryRequestState(),
  comparison: freshHistoryRequestState(),
};
let historyHover = null;
let historyRenderState = null;
let historyLegendScrollTop = { general: 0, comparison: 0 };
let historyLegendFocusMetric = { general: '', comparison: '' };
let historyLegendSelectionScrollLock = { general: null, comparison: null };
let committedFilters = null;

function onGlobalModeFilterChange(event) {
  if (event?.detail?.kind !== 'tournament' || !event.detail.checked) return;
  if (selectedArenaSeasons.length) {
    selectedArenaSeasons = [];
    renderArenaSeasonFilter();
  }
}

export function mount({ dataset = 1 } = {}) {
  mounted = true;
  token += 1;
  isMW = Number(dataset) === 0 ? 0 : 1;
  view = 'general';
  // Player selections are analysis context, not filters. Keep them when the
  // dataset changes; the new dataset simply returns unavailable/empty values
  // when a name has no observations there.
  playerNames = [];
  playerIndexState = 'idle';
  playerIndexError = '';
  suggestionsOpen = false;
  playerGameCount = 0;
  playerSelectedGameCount = 0;
  playerAssociatedGameCount = 0;
  playerIsMerged = false;
  comparisonCounts = [];
  selectedMaps = MAPS.map(([, full]) => full);
  rows = [];
  selectedArenaSeasons = [];
  performancePlayers = [];
  performanceMapModes = { mapPack1: 'include', mapPack2: 'include', legacy: 'exclude', beginner: 'exclude' };
  historyGraphView = { general: false, comparison: false };
  historySelectedMetrics = { general: new Set(), comparison: new Set() };
  historyAxisMode = { general: 'count', comparison: 'count' };
  historyPayload = { general: null, comparison: null };
  historyPayloadKey = { general: '', comparison: '' };
  historyRequests = {
    general: freshHistoryRequestState(),
    comparison: freshHistoryRequestState(),
  };
  historyHover = null;
  historyRenderState = null;
  historyLegendScrollTop = { general: 0, comparison: 0 };
  historyLegendFocusMetric = { general: '', comparison: '' };
  historyLegendSelectionScrollLock = { general: null, comparison: null };
  committedFilters = null;
  Object.assign(window, {
    setPlayersView, resetPlayersFilters, applyPlayersFilters,
    selectAllPlayersMaps, selectNonePlayersMaps, togglePlayersMap,
    onPlayersDateInput, onPlayersLastInput, selectPlayer,
    onPlayersSearchInput, clearPlayersSearch, retryPlayersIndex,
    togglePlayersArenaSeason,
    selectAllPlayersArenaSeasons, selectNonePlayersArenaSeasons,
    setPlayersPerformanceMapMode, resetPlayersPerformanceMapModes,
    togglePlayersHistoryGraph, onPlayersHistoryGraphKey,
    togglePlayersHistoryMetric, clearPlayersHistoryMetrics,
    retryPlayersHistory,
    setPlayersHistoryAxis, onPlayersHistoryGraphMove,
    clearPlayersHistoryGraphHover, closePlayersHistoryModal,
    prepareHistoryLegendSelection,
  });
  renderMapChips();
  syncTabs();
  window.addEventListener('arknova:global-mode-filter-change', onGlobalModeFilterChange);
  syncDateLastControls();
  loadPlayerIndex();
  loadArenaManifest();
  loadData(token);
}

export function unmount() {
  mounted = false;
  token += 1;
  playerIndexRequest += 1;
  cancelComparisonSearch();
  statsAbortController?.abort();
  statsAbortController = null;
  cancelHistoryRequest('general');
  cancelHistoryRequest('comparison');
  closePlayersHistoryModal();
  hideTooltip();
  closeSuggestions();
  setFilterButtonDisabled(false);
  window.removeEventListener('arknova:global-mode-filter-change', onGlobalModeFilterChange);
}

export function setDataset(value) {
  if (view === 'general' || view === 'comparison') cancelHistoryRequest(view);
  isMW = Number(value) === 0 ? 0 : 1;
  // Selected names are analysis context and remain valid when the dataset
  // changes. A name with no observations in the new dataset simply returns an
  // empty Player value; only the dataset-specific autocomplete index reloads.
  closeSuggestions();
  comparisonCounts = [];
  playerGameCount = 0;
  playerSelectedGameCount = 0;
  playerAssociatedGameCount = 0;
  playerIsMerged = false;
  playerNames = [];
  playerIndexState = 'idle';
  playerIndexError = '';
  ensureCompatibleArenaSelection();
  renderArenaSeasonFilter();
  loadPlayerIndex();
  loadData(++token, { recheckGraphAfterLoad: true });
}

function setPlayersView(next) {
  const previous = view;
  view = ['general', 'comparison', 'performance_by_map'].includes(next) ? next : 'general';
  if (previous !== view && (previous === 'general' || previous === 'comparison')) {
    cancelHistoryRequest(previous);
  }
  closeSuggestions();
  syncTabs();
  if (view === 'performance_by_map' && performancePlayers.length === 0) {
    rows = [];
    statsLoading = false;
    renderTable();
  } else loadData(++token);
}

function syncTabs() {
  document.querySelectorAll('.players-tabs .endgames-tab').forEach(button => {
    button.classList.toggle('active', button.dataset.view === view);
  });
  window.setGlobalModeFilterVisibility?.({
    arena: false,
    tournament: true,
  });
  document.getElementById('playersPerformanceCompleted')?.classList.toggle('is-hidden', view !== 'performance_by_map');
  document.getElementById('playersPerformanceModeDivider')?.classList.toggle('is-hidden', view !== 'performance_by_map');
  document.getElementById('playersMapFilter')?.classList.toggle('is-hidden', view === 'performance_by_map');
  document.getElementById('playersMapFilterTrailingDivider')?.classList.toggle('is-hidden', view === 'performance_by_map');
  document.querySelector('.players-arena-filter')?.classList.toggle('players-performance-mode-host', view === 'performance_by_map');
  document.querySelector('.global-mode-filter-shell')?.classList.toggle('players-performance-joined', view === 'performance_by_map');
  window.syncGlobalModeFilterGrouping?.();
  renderPerformanceControls();
  ['general', 'comparison'].forEach(tabView => {
    const toggle = document.getElementById(`players${tabView === 'general' ? 'General' : 'Comparison'}GraphToggle`);
    toggle?.classList.toggle('active', Boolean(historyGraphView[tabView]));
    if (toggle) {
      const showingGraph = Boolean(historyGraphView[tabView]);
      toggle.title = showingGraph ? 'Show table' : 'Show graph';
      toggle.setAttribute('aria-label', showingGraph ? `Show ${tabView} table` : `Show ${tabView} history graph`);
    }
  });
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
    maps: view === 'performance_by_map' ? MAPS.map(([, full]) => full) : selectedMaps,
    opponent_elo_min: value('playersOpponentEloMin') === '' ? 0 : Number(value('playersOpponentEloMin')),
    opponent_elo_max: value('playersOpponentEloMax') === '' ? null : Number(value('playersOpponentEloMax')),
    date_from: dateFromInput?.disabled ? null : (value('playersDateFrom') || null),
    date_to: dateToInput?.disabled ? null : (value('playersDateTo') || null),
    players_player: view === 'general' ? selectedPlayer : null,
    players_players: view === 'comparison' ? selectedPlayers : view === 'performance_by_map' ? performancePlayers : [],
    last_x_games: (
      last === ''
      || (view === 'general' && !selectedPlayer)
      || (view === 'comparison' && selectedPlayers.length === 0)
      || (view === 'performance_by_map' && performancePlayers.length === 0)
    ) ? null : Number(last),
    completed_only: view === 'performance_by_map'
      ? Boolean(document.getElementById('playersCompletedOnly')?.checked)
      : false,
    players_arena_only: selectedArenaSeasons.length > 0,
    players_arena_seasons: selectedArenaSeasons.length > 0 ? [...selectedArenaSeasons] : [],
  };
}

function capturePlayersFilterState() {
  return {
    opponentEloMin: value('playersOpponentEloMin'),
    opponentEloMax: value('playersOpponentEloMax'),
    dateFrom: value('playersDateFrom'),
    dateTo: value('playersDateTo'),
    lastX: value('playersLastX'),
    maps: [...selectedMaps],
    arenaSeasons: [...selectedArenaSeasons],
    tournamentOnly: Boolean(document.getElementById('globalTournamentOnly')?.checked),
    completedOnly: Boolean(document.getElementById('playersCompletedOnly')?.checked),
  };
}

function restorePlayersFilterState(state) {
  if (!state) return;
  const set = (id, next) => { const input = document.getElementById(id); if (input) input.value = next ?? ''; };
  set('playersOpponentEloMin', state.opponentEloMin);
  set('playersOpponentEloMax', state.opponentEloMax);
  set('playersDateFrom', state.dateFrom);
  set('playersDateTo', state.dateTo);
  set('playersLastX', state.lastX);
  selectedMaps = [...state.maps];
  selectedArenaSeasons = [...state.arenaSeasons];
  window.setGlobalTournamentOnly?.(state.tournamentOnly);
  const completed = document.getElementById('playersCompletedOnly');
  if (completed) completed.checked = Boolean(state.completedOnly);
  renderMapChips();
  renderArenaSeasonFilter();
  syncDateLastControls();
}

function isDefault(request) {
  return view === 'general' && !selectedPlayer && request.last_x_games === null
    && request.opponent_elo_min === 0 && request.opponent_elo_max === null
    && request.date_from === null && request.date_to === null
    && selectedMaps.length === MAPS.length && !request.players_arena_only;
}

async function loadArenaManifest() {
  const requestId = ++arenaAssetRequest;
  arenaLoadState = 'loading';
  arenaLoadError = '';
  updatePlayersMeta();
  try {
    const manifestPayload = await loadSnapshot(ARENA_MANIFEST_URL);
    if (!mounted || requestId !== arenaAssetRequest) return;
    if (!manifestPayload?.seasons) throw new Error('Arena season manifest is invalid.');
    arenaManifest = manifestPayload;
    arenaLoadState = 'ready';
    arenaLoadError = '';
    renderArenaSeasonFilter();
    updatePlayersMeta();
  } catch (error) {
    if (!mounted || requestId !== arenaAssetRequest) return;
    arenaLoadState = 'error';
    arenaLoadError = error?.message || String(error);
    renderArenaSeasonFilter();
    updatePlayersMeta();
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
  if (selectedArenaSeasons.length) window.setGlobalTournamentOnly?.(false);
  renderArenaSeasonFilter();
}

function selectAllPlayersArenaSeasons() {
  selectedArenaSeasons = compatibleArenaSeasons().map(item => item.season);
  if (selectedArenaSeasons.length) window.setGlobalTournamentOnly?.(false);
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

function applyPlayersPayload(payload) {
  rows = Array.isArray(payload.data) ? payload.data : [];
  if (view === 'comparison') {
    comparisonCounts = Array.isArray(payload.players) ? payload.players : [];
  } else if (view === 'general') {
    playerGameCount = Number(payload.player_game_count) || 0;
    playerSelectedGameCount = Number(payload.player_selected_game_count) || 0;
    playerAssociatedGameCount = Number(payload.player_associated_game_count) || 0;
    playerIsMerged = Boolean(payload.player_is_merged);
  }
}

function graphEligibilityFromPayload(payload, targetView = view) {
  if (targetView === 'general') {
    if (!selectedPlayer) return { ok: false, message: 'Please select a player' };
    if ((Number(payload?.player_game_count) || 0) < PLAYER_GRAPH_MIN_GAMES) {
      return { ok: false, message: 'Minimum game count: 250' };
    }
    return { ok: true };
  }
  if (selectedPlayers.length < 2) return { ok: false, message: 'Please select at least two players' };
  const counts = Array.isArray(payload?.players) ? payload.players : [];
  if (selectedPlayers.some(name => (Number(counts.find(item => item.name === name)?.game_count) || 0) < PLAYER_GRAPH_MIN_GAMES)) {
    return { ok: false, message: 'Minimum game count for any player: 250' };
  }
  return { ok: true };
}

function currentGraphEligibility(targetView = view) {
  return graphEligibilityFromPayload(targetView === 'general'
    ? { player_game_count: playerGameCount }
    : { players: comparisonCounts }, targetView);
}

function invalidateHistory(targetView = view) {
  cancelHistoryRequest(targetView);
  historyPayload[targetView] = null;
  historyPayloadKey[targetView] = '';
  historyHover = null;
  historyRenderState = null;
}

async function loadData(activeToken, { proposedGraphFilters = false, recheckGraphAfterLoad = false } = {}) {
  if (view === 'performance_by_map' && performancePlayers.length === 0) {
    statsAbortController?.abort();
    rows = [];
    statsLoading = false;
    renderTable();
    return;
  }
  if (view === 'comparison' && selectedPlayers.length === 0) {
    if (historyGraphView.comparison) {
      historyGraphView.comparison = false;
      invalidateHistory('comparison');
      syncTabs();
      showPlayersHistoryModal('Please select at least two players');
    }
    renderLoading();
    try {
      const payload = await loadSnapshot(SNAPSHOT_URL(isMW));
      if (!mounted || activeToken !== token) return;
      rows = (payload.data || []).map(row => ({ ...row, values: [] }));
      comparisonCounts = [];
      statsLoading = false;
      committedFilters = capturePlayersFilterState();
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
    if (proposedGraphFilters && historyGraphView[view]) {
      const eligibility = graphEligibilityFromPayload(payload);
      if (!eligibility.ok) {
        restorePlayersFilterState(committedFilters);
        statsLoading = false;
        document.querySelector('.players-history-graph-shell')?.classList.remove('players-updating');
        updatePlayersMeta();
        showPlayersHistoryModal(view === 'general'
          ? 'Minimum game count: 250 (not fulfilled under proposed filter set)'
          : 'Minimum game count for any player: 250 (not fulfilled under proposed filter set)');
        return false;
      }
    }
    applyPlayersPayload(payload);
    committedFilters = capturePlayersFilterState();
    invalidateHistory(view);
    statsLoading = false;
    if ((recheckGraphAfterLoad || historyGraphView[view]) && historyGraphView[view]) {
      const eligibility = currentGraphEligibility();
      if (!eligibility.ok) {
        historyGraphView[view] = false;
        cancelHistoryRequest(view);
        syncTabs();
        showPlayersHistoryModal(eligibility.message);
      }
    }
    renderTable();
    return true;
  } catch (error) {
    if (error?.name === 'AbortError') return;
    if (mounted && activeToken === token) {
      statsLoading = false;
      const publicError = publicPlayersError(error);
      if (proposedGraphFilters && historyGraphView[view]) {
        restorePlayersFilterState(committedFilters);
        document.querySelector('.players-history-graph-shell')?.classList.remove('players-updating');
        updatePlayersMeta(publicError);
        return false;
      }
      if (rows.length) {
        document.querySelector('.players-table-wrap')?.classList.remove('players-updating');
        updatePlayersMeta(publicError);
      } else renderError(new Error(publicError));
    }
  } finally {
    if (statsAbortController === requestController) statsAbortController = null;
  }
}

function publicPlayersError(error) {
  const message = String(error?.message || error || '');
  if (/merged player identity|same merged|invalid comparison player selection/i.test(message)) {
    return 'The selected player could not be added.';
  }
  return message;
}

function renderTable() {
  if (historyGraphView[view] && (view === 'general' || view === 'comparison')) renderPlayersHistoryGraph();
  else if (view === 'performance_by_map') renderPerformanceTable();
  else if (view === 'comparison') renderComparisonTable();
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
   if (selectedPlayer) closeSuggestions();
   else renderSuggestions();
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

function performanceMapCategory(map) {
  return Object.entries(PERFORMANCE_MAP_GROUPS).find(([, codes]) => codes.has(map.code))?.[0] || null;
}

function visiblePerformanceMaps() {
  const onlyCategory = Object.entries(performanceMapModes).find(([, mode]) => mode === 'only')?.[0] || null;
  return PERFORMANCE_MAPS.filter(map => {
    const category = performanceMapCategory(map);
    if (onlyCategory) return category === onlyCategory;
    return !category || performanceMapModes[category] === 'include';
  });
}

function performanceColumnLayout(mapCount) {
  const playerUnits = 13;
  const mapUnits = 87 / 15;
  const totalUnits = playerUnits + mapUnits * Math.max(mapCount, 1);
  return {
    totalWidthPct: Math.max(100, totalUnits),
    playerWidthPct: playerUnits / totalUnits * 100,
    mapWidthPct: mapUnits / totalUnits * 100,
  };
}

function renderPerformanceControls() {
  const host = document.getElementById('playersPerformanceMapControls');
  if (!host) return;
  host.innerHTML = view !== 'performance_by_map' ? '' : `<div class="maps-metrics-options players-performance-options">
    ${performanceMapOption('Map Pack 1', 'Maps 9 & 10', 'mapPack1')}
    ${performanceMapOption('Map Pack 2', 'Maps 11-14 & T1', 'mapPack2')}
    ${performanceMapOption('Legacy Maps', 'Maps 1-8 (non-alternate map version)', 'legacy')}
    ${performanceMapOption('Beginner Maps', 'Maps A & 0', 'beginner')}
    <button type="button" class="reset-btn maps-metrics-reset-btn" onclick="resetPlayersPerformanceMapModes()">Reset</button>
  </div>`;
}

function performanceMapOption(label, tooltipText, category) {
  const options = [['exclude', '&minus;', 'Exclude'], ['include', 'O', 'Include'], ['only', '+', 'Only']];
  return `<div class="maps-metrics-option"><span>${label}<span class="col-tip" data-tip="${escapeAttr(tooltipText)}">?</span></span>
    <div class="maps-visibility-control" role="group" aria-label="${escapeAttr(`${label} visibility`)}">
      ${options.map(([mode, symbol, tip]) => `<button type="button" class="maps-custom-tip ${performanceMapModes[category] === mode ? 'active' : ''}" aria-pressed="${performanceMapModes[category] === mode}" data-tip="${tip}" onclick="setPlayersPerformanceMapMode('${category}', '${mode}')">${symbol}</button>`).join('')}
    </div></div>`;
}

function setPlayersPerformanceMapMode(category, mode) {
  if (!(category in performanceMapModes) || !['exclude', 'include', 'only'].includes(mode)) return;
  if (mode === 'only') Object.keys(performanceMapModes).forEach(key => { performanceMapModes[key] = key === category ? 'only' : 'exclude'; });
  else {
    if (performanceMapModes[category] === 'only') Object.keys(performanceMapModes).forEach(key => { performanceMapModes[key] = 'exclude'; });
    performanceMapModes[category] = mode;
  }
  renderPerformanceTable();
}

function resetPlayersPerformanceMapModes() {
  performanceMapModes = { mapPack1: 'include', mapPack2: 'include', legacy: 'exclude', beginner: 'exclude' };
  renderPerformanceTable();
}

function performanceColorRange(maps) {
  const values = rows.flatMap(row => maps.map(map => ({
    value: finiteNumber(row[map.key]),
    count: Number(row[`${map.key}_ci95_n`] ?? row[`count_${map.key}`] ?? 0),
  }))).filter(item => item.count >= 50 && Number.isFinite(item.value)).map(item => Math.max(-2, Math.min(2, item.value)));
  return values.length ? { min: Math.min(...values), max: Math.max(...values) } : { min: null, max: null };
}

function performanceCell(row, map, range) {
  const value = finiteNumber(row?.[map.key]);
  if (!Number.isFinite(value)) return '<td class="players-performance-value">-</td>';
  const n = Number(row?.[`${map.key}_ci95_n`] ?? row?.[`count_${map.key}`] ?? 0);
  const display = formatSignedDeltaAdaptive(value);
  if (n < 50) return `<td class="delta sponsor-delta-insufficient players-performance-value" data-tip="Insufficient data (fewer than 50 observations).">${display}</td>`;
  return `<td class="delta delta-ci-cell players-performance-value" data-ci-low="${escapeAttr(row[`${map.key}_ci95_low`] ?? '')}" data-ci-high="${escapeAttr(row[`${map.key}_ci95_high`] ?? '')}" data-ci-n="${escapeAttr(n)}" data-ci-color-min="${escapeAttr(range.min ?? '')}" data-ci-color-max="${escapeAttr(range.max ?? '')}" style="color:${deltaRangeColor(value, range.min, range.max)}">${display}</td>`;
}

function renderPerformanceTable() {
  const host = document.getElementById('playersContent');
  if (!host) return;
  renderPerformanceControls();
  updatePlayersMeta();
  const maps = visiblePerformanceMaps();
  const layout = performanceColumnLayout(maps.length);
  const range = performanceColorRange(maps);
  const searchDisabled = playerIndexState !== 'ready';
  const placeholder = playerIndexState === 'loading' ? 'Loading players...' : playerIndexState === 'error' ? 'Player list unavailable' : 'Search player';
  const body = Array.from({ length: 8 }, (_, slot) => {
    const name = performancePlayers[slot] || '';
    const row = name ? rows.find(item => item.player === name) : null;
    const action = playerIndexState === 'error'
      ? '<button type="button" class="players-search-retry" onclick="retryPlayersIndex()" aria-label="Retry loading player list" title="Retry loading player list">&#8635;</button>'
      : name ? `<button type="button" class="players-search-clear" data-slot="${slot}" onclick="clearPlayersSearch(event)" aria-label="Clear player">&times;</button>` : '';
    const search = `<div class="players-search-wrap"><span class="players-search-icon" aria-hidden="true">&#128269;</span><input id="playersPerformanceSearch${slot}" data-slot="${slot}" type="search" value="${escapeAttr(name)}" placeholder="${placeholder}" oninput="onPlayersSearchInput(event)" autocomplete="off" ${searchDisabled ? 'disabled' : ''}/>${action}</div>`;
    return `<tr><td class="players-performance-player-cell">${search}</td>${maps.map(map => performanceCell(row, map, range)).join('')}</tr>`;
  }).join('');
  host.innerHTML = `<div class="table-wrap players-table-wrap players-performance-table-wrap"><div class="table-scroll">
    <table class="maps-table maps-metrics-table players-performance-table" style="width:${layout.totalWidthPct}%">
      <thead><tr><th style="width:${layout.playerWidthPct}%">Player</th>${maps.map(map => `<th class="maps-map-header maps-custom-tip" data-tip="${escapeAttr(mapTooltipLabel(map.full))}" style="width:${layout.mapWidthPct}%">${escapeHtml(map.code)}</th>`).join('')}</tr></thead>
      <tbody>${body}</tbody>
    </table></div></div><div id="playersSuggestions" class="players-suggestions" role="listbox" aria-label="Matching players"></div>`;
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
  const host = document.getElementById('playersMapFilter');
  if (!host) return;
  host.innerHTML = MAP_GROUPS.map(([id, label, maps]) => `
    <div class="records-map-group" data-map-group="${id}">
      <div class="records-filter-heading">
        <span class="filter-label">${label}</span>
        <span class="map-select-all-none">(<span class="map-toggle-link" onclick="selectAllPlayersMaps('${id}')">all</span> / <span class="map-toggle-link" onclick="selectNonePlayersMaps('${id}')">none</span>)</span>
      </div>
      <div class="records-map-chips">${maps.map(([short, full]) => `<button class="chip ${selectedMaps.includes(full) ? 'active' : ''}" data-map="${escapeAttr(full)}" onclick="togglePlayersMap(this.dataset.map)">${short}</button>`).join('')}</div>
    </div>`).join('');
}

function togglePlayersMap(map) { selectedMaps = selectedMaps.includes(map) ? selectedMaps.filter(item => item !== map) : [...selectedMaps, map]; renderMapChips(); }
function selectAllPlayersMaps(groupId) {
  const maps = MAP_GROUPS.find(([id]) => id === groupId)?.[2] || [];
  selectedMaps = [...new Set([...selectedMaps, ...maps.map(([, full]) => full)])];
  renderMapChips();
}
function selectNonePlayersMaps(groupId) {
  const maps = new Set((MAP_GROUPS.find(([id]) => id === groupId)?.[2] || []).map(([, full]) => full));
  selectedMaps = selectedMaps.filter(map => !maps.has(map));
  renderMapChips();
}

function resetPlayersFilters() {
  const set = (id, next) => { const el = document.getElementById(id); if (el) el.value = next; };
  set('playersOpponentEloMin', ''); set('playersOpponentEloMax', '');
  set('playersDateFrom', ''); set('playersDateTo', ''); set('playersLastX', '');
  selectedArenaSeasons = [];
  selectedMaps = MAPS.map(([, full]) => full);
  window.setGlobalTournamentOnly?.(false);
  const completed = document.getElementById('playersCompletedOnly');
  if (completed) completed.checked = false;
  renderMapChips(); renderArenaSeasonFilter(); syncDateLastControls();
  loadData(++token, { proposedGraphFilters: historyGraphView[view] });
}

function applyPlayersFilters() {
  loadData(++token, { proposedGraphFilters: historyGraphView[view] });
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
  if (view === 'performance_by_map' && performancePlayers[slot]) performancePlayers = performancePlayers.filter((_, index) => index !== slot);
  updatePlayersMeta();
  suggestionsOpen = String(event.target.value || '').trim().length >= 3;
  renderSuggestions(event.target.value);
}

function renderSuggestions(term = value(view === 'general' ? 'playersSearch' : view === 'performance_by_map' ? `playersPerformanceSearch${activeSearchSlot}` : `playersSearch${activeSearchSlot}`)) {
  const host = document.getElementById('playersSuggestions');
  if (!host) return;
  const normalized = String(term || '').trim().toLocaleLowerCase();
  if (view === 'general' && selectedPlayer && normalized === selectedPlayer.toLocaleLowerCase()) {
    closeSuggestions();
    return;
  }
  if (!suggestionsOpen || normalized.length < 3) { closeSuggestions(); return; }
  if (playerIndexState !== 'ready') return;
  if (view === 'comparison' || view === 'performance_by_map') {
    scheduleComparisonSuggestions(String(term || '').trim());
    return;
  }
  const matches = playerNames
    .filter(name => name.toLocaleLowerCase().includes(normalized))
    .slice(0, 50);
  renderSuggestionMatches(matches);
}

function renderSuggestionMatches(matches) {
  const host = document.getElementById('playersSuggestions');
  if (!host) return;
  host.innerHTML = matches.map(name => `<button type="button" role="option" data-player="${escapeAttr(name)}">${escapeHtml(name)}</button>`).join('');
  host.classList.toggle('open', matches.length > 0);
  if (matches.length > 0) requestAnimationFrame(positionSuggestions);
}

function cancelComparisonSearch() {
  if (comparisonSearchTimer !== null) clearTimeout(comparisonSearchTimer);
  comparisonSearchTimer = null;
  comparisonSearchController?.abort();
  comparisonSearchController = null;
  comparisonSearchRequest += 1;
  comparisonMatches = [];
}

function scheduleComparisonSuggestions(term) {
  cancelComparisonSearch();
  const normalized = String(term || '').trim();
  if (!mounted || !['comparison', 'performance_by_map'].includes(view) || normalized.length < 3) return;
  const requestId = ++comparisonSearchRequest;
  const requestedDataset = isMW;
  const requestedSlot = activeSearchSlot;
  const requestedView = view;
  const selectedAtRequest = (view === 'performance_by_map' ? performancePlayers : selectedPlayers).slice();
  const host = document.getElementById('playersSuggestions');
  if (host) {
    host.innerHTML = '';
    host.classList.remove('open');
  }
  comparisonSearchTimer = setTimeout(async () => {
    comparisonSearchTimer = null;
    const controller = new AbortController();
    comparisonSearchController = controller;
    try {
      const payload = await fetchStats({
        stats_page: 'players',
        players_view: requestedView,
        players_search: true,
        players_search_term: normalized,
        players_players: selectedAtRequest,
        is_mw: requestedDataset,
      }, { signal: controller.signal });
      if (
        !mounted
        || view !== requestedView
        || requestId !== comparisonSearchRequest
        || requestedDataset !== isMW
        || requestedSlot !== activeSearchSlot
      ) return;
      comparisonMatches = Array.isArray(payload?.players) ? payload.players : [];
      renderSuggestionMatches(comparisonMatches);
    } catch (error) {
      if (error?.name !== 'AbortError' && requestId === comparisonSearchRequest) {
        comparisonMatches = [];
        renderSuggestionMatches([]);
      }
    } finally {
      if (comparisonSearchController === controller) comparisonSearchController = null;
    }
  }, 180);
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
  cancelComparisonSearch();
  suggestionsOpen = false;
  const host = document.getElementById('playersSuggestions');
  if (!host) return;
  host.innerHTML = ''; host.classList.remove('open');
}

function selectPlayer(name, slot = activeSearchSlot) {
  const exact = String(name);
  if (!playerNames.includes(exact)) return;
  if ((view === 'comparison' || view === 'performance_by_map') && !comparisonMatches.includes(exact)) return;
  if (view === 'general') {
    selectedPlayer = exact;
  } else if (view === 'comparison') {
    const next = selectedPlayers.filter(Boolean);
    next.push(exact);
    selectedPlayers = next.slice(0, 5);
  } else if (view === 'performance_by_map') {
    const next = performancePlayers.filter(Boolean);
    next.push(exact);
    performancePlayers = next.slice(0, 8);
  }
  suggestionsOpen = false;
  closeSuggestions();
  loadData(++token, { recheckGraphAfterLoad: true });
}

function clearPlayersSearch(event) {
  const slot = Number(event?.currentTarget?.dataset?.slot || 0);
  if (view === 'general') selectedPlayer = null;
  else if (view === 'comparison') selectedPlayers = selectedPlayers.filter((_, index) => index !== slot);
  else if (view === 'performance_by_map') performancePlayers = performancePlayers.filter((_, index) => index !== slot);
  closeSuggestions();
  if (historyGraphView[view]) {
    historyGraphView[view] = false;
    invalidateHistory(view);
    syncTabs();
    showPlayersHistoryModal(view === 'general' ? 'Please select a player' : 'Please select at least two players');
  }
  loadData(++token);
}

function formattedMergedGameCount(item) {
  if (!item?.is_merged) return String(Number(item?.game_count) || 0);
  return `${Number(item?.selected_game_count) || 0}+${Number(item?.associated_game_count) || 0}`;
}

function updatePlayersMeta(errorMessage = '') {
  const meta = document.getElementById('playersMeta');
  if (!meta) return;
  if (errorMessage) meta.textContent = `Could not update player statistics: ${errorMessage}`;
  else if (view === 'performance_by_map') meta.textContent = statsLoading ? 'Updating player statistics...' : '';
  else if (statsLoading) meta.textContent = 'Updating player statistics...';
  else if (playerIndexState === 'loading') meta.textContent = 'Loading player list...';
  else if (playerIndexState === 'error') meta.textContent = `Could not load player list${playerIndexError ? `: ${playerIndexError}` : ''}. Use the retry button in the Player header.`;
  else if (view === 'comparison') meta.textContent = selectedPlayers.length
    ? `Number of games considered: ${comparisonCounts.map(item => `${item.name} (${formattedMergedGameCount(item)})`).join(', ')}`
    : 'Select players to compare.';
  else meta.textContent = selectedPlayer
    ? `Number of games considered: ${playerIsMerged ? `${playerSelectedGameCount}+${playerAssociatedGameCount}` : playerGameCount}`
    : 'Select a player to populate the Player column.';
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

function historyMetricCatalog() {
  return rows.map((row, index) => {
    const key = HISTORY_METRIC_KEYS.get(String(row.metric)) || HISTORY_METRIC_KEYS.get(displayMetricName(row.metric));
    if (!key) return null;
    return {
      key,
      label: displayMetricName(row.metric),
      format: row.format || 'number',
      group: HISTORY_GROUPS.get(key) || `metric:${key}`,
      sort_order: index + 1,
    };
  }).filter(Boolean);
}

function historyMetricColor(metricKey, catalog = historyMetricCatalog()) {
  const metric = catalog.find(item => item.key === metricKey);
  if (!metric) return HISTORY_LINE_COLORS[0];
  const groupIndex = catalog
    .filter(item => item.group === metric.group)
    .findIndex(item => item.key === metricKey);
  return HISTORY_LINE_COLORS[Math.max(0, groupIndex) % HISTORY_LINE_COLORS.length];
}

function captureHistoryLegendState(targetView = view) {
  const list = document.getElementById('playersHistoryLegendList');
  if (list && !Number.isFinite(historyLegendSelectionScrollLock[targetView])) {
    historyLegendScrollTop[targetView] = list.scrollTop;
  }
  const focused = document.activeElement?.closest?.('.players-history-legend-item');
  if (focused?.dataset?.metric) historyLegendFocusMetric[targetView] = focused.dataset.metric;
}

function prepareHistoryLegendSelection() {
  const list = document.getElementById('playersHistoryLegendList');
  if (!list || !['general', 'comparison'].includes(view)) return;
  historyLegendSelectionScrollLock[view] = list.scrollTop;
  historyLegendScrollTop[view] = list.scrollTop;
}

function restoreHistoryLegendState(targetView = view) {
  const list = document.getElementById('playersHistoryLegendList');
  if (!list) return;
  const locked = historyLegendSelectionScrollLock[targetView];
  const desiredScroll = Number.isFinite(locked) ? locked : historyLegendScrollTop[targetView] || 0;
  list.scrollTop = desiredScroll;
  list.addEventListener('scroll', () => {
    if (Number.isFinite(historyLegendSelectionScrollLock[targetView])) return;
    historyLegendScrollTop[targetView] = list.scrollTop;
  }, { passive: true });
  const focusMetric = historyLegendFocusMetric[targetView];
  if (focusMetric) {
    const focusTarget = list.querySelector(`[data-metric="${CSS.escape(focusMetric)}"]`);
    focusTarget?.focus?.({ preventScroll: true });
  }
  list.scrollTop = desiredScroll;
  requestAnimationFrame(() => {
    list.scrollTop = desiredScroll;
    historyLegendScrollTop[targetView] = desiredScroll;
    historyLegendSelectionScrollLock[targetView] = null;
  });
}

function showPlayersHistoryModal(message) {
  const modal = document.getElementById('playersHistoryModal');
  const text = document.getElementById('playersHistoryModalMessage');
  if (!modal || !text) return;
  text.textContent = message;
  modal.hidden = false;
  requestAnimationFrame(() => document.getElementById('playersHistoryModalOk')?.focus());
}

function closePlayersHistoryModal() {
  const modal = document.getElementById('playersHistoryModal');
  if (modal) modal.hidden = true;
}

function togglePlayersHistoryGraph(event, targetView) {
  event?.preventDefault?.();
  event?.stopPropagation?.();
  if (view !== targetView || !['general', 'comparison'].includes(targetView)) return;
  if (historyGraphView[targetView]) {
    historyGraphView[targetView] = false;
    cancelHistoryRequest(targetView);
    historyHover = null;
    syncTabs();
    renderTable();
    return;
  }
  const eligibility = currentGraphEligibility(targetView);
  if (!eligibility.ok) {
    showPlayersHistoryModal(eligibility.message);
    return;
  }
  historyGraphView[targetView] = true;
  syncTabs();
  renderPlayersHistoryGraph();
}

function onPlayersHistoryGraphKey(event, targetView) {
  if (event.key !== 'Enter' && event.key !== ' ') return;
  togglePlayersHistoryGraph(event, targetView);
}

function clearPlayersHistoryMetrics() {
  if (!['general', 'comparison'].includes(view)) return;
  historySelectedMetrics[view] = new Set();
  invalidateHistory(view);
  renderPlayersHistoryGraph();
}

function togglePlayersHistoryMetric(metricKey) {
  if (!historyGraphView[view]) return;
  const catalog = historyMetricCatalog();
  const metric = catalog.find(item => item.key === metricKey);
  if (!metric) return;
  if (view === 'comparison') {
    historySelectedMetrics.comparison = new Set([metricKey]);
    invalidateHistory('comparison');
    renderPlayersHistoryGraph();
    return;
  }
  const selected = new Set(historySelectedMetrics.general);
  const activeMetric = catalog.find(item => selected.has(item.key));
  // A cross-group click starts the newly chosen group immediately. This keeps
  // every legend item usable while preserving the one-group-at-a-time rule.
  if (activeMetric && activeMetric.group !== metric.group) {
    historySelectedMetrics.general = new Set([metricKey]);
    invalidateHistory('general');
    renderPlayersHistoryGraph();
    return;
  }
  if (selected.has(metricKey)) selected.delete(metricKey);
  else selected.add(metricKey);
  historySelectedMetrics.general = selected;
  if (selected.size === 0) invalidateHistory('general');
  renderPlayersHistoryGraph();
}

function setPlayersHistoryAxis(axis) {
  if (!['count', 'date'].includes(axis) || !['general', 'comparison'].includes(view)) return;
  historyAxisMode[view] = axis;
  historyHover = null;
  renderPlayersHistoryGraphCanvas();
}

function historyRequestMetrics() {
  const catalog = historyMetricCatalog();
  const selected = [...historySelectedMetrics[view]];
  if (!selected.length) return [];
  if (view === 'comparison') return [selected[0]];
  const first = catalog.find(item => item.key === selected[0]);
  return first ? catalog.filter(item => item.group === first.group).map(item => item.key) : [];
}

function playersHistoryRequest(metricKeys) {
  return {
    ...params(),
    tournament_only: Boolean(document.getElementById('globalTournamentOnly')?.checked),
    players_history: true,
    players_history_metrics: metricKeys,
  };
}

function historyRequestCacheKey(request) {
  return JSON.stringify({
    ...request,
    maps: [...(request.maps || [])].sort(),
    players_arena_seasons: [...(request.players_arena_seasons || [])].sort(),
    players_history_metrics: [...(request.players_history_metrics || [])].sort(),
  });
}

async function ensurePlayersHistory() {
  const metricKeys = historyRequestMetrics();
  if (!metricKeys.length || !historyGraphView[view]) return;
  const targetView = view;
  const requestState = historyRequests[targetView];
  const request = playersHistoryRequest(metricKeys);
  const key = historyRequestCacheKey(request);
  if (historyPayload[targetView] && historyPayloadKey[targetView] === key) {
    requestState.loading = false;
    requestState.error = '';
    renderPlayersHistoryGraphStatus();
    return historyPayload[targetView];
  }
  // Legend rerenders can ask for the same compatibility group repeatedly.
  // Reuse that request instead of aborting it and subscribing to the same
  // already-cancelled promise through the shared filtered-request cache.
  if (requestState.pendingPromise && requestState.pendingKey === key) {
    return requestState.pendingPromise;
  }
  cancelHistoryRequest(targetView);
  const requestId = ++requestState.requestId;
  const controller = new AbortController();
  requestState.controller = controller;
  requestState.pendingKey = key;
  requestState.loading = true;
  requestState.error = '';
  requestState.timedOut = false;
  requestState.timeoutId = window.setTimeout(() => {
    if (requestState.requestId !== requestId || requestState.controller !== controller) return;
    requestState.timedOut = true;
    controller.abort();
  }, HISTORY_REQUEST_TIMEOUT_MS);
  renderPlayersHistoryGraphStatus();
  const pendingPromise = (async () => {
    try {
      // This request owns its abort signal. Do not reuse an in-flight promise
      // whose original caller may have cancelled its underlying fetch.
      const payload = await fetchStats(request, {
        signal: controller.signal,
        shareInFlight: false,
      });
      if (requestState.requestId !== requestId || requestState.controller !== controller) return null;
      if (payload?.players_history !== true || !Array.isArray(payload.metrics) || !Array.isArray(payload.players)) {
        throw new Error('History response has an invalid shape.');
      }
      historyPayload[targetView] = payload;
      historyPayloadKey[targetView] = key;
      requestState.loading = false;
      requestState.error = '';
      if (mounted && view === targetView && historyGraphView[targetView]) renderPlayersHistoryGraph();
      return payload;
    } catch (error) {
      if (requestState.requestId !== requestId || requestState.controller !== controller) return null;
      requestState.loading = false;
      requestState.error = requestState.timedOut
        ? 'The history request timed out.'
        : error?.name === 'AbortError' ? '' : publicPlayersError(error);
      if (mounted && view === targetView && historyGraphView[targetView]) renderPlayersHistoryGraphStatus();
      return null;
    } finally {
      if (requestState.requestId === requestId && requestState.controller === controller) {
        if (requestState.timeoutId !== null) window.clearTimeout(requestState.timeoutId);
        requestState.timeoutId = null;
        requestState.controller = null;
        requestState.pendingKey = '';
        requestState.pendingPromise = null;
        requestState.loading = false;
        requestState.timedOut = false;
        if (mounted && view === targetView && historyGraphView[targetView]) renderPlayersHistoryGraphStatus();
      }
    }
  })();
  requestState.pendingPromise = pendingPromise;
  return pendingPromise;
}

function cancelHistoryRequest(targetView, { clearError = true } = {}) {
  const requestState = historyRequests[targetView];
  if (!requestState) return;
  requestState.requestId += 1;
  if (requestState.timeoutId !== null) window.clearTimeout(requestState.timeoutId);
  requestState.timeoutId = null;
  requestState.controller?.abort();
  requestState.controller = null;
  requestState.pendingKey = '';
  requestState.pendingPromise = null;
  requestState.loading = false;
  requestState.timedOut = false;
  if (clearError) requestState.error = '';
}

function retryPlayersHistory() {
  if (!historyGraphView[view] || !['general', 'comparison'].includes(view)) return;
  historyRequests[view].error = '';
  renderPlayersHistoryGraphStatus();
  void ensurePlayersHistory();
}

function renderPlayersHistoryGraph() {
  const host = document.getElementById('playersContent');
  if (!host || !historyGraphView[view]) return;
  captureHistoryLegendState(view);
  updatePlayersMeta();
  host.innerHTML = `<div class="players-history-graph-shell">
    <div class="players-history-chart" id="playersHistoryChart">
      ${view === 'general' ? `<div class="players-history-player-heading">${escapeHtml(selectedPlayer || '')}</div>` : ''}
      <div class="players-arena-graph-tooltip" id="playersHistoryGraphTooltip" role="status" aria-live="polite"></div>
      <div class="players-history-chart-status" id="playersHistoryChartStatus"></div>
    </div>
    <aside class="players-history-legend">
      <button type="button" class="players-history-deselect" onclick="clearPlayersHistoryMetrics()">Deselect all</button>
      <div class="players-history-legend-list" id="playersHistoryLegendList"></div>
    </aside>
  </div>`;
  renderPlayersHistoryLegend();
  renderPlayersHistoryGraphCanvas();
  void ensurePlayersHistory();
}

function renderPlayersHistoryGraphStatus() {
  const host = document.getElementById('playersHistoryChartStatus');
  if (!host) return;
  const requestState = historyRequests[view];
  const selected = historySelectedMetrics[view].size;
  if (!selected) host.textContent = 'Select a metric from the legend.';
  else if (requestState.loading && requestState.controller) host.textContent = 'Loading rolling averages...';
  else if (requestState.error) {
    host.innerHTML = `<span>Could not load history: ${escapeHtml(requestState.error)}</span><button type="button" onclick="retryPlayersHistory()">Retry</button>`;
  }
  else host.textContent = '';
  host.classList.toggle('is-hidden', host.textContent === '');
}

function renderPlayersHistoryLegend() {
  const host = document.getElementById('playersHistoryLegendList');
  if (!host) return;
  if (host.childElementCount) captureHistoryLegendState(view);
  const catalog = historyMetricCatalog();
  const selected = historySelectedMetrics[view];
  const selectedList = catalog.filter(item => selected.has(item.key));
  const activeGroup = view === 'general' ? selectedList[0]?.group : null;
  host.innerHTML = catalog.map(metric => {
    const active = selected.has(metric.key);
    const compatible = view === 'general' && Boolean(activeGroup) && metric.group === activeGroup;
    const muted = view === 'comparison'
      ? selected.size > 0 && !active
      : Boolean(activeGroup) && !compatible;
    const dotColor = active
      ? view === 'comparison' ? HISTORY_COMPARISON_METRIC_COLOR : historyMetricColor(metric.key, catalog)
      : compatible ? '#ffffff' : 'transparent';
    return `<button type="button" class="players-history-legend-item ${active ? 'active' : ''} ${muted ? 'incompatible' : ''}" data-metric="${escapeAttr(metric.key)}" onpointerdown="prepareHistoryLegendSelection()" onmousedown="event.preventDefault()" onclick="togglePlayersHistoryMetric(this.dataset.metric)"><span class="players-history-metric-dot" style="background:${dotColor}"></span><span>${escapeHtml(metric.label)}</span></button>`;
  }).join('');
  restoreHistoryLegendState(view);
}

function svgPathForHistory(points) {
  let path = '';
  let drawing = false;
  points.forEach(point => {
    if (!Number.isFinite(point.value) || !Number.isFinite(point.x) || !Number.isFinite(point.y)) {
      drawing = false;
      return;
    }
    path += `${drawing ? ' L' : ' M'} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`;
    drawing = true;
  });
  return path.trim();
}

function historyDateLabel(timestamp) {
  return new Date(timestamp).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: '2-digit' });
}

function historyGameCount(player) {
  const explicit = Number(player?.game_count);
  if (Number.isFinite(explicit) && explicit > 0) return explicit;
  const gameNumbers = (player?.game_numbers || []).map(Number).filter(Number.isFinite);
  return gameNumbers.length ? Math.max(...gameNumbers) : 0;
}

function uniqueHistoryTicks(values) {
  return values
    .filter(Number.isFinite)
    .sort((a, b) => a - b)
    .filter((value, index, sorted) => index === 0 || Math.abs(value - sorted[index - 1]) > 1e-7);
}

function historyYAxisLabel(value, isPercent, isReference = false) {
  const rounded = Math.round(value);
  const text = isReference || Math.abs(value - rounded) < 1e-7
    ? String(rounded)
    : Math.abs(value) >= 100 ? value.toFixed(0) : value.toFixed(1);
  return isPercent ? `${text}%` : text;
}

function historyYAxisScale(yMin, yMax, referenceValue, count = 6) {
  if (!Number.isFinite(referenceValue) || referenceValue <= yMin || referenceValue >= yMax) {
    return {
      min: yMin,
      max: yMax,
      ticks: Array.from({ length: count }, (_, index) => yMin + (yMax - yMin) * index / (count - 1)),
    };
  }
  // Anchor the complete scale on the gameplay reference. Every candidate uses
  // one common numeric step; choose the allocation that covers the data with
  // the least added padding. This makes 30 Turns / 50% genuine, equidistant
  // ticks instead of extra lines inserted into an unrelated scale.
  const intervals = count - 1;
  let best = null;
  for (let below = 1; below < intervals; below += 1) {
    const above = intervals - below;
    const step = Math.max((referenceValue - yMin) / below, (yMax - referenceValue) / above);
    const min = referenceValue - below * step;
    const max = referenceValue + above * step;
    const padding = (yMin - min) + (max - yMax);
    if (!best || padding < best.padding) best = { below, above, step, min, max, padding };
  }
  const ticks = Array.from(
    { length: count },
    (_, index) => referenceValue + (index - best.below) * best.step,
  );
  return { min: best.min, max: best.max, ticks };
}

function renderPlayersHistoryGraphCanvas() {
  const host = document.getElementById('playersHistoryChart');
  if (!host) return;
  renderPlayersHistoryGraphStatus();
  const selectedMetrics = [...historySelectedMetrics[view]];
  const payload = historyPayload[view];
  const requestKey = selectedMetrics.length ? historyRequestCacheKey(playersHistoryRequest(historyRequestMetrics())) : '';
  const usable = payload && historyPayloadKey[view] === requestKey;
  host.querySelector('svg')?.remove();
  host.querySelector('.players-history-axis-footer')?.remove();
  host.querySelector('.players-history-player-key')?.remove();
  if (!selectedMetrics.length || !usable) return;
  const width = 900; const height = 430;
  const margin = { left: 64, right: 25, top: 24, bottom: 42 };
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  const metricMap = new Map((payload.metrics || []).map(item => [item.key, item]));
  const catalog = historyMetricCatalog();
  const series = [];
  if (view === 'general') {
    const player = payload.players?.[0];
    selectedMetrics.forEach(metricKey => {
      const values = player?.series?.[metricKey] || [];
      series.push({
        id: metricKey, label: metricMap.get(metricKey)?.label || metricKey,
        format: metricMap.get(metricKey)?.format || 'number',
        color: historyMetricColor(metricKey, catalog),
        gameCount: historyGameCount(player),
        gameNumbers: player?.game_numbers || [], timestamps: player?.timestamps || [], values,
      });
    });
  } else {
    const metricKey = selectedMetrics[0];
    (payload.players || []).forEach((player, index) => series.push({
      id: player.name, label: player.name,
      format: metricMap.get(metricKey)?.format || 'number',
      color: HISTORY_LINE_COLORS[index % HISTORY_LINE_COLORS.length],
      gameCount: historyGameCount(player),
      gameNumbers: player.game_numbers || [], timestamps: player.timestamps || [],
      values: player.series?.[metricKey] || [],
    }));
  }
  const useDate = historyAxisMode[view] === 'date';
  const allY = series.flatMap(item => item.values.map(Number)).filter(Number.isFinite);
  if (!allY.length) return;
  let xMin; let xMax;
  if (useDate) {
    const allX = series.flatMap(item => item.timestamps.map(Date.parse)).filter(Number.isFinite);
    if (!allX.length) return;
    xMin = Math.min(...allX); xMax = Math.max(...allX);
  } else {
    const maxGameCount = Math.max(...series.map(item => item.gameCount).filter(Number.isFinite), 1);
    xMin = -maxGameCount; xMax = 0;
  }
  const isPercent = series.length > 0 && series.every(item => item.format === 'percent');
  const referenceValue = selectedMetrics.includes('turns')
    ? 30
    : selectedMetrics.includes('break_pct') ? 50 : null;
  let domainMin = Math.min(...allY); let domainMax = Math.max(...allY);
  if (Number.isFinite(referenceValue)) {
    domainMin = Math.min(domainMin, referenceValue);
    domainMax = Math.max(domainMax, referenceValue);
  }
  if (xMax <= xMin) xMax = xMin + 1;
  let yMin; let yMax;
  if (isPercent) {
    domainMin = Math.max(0, Math.min(100, domainMin));
    domainMax = Math.max(0, Math.min(100, domainMax));
    const yPad = Math.max((domainMax - domainMin) * .08, Math.abs(domainMax || 1) * .02, .1);
    yMin = Math.min(...allY) < 20 ? 0 : Math.max(0, domainMin - yPad);
    yMax = Math.min(100, domainMax + yPad);
  } else {
    const yPad = Math.max((domainMax - domainMin) * .08, Math.abs(domainMax || 1) * .02, .1);
    yMin = domainMin - yPad; yMax = domainMax + yPad;
  }
  if (yMax <= yMin) {
    if (isPercent && yMin >= 100) { yMin = 99; yMax = 100; }
    else yMax = isPercent ? Math.min(100, yMin + 1) : yMin + 1;
  }
  const referenceScale = historyYAxisScale(yMin, yMax, referenceValue, referenceValue === 50 ? 7 : 6);
  yMin = referenceScale.min;
  yMax = referenceScale.max;
  if (isPercent) { yMin = Math.max(0, yMin); yMax = Math.min(100, yMax); }
  const x = value => margin.left + ((value - xMin) / (xMax - xMin)) * innerWidth;
  const labeledYMax = yMax;
  // When percentages reach their natural 100% ceiling, reserve an unlabeled
  // 12% visual gutter above the 100% gridline. A proportional pixel gutter is
  // stable even for a narrow 93-100 range, where a literal 110% domain would
  // otherwise waste most of the chart. The ceiling remains the final label.
  const scaledYMax = isPercent && labeledYMax >= 100 - 1e-7
    ? yMin + (labeledYMax - yMin) / .88
    : labeledYMax;
  const y = value => margin.top + (1 - (value - yMin) / (scaledYMax - yMin)) * innerHeight;
  const yTicks = uniqueHistoryTicks(referenceScale.ticks.filter(value => value >= yMin - 1e-7 && value <= labeledYMax + 1e-7));
  const xTicks = Array.from({ length: 5 }, (_, index) => xMin + (xMax - xMin) * index / 4);
  const grid = yTicks.map(value => {
    const isReference = Number.isFinite(referenceValue) && Math.abs(value - referenceValue) < 1e-7;
    return `<g><line class="${isReference ? 'players-history-reference-grid' : ''}" x1="${margin.left}" y1="${y(value)}" x2="${width - margin.right}" y2="${y(value)}"/><text x="${margin.left - 9}" y="${y(value) + 4}" text-anchor="end">${historyYAxisLabel(value, isPercent, isReference)}</text></g>`;
  }).join('');
  const xGrid = xTicks.map(value => `<g><line x1="${x(value)}" y1="${margin.top}" x2="${x(value)}" y2="${height - margin.bottom}"/><text x="${x(value)}" y="${height - 18}" text-anchor="middle">${useDate ? historyDateLabel(value) : Math.round(value).toLocaleString('en-US')}</text></g>`).join('');
  const plotted = series.map(item => ({
    ...item,
    points: item.values.map((raw, index) => {
      const value = finiteNumber(raw);
      const gameNumber = Number(item.gameNumbers[index]);
      const rawX = useDate ? Date.parse(item.timestamps[index]) : gameNumber - item.gameCount;
      return { value, rawX, x: Number.isFinite(rawX) ? x(rawX) : Number.NaN, y: Number.isFinite(value) ? y(value) : Number.NaN };
    }),
  }));
  const paths = plotted.map(item => `<path class="players-history-line" data-series="${escapeAttr(item.id)}" d="${svgPathForHistory(item.points)}" stroke="${item.color}"></path>`).join('');
  const svgMarkup = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Trailing 100-game rolling averages" onmousemove="onPlayersHistoryGraphMove(event)" onmouseleave="clearPlayersHistoryGraphHover()"><defs><clipPath id="playersHistoryPlotClip"><rect x="${margin.left}" y="${margin.top}" width="${innerWidth}" height="${innerHeight}"/></clipPath></defs><g class="players-arena-grid">${grid}${xGrid}</g><line class="players-arena-axis" x1="${margin.left}" y1="${height - margin.bottom}" x2="${width - margin.right}" y2="${height - margin.bottom}"/><line class="players-arena-axis" x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${height - margin.bottom}"/><g clip-path="url(#playersHistoryPlotClip)">${paths}</g><text class="players-arena-axis-title" transform="translate(15 ${height / 2}) rotate(-90)" text-anchor="middle">Value</text></svg>`;
  const playerHeading = host.querySelector('.players-history-player-heading');
  if (playerHeading) playerHeading.insertAdjacentHTML('afterend', svgMarkup);
  else host.insertAdjacentHTML('afterbegin', svgMarkup);
  host.insertAdjacentHTML('beforeend', `<div class="players-history-axis-footer"><div class="players-history-axis-modes"><span>Rolling average over 100 games (</span><button type="button" class="${useDate ? '' : 'active'}" onclick="setPlayersHistoryAxis('count')">by game count</button><span> / </span><button type="button" class="${useDate ? 'active' : ''}" onclick="setPlayersHistoryAxis('date')">by date</button><span>)</span></div></div>`);
  if (view === 'comparison') {
    host.insertAdjacentHTML('beforeend', `<div class="players-history-player-key">${plotted.map(item => `<span><i style="background:${item.color}"></i>${escapeHtml(item.label)}</span>`).join('')}</div>`);
  }
  historyRenderState = { series: new Map(plotted.map(item => [item.id, item])) };
  updatePlayersHistoryHoverLabel();
}

function nearestHistoryPoint(points, targetX) {
  let best = null;
  (points || []).forEach(point => {
    if (!Number.isFinite(point.x) || !Number.isFinite(point.value)) return;
    if (!best || Math.abs(point.x - targetX) < Math.abs(best.x - targetX)) best = point;
  });
  return best;
}

function onPlayersHistoryGraphMove(event) {
  const svg = event.currentTarget;
  const line = event.target?.closest?.('.players-history-line');
  if (!svg || !line || !historyRenderState) { clearPlayersHistoryGraphHover(); return; }
  const matrix = svg.getScreenCTM?.();
  if (!matrix) return;
  const pointer = svg.createSVGPoint(); pointer.x = event.clientX; pointer.y = event.clientY;
  const svgPointer = pointer.matrixTransform(matrix.inverse());
  const item = historyRenderState.series.get(line.dataset.series);
  const point = nearestHistoryPoint(item?.points, svgPointer.x);
  if (!point || !item) return;
  historyHover = { value: point.value, format: item.format, clientX: event.clientX, clientY: event.clientY };
  updatePlayersHistoryHoverLabel();
}

function clearPlayersHistoryGraphHover() { historyHover = null; updatePlayersHistoryHoverLabel(); }

function updatePlayersHistoryHoverLabel() {
  const host = document.getElementById('playersHistoryChart');
  const tip = document.getElementById('playersHistoryGraphTooltip');
  if (!host || !tip) return;
  if (!historyHover) { tip.classList.remove('visible'); return; }
  tip.textContent = formatValue(historyHover.value, historyHover.format);
  tip.classList.add('visible');
  const rect = host.getBoundingClientRect();
  const left = historyHover.clientX - rect.left - tip.offsetWidth / 2;
  const top = historyHover.clientY - rect.top - tip.offsetHeight - 8;
  tip.style.left = `${Math.max(8, Math.min(rect.width - tip.offsetWidth - 8, left))}px`;
  tip.style.top = `${Math.max(4, top)}px`;
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
  const seasonStart = Date.parse(data.start_utc);
  const officialSeasonEnd = Date.parse(data.end_utc);
  const effectiveSeasonEnd = Date.parse(data.effective_end_utc || data.end_utc);
  const dayMs = 24 * 60 * 60 * 1000;
  const maxDay = arenaSeasonDayCount(data);
  const start = seasonStart + (arenaGraphDayStart - 1) * dayMs;
  // Day numbering follows the official season interval. The final day extends
  // through the backend's two-hour completion grace so late-finishing games
  // remain visible without creating an extra numbered day in the UI.
  const end = arenaGraphDayEnd >= maxDay
    ? effectiveSeasonEnd
    : Math.min(officialSeasonEnd, seasonStart + arenaGraphDayEnd * dayMs);
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
  const plottedSeries = selectedPoints.map(({ item, points }) => ({
    item,
    points: points.map(point => ({ ...point, x: x(point.time), y: y(point.rating) })),
  }));
  const lines = plottedSeries.map(({ item, points }, index) => {
    const path = points.map((point, pointIndex) => `${pointIndex ? 'L' : 'M'} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(' ');
    const color = ARENA_LINE_COLORS[index % ARENA_LINE_COLORS.length];
    return path ? `<path class="players-arena-rating-line" d="${path}" stroke="${color}" data-player="${escapeAttr(item.player)}"></path>` : '';
  }).join('');
  host.querySelector('svg')?.remove();
  host.querySelector('.players-arena-empty-chart')?.remove();
  host.insertAdjacentHTML('afterbegin', `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Arena rating progression for selected players" onmousemove="onPlayersArenaGraphMove(event)" onmouseleave="clearPlayersArenaGraphHover()"><g class="players-arena-grid">${grid}${dates}</g><line class="players-arena-axis" x1="${margin.left}" y1="${height - margin.bottom}" x2="${width - margin.right}" y2="${height - margin.bottom}"/><line class="players-arena-axis" x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${height - margin.bottom}"/>${lines}<text class="players-arena-axis-title" transform="translate(15 ${height / 2}) rotate(-90)" text-anchor="middle">Arena rating</text></svg>${selected.length ? '' : '<div class="players-arena-empty-chart">Select up to five players from the legend.</div>'}`);
  arenaGraphRenderState = {
    pointsByPlayer: new Map(plottedSeries.map(entry => [entry.item.player, entry.points])),
  };
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

function nearestArenaPoint(points, targetX) {
  let best = null;
  (points || []).forEach(point => {
    if (!Number.isFinite(point.x) || !Number.isFinite(point.rating)) return;
    if (!best || Math.abs(point.x - targetX) < Math.abs(best.x - targetX)) best = point;
  });
  return best;
}

function onPlayersArenaGraphMove(event) {
  const data = currentArenaSeasonData();
  const svg = event.currentTarget;
  if (!data || !svg || !arenaGraphRenderState) return;
  const line = event.target?.closest?.('.players-arena-rating-line');
  if (!line) {
    clearPlayersArenaGraphHover();
    return;
  }
  const screenMatrix = svg.getScreenCTM?.();
  if (!screenMatrix) return;
  const pointer = svg.createSVGPoint();
  pointer.x = event.clientX;
  pointer.y = event.clientY;
  const svgPointer = pointer.matrixTransform(screenMatrix.inverse());
  // Use the exact points used to draw this line. This avoids both CSS/viewBox
  // scaling drift and selecting an off-screen observation outside Day X-Y.
  const points = arenaGraphRenderState.pointsByPlayer.get(line.dataset.player) || [];
  const point = nearestArenaPoint(points, svgPointer.x);
  if (!point) return;
  arenaGraphHover = {
    time: point.time,
    rating: point.rating,
    clientX: event.clientX,
    clientY: event.clientY,
  };
  updateArenaGraphHoverLabel();
}

function clearPlayersArenaGraphHover() {
  arenaGraphHover = null;
  updateArenaGraphHoverLabel();
}

function updateArenaGraphHoverLabel() {
  const host = document.getElementById('playersArenaChart');
  const tooltip = document.getElementById('playersArenaGraphTooltip');
  if (!host || !tooltip) return;
  if (!arenaGraphHover) {
    tooltip.classList.remove('visible');
    return;
  }
  tooltip.textContent = wholeOrDash(arenaGraphHover.rating);
  tooltip.classList.add('visible');
  const chartRect = host.getBoundingClientRect();
  const left = arenaGraphHover.clientX - chartRect.left - (tooltip.offsetWidth / 2);
  const top = arenaGraphHover.clientY - chartRect.top - tooltip.offsetHeight - 8;
  tooltip.style.left = `${Math.max(8, Math.min(chartRect.width - tooltip.offsetWidth - 8, left))}px`;
  tooltip.style.top = `${Math.max(4, top)}px`;
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
  const graph = document.querySelector('.players-history-graph-shell');
  if (graph && historyGraphView[view]) {
    graph.classList.add('players-updating');
    updatePlayersMeta();
    return;
  }
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
document.addEventListener('mouseover', event => { if (!mounted || !tooltip) return; const source = event.target.closest?.('.players-value-cell, .players-performance-value, .col-tip, .maps-custom-tip'); if (!source || !source.dataset.tip) return; tooltip.textContent = source.dataset.tip; tooltip.style.display = 'block'; tooltip.style.left = `${Math.max(8, Math.min(event.clientX + 12, window.innerWidth - tooltip.offsetWidth - 8))}px`; tooltip.style.top = `${event.clientY + 18}px`; });
document.addEventListener('mouseout', event => { if (mounted && tooltip && event.target.closest?.('.players-value-cell, .players-performance-value, .col-tip, .maps-custom-tip')) tooltip.style.display = 'none'; });
document.addEventListener('click', event => {
  if (!mounted) return;
  const option = event.target.closest?.('.players-suggestions button[data-player]');
  if (option) { selectPlayer(option.dataset.player, activeSearchSlot); return; }
  if (!event.target.closest?.('.players-search-wrap, .players-suggestions')) closeSuggestions();
});
document.addEventListener('scroll', () => { if (mounted) positionSuggestions(); }, true);
window.addEventListener('resize', () => { if (mounted) positionSuggestions(); });
document.addEventListener('keydown', event => {
  if (!mounted || event.key !== 'Escape') return;
  const modal = document.getElementById('playersHistoryModal');
  if (modal && !modal.hidden) {
    event.preventDefault();
    closePlayersHistoryModal();
  }
});
