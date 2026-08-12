import {
  cappedNumericRange,
  colorFromStops,
  deltaRangeColor,
  normalizeToRange,
  numericRange,
  playrateColor,
  relativeEloColor,
} from '../color-scales.js?v=20260812-2';
import { formatSignedDeltaAdaptive, mapTooltipLabel } from '../table-cells.js?v=20260812-2';
import { setTopbarDatasetLock } from '../layout.js?v=20260812-2';
import { loadStats } from '../snapshot-cache.js?v=20260812-2';

export const id = 'mw-action-cards';
export const title = 'MW Action Cards';
export const navLabel = 'MW Action Cards';

const SNAPSHOT_BASE = 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/mw-action-cards';
const SNAPSHOTS = {
  general: `${SNAPSHOT_BASE}/general/default-mw.json`,
  by_map: `${SNAPSHOT_BASE}/by-map/default-mw.json`,
  synergies: `${SNAPSHOT_BASE}/synergies/default-mw.json`,
};
const MAPS = [
  ['1a', 'Map 1a: Observation Tower', 'map_1a'], ['2a', 'Map 2a: Outdoor Areas', 'map_2a'],
  ['3a', 'Map 3a: Silver Lake', 'map_3a'], ['4a', 'Map 4a: Commercial Harbor', 'map_4a'],
  ['5a', 'Map 5a: Park Restaurant', 'map_5a'], ['6a', 'Map 6a: Research Institute', 'map_6a'],
  ['7a', 'Map 7a: Ice Cream Parlors', 'map_7a'], ['8a', 'Map 8a: Hollywood Hills', 'map_8a'],
  ['9', 'Map 9: Geographical Zoo', 'map_9'], ['10', 'Map 10: Rescue Station', 'map_10'],
  ['11', 'Map 11: Caves', 'map_11'], ['12', 'Map 12: Artificial Intelligence', 'map_12'],
  ['13', 'Map 13: Drawing Board', 'map_13'], ['14', 'Map 14: Lagoon', 'map_14'],
  ['T1', 'Map T1: Tournament 1', 'map_t1'],
];
const TYPES = ['Animals', 'Association', 'Build', 'Cards', 'Sponsors'];
const VIEWS = ['general', 'draft', 'by_map', 'synergies'];
const CHART_COLORS = [
  '#45d6a1', '#58a6ff', '#ff9f0a', '#ff6685', '#b678f5', '#f4d35e', '#56cfe1',
  '#ef8354', '#9be564', '#d17b88', '#4cc9f0', '#c77dff', '#80ed99', '#f72585',
  '#90e0ef', '#ffb703', '#a8dadc', '#e76f51', '#7bdff2', '#b8f2e6',
];
const SORTABLE = {
  general: new Set(['delta_picked', 'delta_picked_upgraded', 'delta_picked_basic', 'elo_picked', 'picked_pct']),
  draft: new Set(['picked_pct', 'drafted_first_pct', 'drafted_second_pct', 'undrafted_pct']),
  by_map: new Set([...MAPS.map(([, , key]) => key), 'delta_overall']),
  synergies: new Set(['delta_combined', 'delta_actual', 'interaction', 'avg_elo', 'n_picked']),
};

export const mainHtml = `
  <div class="main-header mw-action-cards-main-header">
    <div class="table-meta" id="tableMeta"></div>
    <div class="mw-action-main-controls">
      <div class="maps-h2h-mode mw-action-map-mode" id="mwActionMapMode" role="group" aria-label="By map comparison" hidden>
        <button type="button" class="active" data-mode="raw" onclick="setMwActionMapMode('raw')">Raw</button>
        <button type="button" data-mode="average" onclick="setMwActionMapMode('average')">vs. avg</button>
      </div>
      <div class="mw-action-pair-controls" id="mwActionPairControls" hidden>
        <label>Minimum picks <input class="min-plays-input" id="mwActionMinPicks" type="number" min="0" value="1000" oninput="setMwActionMinimum(this.value)" /></label>
        <label>Rows <select id="mwActionRows" onchange="setMwActionRows(this.value)"><option>25</option><option selected>50</option><option>100</option></select></label>
      </div>
    </div>
  </div>
  <div class="attributes-bar endgames-tabs-bar mw-action-cards-tabs-bar">
    <div class="attributes-bar-header endgames-tabs-header">
      <div class="endgames-tabs mw-action-cards-tabs" role="tablist" aria-label="MW Action Cards views">
        <button class="endgames-tab active" type="button" data-view="general" onclick="setMwActionCardsView('general')">General</button>
        <button class="endgames-tab" type="button" data-view="draft" onclick="setMwActionCardsView('draft')">Draft</button>
        <button class="endgames-tab" type="button" data-view="by_map" onclick="setMwActionCardsView('by_map')">
          <span>By map</span><span class="endgames-graph-toggle" role="button" tabindex="0" title="Show graph" aria-label="Show action cards by map graph" onclick="toggleMwActionMapGraph(event)" onkeydown="onMwActionMapGraphKey(event)">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 19h16"/><path d="M4 5v14"/><path d="M6.5 15.5 10 11l3.5 2.5L18 7"/></svg>
          </span>
        </button>
        <button class="endgames-tab" type="button" data-view="synergies" onclick="setMwActionCardsView('synergies')">Synergies</button>
      </div>
    </div>
  </div>
  <div class="table-wrap mw-action-cards-table-wrap"><div class="table-scroll">
    <table id="statsTable" class="mw-action-cards-table"><thead id="tableHead"></thead><tbody id="tableBody"></tbody></table>
  </div><div class="pagination" id="pagination" hidden></div></div>`;

export const sidebarHtml = `
  <div class="sidebar-header"><span class="sidebar-title">Filters</span><div style="display:flex;align-items:center;gap:6px;">
    <button class="reset-btn" onclick="resetFilters()">Reset</button><button class="sidebar-close-btn" onclick="toggleSidebar()" title="Close filters">x</button>
  </div></div><hr class="divider" />
  <div class="filter-group" id="mwActionPlayerEloGroup"><span class="filter-label">Player ELO</span><div class="range-row">
    <input class="range-input" type="number" id="playerEloMin" placeholder="Min" value="300" min="0" /><input class="range-input" type="number" id="playerEloMax" placeholder="Max" min="0" />
  </div></div>
  <div class="filter-group" id="mwActionOpponentEloGroup"><span class="filter-label">Opponent ELO</span><div class="range-row">
    <input class="range-input" type="number" id="opponentEloMin" placeholder="Min" value="300" min="0" /><input class="range-input" type="number" id="opponentEloMax" placeholder="Max" min="0" />
  </div></div>
  <hr class="divider" id="mwActionMapDivider" />
  <div class="filter-group" id="mwActionMapSection"><div style="display:flex;align-items:baseline;gap:6px;margin-bottom:8px;">
    <span class="filter-label" style="margin-bottom:0">Maps</span><span class="map-select-all-none">(<span class="map-toggle-link" onclick="selectAllMaps()">all</span> / <span class="map-toggle-link" onclick="selectNoneMaps()">none</span>)</span>
  </div><div class="chip-grid" id="mapChips"></div></div><hr class="divider" />
  <div class="filter-group"><span class="filter-label">Date Range</span><input class="date-input" type="text" id="dateFrom" value="2025-01-01" placeholder="yyyy-mm-dd" /><input class="date-input" type="text" id="dateTo" placeholder="yyyy-mm-dd" /></div>
  <hr class="divider" /><div class="filter-group"><div class="toggle-row"><span class="toggle-label">Completed games only</span><label class="toggle"><input type="checkbox" id="completedToggle" /><span class="toggle-track"></span></label></div></div>
  <hr class="divider" /><div class="filter-action-stack"><button class="apply-btn" onclick="applyFiltersFromSidebar()">Apply filters</button></div>`;

let mounted = false;
let requestToken = 0;
let activeView = 'general';
let viewRows = { general: null, by_map: null, synergies: null };
let selectedMaps = MAPS.map(([, full]) => full);
let selectedTypes = new Set(TYPES);
let pairTypeSelections = { synergies: null };
let sortStates = {
  general: { field: 'delta_picked', direction: 'desc' }, draft: { field: 'picked_pct', direction: 'desc' },
  by_map: { field: 'delta_overall', direction: 'desc' }, synergies: { field: 'interaction', direction: 'desc' },
};
let byMapMode = 'raw';
let byMapGraph = false;
let pairSearches = { synergies: ['', ''] };
let minimumPicks = 1000;
let rowsPerPage = 50;
let currentPage = 1;

export function mount({ dataset = 1 } = {}) {
  mounted = true; requestToken += 1; activeView = 'general';
  viewRows = { general: null, by_map: null, synergies: null };
  selectedMaps = MAPS.map(([, full]) => full); selectedTypes = new Set(TYPES);
  pairTypeSelections = { synergies: null };
  byMapMode = 'raw'; byMapGraph = false;
  pairSearches = { synergies: ['', ''] };
  minimumPicks = 1000; rowsPerPage = 50; currentPage = 1;
  Object.assign(window, {
    setMwActionCardsView, sortMwActionCards, toggleMwActionCardTypePopup, toggleMwActionCardType,
    toggleMwPairTypePopup, toggleMwPairType, selectAllMwPairTypes, selectNoneMwPairTypes,
    openMwActionCardSearch, renderMwActionSearchChoices, selectMwActionCardSearch, clearMwActionCardSearch,
    setMwActionMapMode, toggleMwActionMapGraph, onMwActionMapGraphKey,
    setMwActionMinimum, setMwActionRows, goMwActionPage,
    resetFilters, applyFiltersFromSidebar, selectAllMaps, selectNoneMaps, toggleMwActionCardMap,
  });
  setTopbarDatasetLock(1);
  if (Number(dataset) !== 1) window.dispatchEvent(new CustomEvent('arknova:set-dataset', { detail: { value: 1 } }));
  document.addEventListener('click', closePopupsOnOutsideClick);
  document.addEventListener('mouseover', showTooltip); document.addEventListener('mousemove', moveTooltip); document.addEventListener('mouseout', hideTooltip);
  window.addEventListener('resize', repositionMwActionPopups);
  document.addEventListener('scroll', repositionMwActionPopups, true);
  renderMapChips(); syncViewChrome(); void loadView('general', requestToken);
}

export function unmount() {
  mounted = false; requestToken += 1;
  document.removeEventListener('click', closePopupsOnOutsideClick);
  document.removeEventListener('mouseover', showTooltip); document.removeEventListener('mousemove', moveTooltip); document.removeEventListener('mouseout', hideTooltip);
  window.removeEventListener('resize', repositionMwActionPopups);
  document.removeEventListener('scroll', repositionMwActionPopups, true);
  setTopbarDatasetLock(null);
}

export function setDataset(value) {
  if (Number(value) === 1) return;
  setTopbarDatasetLock(1); window.dispatchEvent(new CustomEvent('arknova:set-dataset', { detail: { value: 1 } }));
}

function canonicalView(view = activeView) { return view === 'draft' ? 'general' : view; }
function rowsForView(view = activeView) { return viewRows[canonicalView(view)] || []; }

function setMwActionCardsView(view) {
  activeView = VIEWS.includes(view) ? view : 'general'; currentPage = 1;
  syncViewChrome();
  const canonical = canonicalView();
  if (viewRows[canonical] !== null) render(); else void loadView(canonical, ++requestToken);
}

function syncViewChrome() {
  document.querySelectorAll('.mw-action-cards-tabs .endgames-tab').forEach(button => button.classList.toggle('active', button.dataset.view === activeView));
  const graphToggle = document.querySelector('.mw-action-cards-tabs [data-view="by_map"] .endgames-graph-toggle');
  graphToggle?.classList.toggle('graph-active', activeView === 'by_map' && byMapGraph);
  const mapMode = document.getElementById('mwActionMapMode'); if (mapMode) mapMode.hidden = activeView !== 'by_map';
  const pairControls = document.getElementById('mwActionPairControls'); if (pairControls) pairControls.hidden = activeView !== 'synergies';
  const hideMaps = activeView === 'by_map';
  if (document.getElementById('mwActionMapSection')) document.getElementById('mwActionMapSection').hidden = hideMaps;
  if (document.getElementById('mwActionMapDivider')) document.getElementById('mwActionMapDivider').hidden = hideMaps;
}

function params(view = canonicalView()) {
  const value = id => document.getElementById(id)?.value ?? '';
  const playerMin = value('playerEloMin');
  const playerMax = value('playerEloMax');
  const opponentMin = value('opponentEloMin');
  const opponentMax = value('opponentEloMax');
  return {
    stats_page: 'mw_action_cards', mw_action_cards_view: view, is_mw: 1,
    maps: selectedMaps,
    player_elo_min: playerMin === '' ? 0 : Number(playerMin),
    player_elo_max: playerMax === '' ? null : Number(playerMax),
    opponent_elo_min: opponentMin === '' ? 0 : Number(opponentMin),
    opponent_elo_max: opponentMax === '' ? null : Number(opponentMax),
    date_from: value('dateFrom') || null, date_to: value('dateTo') || null,
    completed_only: Boolean(document.getElementById('completedToggle')?.checked),
    arena_only: Boolean(document.getElementById('globalArenaOnly')?.checked),
    tournament_only: Boolean(document.getElementById('globalTournamentOnly')?.checked),
  };
}

function isDefault(request, view) {
  return request.player_elo_min === 300 && request.player_elo_max === null
    && request.opponent_elo_min === 300 && request.opponent_elo_max === null
    && request.date_from === '2025-01-01' && request.date_to === null
    && !request.completed_only && !request.arena_only && !request.tournament_only
    && (view === 'by_map' || selectedMaps.length === MAPS.length);
}

async function loadView(view, token) {
  if (view !== 'by_map' && !selectedMaps.length) { viewRows[view] = []; render(); return; }
  const wrap = document.querySelector('.mw-action-cards-table-wrap');
  const preserve = rowsForView().length > 0;
  if (preserve) wrap?.classList.add('stats-updating'); else renderLoading();
  try {
    const request = params(view);
    const payload = await loadStats(request, isDefault(request, view) ? SNAPSHOTS[view] : null);
    if (!mounted || token !== requestToken) return;
    viewRows[view] = Array.isArray(payload.data) ? payload.data : [];
    if (view === 'synergies' && pairTypeSelections.synergies === null) pairTypeSelections.synergies = new Set(pairTypeOptions(viewRows[view]));
    render();
  } catch (error) {
    if (mounted && token === requestToken) preserve ? console.error('Could not update MW Action Cards', error) : renderError(error);
  } finally {
    if (mounted && token === requestToken) wrap?.classList.remove('stats-updating');
  }
}

function render() {
  syncViewChrome();
  if (activeView === 'general' || activeView === 'draft') renderGeneralDraft();
  else if (activeView === 'by_map') renderByMap();
  else renderPairs();
}

function renderGeneralDraft() {
  const rows = rowsForView(); renderGeneralDraftHead();
  const globallyRanked = [...rows].sort(compareRows).map((row, index) => ({ ...row, global_rank: index + 1 }));
  const visible = globallyRanked.filter(row => selectedTypes.has(String(row.type)));
  setMeta(`<strong>${visible.length}</strong> action cards`); hidePagination();
  const body = document.getElementById('tableBody');
  const rateRanges = Object.fromEntries(['picked_pct', 'drafted_first_pct', 'drafted_second_pct', 'undrafted_pct'].map(field => [field, numericRange(rows, row => row[field])]));
  if (activeView === 'draft') {
    body.innerHTML = visible.map(row => `<tr><td class="rank-cell">${row.global_rank}</td>${typeCell(row.type)}<td class="card-name">${escapeHtml(row.card_name)}</td>
      ${percentageCell(row, 'picked_pct', 'picked_n', rateRanges.picked_pct, 'blue')}${percentageCell(row, 'drafted_first_pct', 'drafted_first_n', rateRanges.drafted_first_pct, 'violet')}${percentageCell(row, 'drafted_second_pct', 'drafted_second_n', rateRanges.drafted_second_pct, 'violet')}${percentageCell(row, 'undrafted_pct', 'undrafted_n', rateRanges.undrafted_pct, 'violet')}</tr>`).join('') || emptyRow(7);
    return;
  }
  const deltaRanges = Object.fromEntries(['delta_picked', 'delta_picked_upgraded', 'delta_picked_basic'].map(field => [field, cappedNumericRange(rows, row => row[field])]));
  const eloRange = numericRange(rows, row => row.elo_picked);
  body.innerHTML = visible.map(row => `<tr><td class="rank-cell">${row.global_rank}</td>${typeCell(row.type)}<td class="card-name">${escapeHtml(row.card_name)}</td>
    ${deltaCell(row, 'delta_picked', deltaRanges.delta_picked, true)}${deltaCell(row, 'delta_picked_upgraded', deltaRanges.delta_picked_upgraded)}${deltaCell(row, 'delta_picked_basic', deltaRanges.delta_picked_basic)}${eloCell(row.elo_picked, eloRange)}${percentageCell(row, 'picked_pct', 'picked_n', rateRanges.picked_pct, 'blue')}</tr>`).join('') || emptyRow(8);
}

function renderGeneralDraftHead() {
  setTableClasses(activeView === 'draft' ? 'mw-action-cards-draft-table' : 'mw-action-cards-general-table');
  const head = document.getElementById('tableHead');
  if (activeView === 'draft') head.innerHTML = `<tr><th style="width:5%">#</th>${typeHeader('15%')}<th style="width:15%">Card</th>${sortableHeader('picked_pct', 'Picked%', 'tables where the card was picked / tables where it was available', '16.25%')}${sortableHeader('drafted_first_pct', 'Drafted% (1st)', 'tables where the card appeared in either first draft slot / available tables', '16.25%')}${sortableHeader('drafted_second_pct', 'Drafted% (2nd)', 'tables where the card appeared in either second draft slot / available tables', '16.25%')}${sortableHeader('undrafted_pct', 'Undrafted%', 'tables where the card appeared in either returned third slot / available tables', '16.25%')}</tr>`;
  else head.innerHTML = `<tr><th style="width:5%">#</th>${typeHeader('15%')}<th style="width:15%">Card</th>${sortableHeader('delta_picked', '&Delta; Elo', 'average Elo delta when picked', '12%')}${sortableHeader('delta_picked_upgraded', '&Delta; Elo (Upg)', 'average Elo delta when picked and upgraded', '12%')}${sortableHeader('delta_picked_basic', '&Delta; Elo (Basic)', 'average Elo delta when picked and not upgraded', '12%')}${sortableHeader('elo_picked', 'Elo', 'average pre-match Elo of players who picked this card', '10%')}${sortableHeader('picked_pct', 'Picked%', 'tables where the card was picked / tables where it was available', '19%')}</tr>`;
}

function renderByMap() {
  renderByMapHead();
  const rows = rowsForView();
  const ranked = [...rows].sort(compareRows).map((row, index) => ({ ...row, global_rank: index + 1 }));
  const visible = ranked;
  setMeta(byMapGraph ? '' : `<strong>${visible.length}</strong> action cards`); hidePagination();
  if (byMapGraph) { renderByMapGraph(visible); return; }
  const ranges = Object.fromEntries([...MAPS.map(([, , key]) => key), 'delta_overall'].map(field => [field, cappedNumericRange(rows, row => byMapValue(row, field))]));
  document.getElementById('tableBody').innerHTML = visible.map(row => `<tr><td class="rank-cell">${row.global_rank}</td><td class="card-name">${escapeHtml(row.card_name)}</td>${MAPS.map(([, , key]) => mapDeltaCell(row, key, ranges[key])).join('')}${mapDeltaCell(row, 'delta_overall', ranges.delta_overall, true)}</tr>`).join('') || emptyRow(18);
}

function renderByMapHead() {
  setTableClasses('mw-action-cards-by-map-table');
  const head = document.getElementById('tableHead');
  head.innerHTML = byMapGraph ? '' : `<tr><th style="width:4%">#</th><th style="width:16%">Action Card</th>${MAPS.map(([short, full, key]) => mapSortableHeader(key, short, mapTooltipLabel(full), '5%')).join('')}${sortableHeader('delta_overall', '&Delta;', '', '5%')}</tr>`;
}

function renderPairs() {
  renderPairHead();
  const all = rowsForView();
  const projectedAll = all.map(projectPairRow);
  const selectedPairTypes = pairTypeSelections[activeView] || new Set();
  const matchingBeforeMinimum = projectedAll.filter(row => selectedPairTypes.has(row.pair_type) && pairSearchMatch(row));
  const candidates = all.filter(row => Number(row.n_picked || 0) >= minimumPicks).sort(compareRows);
  const ranked = candidates.map((row, index) => ({ ...row, global_rank: index + 1 }));
  const visible = ranked.map(projectPairRow).filter(row => selectedPairTypes.has(row.pair_type) && pairSearchMatch(row));
  window.setMinimumPlaysWarning?.(
    document.getElementById('mwActionMinPicks'),
    minimumPicks > 0 && matchingBeforeMinimum.length > 0 && visible.length === 0,
  );
  const totalPages = Math.max(1, Math.ceil(visible.length / rowsPerPage)); currentPage = Math.min(currentPage, totalPages);
  const start = visible.length ? (currentPage - 1) * rowsPerPage : 0;
  const page = visible.slice(start, start + rowsPerPage);
  setMeta(`<span class="meta-prefix">Showing </span><strong>${visible.length ? start + 1 : 0}-${Math.min(start + rowsPerPage, visible.length)}</strong> of <strong>${visible.length}</strong> combinations`);
  const expectedField = 'delta_combined';
  const residualField = 'interaction';
  const ranges = {
    delta_1: cappedNumericRange(all, row => row.delta_1), delta_2: cappedNumericRange(all, row => row.delta_2),
    expected: cappedNumericRange(all, row => row[expectedField]), actual: cappedNumericRange(all, row => row.delta_actual),
    residual: cappedNumericRange(all, row => row[residualField]), elo: numericRange(all, row => row.avg_elo),
  };
  document.getElementById('tableBody').innerHTML = page.map(row => `<tr><td class="rank-cell">${row.global_rank}</td>${pairCardCell(row.display_card_1, row.display_delta_1, ranges.delta_1)}${pairCardCell(row.display_card_2, row.display_delta_2, ranges.delta_2)}${simpleDeltaCell(row[expectedField], ranges.expected)}${deltaActualCell(row, ranges.actual)}${residualCell(row[residualField], ranges.residual)}${eloCell(row.avg_elo, ranges.elo)}<td class="n-cell">${formatInteger(row.n_picked)}</td>${pairTypeCell(row)}</tr>`).join('') || emptyRow(9);
  renderPagination(totalPages);
}

function renderPairHead() {
  setTableClasses('combinations-pair-table mw-action-pair-table');
  document.getElementById('tableHead').innerHTML = `<tr><th style="width:5%">#</th>${pairCardSearchHeader(1, '18%', 'Action Card 1')}${pairCardSearchHeader(2, '18%', 'Action Card 2')}${sortableHeader('delta_combined', '&Delta; (Sum)', '&Delta; Card 1 + &Delta; Card 2', '11%')}${sortableHeader('delta_actual', '&Delta; (Actual)', 'average Elo delta when both cards were picked', '11%')}${sortableHeader('interaction', 'Synergy', '&Delta; Actual - &Delta; Sum', '11%')}${sortableHeader('avg_elo', 'Elo', 'average oriented player pre-match Elo', '7%')}${sortableHeader('n_picked', 'Picked', 'number of player-game observations', '9%')}${pairTypeHeader('10%')}</tr>`;
}

function setTableClasses(extra) {
  const table = document.getElementById('statsTable');
  table.className = `mw-action-cards-table ${extra}`;
}

function compareRows(a, b) {
  const state = sortStates[activeView]; const av = sortValue(a, state.field); const bv = sortValue(b, state.field);
  if (av === null && bv !== null) return 1; if (bv === null && av !== null) return -1;
  if (typeof av === 'string' || typeof bv === 'string') { const result = String(av ?? '').localeCompare(String(bv ?? '')); if (result) return state.direction === 'asc' ? result : -result; }
  else if (av !== null && bv !== null && av !== bv) return state.direction === 'asc' ? av - bv : bv - av;
  return Number(a.card_order ?? a.card_1_order ?? 0) - Number(b.card_order ?? b.card_1_order ?? 0) || Number(a.card_2_order ?? 0) - Number(b.card_2_order ?? 0);
}
function sortValue(row, field) { const value = row[field]; if (value === null || value === undefined || value === '') return null; const number = Number(value); return Number.isFinite(number) ? number : String(value); }

function sortableHeader(field, label, tooltip, width) {
  const state = sortStates[activeView]; const active = state?.field === field; const arrow = active ? (state.direction === 'desc' ? '\u2193' : '\u2191') : '\u2195';
  return `<th class="${active ? 'sorted' : ''}" style="width:${width}" onclick="sortMwActionCards('${field}')"><span class="mw-action-sort-label">${label}${tooltip ? `<span class="col-tip" data-tip="${escapeAttr(tooltip)}">?</span>` : ''}<span class="sort-arrow ${active ? 'active' : ''}">${arrow}</span></span></th>`;
}
function mapSortableHeader(field, label, tooltip, width) {
  const state = sortStates[activeView]; const active = state?.field === field; const arrow = active ? (state.direction === 'desc' ? '\u2193' : '\u2191') : '\u2195';
  return `<th class="maps-custom-tip ${active ? 'sorted' : ''}" data-tip="${escapeAttr(tooltip)}" style="width:${width};text-align:center" onclick="sortMwActionCards('${field}')"><span class="mw-action-sort-label">${escapeHtml(label)}<span class="sort-arrow ${active ? 'active' : ''}">${arrow}</span></span></th>`;
}
function sortMwActionCards(field) { if (!SORTABLE[activeView]?.has(field)) return; const state = sortStates[activeView]; if (state.field === field) state.direction = state.direction === 'asc' ? 'desc' : 'asc'; else sortStates[activeView] = { field, direction: 'desc' }; currentPage = 1; render(); }

function typeHeader(width) {
  return `<th class="type-filter-header ${selectedTypes.size === TYPES.length ? '' : 'type-filter-active'}" id="mwActionTypeHeader" style="width:${width}" onclick="toggleMwActionCardTypePopup(event)"><span class="type-filter-label">Type <span class="type-filter-indicator ${selectedTypes.size === TYPES.length ? 'type-filter-icon' : ''}">${selectedTypes.size === TYPES.length ? '' : `${selectedTypes.size}/5`}</span></span><div class="type-filter-popup mw-action-type-popup" id="mwActionTypePopup" onclick="event.stopPropagation()">${TYPES.map(type => `<button class="chip ${selectedTypes.has(type) ? 'active' : ''}" data-type="${type}" onclick="toggleMwActionCardType(event, this.dataset.type)">${type}</button>`).join('')}</div></th>`;
}
function pairTypeHeader(width) {
  const options = pairTypeOptions(rowsForView()); const selected = pairTypeSelections[activeView] || new Set(); const narrowed = selected.size !== options.length;
  return `<th class="type-filter-header mw-pair-type-header ${narrowed ? 'type-filter-active' : ''}" id="mwPairTypeHeader" style="width:${width}" onclick="toggleMwPairTypePopup(event)"><span class="type-filter-label">Type <span class="type-filter-indicator ${narrowed ? '' : 'type-filter-icon'}">${narrowed ? `${selected.size}/${options.length}` : ''}</span></span><div class="type-filter-popup mw-pair-type-popup" id="mwPairTypePopup" onclick="event.stopPropagation()"><div class="combination-popup-actions map-select-all-none"><span class="map-toggle-link" onclick="selectAllMwPairTypes(event)">all</span> / <span class="map-toggle-link" onclick="selectNoneMwPairTypes(event)">none</span></div><div class="mw-pair-type-options">${options.map(type => `<button class="chip ${selected.has(type) ? 'active' : ''}" data-type="${escapeAttr(type)}" onclick="toggleMwPairType(this.dataset.type,event)">${escapeHtml(type)}</button>`).join('')}</div></div></th>`;
}
function pairTypeOptions(data) { return [...new Set(data.map(row => String(row.pair_type || '')))].filter(Boolean).sort((a, b) => a.localeCompare(b)); }

function pairCardSearchHeader(slot, width, label = `Action Card ${slot}`) {
  const selected = pairSearches[activeView][slot - 1];
  const action = selected ? `clearMwActionCardSearch(${slot},event)` : `openMwActionCardSearch(${slot},event)`;
  const title = selected ? `Clear Action Card ${slot} filter` : `Search Action Card ${slot}`;
  return `<th class="card-search-header combination-card-filter-header" style="width:${width}"><div class="card-header-content"><button class="card-search-btn ${selected ? 'search-active combination-filter-clear' : ''}" type="button" title="${title}" aria-label="${title}" onclick="${action}">${selected ? '&#10005;' : '&#128269;'}</button><span class="card-header-title">${escapeHtml(label)}</span></div><div class="combination-header-popup combination-card-popup" id="mwActionSearchPopup${slot}" onclick="event.stopPropagation()"><input class="abilities-search-input" type="text" placeholder="Search action cards..." oninput="renderMwActionSearchChoices(${slot},this.value)"/><div class="combination-card-choice-list" id="mwActionSearchChoices${slot}"></div></div></th>`;
}

function toggleMwActionCardTypePopup(event) {
  event.stopPropagation();
  const popup = document.getElementById('mwActionTypePopup');
  if (!popup) return;
  const opening = !popup.classList.contains('open');
  closeAllPopups();
  popup.classList.toggle('open', opening);
  if (opening) {
    positionMwActionTypePopup(popup);
    requestAnimationFrame(() => positionMwActionTypePopup(popup));
  }
}
function toggleMwActionCardType(event, type) {
  event.stopPropagation();
  selectedTypes.has(type) ? selectedTypes.delete(type) : selectedTypes.add(type);
  render();
  const popup = document.getElementById('mwActionTypePopup');
  popup?.classList.add('open');
  if (popup) {
    positionMwActionTypePopup(popup);
    requestAnimationFrame(() => positionMwActionTypePopup(popup));
  }
}
function positionMwActionTypePopup(popup = document.getElementById('mwActionTypePopup')) {
  const anchor = document.getElementById('mwActionTypeHeader');
  if (!popup || !anchor || !popup.classList.contains('open')) return;
  const margin = 8;
  const rect = anchor.getBoundingClientRect();
  if (rect.bottom < 0 || rect.top > window.innerHeight || rect.right < 0 || rect.left > window.innerWidth) {
    popup.classList.remove('open');
    return;
  }
  const popupRect = popup.getBoundingClientRect();
  const width = Math.min(popupRect.width || 142, window.innerWidth - margin * 2);
  const height = popupRect.height;
  const left = Math.max(margin, Math.min(rect.left + (rect.width - width) / 2, window.innerWidth - width - margin));
  const below = rect.bottom;
  const top = below + height <= window.innerHeight - margin ? below : Math.max(margin, rect.top - height);
  popup.style.maxWidth = `${Math.max(0, window.innerWidth - margin * 2)}px`;
  popup.style.left = `${left}px`;
  popup.style.top = `${top}px`;
}
function toggleMwPairTypePopup(event) {
  event.stopPropagation();
  const popup = document.getElementById('mwPairTypePopup');
  if (!popup) return;
  const opening = !popup.classList.contains('open');
  popup.classList.toggle('open', opening);
  if (opening) positionMwPairTypePopup(popup);
}
function toggleMwPairType(type, event) {
  event.stopPropagation();
  const selected = pairTypeSelections[activeView];
  selected.has(type) ? selected.delete(type) : selected.add(type);
  currentPage = 1;
  render();
  const popup = document.getElementById('mwPairTypePopup');
  popup?.classList.add('open');
  if (popup) positionMwPairTypePopup(popup);
}
function selectAllMwPairTypes(event) {
  event.stopPropagation();
  pairTypeSelections[activeView] = new Set(pairTypeOptions(rowsForView()));
  currentPage = 1;
  render();
  const popup = document.getElementById('mwPairTypePopup');
  popup?.classList.add('open');
  if (popup) positionMwPairTypePopup(popup);
}
function selectNoneMwPairTypes(event) {
  event.stopPropagation();
  pairTypeSelections[activeView] = new Set();
  currentPage = 1;
  render();
  const popup = document.getElementById('mwPairTypePopup');
  popup?.classList.add('open');
  if (popup) positionMwPairTypePopup(popup);
}
function positionMwPairTypePopup(popup) {
  const anchor = document.getElementById('mwPairTypeHeader');
  if (!popup || !anchor) return;
  const margin = 8;
  const width = Math.min(220, Math.max(0, window.innerWidth - margin * 2));
  const height = popup.getBoundingClientRect().height || 190;
  const rect = anchor.getBoundingClientRect();
  const left = Math.max(margin, Math.min(rect.left, window.innerWidth - width - margin));
  const top = rect.bottom + height <= window.innerHeight - margin
    ? rect.bottom
    : Math.max(margin, rect.top - height);
  popup.style.width = `${width}px`;
  popup.style.maxWidth = `${width}px`;
  popup.style.left = `${left}px`;
  popup.style.top = `${top}px`;
}
function repositionMwPairTypePopup() {
  const popup = document.getElementById('mwPairTypePopup');
  if (popup?.classList.contains('open')) positionMwPairTypePopup(popup);
}

function positionMwActionSearchPopup(popup, anchor, preferredWidth = 280) {
  if (!popup || !anchor || !popup.classList.contains('open')) return;
  const margin = 8;
  const rect = anchor.getBoundingClientRect();
  if (rect.bottom < 0 || rect.top > window.innerHeight || rect.right < 0 || rect.left > window.innerWidth) {
    popup.classList.remove('open');
    return;
  }
  const tableRect = anchor.closest('.table-scroll')?.getBoundingClientRect();
  const width = Math.min(preferredWidth, window.innerWidth - margin * 2);
  const rightLimit = Math.min(window.innerWidth - margin, tableRect?.right ?? window.innerWidth - margin);
  const left = Math.max(margin, Math.min(rect.left, rightLimit - width));
  const height = popup.getBoundingClientRect().height;
  const top = rect.bottom + height <= window.innerHeight - margin ? rect.bottom : Math.max(margin, rect.top - height);
  popup.style.width = `${width}px`;
  popup.style.left = `${left}px`;
  popup.style.top = `${top}px`;
}

function repositionMwActionPopups() {
  positionMwActionTypePopup();
  repositionMwPairTypePopup();
  [1, 2].forEach(slot => {
    const popup = document.getElementById(`mwActionSearchPopup${slot}`);
    const anchor = popup?.closest('th');
    if (popup?.classList.contains('open')) positionMwActionSearchPopup(popup, anchor);
  });
}

function cardCatalogOptions() { const data = rowsForView(); const map = new Map(); data.forEach(row => { if (row.card_name) map.set(row.card_name, Number(row.card_order || 0)); if (row.card_1_name) map.set(row.card_1_name, Number(row.card_1_order || 0)); if (row.card_2_name) map.set(row.card_2_name, Number(row.card_2_order || 0)); }); return [...map].sort((a, b) => a[1] - b[1]).map(([name]) => name); }
function openMwActionCardSearch(slot, event) {
  event.stopPropagation();
  closeAllPopups();
  const popup = document.getElementById(`mwActionSearchPopup${slot}`);
  const anchor = event.currentTarget.closest('th');
  popup?.classList.add('open');
  renderMwActionSearchChoices(slot, '');
  if (popup) {
    positionMwActionSearchPopup(popup, anchor);
    requestAnimationFrame(() => positionMwActionSearchPopup(popup, anchor));
    popup.querySelector('input')?.focus({ preventScroll: true });
  }
}
function renderMwActionSearchChoices(slot, term) {
  const host = document.getElementById(`mwActionSearchChoices${slot}`);
  if (!host) return;
  const query = String(term || '').toLowerCase();
  const matches = cardCatalogOptions().filter(name => name.toLowerCase().includes(query));
  host.innerHTML = matches.map(name => `<button class="combination-card-choice" type="button" data-card="${escapeAttr(name)}" onclick="selectMwActionCardSearch(${slot},this.dataset.card)">${escapeHtml(name)}</button>`).join('') || '<div class="abilities-list-empty">No action cards match.</div>';
  const popup = document.getElementById(`mwActionSearchPopup${slot}`);
  if (popup?.classList.contains('open')) positionMwActionSearchPopup(popup, popup.closest('th'));
}
function selectMwActionCardSearch(slot, name) { if (slot < 1) return; pairSearches[activeView][slot - 1] = name; currentPage = 1; closeAllPopups(); render(); }
function clearMwActionCardSearch(slot, event) { event?.stopPropagation(); if (slot < 1) return; pairSearches[activeView][slot - 1] = ''; currentPage = 1; render(); }

function projectPairRow(row) {
  const [one, two] = pairSearches.synergies;
  const swap = (one && row.card_2_name === one) || (!one && two && row.card_1_name === two);
  return { ...row, display_card_1: swap ? row.card_2_name : row.card_1_name, display_card_2: swap ? row.card_1_name : row.card_2_name, display_delta_1: swap ? row.delta_2 : row.delta_1, display_delta_2: swap ? row.delta_1 : row.delta_2 };
}
function pairSearchMatch(row) { const [one, two] = pairSearches[activeView]; return (!one || row.display_card_1 === one) && (!two || row.display_card_2 === two); }

function setMwActionMapMode(mode) { byMapMode = mode === 'average' ? 'average' : 'raw'; document.querySelectorAll('#mwActionMapMode button').forEach(button => button.classList.toggle('active', button.dataset.mode === byMapMode)); render(); }
function toggleMwActionMapGraph(event) { event?.stopPropagation(); if (activeView !== 'by_map') activeView = 'by_map'; byMapGraph = !byMapGraph; syncViewChrome(); if (viewRows.by_map !== null) render(); else void loadView('by_map', ++requestToken); }
function onMwActionMapGraphKey(event) { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); toggleMwActionMapGraph(event); } }
function byMapValue(row, field) { const raw = finiteOrNull(row[field]); if (raw === null || field === 'delta_overall' || byMapMode === 'raw') return raw; const overall = finiteOrNull(row.delta_overall); return overall === null ? null : raw - overall; }

function renderByMapGraph(data) {
  const body = document.getElementById('tableBody'); body.innerHTML = '<tr><td colspan="18" class="chart-host-cell"></td></tr>';
  body.querySelector('.chart-host-cell')?.appendChild(buildByMapChart(data));
}
function buildByMapChart(data) {
  const wrap = document.createElement('div'); wrap.className = 'cp-dist-chart-wrap mw-action-map-chart-wrap';
  const chart = document.createElement('div'); chart.className = 'cp-dist-chart';
  const legend = document.createElement('div'); legend.className = 'cp-dist-legend';
  const controls = document.createElement('div'); controls.className = 'cp-dist-legend-controls'; controls.innerHTML = '<span>Action cards</span><span>(<button type="button" data-action="all">all</button> / <button type="button" data-action="none">none</button>)</span><input class="abilities-search-input mw-action-legend-search" type="search" placeholder="Search..." />';
  const list = document.createElement('div'); list.className = 'cp-dist-legend-list';
  const tooltip = document.createElement('div'); tooltip.className = 'cp-dist-tooltip';
  const selected = new Set(data.map((_, index) => index));
  const values = data.flatMap(row => MAPS.map(([, , key]) => byMapValue(row, key))).filter(Number.isFinite);
  let min = values.length ? Math.min(0, ...values) : -1; let max = values.length ? Math.max(0, ...values) : 1; const pad = Math.max(0.1, (max - min) * 0.08); min -= pad; max += pad;
  const width = 900; const height = 430; const margin = { top: 22, right: 22, bottom: 48, left: 58 }; const iw = width - margin.left - margin.right; const ih = height - margin.top - margin.bottom;
  const x = index => margin.left + index / (MAPS.length - 1) * iw; const y = value => margin.top + ih - (value - min) / (max - min) * ih;
  const ns = 'http://www.w3.org/2000/svg'; const svg = document.createElementNS(ns, 'svg'); svg.setAttribute('viewBox', `0 0 ${width} ${height}`); svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', 'MW Action Cards Elo delta by map');
  const svgEl = (tag, attrs) => { const el = document.createElementNS(ns, tag); Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, value)); svg.appendChild(el); return el; };
  for (let i = 0; i <= 4; i += 1) { const tick = min + (max - min) * i / 4; const gy = y(tick); svgEl('line', { x1: margin.left, x2: width - margin.right, y1: gy, y2: gy, class: 'cp-dist-grid' }); const label = svgEl('text', { x: margin.left - 10, y: gy + 4, 'text-anchor': 'end', class: 'cp-dist-axis-label' }); label.textContent = formatSignedDeltaAdaptive(tick, true); }
  MAPS.forEach(([short], index) => { const label = svgEl('text', { x: x(index), y: height - 15, 'text-anchor': 'middle', class: 'cp-dist-axis-label' }); label.textContent = short; });
  svgEl('line', { x1: margin.left, x2: width - margin.right, y1: margin.top + ih, y2: margin.top + ih, class: 'cp-dist-axis' }); svgEl('line', { x1: margin.left, x2: margin.left, y1: margin.top, y2: margin.top + ih, class: 'cp-dist-axis' });
  if (min <= 0 && max >= 0) svgEl('line', { x1: margin.left, x2: width - margin.right, y1: y(0), y2: y(0), class: 'icons-chart-zero' });
  const sync = () => { svg.querySelectorAll('.cp-dist-line,.cp-dist-dot').forEach(el => el.classList.toggle('deselected', !selected.has(Number(el.dataset.index)))); list.querySelectorAll('.cp-dist-legend-item').forEach(el => { const active = selected.has(Number(el.dataset.index)); el.classList.toggle('deselected', !active); el.setAttribute('aria-pressed', String(active)); }); };
  controls.addEventListener('click', event => { if (event.target.dataset.action === 'all') data.forEach((_, i) => selected.add(i)); if (event.target.dataset.action === 'none') selected.clear(); sync(); });
  controls.querySelector('input').addEventListener('input', event => { const q = event.target.value.toLowerCase(); list.querySelectorAll('.cp-dist-legend-item').forEach(item => { item.hidden = !item.dataset.name.includes(q); }); });
  data.forEach((row, rowIndex) => {
    const color = CHART_COLORS[Number(row.card_order || rowIndex + 1) - 1]; const points = MAPS.map((map, index) => { const value = byMapValue(row, map[2]); return Number.isFinite(value) ? { value, index, x: x(index), y: y(value) } : null; });
    let path = ''; let open = false; points.forEach(point => { if (!point) { open = false; return; } path += `${open ? 'L' : 'M'} ${point.x.toFixed(2)} ${point.y.toFixed(2)} `; open = true; });
    if (path) { const line = svgEl('path', { d: path.trim(), class: 'cp-dist-line', stroke: color }); line.dataset.index = rowIndex; line.addEventListener('mousemove', event => { const rect = svg.getBoundingClientRect(); const px = (event.clientX - rect.left) / rect.width * width; const nearest = points.filter(Boolean).reduce((best, point) => !best || Math.abs(point.x - px) < Math.abs(best.x - px) ? point : best, null); if (!nearest) return; tooltip.textContent = formatSignedDeltaAdaptive(nearest.value, true); tooltip.style.display = 'block'; const chartRect = chart.getBoundingClientRect(); tooltip.style.left = `${Math.min(event.clientX - chartRect.left + 10, chartRect.width - 70)}px`; tooltip.style.top = `${Math.max(8, event.clientY - chartRect.top - 30)}px`; }); line.addEventListener('mouseleave', () => { tooltip.style.display = 'none'; }); }
    points.filter(Boolean).forEach(point => { const dot = svgEl('circle', { cx: point.x, cy: point.y, r: 2.7, class: 'cp-dist-dot', fill: color }); dot.dataset.index = rowIndex; });
    const item = document.createElement('button'); item.type = 'button'; item.className = 'cp-dist-legend-item'; item.dataset.index = rowIndex; item.dataset.name = row.card_name.toLowerCase(); item.setAttribute('aria-pressed', 'true'); item.innerHTML = `<span class="cp-dist-legend-swatch" style="background:${color}"></span><span>${escapeHtml(row.card_name)}</span>`; item.addEventListener('click', () => { selected.has(rowIndex) ? selected.delete(rowIndex) : selected.add(rowIndex); sync(); }); list.appendChild(item);
  });
  legend.append(controls, list); chart.append(svg, tooltip); wrap.append(chart, legend); sync(); return wrap;
}

function mapDeltaCell(row, field, range, overall = false) { const value = byMapValue(row, field); if (value === null) return '<td class="unavailable-cell">-</td>'; const ci = byMapMode === 'raw' || overall ? ciAttrs(row, field, range) : ''; return `<td class="delta ${ci ? 'delta-ci-cell' : ''}"${ci} style="color:${deltaRangeColor(value, range.min, range.max)}">${formatSignedDeltaAdaptive(value, true)}</td>`; }
function ciAttrs(row, field, range) { return ` data-ci-low="${escapeAttr(row[`${field}_ci95_low`] ?? '')}" data-ci-high="${escapeAttr(row[`${field}_ci95_high`] ?? '')}" data-ci-n="${escapeAttr(row[`${field}_ci95_n`] ?? '')}" data-ci-color-min="${escapeAttr(range?.min ?? '')}" data-ci-color-max="${escapeAttr(range?.max ?? '')}"`; }
function deltaCell(row, field, range, primary = false) { const value = finiteOrNull(row[field]); if (value === null) return '<td class="unavailable-cell">-</td>'; return `<td class="delta delta-ci-cell ${primary ? 'mw-action-delta-primary' : 'mw-action-delta-secondary'}"${ciAttrs(row, field, range)} style="color:${deltaRangeColor(value, range.min, range.max)}">${formatSignedDeltaAdaptive(value, true)}</td>`; }
function simpleDeltaCell(raw, range) { const value = finiteOrNull(raw); return value === null ? '<td class="unavailable-cell">-</td>' : `<td class="delta" style="color:${deltaRangeColor(value, range.min, range.max)}">${formatSignedDeltaAdaptive(value, true)}</td>`; }
function deltaActualCell(row, range) { const value = finiteOrNull(row.delta_actual); return value === null ? '<td class="unavailable-cell">-</td>' : `<td class="delta delta-ci-cell"${ciAttrs(row, 'delta_actual', range)} style="color:${deltaRangeColor(value, range.min, range.max)}">${formatSignedDeltaAdaptive(value, true)}</td>`; }
function residualCell(raw, range) { const value = finiteOrNull(raw); return value === null ? '<td class="unavailable-cell">-</td>' : `<td class="combination-interaction" style="color:${deltaRangeColor(value, range.min, range.max)}">${formatSignedDeltaAdaptive(value, true)}</td>`; }
function pairCardCell(name, delta, range) { const value = finiteOrNull(delta); return `<td class="combination-card-cell combination-card-with-delta"><span class="combination-card-name">${escapeHtml(name)}</span><span class="combination-card-delta" style="color:${value === null ? 'var(--text-muted)' : deltaRangeColor(value, range.min, range.max)}">(${value === null ? '-' : formatSignedDeltaAdaptive(value, true)})</span></td>`; }
function eloCell(raw, range) { const value = finiteOrNull(raw); return value === null ? '<td class="unavailable-cell">-</td>' : `<td class="elo-cell" style="color:${relativeEloColor(value, range.min, range.max)}">${Math.round(value).toLocaleString('en-US')}</td>`; }
function typeCell(type) { return `<td class="mw-action-type-cell"><span class="mw-action-type-badge mw-action-type-${slug(type)}">${escapeHtml(type)}</span></td>`; }
function pairTypeCell(row) { return `<td><span class="combination-type-badge mw-action-combination-type-badge" aria-label="${escapeAttr(row.pair_type || '')}"><span class="combination-type-part mw-action-type-${slug(row.card_1_type)}">${escapeHtml(row.card_1_type)}</span><span class="combination-type-separator" aria-hidden="true"></span><span class="combination-type-part mw-action-type-${slug(row.card_2_type)}">${escapeHtml(row.card_2_type)}</span></span></td>`; }
function percentageCell(row, field, countField, range, family) { const value = finiteOrNull(row[field]); if (value === null) return '<td class="unavailable-cell">-</td>'; const color = family === 'blue' ? playrateColor(value, range.min, range.max) : draftPercentageColor(value, range.min, range.max); return `<td class="build-value-tooltip" data-value-tooltip="${formatInteger(row[countField])} / ${formatInteger(row.available_n)}"><div class="playrate-cell mw-action-rate-cell"><div class="playrate-bar-wrap"><div class="playrate-bar" style="width:${Math.max(0, Math.min(100, value))}%;background:${color}"></div></div><span class="playrate-val" style="color:${color}">${value.toFixed(2)}%</span></div></td>`; }
function draftPercentageColor(value, min, max) { const normalized = normalizeToRange(value, min, max); return normalized === null ? 'var(--text-muted)' : colorFromStops(normalized, [[0, '#35446f'], [0.5, '#636ca7'], [1, '#9a91dc']]); }

function setMwActionMinimum(value) { minimumPicks = Math.max(0, Number.parseInt(value || '0', 10) || 0); currentPage = 1; render(); }
function setMwActionRows(value) { rowsPerPage = [25, 50, 100].includes(Number(value)) ? Number(value) : 50; currentPage = 1; render(); }
function goMwActionPage(page) { const total = Math.max(1, Math.ceil(pairVisibleCount() / rowsPerPage)); if (page < 1 || page > total) return; currentPage = page; render(); }
function pairVisibleCount() { const selected = pairTypeSelections[activeView] || new Set(); return rowsForView().filter(row => Number(row.n_picked || 0) >= minimumPicks).map(projectPairRow).filter(row => selected.has(row.pair_type) && pairSearchMatch(row)).length; }
function renderPagination(total) { const host = document.getElementById('pagination'); if (!host || total <= 1) { hidePagination(); return; } host.hidden = false; const pages = paginationRange(currentPage, total); let html = `<button class="page-btn" onclick="goMwActionPage(${currentPage - 1})" ${currentPage === 1 ? 'disabled' : ''}>&lsaquo;</button>`; let previous = null; pages.forEach(page => { if (previous !== null && page - previous > 1) html += '<span class="page-info">...</span>'; html += `<button class="page-btn ${page === currentPage ? 'active' : ''}" onclick="goMwActionPage(${page})">${page}</button>`; previous = page; }); html += `<button class="page-btn" onclick="goMwActionPage(${currentPage + 1})" ${currentPage === total ? 'disabled' : ''}>&rsaquo;</button>`; host.innerHTML = html; }
function paginationRange(current, total) { const pages = []; for (let page = Math.max(1, current - 2); page <= Math.min(total, current + 2); page += 1) pages.push(page); if (!pages.includes(1)) pages.unshift(1); if (!pages.includes(total)) pages.push(total); return pages; }
function hidePagination() { const host = document.getElementById('pagination'); if (host) { host.hidden = true; host.innerHTML = ''; } }

function closeAllPopups() { document.querySelectorAll('.mw-action-cards-table .type-filter-popup.open,.mw-action-cards-table .combination-header-popup.open').forEach(popup => popup.classList.remove('open')); }
function closePopupsOnOutsideClick(event) { if (!event.target.closest?.('.mw-action-cards-table th')) closeAllPopups(); }
function tooltipSource(event) { return event.target.closest?.('.mw-action-cards-table .build-value-tooltip,.mw-action-cards-table .col-tip,.mw-action-cards-table .maps-custom-tip'); }
function showTooltip(event) { const source = tooltipSource(event); const tooltip = document.getElementById('col-tooltip'); if (!source || !tooltip) return; const text = source.dataset.valueTooltip || source.dataset.tip; if (!text) return; tooltip.textContent = text; tooltip.style.display = 'block'; positionTooltip(event, tooltip); }
function moveTooltip(event) { const tooltip = document.getElementById('col-tooltip'); if (tooltipSource(event) && tooltip?.style.display !== 'none') positionTooltip(event, tooltip); }
function hideTooltip(event) { const source = tooltipSource(event); if (!source || source.contains(event.relatedTarget)) return; const tooltip = document.getElementById('col-tooltip'); if (tooltip) tooltip.style.display = 'none'; }
function positionTooltip(event, tooltip) { tooltip.style.left = `${Math.max(8, Math.min(event.clientX + 12, window.innerWidth - tooltip.offsetWidth - 8))}px`; tooltip.style.top = `${Math.max(8, Math.min(event.clientY + 16, window.innerHeight - tooltip.offsetHeight - 8))}px`; }

function renderLoading() { setMeta(''); hidePagination(); document.getElementById('tableHead').innerHTML = ''; document.getElementById('tableBody').innerHTML = `<tr><td><div class="state-overlay"><div class="spinner"></div><div class="state-title">Loading MW Action Cards...</div></div></td></tr>`; }
function renderError(error) { setMeta(''); hidePagination(); document.getElementById('tableHead').innerHTML = ''; document.getElementById('tableBody').innerHTML = `<tr><td><div class="state-overlay"><div class="state-title">Could not load MW Action Cards</div><div class="state-sub">${escapeHtml(error?.message || error)}</div></div></td></tr>`; }
function emptyRow(columns) { return `<tr><td colspan="${columns}"><div class="state-overlay"><div class="state-title">No action cards match the current filters.</div></div></td></tr>`; }
function setMeta(html) { const meta = document.getElementById('tableMeta'); if (meta) meta.innerHTML = html; }

function renderMapChips() { const host = document.getElementById('mapChips'); if (host) host.innerHTML = MAPS.map(([short, full]) => `<button class="chip ${selectedMaps.includes(full) ? 'active' : ''}" data-map="${escapeAttr(full)}" onclick="toggleMwActionCardMap(this.dataset.map)">${short}</button>`).join(''); }
function toggleMwActionCardMap(map) { selectedMaps = selectedMaps.includes(map) ? selectedMaps.filter(item => item !== map) : [...selectedMaps, map]; renderMapChips(); }
function selectAllMaps() { selectedMaps = MAPS.map(([, full]) => full); renderMapChips(); }
function selectNoneMaps() { selectedMaps = []; renderMapChips(); }
function resetFilters() { const set = (id, value) => { const element = document.getElementById(id); if (element) element.value = value; }; set('playerEloMin', '300'); set('playerEloMax', ''); set('opponentEloMin', '300'); set('opponentEloMax', ''); set('dateFrom', '2025-01-01'); set('dateTo', ''); ['completedToggle', 'globalArenaOnly', 'globalTournamentOnly'].forEach(id => { const element = document.getElementById(id); if (element) element.checked = false; }); selectedMaps = MAPS.map(([, full]) => full); renderMapChips(); reloadAllActive(); }
function applyFiltersFromSidebar() { reloadAllActive(); document.getElementById('sidebar')?.classList.remove('open'); document.getElementById('sidebarOverlay')?.classList.remove('active'); }
function reloadAllActive() { const view = canonicalView(); viewRows = { general: null, by_map: null, synergies: null }; void loadView(view, ++requestToken); }

function finiteOrNull(value) { if (value === null || value === undefined || value === '') return null; const number = Number(value); return Number.isFinite(number) ? number : null; }
function formatInteger(value) { return Number(value || 0).toLocaleString('en-US'); }
function slug(value) { return String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, '-'); }
function escapeHtml(value) { return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;'); }
const escapeAttr = escapeHtml;
