import {
  cappedNumericRange,
  colorFromStops,
  deltaRangeColor,
  normalizeToRange,
  numericRange,
  playrateColor,
  relativeEloColor,
} from '../color-scales.js?v=20260809-1';
import { formatSignedDeltaAdaptive } from '../table-cells.js?v=20260809-1';
import { setTopbarDatasetLock } from '../layout.js?v=20260809-1';
import { loadStats } from '../snapshot-cache.js?v=20260810-1';

export const id = 'mw-action-cards';
export const title = 'MW Action Cards';
export const navLabel = 'MW Action Cards';

const SNAPSHOT_URL = 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/mw-action-cards/general/default-mw.json';
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
const TYPES = ['Animals', 'Association', 'Build', 'Cards', 'Sponsors'];
const DATA_VIEWS = new Set(['general', 'draft']);
const SORTABLE_BY_VIEW = {
  general: new Set([
    'delta_picked', 'delta_picked_upgraded', 'delta_picked_basic',
    'elo_picked', 'picked_pct',
  ]),
  draft: new Set([
    'picked_pct', 'drafted_first_pct', 'drafted_second_pct', 'undrafted_pct',
  ]),
};

export const mainHtml = `
  <div class="main-header mw-action-cards-main-header">
    <div class="table-meta" id="tableMeta"></div>
  </div>
  <div class="attributes-bar endgames-tabs-bar mw-action-cards-tabs-bar">
    <div class="attributes-bar-header endgames-tabs-header">
      <div class="endgames-tabs mw-action-cards-tabs" role="tablist" aria-label="MW Action Cards views">
        <button class="endgames-tab active" type="button" data-view="general" onclick="setMwActionCardsView('general')">General</button>
        <button class="endgames-tab" type="button" data-view="draft" onclick="setMwActionCardsView('draft')">Draft</button>
        <button class="endgames-tab" type="button" data-view="by_map" onclick="setMwActionCardsView('by_map')">By map</button>
        <button class="endgames-tab" type="button" data-view="synergies" onclick="setMwActionCardsView('synergies')">Synergies</button>
        <button class="endgames-tab" type="button" data-view="matchups" onclick="setMwActionCardsView('matchups')">Matchups</button>
      </div>
    </div>
  </div>
  <div class="table-wrap mw-action-cards-table-wrap"><div class="table-scroll">
    <table id="statsTable" class="mw-action-cards-table">
      <thead id="tableHead"></thead><tbody id="tableBody"></tbody>
    </table>
  </div></div>`;

export const sidebarHtml = `
  <div class="sidebar-header"><span class="sidebar-title">Filters</span><div style="display:flex;align-items:center;gap:6px;">
    <button class="reset-btn" onclick="resetFilters()">Reset</button>
    <button class="sidebar-close-btn" onclick="toggleSidebar()" title="Close filters">x</button>
  </div></div>
  <hr class="divider" />
  <div class="filter-group"><span class="filter-label">Player ELO</span><div class="range-row">
    <input class="range-input" type="number" id="playerEloMin" placeholder="Min" value="300" min="0" />
    <input class="range-input" type="number" id="playerEloMax" placeholder="Max" min="0" />
  </div></div>
  <div class="filter-group"><span class="filter-label">Opponent ELO</span><div class="range-row">
    <input class="range-input" type="number" id="opponentEloMin" placeholder="Min" value="300" min="0" />
    <input class="range-input" type="number" id="opponentEloMax" placeholder="Max" min="0" />
  </div></div>
  <hr class="divider" />
  <div class="filter-group"><div style="display:flex;align-items:baseline;gap:6px;margin-bottom:8px;">
    <span class="filter-label" style="margin-bottom:0">Maps</span>
    <span class="map-select-all-none">(<span class="map-toggle-link" onclick="selectAllMaps()">all</span> / <span class="map-toggle-link" onclick="selectNoneMaps()">none</span>)</span>
  </div><div class="chip-grid" id="mapChips"></div></div>
  <hr class="divider" />
  <div class="filter-group"><span class="filter-label">Date Range</span>
    <input class="date-input" type="text" id="dateFrom" value="2025-01-01" placeholder="yyyy-mm-dd" />
    <input class="date-input" type="text" id="dateTo" placeholder="yyyy-mm-dd" />
  </div>
  <hr class="divider" />
  <div class="filter-group">
    <div class="toggle-row"><span class="toggle-label">Completed games only</span><label class="toggle"><input type="checkbox" id="completedToggle" /><span class="toggle-track"></span></label></div>
  </div>
  <hr class="divider" />
  <div class="filter-action-stack"><button class="apply-btn" onclick="applyFiltersFromSidebar()">Apply filters</button></div>`;

let mounted = false;
let requestToken = 0;
let activeView = 'general';
let rows = [];
let selectedMaps = MAPS.map(([, full]) => full);
let selectedTypes = new Set(TYPES);
let sortStates = {
  general: { field: 'delta_picked', direction: 'desc' },
  draft: { field: 'picked_pct', direction: 'desc' },
};

export function mount({ dataset = 1 } = {}) {
  mounted = true;
  requestToken += 1;
  activeView = 'general';
  rows = [];
  selectedMaps = MAPS.map(([, full]) => full);
  selectedTypes = new Set(TYPES);
  sortStates = {
    general: { field: 'delta_picked', direction: 'desc' },
    draft: { field: 'picked_pct', direction: 'desc' },
  };
  Object.assign(window, {
    setMwActionCardsView,
    sortMwActionCards,
    toggleMwActionCardTypePopup,
    toggleMwActionCardType,
    resetFilters,
    applyFiltersFromSidebar,
    selectAllMaps,
    selectNoneMaps,
    toggleMwActionCardMap,
  });
  setTopbarDatasetLock(1);
  if (Number(dataset) !== 1) {
    window.dispatchEvent(new CustomEvent('arknova:set-dataset', { detail: { value: 1 } }));
  }
  document.addEventListener('click', closeTypePopupOnOutsideClick);
  document.addEventListener('mouseover', showMwActionTooltip);
  document.addEventListener('mousemove', moveMwActionTooltip);
  document.addEventListener('mouseout', hideMwActionTooltip);
  renderMapChips();
  syncTabs();
  void loadData(requestToken);
}

export function unmount() {
  mounted = false;
  requestToken += 1;
  document.removeEventListener('click', closeTypePopupOnOutsideClick);
  document.removeEventListener('mouseover', showMwActionTooltip);
  document.removeEventListener('mousemove', moveMwActionTooltip);
  document.removeEventListener('mouseout', hideMwActionTooltip);
  setTopbarDatasetLock(null);
}

export function setDataset(value) {
  if (Number(value) === 1) return;
  setTopbarDatasetLock(1);
  window.dispatchEvent(new CustomEvent('arknova:set-dataset', { detail: { value: 1 } }));
}

function setMwActionCardsView(view) {
  activeView = ['general', 'draft', 'by_map', 'synergies', 'matchups'].includes(view) ? view : 'general';
  syncTabs();
  if (DATA_VIEWS.has(activeView)) render();
  else renderPlaceholder();
}

function syncTabs() {
  document.querySelectorAll('.mw-action-cards-tabs .endgames-tab').forEach(button => {
    button.classList.toggle('active', button.dataset.view === activeView);
  });
}

function params() {
  const value = id => document.getElementById(id)?.value ?? '';
  return {
    stats_page: 'mw_action_cards',
    mw_action_cards_view: 'general',
    is_mw: 1,
    maps: selectedMaps,
    player_elo_min: value('playerEloMin') === '' ? 0 : Number(value('playerEloMin')),
    player_elo_max: value('playerEloMax') === '' ? null : Number(value('playerEloMax')),
    opponent_elo_min: value('opponentEloMin') === '' ? 0 : Number(value('opponentEloMin')),
    opponent_elo_max: value('opponentEloMax') === '' ? null : Number(value('opponentEloMax')),
    date_from: value('dateFrom') || null,
    date_to: value('dateTo') || null,
    completed_only: Boolean(document.getElementById('completedToggle')?.checked),
    arena_only: Boolean(document.getElementById('globalArenaOnly')?.checked),
    tournament_only: Boolean(document.getElementById('globalTournamentOnly')?.checked),
  };
}

function isDefault(request) {
  return request.player_elo_min === 300 && request.player_elo_max === null
    && request.opponent_elo_min === 300 && request.opponent_elo_max === null
    && request.date_from === '2025-01-01' && request.date_to === null
    && request.completed_only === false && request.arena_only === false
    && request.tournament_only === false
    && selectedMaps.length === MAPS.length;
}

async function loadData(token) {
  if (!DATA_VIEWS.has(activeView)) return;
  if (!selectedMaps.length) {
    rows = [];
    render();
    return;
  }
  const wrap = document.querySelector('.mw-action-cards-table-wrap');
  const preserve = rows.length > 0;
  if (preserve) wrap?.classList.add('stats-updating');
  else renderLoading();
  try {
    const request = params();
    const payload = await loadStats(request, isDefault(request) ? SNAPSHOT_URL : null);
    if (!mounted || token !== requestToken) return;
    rows = Array.isArray(payload.data) ? payload.data : [];
    render();
  } catch (error) {
    if (mounted && token === requestToken) {
      if (preserve) console.error('Could not update MW Action Cards', error);
      else renderError(error);
    }
  } finally {
    if (mounted && token === requestToken) wrap?.classList.remove('stats-updating');
  }
}

function typeHeader(width) {
  return `<th class="type-filter-header ${selectedTypes.size === TYPES.length ? '' : 'type-filter-active'}" id="mwActionTypeHeader" style="width:${width};text-align:center" onclick="toggleMwActionCardTypePopup(event)">
    <span class="type-filter-label">Type <span class="type-filter-indicator ${selectedTypes.size === TYPES.length ? 'type-filter-icon' : ''}" id="mwActionTypeIndicator">${selectedTypes.size === TYPES.length ? '' : `${selectedTypes.size}/5`}</span></span>
    <div class="type-filter-popup mw-action-type-popup" id="mwActionTypePopup" onclick="event.stopPropagation()">
      ${TYPES.map(type => `<button class="chip ${selectedTypes.has(type) ? 'active' : ''}" data-type="${type}" onclick="toggleMwActionCardType(event, this.dataset.type)">${type}</button>`).join('')}
    </div>
  </th>`;
}

function renderHead() {
  const header = document.getElementById('tableHead');
  if (!header) return;
  document.getElementById('statsTable')?.classList.toggle(
    'mw-action-cards-draft-table',
    activeView === 'draft',
  );
  if (activeView === 'draft') {
    header.innerHTML = `<tr>
      <th style="width:5%;cursor:default;text-align:center">#</th>
      ${typeHeader('15%')}
      <th style="width:15%;cursor:default;text-align:center">Card</th>
      ${sortableHeader('picked_pct', 'Picked%', 'tables where the card was picked / tables where it was available', '16.25%')}
      ${sortableHeader('drafted_first_pct', 'Drafted% (1st)', 'tables where the card appeared in the first draft slot / available tables', '16.25%')}
      ${sortableHeader('drafted_second_pct', 'Drafted% (2nd)', 'tables where the card appeared in the second draft slot / available tables', '16.25%')}
      ${sortableHeader('undrafted_pct', 'Undrafted%', 'tables where the card appeared in the third draft slot / available tables', '16.25%')}
    </tr>`;
    return;
  }
  header.innerHTML = `<tr>
    <th style="width:5%;cursor:default;text-align:center">#</th>
    ${typeHeader('15%')}
    <th style="width:15%;cursor:default;text-align:center">Card</th>
    ${sortableHeader('delta_picked', '&Delta; Elo', 'average Elo delta when this special action card was picked', '12%')}
    ${sortableHeader('delta_picked_upgraded', '&Delta; Elo (Upg)', 'average Elo delta when this special action card was picked and its action was upgraded', '12%')}
    ${sortableHeader('delta_picked_basic', '&Delta; Elo (Basic)', 'average Elo delta when this special action card was picked and its action was not upgraded', '12%')}
    ${sortableHeader('elo_picked', 'Elo', 'average Elo of players who picked this special action card', '10%')}
    ${sortableHeader('picked_pct', 'Picked%', 'tables where the card was picked / tables where it was available', '19%')}
  </tr>`;
}

function sortableHeader(field, label, tooltip, width) {
  const sortState = sortStates[activeView];
  const active = sortState?.field === field;
  const arrow = active ? (sortState.direction === 'desc' ? '\u2193' : '\u2191') : '\u2195';
  return `<th class="${active ? 'sorted' : ''}" style="width:${width};text-align:center" onclick="sortMwActionCards('${field}')">${label}<span class="col-tip" data-tip="${escapeAttr(tooltip)}">?</span><span class="sort-arrow">${arrow}</span></th>`;
}

function render() {
  if (!DATA_VIEWS.has(activeView)) return;
  renderHead();
  const globallyRanked = [...rows].sort(compareRows).map((row, index) => ({ ...row, global_rank: index + 1 }));
  const visible = globallyRanked.filter(row => selectedTypes.has(String(row.type)));
  const percentageRanges = Object.fromEntries([
    'picked_pct', 'drafted_first_pct', 'drafted_second_pct', 'undrafted_pct',
  ].map(field => [field, numericRange(rows, row => row[field])]));
  const meta = document.getElementById('tableMeta');
  if (meta) meta.innerHTML = `<strong>${visible.length}</strong> action cards`;
  const body = document.getElementById('tableBody');
  if (!body) return;
  if (activeView === 'draft') {
    body.innerHTML = visible.map(row => `<tr>
      <td class="rank-cell">${row.global_rank}</td>
      <td class="mw-action-type-cell"><span class="mw-action-type-badge mw-action-type-${slug(row.type)}">${escapeHtml(row.type)}</span></td>
      <td class="card-name">${escapeHtml(row.card_name)}</td>
      ${percentageCell(row, 'picked_pct', 'picked_n', percentageRanges.picked_pct, 'blue')}
      ${percentageCell(row, 'drafted_first_pct', 'drafted_first_n', percentageRanges.drafted_first_pct, 'violet')}
      ${percentageCell(row, 'drafted_second_pct', 'drafted_second_n', percentageRanges.drafted_second_pct, 'violet')}
      ${percentageCell(row, 'undrafted_pct', 'undrafted_n', percentageRanges.undrafted_pct, 'violet')}
    </tr>`).join('') || '<tr><td colspan="7"><div class="state-overlay"><div class="state-title">No action cards match the current filters.</div></div></td></tr>';
    return;
  }
  const deltaRanges = {
    delta_picked: cappedNumericRange(rows, row => row.delta_picked),
    delta_picked_upgraded: cappedNumericRange(rows, row => row.delta_picked_upgraded),
    delta_picked_basic: cappedNumericRange(rows, row => row.delta_picked_basic),
  };
  const eloRange = numericRange(rows, row => row.elo_picked);
  body.innerHTML = visible.map(row => `<tr>
    <td class="rank-cell">${row.global_rank}</td>
    <td class="mw-action-type-cell"><span class="mw-action-type-badge mw-action-type-${slug(row.type)}">${escapeHtml(row.type)}</span></td>
    <td class="card-name">${escapeHtml(row.card_name)}</td>
    ${deltaCell(row, 'delta_picked', deltaRanges.delta_picked, true)}
    ${deltaCell(row, 'delta_picked_upgraded', deltaRanges.delta_picked_upgraded)}
    ${deltaCell(row, 'delta_picked_basic', deltaRanges.delta_picked_basic)}
    ${eloCell(row, eloRange)}
    ${percentageCell(row, 'picked_pct', 'picked_n', percentageRanges.picked_pct, 'blue')}
  </tr>`).join('') || '<tr><td colspan="8"><div class="state-overlay"><div class="state-title">No action cards match the current filters.</div></div></td></tr>';
}

function compareRows(a, b) {
  const sortState = sortStates[activeView];
  const av = finiteOrNull(a[sortState.field]);
  const bv = finiteOrNull(b[sortState.field]);
  if (av === null && bv !== null) return 1;
  if (bv === null && av !== null) return -1;
  if (av !== null && bv !== null && av !== bv) {
    return sortState.direction === 'asc' ? av - bv : bv - av;
  }
  return Number(a.card_order || 0) - Number(b.card_order || 0);
}

function deltaCell(row, field, range, primary = false) {
  const value = finiteOrNull(row[field]);
  if (value === null) return '<td class="unavailable-cell">-</td>';
  const weightClass = primary ? 'mw-action-delta-primary' : 'mw-action-delta-secondary';
  return `<td class="delta delta-ci-cell ${weightClass}" data-ci-low="${escapeAttr(row[`${field}_ci95_low`] ?? '')}" data-ci-high="${escapeAttr(row[`${field}_ci95_high`] ?? '')}" data-ci-n="${escapeAttr(row[`${field}_ci95_n`] ?? '')}" data-ci-color-min="${escapeAttr(range.min ?? '')}" data-ci-color-max="${escapeAttr(range.max ?? '')}" style="color:${deltaRangeColor(value, range.min, range.max)}">${formatSignedDeltaAdaptive(value, true)}</td>`;
}

function eloCell(row, range) {
  const value = finiteOrNull(row.elo_picked);
  if (value === null) return '<td class="unavailable-cell">-</td>';
  return `<td style="color:${relativeEloColor(value, range.min, range.max)}">${Math.round(value).toLocaleString('en-US')}</td>`;
}

function percentageCell(row, valueField, countField, range, family) {
  const value = finiteOrNull(row[valueField]);
  if (value === null) return '<td class="unavailable-cell">-</td>';
  const color = family === 'blue'
    ? playrateColor(value, range.min, range.max)
    : draftPercentageColor(value, range.min, range.max);
  const width = Math.max(0, Math.min(100, value));
  return `<td class="build-value-tooltip" data-value-tooltip="${Number(row[countField] || 0).toLocaleString('en-US')} / ${Number(row.available_n || 0).toLocaleString('en-US')}"><div class="playrate-cell mw-action-rate-cell"><div class="playrate-bar-wrap"><div class="playrate-bar" style="width:${width}%;background:${color}"></div></div><span class="playrate-val" style="color:${color}">${value.toFixed(2)}%</span></div></td>`;
}

function draftPercentageColor(value, min, max) {
  const normalized = normalizeToRange(value, min, max);
  return normalized === null ? 'var(--text-muted)' : colorFromStops(normalized, [
    [0, '#35446f'], [0.5, '#636ca7'], [1, '#9a91dc'],
  ]);
}

function sortMwActionCards(field) {
  if (!SORTABLE_BY_VIEW[activeView]?.has(field)) return;
  const sortState = sortStates[activeView];
  if (sortState.field === field) sortState.direction = sortState.direction === 'asc' ? 'desc' : 'asc';
  else sortStates[activeView] = { field, direction: 'desc' };
  render();
}

function toggleMwActionCardTypePopup(event) {
  event.stopPropagation();
  const popup = document.getElementById('mwActionTypePopup');
  const header = document.getElementById('mwActionTypeHeader');
  if (!popup || !header) return;
  const opening = !popup.classList.contains('open');
  popup.classList.toggle('open', opening);
  if (opening) positionTypePopup();
}

function toggleMwActionCardType(event, type) {
  event.stopPropagation();
  if (!TYPES.includes(type)) return;
  if (selectedTypes.has(type)) selectedTypes.delete(type);
  else selectedTypes.add(type);
  render();
  document.getElementById('mwActionTypePopup')?.classList.add('open');
  positionTypePopup();
}

function positionTypePopup() {
  const popup = document.getElementById('mwActionTypePopup');
  const header = document.getElementById('mwActionTypeHeader');
  if (!popup || !header) return;
  const rect = header.getBoundingClientRect();
  popup.style.left = `${Math.max(8, Math.min(rect.left, window.innerWidth - popup.offsetWidth - 8))}px`;
  popup.style.top = `${Math.min(rect.bottom + 5, window.innerHeight - popup.offsetHeight - 8)}px`;
}

function closeTypePopupOnOutsideClick(event) {
  if (!event.target.closest?.('#mwActionTypeHeader')) document.getElementById('mwActionTypePopup')?.classList.remove('open');
}

function tooltipSource(event) {
  return event.target.closest?.('.mw-action-cards-table .build-value-tooltip, .mw-action-cards-table .col-tip');
}

function showMwActionTooltip(event) {
  const source = tooltipSource(event);
  const tooltip = document.getElementById('col-tooltip');
  if (!source || !tooltip) return;
  const text = source.dataset.valueTooltip || source.dataset.tip;
  if (!text) return;
  tooltip.textContent = text;
  tooltip.style.display = 'block';
  positionMwActionTooltip(event, tooltip);
}

function moveMwActionTooltip(event) {
  const tooltip = document.getElementById('col-tooltip');
  if (!tooltipSource(event) || !tooltip || tooltip.style.display === 'none') return;
  positionMwActionTooltip(event, tooltip);
}

function hideMwActionTooltip(event) {
  const source = tooltipSource(event);
  if (!source || source.contains(event.relatedTarget)) return;
  const tooltip = document.getElementById('col-tooltip');
  if (tooltip) tooltip.style.display = 'none';
}

function positionMwActionTooltip(event, tooltip) {
  const left = Math.max(8, Math.min(event.clientX + 12, window.innerWidth - tooltip.offsetWidth - 8));
  const preferredTop = event.clientY + 16;
  const top = preferredTop + tooltip.offsetHeight > window.innerHeight - 8
    ? event.clientY - tooltip.offsetHeight - 10
    : preferredTop;
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${Math.max(8, top)}px`;
}

function renderPlaceholder() {
  const meta = document.getElementById('tableMeta');
  if (meta) meta.textContent = '';
  document.getElementById('tableHead').innerHTML = '';
  document.getElementById('tableBody').innerHTML = `<tr><td><div class="state-overlay"><div class="state-title">${escapeHtml(viewLabel(activeView))}</div><div class="state-sub">This view will be added in a future update.</div></div></td></tr>`;
}

function renderLoading() {
  renderHead();
  document.getElementById('tableBody').innerHTML = `<tr><td colspan="${activeView === 'draft' ? 7 : 8}"><div class="state-overlay"><div class="spinner"></div><div class="state-title">Loading MW Action Cards...</div></div></td></tr>`;
}

function renderError(error) {
  renderHead();
  document.getElementById('tableBody').innerHTML = `<tr><td colspan="${activeView === 'draft' ? 7 : 8}"><div class="state-overlay"><div class="state-title">Could not load MW Action Cards</div><div class="state-sub">${escapeHtml(error?.message || error)}</div></div></td></tr>`;
}

function renderMapChips() {
  const host = document.getElementById('mapChips');
  if (!host) return;
  host.innerHTML = MAPS.map(([short, full]) => `<button class="chip ${selectedMaps.includes(full) ? 'active' : ''}" data-map="${escapeAttr(full)}" onclick="toggleMwActionCardMap(this.dataset.map)">${short}</button>`).join('');
}

function toggleMwActionCardMap(map) {
  selectedMaps = selectedMaps.includes(map) ? selectedMaps.filter(item => item !== map) : [...selectedMaps, map];
  renderMapChips();
}

function selectAllMaps() { selectedMaps = MAPS.map(([, full]) => full); renderMapChips(); }
function selectNoneMaps() { selectedMaps = []; renderMapChips(); }

function resetFilters() {
  const setValue = (id, value) => { const element = document.getElementById(id); if (element) element.value = value; };
  setValue('playerEloMin', '300'); setValue('playerEloMax', '');
  setValue('opponentEloMin', '300'); setValue('opponentEloMax', '');
  setValue('dateFrom', '2025-01-01'); setValue('dateTo', '');
  ['completedToggle', 'globalArenaOnly', 'globalTournamentOnly'].forEach(id => {
    const element = document.getElementById(id); if (element) element.checked = false;
  });
  selectedMaps = MAPS.map(([, full]) => full);
  renderMapChips();
  void loadData(++requestToken);
}

function applyFiltersFromSidebar() {
  void loadData(++requestToken);
  document.getElementById('sidebar')?.classList.remove('open');
  document.getElementById('sidebarOverlay')?.classList.remove('active');
}

function finiteOrNull(value) {
  if (value === null || value === undefined || value === '') return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}
function viewLabel(view) { return ({ by_map: 'By map', synergies: 'Synergies', matchups: 'Matchups' })[view] || 'General'; }
function slug(value) { return String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, '-'); }
function escapeHtml(value) { return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;'); }
const escapeAttr = escapeHtml;
