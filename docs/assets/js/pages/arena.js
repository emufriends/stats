import { fetchStats, loadSnapshot } from '../snapshot-cache.js?v=20260908-arena-bootstrap1';
import { setFilterButtonDisabled, setTopbarDatasetLock } from '../layout.js?v=20260801-2';

export const id = 'arena';
export const title = 'Arena';
export const navLabel = 'Arena';

const API_ROOT = 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/players';
const ARENA_LATEST_URL = `${API_ROOT}/arena/latest.json`;
const ARENA_BUNDLE_URL = `${API_ROOT}/arena-top-100/all-seasons.json`;
const LINE_COLORS = ['#42d392', '#60a5fa', '#f59e0b', '#c084fc', '#fb7185'];

export const mainHtml = `
  <div class="main-header players-main-header arena-main-header">
    <div class="table-meta" id="arenaTableMeta"></div>
    <div class="players-arena-day-control is-hidden" id="arenaDayControl" aria-label="Arena graph day range">
      <span>Day</span><input id="arenaDayStart" type="text" inputmode="numeric" pattern="[0-9]*" oninput="onArenaDayInput(event, 'start')" aria-label="Arena graph start day">
      <span>to Day</span><input id="arenaDayEnd" type="text" inputmode="numeric" pattern="[0-9]*" oninput="onArenaDayInput(event, 'end')" aria-label="Arena graph end day">
    </div>
    <div class="players-arena-season-control" id="arenaSeasonControl">
      <label for="arenaSeasonSelect">Season</label>
      <select id="arenaSeasonSelect" onchange="setArenaSeason(this.value)"></select>
    </div>
    <div class="main-controls arena-main-controls" id="arenaTableControls">
      <div class="rpp-wrap">
        <span>Rows</span>
        <select class="rpp-select" id="arenaRppSelect" onchange="onArenaRppChange()" aria-label="Rows per page">
          <option value="25">25</option>
          <option value="50">50</option>
          <option value="100" selected>100</option>
          <option value="9999">All</option>
        </select>
      </div>
    </div>
  </div>
  <div class="attributes-bar endgames-tabs-bar players-tabs-bar arena-tabs-bar">
    <div class="attributes-bar-header endgames-tabs-header">
      <div class="endgames-tabs players-tabs arena-tabs" role="tablist" aria-label="Arena views">
        <button class="endgames-tab players-arena-tab active" type="button">
          <span>Elite League</span>
          <span class="endgames-graph-toggle" id="arenaGraphToggle" role="button" tabindex="0" title="Show graph" aria-label="Show Arena rating graph" onclick="toggleArenaGraph(event)" onkeydown="onArenaGraphKey(event)"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 19h16"/><path d="M4 5v14"/><path d="M6.5 15.5 10 11l3.5 2.5L18 7"/></svg></span>
        </button>
      </div>
    </div>
  </div>
  <div id="arenaContent"><div class="state-overlay"><div class="spinner"></div><div class="state-title">Loading Arena Elite League...</div></div></div>`;

export const sidebarHtml = '';

let mounted = false;
let isMW = 1;
let bundle = null;
let loadState = 'loading';
let loadError = '';
let selectedSeason = null;
let graphView = false;
let graphSelected = new Set();
// Keep a player's line color tied to that player for the mounted season. The
// selected series is drawn in dataset order, so deriving colors from that
// order would recolor existing lines whenever another player is selected.
let graphColorByPlayer = new Map();
let graphSearch = '';
let arenaPlayerSearch = '';
let arenaPlayerSuggestionsOpen = false;
let graphDayStart = 1;
let graphDayEnd = null;
let graphHover = null;
let graphRenderState = null;
let tableSort = { field: 'end', direction: 'desc' };
let arenaRowsPerPage = 100;
let arenaCurrentPage = 1;
let fullBundleLoading = false;
let assetRequest = 0;

export function mount({ dataset = 1 } = {}) {
  mounted = true;
  isMW = Number(dataset) === 0 ? 0 : 1;
  graphView = false;
  graphSelected = new Set();
  graphColorByPlayer = new Map();
  graphSearch = '';
  arenaPlayerSearch = '';
  arenaPlayerSuggestionsOpen = false;
  graphDayStart = 1;
  graphDayEnd = null;
  graphHover = null;
  graphRenderState = null;
  tableSort = { field: 'end', direction: 'desc' };
  arenaRowsPerPage = 100;
  arenaCurrentPage = 1;
  fullBundleLoading = false;
  Object.assign(window, {
    setArenaSeason,
    toggleArenaGraph,
    onArenaGraphKey,
    setArenaGraphSearch,
    toggleArenaGraphPlayer,
    onArenaGraphMove,
    clearArenaGraphHover,
    onArenaDayInput,
    selectArenaTopFive,
    clearArenaGraphSelection,
    selectArenaRandom,
    sortArenaTable,
    onArenaRppChange,
    goArenaPage,
    onArenaPlayerSearchInput,
    clearArenaPlayerSearch,
    selectArenaPlayerSuggestion,
  });
  setFilterButtonDisabled(true);
  loadArenaAssets();
}

export function unmount() {
  mounted = false;
  assetRequest += 1;
  setFilterButtonDisabled(false);
  setTopbarDatasetLock(null);
  hideTooltip();
}

export function setDataset(value) {
  isMW = Number(value) === 0 ? 0 : 1;
  syncDatasetLock();
  render();
}

async function loadArenaAssets() {
  const requestId = ++assetRequest;
  loadState = 'loading';
  loadError = '';
  fullBundleLoading = true;
  render();
  const latestPromise = loadSnapshot(ARENA_LATEST_URL).catch(() => null);
  const bundlePromise = loadSnapshot(ARENA_BUNDLE_URL).catch(() => fetchStats({
    stats_page: 'arena', arena_view: 'top_100', is_mw: isMW,
  }));
  try {
    const latest = await latestPromise;
    if (!mounted || requestId !== assetRequest) return;
    if (isArenaPayload(latest)) {
      installArenaPayload(latest);
      void bundlePromise.then(payload => {
        if (!mounted || requestId !== assetRequest) return;
        if (!isArenaPayload(payload)) {
          fullBundleLoading = false;
          render();
          return;
        }
        fullBundleLoading = false;
        installArenaPayload(payload);
      }).catch(() => {
        if (mounted && requestId === assetRequest) fullBundleLoading = false;
      });
      return;
    }
    const payload = await bundlePromise;
    if (!mounted || requestId !== assetRequest) return;
    if (!isArenaPayload(payload)) throw new Error('Arena Elite League bundle has an invalid response shape.');
    fullBundleLoading = false;
    installArenaPayload(payload);
  } catch (error) {
    if (!mounted || requestId !== assetRequest) return;
    fullBundleLoading = false;
    loadState = 'error';
    loadError = error?.message || String(error);
    render();
  }
}

function isArenaPayload(payload) {
  return Boolean(payload && Array.isArray(payload.seasons) && payload.data && typeof payload.data === 'object');
}

function installArenaPayload(payload) {
  bundle = payload;
  loadState = 'ready';
  loadError = '';
  selectedSeason ||= payload.latest_season || payload.seasons[0]?.season || null;
  syncSeasonSelect();
  syncDatasetLock();
  resetGraphSelection();
  render();
}

function seasons() {
  return (bundle?.seasons || []).slice().sort((a, b) => Number(b.number) - Number(a.number));
}

function currentData() {
  return selectedSeason ? bundle?.data?.[selectedSeason] || null : null;
}

function syncSeasonSelect() {
  const select = document.getElementById('arenaSeasonSelect');
  if (!select) return;
  const items = seasons();
  if (!selectedSeason || !items.some(item => item.season === selectedSeason)) {
    selectedSeason = bundle?.latest_season || items[0]?.season || null;
  }
  select.innerHTML = items.map(item => `<option value="${escapeAttr(item.season)}" ${item.season === selectedSeason ? 'selected' : ''}>${escapeHtml(item.season)}</option>`).join('');
  select.disabled = items.length === 0;
}

function syncDatasetLock() {
  const metadata = seasons().find(item => item.season === selectedSeason);
  if (!metadata) return;
  const required = Number(metadata.is_mw);
  setTopbarDatasetLock(required);
  if (required !== Number(isMW)) {
    window.dispatchEvent(new CustomEvent('arknova:set-dataset', { detail: { value: required } }));
  }
}

function resetGraphSelection() {
  const data = currentData();
  graphSelected = new Set((data?.series || [])
    .filter(item => Number(item.rank) <= 5 && (item.ratings || []).length > 0)
    .map(item => item.player));
}

function syncGraphColorAssignments(players) {
  const selectedPlayers = [...new Set(players || [])].filter(Boolean);
  const used = new Set();
  const assigned = new Set();
  selectedPlayers.forEach(player => {
    const index = graphColorByPlayer.get(player);
    if (Number.isInteger(index) && index >= 0 && index < LINE_COLORS.length && !used.has(index)) {
      used.add(index);
      assigned.add(player);
    }
  });
  selectedPlayers.forEach(player => {
    if (assigned.has(player)) return;
    const next = LINE_COLORS.findIndex((_, index) => !used.has(index));
    const index = next >= 0 ? next : selectedPlayers.indexOf(player) % LINE_COLORS.length;
    graphColorByPlayer.set(player, index);
    used.add(index);
  });
}

function graphColorForPlayer(player) {
  const index = graphColorByPlayer.get(player);
  return Number.isInteger(index) ? LINE_COLORS[index % LINE_COLORS.length] : 'transparent';
}

function syncDayControl() {
  const control = document.getElementById('arenaDayControl');
  const data = currentData();
  if (!control || !data) return;
  syncDayRange(data);
  control.classList.toggle('is-hidden', !graphView);
  const start = document.getElementById('arenaDayStart');
  const end = document.getElementById('arenaDayEnd');
  if (start) start.value = graphDayStart;
  if (end) end.value = graphDayEnd;
}

function setArenaSeason(season) {
  if (!seasons().some(item => item.season === season)) return;
  selectedSeason = season;
  graphColorByPlayer = new Map();
  graphSearch = '';
  graphDayStart = 1;
  graphDayEnd = null;
  graphHover = null;
  tableSort = { field: 'end', direction: 'desc' };
  arenaCurrentPage = 1;
  resetGraphSelection();
  syncSeasonSelect();
  syncDatasetLock();
  render();
}

function toggleArenaGraph(event) {
  event?.preventDefault?.();
  event?.stopPropagation?.();
  graphView = !graphView;
  if (graphView && graphSelected.size === 0) resetGraphSelection();
  render();
}

function onArenaGraphKey(event) {
  if (event.key === 'Enter' || event.key === ' ') toggleArenaGraph(event);
}

function setArenaGraphSearch(value) {
  graphSearch = String(value || '');
  renderGraphLegend();
}

function toggleArenaGraphPlayer(player) {
  const series = currentData()?.series?.find(item => item.player === player);
  if (!series || !(series.ratings || []).length) return;
  const wasSelected = graphSelected.has(player);
  if (wasSelected) graphSelected.delete(player);
  else {
    if (graphSelected.size >= 5) {
      document.getElementById('arenaGraphLimit')?.classList.add('limit-pulse');
      window.setTimeout(() => document.getElementById('arenaGraphLimit')?.classList.remove('limit-pulse'), 700);
      return;
    }
    graphSelected.add(player);
  }
  renderGraphCanvas();
  renderGraphLegend();
  if (!wasSelected) {
    const legendList = document.getElementById('arenaLegendList');
    if (legendList) legendList.scrollTop = 0;
  }
}

function selectArenaTopFive() { resetGraphSelection(); renderGraphCanvas(); renderGraphLegend(); }
function clearArenaGraphSelection() { graphSelected.clear(); renderGraphCanvas(); renderGraphLegend(); }

function selectArenaRandom() {
  const eligible = (currentData()?.series || []).filter(item => (item.ratings || []).length > 0);
  for (let index = eligible.length - 1; index > 0; index -= 1) {
    const swap = Math.floor(Math.random() * (index + 1));
    [eligible[index], eligible[swap]] = [eligible[swap], eligible[index]];
  }
  graphSelected = new Set(eligible.slice(0, 5).map(item => item.player));
  graphHover = null;
  renderGraphCanvas();
  renderGraphLegend();
}

function render() {
  const host = document.getElementById('arenaContent');
  if (!host) return;
  syncSeasonSelect();
  syncDayControl();
  const tableMeta = document.getElementById('arenaTableMeta');
  const tableControls = document.getElementById('arenaTableControls');
  if (tableMeta && graphView) tableMeta.innerHTML = '';
  tableControls?.toggleAttribute('hidden', graphView);
  const toggle = document.getElementById('arenaGraphToggle');
  toggle?.classList.toggle('active', graphView);
  if (toggle) {
    toggle.title = graphView ? 'Show table' : 'Show graph';
    toggle.setAttribute('aria-label', graphView ? 'Show Arena Elite League table' : 'Show Arena rating graph');
  }
  if (loadState === 'loading') {
    host.innerHTML = '<div class="state-overlay"><div class="spinner"></div><div class="state-title">Loading Arena Elite League...</div></div>';
    return;
  }
  if (loadState === 'error' || !bundle) {
    host.innerHTML = `<div class="state-overlay"><div class="state-title">Could not load Arena Elite League</div><div class="state-sub">${escapeHtml(loadError || 'Static bundle unavailable')}</div><button type="button" class="reset-btn" onclick="location.reload()">Retry</button></div>`;
    return;
  }
  const data = currentData();
  if (!data) {
    host.innerHTML = `<div class="state-overlay"><div class="${fullBundleLoading ? 'spinner' : 'error-icon'}">${fullBundleLoading ? '' : '&#128269;'}</div><div class="state-title">${fullBundleLoading ? 'Loading this season...' : 'No ranking snapshot is available for this season.'}</div></div>`;
    return;
  }
  if (graphView) renderGraph(host, data);
  else renderTable(host, data);
}

function finiteNumber(raw) {
  if (raw === null || raw === undefined || raw === '') return Number.NaN;
  const value = Number(raw);
  return Number.isFinite(value) ? value : Number.NaN;
}

function wholeOrDash(raw) {
  const value = finiteNumber(raw);
  return Number.isFinite(value) ? Math.round(value).toLocaleString('en-US') : '-';
}

function twoOrDash(raw, suffix = '') {
  const value = finiteNumber(raw);
  return Number.isFinite(value) ? `${value.toFixed(2)}${suffix}` : '-';
}

function arenaPlayerNameMarkup(row) {
  const name = escapeHtml(row.player);
  const playerId = Number(row.player_id);
  if (!Number.isInteger(playerId) || playerId <= 0) return name;
  return `<a class="card-details-link" href="https://boardgamearena.com/player?id=${playerId}" target="_blank" rel="noopener noreferrer">${name}</a>`;
}

const SORT_FIELDS = ['end', 'peak', 'games', 'winrate', 'opponent_elo', 'pr', 'turns', 'ppt'];

function compareRows(a, b) {
  const av = finiteNumber(a[tableSort.field]);
  const bv = finiteNumber(b[tableSort.field]);
  if (!Number.isFinite(av) && Number.isFinite(bv)) return 1;
  if (Number.isFinite(av) && !Number.isFinite(bv)) return -1;
  let comparison = Number.isFinite(av) && Number.isFinite(bv) ? av - bv : 0;
  if (comparison !== 0) return tableSort.direction === 'asc' ? comparison : -comparison;

  // Displayed rank (#) is the stable, ascending tie-breaker for every Arena
  // sort. It must not reverse when the primary metric is sorted descending.
  const ar = finiteNumber(a.rank);
  const br = finiteNumber(b.rank);
  if (!Number.isFinite(ar) && Number.isFinite(br)) return 1;
  if (Number.isFinite(ar) && !Number.isFinite(br)) return -1;
  return Number.isFinite(ar) && Number.isFinite(br) ? ar - br : 0;
}

function sortArenaTable(field) {
  if (!SORT_FIELDS.includes(field)) return;
  tableSort = tableSort.field === field
    ? { field, direction: tableSort.direction === 'desc' ? 'asc' : 'desc' }
    : { field, direction: 'desc' };
  render();
}

function onArenaRppChange() {
  const select = document.getElementById('arenaRppSelect');
  const value = Number(select?.value);
  if (![25, 50, 100, 9999].includes(value)) return;
  arenaRowsPerPage = value;
  arenaCurrentPage = 1;
  render();
}

function renderTable(host, data) {
  const sortedRows = [...(data.rows || [])].sort(compareRows);
  const searchTerm = arenaPlayerSearch.trim().toLocaleLowerCase();
  const filteredRows = searchTerm
    ? sortedRows.filter(row => String(row.player || '').toLocaleLowerCase().includes(searchTerm))
    : sortedRows;
  const totalRows = filteredRows.length;
  const rowsPerPage = arenaRowsPerPage >= 9999 ? Math.max(1, totalRows) : arenaRowsPerPage;
  const totalPages = Math.max(1, Math.ceil(totalRows / rowsPerPage));
  if (arenaCurrentPage > totalPages) arenaCurrentPage = totalPages;
  const start = (arenaCurrentPage - 1) * rowsPerPage;
  const pageRows = filteredRows.slice(start, start + rowsPerPage);
  const from = totalRows ? start + 1 : 0;
  const to = totalRows ? Math.min(start + pageRows.length, totalRows) : 0;
  const meta = document.getElementById('arenaTableMeta');
  if (meta) meta.innerHTML = totalRows
    ? `<span class="meta-prefix">Showing </span><strong>${from}-${to}</strong> of <strong>${totalRows}</strong> players`
    : 'No players';
  const sortArrow = field => tableSort.field === field ? (tableSort.direction === 'asc' ? '&#8593;' : '&#8595;') : '&#8597;';
  const sortHeader = (field, label, tip = '') => `<th class="sortable ${tableSort.field === field ? 'sorted' : ''}" onclick="sortArenaTable('${field}')"><span class="sortable-header-content"><span class="sortable-header-label">${label}${tip ? ` <span class="col-tip" data-tip="${escapeAttr(tip)}">?</span>` : ''}</span><span class="sort-arrow">${sortArrow(field)}</span></span></th>`;
  const searchMatches = searchTerm.length >= 3
    ? [...new Set(sortedRows.filter(row => String(row.player || '').toLocaleLowerCase().includes(searchTerm)).map(row => String(row.player || '')))].slice(0, 50)
    : [];
  const searchAction = '<button type="button" class="players-search-clear" onclick="clearArenaPlayerSearch(event)" aria-label="Clear player search">&times;</button>';
  const suggestionHtml = arenaPlayerSuggestionsOpen && searchMatches.length
    ? searchMatches.map(player => `<button type="button" role="option" data-player="${escapeAttr(player)}">${escapeHtml(player)}</button>`).join('')
    : '';
  host.innerHTML = `<div class="table-wrap players-arena-table-wrap"><div class="table-scroll"><table class="players-arena-table">
     <colgroup><col style="width:5%"><col style="width:20%">${'<col style="width:9.375%">'.repeat(8)}</colgroup>
     <thead><tr><th>#</th><th class="players-player-header"><div class="players-search-wrap"><span class="players-search-icon" aria-hidden="true">&#128269;</span><input id="arenaPlayerSearch" type="search" value="${escapeAttr(arenaPlayerSearch)}" placeholder="Search player" oninput="onArenaPlayerSearchInput(event)" autocomplete="off" aria-label="Search Arena players">${searchAction}</div></th>${sortHeader('end', 'End')}${sortHeader('peak', 'Peak')}${sortHeader('games', 'Games')}${sortHeader('winrate', 'Winrate')}${sortHeader('opponent_elo', 'Opp. Elo')}${sortHeader('pr', 'PR', 'performance rating')}${sortHeader('turns', 'Turns')}${sortHeader('ppt', 'PPT', 'points per turn')}</tr></thead>
     <tbody>${pageRows.map(row => `<tr><td class="rank-cell">${wholeOrDash(row.rank)}</td><td class="players-arena-name">${arenaPlayerNameMarkup(row)}</td><td>${wholeOrDash(row.end)}</td><td>${wholeOrDash(row.peak)}</td><td>${wholeOrDash(row.games)}</td><td>${twoOrDash(row.winrate, '%')}</td><td>${wholeOrDash(row.opponent_elo)}</td><td>${wholeOrDash(row.pr)}</td><td>${twoOrDash(row.turns)}</td><td>${twoOrDash(row.ppt)}</td></tr>`).join('') || '<tr><td colspan="10"><div class="state-overlay"><div class="state-title">No matching players</div></div></td></tr>'}</tbody>
   </table></div><div class="pagination" id="arenaPagination"${totalPages <= 1 ? ' hidden' : ''}>${totalPages > 1 ? buildArenaPagination(totalPages) : ''}</div></div><div id="arenaPlayerSuggestions" class="players-suggestions${arenaPlayerSuggestionsOpen && searchMatches.length ? ' open' : ''}" role="listbox" aria-label="Matching Arena players">${suggestionHtml}</div>`;
  if (arenaPlayerSuggestionsOpen && searchMatches.length) requestAnimationFrame(positionArenaPlayerSuggestions);
}

function onArenaPlayerSearchInput(event) {
  const input = event.target;
  arenaPlayerSearch = String(input?.value || '');
  arenaPlayerSuggestionsOpen = arenaPlayerSearch.trim().length >= 3;
  const wasFocused = document.activeElement === input;
  const cursor = input?.selectionStart ?? arenaPlayerSearch.length;
  render();
  if (wasFocused) {
    requestAnimationFrame(() => {
      const next = document.getElementById('arenaPlayerSearch');
      next?.focus();
      try { next?.setSelectionRange(cursor, cursor); } catch (_) { /* input may have been replaced during navigation */ }
    });
  }
}

function clearArenaPlayerSearch(event) {
  event?.stopPropagation?.();
  arenaPlayerSearch = '';
  arenaPlayerSuggestionsOpen = false;
  render();
}

function selectArenaPlayerSuggestion(player) {
  const exact = String(player || '');
  if (!exact) return;
  arenaPlayerSearch = exact;
  arenaPlayerSuggestionsOpen = false;
  render();
}

function positionArenaPlayerSuggestions() {
  const host = document.getElementById('arenaPlayerSuggestions');
  const input = document.getElementById('arenaPlayerSearch');
  if (!host?.classList.contains('open') || !input) return;
  const rect = input.getBoundingClientRect();
  const width = Math.min(Math.max(180, rect.width), window.innerWidth - 16);
  const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
  host.style.left = `${left}px`;
  host.style.width = `${width}px`;
  host.style.top = `${rect.bottom + 4}px`;
  const listRect = host.getBoundingClientRect();
  if (listRect.bottom > window.innerHeight - 8 && rect.top > listRect.height + 12) host.style.top = `${rect.top - listRect.height - 4}px`;
}

function buildArenaPagination(totalPages) {
  let html = `<button class="page-btn" onclick="goArenaPage(${arenaCurrentPage - 1})" ${arenaCurrentPage === 1 ? 'disabled' : ''}>&lsaquo;</button>`;
  const pages = arenaPaginationRange(arenaCurrentPage, totalPages);
  let previous = null;
  for (const page of pages) {
    if (previous !== null && page - previous > 1) html += '<span class="page-info">...</span>';
    html += `<button class="page-btn ${page === arenaCurrentPage ? 'active' : ''}" onclick="goArenaPage(${page})">${page}</button>`;
    previous = page;
  }
  return `${html}<button class="page-btn" onclick="goArenaPage(${arenaCurrentPage + 1})" ${arenaCurrentPage === totalPages ? 'disabled' : ''}>&rsaquo;</button>`;
}

function arenaPaginationRange(current, total) {
  const range = [];
  for (let page = Math.max(1, current - 2); page <= Math.min(total, current + 2); page += 1) range.push(page);
  if (!range.includes(1)) range.unshift(1);
  if (!range.includes(total)) range.push(total);
  return range;
}

function goArenaPage(page) {
  const totalRows = currentData()?.rows?.length || 0;
  const rowsPerPage = arenaRowsPerPage >= 9999 ? Math.max(1, totalRows) : arenaRowsPerPage;
  const totalPages = Math.max(1, Math.ceil(totalRows / rowsPerPage));
  if (page < 1 || page > totalPages) return;
  arenaCurrentPage = page;
  render();
  document.querySelector('.players-arena-table-wrap')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderGraph(host, data) {
  syncDayRange(data);
  host.innerHTML = `<div class="players-arena-graph-shell">
    <div class="players-arena-chart" id="arenaChart"><div class="players-arena-graph-tooltip" id="arenaGraphTooltip" role="status" aria-live="polite"></div></div>
    <aside class="players-arena-legend">
      <input type="search" value="${escapeAttr(graphSearch)}" placeholder="Search players" oninput="setArenaGraphSearch(this.value)" aria-label="Search Arena players">
      <div class="players-arena-legend-actions"><button type="button" onclick="selectArenaTopFive()">Top 5</button><button type="button" onclick="clearArenaGraphSelection()">None</button><button type="button" onclick="selectArenaRandom()">Random</button></div>
      <div class="players-arena-limit" id="arenaGraphLimit">Maximum 5 players</div>
      <div class="players-arena-legend-list" id="arenaLegendList"></div>
    </aside>
  </div>`;
  renderGraphCanvas();
  renderGraphLegend();
}

function renderGraphCanvas() {
  const host = document.getElementById('arenaChart');
  const data = currentData();
  if (!host || !data) return;
  syncDayRange(data);
  const selectedPlayers = [...graphSelected].filter(player => data.series?.some(item => item.player === player && (item.ratings || []).length));
  syncGraphColorAssignments(selectedPlayers);
  const selected = (data.series || []).filter(item => graphSelected.has(item.player) && (item.ratings || []).length);
  const width = 900; const height = 470;
  const margin = { left: 62, right: 24, top: 25, bottom: 34 };
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  const seasonStart = Date.parse(data.start_utc);
  const officialEnd = Date.parse(data.end_utc);
  const effectiveEnd = Date.parse(data.effective_end_utc || data.end_utc);
  const dayMs = 86400000;
  const maxDay = seasonDayCount(data);
  const start = seasonStart + (graphDayStart - 1) * dayMs;
  const end = graphDayEnd >= maxDay ? effectiveEnd : Math.min(officialEnd, seasonStart + graphDayEnd * dayMs);
  const pointsFor = item => (item.timestamps || []).map((timestamp, index) => ({
    time: Date.parse(timestamp), rating: Number(item.ratings?.[index]),
  })).filter(point => Number.isFinite(point.time) && Number.isFinite(point.rating) && point.time >= start && point.time <= end);
  const selectedPoints = selected.map(item => ({ item, points: pointsFor(item) }));
  const ratings = selectedPoints.flatMap(entry => entry.points.map(point => point.rating));
  let yMin = ratings.length ? Math.min(...ratings) : 0;
  let yMax = ratings.length ? Math.max(...ratings) : 100;
  const padding = Math.max(20, (yMax - yMin) * .08);
  yMin = Math.floor((yMin - padding) / 50) * 50;
  yMax = Math.ceil((yMax + padding) / 50) * 50;
  if (yMax <= yMin) yMax = yMin + 100;
  const x = time => margin.left + ((time - start) / Math.max(1, end - start)) * innerWidth;
  const y = rating => margin.top + (1 - (rating - yMin) / (yMax - yMin)) * innerHeight;
  const yTicks = Array.from({ length: 6 }, (_, index) => yMin + (yMax - yMin) * index / 5);
  const xTicks = Array.from({ length: 5 }, (_, index) => start + (end - start) * index / 4);
  const grid = yTicks.map(value => `<g><line x1="${margin.left}" y1="${y(value)}" x2="${width - margin.right}" y2="${y(value)}"/><text x="${margin.left - 10}" y="${y(value) + 4}" text-anchor="end">${Math.round(value)}</text></g>`).join('');
  const dates = xTicks.map((value, index) => {
    const tickX = x(value);
    const labelX = index === 0 ? tickX + 12 : tickX;
    return `<g><line x1="${tickX}" y1="${margin.top}" x2="${tickX}" y2="${height - margin.bottom}"/><text x="${labelX}" y="${height - 18}" text-anchor="middle">${new Date(value).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })}</text></g>`;
  }).join('');
  const plotted = selectedPoints.map(({ item, points }) => ({ item, points: points.map(point => ({ ...point, x: x(point.time), y: y(point.rating) })) }));
  const lines = plotted.map(({ item, points }) => {
    const path = points.map((point, pointIndex) => `${pointIndex ? 'L' : 'M'} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(' ');
    return path ? `<path class="players-arena-rating-line" d="${path}" stroke="${graphColorForPlayer(item.player)}" data-player="${escapeAttr(item.player)}"></path>` : '';
  }).join('');
  host.querySelector('svg')?.remove();
  host.querySelector('.players-arena-empty-chart')?.remove();
  host.insertAdjacentHTML('afterbegin', `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Arena rating progression for selected players" onmousemove="onArenaGraphMove(event)" onmouseleave="clearArenaGraphHover()"><g class="players-arena-grid">${grid}${dates}</g><line class="players-arena-axis" x1="${margin.left}" y1="${height - margin.bottom}" x2="${width - margin.right}" y2="${height - margin.bottom}"/><line class="players-arena-axis" x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${height - margin.bottom}"/>${lines}<text class="players-arena-axis-title" transform="translate(15 ${height / 2}) rotate(-90)" text-anchor="middle">Arena rating</text></svg>${selected.length ? '' : '<div class="players-arena-empty-chart">Select up to five players from the legend.</div>'}`);
  graphRenderState = { pointsByPlayer: new Map(plotted.map(entry => [entry.item.player, entry.points])) };
  updateGraphHoverLabel();
}

function seasonDayCount(data) {
  const start = Date.parse(data?.start_utc); const end = Date.parse(data?.end_utc);
  return Number.isFinite(start) && Number.isFinite(end) ? Math.max(1, Math.ceil((end - start) / 86400000)) : 1;
}

function syncDayRange(data) {
  const maxDay = seasonDayCount(data);
  if (!Number.isFinite(graphDayEnd) || graphDayEnd === null) graphDayEnd = maxDay;
  if (graphDayStart < 1 || graphDayStart >= maxDay) graphDayStart = 1;
  if (graphDayEnd > maxDay || graphDayEnd <= graphDayStart) graphDayEnd = maxDay;
}

function onArenaDayInput(event, side) {
  const data = currentData();
  if (!data) return;
  event.target.value = String(event.target.value || '').replace(/\D/g, '');
  const maxDay = seasonDayCount(data);
  const parsed = Number(event.target.value);
  if (side === 'start') graphDayStart = Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
  else graphDayEnd = Number.isFinite(parsed) && parsed > 0 ? parsed : maxDay;
  syncDayRange(data);
  document.getElementById('arenaDayStart').value = graphDayStart;
  document.getElementById('arenaDayEnd').value = graphDayEnd;
  graphHover = null;
  renderGraphCanvas();
}

function nearestPoint(points, targetX) {
  let best = null;
  (points || []).forEach(point => {
    if (!Number.isFinite(point.x) || !Number.isFinite(point.rating)) return;
    if (!best || Math.abs(point.x - targetX) < Math.abs(best.x - targetX)) best = point;
  });
  return best;
}

function onArenaGraphMove(event) {
  const svg = event.currentTarget;
  const line = event.target?.closest?.('.players-arena-rating-line');
  if (!svg || !line || !graphRenderState) { clearArenaGraphHover(); return; }
  const matrix = svg.getScreenCTM?.();
  if (!matrix) return;
  const pointer = svg.createSVGPoint(); pointer.x = event.clientX; pointer.y = event.clientY;
  const local = pointer.matrixTransform(matrix.inverse());
  const point = nearestPoint(graphRenderState.pointsByPlayer.get(line.dataset.player), local.x);
  if (!point) return;
  graphHover = { rating: point.rating, clientX: event.clientX, clientY: event.clientY };
  updateGraphHoverLabel();
}

function clearArenaGraphHover() { graphHover = null; updateGraphHoverLabel(); }

function updateGraphHoverLabel() {
  const host = document.getElementById('arenaChart');
  const tooltip = document.getElementById('arenaGraphTooltip');
  if (!host || !tooltip) return;
  if (!graphHover) { tooltip.classList.remove('visible'); return; }
  tooltip.textContent = wholeOrDash(graphHover.rating);
  tooltip.classList.add('visible');
  const rect = host.getBoundingClientRect();
  const left = graphHover.clientX - rect.left - tooltip.offsetWidth / 2;
  const top = graphHover.clientY - rect.top - tooltip.offsetHeight - 8;
  tooltip.style.left = `${Math.max(8, Math.min(rect.width - tooltip.offsetWidth - 8, left))}px`;
  tooltip.style.top = `${Math.max(4, top)}px`;
}

function renderGraphLegend() {
  const host = document.getElementById('arenaLegendList');
  const data = currentData();
  if (!host || !data) return;
  const term = graphSearch.trim().toLocaleLowerCase();
  syncGraphColorAssignments([...graphSelected].filter(player => data.series?.some(item => item.player === player && (item.ratings || []).length)));
  const visibleSeries = (data.series || []).filter(item => !term || item.player.toLocaleLowerCase().includes(term));
  visibleSeries.sort((a, b) => Number(graphSelected.has(b.player)) - Number(graphSelected.has(a.player)));
  host.innerHTML = visibleSeries.map(item => {
    const selected = graphSelected.has(item.player);
    const disabled = !(item.ratings || []).length;
    const color = selected ? graphColorForPlayer(item.player) : 'transparent';
    return `<button type="button" class="players-arena-legend-item ${selected ? 'active' : ''}" data-player="${escapeAttr(item.player)}" onclick="toggleArenaGraphPlayer(this.dataset.player)" ${disabled ? 'disabled' : ''}><span class="players-arena-legend-swatch" style="background:${color}"></span><span class="players-arena-legend-rank">${item.rank}</span><span>${escapeHtml(item.player)}</span></button>`;
  }).join('');
}

const tooltip = document.getElementById('col-tooltip');
function hideTooltip() { if (tooltip) tooltip.style.display = 'none'; }
document.addEventListener('mouseover', event => {
  if (!mounted || !tooltip) return;
  const source = event.target.closest?.('.col-tip');
  if (!source?.dataset.tip) return;
  tooltip.textContent = source.dataset.tip;
  tooltip.style.display = 'block';
  tooltip.style.left = `${Math.max(8, Math.min(event.clientX + 12, window.innerWidth - tooltip.offsetWidth - 8))}px`;
  tooltip.style.top = `${event.clientY + 18}px`;
});
document.addEventListener('mouseout', event => {
  if (mounted && tooltip && event.target.closest?.('.col-tip')) tooltip.style.display = 'none';
});
document.addEventListener('click', event => {
  if (!mounted) return;
  const option = event.target.closest?.('#arenaPlayerSuggestions button[data-player]');
  if (option) {
    selectArenaPlayerSuggestion(option.dataset.player);
    return;
  }
  if (!event.target.closest?.('.players-search-wrap, #arenaPlayerSuggestions')) {
    arenaPlayerSuggestionsOpen = false;
    document.getElementById('arenaPlayerSuggestions')?.classList.remove('open');
  }
});
document.addEventListener('scroll', () => { if (mounted) positionArenaPlayerSuggestions(); }, true);
window.addEventListener('resize', () => { if (mounted) positionArenaPlayerSuggestions(); });

function escapeHtml(value) { return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;'); }
const escapeAttr = escapeHtml;
