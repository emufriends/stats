export const id = 'maps';
import {
  cappedNumericRange,
  cssColorRgb,
  deltaRangeColor,
  divergingRangeColor,
  normalizeToRange,
  numericRange,
  orangeGreenRangeColor,
} from '../color-scales.js?v=20260711-1';
import { formatSignedDeltaAdaptive, mapTooltipLabel } from '../table-cells.js?v=20260712-4';
import { loadSnapshot, fetchStats } from '../snapshot-cache.js?v=20260713-1';

export const title = 'Maps';
export const navLabel = 'Maps';

const METRICS_VIEW = 'metrics';
const H2H_VIEW = 'tournament_h2h';
const METRICS_DEFAULT_DATE_FROM = '2026-01-13';

export const mainHtml = `
  <div class="main-header maps-main-header">
    <div class="table-meta" id="tableMeta"></div>
  </div>

  <div class="attributes-bar endgames-tabs-bar maps-tabs-bar">
    <div class="attributes-bar-header endgames-tabs-header maps-tabs-header">
      <div class="endgames-tabs maps-tabs" role="tablist" aria-label="Maps views">
        <button class="endgames-tab active" type="button" data-view="metrics" onclick="setMapsView('metrics')">Metrics</button>
        <button class="endgames-tab" type="button" data-view="tournament_h2h" onclick="setMapsView('tournament_h2h')" title="Head-to-head record in all UEFA tournaments">Tournament H2H</button>
      </div>
    </div>
  </div>

  <div class="table-wrap maps-table-wrap">
    <div class="table-scroll">
      <table id="statsTable" class="maps-table maps-metrics-table">
        <thead id="tableHead"></thead>
        <tbody id="tableBody">
          <tr><td colspan="17">
            <div class="state-overlay">
              <div class="spinner"></div>
              <div class="state-title">Fetching data...</div>
              <div class="state-sub">Querying map metrics.</div>
            </div>
          </td></tr>
        </tbody>
        <tfoot id="tableFoot"></tfoot>
      </table>
    </div>
  </div>`;

export const sidebarHtml = `
  <div class="sidebar-header">
    <span class="sidebar-title">Filters</span>
    <div style="display:flex;align-items:center;gap:6px;">
      <button class="reset-btn" onclick="resetFilters()">Reset</button>
      <button class="sidebar-close-btn" onclick="toggleSidebar()" title="Close filters">x</button>
    </div>
  </div>

  <div class="maps-h2h-filter-note" id="mapsH2hFilterNote">Tournament H2H only uses the MW/Base switch.</div>

  <hr class="divider maps-metrics-filter" />

  <div class="filter-group maps-metrics-filter">
    <span class="filter-label">Player ELO</span>
    <div class="range-row">
      <input class="range-input" type="number" id="playerEloMin" placeholder="Min" value="300" min="0" />
      <input class="range-input" type="number" id="playerEloMax" placeholder="Max" min="0" />
    </div>
  </div>

  <div class="filter-group maps-metrics-filter">
    <span class="filter-label">Opponent ELO</span>
    <div class="range-row">
      <input class="range-input" type="number" id="opponentEloMin" placeholder="Min" value="300" min="0" />
      <input class="range-input" type="number" id="opponentEloMax" placeholder="Max" min="0" />
    </div>
  </div>

  <hr class="divider maps-metrics-filter" />

  <div class="filter-group maps-metrics-filter">
    <span class="filter-label">
      Date Range
      <span class="col-tip" data-tip="Map Pack 2 was added to the game on January 13th, 2026.">?</span>
    </span>
    <input class="date-input" type="text" inputmode="numeric" pattern="\\d{4}-\\d{2}-\\d{2}" placeholder="yyyy-mm-dd" id="dateFrom" value="2026-01-13" />
    <input class="date-input" type="text" inputmode="numeric" pattern="\\d{4}-\\d{2}-\\d{2}" placeholder="yyyy-mm-dd" id="dateTo" />
  </div>

  <hr class="divider maps-metrics-filter" />

  <div class="filter-action-stack maps-metrics-filter">
    <button class="apply-btn" id="applyBtn" onclick="applyFiltersFromSidebar()">Apply filters</button>
  </div>`;

const API_URL = 'https://europe-west1-ark-nova-stats-dashboard.cloudfunctions.net/get-card-stats';
const DEFAULT_SNAPSHOT_URLS = {
  metrics: {
    1: 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/maps/metrics/default-mw.json',
    0: 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/maps/metrics/default-base.json',
  },
  tournament_h2h: {
    1: 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/maps/tournament_h2h/default-mw.json',
    0: 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/maps/tournament_h2h/default-base.json',
  },
};

const FALLBACK_MAPS = [
  { code: '1a', key: 'map_1a', full: 'Map 1a: Observation Tower', visible_default: true },
  { code: '2a', key: 'map_2a', full: 'Map 2a: Outdoor Areas', visible_default: true },
  { code: '3a', key: 'map_3a', full: 'Map 3a: Silver Lake', visible_default: true },
  { code: '4a', key: 'map_4a', full: 'Map 4a: Commercial Harbor', visible_default: true },
  { code: '5a', key: 'map_5a', full: 'Map 5a: Park Restaurant', visible_default: true },
  { code: '6a', key: 'map_6a', full: 'Map 6a: Research Institute', visible_default: true },
  { code: '7a', key: 'map_7a', full: 'Map 7a: Ice Cream Parlors', visible_default: true },
  { code: '8a', key: 'map_8a', full: 'Map 8a: Hollywood Hills', visible_default: true },
  { code: '9', key: 'map_9', full: 'Map 9: Geographical Zoo', visible_default: true },
  { code: '10', key: 'map_10', full: 'Map 10: Rescue Station', visible_default: true },
  { code: '11', key: 'map_11', full: 'Map 11: Caves', visible_default: true },
  { code: '12', key: 'map_12', full: 'Map 12: Artificial Intelligence', visible_default: true },
  { code: '13', key: 'map_13', full: 'Map 13: Drawing Board', visible_default: true },
  { code: '14', key: 'map_14', full: 'Map 14: Lagoon', visible_default: true },
  { code: 'T1', key: 'map_t1', full: 'Map T1: Tournament 1', visible_default: true },
  { code: '1', key: 'map_1', full: 'Map 1: Observation Tower', visible_default: false },
  { code: '2', key: 'map_2', full: 'Map 2: Outdoor Areas', visible_default: false },
  { code: '3', key: 'map_3', full: 'Map 3: Silver Lake', visible_default: false },
  { code: '4', key: 'map_4', full: 'Map 4: Commercial Harbor', visible_default: false },
  { code: '5', key: 'map_5', full: 'Map 5: Park Restaurant', visible_default: false },
  { code: '6', key: 'map_6', full: 'Map 6: Research Institute', visible_default: false },
  { code: '7', key: 'map_7', full: 'Map 7: Ice Cream Parlors', visible_default: false },
  { code: '8', key: 'map_8', full: 'Map 8: Hollywood Hills', visible_default: false },
  { code: 'A', key: 'map_a', full: 'Map A', visible_default: false },
  { code: '0', key: 'map_0', full: 'Map 0', visible_default: false },
];

const PAGE_WINDOW_HANDLERS = {
  applyFiltersFromSidebar,
  resetFilters,
  setMapsView,
  setMapsH2hMode,
  setMapVisibilityMode,
  resetMetricsSwitches,
  sortMapsByHeader,
  sortMapsByMetric,
  sortH2hByOverall,
  sortH2hByMap,
};

let isMW = 1;
let isPageMounted = false;
let mountToken = 0;
let viewRows = { metrics: [], tournament_h2h: [] };
let mapMeta = FALLBACK_MAPS;
let visibleMaps = FALLBACK_MAPS;
let activeView = METRICS_VIEW;
let h2hMode = 'win';
let h2hSortByOverall = false;
let currentSortMetric = 'Turns';
let useNaturalMapOrder = false;
let mapVisibilityModes = {
  mapPack1: 'include',
  mapPack2: 'include',
  legacy: 'exclude',
  beginner: 'exclude',
};
const defaultSnapshotCache = {
  metrics: { 0: null, 1: null },
  tournament_h2h: { 0: null, 1: null },
};

export function mount({ dataset = 1 } = {}) {
  bindWindowHandlers();
  isPageMounted = true;
  const activeMountToken = ++mountToken;
  isMW = Number(dataset) === 0 ? 0 : 1;
  activeView = METRICS_VIEW;
  h2hMode = 'win';
  h2hSortByOverall = false;
  currentSortMetric = 'Turns';
  useNaturalMapOrder = false;
  mapVisibilityModes = {
    mapPack1: 'include',
    mapPack2: 'include',
    legacy: 'exclude',
    beginner: 'exclude',
  };
  viewRows = { metrics: [], tournament_h2h: [] };
  mapMeta = FALLBACK_MAPS;
  visibleMaps = FALLBACK_MAPS;
  setDefaultDates();
  updateVisibleMaps();
  renderTabs();
  syncFilterVisibility();
  renderTableHead();
  renderViewMeta();
  applyFilters(activeMountToken);
}

export function unmount() {
  isPageMounted = false;
  mountToken++;
  if (h2hResizeObserver) {
    h2hResizeObserver.disconnect();
    h2hResizeObserver = null;
  }
}

export function setDataset(dataset) {
  isMW = Number(dataset) === 0 ? 0 : 1;
  currentSortMetric = 'Turns';
  useNaturalMapOrder = false;
  applyFilters(++mountToken);
}

function bindWindowHandlers() {
  Object.assign(window, PAGE_WINDOW_HANDLERS);
}

function isCurrentMount(token) {
  return isPageMounted && token === mountToken;
}

function setMapsView(view) {
  activeView = view === H2H_VIEW ? H2H_VIEW : METRICS_VIEW;
  renderTabs();
  syncFilterVisibility();
  applyFilters(++mountToken);
}

function setMapsH2hMode(mode) {
  h2hMode = mode === 'elo' ? 'elo' : 'win';
  renderH2h();
}

function setMapVisibilityMode(category, mode) {
  if (!['mapPack1', 'mapPack2', 'legacy', 'beginner'].includes(category)) return;
  if (!['exclude', 'include', 'only'].includes(mode)) return;
  if (mode === 'only') {
    mapVisibilityModes = {
      mapPack1: 'exclude',
      mapPack2: 'exclude',
      legacy: 'exclude',
      beginner: 'exclude',
      [category]: 'only',
    };
  } else {
    mapVisibilityModes = { ...mapVisibilityModes, [category]: mode };
  }
  updateVisibleMaps();
  renderActiveView();
}

function resetMetricsSwitches() {
  if (activeView !== METRICS_VIEW) return;
  mapVisibilityModes = {
    mapPack1: 'include',
    mapPack2: 'include',
    legacy: 'exclude',
    beginner: 'exclude',
  };
  useNaturalMapOrder = false;
  currentSortMetric = 'Turns';
  updateVisibleMaps();
  renderActiveView();
}

function renderTabs() {
  document.querySelectorAll('.maps-tabs .endgames-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.view === activeView);
  });
}

function syncFilterVisibility() {
  const isH2h = activeView === H2H_VIEW;
  document.querySelectorAll('.maps-metrics-filter').forEach(el => {
    el.style.display = isH2h ? 'none' : '';
  });
  const note = document.getElementById('mapsH2hFilterNote');
  if (note) note.style.display = isH2h ? 'block' : 'none';
}

function setDefaultDates() {
  const dateTo = document.getElementById('dateTo');
  if (dateTo) dateTo.value = '';
}

function getFilterParams() {
  if (activeView === H2H_VIEW) {
    return {
      stats_page: 'maps',
      maps_view: H2H_VIEW,
      is_mw: isMW,
    };
  }
  const val = id => document.getElementById(id)?.value || '';
  return {
    stats_page: 'maps',
    maps_view: METRICS_VIEW,
    is_mw: isMW,
    player_elo_min: val('playerEloMin') === '' ? 0 : Number(val('playerEloMin')),
    player_elo_max: val('playerEloMax') ? Number(val('playerEloMax')) : null,
    opponent_elo_min: val('opponentEloMin') === '' ? 0 : Number(val('opponentEloMin')),
    opponent_elo_max: val('opponentEloMax') ? Number(val('opponentEloMax')) : null,
    date_from: val('dateFrom') || METRICS_DEFAULT_DATE_FROM,
    date_to: val('dateTo') || null,
  };
}

function isDefaultParams(params) {
  if (params.maps_view === H2H_VIEW) return true;
  return params.player_elo_min === 300 &&
    params.player_elo_max === null &&
    params.opponent_elo_min === 300 &&
    params.opponent_elo_max === null &&
    params.date_from === METRICS_DEFAULT_DATE_FROM &&
    params.date_to === null;
}

async function applyFilters(token = mountToken) {
  renderLoading();
  const params = getFilterParams();
  try {
    let payload;
    if (isDefaultParams(params)) {
      try {
        payload = await loadDefaultSnapshot(params.maps_view, isMW);
      } catch {
        payload = await fetchApi(params);
      }
    } else {
      payload = await fetchApi(params);
    }
    if (!isCurrentMount(token)) return;
    viewRows[activeView] = Array.isArray(payload.data) ? payload.data : [];
    mapMeta = Array.isArray(payload.maps) ? payload.maps : FALLBACK_MAPS;
    updateVisibleMaps();
    renderActiveView();
  } catch (error) {
    if (!isCurrentMount(token)) return;
    renderError(error);
  }
}

async function loadDefaultSnapshot(view, dataset) {
  if (defaultSnapshotCache[view]?.[dataset]) return defaultSnapshotCache[view][dataset];
  const url = DEFAULT_SNAPSHOT_URLS[view]?.[dataset];
  if (!url) throw new Error('Missing default snapshot');
  const payload = await loadSnapshot(url);
  defaultSnapshotCache[view][dataset] = payload;
  return payload;
}

async function fetchApi(params) {
  return fetchStats(params);
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

function resetFilters() {
  const setValue = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.value = value;
  };
  setValue('playerEloMin', '300');
  setValue('playerEloMax', '');
  setValue('opponentEloMin', '300');
  setValue('opponentEloMax', '');
  setValue('dateFrom', METRICS_DEFAULT_DATE_FROM);
  setValue('dateTo', '');
  applyFilters(++mountToken);
}

function renderActiveView() {
  if (activeView === H2H_VIEW) {
    renderH2h();
    return;
  }
  renderMetricsControls();
  renderTableHead();
  renderRows();
}

function setTableModeClass() {
  const table = document.getElementById('statsTable');
  if (!table) return;
  table.className = activeView === H2H_VIEW ? 'maps-table maps-h2h-table' : 'maps-table maps-metrics-table';
  const mobileWidth = activeView === H2H_VIEW
    ? 1025
    : 110 + Math.max(visibleMaps.length, 1) * 64;
  table.style.setProperty('--maps-mobile-table-width', `${mobileWidth}px`);
  if (activeView === METRICS_VIEW) {
    const layout = metricsColumnLayout();
    table.style.width = `${layout.totalWidthPct}%`;
    table.style.tableLayout = 'fixed';
  } else {
    table.style.width = '';
    table.style.tableLayout = '';
  }
}

function renderTableHead() {
  setTableModeClass();
  const thead = document.getElementById('tableHead');
  if (!thead) return;
  if (activeView === H2H_VIEW) {
    renderH2hHead();
    return;
  }
  const maps = currentRows().length ? sortedMapsForCurrentMetric() : visibleMaps;
  const layout = metricsColumnLayout();
  thead.innerHTML = `
    <tr>
      <th onclick="sortMapsByHeader()" style="width:${layout.metricWidthPct}%;text-align:center;">Maps${useNaturalMapOrder ? '<span class="maps-sort-indicator">&#8595;</span>' : ''}</th>
      ${maps.map(map => `<th class="maps-map-header maps-custom-tip" data-tip="${escapeAttr(mapTooltipLabel(map.full))}" style="width:${layout.mapWidthPct}%;text-align:center;">${escapeHtml(map.code)}</th>`).join('')}
    </tr>`;
}

function renderRows() {
  const tbody = document.getElementById('tableBody');
  if (!tbody) return;
  renderTableHead();
  renderMetricsControls();
  const rows = sortedVisibleRows();
  tbody.innerHTML = rows.map(rowHtml).join('');
  renderGamesFooter();
}

function updateVisibleMaps() {
  if (activeView === H2H_VIEW) {
    visibleMaps = mapMeta.filter(map => map.visible_default !== false);
    return;
  }
  const onlyCategory = Object.entries(mapVisibilityModes)
    .find(([, mode]) => mode === 'only')?.[0] || null;
  visibleMaps = mapMeta.filter(map => {
    const category = mapVisibilityCategory(map);
    if (onlyCategory) return category === onlyCategory;
    if (!category) return true;
    return mapVisibilityModes[category] === 'include';
  });
}

function mapVisibilityCategory(map) {
  if (/^Map [1-8]:/.test(map.full)) return 'legacy';
  if (map.full === 'Map A' || map.full === 'Map 0') return 'beginner';
  if (['9', '10'].includes(map.code)) return 'mapPack1';
  if (['11', '12', '13', '14', 'T1'].includes(map.code)) return 'mapPack2';
  return null;
}

function metricsColumnLayout() {
  const metricUnits = 13;
  const mapUnits = 87 / 15;
  const totalUnits = metricUnits + mapUnits * Math.max(visibleMaps.length, 1);
  return {
    totalWidthPct: Math.max(100, totalUnits),
    metricWidthPct: metricUnits / totalUnits * 100,
    mapWidthPct: mapUnits / totalUnits * 100,
  };
}

function mapsBarMetaEl() {
  return document.getElementById('tableMeta');
}

function renderMetricsControls() {
  const meta = mapsBarMetaEl();
  if (!meta || activeView !== METRICS_VIEW) return;
  meta.innerHTML = `
    <div class="maps-metrics-options">
      ${mapOptionToggle(
        'Map Pack 1',
        'Maps 9 & 10',
        'mapPack1',
      )}
      ${mapOptionToggle(
        'Map Pack 2',
        'Maps 11-14 & T1',
        'mapPack2',
      )}
      ${mapOptionToggle(
        'Legacy Maps',
        'Maps 1-8 (non-alternate map version)',
        'legacy',
      )}
      ${mapOptionToggle(
        'Beginner Maps',
        'Maps A & 0',
        'beginner',
      )}
      <button type="button" class="reset-btn maps-metrics-reset-btn" onclick="resetMetricsSwitches()">Reset</button>
    </div>`;
}

function mapOptionToggle(label, tooltip, category) {
  const mode = mapVisibilityModes[category];
  const options = [
    ['exclude', '&minus;', 'Exclude'],
    ['include', 'O', 'Include'],
    ['only', '+', 'Only'],
  ];
  return `
    <div class="maps-metrics-option">
      <span>${label}<span class="col-tip" data-tip="${escapeAttr(tooltip)}">?</span></span>
      <div class="maps-visibility-control" role="group" aria-label="${escapeAttr(`${label} visibility`)}">
        ${options.map(([value, symbol, description]) => `
          <button type="button" class="maps-custom-tip ${mode === value ? 'active' : ''}"
            aria-pressed="${mode === value}" data-tip="${description}"
            onclick="setMapVisibilityMode('${category}', '${value}')">${symbol}</button>`).join('')}
      </div>
    </div>`;
}

function renderViewMeta(totalGames = null) {
  if (activeView === H2H_VIEW) {
    renderH2hMeta(totalGames);
    return;
  }
  renderMetricsControls();
}

function renderH2hMeta(totalGames = null) {
  const meta = mapsBarMetaEl();
  if (!meta || activeView !== H2H_VIEW) return;
  const gamesText = totalGames === null
    ? ''
    : `<span>${compactNumber(totalGames)} games across ${visibleMaps.length} maps</span>`;
  meta.innerHTML = `
    <div class="maps-h2h-meta">
      <div class="maps-h2h-mode" role="group" aria-label="Tournament H2H metric">
        <button type="button" class="${h2hMode === 'win' ? 'active' : ''}" onclick="setMapsH2hMode('win')">Win%</button>
        <button type="button" class="${h2hMode === 'elo' ? 'active' : ''}" onclick="setMapsH2hMode('elo')">Elo Δ</button>
      </div>
      ${gamesText}
    </div>`;
}

function currentRows() {
  return viewRows[activeView] || [];
}

function visibleRows() {
  return currentRows().filter(row => row.metric !== 'Games');
}

function sortedVisibleRows() {
  return [...visibleRows()].sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
}

function sortedMapsForCurrentMetric() {
  if (useNaturalMapOrder) return [...visibleMaps];
  const rows = currentRows();
  const row = rows.find(item => item.metric === currentSortMetric) || rows.find(item => item.metric === 'Turns');
  const lowerIsBetter = isLowerBetter(row);
  return [...visibleMaps].sort((a, b) => {
    const av = Number(row?.[a.key]);
    const bv = Number(row?.[b.key]);
    if (!Number.isFinite(av) && !Number.isFinite(bv)) return 0;
    if (!Number.isFinite(av)) return 1;
    if (!Number.isFinite(bv)) return -1;
    return lowerIsBetter ? av - bv : bv - av;
  });
}

function rowHtml(row) {
  const sortedMaps = sortedMapsForCurrentMetric();
  const sortedKeys = sortedMaps.map(map => map.key);
  const values = sortedKeys.map(key => Number(row[key])).filter(Number.isFinite);
  const min = values.length ? Math.min(...values) : null;
  const max = values.length ? Math.max(...values) : null;
  const active = row.metric === currentSortMetric && !useNaturalMapOrder;
  return `
    <tr class="${active ? 'maps-active-sort-row' : ''}">
      <td class="maps-metric-cell" onclick="sortMapsByMetric('${escapeAttr(row.metric)}')">
        <span>${escapeHtml(displayMetricName(row.metric))}</span>
        ${metricTooltip(row) ? `<span class="col-tip" data-tip="${escapeAttr(metricTooltip(row))}">?</span>` : ''}
        ${active ? `<span class="maps-sort-indicator">${isLowerBetter(row) ? '&#8593;' : '&#8595;'}</span>` : ''}
      </td>
      ${sortedMaps.map(map => mapCellHtml(row, map, min, max)).join('')}
    </tr>`;
}

function mapCellHtml(row, map, min, max) {
  const raw = row[map.key];
  const value = Number(raw);
  const style = Number.isFinite(value) ? ` style="color:${rowColor(value, min, max, isLowerBetter(row))}"` : '';
  const tooltip = metricCellTooltip(row, map.key);
  return `<td class="maps-value-cell${tooltip ? ' maps-custom-tip' : ''}"${tooltip ? ` data-tip="${escapeAttr(tooltip)}"` : ''}${style}>${formatValue(raw, row.format)}</td>`;
}

function metricCellTooltip(row, mapKey) {
  if (!String(row.metric || '').startsWith('Money spent (')) return '';
  const value = Number(row[`tooltip_${mapKey}`]);
  if (!Number.isFinite(value)) return '';
  return value.toFixed(2);
}

function sortMapsByMetric(metric) {
  currentSortMetric = metric;
  useNaturalMapOrder = false;
  renderTableHead();
  renderRows();
}

function sortMapsByHeader() {
  useNaturalMapOrder = true;
  renderTableHead();
  renderRows();
}

function rowColor(value, min, max, lowerIsBetter) {
  return divergingRangeColor(value, min, max, lowerIsBetter);
}

function isLowerBetter(row) {
  return row?.lower_is_better === true || row?.metric === 'Turns' || row?.metric === 'Rounds';
}

function formatValue(raw, format) {
  const value = Number(raw);
  if (!Number.isFinite(value)) return '-';
  if (format === 'compact') return compactNumber(value);
  if (format === 'percent') return `${value.toFixed(1)}%`;
  return Math.abs(value) >= 100 ? value.toFixed(2) : value.toFixed(2);
}

function displayMetricName(metric) {
  return String(metric)
    .replaceAll('Points per money', 'Points per $')
    .replaceAll('Money per turn', '$ gained per turn')
    .replaceAll('Money gained', '$ gained')
    .replaceAll('Money spent', '$ spent')
    .replaceAll('Cards drawn from deck', 'Cards drawn (deck)')
    .replaceAll('Cards drawn from range', 'Cards drawn (Range)');
}

function metricTooltip(row) {
  if (row.tooltip) return row.tooltip;
  if (row.metric === 'Cards drawn from deck' || row.metric === 'Cards drawn (deck)') return 'Cards drawn from deck';
  if (row.metric === 'Cards drawn from range' || row.metric === 'Cards drawn (Range)') return 'Cards drawn from reputation range';
  return '';
}

function renderGamesFooter() {
  const tfoot = document.getElementById('tableFoot');
  if (!tfoot) return;
  const games = currentRows().find(row => row.metric === 'Games');
  if (!games || activeView !== METRICS_VIEW) {
    tfoot.innerHTML = '';
    return;
  }
  const sortedMaps = sortedMapsForCurrentMetric();
  tfoot.innerHTML = `
    <tr class="maps-games-row">
      <td class="maps-metric-cell" onclick="sortMapsByMetric('Games')">Games${currentSortMetric === 'Games' && !useNaturalMapOrder ? '<span class="maps-sort-indicator">&#8595;</span>' : ''}</td>
      ${sortedMaps.map(map => `<td class="maps-value-cell maps-games-cell maps-custom-tip" data-tip="${formatInteger(games[map.key])}">${formatValue(games[map.key], games.format)}</td>`).join('')}
    </tr>`;
}

function renderH2h() {
  setTableModeClass();
  const tbody = document.getElementById('tableBody');
  const tfoot = document.getElementById('tableFoot');
  if (!tbody) return;
  if (tfoot) tfoot.innerHTML = '';
  renderH2hHead();
  const matrix = buildH2hMatrix();
  const matchupRows = currentRows().filter(row => row.row_type !== 'overall' && Number(row.games) > 0);
  const overallRows = currentRows().filter(row => row.row_type === 'overall' && Number(row.games) > 0);
  const matchupRange = h2hMode === 'win'
    ? numericRange(matchupRows, row => row.win_pct)
    : cappedNumericRange(matchupRows, row => row.elo_delta);
  const overallRange = numericRange(
    overallRows,
    row => h2hMode === 'win' ? row.win_pct : row.elo_delta,
  );
  const totalGames = totalH2hGames(matrix);
  renderH2hMeta(totalGames);
  const rowMaps = sortedMapsForH2h(matrix);
  tbody.innerHTML = rowMaps.map(rowMap => `
    <tr>
      <td class="maps-h2h-row-head maps-custom-tip" data-tip="${escapeAttr(mapTooltipLabel(rowMap.full))}">${escapeHtml(rowMap.code)}</td>
      ${visibleMaps.map(colMap => h2hCellHtml(
        matrix.matchups.get(h2hKey(rowMap.full, colMap.full)),
        rowMap.full === colMap.full,
        false,
        matchupRange,
        overallRange,
      )).join('')}
      ${h2hCellHtml(matrix.overall.get(rowMap.full), false, true, matchupRange, overallRange)}
    </tr>`).join('');
  syncH2hRowHeight();
  ensureH2hResizeObserver();
}

// Row order. Natural order (default) always follows visibleMaps, which is
// already 1a, 2a, ..., T1. Sorting by Overall ranks rows by whichever metric
// is currently active (Win% or Elo delta), best record first; rows with no
// Overall data sort to the bottom rather than being dropped.
function sortedMapsForH2h(matrix) {
  if (!h2hSortByOverall) return [...visibleMaps];
  return visibleMaps
    .map((map, naturalIndex) => ({
      map,
      naturalIndex,
      value: h2hOverallSortValue(matrix, map),
    }))
    .sort((a, b) => {
      if (a.value === b.value) return a.naturalIndex - b.naturalIndex;
      if (a.value === -Infinity) return 1;
      if (b.value === -Infinity) return -1;
      return b.value - a.value;
    })
    .map(item => item.map);
}

function h2hOverallSortValue(matrix, map) {
  const row = matrix.overall.get(map.full);
  const raw = row ? (h2hMode === 'win' ? row.win_pct : row.elo_delta) : null;
  if (raw === null || raw === undefined || raw === '') return -Infinity;
  const value = Number(raw);
  return Number.isFinite(value) ? value : -Infinity;
}

function sortH2hByOverall() {
  h2hSortByOverall = true;
  renderH2h();
}

function sortH2hByMap() {
  h2hSortByOverall = false;
  renderH2h();
}

function renderH2hHead() {
  const thead = document.getElementById('tableHead');
  if (!thead) return;
  thead.innerHTML = `
    <tr>
      <th class="maps-h2h-corner" onclick="sortH2hByMap()">You \\ Opp${!h2hSortByOverall ? '<span class="maps-sort-indicator">&#8595;</span>' : ''}</th>
      ${visibleMaps.map(map => `<th class="maps-h2h-map-head maps-custom-tip" data-tip="${escapeAttr(mapTooltipLabel(map.full))}">${escapeHtml(map.code)}</th>`).join('')}
      <th class="maps-h2h-overall-head" onclick="sortH2hByOverall()">Overall${h2hSortByOverall ? '<span class="maps-sort-indicator">&#8595;</span>' : ''}</th>
    </tr>`;
}

let h2hResizeObserver = null;

// Row height = 80% of the actual rendered map-column width, read from the
// live DOM after each render since the column's px width depends on the
// current viewport/nav-rail state and isn't knowable from CSS alone.
function syncH2hRowHeight() {
  if (activeView !== H2H_VIEW) return;
  const table = document.getElementById('statsTable');
  const sampleCell = table?.querySelector('.maps-h2h-map-head');
  if (!table || !sampleCell) return;
  const width = sampleCell.getBoundingClientRect().width;
  if (!width) return;
  table.style.setProperty('--h2h-row-height', `${(width * 0.8).toFixed(1)}px`);
}

// Keeps the row height in sync as the table's rendered width changes, e.g.
// window resize or the nav rail expanding/collapsing.
function ensureH2hResizeObserver() {
  if (typeof ResizeObserver === 'undefined') return;
  const table = document.getElementById('statsTable');
  const sampleCell = table?.querySelector('.maps-h2h-map-head');
  if (!sampleCell) return;
  if (h2hResizeObserver) h2hResizeObserver.disconnect();
  h2hResizeObserver = new ResizeObserver(() => syncH2hRowHeight());
  // Observe the measured column itself. Watching the whole table also reacts
  // to row-height changes caused by this callback and adds a redundant cycle.
  h2hResizeObserver.observe(sampleCell);
}

function buildH2hMatrix() {
  const matchups = new Map();
  const overall = new Map();
  currentRows().forEach(row => {
    if (row.row_type === 'overall') {
      overall.set(row.row_map, row);
    } else {
      matchups.set(h2hKey(row.row_map, row.col_map), row);
    }
  });
  return { matchups, overall };
}

function h2hKey(rowMap, colMap) {
  return `${rowMap}|||${colMap}`;
}

function h2hCellHtml(cell, diagonal = false, overall = false, matchupRange = null, overallRange = null) {
  if (diagonal || !cell || !Number.isFinite(Number(cell.games)) || Number(cell.games) <= 0) {
    return `<td class="maps-h2h-cell maps-h2h-empty${overall ? ' maps-h2h-overall-cell' : ''}">-</td>`;
  }
  const activeValue = Number(h2hMode === 'win' ? cell.win_pct : cell.elo_delta);
  const style = overall
    ? `color:${orangeGreenRangeColor(activeValue, overallRange?.min, overallRange?.max)}`
    : h2hMode === 'win'
      ? h2hWinStyle(activeValue, matchupRange)
      : h2hEloStyle(activeValue, matchupRange);
  const main = h2hMode === 'win'
    ? formatWinPct(cell.win_pct)
    : signedOneDecimal(cell.elo_delta);
  const sub = h2hMode === 'win'
    ? `${Number(cell.wins || 0)}-${Number(cell.losses || 0)}`
    : `n = ${Number(cell.games || 0)}`;
  return `
    <td class="maps-h2h-cell${overall ? ' maps-h2h-overall-cell' : ''}" style="${style}">
      <div class="maps-h2h-main">${main}</div>
      <div class="maps-h2h-sub">${sub}</div>
    </td>`;
}

function h2hWinStyle(value, range) {
  if (!Number.isFinite(value)) return '';
  const t = normalizeToRange(value, range?.min, range?.max);
  const normalized = t === null ? 0 : t * 2 - 1;
  return h2hColorStyle(normalized);
}

function h2hEloStyle(value, range) {
  if (!Number.isFinite(value)) return '';
  const color = deltaRangeColor(value, range?.min, range?.max);
  const t = normalizeToRange(clamp(value, -2, 2), range?.min, range?.max);
  const magnitude = t === null ? 0 : Math.abs(t * 2 - 1);
  return `color:${color};background:rgba(${cssColorRgb(color)},${(0.08 + magnitude * 0.22).toFixed(3)})`;
}

function h2hColorStyle(normalized) {
  // Text and heatmap backgrounds share the same continuous diverging scale.
  const color = divergingRangeColor(normalized, -1, 1);
  const alpha = 0.08 + Math.abs(normalized) * 0.22;
  return `color:${color};background:rgba(${cssColorRgb(color)},${alpha.toFixed(3)})`;
}

function totalH2hGames(matrix) {
  let total = 0;
  matrix.overall.forEach(row => { total += Number(row.games || 0); });
  return total / 2;
}

function formatWinPct(raw) {
  const value = Number(raw);
  if (!Number.isFinite(value)) return '-';
  if (value === 0 || value === 100) return `${value.toFixed(0)}%`;
  return `${value.toFixed(1)}%`;
}

function signedOneDecimal(raw) {
  return formatSignedDeltaAdaptive(raw);
}

function compactNumber(value) {
  if (value >= 1000000) return `${(value / 1000000).toFixed(2).replace(/\.?0+$/, '')}m`;
  if (value >= 100000) return `${Math.round(value / 1000)}k`;
  if (value >= 10000) return `${(value / 1000).toFixed(1).replace(/\.0$/, '')}k`;
  if (value >= 1000) return `${(value / 1000).toFixed(2).replace(/\.?0+$/, '')}k`;
  return String(Math.round(value));
}

function formatInteger(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? Math.round(numeric).toLocaleString('en-US') : '-';
}

function renderLoading() {
  setTableModeClass();
  updateVisibleMaps();
  renderTableHead();
  renderViewMeta();
  const foot = document.getElementById('tableFoot');
  if (foot) foot.innerHTML = '';
  const label = activeView === H2H_VIEW ? 'tournament H2H' : 'map metrics';
  document.getElementById('tableBody').innerHTML = `<tr><td colspan="17">
    <div class="state-overlay">
      <div class="spinner"></div>
      <div class="state-title">Fetching data...</div>
      <div class="state-sub">Querying ${label}.</div>
    </div>
  </td></tr>`;
}

function renderError(error) {
  renderViewMeta();
  const foot = document.getElementById('tableFoot');
  if (foot) foot.innerHTML = '';
  document.getElementById('tableBody').innerHTML = `<tr><td colspan="17">
    <div class="state-overlay">
      <div class="state-title">Could not load maps data</div>
      <div class="state-sub">${escapeHtml(error.message || String(error))}</div>
    </div>
  </td></tr>`;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

const _colTip = document.getElementById('col-tooltip');
document.addEventListener('mousemove', event => {
  if (!isPageMounted || !_colTip) return;
  const tipEl = event.target.closest?.('.col-tip, .maps-custom-tip');
  if (!tipEl) {
    _colTip.style.display = 'none';
    return;
  }
  _colTip.textContent = tipEl.dataset.tip || '';
  _colTip.style.display = 'block';
  _colTip.style.left = `${event.clientX + 12}px`;
  _colTip.style.top = `${event.clientY + 12}px`;
});

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
