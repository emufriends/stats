import { divergingRangeColor } from '../color-scales.js?v=20260711-1';
import { fetchStats, loadSnapshot, loadStats } from '../snapshot-cache.js?v=20260713-1';

export const id = 'players';
export const title = 'Players';
export const navLabel = 'Players';

const API_ROOT = 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/players';
const API_URL = 'https://europe-west1-ark-nova-stats-dashboard.cloudfunctions.net/get-card-stats';
const INDEX_URL = dataset => `${API_ROOT}/index/default-${dataset ? 'mw' : 'base'}.json`;
const SNAPSHOT_URL = dataset => `${API_ROOT}/general/default-${dataset ? 'mw' : 'base'}.json`;
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
  </div>
  <div class="attributes-bar endgames-tabs-bar players-tabs-bar">
    <div class="attributes-bar-header endgames-tabs-header">
      <div class="endgames-tabs players-tabs" role="tablist" aria-label="Players views">
        <button class="endgames-tab active" data-view="general" onclick="setPlayersView('general')">General</button>
        <button class="endgames-tab" data-view="comparison" onclick="setPlayersView('comparison')">Comparison</button>
        <button class="endgames-tab" data-view="arena" onclick="setPlayersView('arena')">Arena</button>
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
  Object.assign(window, {
    setPlayersView, resetPlayersFilters, applyPlayersFilters,
    selectAllPlayersMaps, selectNonePlayersMaps, togglePlayersMap,
    onPlayersDateInput, onPlayersLastInput, selectPlayer,
    onPlayersSearchInput, clearPlayersSearch, retryPlayersIndex,
  });
  renderMapChips();
  syncTabs();
  syncDateLastControls();
  loadPlayerIndex();
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
}

export function setDataset(value) {
  isMW = Number(value) === 0 ? 0 : 1;
  selectedPlayer = null;
  selectedPlayers = [];
  comparisonCounts = [];
  playerGameCount = 0;
  playerNames = [];
  playerIndexState = 'idle';
  playerIndexError = '';
  loadPlayerIndex();
  loadData(++token);
}

function setPlayersView(next) {
  view = ['general', 'comparison', 'arena'].includes(next) ? next : 'general';
  closeSuggestions();
  syncTabs();
  loadData(++token);
}

function syncTabs() {
  document.querySelectorAll('.players-tabs .endgames-tab').forEach(button => {
    button.classList.toggle('active', button.dataset.view === view);
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
    maps: selectedMaps,
    opponent_elo_min: value('playersOpponentEloMin') === '' ? 0 : Number(value('playersOpponentEloMin')),
    opponent_elo_max: value('playersOpponentEloMax') === '' ? null : Number(value('playersOpponentEloMax')),
    date_from: dateFromInput?.disabled ? null : (value('playersDateFrom') || null),
    date_to: dateToInput?.disabled ? null : (value('playersDateTo') || null),
    players_player: view === 'general' ? selectedPlayer : null,
    players_players: view === 'comparison' ? selectedPlayers : [],
    last_x_games: last === '' ? null : Number(last),
  };
}

function isDefault(request) {
  return view === 'general' && !selectedPlayer && request.last_x_games === null
    && request.opponent_elo_min === 0 && request.opponent_elo_max === null
    && request.date_from === null && request.date_to === null
    && selectedMaps.length === MAPS.length;
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
  if (view === 'arena') {
    statsAbortController?.abort();
    statsLoading = false;
    document.getElementById('playersContent').innerHTML = '<div class="build-placeholder players-placeholder"><h2>Arena</h2><p>This Players view is reserved for a future update.</p></div>';
    updatePlayersMeta();
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
  selectedMaps = MAPS.map(([, full]) => full);
  renderMapChips(); syncDateLastControls(); loadData(++token);
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
  const excluded = new Set([...selectedPlayers, selectedPlayer].filter(Boolean));
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
