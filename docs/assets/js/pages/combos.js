export const id = 'combos';
export const title = 'Combos';
export const navLabel = 'Combos';

export const mainHtml = `
  <div class="main-header combinations-main-header">
    <div class="table-meta" id="tableMeta"></div>
    <div class="main-controls">
      <div class="min-plays-wrap">
        <label class="min-plays-label" for="minPlayedInput">Minimum plays</label>
        <input class="min-plays-input" type="number" id="minPlayedInput" value="1000" min="0"
               inputmode="numeric" oninput="onCombinationFilterChange()" />
      </div>
      <div class="rpp-wrap">Rows
        <select class="rpp-select" id="rppSelect" onchange="onCombinationRowsChange()">
          <option value="25">25</option>
          <option value="50" selected>50</option>
          <option value="100">100</option>
        </select>
      </div>
    </div>
  </div>

  <div class="attributes-bar endgames-tabs-bar combinations-tabs-bar">
    <div class="attributes-bar-header endgames-tabs-header">
      <div class="endgames-tabs combinations-tabs" role="tablist" aria-label="Combination views">
        <button class="endgames-tab active" type="button" data-view="card_card"
                onclick="setCombinationsView('card_card')">Card + Card</button>
        <button class="endgames-tab" type="button" data-view="card_map"
                onclick="setCombinationsView('card_map')">Card + Map</button>
        <button class="endgames-tab" type="button" data-view="card_round"
                onclick="setCombinationsView('card_round')">Card + Round</button>
      </div>
    </div>
  </div>

  <div class="table-wrap combinations-table-wrap">
    <div class="table-scroll">
      <table id="statsTable" class="combinations-table">
        <thead id="tableHead"></thead>
        <tbody id="tableBody"></tbody>
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
  <div id="combinationSidebarMapSection">
    <div class="filter-group">
      <div style="display:flex;align-items:baseline;gap:6px;margin-bottom:8px;">
        <span class="filter-label" style="margin-bottom:0">Maps</span>
        <span class="map-select-all-none">
          (<span class="map-toggle-link" onclick="selectAllMaps()">all</span> /
          <span class="map-toggle-link" onclick="selectNoneMaps()">none</span>)
        </span>
      </div>
      <div class="chip-grid" id="mapChips"></div>
    </div>
    <hr class="divider" />
  </div>
  <div id="combinationSidebarRoundSection">
    <div class="filter-group">
      <div style="display:flex;align-items:baseline;gap:6px;margin-bottom:8px;">
        <span class="filter-label" style="margin-bottom:0">Round</span>
        <span class="map-select-all-none">
          (<span class="map-toggle-link" onclick="selectAllRounds()">all</span> /
          <span class="map-toggle-link" onclick="selectNoneRounds()">none</span>)
        </span>
      </div>
      <div class="chip-grid" id="roundChips"></div>
    </div>
    <hr class="divider" />
  </div>
  <div class="filter-group">
    <span class="filter-label">Date Range</span>
    <input class="date-input" type="text" inputmode="numeric" pattern="\\d{4}-\\d{2}-\\d{2}"
           placeholder="yyyy-mm-dd" id="dateFrom" value="2025-01-01" />
    <input class="date-input" type="text" inputmode="numeric" pattern="\\d{4}-\\d{2}-\\d{2}"
           placeholder="yyyy-mm-dd" id="dateTo" />
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
    <button class="apply-btn" onclick="applyFiltersFromSidebar()">Apply filters</button>
  </div>`;

const API_URL = 'https://europe-west1-ark-nova-stats-dashboard.cloudfunctions.net/get-card-stats';
const SNAPSHOT_ROOT = 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats';
const CARD_ALIASES_URL = 'cards_altnames.csv';
const SNAPSHOT_VIEWS = {
  card_card: 'card-card',
  card_map: 'card-map',
  card_round: 'card-round',
};
const ROUNDS = ['1', '2', '3', '4', '5', '6+'];
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
const PAIR_TYPES = [
  'Animal + Animal', 'Animal + Project', 'Animal + Sponsor',
  'Project + Project', 'Project + Sponsor', 'Sponsor + Sponsor',
];
const CARD_TYPES = ['animal', 'sponsor', 'project'];

let mounted = false;
let mountToken = 0;
let isMW = 1;
let activeView = 'card_card';
let allData = [];
let filteredData = [];
let cardCatalogue = [];
let cardAliases = new Map();
let selectedMaps = MAPS.map(([, full]) => full);
let selectedRounds = new Set(ROUNDS);
let selectedHeaderMaps = new Set(MAPS.map(([, full]) => full));
let selectedHeaderRounds = new Set(ROUNDS);
let selectedTypes = new Set(PAIR_TYPES);
let selectedCardTypes = new Set(CARD_TYPES);
let selectedOne = '';
let selectedTwo = '';
let currentPage = 1;
let rowsPerPage = 50;
let sortState = { col: 'interaction', dir: 'desc' };
let eloRange = { min: null, max: null };

export function mount({ dataset = 1 } = {}) {
  mounted = true;
  mountToken += 1;
  isMW = Number(dataset) === 0 ? 0 : 1;
  activeView = 'card_card';
  selectedMaps = MAPS.map(([, full]) => full);
  selectedRounds = new Set(ROUNDS);
  selectedHeaderMaps = new Set(MAPS.map(([, full]) => full));
  selectedHeaderRounds = new Set(ROUNDS);
  selectedTypes = new Set(PAIR_TYPES);
  selectedCardTypes = new Set(CARD_TYPES);
  selectedOne = '';
  selectedTwo = '';
  currentPage = 1;
  rowsPerPage = 50;
  sortState = { col: 'interaction', dir: 'desc' };
  bindHandlers();
  renderMapChips();
  renderRoundChips();
  renderTabs();
  renderSidebarMapVisibility();
  loadCardAliases();
  loadCardCatalogue();
  applyFilters(mountToken);
}

export function unmount() {
  mounted = false;
  mountToken += 1;
  closeCombinationHeaderPopups();
  hideTooltip();
}

export function setDataset(value) {
  isMW = Number(value) === 0 ? 0 : 1;
  selectedOne = '';
  selectedTwo = '';
  selectedHeaderMaps = new Set(MAPS.map(([, full]) => full));
  selectedHeaderRounds = new Set(ROUNDS);
  selectedRounds = new Set(ROUNDS);
  selectedCardTypes = new Set(CARD_TYPES);
  renderRoundChips();
  closeCombinationHeaderPopups();
  loadCardCatalogue();
  applyFilters(++mountToken);
}

function bindHandlers() {
  Object.assign(window, {
    setCombinationsView,
    sortCombinations,
    onCombinationFilterChange,
    onCombinationRowsChange,
    goCombinationPage,
    toggleCombinationType,
    toggleCombinationTypePopup,
    selectAllCombinationTypes,
    selectNoneCombinationTypes,
    toggleCombinationSingleType,
    toggleCombinationSingleTypePopup,
    selectCombinationCard,
    clearCombinationSelection,
    openCombinationCardFilter,
    renderCombinationCardChoices,
    toggleCombinationMapPopup,
    toggleCombinationHeaderMap,
    selectAllCombinationHeaderMaps,
    selectNoneCombinationHeaderMaps,
    toggleCombinationHeaderRound,
    selectAllCombinationHeaderRounds,
    selectNoneCombinationHeaderRounds,
    toggleCombinationRoundPopup,
    toggleMapChip,
    selectAllMaps,
    selectNoneMaps,
    toggleRoundChip,
    selectAllRounds,
    selectNoneRounds,
    resetFilters,
    applyFiltersFromSidebar,
  });
}

function setCombinationsView(view) {
  if (!Object.hasOwn(SNAPSHOT_VIEWS, view) || view === activeView) return;
  activeView = view;
  selectedOne = '';
  selectedTwo = '';
  selectedHeaderMaps = new Set(MAPS.map(([, full]) => full));
  selectedHeaderRounds = new Set(ROUNDS);
  selectedRounds = new Set(ROUNDS);
  renderRoundChips();
  if (activeView === 'card_map') {
    selectedMaps = MAPS.map(([, full]) => full);
    renderMapChips();
  }
  selectedTypes = new Set(PAIR_TYPES);
  selectedCardTypes = new Set(CARD_TYPES);
  sortState = { col: 'interaction', dir: 'desc' };
  currentPage = 1;
  renderTabs();
  renderSidebarMapVisibility();
  applyFilters(++mountToken);
}

function renderTabs() {
  document.querySelectorAll('.combinations-tabs .endgames-tab').forEach(button => {
    button.classList.toggle('active', button.dataset.view === activeView);
  });
}

function renderSidebarMapVisibility() {
  const section = document.getElementById('combinationSidebarMapSection');
  if (section) section.style.display = activeView === 'card_map' ? 'none' : '';
  const roundSection = document.getElementById('combinationSidebarRoundSection');
  if (roundSection) roundSection.style.display = activeView === 'card_round' ? 'none' : '';
}

function getParams() {
  const value = id => document.getElementById(id)?.value || '';
  const params = {
    stats_page: 'combinations',
    combinations_view: activeView,
    is_mw: isMW,
    maps: selectedMaps,
    player_elo_min: Number(value('playerEloMin') || 300),
    player_elo_max: value('playerEloMax') ? Number(value('playerEloMax')) : null,
    opponent_elo_min: Number(value('opponentEloMin') || 300),
    opponent_elo_max: value('opponentEloMax') ? Number(value('opponentEloMax')) : null,
    date_from: value('dateFrom') || '2025-01-01',
    date_to: value('dateTo') || null,
    end_game_triggered: document.getElementById('endGameToggle')?.checked ? true : null,
  };
  if (activeView !== 'card_round' && selectedRounds.size < ROUNDS.length) {
    params.rounds = [...selectedRounds];
  }
  return params;
}

function isDefaultParams(params) {
  return params.player_elo_min === 300 && params.player_elo_max === null
    && params.opponent_elo_min === 300 && params.opponent_elo_max === null
    && params.date_from === '2025-01-01' && params.date_to === null
    && params.end_game_triggered === null && selectedMaps.length === MAPS.length
    && selectedRounds.size === ROUNDS.length;
}

async function applyFilters(token = mountToken) {
  renderLoading();
  if (!selectedMaps.length || (activeView !== 'card_round' && !selectedRounds.size)) {
    allData = [];
    applyClientFilters();
    return;
  }
  const params = getParams();
  try {
    let payload;
    if (isDefaultParams(params)) {
      try {
        const dataset = isMW ? 'mw' : 'base';
        const url = `${SNAPSHOT_ROOT}/combinations/${SNAPSHOT_VIEWS[activeView]}/default-${dataset}.json?v=20260629-13`;
        const response = await fetch(url);
        if (!response.ok) throw new Error(`Snapshot request failed (${response.status})`);
        payload = await response.json();
      } catch {
        payload = await fetchApi(params);
      }
    } else {
      payload = await fetchApi(params);
    }
    if (!mounted || token !== mountToken) return;
    allData = Array.isArray(payload.data) ? payload.data : [];
    mergeCardCatalogueFromRows(allData);
    currentPage = 1;
    applyClientFilters();
  } catch (error) {
    if (!mounted || token !== mountToken) return;
    renderError(error);
  }
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

async function loadCardCatalogue() {
  const dataset = isMW ? 'mw' : 'base';
  try {
    let payload;
    try {
      const response = await fetch(`${SNAPSHOT_ROOT}/default-${dataset}.json`, { cache: 'no-store' });
      if (!response.ok) throw new Error(`Snapshot request failed (${response.status})`);
      payload = await response.json();
    } catch {
      payload = await fetchApi({
        stats_page: 'cards',
        is_mw: isMW,
        maps: MAPS.map(([, full]) => full),
        player_elo_min: 300,
        player_elo_max: null,
        opponent_elo_min: 300,
        opponent_elo_max: null,
        date_from: '2025-01-01',
        date_to: null,
        end_game_triggered: null,
      });
    }
    mergeCardCatalogueFromRows(payload.data || []);
  } catch {
    // Combination rows populate the catalogue once the main request completes.
  }
}

function mergeCardCatalogueFromRows(sourceRows) {
  const names = new Set(cardCatalogue);
  for (const row of sourceRows) {
    if (row.card_name) names.add(row.card_name);
    if (row.card_1) names.add(row.card_1);
    if (row.card_2) names.add(row.card_2);
  }
  cardCatalogue = [...names].sort((a, b) => a.localeCompare(b));
}

function applyClientFilters({ preserveHead = false } = {}) {
  const minimum = Math.max(0, Number(document.getElementById('minPlayedInput')?.value || 0));
  const candidatesBeforeMinimum = allData.filter(row => {
    const normalizedPairType = String(row.pair_type || '').replace(' vs. ', ' + ');
    if (activeView === 'card_card' && !selectedTypes.has(normalizedPairType)) return false;
    if (activeView === 'card_map' || activeView === 'card_round') {
      const normalizedCardType = String(row.card_type || '').toLowerCase();
      if (!selectedCardTypes.has(normalizedCardType)) return false;
      if (selectedOne && row.card_name !== selectedOne) return false;
      if (activeView === 'card_map' && !selectedHeaderMaps.has(row.map_name)) return false;
      if (activeView === 'card_round' && !selectedHeaderRounds.has(row.round_name)) return false;
      return true;
    }
    if (selectedOne && selectedTwo) {
      const exact = (row.card_1 === selectedOne && row.card_2 === selectedTwo)
        || (row.card_1 === selectedTwo && row.card_2 === selectedOne);
      if (!exact) return false;
    } else {
      const selectedCard = selectedOne || selectedTwo;
      if (selectedCard && row.card_1 !== selectedCard && row.card_2 !== selectedCard) return false;
    }
    return true;
  });
  filteredData = candidatesBeforeMinimum.filter(row => Number(row.n_played) >= minimum);
  window.setMinimumPlaysWarning?.(
    document.getElementById('minPlayedInput'),
    minimum > 0 && candidatesBeforeMinimum.length > 0 && filteredData.length === 0
  );
  sortFilteredData();
  const eloValues = filteredData.map(row => Number(row.avg_elo)).filter(Number.isFinite);
  eloRange = {
    min: eloValues.length ? Math.min(...eloValues) : null,
    max: eloValues.length ? Math.max(...eloValues) : null,
  };
  const pages = Math.max(1, Math.ceil(filteredData.length / rowsPerPage));
  currentPage = Math.min(currentPage, pages);
  renderTable(preserveHead);
}

function sortFilteredData() {
  const direction = sortState.dir === 'asc' ? 1 : -1;
  filteredData.sort((a, b) => {
    const av = a[sortState.col];
    const bv = b[sortState.col];
    if (typeof av === 'string' || typeof bv === 'string') {
      return String(av || '').localeCompare(String(bv || '')) * direction;
    }
    const an = Number(av);
    const bn = Number(bv);
    if (!Number.isFinite(an) && !Number.isFinite(bn)) return 0;
    if (!Number.isFinite(an)) return 1;
    if (!Number.isFinite(bn)) return -1;
    return (an - bn) * direction;
  });
}

function sortCombinations(col) {
  if (sortState.col === col) sortState.dir = sortState.dir === 'desc' ? 'asc' : 'desc';
  else sortState = {
    col,
    dir: ['card_1', 'card_2', 'card_name', 'map_name', 'round_name', 'pair_type', 'card_type'].includes(col)
      ? 'asc'
      : 'desc',
  };
  currentPage = 1;
  applyClientFilters();
}

function renderTable(preserveHead = false) {
  if (!preserveHead) renderHead();
  const meta = document.getElementById('tableMeta');
  const start = filteredData.length ? (currentPage - 1) * rowsPerPage + 1 : 0;
  const end = Math.min(currentPage * rowsPerPage, filteredData.length);
  if (meta) meta.innerHTML = `Showing <strong>${start}-${end}</strong> of <strong>${filteredData.length}</strong> combinations`;
  const tbody = document.getElementById('tableBody');
  if (!tbody) return;
  const pageRows = filteredData.slice(start ? start - 1 : 0, end);
  tbody.innerHTML = pageRows.length
    ? pageRows.map((row, index) => rowHtml(row, start + index)).join('')
    : '<tr><td colspan="9"><div class="state-overlay"><div class="state-title">No combinations found</div></div></td></tr>';
  renderPagination();
}

function renderHead() {
  const thead = document.getElementById('tableHead');
  if (!thead) return;
  const table = document.getElementById('statsTable');
  table?.classList.toggle('combinations-pair-table', activeView === 'card_card');
  table?.classList.toggle('combinations-map-table', activeView !== 'card_card');
  if (activeView === 'card_map' || activeView === 'card_round') {
    const isMap = activeView === 'card_map';
    const contextLabel = isMap ? 'Map' : 'Round';
    const cardWidth = isMap ? '16%' : '20%';
    const contextWidth = isMap ? '18%' : '11%';
    const deltaCardWidth = isMap ? '11%' : '12%';
    const contextDeltaWidth = isMap ? '11%' : '12%';
    const eloWidth = isMap ? '7%' : '8%';
    const contextDeltaLabel = isMap ? '\u0394 (On Map)' : '\u0394 (Round)';
    thead.innerHTML = `<tr>
      <th style="width:5%">#</th>
      ${cardFilterHeader('card_name', 'Card', 1, cardWidth)}
      ${isMap ? mapFilterHeader(contextWidth) : roundFilterHeader(contextWidth)}
      ${header('delta_general', '\u0394 (Card)',
        'average elo gain when this card was played overall', deltaCardWidth)}
      ${header(isMap ? 'delta_map' : 'delta_round', contextDeltaLabel,
        `average elo gain when played in this specific ${contextLabel.toLowerCase()}`, contextDeltaWidth)}
      ${header('interaction', 'Synergy', `${contextDeltaLabel} - \u0394 (Card)`, '12%')}
      ${header('avg_elo', 'Elo',
        `average player elo when the card was played in this specific ${contextLabel.toLowerCase()}`, eloWidth)}
      ${header('n_played', 'Played',
        `n (card played in this specific ${contextLabel.toLowerCase()})`, '10%')}
      ${singleCardTypeFilterHeader('10%')}
    </tr>`;
    return;
  }
  thead.innerHTML = `<tr>
    <th style="width:5%">#</th>
    ${cardFilterHeader('card_1', 'Card 1', 1, '19%')}
    ${cardFilterHeader('card_2', 'Card 2', 2, '19%')}
    ${header('delta_combined', '\u0394 (Sum)', '\u0394 (Card 1) + \u0394 (Card 2)', '11%')}
    ${header('delta_actual', '\u0394 (Actual)',
      'average elo gain when both cards were played in the same game by the same player', '11%')}
    ${header('interaction', 'Synergy',
      '\u0394 (Actual) - \u0394 (Combined)', '11%')}
    ${header('avg_elo', 'Elo', 'average player elo when both cards were played', '7%')}
    ${header('n_played', 'Played', 'n (both cards played)', '9%')}
    <th class="type-filter-header combination-type-header ${selectedTypes.size === PAIR_TYPES.length ? '' : 'type-filter-active'}"
        style="width:8%" onclick="toggleCombinationTypePopup(event)">
      <span class="type-filter-label">Type
        <span class="type-filter-indicator type-filter-icon">${selectedTypes.size === PAIR_TYPES.length ? '' : `(${selectedTypes.size})`}</span>
      </span>
      <div class="type-filter-popup combination-type-popup" id="combinationTypePopup">
        <div class="combination-popup-actions map-select-all-none">
          <span class="map-toggle-link" onclick="selectAllCombinationTypes(event)">all</span> /
          <span class="map-toggle-link" onclick="selectNoneCombinationTypes(event)">none</span>
        </div>
        ${PAIR_TYPES.map(type => `<button class="chip ${selectedTypes.has(type) ? 'active' : ''}"
          data-type="${escapeAttr(type)}" onclick="toggleCombinationType(this.dataset.type, event)">${escapeHtml(type)}</button>`).join('')}
      </div>
    </th>
  </tr>`;
}

function header(field, label, tooltip = '', width = '') {
  const active = sortState.col === field;
  const arrow = active ? (sortState.dir === 'desc' ? '\u2193' : '\u2191') : '\u2195';
  const labelHtml = `${label}${tooltip ? `<span class="col-tip" data-tip="${escapeAttr(tooltip)}">?</span>` : ''}`;
  const isPairMetricHeader = activeView === 'card_card'
    && ['delta_combined', 'delta_actual', 'interaction', 'avg_elo', 'n_played'].includes(field);
  if (isPairMetricHeader) {
    return `<th class="${active ? 'sorted' : ''}" style="${width ? `width:${width};` : ''}" onclick="sortCombinations('${field}')"><span class="combo-card-card-metric-header"><span class="combo-card-card-header-label">${labelHtml}</span><span class="sort-arrow ${active ? 'active' : ''}">${arrow}</span></span></th>`;
  }
  return `<th class="${active ? 'sorted' : ''}" style="${width ? `width:${width};` : ''}" onclick="sortCombinations('${field}')">${labelHtml}<span class="sort-arrow ${active ? 'active' : ''}">${arrow}</span></th>`;
}

function cardFilterHeader(field, label, slot, width = '20%') {
  const selected = slot === 1 ? selectedOne : selectedTwo;
  const active = sortState.col === field;
  const arrow = active ? (sortState.dir === 'desc' ? '\u2193' : '\u2191') : '\u2195';
  return `<th class="card-search-header combination-card-filter-header ${active ? 'sorted' : ''}" style="width:${width}"
              onclick="sortCombinations('${field}')">
    <div class="card-header-content">
      <button class="card-search-btn ${selected ? 'search-active combination-filter-clear' : ''}"
        type="button" title="${selected ? `Clear ${label} filter` : `Filter ${label}`}"
        aria-label="${selected ? `Clear ${label} filter` : `Filter ${label}`}"
        onclick="${selected ? `clearCombinationSelection(${slot}, event)` : `openCombinationCardFilter(${slot}, event)`}">
        ${selected ? 'x' : '&#128269;'}
      </button>
      <span class="card-header-title ${selected ? 'combination-filter-active' : ''}">${escapeHtml(selected ? titleCase(selected) : label)}</span>
      <span class="sort-arrow ${active ? 'active' : ''}">${arrow}</span>
    </div>
    <div class="combination-header-popup combination-card-popup" id="combinationCardPopup${slot}"
         onclick="event.stopPropagation()">
      <input class="abilities-search-input" type="text" placeholder="Search cards..."
             oninput="renderCombinationCardChoices(${slot}, this.value)" />
      <div class="combination-card-choice-list" id="combinationCardChoices${slot}"></div>
    </div>
  </th>`;
}


function singleCardTypeFilterHeader(width = '10%') {
  const narrowed = selectedCardTypes.size !== CARD_TYPES.length;
  const indicatorText = narrowed ? (selectedCardTypes.size === 1 ? '\u2022' : '\u2022\u2022') : '';
  return `<th class="type-filter-header combination-single-type-header ${narrowed ? 'type-filter-active' : ''}"
              style="width:${width};text-align:center;cursor:pointer;"
              onclick="toggleCombinationSingleTypePopup(event)">
    <span class="type-filter-label">Type <span class="type-filter-indicator ${narrowed ? '' : 'type-filter-icon'}">${indicatorText}</span></span>
    <div class="type-filter-popup combination-single-type-popup" id="combinationSingleTypePopup">
      ${CARD_TYPES.map(type => `<button class="chip ${selectedCardTypes.has(type) ? 'active' : ''}"
        type="button" data-type="${escapeAttr(type)}"
        onclick="toggleCombinationSingleType(this.dataset.type, event)">${escapeHtml(titleCase(type))}</button>`).join('')}
    </div>
  </th>`;
}

function mapFilterHeader(width = '20%') {
  const narrowed = selectedHeaderMaps.size !== MAPS.length;
  return `<th class="combination-map-filter-header ${narrowed ? 'combination-header-filter-active' : ''}"
              style="width:${width}">
    <span class="combination-context-filter-header">
      <span class="combination-context-filter-title">Map</span>
      <button class="combination-map-filter-btn ${narrowed ? 'search-active' : ''}" type="button"
              aria-label="Filter maps" title="Filter maps" onclick="toggleCombinationMapPopup(event)">
        ${narrowed
          ? `<span class="combination-filter-count">${selectedHeaderMaps.size}/${MAPS.length}</span>`
          : '<span class="type-filter-indicator type-filter-icon"></span>'}
      </button>
    </span>
    <div class="combination-header-popup combination-map-popup" id="combinationMapPopup"
         onclick="event.stopPropagation()">
      <div class="combination-popup-actions map-select-all-none">
        <span class="map-toggle-link" onclick="selectAllCombinationHeaderMaps()">all</span> /
        <span class="map-toggle-link" onclick="selectNoneCombinationHeaderMaps()">none</span>
      </div>
      <div class="combination-map-choice-grid">
        ${MAPS.map(([short, full]) => `<button class="chip ${selectedHeaderMaps.has(full) ? 'active' : ''}"
          type="button" data-map="${escapeAttr(full)}" data-tooltip="${escapeAttr(full)}"
          onclick="toggleCombinationHeaderMap(this.dataset.map, event)">${escapeHtml(short)}</button>`).join('')}
      </div>
    </div>
  </th>`;
}

function roundFilterHeader(width = '20%') {
  const active = sortState.col === 'round_name';
  const narrowed = selectedHeaderRounds.size !== ROUNDS.length;
  const arrow = active ? (sortState.dir === 'desc' ? '\u2193' : '\u2191') : '\u2195';
  return `<th class="combination-round-filter-header ${active ? 'sorted' : ''}" style="width:${width}" onclick="sortCombinations('round_name')">
    <span class="combination-context-filter-header">
      <span class="combination-context-filter-title ${narrowed ? 'combination-filter-active' : ''}">Round</span>
      <button class="combination-map-filter-btn ${narrowed ? 'search-active' : ''}" type="button"
              aria-label="Filter rounds" title="Filter rounds" onclick="toggleCombinationRoundPopup(event)">
        <span class="type-filter-indicator type-filter-icon">${narrowed ? `(${selectedHeaderRounds.size})` : ''}</span>
      </button>
      <span class="sort-arrow ${active ? 'active' : ''}">${arrow}</span>
    </span>
    <div class="combination-header-popup combination-map-popup" id="combinationRoundPopup"
         onclick="event.stopPropagation()">
      <div class="combination-popup-actions map-select-all-none">
        <span class="map-toggle-link" onclick="selectAllCombinationHeaderRounds()">all</span> /
        <span class="map-toggle-link" onclick="selectNoneCombinationHeaderRounds()">none</span>
      </div>
      <div class="combination-map-choice-grid combination-round-choice-grid">
        ${ROUNDS.map(round => `<button class="chip ${selectedHeaderRounds.has(round) ? 'active' : ''}"
          type="button" data-round="${round}"
          onclick="toggleCombinationHeaderRound(this.dataset.round, event)">${round}</button>`).join('')}
      </div>
    </div>
  </th>`;
}

function rowHtml(row, rank) {
  if (activeView === 'card_map' || activeView === 'card_round') {
    const isMap = activeView === 'card_map';
    return `<tr>
      <td class="rank-cell">${rank}</td>
      <td class="combination-card-cell">${escapeHtml(titleCase(row.card_name))}</td>
      <td>${escapeHtml(isMap ? formatMapName(row.map_name) : row.round_name)}</td>
      ${deltaTd(row.delta_general)}${deltaTd(isMap ? row.delta_map : row.delta_round)}
      ${interactionTd(row.interaction)}
      <td class="elo-cell" style="color:${eloColor(row.avg_elo)}">${formatNumber(row.avg_elo, 0)}</td>
      <td class="n-cell">${formatInteger(row.n_played)}</td>
      <td>${singleTypeBadge(row.card_type)}</td>
    </tr>`;
  }
  return `<tr>
    <td class="rank-cell">${rank}</td>
    ${combinedCardTd(row.card_1, row.delta_1)}
    ${combinedCardTd(row.card_2, row.delta_2)}
    ${deltaTd(row.delta_combined)}${deltaTd(row.delta_actual)}
    ${interactionTd(row.interaction)}
    <td class="elo-cell" style="color:${eloColor(row.avg_elo)}">${formatNumber(row.avg_elo, 0)}</td>
    <td class="n-cell">${formatInteger(row.n_played)}</td>
    <td>${pairTypeBadge(row.type_1, row.type_2)}</td>
  </tr>`;
}

function combinedCardTd(cardName, delta) {
  const value = Number(delta);
  return `<td class="combination-card-cell combination-card-with-delta">
    <span class="combination-card-name">${escapeHtml(titleCase(cardName))}</span>
    <span class="combination-card-delta" style="color:${deltaColor(value)}">(${formatSigned(value)})</span>
  </td>`;
}

function singleTypeBadge(rawType) {
  const type = String(rawType || '').toLowerCase();
  const safeType = ['animal', 'project', 'sponsor'].includes(type) ? type : 'unknown';
  return `<span class="type-badge type-${safeType}">${escapeHtml(titleCase(type || 'unknown'))}</span>`;
}

function pairTypeBadge(rawTypeOne, rawTypeTwo) {
  const typeOrder = { animal: 0, project: 1, sponsor: 2 };
  const [typeOne, typeTwo] = [rawTypeOne, rawTypeTwo]
    .map(value => String(value || '').toLowerCase())
    .sort((a, b) => (typeOrder[a] ?? 99) - (typeOrder[b] ?? 99));
  const safeOne = ['animal', 'project', 'sponsor'].includes(typeOne) ? typeOne : 'unknown';
  const safeTwo = ['animal', 'project', 'sponsor'].includes(typeTwo) ? typeTwo : 'unknown';
  return `<span class="combination-type-badge">
    <span class="combination-type-part type-${safeOne}">${escapeHtml(titleCase(typeOne || 'unknown'))}</span>
    <span class="combination-type-separator" aria-hidden="true"></span>
    <span class="combination-type-part type-${safeTwo}">${escapeHtml(titleCase(typeTwo || 'unknown'))}</span>
  </span>`;
}

function deltaTd(raw) {
  const value = Number(raw);
  return `<td class="delta" style="color:${deltaColor(value)}">${formatSigned(value)}</td>`;
}

function interactionTd(raw) {
  const value = Number(raw);
  return `<td class="combination-interaction" style="color:${interactionColor(value)}">${formatSigned(value)}</td>`;
}

function renderPagination() {
  const host = document.getElementById('pagination');
  if (!host) return;
  const total = Math.max(1, Math.ceil(filteredData.length / rowsPerPage));
  if (total <= 1) {
    hidePagination();
    return;
  }
  host.style.display = 'flex';
  let html = `<button class="page-btn" onclick="goCombinationPage(${currentPage - 1})"
    ${currentPage === 1 ? 'disabled' : ''}>&lsaquo;</button>`;
  const pages = paginationRange(currentPage, total);
  let previous = null;
  for (const page of pages) {
    if (previous !== null && page - previous > 1) html += '<span class="page-info">...</span>';
    html += `<button class="page-btn ${page === currentPage ? 'active' : ''}"
      onclick="goCombinationPage(${page})">${page}</button>`;
    previous = page;
  }
  html += `<button class="page-btn" onclick="goCombinationPage(${currentPage + 1})"
    ${currentPage === total ? 'disabled' : ''}>&rsaquo;</button>`;
  host.innerHTML = html;
}

function paginationRange(current, total) {
  const range = [];
  for (let page = Math.max(1, current - 2); page <= Math.min(total, current + 2); page += 1) {
    range.push(page);
  }
  if (!range.includes(1)) range.unshift(1);
  if (!range.includes(total)) range.push(total);
  return range;
}

function goCombinationPage(page) {
  const total = Math.max(1, Math.ceil(filteredData.length / rowsPerPage));
  const nextPage = Number(page);
  if (nextPage < 1 || nextPage > total) return;
  currentPage = nextPage;
  renderTable();
  document.querySelector('.combinations-table-wrap')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function onCombinationRowsChange() {
  rowsPerPage = Number(document.getElementById('rppSelect')?.value || 50);
  currentPage = 1;
  renderTable();
}

function onCombinationFilterChange() {
  currentPage = 1;
  applyClientFilters();
}

function toggleCombinationTypePopup(event) {
  event.stopPropagation();
  if (event.target.closest('.combination-type-popup')) return;
  const popup = document.getElementById('combinationTypePopup');
  if (!popup) return;
  const opening = !popup.classList.contains('open');
  closeCombinationHeaderPopups();
  popup.classList.toggle('open', opening);
  if (!opening) return;
  popup.dataset.openHeight = String(
    popup.getBoundingClientRect().height || popup.scrollHeight || 120
  );
  positionCombinationPairTypePopup(popup);
}

function toggleCombinationType(type, event) {
  event.stopPropagation();
  if (selectedTypes.size === PAIR_TYPES.length && selectedTypes.has(type)) selectedTypes = new Set([type]);
  else if (selectedTypes.has(type)) selectedTypes.delete(type);
  else selectedTypes.add(type);
  currentPage = 1;
  updateCombinationTypeHeader();
  applyClientFilters({ preserveHead: true });
}

function selectAllCombinationTypes(event) {
  if (event) event.stopPropagation();
  selectedTypes = new Set(PAIR_TYPES);
  currentPage = 1;
  updateCombinationTypeHeader();
  applyClientFilters({ preserveHead: true });
}

function selectNoneCombinationTypes(event) {
  if (event) event.stopPropagation();
  selectedTypes = new Set();
  currentPage = 1;
  updateCombinationTypeHeader();
  applyClientFilters({ preserveHead: true });
}

function updateCombinationTypeHeader() {
  const header = document.querySelector('.combination-type-header');
  if (!header) return;
  const narrowed = selectedTypes.size !== PAIR_TYPES.length;
  header.classList.toggle('type-filter-active', narrowed);
  const indicator = header.querySelector('.type-filter-indicator');
  if (indicator) indicator.textContent = narrowed ? `(${selectedTypes.size})` : '';
  header.querySelectorAll('[data-type]').forEach(button => {
    button.classList.toggle('active', selectedTypes.has(button.dataset.type));
  });
}


function toggleCombinationSingleTypePopup(event) {
  event.stopPropagation();
  if (event.target.closest('.type-filter-popup')) return;
  const popup = document.getElementById('combinationSingleTypePopup');
  if (!popup) return;
  const opening = !popup.classList.contains('open');
  closeCombinationHeaderPopups();
  if (!opening) return;
  popup.classList.add('open');
  positionCombinationCenteredPopup(popup, event.currentTarget.closest('th'), 110);
}

function toggleCombinationSingleType(type, event) {
  if (event) event.stopPropagation();
  if (!CARD_TYPES.includes(type)) return;
  if (selectedCardTypes.size === CARD_TYPES.length && selectedCardTypes.has(type)) {
    selectedCardTypes = new Set([type]);
  } else if (selectedCardTypes.size === 1 && selectedCardTypes.has(type)) {
    return;
  } else if (selectedCardTypes.has(type)) {
    selectedCardTypes.delete(type);
  } else {
    selectedCardTypes.add(type);
  }
  currentPage = 1;
  applyClientFilters();
  reopenCombinationPopup('singleType');
}

function openCombinationCardFilter(slot, event) {
  event.stopPropagation();
  closeCombinationHeaderPopups();
  const popup = document.getElementById(`combinationCardPopup${slot}`);
  if (!popup) return;
  popup.classList.add('open');
  renderCombinationCardChoices(slot, '');
  positionCombinationPopup(popup, event.currentTarget.closest('th'), 280);
  const input = popup.querySelector('input');
  if (input) input.focus({ preventScroll: true });
}

function renderCombinationCardChoices(slot, query = '') {
  const results = document.getElementById(`combinationCardChoices${slot}`);
  if (!results) return;
  const needle = normalize(query);
  const excluded = slot === 1 ? selectedTwo : selectedOne;
  const matches = cardCatalogue.filter(card => {
    if (card === excluded) return false;
    if (!needle) return true;
    return normalize(card).includes(needle)
      || (cardAliases.get(normalize(card)) || []).some(alias => alias.includes(needle));
  });
  results.innerHTML = matches.map(card =>
    `<button class="combination-card-choice" type="button" data-card="${escapeAttr(card)}"
      onclick="selectCombinationCard(${slot}, this.dataset.card)">${escapeHtml(titleCase(card))}</button>`
  ).join('');
  if (!matches.length) results.innerHTML = '<div class="abilities-list-empty">No cards match.</div>';
}

function selectCombinationCard(slot, card) {
  if (slot === 1) {
    selectedOne = card;
  } else {
    selectedTwo = card;
  }
  if (selectedOne === selectedTwo) {
    if (slot === 1) selectedTwo = '';
    else selectedOne = '';
  }
  currentPage = 1;
  closeCombinationHeaderPopups();
  applyClientFilters();
}

function clearCombinationSelection(slot, event) {
  if (event) event.stopPropagation();
  if (slot === 1) selectedOne = '';
  else selectedTwo = '';
  currentPage = 1;
  closeCombinationHeaderPopups();
  applyClientFilters();
}

function toggleCombinationMapPopup(event) {
  event.stopPropagation();
  const popup = document.getElementById('combinationMapPopup');
  if (!popup) return;
  const opening = !popup.classList.contains('open');
  closeCombinationHeaderPopups();
  if (!opening) return;
  popup.classList.add('open');
  positionCombinationPopup(popup, event.currentTarget.closest('th'), 250);
}

function toggleCombinationHeaderMap(map, event) {
  if (event) event.stopPropagation();
  if (selectedHeaderMaps.size === MAPS.length && selectedHeaderMaps.has(map)) {
    selectedHeaderMaps = new Set([map]);
  } else if (selectedHeaderMaps.has(map)) {
    selectedHeaderMaps.delete(map);
  } else {
    selectedHeaderMaps.add(map);
  }
  currentPage = 1;
  updateCombinationMapHeader();
  applyClientFilters({ preserveHead: true });
}

function selectAllCombinationHeaderMaps() {
  selectedHeaderMaps = new Set(MAPS.map(([, full]) => full));
  currentPage = 1;
  updateCombinationMapHeader();
  applyClientFilters({ preserveHead: true });
}

function selectNoneCombinationHeaderMaps() {
  selectedHeaderMaps = new Set();
  currentPage = 1;
  updateCombinationMapHeader();
  applyClientFilters({ preserveHead: true });
}

function updateCombinationMapHeader() {
  const header = document.querySelector('.combination-map-filter-header');
  if (!header) return;
  const narrowed = selectedHeaderMaps.size !== MAPS.length;
  header.classList.toggle('combination-header-filter-active', narrowed);
  const button = header.querySelector('.combination-map-filter-btn');
  if (button) {
    button.classList.toggle('search-active', narrowed);
    button.innerHTML = narrowed
      ? `<span class="combination-filter-count">${selectedHeaderMaps.size}/${MAPS.length}</span>`
      : '<span class="type-filter-indicator type-filter-icon"></span>';
  }
  header.querySelectorAll('[data-map]').forEach(chip => {
    chip.classList.toggle('active', selectedHeaderMaps.has(chip.dataset.map));
  });
}

function toggleCombinationRoundPopup(event) {
  event.stopPropagation();
  const popup = document.getElementById('combinationRoundPopup');
  if (!popup) return;
  const opening = !popup.classList.contains('open');
  closeCombinationHeaderPopups();
  if (!opening) return;
  popup.classList.add('open');
  positionCombinationPopup(popup, event.currentTarget.closest('th'), 250);
}

function toggleCombinationHeaderRound(round, event) {
  if (event) event.stopPropagation();
  if (selectedHeaderRounds.size === ROUNDS.length && selectedHeaderRounds.has(round)) {
    selectedHeaderRounds = new Set([round]);
  } else if (selectedHeaderRounds.has(round)) {
    selectedHeaderRounds.delete(round);
  } else {
    selectedHeaderRounds.add(round);
  }
  currentPage = 1;
  applyClientFilters();
  reopenCombinationPopup('round');
}

function selectAllCombinationHeaderRounds() {
  selectedHeaderRounds = new Set(ROUNDS);
  currentPage = 1;
  applyClientFilters();
  reopenCombinationPopup('round');
}

function selectNoneCombinationHeaderRounds() {
  selectedHeaderRounds = new Set();
  currentPage = 1;
  applyClientFilters();
  reopenCombinationPopup('round');
}


function positionCombinationCenteredPopup(popup, anchor, preferredWidth) {
  if (!popup || !anchor) return;
  const margin = 8;
  const gap = 0;
  const rect = anchor.getBoundingClientRect();
  const popupHeight = Number(popup.dataset.openHeight)
    || popup.getBoundingClientRect().height
    || popup.scrollHeight
    || 120;
  const anchoredTop = rect.bottom + gap;
  if (anchoredTop + popupHeight <= 0 || anchoredTop >= window.innerHeight) {
    popup.classList.remove('open');
    return;
  }
  const width = popup.offsetWidth || preferredWidth;
  const left = rect.left + (rect.width / 2) - (width / 2);
  popup.style.left = `${Math.max(margin, Math.min(left, window.innerWidth - width - margin))}px`;
  popup.style.top = `${anchoredTop}px`;
}

function positionCombinationPopup(popup, anchor, preferredWidth) {
  if (!popup || !anchor) return;
  const margin = 8;
  const gap = 0;
  const rect = anchor.getBoundingClientRect();
  if (rect.bottom <= 0 || rect.top >= window.innerHeight) {
    popup.classList.remove('open');
    return;
  }
  const width = popup.offsetWidth || preferredWidth;
  const tableRight = document.querySelector('.combinations-table-wrap')?.getBoundingClientRect().right
    || window.innerWidth;
  const rightBoundary = Math.min(window.innerWidth, tableRight);
  const left = Math.max(margin, Math.min(rect.left, rightBoundary - width - margin));
  const maxTop = window.innerHeight - popup.offsetHeight - margin;
  popup.style.left = `${left}px`;
  popup.style.top = `${Math.max(margin, Math.min(rect.bottom + gap, maxTop))}px`;
}

function positionCombinationPairTypePopup(popup) {
  if (!popup) return;
  const headers = document.querySelectorAll('.combinations-pair-table thead th');
  const played = headers[7];
  const type = headers[8];
  if (!played || !type) return;
  const playedRect = played.getBoundingClientRect();
  const typeRect = type.getBoundingClientRect();
  const popupHeight = Number(popup.dataset.openHeight)
    || popup.getBoundingClientRect().height
    || popup.scrollHeight
    || 120;
  const anchoredTop = typeRect.bottom;
  if (anchoredTop + popupHeight <= 0 || anchoredTop >= window.innerHeight) {
    popup.classList.remove('open');
    return;
  }
  popup.style.left = `${playedRect.left}px`;
  popup.style.top = `${typeRect.bottom}px`;
  popup.style.width = `${typeRect.right - playedRect.left}px`;
}

function closeCombinationHeaderPopups() {
  document.querySelectorAll('.combination-header-popup.open, .combination-type-popup.open, .combination-single-type-popup.open')
    .forEach(popup => popup.classList.remove('open'));
}

function reopenCombinationPopup(kind) {
  // Reopen after the originating click has fully bubbled. This keeps the newly
  // rendered popup from being mistaken for an outside-click target.
  window.setTimeout(() => {
    if (!mounted) return;
    if (kind === 'map') {
      const popup = document.getElementById('combinationMapPopup');
      const anchor = document.querySelector('.combination-map-filter-header');
      if (!popup || !anchor) return;
      popup.classList.add('open');
      positionCombinationPopup(popup, anchor, 250);
      return;
    }
    if (kind === 'round') {
      const popup = document.getElementById('combinationRoundPopup');
      const anchor = document.querySelector('.combination-round-filter-header');
      if (!popup || !anchor) return;
      popup.classList.add('open');
      positionCombinationPopup(popup, anchor, 250);
      return;
    }
    if (kind === 'singleType') {
      const popup = document.getElementById('combinationSingleTypePopup');
      const anchor = document.querySelector('.combination-single-type-header');
      if (!popup || !anchor) return;
      popup.classList.add('open');
      positionCombinationCenteredPopup(popup, anchor, 110);
      return;
    }
    const popup = document.getElementById('combinationTypePopup');
    if (!popup) return;
    popup.classList.add('open');
    positionCombinationPairTypePopup(popup);
  }, 0);
}

function repositionOpenCombinationPopups() {
  if (!mounted) return;
  const placements = [
    ['#combinationMapPopup', 250, false],
    ['#combinationRoundPopup', 250, false],
    ['#combinationSingleTypePopup', 110, true],
    ['#combinationCardPopup1', 280, false],
    ['#combinationCardPopup2', 280, false],
  ];
  placements.forEach(([popupSelector, width, centered]) => {
    const popup = document.querySelector(popupSelector);
    const anchor = popup?.closest('th');
    if (!popup?.classList.contains('open') || !anchor) return;
    if (centered) positionCombinationCenteredPopup(popup, anchor, width);
    else positionCombinationPopup(popup, anchor, width);
  });
  const pairTypePopup = document.getElementById('combinationTypePopup');
  if (pairTypePopup?.classList.contains('open')) positionCombinationPairTypePopup(pairTypePopup);
}

function renderMapChips() {
  const host = document.getElementById('mapChips');
  if (!host) return;
  host.innerHTML = MAPS.map(([short, full]) =>
    `<button class="chip ${selectedMaps.includes(full) ? 'active' : ''}" type="button"
      data-map="${escapeAttr(full)}" title="${escapeAttr(full)}"
      onclick="toggleMapChip(this.dataset.map)">${short}</button>`
  ).join('');
}

function toggleMapChip(map) {
  if (selectedMaps.length === MAPS.length && selectedMaps.includes(map)) selectedMaps = [map];
  else if (selectedMaps.includes(map)) selectedMaps = selectedMaps.filter(item => item !== map);
  else selectedMaps.push(map);
  renderMapChips();
}

function selectAllMaps() {
  selectedMaps = MAPS.map(([, full]) => full);
  renderMapChips();
}

function selectNoneMaps() {
  selectedMaps = [];
  renderMapChips();
}

function renderRoundChips() {
  const host = document.getElementById('roundChips');
  if (!host) return;
  host.innerHTML = ROUNDS.map(round => `
    <button class="chip ${selectedRounds.has(round) ? 'active' : ''}" type="button"
            data-round="${round}" onclick="toggleRoundChip(this.dataset.round)">${round}</button>
  `).join('');
}

function toggleRoundChip(round) {
  if (selectedRounds.size === ROUNDS.length && selectedRounds.has(round)) {
    selectedRounds = new Set([round]);
  } else if (selectedRounds.has(round)) {
    selectedRounds.delete(round);
  } else {
    selectedRounds.add(round);
  }
  renderRoundChips();
}

function selectAllRounds() {
  selectedRounds = new Set(ROUNDS);
  renderRoundChips();
}

function selectNoneRounds() {
  selectedRounds = new Set();
  renderRoundChips();
}

function resetFilters() {
  const set = (id, value) => {
    const element = document.getElementById(id);
    if (element) element.value = value;
  };
  set('playerEloMin', '300'); set('playerEloMax', '');
  set('opponentEloMin', '300'); set('opponentEloMax', '');
  set('dateFrom', '2025-01-01'); set('dateTo', '');
  const completed = document.getElementById('endGameToggle');
  if (completed) completed.checked = false;
  selectAllMaps();
  selectAllRounds();
  selectedCardTypes = new Set(CARD_TYPES);
  applyFilters(++mountToken);
}

function applyFiltersFromSidebar() {
  applyFilters(++mountToken);
  document.getElementById('sidebar')?.classList.remove('open');
  document.getElementById('sidebarOverlay')?.classList.remove('active');
}

function hidePagination() {
  const host = document.getElementById('pagination');
  if (!host) return;
  host.style.display = 'none';
  host.innerHTML = '';
}

function renderLoading() {
  renderHead();
  document.querySelectorAll('#statsTable th.sorted').forEach(th => th.classList.remove('sorted'));
  document.querySelectorAll('#statsTable .sort-arrow').forEach(arrow => {
    arrow.classList.remove('active');
    arrow.textContent = '\u2195';
  });
  hidePagination();
  const body = document.getElementById('tableBody');
  if (body) body.innerHTML = '<tr><td colspan="9"><div class="state-overlay"><div class="spinner"></div><div class="state-title">Fetching combinations...</div></div></td></tr>';
}

function renderError(error) {
  hidePagination();
  const body = document.getElementById('tableBody');
  if (body) body.innerHTML = `<tr><td colspan="9"><div class="state-overlay"><div class="state-title">Could not load combinations</div><div class="state-sub">${escapeHtml(error.message || error)}</div></div></td></tr>`;
}

function deltaColor(value) {
  if (!Number.isFinite(value)) return 'var(--text-muted)';
  if (value >= 0.6) return 'var(--pos-strong)';
  if (value >= 0.3) return 'var(--pos-mid)';
  if (value >= 0.05) return 'var(--pos-weak)';
  if (value >= -0.05) return 'var(--neutral)';
  if (value >= -0.3) return 'var(--neg-weak)';
  if (value >= -0.6) return 'var(--neg-mid)';
  return 'var(--neg-strong)';
}

function interactionColor(value) {
  if (!Number.isFinite(value)) return 'var(--text-muted)';
  const t = Math.max(0, Math.min(1, (value + 1.5) / 3));
  const low = { r: 0xFF, g: 0x60, b: 0x27 };
  const high = { r: 0x7C, g: 0xBA, b: 0x43 };
  const mix = key => Math.round(low[key] + (high[key] - low[key]) * t);
  return `rgb(${mix('r')}, ${mix('g')}, ${mix('b')})`;
}

function eloColor(raw) {
  const value = Number(raw);
  if (!Number.isFinite(value)) return 'var(--text-muted)';
  if (!Number.isFinite(eloRange.min) || !Number.isFinite(eloRange.max) || eloRange.min === eloRange.max) {
    return 'var(--elo-mid)';
  }
  const t = (value - eloRange.min) / (eloRange.max - eloRange.min);
  if (t >= 0.66) return 'var(--elo-high)';
  if (t >= 0.33) return 'var(--elo-mid)';
  return 'var(--elo-low)';
}

function formatSigned(raw) {
  const value = Number(raw);
  return Number.isFinite(value) ? `${value >= 0 ? '+' : ''}${value.toFixed(3)}` : '-';
}

function formatNumber(raw, decimals) {
  const value = Number(raw);
  return Number.isFinite(value) ? value.toFixed(decimals) : '-';
}

function formatInteger(raw) {
  const value = Number(raw);
  return Number.isFinite(value) ? Math.round(value).toLocaleString('en-US') : '-';
}

function titleCase(value) {
  // Display-only formatting; raw names remain untouched for filters and API data.
  const lowerWords = new Set(['on', 'in', 'of', 'the', 'a']);
  const displayName = String(value || '')
    .split(' ')
    .map((word, index) => {
      const normalized = word.toLowerCase();
      if (index > 0 && lowerWords.has(normalized)) return normalized;
      return normalized.replace(
        /[A-Za-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u00FF]/,
        character => character.toUpperCase()
      );
    })
    .join(' ');

  return displayName
    .replace(/\bWaza\b/g, 'WAZA')
    .replace(/\bGalapagos\b/g, 'Gal\u00e1pagos');
}

function formatMapName(value) {
  const raw = String(value || '');
  const match = raw.match(/^Map\s+([^:]+):\s*(.+)$/);
  return match ? `${match[2]} (${match[1]})` : raw;
}

function normalize(value) {
  return String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
}

async function loadCardAliases() {
  try {
    const response = await fetch(CARD_ALIASES_URL, { cache: 'no-cache' });
    if (!response.ok) throw new Error(`Could not load ${CARD_ALIASES_URL}`);
    const rows = parseCsv(await response.text());
    const aliases = new Map();
    rows.slice(1).forEach(row => {
      const cardName = normalize(row[0]);
      const values = String(row[1] || '').split(';').map(normalize).filter(Boolean);
      if (cardName && values.length) aliases.set(cardName, values);
    });
    cardAliases = aliases;
  } catch (error) {
    console.warn('Card aliases were not loaded. Combo search will use card names only.', error);
    cardAliases = new Map();
  }
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = '';
  let inQuotes = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const next = text[index + 1];
    if (char === '"') {
      if (inQuotes && next === '"') {
        field += '"';
        index += 1;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (char === ',' && !inQuotes) {
      row.push(field);
      field = '';
    } else if ((char === '\n' || char === '\r') && !inQuotes) {
      if (char === '\r' && next === '\n') index += 1;
      row.push(field);
      if (row.some(cell => cell.trim())) rows.push(row);
      row = [];
      field = '';
    } else {
      field += char;
    }
  }
  row.push(field);
  if (row.some(cell => cell.trim())) rows.push(row);
  if (rows[0]?.[0]) rows[0][0] = rows[0][0].replace(/^\uFEFF/, '');
  return rows;
}

function escapeHtml(value) {
  return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}

function escapeAttr(value) {
  return escapeHtml(value);
}

const getCombinationColTooltip = () => document.getElementById('col-tooltip');

document.addEventListener('mouseover', event => {
  const tooltip = getCombinationColTooltip();
  if (!mounted || !tooltip) return;
  const tip = event.target.closest('.col-tip');
  if (!tip) return;
  tooltip.textContent = tip.dataset.tip || '';
  tooltip.style.display = 'block';
  positionTooltip(event);
});

document.addEventListener('mousemove', event => {
  const tooltip = getCombinationColTooltip();
  if (!mounted || !tooltip || tooltip.style.display === 'none') return;
  if (!event.target.closest('.col-tip')) return hideTooltip();
  positionTooltip(event);
});

document.addEventListener('mouseout', event => {
  if (!mounted || !event.target.closest('.col-tip')) return;
  hideTooltip();
});

document.addEventListener('click', event => {
  if (!mounted) return;
  if (event.target.closest('#filterToggleBtn, .sidebar-close-btn, .attributes-bar-header')) return;
  if (!event.target.closest(
    '.combination-card-filter-header, .combination-map-filter-header, ' +
    '.combination-round-filter-header, .combination-type-header, .combination-single-type-header'
  )) closeCombinationHeaderPopups();
});

window.addEventListener('resize', repositionOpenCombinationPopups);
window.addEventListener('scroll', repositionOpenCombinationPopups, true);
document.addEventListener('scroll', repositionOpenCombinationPopups, true);

function positionTooltip(event) {
  const tooltip = getCombinationColTooltip();
  if (!tooltip) return;
  const margin = 8;
  const width = tooltip.offsetWidth;
  const height = tooltip.offsetHeight;
  let left = event.clientX - width / 2;
  let top = event.clientY + 18;
  left = Math.max(margin, Math.min(left, window.innerWidth - width - margin));
  if (top + height > window.innerHeight - margin) top = event.clientY - height - 10;
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

function hideTooltip() {
  const tooltip = getCombinationColTooltip();
  if (tooltip) tooltip.style.display = 'none';
}
