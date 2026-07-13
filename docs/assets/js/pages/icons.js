import {
  cappedNumericRange,
  deltaRangeColor,
  frequencyColor,
  numericRange,
  orangeGreenRangeColor,
} from '../color-scales.js?v=20260710-2';
import {
  INSUFFICIENT_DATA_TOOLTIP,
  formatSignedDeltaAdaptive,
  isInsufficientObservationCount,
} from '../table-cells.js?v=20260712-4';
import { loadSnapshot, fetchStats } from '../snapshot-cache.js?v=20260713-1';

export const id = 'icons';
export const title = 'Icons';
export const navLabel = 'Icons';

const ICON_GROUPS = [
  {
    id: 'species',
    label: 'Species',
    icons: [
      ['Birds', 'bird.png'], ['Herbivores', 'herbivore.png'],
      ['Predators', 'predator.png'], ['Primates', 'primate.png'],
      ['Reptiles', 'reptile.png'], ['Sea Animals', 'sea-animal.png'],
      ['Bears', 'bear.png'], ['Petting Zoo Animals', 'petting-zoo.png'],
    ],
  },
  {
    id: 'habitat',
    label: 'Habitat',
    icons: [
      ['Africa', 'africa.png'], ['Americas', 'americas.png'], ['Asia', 'asia.png'],
      ['Australia', 'australia.png'], ['Europe', 'europe.png'],
    ],
  },
  {
    id: 'other',
    label: 'Other',
    icons: [['Rock', 'rock.png'], ['Water', 'water.png'], ['Science', 'science.png']],
  },
];
const ICONS = ICON_GROUPS.flatMap(group => group.icons.map(([name]) => name));
const ICON_ASSETS = Object.fromEntries(
  ICON_GROUPS.flatMap(group => group.icons.map(([name, asset]) => [name, asset])),
);
const BUCKETS = [
  ['delta_0', '0'], ['delta_1', '1'], ['delta_2', '2'], ['delta_3', '3'],
  ['delta_4', '4'], ['delta_5', '5'], ['delta_6', '6'], ['delta_7_plus', '7+'],
];
const VALID_MAPS = [
  ['1a', 'Map 1a: Observation Tower'], ['2a', 'Map 2a: Outdoor Areas'],
  ['3a', 'Map 3a: Silver Lake'], ['4a', 'Map 4a: Commercial Harbor'],
  ['5a', 'Map 5a: Park Restaurant'], ['6a', 'Map 6a: Research Institute'],
  ['7a', 'Map 7a: Ice Cream Parlors'], ['8a', 'Map 8a: Hollywood Hills'],
  ['9', 'Map 9: Geographical Zoo'], ['10', 'Map 10: Rescue Station'],
  ['11', 'Map 11: Caves'], ['12', 'Map 12: Artificial Intelligence'],
  ['13', 'Map 13: Drawing Board'], ['14', 'Map 14: Lagoon'],
  ['T1', 'Map T1: Tournament 1'],
];
const API_URL = 'https://europe-west1-ark-nova-stats-dashboard.cloudfunctions.net/get-card-stats';
const SNAPSHOTS = {
  1: 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/icons/default-mw.json?v=20260704-1',
  0: 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/icons/default-base.json?v=20260704-1',
};
const CHART_LINE_COLORS = [
  '#34d399', '#60a5fa', '#f59e0b', '#f472b6', '#a78bfa', '#22d3ee',
  '#fb7185', '#84cc16', '#f97316', '#2dd4bf', '#818cf8', '#eab308',
  '#4ade80', '#38bdf8', '#c084fc', '#f43f5e',
];

export const mainHtml = `
  <div class="main-header sponsor-endgames-main-header">
    <div class="table-meta" id="tableMeta"></div>
    <div class="maps-h2h-mode sponsor-endgames-mode icons-mode" role="group" aria-label="Icons metric">
      <button type="button" class="active" data-mode="delta" onclick="setIconsMode('delta')">Elo &Delta;</button>
      <button type="button" data-mode="frequency" onclick="setIconsMode('frequency')">Frequency</button>
    </div>
  </div>
  <div class="attributes-bar endgames-tabs-bar icons-filter-bar">
    <div class="icons-filter-scroll">
      <div class="icons-filter-controls">
        <div class="icons-filter-groups" id="iconFilterChips"></div>
        <div class="attr-separator icons-group-separator icons-graph-separator" aria-hidden="true"></div>
        <div class="icons-graph-zone">
          <button type="button" class="endgames-graph-toggle icons-graph-toggle" aria-label="Toggle icon graph"
            title="Show graph" onclick="toggleIconsGraphView()">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 19h16" /><path d="M4 5v14" /><path d="M6.5 15.5 10 11l3.5 2.5L18 7" /></svg>
          </button>
        </div>
      </div>
    </div>
  </div>
  <div class="table-wrap">
    <div class="table-scroll">
      <table id="statsTable" class="sponsor-endgames-table icons-table">
        <thead id="tableHead"></thead>
        <tbody id="tableBody"><tr><td colspan="11"><div class="state-overlay">
          <div class="spinner"></div><div class="state-title">Fetching data...</div>
          <div class="state-sub">Querying icon statistics.</div>
        </div></td></tr></tbody>
      </table>
    </div>
  </div>`;

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
    <input class="date-input" type="text" inputmode="numeric" pattern="\\d{4}-\\d{2}-\\d{2}" placeholder="yyyy-mm-dd" id="dateFrom" value="2025-01-01" />
    <input class="date-input" type="text" inputmode="numeric" pattern="\\d{4}-\\d{2}-\\d{2}" placeholder="yyyy-mm-dd" id="dateTo" />
  </div>
  <hr class="divider" />
  <div class="filter-action-stack"><button class="apply-btn" id="applyBtn" onclick="applyFiltersFromSidebar()">Apply filters</button></div>`;

let mounted = false;
let token = 0;
let isMW = 1;
let mode = 'delta';
let graphView = false;
let rows = [];
let selectedIcons = new Set(ICONS);
let selectedMaps = VALID_MAPS.map(([, full]) => full);
let sort = { col: 'amount', dir: 'desc' };
const snapshotCache = { 0: null, 1: null };

export function mount({ dataset = 1 } = {}) {
  mounted = true;
  token += 1;
  isMW = Number(dataset) === 0 ? 0 : 1;
  mode = 'delta';
  graphView = false;
  selectedIcons = new Set(availableIconNames());
  selectedMaps = VALID_MAPS.map(([, full]) => full);
  sort = { col: 'amount', dir: 'desc' };
  bindHandlers();
  renderIconChips();
  renderMapChips();
  applyFilters(token);
}

export function unmount() {
  mounted = false;
  token += 1;
}

export function setDataset(dataset) {
  isMW = Number(dataset) === 0 ? 0 : 1;
  if (isMW) selectedIcons.add('Sea Animals');
  else selectedIcons.delete('Sea Animals');
  renderIconChips();
  applyFilters(++token);
}

function bindHandlers() {
  Object.assign(window, {
    applyFiltersFromSidebar,
    resetFilters,
    selectAllIcons,
    selectNoneIcons,
    selectAllMaps,
    selectNoneMaps,
    setIconsMode,
    sortIcons,
    toggleIconGroup,
    toggleIconChip,
    toggleIconsGraphView,
    toggleMapChip,
  });
}

function setIconsMode(next) {
  mode = next === 'frequency' ? 'frequency' : 'delta';
  document.querySelectorAll('.icons-mode button').forEach(button => {
    button.classList.toggle('active', button.dataset.mode === mode);
  });
  renderCurrentView();
}

function toggleIconsGraphView() {
  graphView = !graphView;
  document.querySelector('.icons-graph-toggle')?.classList.toggle('active', graphView);
  document.querySelector('.icons-table')?.classList.toggle('icons-graph-view', graphView);
  renderCurrentView();
}

function sortIcons(col) {
  sort = sort.col === col
    ? { col, dir: sort.dir === 'desc' ? 'asc' : 'desc' }
    : { col, dir: col === 'icon' ? 'asc' : 'desc' };
  renderTable();
}

function params() {
  const value = id => document.getElementById(id)?.value || '';
  return {
    stats_page: 'icons',
    is_mw: isMW,
    maps: selectedMaps,
    player_elo_min: value('playerEloMin') === '' ? 0 : Number(value('playerEloMin')),
    player_elo_max: value('playerEloMax') ? Number(value('playerEloMax')) : null,
    opponent_elo_min: value('opponentEloMin') === '' ? 0 : Number(value('opponentEloMin')),
    opponent_elo_max: value('opponentEloMax') ? Number(value('opponentEloMax')) : null,
    date_from: value('dateFrom') || '2025-01-01',
    date_to: value('dateTo') || null,
  };
}

function isDefault(p) {
  return p.player_elo_min === 300 && p.player_elo_max === null &&
    p.opponent_elo_min === 300 && p.opponent_elo_max === null &&
    p.date_from === '2025-01-01' && p.date_to === null &&
    selectedMaps.length === VALID_MAPS.length;
}

async function applyFilters(activeToken = token) {
  renderLoading();
  if (!selectedMaps.length) {
    rows = [];
    renderTable();
    return;
  }
  try {
    const p = params();
    let payload;
    if (isDefault(p)) {
      try {
        payload = snapshotCache[isMW] || await fetchJson(SNAPSHOTS[isMW]);
        snapshotCache[isMW] = payload;
      } catch {
        payload = await fetchApi(p);
      }
    } else {
      payload = await fetchApi(p);
    }
    if (!mounted || activeToken !== token) return;
    rows = Array.isArray(payload.data) ? payload.data : [];
    renderCurrentView();
  } catch (error) {
    if (mounted && activeToken === token) renderError(error);
  }
}

async function fetchJson(url) {
  return loadSnapshot(url);
}

async function fetchApi(p) {
  return fetchStats(p);
}

function availableIconNames() {
  return ICONS.filter(icon => isMW || icon !== 'Sea Animals');
}

function datasetRows() {
  return rows.filter(row => isMW || row.icon !== 'Sea Animals');
}

function visibleRows() {
  return datasetRows().filter(row => selectedIcons.has(row.icon));
}

function sortedRows(data) {
  const direction = sort.dir === 'desc' ? -1 : 1;
  return [...data].sort((a, b) => {
    if (sort.col.startsWith('delta_')) {
      const aTier = bucketSortTier(a, sort.col);
      const bTier = bucketSortTier(b, sort.col);
      if (aTier !== bTier) return aTier - bTier;
      if (aTier === 2) return String(a.icon).localeCompare(String(b.icon));
    }
    const av = sort.col === 'icon' ? a.icon : sortValue(a, sort.col);
    const bv = sort.col === 'icon' ? b.icon : sortValue(b, sort.col);
    if (typeof av === 'string' || typeof bv === 'string') return String(av).localeCompare(String(bv)) * direction;
    return compareValues(av, bv) * direction || String(a.icon).localeCompare(String(b.icon));
  });
}

function isRankEligible(row) {
  if (!sort.col.startsWith('delta_')) return true;
  return bucketSortTier(row, sort.col) === 0;
}

function bucketSortTier(row, field) {
  if (isImpossibleBucket(row, field)) return 2;
  const value = mode === 'frequency' ? frequency(row, field) : Number(row[field]);
  if (!Number.isFinite(value)) return 2;
  return mode === 'delta' && isInsufficientObservationCount(count(row, field)) ? 1 : 0;
}

function sortValue(row, field) {
  if (mode === 'frequency' && field.startsWith('delta_')) return frequency(row, field);
  return row[field];
}

function compareValues(a, b) {
  const an = Number(a);
  const bn = Number(b);
  if (!Number.isFinite(an) && !Number.isFinite(bn)) return 0;
  if (!Number.isFinite(an)) return -1;
  if (!Number.isFinite(bn)) return 1;
  return an - bn;
}

function renderCurrentView() {
  if (graphView) renderGraph();
  else renderTable();
}

function renderTable() {
  renderHead();
  const universe = datasetRows();
  const sortedUniverse = sortedRows(universe);
  let nextRank = 1;
  sortedUniverse.forEach(row => {
    row.current_rank = isRankEligible(row) ? nextRank++ : null;
  });
  const data = sortedUniverse.filter(row => selectedIcons.has(row.icon));
  const meta = document.getElementById('tableMeta');
  if (meta) meta.innerHTML = `Showing <strong>${data.length}</strong> of <strong>${universe.length}</strong> icons`;
  const body = document.getElementById('tableBody');
  if (!body) return;
  if (!data.length) {
    body.innerHTML = '<tr><td colspan="11"><div class="state-overlay"><div class="state-title">No icons selected</div><div class="state-sub">Enable at least one icon above the table.</div></div></td></tr>';
    return;
  }
  const amountRange = numericRange(universe, row => row.amount);
  const sharedDeltaRange = cappedNumericRange(
    universe.flatMap(row => BUCKETS.map(([field]) => ({
      value: !isImpossibleBucket(row, field) && !isInsufficientObservationCount(count(row, field)) ? row[field] : null,
    }))),
    row => row.value,
  );
  const sharedFrequencyRange = numericRange(
    universe.flatMap(row => BUCKETS.map(([field]) => ({
      value: !isImpossibleBucket(row, field) ? frequency(row, field) : null,
    }))),
    row => row.value,
  );
  const deltaRanges = Object.fromEntries(BUCKETS.map(([field]) => [field, sharedDeltaRange]));
  const frequencyRanges = Object.fromEntries(BUCKETS.map(([field]) => [field, sharedFrequencyRange]));
  body.innerHTML = data.map(row => `
    <tr>
      <td class="rank-cell">${row.current_rank ?? '\u2014'}</td>
      <td class="sponsor-name-cell">${escapeHtml(row.icon)}</td>
      <td class="sponsor-avg-cell" style="color:${orangeGreenRangeColor(row.amount, amountRange.min, amountRange.max)}">${format(row.amount, 2)}</td>
      ${BUCKETS.map(([field]) => bucketCell(row, field, deltaRanges[field], frequencyRanges[field])).join('')}
    </tr>`).join('');
}

function renderHead() {
  const head = document.getElementById('tableHead');
  if (!head) return;
  const prefix = mode === 'frequency' ? 'f' : '\u0394';
  head.innerHTML = `<tr>
    <th style="width:5%;text-align:center;">#</th>
    ${header('icon', 'Icon', '18%')}
    ${header('amount', 'Amount', '10%')}
    ${BUCKETS.map(([field, label]) => {
      const description = mode === 'frequency'
        ? `relative frequency of games ending with ${label === '7+' ? '7 or more' : label} of this icon`
        : `average elo gain in games ending with ${label === '7+' ? '7 or more' : label} of this icon`;
      return header(field, `${prefix} (${label})`, '8.375%', description);
    }).join('')}
  </tr>`;
}

function header(field, label, width, tooltip = '') {
  const active = sort.col === field;
  const arrow = active ? (sort.dir === 'desc' ? '\u2193' : '\u2191') : '\u2195';
  return `<th class="${active ? 'sorted' : ''}" onclick="sortIcons('${field}')" style="width:${width};text-align:center;">
    ${label}${tooltip ? `<span class="col-tip" data-tip="${escapeAttr(tooltip)}">?</span>` : ''}
    <span class="sort-arrow${active ? ' active' : ''}">${arrow}</span></th>`;
}

function bucketCell(row, field, deltaRange, frequencyRange) {
  if (isImpossibleBucket(row, field)) return '<td class="unavailable-cell">-</td>';
  const occurrences = count(row, field);
  if (mode === 'frequency') {
    const pct = frequency(row, field);
    if (!Number.isFinite(pct)) return '<td class="unavailable-cell">-</td>';
    const tip = `${occurrences.toLocaleString('en-US')} / ${Number(row.n_total || 0).toLocaleString('en-US')}`;
    return `<td class="sponsor-frequency-cell icons-value-tooltip" data-value-tooltip="${escapeAttr(tip)}"
      style="color:${frequencyColor(pct)}">${pct.toFixed(2)}%</td>`;
  }
  const value = Number(row[field]);
  if (!Number.isFinite(value)) return '<td class="unavailable-cell">-</td>';
  if (isInsufficientObservationCount(occurrences)) {
    return `<td class="delta sponsor-delta-insufficient icons-value-tooltip"
      data-value-tooltip="${INSUFFICIENT_DATA_TOOLTIP}">${signed(value)}</td>`;
  }
  return `<td class="delta delta-ci-cell"
    data-ci-low="${escapeAttr(row[`${field}_ci95_low`] ?? '')}"
    data-ci-high="${escapeAttr(row[`${field}_ci95_high`] ?? '')}"
    data-ci-n="${escapeAttr(row[`${field}_ci95_n`] ?? '')}"
    data-ci-color-min="${escapeAttr(deltaRange.min ?? '')}"
    data-ci-color-max="${escapeAttr(deltaRange.max ?? '')}"
    style="color:${deltaRangeColor(value, deltaRange.min, deltaRange.max)}">${signed(value)}</td>`;
}

function isImpossibleBucket(row, field) {
  if (row.icon !== 'Petting Zoo Animals') return false;
  const index = BUCKETS.findIndex(([bucket]) => bucket === field);
  const maximum = isMW ? 4 : 3;
  return index > maximum;
}

function count(row, field) {
  const value = Number(row[field.replace('delta_', 'count_')]);
  return Number.isFinite(value) ? value : 0;
}

function frequency(row, field) {
  const total = Number(row.n_total);
  return total > 0 ? 100 * count(row, field) / total : Number.NaN;
}

function renderGraph() {
  const data = visibleRows();
  const body = document.getElementById('tableBody');
  const head = document.getElementById('tableHead');
  const meta = document.getElementById('tableMeta');
  if (head) head.innerHTML = '';
  if (meta) meta.innerHTML = '';
  if (!body) return;
  body.innerHTML = '<tr><td colspan="11" class="chart-host-cell"></td></tr>';
  const host = body.querySelector('.chart-host-cell');
  if (!data.length) {
    host.innerHTML = '<div class="state-overlay"><div class="state-title">No icons selected</div><div class="state-sub">Enable at least one icon above the graph.</div></div>';
    return;
  }
  host.appendChild(buildIconsChart(data));
}

function buildIconsChart(data) {
  const wrap = document.createElement('div');
  wrap.className = 'cp-dist-chart-wrap icons-chart-wrap';
  const chart = document.createElement('div');
  chart.className = 'cp-dist-chart';
  const legend = document.createElement('div');
  legend.className = 'cp-dist-legend';
  const controls = document.createElement('div');
  controls.className = 'cp-dist-legend-controls';
  controls.innerHTML = '<span>Lines</span><span>(<button type="button" data-action="all">all</button> / <button type="button" data-action="none">none</button>)</span>';
  const legendList = document.createElement('div');
  legendList.className = 'cp-dist-legend-list';
  const chartTooltip = document.createElement('div');
  chartTooltip.className = 'cp-dist-tooltip';
  const selected = new Set(data.map((_, index) => index));

  const width = 820;
  const height = 440;
  const margin = { top: 24, right: 28, bottom: 56, left: 64 };
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  const allValues = data.flatMap(row => BUCKETS.flatMap(([field]) => {
    if (isImpossibleBucket(row, field)) return [];
    if (mode === 'delta') {
      const value = Number(row[field]);
      return !isInsufficientObservationCount(count(row, field)) && Number.isFinite(value) ? [value] : [];
    }
    const value = frequency(row, field);
    return Number.isFinite(value) ? [value] : [];
  }));
  let yMin;
  let yMax;
  if (mode === 'frequency') {
    yMin = 0;
    yMax = Math.max(10, Math.ceil((Math.max(...allValues, 0) * 1.08) / 10) * 10);
  } else {
    const rawMin = Math.min(0, ...allValues);
    const rawMax = Math.max(0, ...allValues);
    const padding = Math.max(0.1, (rawMax - rawMin) * 0.1);
    yMin = Math.floor((rawMin - padding) * 2) / 2;
    yMax = Math.ceil((rawMax + padding) * 2) / 2;
    if (yMin === yMax) { yMin -= 0.5; yMax += 0.5; }
  }
  const x = index => margin.left + index / (BUCKETS.length - 1) * innerWidth;
  const y = value => margin.top + innerHeight -
    (Number(value) - yMin) / (yMax - yMin) * innerHeight;
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', `Icon ${mode === 'delta' ? 'Elo delta' : 'frequency'} line chart`);

  for (let index = 0; index <= 4; index += 1) {
    const tick = yMin + (yMax - yMin) * index / 4;
    const gy = y(tick);
    appendSvg(svg, 'line', { x1: margin.left, x2: width - margin.right, y1: gy, y2: gy, class: 'cp-dist-grid' });
    const label = appendSvg(svg, 'text', {
      x: margin.left - 10, y: gy + 4, 'text-anchor': 'end', class: 'cp-dist-axis-label',
    });
    label.textContent = mode === 'frequency' ? `${tick.toFixed(0)}%` : signedAxis(tick);
  }
  BUCKETS.forEach(([, bucket], index) => {
    const label = appendSvg(svg, 'text', {
      x: x(index), y: height - 17, 'text-anchor': 'middle', class: 'cp-dist-axis-label',
    });
    label.textContent = `${mode === 'frequency' ? 'f' : '\u0394'} (${bucket})`;
  });
  appendSvg(svg, 'line', {
    x1: margin.left, x2: width - margin.right,
    y1: margin.top + innerHeight, y2: margin.top + innerHeight, class: 'cp-dist-axis',
  });
  appendSvg(svg, 'line', {
    x1: margin.left, x2: margin.left, y1: margin.top,
    y2: margin.top + innerHeight, class: 'cp-dist-axis',
  });
  if (mode === 'delta' && yMin < 0 && yMax > 0) {
    appendSvg(svg, 'line', {
      x1: margin.left, x2: width - margin.right, y1: y(0), y2: y(0),
      class: 'icons-chart-zero',
    });
  }

  const syncSelection = () => {
    svg.querySelectorAll('.cp-dist-line, .cp-dist-dot').forEach(element => {
      element.classList.toggle('deselected', !selected.has(Number(element.dataset.index)));
    });
    legendList.querySelectorAll('.cp-dist-legend-item').forEach(element => {
      const active = selected.has(Number(element.dataset.index));
      element.classList.toggle('deselected', !active);
      element.setAttribute('aria-pressed', String(active));
    });
  };
  const toggleLine = index => {
    if (selected.size === data.length) {
      selected.clear();
      selected.add(index);
    } else if (selected.has(index)) selected.delete(index);
    else selected.add(index);
    syncSelection();
  };
  const highlight = index => {
    svg.querySelectorAll('.cp-dist-line').forEach(element => {
      element.classList.toggle('highlighted', Number(element.dataset.index) === index);
      element.classList.toggle('dimmed', Number(element.dataset.index) !== index);
    });
    legendList.querySelectorAll('.cp-dist-legend-item').forEach(element => {
      element.classList.toggle('highlighted', Number(element.dataset.index) === index);
      element.classList.toggle('dimmed', Number(element.dataset.index) !== index);
    });
  };
  const clearHighlight = () => {
    svg.querySelectorAll('.cp-dist-line').forEach(element => element.classList.remove('highlighted', 'dimmed'));
    legendList.querySelectorAll('.cp-dist-legend-item').forEach(element => element.classList.remove('highlighted', 'dimmed'));
    chartTooltip.style.display = 'none';
  };

  controls.addEventListener('click', event => {
    const action = event.target?.dataset?.action;
    if (action === 'all') data.forEach((_, index) => selected.add(index));
    if (action === 'none') selected.clear();
    syncSelection();
  });

  data.forEach((row, rowIndex) => {
    const colorIndex = availableIconNames().indexOf(row.icon);
    const color = CHART_LINE_COLORS[Math.max(0, colorIndex) % CHART_LINE_COLORS.length];
    const points = BUCKETS.map(([field], bucketIndex) => {
      if (isImpossibleBucket(row, field)) return null;
      const value = mode === 'delta' ? Number(row[field]) : frequency(row, field);
      if (!Number.isFinite(value)) return null;
      if (mode === 'delta' && isInsufficientObservationCount(count(row, field))) return null;
      return { field, bucketIndex, value, x: x(bucketIndex), y: y(value) };
    });
    let pathData = '';
    let segmentOpen = false;
    points.forEach(point => {
      if (!point) { segmentOpen = false; return; }
      pathData += `${segmentOpen ? 'L' : 'M'} ${point.x.toFixed(2)} ${point.y.toFixed(2)} `;
      segmentOpen = true;
    });
    if (pathData) {
      const path = appendSvg(svg, 'path', { d: pathData.trim(), class: 'cp-dist-line', stroke: color });
      path.dataset.index = String(rowIndex);
      path.addEventListener('click', event => { event.stopPropagation(); toggleLine(rowIndex); });
      path.addEventListener('mouseenter', () => highlight(rowIndex));
      path.addEventListener('mousemove', event => {
        const rect = svg.getBoundingClientRect();
        const relativeX = (event.clientX - rect.left) / rect.width * width;
        const nearest = points.filter(Boolean).reduce((best, point) =>
          !best || Math.abs(point.x - relativeX) < Math.abs(best.x - relativeX) ? point : best, null);
        if (nearest) showIconsChartTooltip(row, nearest, event, chartTooltip);
      });
      path.addEventListener('mouseleave', clearHighlight);
    }
    points.filter(Boolean).forEach(point => {
      const dot = appendSvg(svg, 'circle', {
        cx: point.x, cy: point.y, r: 3, class: 'cp-dist-dot', fill: color,
      });
      dot.dataset.index = String(rowIndex);
      dot.addEventListener('click', event => { event.stopPropagation(); toggleLine(rowIndex); });
      dot.addEventListener('mouseenter', event => {
        highlight(rowIndex);
        showIconsChartTooltip(row, point, event, chartTooltip);
      });
      dot.addEventListener('mousemove', event => showIconsChartTooltip(row, point, event, chartTooltip));
      dot.addEventListener('mouseleave', clearHighlight);
    });

    const legendItem = document.createElement('button');
    legendItem.type = 'button';
    legendItem.className = 'cp-dist-legend-item icons-chart-legend-item';
    legendItem.dataset.index = String(rowIndex);
    legendItem.setAttribute('aria-pressed', 'true');
    legendItem.innerHTML = `<span class="cp-dist-legend-swatch" style="background:${color}"></span>
      <img src="assets/img/icons/${ICON_ASSETS[row.icon]}" alt="" /><span>${escapeHtml(row.icon)}</span>`;
    legendItem.addEventListener('click', () => toggleLine(rowIndex));
    legendItem.addEventListener('mouseenter', () => highlight(rowIndex));
    legendItem.addEventListener('mouseleave', clearHighlight);
    legendList.appendChild(legendItem);
  });

  legend.append(controls, legendList);
  syncSelection();
  chart.append(svg, chartTooltip);
  wrap.append(chart, legend);
  return wrap;
}

function appendSvg(parent, tag, attributes) {
  const element = document.createElementNS('http://www.w3.org/2000/svg', tag);
  Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
  parent.appendChild(element);
  return element;
}

function signedAxis(value) {
  const rounded = Math.abs(value) < 0.0001 ? 0 : value;
  return `${rounded > 0 ? '+' : ''}${rounded.toFixed(1)}`;
}

function showIconsChartTooltip(row, point, event, chartTooltip) {
  const bucket = BUCKETS[point.bucketIndex][1];
  const value = mode === 'frequency' ? `${point.value.toFixed(2)}%` : signed(point.value);
  chartTooltip.innerHTML = `<strong>${escapeHtml(row.icon)}</strong>
    <div>${mode === 'frequency' ? 'f' : '\u0394'} (${bucket}): ${value}</div>`;
  chartTooltip.style.display = 'block';
  const rect = chartTooltip.parentElement.getBoundingClientRect();
  chartTooltip.style.left = `${event.clientX - rect.left + 12}px`;
  chartTooltip.style.top = `${event.clientY - rect.top + 12}px`;
}

function renderIconChips() {
  const container = document.getElementById('iconFilterChips');
  if (!container) return;
  container.innerHTML = ICON_GROUPS.map(group => {
    const groupIcons = group.icons
      .map(([name]) => name)
      .filter(icon => isMW || icon !== 'Sea Animals');
    const selectedCount = groupIcons.filter(icon => selectedIcons.has(icon)).length;
    return `<div class="icons-filter-group" data-group="${group.id}">
      <button type="button" class="icons-group-button ${selectedCount ? 'active' : ''}"
        onclick="toggleIconGroup('${group.id}')">${group.label}</button>
      <div class="icons-group-items">${groupIcons.map(icon => `
        <button type="button" class="icons-image-chip icons-value-tooltip ${selectedIcons.has(icon) ? 'active' : ''}"
          onclick="toggleIconChip('${escapeAttr(icon)}')" aria-pressed="${selectedIcons.has(icon)}"
          data-value-tooltip="${escapeAttr(icon)}" aria-label="${escapeAttr(icon)}">
          <img src="assets/img/icons/${ICON_ASSETS[icon]}" alt="" />
        </button>`).join('')}</div>
    </div>`;
  }).join('<div class="attr-separator icons-group-separator" aria-hidden="true"></div>');
}

function toggleIconGroup(groupId) {
  const group = ICON_GROUPS.find(item => item.id === groupId);
  if (!group) return;
  const icons = group.icons.map(([name]) => name).filter(icon => isMW || icon !== 'Sea Animals');
  const allSelected = icons.every(icon => selectedIcons.has(icon));
  icons.forEach(icon => {
    if (allSelected) selectedIcons.delete(icon);
    else selectedIcons.add(icon);
  });
  renderIconChips();
  renderCurrentView();
}

function toggleIconChip(icon) {
  if (selectedIcons.has(icon)) selectedIcons.delete(icon);
  else selectedIcons.add(icon);
  renderIconChips();
  renderCurrentView();
}

function selectAllIcons() {
  selectedIcons = new Set(availableIconNames());
  renderIconChips();
  renderCurrentView();
}

function selectNoneIcons() {
  selectedIcons.clear();
  renderIconChips();
  renderCurrentView();
}

function renderMapChips() {
  const container = document.getElementById('mapChips');
  if (!container) return;
  container.innerHTML = VALID_MAPS.map(([short, full]) => `<button class="chip ${selectedMaps.includes(full) ? 'active' : ''}"
    data-map="${escapeAttr(full)}" title="${escapeAttr(full)}" onclick="toggleMapChip(this.dataset.map)">${short}</button>`).join('');
}

function toggleMapChip(map) {
  if (selectedMaps.includes(map)) selectedMaps = selectedMaps.filter(value => value !== map);
  else selectedMaps.push(map);
  renderMapChips();
}

function selectAllMaps() {
  selectedMaps = VALID_MAPS.map(([, full]) => full);
  renderMapChips();
}

function selectNoneMaps() {
  selectedMaps = [];
  renderMapChips();
}

function resetFilters() {
  const set = (id, value) => { const element = document.getElementById(id); if (element) element.value = value; };
  set('playerEloMin', '300'); set('playerEloMax', '');
  set('opponentEloMin', '300'); set('opponentEloMax', '');
  set('dateFrom', '2025-01-01'); set('dateTo', '');
  selectedMaps = VALID_MAPS.map(([, full]) => full);
  renderMapChips();
}

function applyFiltersFromSidebar() {
  applyFilters(++token);
  window.toggleSidebar?.();
}

function renderLoading() {
  renderHead();
  const body = document.getElementById('tableBody');
  if (body) body.innerHTML = '<tr><td colspan="11"><div class="state-overlay"><div class="spinner"></div><div class="state-title">Fetching data...</div><div class="state-sub">Querying icon statistics.</div></div></td></tr>';
}

function renderError(error) {
  const body = document.getElementById('tableBody');
  if (body) body.innerHTML = `<tr><td colspan="11"><div class="state-overlay"><div class="state-title">Could not load icon statistics</div><div class="state-sub">${escapeHtml(error.message || error)}</div></div></td></tr>`;
}

function format(value, decimals) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(decimals) : '-';
}

function signed(value) {
  return formatSignedDeltaAdaptive(value);
}

function escapeHtml(value) {
  return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}
const escapeAttr = escapeHtml;

const tooltip = document.getElementById('col-tooltip');
document.addEventListener('mouseover', event => {
  if (!mounted || !tooltip) return;
  const cell = event.target.closest?.('.icons-value-tooltip');
  const tipEl = event.target.closest?.('th')?.querySelector('.col-tip');
  if (!cell && !tipEl) return;
  tooltip.textContent = cell?.dataset.valueTooltip || tipEl?.dataset.tip || '';
  tooltip.style.display = 'block';
});
document.addEventListener('mousemove', event => {
  if (!mounted || !tooltip) return;
  const cell = event.target.closest?.('.icons-value-tooltip');
  const tipEl = event.target.closest?.('th')?.querySelector('.col-tip');
  if (!cell && !tipEl) return;
  tooltip.style.left = `${Math.max(8, Math.min(event.clientX + 12, window.innerWidth - tooltip.offsetWidth - 8))}px`;
  tooltip.style.top = `${event.clientY + 18}px`;
});
document.addEventListener('mouseout', event => {
  if (!mounted || !tooltip) return;
  const source = event.target.closest?.('.icons-value-tooltip, th');
  const destination = event.relatedTarget?.closest?.('.icons-value-tooltip, th');
  if (source && destination !== source) tooltip.style.display = 'none';
});
