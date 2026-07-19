import { loadSnapshot, fetchStats } from '../snapshot-cache.js?v=20260719-1';
import { mapTooltipLabel } from '../table-cells.js?v=20260712-4';

export const id = 'records';
export const title = 'Records';
export const navLabel = 'Records';

const API_ROOT = 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/records';
const API_VIEWS = {
  elo_leaderboard: 'elo-leaderboard',
  fastest_games: 'fastest-games',
  highest_scores: 'highest-scores',
  biggest_turns: 'biggest-turns',
  most_icons: 'most-icons',
};
const STANDARD_MAPS = [
  ['1a', 'Map 1a: Observation Tower'], ['2a', 'Map 2a: Outdoor Areas'],
  ['3a', 'Map 3a: Silver Lake'], ['4a', 'Map 4a: Commercial Harbor'],
  ['5a', 'Map 5a: Park Restaurant'], ['6a', 'Map 6a: Research Institute'],
  ['7a', 'Map 7a: Ice Cream Parlors'], ['8a', 'Map 8a: Hollywood Hills'],
  ['9', 'Map 9: Geographical Zoo'], ['10', 'Map 10: Rescue Station'],
  ['11', 'Map 11: Caves'], ['12', 'Map 12: Artificial Intelligence'],
  ['13', 'Map 13: Drawing Board'], ['14', 'Map 14: Lagoon'], ['T1', 'Map T1: Tournament 1'],
];
const LEGACY_MAPS = [
  ['1', 'Map 1: Observation Tower'], ['2', 'Map 2: Outdoor Areas'],
  ['3', 'Map 3: Silver Lake'], ['4', 'Map 4: Commercial Harbor'],
  ['5', 'Map 5: Park Restaurant'], ['6', 'Map 6: Research Institute'],
  ['7', 'Map 7: Ice Cream Parlors'], ['8', 'Map 8: Hollywood Hills'],
];
const BEGINNER_MAPS = [['A', 'Map A'], ['0', 'Map 0']];
const DEFAULT_MAPS = [...STANDARD_MAPS, ...LEGACY_MAPS];
const MAP_GROUPS = [
  ['regular', 'Regular maps', STANDARD_MAPS],
  ['legacy', 'Legacy maps', LEGACY_MAPS],
  ['beginner', 'Beginner maps', BEGINNER_MAPS],
];
const ICON_ASSETS = {
  Birds: 'bird.png', Herbivores: 'herbivore.png', Predators: 'predator.png',
  Primates: 'primate.png', Reptiles: 'reptile.png', 'Sea Animals': 'sea-animal.png',
  Africa: 'africa.png', Americas: 'americas.png', Asia: 'asia.png',
  Australia: 'australia.png', Europe: 'europe.png', Rock: 'rock.png',
  Water: 'water.png', Science: 'science.png',
};
const ICON_GROUPS = [
  ['Species', ['Birds', 'Herbivores', 'Predators', 'Primates', 'Reptiles', 'Sea Animals']],
  ['Habitat', ['Africa', 'Americas', 'Asia', 'Australia', 'Europe']],
  ['Other', ['Rock', 'Water', 'Science']],
];
const ALL_ICON_TYPES = ICON_GROUPS.flatMap(([, icons]) => icons);
const VIEWS = {
  elo_leaderboard: 'Elo leaderboard',
  fastest_games: 'Fastest games',
  highest_scores: 'Highest scores',
  biggest_turns: 'Biggest turns',
  most_icons: 'Most icons',
};

export const mainHtml = `
  <div class="main-header records-main-header">
    <div class="table-meta" id="recordsMeta"></div>
    <div class="main-controls">
      <div class="rpp-wrap"><span>Rows</span><select class="rpp-select" id="recordsRowsPerPage" onchange="setRecordsRows(this.value)">
        <option value="25">25</option><option value="50" selected>50</option><option value="100">100</option><option value="9999">All</option>
      </select></div>
    </div>
  </div>
  <div class="attributes-bar endgames-tabs-bar records-tabs-bar">
    <div class="attributes-bar-header endgames-tabs-header"><div class="endgames-tabs records-tabs" role="tablist" aria-label="Records views">
      ${Object.entries(VIEWS).map(([view, label], index) => `<button class="endgames-tab${index === 0 ? ' active' : ''}" type="button" data-view="${view}" onclick="setRecordsView('${view}')">${label}</button>`).join('')}
    </div></div>
  </div>
  <div class="table-wrap records-table-wrap"><div class="table-scroll"><table id="recordsTable" class="records-table"><thead id="recordsHead"></thead><tbody id="recordsBody"><tr><td colspan="8"><div class="state-overlay"><div class="spinner"></div><div class="state-title">Fetching records...</div></div></td></tr></tbody></table></div><div class="pagination" id="recordsPagination" style="display:none;"></div></div>`;

export const sidebarHtml = `
  <div class="sidebar-header"><span class="sidebar-title">Filters</span><div style="display:flex;align-items:center;gap:6px;"><button class="reset-btn" onclick="resetFilters()">Reset</button><button class="sidebar-close-btn" onclick="toggleSidebar()" title="Close filters">x</button></div></div>
  <hr class="divider" />
  <div class="filter-group"><span class="filter-label">Opponent ELO</span><div class="range-row"><input class="range-input" type="number" id="opponentEloMin" placeholder="Min" value="300" min="0" /><input class="range-input" type="number" id="opponentEloMax" placeholder="Max" min="0" /></div></div>
  <hr class="divider" />
  <div class="records-map-filter" id="recordsMapFilter"></div>
  <hr class="divider" />
  <div class="filter-group"><span class="filter-label">Date Range</span><input class="date-input" type="text" inputmode="numeric" pattern="\\d{4}-\\d{2}-\\d{2}" placeholder="yyyy-mm-dd" id="recordsDateFrom" /><input class="date-input" type="text" inputmode="numeric" pattern="\\d{4}-\\d{2}-\\d{2}" placeholder="yyyy-mm-dd" id="recordsDateTo" /></div>
  <hr class="divider" />
  <div class="filter-group records-mode-filters"><div class="toggle-row"><span class="toggle-label">Arena games only</span><label class="toggle"><input type="checkbox" id="recordsArenaOnly" onchange="onRecordsModeChange('arena')" /><span class="toggle-track"></span></label></div><div class="toggle-row"><span class="toggle-label">Tournament games only</span><label class="toggle"><input type="checkbox" id="recordsTournamentOnly" onchange="onRecordsModeChange('tournament')" /><span class="toggle-track"></span></label></div></div>
  <hr class="divider" /><div class="filter-action-stack"><button class="apply-btn" id="applyBtn" onclick="applyFiltersFromSidebar()">Apply filters</button></div>`;

let mounted = false;
let isMW = 1;
let view = 'elo_leaderboard';
let selectedMaps = DEFAULT_MAPS.map(([, full]) => full);
let selectedPlayer = '';
let playerSearch = '';
let playerIndex = null;
let playerIndexLoading = false;
let playerIndexError = '';
let rows = [];
let rowsPerPage = 50;
let currentPage = 1;
let iconFilterOpen = false;
let selectedIconTypes = new Set(ALL_ICON_TYPES);
let requestToken = 0;
let requestController = null;
const snapshotRows = new Map();

const handlers = {
  setRecordsView, applyFiltersFromSidebar, resetFilters, toggleRecordsMap,
  selectAllRecordsMaps, selectNoneRecordsMaps, onRecordsModeChange,
  onRecordsPlayerInput, selectRecordsPlayer, clearRecordsPlayer,
  toggleRecordsPlayerSearch, toggleRecordsIconFilter, toggleRecordsIconType,
  selectAllRecordsIcons, selectNoneRecordsIcons, setRecordsRows, goRecordsPage,
};

export function mount({ dataset = 1 } = {}) {
  Object.assign(window, handlers);
  mounted = true;
  isMW = Number(dataset) === 0 ? 0 : 1;
  view = 'elo_leaderboard';
  selectedMaps = DEFAULT_MAPS.map(([, full]) => full);
  selectedPlayer = '';
  playerSearch = '';
   iconFilterOpen = false;
  selectedIconTypes = new Set(ALL_ICON_TYPES);
  rowsPerPage = 50;
  currentPage = 1;
  rows = [];
  renderTabs();
  renderMapFilter();
  renderHead();
  renderPlayerSearch();
  loadRecords(++requestToken);
}

export function unmount() {
  mounted = false;
  requestToken += 1;
  requestController?.abort();
  requestController = null;
  document.getElementById('recordsPlayerSuggestions')?.remove();
  document.getElementById('recordsIconFilterPopup')?.remove();
  hideRecordsTooltip();
}

export function setDataset(dataset) {
  isMW = Number(dataset) === 0 ? 0 : 1;
  // The Elo Leaderboard is sourced from one dataset-neutral Masters sheet.
  // Keep the visible table stable when the global MW/Base switch changes.
  if (view === 'elo_leaderboard' && rows.length) {
    renderHead();
    renderBody();
    return;
  }
  loadRecords(++requestToken);
}

function renderTabs() {
  document.querySelectorAll('.records-tabs .endgames-tab').forEach(button => {
    button.classList.toggle('active', button.dataset.view === view);
  });
}

function setRecordsView(next) {
  if (!VIEWS[next]) return;
  view = next;
  currentPage = 1;
  iconFilterOpen = false;
  document.getElementById('recordsIconFilterPopup')?.remove();
  renderTabs();
  renderHead();
  renderPlayerSearch();
  if (view === 'elo_leaderboard') {
    rows = [];
    renderBody();
  }
  loadRecords(++requestToken);
}

function renderMapFilter() {
  const host = document.getElementById('recordsMapFilter');
  if (!host) return;
  host.innerHTML = MAP_GROUPS.map(([id, label, maps]) => `<div class="filter-group records-map-group"><div class="records-filter-heading"><span class="filter-label">${label}</span><span class="map-select-all-none">(<span class="map-toggle-link" onclick="selectAllRecordsMaps('${id}')">all</span> / <span class="map-toggle-link" onclick="selectNoneRecordsMaps('${id}')">none</span>)</span></div><div class="chip-grid records-map-chips">${maps.map(([code, full]) => `<button type="button" class="chip records-map-chip ${selectedMaps.includes(full) ? 'active' : ''}" data-map="${escapeAttr(full)}" data-group="${id}" onclick="toggleRecordsMap(this.dataset.map)">${code}</button>`).join('')}</div></div>`).join('');
}

function toggleRecordsMap(map) {
  selectedMaps = selectedMaps.includes(map) ? selectedMaps.filter(item => item !== map) : [...selectedMaps, map];
  renderMapFilter();
}

function selectAllRecordsMaps(groupId) {
  const group = MAP_GROUPS.find(([id]) => id === groupId);
  if (!group) return;
  selectedMaps = [...new Set([...selectedMaps, ...group[2].map(([, full]) => full)])];
  renderMapFilter();
}

function selectNoneRecordsMaps(groupId) {
  const group = MAP_GROUPS.find(([id]) => id === groupId);
  if (!group) return;
  const excluded = new Set(group[2].map(([, full]) => full));
  selectedMaps = selectedMaps.filter(item => !excluded.has(item));
  renderMapFilter();
}

function onRecordsModeChange(which) {
  const arena = document.getElementById('recordsArenaOnly');
  const tournament = document.getElementById('recordsTournamentOnly');
  if (which === 'arena' && arena?.checked && tournament) tournament.checked = false;
  if (which === 'tournament' && tournament?.checked && arena) arena.checked = false;
}

function renderPlayerSearchMarkup() {
  return `<div class="records-player-search records-player-search-open"><span class="records-search-icon" aria-hidden="true">&#128269;</span><input id="recordsPlayerSearch" type="search" value="${escapeAttr(playerSearch)}" placeholder="Search player" autocomplete="off" oninput="onRecordsPlayerInput(this.value)" aria-label="Search player" />${selectedPlayer ? '<button type="button" class="records-search-clear" onclick="clearRecordsPlayer()" aria-label="Clear player">&times;</button>' : ''}</div>`;
}

function renderIconFilterMarkup() {
  const allSelected = selectedIconTypes.size === ALL_ICON_TYPES.length;
  const indicator = allSelected ? '<span class="type-filter-indicator type-filter-icon" aria-hidden="true"></span>' : `<span class="records-type-filter-count">${selectedIconTypes.size}/${ALL_ICON_TYPES.length}</span>`;
  return `<div class="records-icon-filter-wrap"><button id="recordsIconFilterButton" type="button" class="records-icon-filter-button${allSelected ? '' : ' active'}" onclick="toggleRecordsIconFilter(event)" aria-label="Filter icon types" aria-expanded="${iconFilterOpen}">TYPE ${indicator}</button></div>`;
}

function renderIconFilterPopup() {
  document.getElementById('recordsIconFilterPopup')?.remove();
  if (!iconFilterOpen || view !== 'most_icons') return;
  const popup = document.createElement('div');
  popup.id = 'recordsIconFilterPopup';
  popup.className = 'records-icon-filter-popup open';
  popup.innerHTML = `<div class="records-icon-filter-actions"><span class="map-toggle-link" onclick="selectAllRecordsIcons()">all</span> / <span class="map-toggle-link" onclick="selectNoneRecordsIcons()">none</span></div>${ICON_GROUPS.map(([, icons]) => `<div class="records-icon-filter-icons">${icons.map(icon => `<button type="button" class="attribute-icon-chip records-icon-filter-chip${selectedIconTypes.has(icon) ? ' active' : ''}" data-type="${escapeAttr(icon)}" data-tip="${escapeAttr(icon)}" onclick="toggleRecordsIconType(this.dataset.type)" aria-label="${escapeAttr(icon)}" aria-pressed="${selectedIconTypes.has(icon)}"><img src="assets/img/icons/${ICON_ASSETS[icon]}" alt="" /></button>`).join('')}</div>`).join('')}`;
  document.body.appendChild(popup);
  positionIconFilterPopup();
}

function positionIconFilterPopup() {
  const popup = document.getElementById('recordsIconFilterPopup');
  const button = document.getElementById('recordsIconFilterButton');
  const frame = document.querySelector('.records-table-wrap');
  if (!popup || !button || !frame) return;
  const buttonRect = button.getBoundingClientRect();
  const frameRect = frame.getBoundingClientRect();
  const width = Math.min(310, Math.max(220, frameRect.width - 16));
  const left = Math.max(frameRect.left + 8, Math.min(buttonRect.left + buttonRect.width / 2 - width / 2, frameRect.right - width - 8));
  popup.style.width = `${width}px`;
  popup.style.left = `${left}px`;
  popup.style.top = `${buttonRect.bottom + 5}px`;
}

function renderHead() {
  const head = document.getElementById('recordsHead');
  if (!head) return;
  const table = document.getElementById('recordsTable');
  table?.classList.toggle('records-biggest-turns-table', view === 'biggest_turns');
  table?.classList.toggle('records-elo-leaderboard-table', view === 'elo_leaderboard');
  const search = renderPlayerSearchMarkup();
  if (view === 'elo_leaderboard') {
    head.innerHTML = `<tr><th style="width:10%">Rank</th><th style="width:15%">Country</th><th class="records-player-header" style="width:40%">${search}</th><th style="width:17.5%">Peak Elo</th><th style="width:17.5%">Peak Arena</th></tr>`;
  } else if (view === 'most_icons') {
    head.innerHTML = `<tr><th style="width:5%">n</th><th style="width:10%">${renderIconFilterMarkup()}</th><th style="width:20%">${search}</th><th style="width:10%">Turns</th><th style="width:10%">Score</th><th style="width:20%">Map</th><th style="width:15%">ID</th><th style="width:10%">Date</th></tr>`;
  } else if (view === 'biggest_turns') {
    head.innerHTML = `<tr><th style="width:6%">Flat</th><th style="width:6%">End</th><th style="width:6%">Total</th><th class="records-player-header" style="width:18%">${search}</th><th style="width:6%">Score</th><th style="width:6%">Turns</th><th style="width:15%">Map</th><th style="width:6%">Move</th><th style="width:6%">Actions</th><th style="width:15%">ID</th><th style="width:10%">Date</th></tr>`;
  } else {
    const first = view === 'highest_scores' ? 'Score' : 'Turns';
    const third = view === 'highest_scores' ? 'Turns' : 'Score';
    head.innerHTML = `<tr><th style="width:10%">${first}</th><th class="records-player-header" style="width:20%">${search}</th><th style="width:10%">${third}</th><th style="width:25%">Map</th><th style="width:10%">ID</th><th style="width:15%">Date</th><th style="width:10%">EPT <span class="col-tip" data-tip="extrapolated turns">?</span></th></tr>`;
  }
  if (view === 'most_icons') head.querySelector('th:nth-child(3)')?.classList.add('records-player-header');
  renderIconFilterPopup();
}

function renderPlayerSearch() {
  renderHead();
  const input = document.getElementById('recordsPlayerSearch');
  if (input && playerSearch) positionSuggestions();
}

function renderBody() {
  const body = document.getElementById('recordsBody');
  if (!body) return;
  const meta = document.getElementById('recordsMeta');
  const filteredRows = filteredRecordsRows();
  if (view === 'elo_leaderboard') {
    if (meta) meta.innerHTML = 'Top 100 players (for full leaderboard, click <a href="https://emufriends.pet/leaderboard" target="_blank" rel="noopener noreferrer">here</a>).';
    if (!filteredRows.length) {
      body.innerHTML = `<tr><td colspan="${recordsColumnCount()}"><div class="state-overlay"><div class="state-title">No matching players</div></div></td></tr>`;
      renderPagination(0);
      return;
    }
    const pageSize = rowsPerPage >= 9999 ? filteredRows.length : rowsPerPage;
    const totalPages = Math.max(1, Math.ceil(filteredRows.length / pageSize));
    currentPage = Math.min(Math.max(1, currentPage), totalPages);
    const pageRows = filteredRows.slice((currentPage - 1) * pageSize, currentPage * pageSize);
    body.innerHTML = pageRows.map(row => `<tr><td>${whole(row.rank)}</td><td class="records-country-cell">${countryCodeToFlag(row.country)}</td><td>${escapeHtml(row.player)}</td><td>${two(row.peak_elo)}</td><td>${row.peak_arena == null ? 'n/a' : whole(row.peak_arena)}</td></tr>`).join('');
    renderPagination(totalPages);
    return;
  }
  if (meta) meta.textContent = `${filteredRows.length.toLocaleString('en-US')} game${filteredRows.length === 1 ? '' : 's'}`;
  if (!filteredRows.length) {
    body.innerHTML = `<tr><td colspan="${recordsColumnCount()}"><div class="state-overlay"><div class="state-title">No matching games</div><div class="state-sub">Try changing the filters.</div></div></td></tr>`;
    renderPagination(0);
    return;
  }
  const pageSize = rowsPerPage >= 9999 ? filteredRows.length : rowsPerPage;
  const totalPages = Math.max(1, Math.ceil(filteredRows.length / pageSize));
  currentPage = Math.min(Math.max(1, currentPage), totalPages);
  const pageRows = filteredRows.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  if (view === 'most_icons') {
     body.innerHTML = pageRows.map(row => `<tr><td>${whole(row.n)}</td><td><span class="records-icon-cell"><img src="assets/img/icons/${ICON_ASSETS[row.icon] || ''}" alt="${escapeAttr(row.icon)}" title="${escapeAttr(row.icon)}" /></span></td><td>${escapeHtml(row.player)}</td><td>${whole(row.turns)}</td><td>${whole(row.score)}</td><td title="${escapeAttr(mapTooltipLabel(row.map_name))}">${escapeHtml(mapTooltipLabel(row.map_name))}</td>${idCell(row.table_id, row.result_code)}<td>${escapeHtml(row.game_date || '-')}</td></tr>`).join('');
    renderPagination(totalPages);
    return;
  }
  if (view === 'biggest_turns') {
    body.innerHTML = pageRows.map(row => `<tr><td>${whole(row.flat)}</td><td>${whole(row.end)}</td><td>${whole(row.total)}</td><td>${escapeHtml(row.player)}</td><td>${whole(row.score)}</td><td>${whole(row.turns)}</td><td title="${escapeAttr(mapTooltipLabel(row.map_name))}">${escapeHtml(mapTooltipLabel(row.map_name))}</td><td>${whole(row.move)}</td><td>${whole(row.actions)}</td>${idCell(row.table_id, row.result_code)}<td>${escapeHtml(row.game_date || '-')}</td></tr>`).join('');
    renderPagination(totalPages);
    return;
  }
  body.innerHTML = pageRows.map(row => {
    const first = view === 'highest_scores' ? whole(row.score) : whole(row.turns);
    const third = view === 'highest_scores' ? whole(row.turns) : whole(row.score);
     return `<tr><td>${first}</td><td>${escapeHtml(row.player)}</td><td>${third}</td><td title="${escapeAttr(mapTooltipLabel(row.map_name))}">${escapeHtml(mapTooltipLabel(row.map_name))}</td>${idCell(row.table_id)}<td>${escapeHtml(row.game_date || '-')}</td><td>${whole(row.ept)}</td></tr>`;
  }).join('');
  renderPagination(totalPages);
}

function renderPagination(totalPages) {
  const host = document.getElementById('recordsPagination');
  if (!host) return;
  if (totalPages <= 1) {
    host.innerHTML = '';
    host.style.display = 'none';
    return;
  }
  const pages = [...new Set([1, totalPages, currentPage - 1, currentPage, currentPage + 1].filter(page => page >= 1 && page <= totalPages))].sort((a, b) => a - b);
  let html = `<button type="button" class="page-btn" onclick="goRecordsPage(${Math.max(1, currentPage - 1)})" ${currentPage === 1 ? 'disabled' : ''}>&lsaquo;</button>`;
  let previous = 0;
  for (const page of pages) {
    if (previous && page - previous > 1) html += '<span class="page-info">...</span>';
    html += `<button type="button" class="page-btn ${page === currentPage ? 'active' : ''}" onclick="goRecordsPage(${page})">${page}</button>`;
    previous = page;
  }
  html += `<button type="button" class="page-btn" onclick="goRecordsPage(${Math.min(totalPages, currentPage + 1)})" ${currentPage === totalPages ? 'disabled' : ''}>&rsaquo;</button>`;
  host.innerHTML = html;
  host.style.display = 'flex';
}

function idCell(id, resultCode = '') {
  const value = String(id ?? '').trim();
  const suffix = ['W', 'D', 'L'].includes(resultCode) ? ` (${resultCode})` : '';
  return `<td>${value ? `<a href="https://boardgamearena.com/table?table=${encodeURIComponent(value)}" target="_blank" rel="noopener">${escapeHtml(value)}</a>${suffix}` : '-'}</td>`;
}

function renderLoading() {
  const body = document.getElementById('recordsBody');
  if (body) body.innerHTML = `<tr><td colspan="${recordsColumnCount()}"><div class="state-overlay"><div class="spinner"></div><div class="state-title">Fetching records...</div></div></td></tr>`;
}

function renderError(error) {
  const body = document.getElementById('recordsBody');
  if (body) body.innerHTML = `<tr><td colspan="${recordsColumnCount()}"><div class="state-overlay"><div class="state-title">Could not load records</div><div class="state-sub">${escapeHtml(error?.message || error)}</div></div></td></tr>`;
}

function recordsColumnCount() {
  if (view === 'elo_leaderboard') return 5;
  if (view === 'biggest_turns') return 11;
  if (view === 'most_icons') return 8;
  return 7;
}

function numericOrNull(value) {
  if (value === '' || value == null) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function compareNumber(a, b, direction = 'desc') {
  const left = Number(a);
  const right = Number(b);
  const leftValid = Number.isFinite(left);
  const rightValid = Number.isFinite(right);
  if (!leftValid && !rightValid) return 0;
  if (!leftValid) return 1;
  if (!rightValid) return -1;
  return direction === 'asc' ? left - right : right - left;
}

function compareText(a, b) {
  return String(a ?? '').localeCompare(String(b ?? ''), undefined, { sensitivity: 'base' });
}

function compareRecordRows(a, b) {
  if (view === 'elo_leaderboard') return compareNumber(a.rank, b.rank, 'asc');
  if (view === 'fastest_games') {
    return compareNumber(a.turns, b.turns, 'asc') || compareNumber(a.score, b.score) || compareText(a.player, b.player) || compareText(a.table_id, b.table_id);
  }
  if (view === 'highest_scores') {
    return compareNumber(a.score, b.score) || compareNumber(a.turns, b.turns, 'asc') || compareText(a.player, b.player) || compareText(a.table_id, b.table_id);
  }
  if (view === 'biggest_turns') {
    return compareNumber(a.total, b.total) || compareNumber(a.source_row, b.source_row, 'asc') || compareText(a.table_id, b.table_id);
  }
  return compareNumber(a.n, b.n) || compareNumber(a.turns, b.turns, 'asc') || compareText(a.player, b.player) || compareText(a.table_id, b.table_id);
}

function filteredRecordsRows() {
  if (view === 'elo_leaderboard') {
    return rows
      .filter(row => !selectedPlayer || row.player === selectedPlayer)
      .sort(compareRecordRows);
  }
  const opponentMin = numericOrNull(document.getElementById('opponentEloMin')?.value) ?? 0;
  const opponentMax = numericOrNull(document.getElementById('opponentEloMax')?.value);
  const dateFrom = document.getElementById('recordsDateFrom')?.value.trim() || '';
  const dateTo = document.getElementById('recordsDateTo')?.value.trim() || '';
  const arenaOnly = Boolean(document.getElementById('recordsArenaOnly')?.checked);
  const tournamentOnly = Boolean(document.getElementById('recordsTournamentOnly')?.checked);
  return rows.filter(row => {
    if (!selectedMaps.includes(row.map_name)) return false;
    if (selectedPlayer && row.player !== selectedPlayer) return false;
    if (view === 'most_icons' && !selectedIconTypes.has(row.icon)) return false;
    if (dateFrom && String(row.game_date || '') < dateFrom) return false;
    if (dateTo && String(row.game_date || '') > dateTo) return false;
    if (arenaOnly && !row.is_arena) return false;
    if (tournamentOnly && !row.is_tournament) return false;
    const opponentElo = numericOrNull(row.opponent_elo);
    // Spreadsheet records without source Elo metadata remain visible by design.
    if (opponentElo != null && (opponentElo < opponentMin || (opponentMax != null && opponentElo > opponentMax))) return false;
    return true;
  }).sort(compareRecordRows);
}

function validDateInput(input) {
  if (!input?.value) { input?.setCustomValidity(''); return true; }
  const token = input.value.trim();
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(token);
  if (!match) { input.setCustomValidity('Use YYYY-MM-DD.'); return false; }
  const date = new Date(`${token}T00:00:00Z`);
  const valid = Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === token;
  input.setCustomValidity(valid ? '' : 'Enter a valid date.');
  return valid;
}

function validateDateRange() {
  const from = document.getElementById('recordsDateFrom');
  const to = document.getElementById('recordsDateTo');
  if (!validDateInput(from)) { from.reportValidity(); return false; }
  if (!validDateInput(to)) { to.reportValidity(); return false; }
  if (from.value && to.value && from.value > to.value) {
    to.setCustomValidity('Date To must be on or after Date From.');
    to.reportValidity();
    return false;
  }
  to?.setCustomValidity('');
  return true;
}

async function loadRecords(token) {
  if (!mounted) return;
  requestController?.abort();
  requestController = new AbortController();
  try {
    const dataset = view === 'elo_leaderboard' ? 'mw' : (isMW ? 'mw' : 'base');
    const cacheKey = view === 'elo_leaderboard' ? `${view}:shared` : `${view}:${dataset}`;
    let payload = snapshotRows.get(cacheKey);
    if (!payload) {
      renderLoading();
      payload = await loadSnapshot(`${API_ROOT}/${API_VIEWS[view]}/default-${dataset}.json`);
      snapshotRows.set(cacheKey, payload);
    }
    if (!mounted || token !== requestToken) return;
    rows = Array.isArray(payload?.data) ? payload.data : [];
    currentPage = 1;
    renderBody();
  } catch (error) {
    if (error?.name === 'AbortError' || token !== requestToken) return;
    renderError(error);
  }
}

function applyFiltersFromSidebar() {
  if (!validateDateRange()) return;
  currentPage = 1;
  renderBody();
  window.toggleSidebar?.();
}
function resetFilters() {
  const min = document.getElementById('opponentEloMin'); if (min) min.value = 300;
  const max = document.getElementById('opponentEloMax'); if (max) max.value = '';
  const dateFrom = document.getElementById('recordsDateFrom'); if (dateFrom) { dateFrom.value = ''; dateFrom.setCustomValidity(''); }
  const dateTo = document.getElementById('recordsDateTo'); if (dateTo) { dateTo.value = ''; dateTo.setCustomValidity(''); }
  selectedMaps = DEFAULT_MAPS.map(([, full]) => full);
  const arena = document.getElementById('recordsArenaOnly'); if (arena) arena.checked = false;
  const tournament = document.getElementById('recordsTournamentOnly'); if (tournament) tournament.checked = false;
  currentPage = 1;
  renderMapFilter(); renderBody();
}

function setRecordsRows(value) {
  rowsPerPage = Number(value) >= 9999 ? 9999 : Math.max(1, Number(value) || 50);
  currentPage = 1;
  renderBody();
}

function goRecordsPage(page) {
  currentPage = Number(page) || 1;
  renderBody();
}

function toggleRecordsPlayerSearch(event) {
  event?.stopPropagation();
  renderHead();
  const input = document.getElementById('recordsPlayerSearch');
  input?.focus();
  if (playerSearch) renderSuggestions();
}

function toggleRecordsIconFilter(event) {
  event?.stopPropagation();
  iconFilterOpen = !iconFilterOpen;
  renderHead();
}

function toggleRecordsIconType(icon) {
  if (!ALL_ICON_TYPES.includes(icon)) return;
  if (selectedIconTypes.has(icon)) selectedIconTypes.delete(icon);
  else selectedIconTypes.add(icon);
  renderHead();
  renderBody();
}

function selectAllRecordsIcons() {
  selectedIconTypes = new Set(ALL_ICON_TYPES);
  renderHead();
  renderBody();
}

function selectNoneRecordsIcons() {
  selectedIconTypes.clear();
  renderHead();
  renderBody();
}

async function ensurePlayerIndex() {
  if (playerIndex && playerIndex.dataset === isMW) return;
  if (playerIndexLoading) return;
  playerIndexLoading = true;
  playerIndexError = '';
  try {
    const dataset = isMW ? 'mw' : 'base';
    try { playerIndex = await loadSnapshot(`https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/players/index/default-${dataset}.json`); }
    catch { playerIndex = await fetchStats({ stats_page: 'players', players_index: true, is_mw: isMW }); }
    if (playerIndex) playerIndex.dataset = isMW;
  } catch (error) { playerIndexError = error?.message || String(error); }
  finally { playerIndexLoading = false; }
}

function onRecordsPlayerInput(value) {
  playerSearch = String(value || '');
  selectedPlayer = '';
  if (playerSearch.trim().length < 3) { closeSuggestions(); return; }
  if (view !== 'elo_leaderboard') void ensurePlayerIndex().then(() => renderSuggestions());
  renderSuggestions();
}

function renderSuggestions() {
  const input = document.getElementById('recordsPlayerSearch');
  if (!input || playerSearch.trim().length < 3) { closeSuggestions(); return; }
  let host = document.getElementById('recordsPlayerSuggestions');
  if (!host) { host = document.createElement('div'); host.id = 'recordsPlayerSuggestions'; host.className = 'records-player-suggestions'; document.body.appendChild(host); }
  const players = view === 'elo_leaderboard'
    ? rows.map(row => row.player).filter(Boolean)
    : Array.isArray(playerIndex?.players) ? playerIndex.players : [];
  const term = playerSearch.trim().toLocaleLowerCase();
  const matches = players.filter(name => String(name).toLocaleLowerCase().includes(term)).slice(0, 50);
  host.innerHTML = playerIndexLoading ? '<div class="records-suggestion-state">Loading players...</div>' : playerIndexError ? `<div class="records-suggestion-state">${escapeHtml(playerIndexError)}</div>` : matches.length ? matches.map(name => `<button type="button" data-player="${escapeAttr(name)}" onclick="selectRecordsPlayer(this.dataset.player)">${escapeHtml(name)}</button>`).join('') : '<div class="records-suggestion-state">No matching players</div>';
  host.classList.add('visible');
  positionSuggestions();
}

function positionSuggestions() {
  const input = document.getElementById('recordsPlayerSearch'); const host = document.getElementById('recordsPlayerSuggestions');
  if (!input || !host) return;
  const rect = input.getBoundingClientRect();
  host.style.left = `${Math.max(8, Math.min(rect.left, window.innerWidth - Math.max(220, rect.width) - 8))}px`;
  host.style.top = `${Math.min(window.innerHeight - 8, rect.bottom + 4)}px`;
  host.style.width = `${Math.max(220, rect.width)}px`;
}

function selectRecordsPlayer(player) {
  selectedPlayer = String(player || ''); playerSearch = selectedPlayer; closeSuggestions(); renderHead(); currentPage = 1; renderBody();
}
function clearRecordsPlayer() { selectedPlayer = ''; playerSearch = ''; closeSuggestions(); renderHead(); currentPage = 1; renderBody(); }
function closeSuggestions() { document.getElementById('recordsPlayerSuggestions')?.classList.remove('visible'); }

function whole(value) { const number = Number(value); return Number.isFinite(number) ? Math.round(number).toLocaleString('en-US') : '-'; }
function two(value) { const number = Number(value); return Number.isFinite(number) ? number.toFixed(2) : '-'; }
function countryName(code) {
  const normalized = String(code || '').trim().toUpperCase();
  if (!/^[A-Z]{2}$/.test(normalized)) return normalized || 'Unknown';
  if (normalized === 'XK') return 'Kosovo';
  if (normalized === 'AQ') return 'Unknown';
  try {
    return new Intl.DisplayNames(['en'], { type: 'region' }).of(normalized) || normalized;
  } catch { return normalized; }
}
function countryCodeToFlag(code) {
  const normalized = String(code || '').trim().toLowerCase();
  if (!/^[a-z]{2}$/.test(normalized)) return '-';
  const label = countryName(normalized);
  return `<img class="records-flag-img" src="https://flagcdn.io/flags/4x3/${normalized}.svg" alt="${escapeAttr(label)} flag" title="${escapeAttr(label)}" loading="lazy" decoding="async" />`;
}
function escapeAttr(value) { return escapeHtml(value).replaceAll('`', '&#96;'); }
function escapeHtml(value) { return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;'); }

function hideRecordsTooltip() {
  const tooltip = document.getElementById('col-tooltip');
  if (tooltip) tooltip.style.display = 'none';
}

function positionRecordsTooltip(event) {
  const tooltip = document.getElementById('col-tooltip');
  if (!tooltip) return;
  const margin = 8;
  const left = Math.max(margin, Math.min(event.clientX + 12, window.innerWidth - tooltip.offsetWidth - margin));
  const below = event.clientY + 18;
  const top = below + tooltip.offsetHeight <= window.innerHeight - margin ? below : event.clientY - tooltip.offsetHeight - 10;
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

window.addEventListener('resize', positionSuggestions);
window.addEventListener('resize', positionIconFilterPopup);
document.addEventListener('scroll', () => { if (mounted && iconFilterOpen) positionIconFilterPopup(); }, true);
document.addEventListener('mouseover', event => {
  if (!mounted) return;
  const source = event.target.closest?.('.records-table .col-tip, #recordsIconFilterPopup [data-tip]');
  if (!source?.dataset.tip) return;
  const tooltip = document.getElementById('col-tooltip');
  if (!tooltip) return;
  tooltip.textContent = source.dataset.tip;
  tooltip.style.display = 'block';
  positionRecordsTooltip(event);
});
document.addEventListener('mousemove', event => {
  if (!mounted || !event.target.closest?.('.records-table .col-tip, #recordsIconFilterPopup [data-tip]')) return;
  positionRecordsTooltip(event);
});
document.addEventListener('mouseout', event => {
  if (!mounted) return;
  const source = event.target.closest?.('.records-table .col-tip, #recordsIconFilterPopup [data-tip]');
  if (!source || source.contains(event.relatedTarget)) return;
  hideRecordsTooltip();
});
document.addEventListener('click', event => {
  if (!event.target.closest?.('.records-player-search, .records-player-search-toggle, #recordsPlayerSuggestions')) closeSuggestions();
  if (!event.target.closest?.('.records-icon-filter-wrap, #recordsIconFilterPopup')) {
    if (iconFilterOpen) { iconFilterOpen = false; document.getElementById('recordsIconFilterPopup')?.remove(); renderHead(); }
  }
});
