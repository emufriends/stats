import {
  cappedNumericRange,
  deltaRangeColor,
  frequencyColor,
  numericRange,
  orangeGreenRangeColor,
  violetRangeColor,
} from '../color-scales.js?v=20260711-1';
import {
  INSUFFICIENT_DATA_TOOLTIP,
  formatSignedDeltaAdaptive,
  formatSignedPercentAdaptive,
  isInsufficientObservationCount,
  mapTooltipLabel,
} from '../table-cells.js?v=20260712-4';
import { loadStats } from '../snapshot-cache.js?v=20260719-1';

export const id = 'scoring';
export const title = 'Scoring';
export const navLabel = 'Scoring';

const SNAPSHOT_ROOT = 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/scoring';
const MAPS = [
  ['1a', 'map_1a', 'Map 1a: Observation Tower'], ['2a', 'map_2a', 'Map 2a: Outdoor Areas'],
  ['3a', 'map_3a', 'Map 3a: Silver Lake'], ['4a', 'map_4a', 'Map 4a: Commercial Harbor'],
  ['5a', 'map_5a', 'Map 5a: Park Restaurant'], ['6a', 'map_6a', 'Map 6a: Research Institute'],
  ['7a', 'map_7a', 'Map 7a: Ice Cream Parlors'], ['8a', 'map_8a', 'Map 8a: Hollywood Hills'],
  ['9', 'map_9', 'Map 9: Geographical Zoo'], ['10', 'map_10', 'Map 10: Rescue Station'],
  ['11', 'map_11', 'Map 11: Caves'], ['12', 'map_12', 'Map 12: Artificial Intelligence'],
  ['13', 'map_13', 'Map 13: Drawing Board'], ['14', 'map_14', 'Map 14: Lagoon'],
  ['T1', 'map_t1', 'Map T1: Tournament 1'],
];
const VIEWS = {
  final_score: { label: 'Final score', header: 'Final score', slug: 'final-score', expandable: true },
  appeal: { label: 'Appeal', header: 'Appeal', slug: 'appeal', expandable: true },
  conservation_points: { label: 'Conservation points', header: 'Conservation points', slug: 'conservation-points', expandable: true },
  reputation: { label: 'Reputation', header: 'Reputation', slug: 'reputation', expandable: false },
};

export const mainHtml = `
  <div class="main-header sponsor-endgames-main-header scoring-main-header">
    <div class="table-meta" id="scoringMeta"></div>
    <div class="build-switches scoring-switches">
      <div class="maps-h2h-mode scoring-compare" role="group" aria-label="Scoring comparison mode">
        <button type="button" class="active" data-compare="raw" onclick="setScoringCompare('raw')">Raw</button>
        <button type="button" data-compare="average" onclick="setScoringCompare('average')">vs. avg</button>
      </div>
      <div class="maps-h2h-mode scoring-mode" role="group" aria-label="Scoring metric">
        <button type="button" class="active" data-mode="delta" onclick="setScoringMode('delta')">Elo &Delta;</button>
        <button type="button" data-mode="frequency" onclick="setScoringMode('frequency')">Frequency</button>
      </div>
    </div>
  </div>
  <div class="attributes-bar endgames-tabs-bar">
    <div class="attributes-bar-header endgames-tabs-header">
      <div class="endgames-tabs scoring-tabs" role="tablist" aria-label="Scoring views">
        ${Object.entries(VIEWS).map(([key, item], index) => `<button type="button" class="endgames-tab${index === 0 ? ' active' : ''}" data-view="${key}" onclick="setScoringView('${key}')">${item.label}</button>`).join('')}
      </div>
    </div>
  </div>
  <div id="scoringContent"></div>`;

export const sidebarHtml = `
  <div class="sidebar-header"><span class="sidebar-title">Filters</span><div style="display:flex;align-items:center;gap:6px;">
    <button class="reset-btn" onclick="resetScoringFilters()">Reset</button>
    <button class="sidebar-close-btn" onclick="toggleSidebar()" title="Close filters">x</button>
  </div></div>
  <hr class="divider" />
  <div class="filter-group"><span class="filter-label">Player ELO</span><div class="range-row">
    <input class="range-input" type="number" id="scoringPlayerEloMin" placeholder="Min" value="300" min="0" />
    <input class="range-input" type="number" id="scoringPlayerEloMax" placeholder="Max" min="0" />
  </div></div>
  <div class="filter-group"><span class="filter-label">Opponent ELO</span><div class="range-row">
    <input class="range-input" type="number" id="scoringOpponentEloMin" placeholder="Min" value="300" min="0" />
    <input class="range-input" type="number" id="scoringOpponentEloMax" placeholder="Max" min="0" />
  </div></div>
  <hr class="divider" />
  <div class="filter-group"><span class="filter-label">Date Range</span>
    <input class="date-input" type="text" id="scoringDateFrom" value="2025-01-01" placeholder="yyyy-mm-dd" />
    <input class="date-input" type="text" id="scoringDateTo" placeholder="yyyy-mm-dd" />
  </div>
  <hr class="divider" />
  <div class="filter-action-stack"><button class="apply-btn" onclick="applyScoringFilters()">Apply filters</button></div>`;

let mounted = false;
let token = 0;
let isMW = 1;
let view = 'final_score';
let mode = 'delta';
let compare = 'raw';
let rows = [];
let expandedRows = [];
let expandedByView = { final_score: false, appeal: false, conservation_points: false, reputation: false };

export function mount({ dataset = 1 } = {}) {
  mounted = true;
  token += 1;
  isMW = Number(dataset) === 0 ? 0 : 1;
  view = 'final_score';
  mode = 'delta';
  compare = 'raw';
  rows = [];
  expandedRows = [];
  expandedByView = { final_score: false, appeal: false, conservation_points: false, reputation: false };
  Object.assign(window, {
    setScoringView, setScoringMode, setScoringCompare, toggleScoringExpanded,
    resetScoringFilters, applyScoringFilters,
  });
  syncControls();
  loadData(token);
}

export function unmount() { mounted = false; token += 1; hideTooltip(); }
export function setDataset(value) { isMW = Number(value) === 0 ? 0 : 1; loadData(++token); }

function setScoringView(next) {
  if (!VIEWS[next]) return;
  view = next;
  mode = 'delta';
  compare = 'raw';
  rows = [];
  expandedRows = [];
  syncControls();
  loadData(++token);
}
function setScoringMode(next) { mode = next === 'frequency' ? 'frequency' : 'delta'; syncControls(); render(); }
function setScoringCompare(next) { compare = next === 'average' ? 'average' : 'raw'; syncControls(); render(); }
function toggleScoringExpanded() {
  if (!VIEWS[view].expandable) return;
  expandedByView[view] = !expandedByView[view];
  render();
}
function syncControls() {
  document.querySelectorAll('.scoring-tabs .endgames-tab').forEach(button => button.classList.toggle('active', button.dataset.view === view));
  document.querySelectorAll('.scoring-mode button').forEach(button => button.classList.toggle('active', button.dataset.mode === mode));
  document.querySelectorAll('.scoring-compare button').forEach(button => button.classList.toggle('active', button.dataset.compare === compare));
}

function inputValue(id) { return document.getElementById(id)?.value ?? ''; }
function params() {
  return {
    stats_page: 'scoring', scoring_view: view, is_mw: isMW,
    maps: MAPS.map(([, , full]) => full),
    player_elo_min: inputValue('scoringPlayerEloMin') === '' ? 0 : Number(inputValue('scoringPlayerEloMin')),
    player_elo_max: inputValue('scoringPlayerEloMax') === '' ? null : Number(inputValue('scoringPlayerEloMax')),
    opponent_elo_min: inputValue('scoringOpponentEloMin') === '' ? 0 : Number(inputValue('scoringOpponentEloMin')),
    opponent_elo_max: inputValue('scoringOpponentEloMax') === '' ? null : Number(inputValue('scoringOpponentEloMax')),
    date_from: inputValue('scoringDateFrom') || null,
    date_to: inputValue('scoringDateTo') || null,
    completed_only: null,
  };
}
function isDefault(p) {
  return p.player_elo_min === 300 && p.player_elo_max === null && p.opponent_elo_min === 300 &&
    p.opponent_elo_max === null && p.date_from === '2025-01-01' && p.date_to === null;
}
function snapshotUrl() { return `${SNAPSHOT_ROOT}/${VIEWS[view].slug}/default-${isMW ? 'mw' : 'base'}.json`; }

async function loadData(activeToken) {
  renderLoading();
  try {
    const p = params();
    const payload = await loadStats(p, isDefault(p) ? snapshotUrl() : null);
    if (!mounted || activeToken !== token) return;
    rows = payload.data || [];
    expandedRows = payload.expanded_data || [];
    render();
  } catch (error) {
    if (mounted && activeToken === token) renderError(error);
  }
}

function render() {
  const expanded = VIEWS[view].expandable && expandedByView[view];
  const displayRows = expanded ? expandedRows : rows;
  const mapFields = MAPS.map(([, key]) => key);
  const mapValues = displayRows.flatMap(row => mapFields.map(field => ({ value: displayedValue(row, field), count: row[`count_${field}`] })));
  const mapRange = mode === 'delta'
    ? cappedNumericRange(mapValues.filter(item => !isInsufficientObservationCount(item.count)), item => item.value)
    : numericRange(mapValues, item => item.value);
  const avgRange = mode === 'delta'
    ? numericRange(displayRows, row => row.avg)
    : numericRange(displayRows, row => frequencyFor(row, 'avg'));
  document.getElementById('scoringMeta').textContent = '';
  document.getElementById('scoringContent').innerHTML = `<div class="build-hexes-shell scoring-table-shell ${VIEWS[view].expandable ? 'is-expandable' : ''} ${expanded ? 'is-expanded' : ''}">
    <div class="table-wrap build-hexes-wrap"><div class="table-scroll">
      <table class="maps-table build-hexes-table scoring-table ${mode === 'frequency' ? 'build-hexes-frequency scoring-frequency-table' : ''}">
        <thead><tr><th class="build-hexes-bucket-header" style="width:10%">${escapeHtml(VIEWS[view].header)}</th>
          ${MAPS.map(([short, , full]) => `<th class="maps-custom-tip" data-tip="${escapeAttr(mapTooltipLabel(full))}" style="width:5.5%">${escapeHtml(short)}</th>`).join('')}
          <th style="width:7.5%">Avg</th></tr></thead>
        <tbody>${displayRows.map(row => `<tr class="${expanded ? 'hexes-expanded-row' : ''}"><td class="sponsor-name-cell build-hexes-bucket-cell scoring-bucket-cell">${escapeHtml(row.bucket_label)}</td>
          ${MAPS.map(([, field]) => mapCell(row, field, mapRange, expanded)).join('')}${avgCell(row, avgRange)}</tr>`).join('')}</tbody>
      </table>
    </div></div>
    ${VIEWS[view].expandable ? `<button type="button" class="build-expand-btn" onclick="toggleScoringExpanded()" aria-expanded="${expanded}" aria-label="${expanded ? 'Collapse scoring values' : 'Expand scoring values'}" title="${expanded ? 'Collapse values' : 'Expand values'}"><span aria-hidden="true">${expanded ? '&#9650;' : '&#9660;'}</span></button>` : ''}
  </div>`;
}

function frequencyFor(row, field) {
  const denominator = Number(row[`denom_${field}`]);
  return denominator > 0 ? 100 * Number(row[`count_${field}`] || 0) / denominator : Number.NaN;
}
function displayedValue(row, field) {
  const raw = mode === 'frequency' ? frequencyFor(row, field) : Number(row[field]);
  if (!Number.isFinite(raw) || compare === 'raw') return raw;
  const avg = mode === 'frequency' ? frequencyFor(row, 'avg') : Number(row.avg);
  return Number.isFinite(avg) ? raw - avg : Number.NaN;
}
function mapCell(row, field, range, expanded) {
  const value = displayedValue(row, field);
  if (!Number.isFinite(value)) return unavailableCell();
  if (mode === 'frequency') {
    const raw = frequencyFor(row, field);
    const text = compare === 'average' ? formatSignedPercentAdaptive(value) : `${raw.toFixed(2)}%`;
    const tooltip = `${fmtInt(row[`count_${field}`])} / ${fmtInt(row[`denom_${field}`])}`;
    return `<td class="build-value-tooltip" data-value-tooltip="${tooltip}" style="color:${frequencyColor(value, expanded ? 20 : 50)}">${text}</td>`;
  }
  const count = Number(row[`count_${field}`]) || 0;
  const text = formatSignedDeltaAdaptive(value, true);
  if (compare === 'average') {
    if (isInsufficientObservationCount(count)) return `<td class="delta sponsor-delta-insufficient build-value-tooltip" data-value-tooltip="${INSUFFICIENT_DATA_TOOLTIP}">${text}</td>`;
    return `<td class="delta cp-map-comparison" style="color:${deltaRangeColor(value, range.min, range.max)}">${text}</td>`;
  }
  if (isInsufficientObservationCount(count)) return `<td class="delta sponsor-delta-insufficient build-value-tooltip" data-value-tooltip="${INSUFFICIENT_DATA_TOOLTIP}">${text}</td>`;
  return `<td class="delta delta-ci-cell" data-ci-low="${escapeAttr(row[`${field}_ci95_low`] ?? '')}" data-ci-high="${escapeAttr(row[`${field}_ci95_high`] ?? '')}" data-ci-n="${escapeAttr(row[`${field}_ci95_n`] ?? '')}" data-ci-color-min="${escapeAttr(range.min ?? '')}" data-ci-color-max="${escapeAttr(range.max ?? '')}" style="color:${deltaRangeColor(value, range.min, range.max)}">${text}</td>`;
}
function avgCell(row, range) {
  if (mode === 'frequency') {
    const value = frequencyFor(row, 'avg');
    if (!Number.isFinite(value)) return unavailableCell();
    return `<td class="build-value-tooltip" data-value-tooltip="${fmtInt(row.count_avg)} / ${fmtInt(row.denom_avg)}" style="color:${violetRangeColor(value, range.min, range.max)}">${value.toFixed(2)}%</td>`;
  }
  const value = Number(row.avg);
  if (!Number.isFinite(value)) return unavailableCell();
  const text = formatSignedDeltaAdaptive(value, true);
  if (isInsufficientObservationCount(row.count_avg)) return `<td class="delta sponsor-delta-insufficient build-value-tooltip" data-value-tooltip="${INSUFFICIENT_DATA_TOOLTIP}">${text}</td>`;
  return `<td class="delta delta-ci-cell" data-ci-low="${escapeAttr(row.avg_ci95_low ?? '')}" data-ci-high="${escapeAttr(row.avg_ci95_high ?? '')}" data-ci-n="${escapeAttr(row.avg_ci95_n ?? '')}" data-ci-color-scale="orange-green" data-ci-color-min="${escapeAttr(range.min ?? '')}" data-ci-color-max="${escapeAttr(range.max ?? '')}" style="color:${orangeGreenRangeColor(value, range.min, range.max)}">${text}</td>`;
}
function unavailableCell() { return '<td class="unavailable-cell">-</td>'; }

function resetScoringFilters() {
  const set = (id, value) => { const element = document.getElementById(id); if (element) element.value = value; };
  set('scoringPlayerEloMin', '300'); set('scoringPlayerEloMax', '');
  set('scoringOpponentEloMin', '300'); set('scoringOpponentEloMax', '');
  set('scoringDateFrom', '2025-01-01'); set('scoringDateTo', '');
  compare = 'raw';
  expandedByView[view] = false;
  syncControls();
  loadData(++token);
}
function applyScoringFilters() {
  loadData(++token);
  document.getElementById('sidebar')?.classList.remove('open');
  document.getElementById('sidebarOverlay')?.classList.remove('active');
}
function renderLoading() { document.getElementById('scoringContent').innerHTML = '<div class="state-overlay"><div class="spinner"></div><div class="state-title">Fetching scoring statistics...</div></div>'; }
function renderError(error) { document.getElementById('scoringContent').innerHTML = `<div class="state-overlay"><div class="state-title">Could not load scoring statistics</div><div class="state-sub">${escapeHtml(error.message || error)}</div></div>`; }
function fmtInt(value) { return Number(value || 0).toLocaleString('en-US'); }
function escapeHtml(value) { return String(value ?? '').replace(/[&<>"']/g, character => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[character])); }
const escapeAttr = escapeHtml;

const tooltip = document.getElementById('col-tooltip');
function tooltipSource(event) { return event.target.closest?.('.build-value-tooltip, .maps-custom-tip'); }
function positionTooltip(event) {
  if (!tooltip) return;
  tooltip.style.left = `${Math.max(8, Math.min(event.clientX + 12, window.innerWidth - tooltip.offsetWidth - 8))}px`;
  tooltip.style.top = `${event.clientY + 18}px`;
}
function hideTooltip() { if (tooltip) tooltip.style.display = 'none'; }
document.addEventListener('mouseover', event => {
  if (!mounted || !tooltip) return;
  const source = tooltipSource(event);
  if (!source) return;
  tooltip.textContent = source.dataset.valueTooltip || source.dataset.tip || '';
  tooltip.style.display = 'block';
  positionTooltip(event);
});
document.addEventListener('mousemove', event => { if (mounted && tooltip && tooltipSource(event)) positionTooltip(event); });
document.addEventListener('mouseout', event => {
  if (!mounted || !tooltip) return;
  const source = tooltipSource(event);
  const destination = event.relatedTarget ? tooltipSource({ target: event.relatedTarget }) : null;
  if (source && destination !== source) hideTooltip();
});
