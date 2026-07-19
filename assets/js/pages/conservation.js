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

export const id = 'conservation';
export const title = 'Conservation';
export const navLabel = 'Conservation';

const API_ROOT = 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/conservation';
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
const VIEW_SLUG = { projects: 'projects', project_rewards: 'project-rewards', cp_rewards: 'cp-rewards' };

export const mainHtml = `
  <div class="main-header sponsor-endgames-main-header conservation-main-header">
    <div class="table-meta" id="conservationMeta"></div>
    <div class="conservation-switches">
      <div class="maps-h2h-mode conservation-subject" role="group" aria-label="Conservation project subject">
        <button type="button" class="active" data-subject="projects" onclick="setConservationSubject('projects')">Projects</button>
        <button type="button" data-subject="releases" onclick="setConservationSubject('releases')">Releases</button>
      </div>
      <div class="maps-h2h-mode conservation-scope" role="group" aria-label="CP reward threshold">
        <button type="button" data-scope="5" onclick="setConservationScope('5')">5 CP</button>
        <button type="button" data-scope="8" onclick="setConservationScope('8')">8 CP</button>
        <button type="button" class="active" data-scope="combined" onclick="setConservationScope('combined')">5+8 CP</button>
      </div>
      <div class="maps-h2h-mode conservation-compare" role="group" aria-label="Conservation comparison mode">
        <button type="button" class="active" data-compare="raw" onclick="setConservationCompare('raw')">Raw</button>
        <button type="button" data-compare="average" onclick="setConservationCompare('average')">vs. avg</button>
      </div>
      <div class="maps-h2h-mode conservation-mode" role="group" aria-label="Conservation metric">
        <button type="button" class="active" data-mode="delta" onclick="setConservationMode('delta')">Elo &Delta;</button>
        <button type="button" data-mode="frequency" onclick="setConservationMode('frequency')">Frequency</button>
      </div>
    </div>
  </div>
  <div class="attributes-bar endgames-tabs-bar">
    <div class="attributes-bar-header endgames-tabs-header">
      <div class="endgames-tabs conservation-tabs" role="tablist" aria-label="Conservation views">
        <button class="endgames-tab active" data-view="projects" onclick="setConservationView('projects')">Projects</button>
        <button class="endgames-tab" data-view="project_rewards" onclick="setConservationView('project_rewards')">Project rewards</button>
        <button class="endgames-tab" data-view="cp_rewards" onclick="setConservationView('cp_rewards')">CP rewards</button>
      </div>
    </div>
  </div>
  <div id="conservationContent"></div>`;

export const sidebarHtml = `
  <div class="sidebar-header"><span class="sidebar-title">Filters</span><div style="display:flex;align-items:center;gap:6px;">
    <button class="reset-btn" onclick="resetConservationFilters()">Reset</button>
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
  <hr class="divider conservation-map-divider" />
  <div class="filter-group conservation-map-filter"><div style="display:flex;align-items:baseline;gap:6px;margin-bottom:8px;">
    <span class="filter-label" style="margin-bottom:0">Maps</span>
    <span class="map-select-all-none">(<span class="map-toggle-link" onclick="selectAllConservationMaps()">all</span> / <span class="map-toggle-link" onclick="selectNoneConservationMaps()">none</span>)</span>
  </div><div class="chip-grid" id="conservationMapChips"></div></div>
  <hr class="divider" />
  <div class="filter-group"><span class="filter-label">Date Range</span>
    <input class="date-input" type="text" id="dateFrom" value="2025-01-01" placeholder="yyyy-mm-dd" />
    <input class="date-input" type="text" id="dateTo" placeholder="yyyy-mm-dd" />
  </div>
  <hr class="divider conservation-completed-divider" />
  <div class="filter-group conservation-completed-filter"><div class="toggle-row"><span class="toggle-label">Completed games only</span>
    <label class="toggle"><input type="checkbox" id="conservationCompletedToggle" /><span class="toggle-track"></span></label>
  </div></div>
  <hr class="divider" />
  <div class="filter-action-stack"><button class="apply-btn" onclick="applyConservationFilters()">Apply filters</button></div>`;

let mounted = false;
let token = 0;
let isMW = 1;
let view = 'projects';
let mode = 'delta';
let scope = 'combined';
let compare = 'raw';
let subject = 'projects';
let rows = [];
let selectedMaps = MAPS.map(([, , full]) => full);
let rewardSort = { field: 'delta_overall', direction: 'desc' };

export function mount({ dataset = 1 } = {}) {
  mounted = true; token += 1; isMW = Number(dataset) === 0 ? 0 : 1;
  view = 'projects'; mode = 'delta'; scope = 'combined'; compare = 'raw'; subject = 'projects'; rows = [];
  rewardSort = { field: 'delta_overall', direction: 'desc' };
  selectedMaps = MAPS.map(([, , full]) => full);
  Object.assign(window, {
    setConservationView, setConservationMode, setConservationScope, setConservationCompare, setConservationSubject,
    sortConservationRewards, resetConservationFilters, applyConservationFilters,
    toggleConservationMap, selectAllConservationMaps, selectNoneConservationMaps,
  });
  renderMapChips(); syncControls(); loadData(token);
}

export function unmount() { mounted = false; token += 1; hideTooltip(); }
export function setDataset(value) { isMW = Number(value) === 0 ? 0 : 1; loadData(++token); }

function setConservationView(next) {
  view = ['projects', 'project_rewards', 'cp_rewards'].includes(next) ? next : 'projects';
  mode = 'delta'; scope = 'combined'; compare = 'raw';
  rewardSort = { field: 'delta_overall', direction: 'desc' };
  syncControls(); loadData(++token);
}
function setConservationMode(next) { mode = next === 'frequency' ? 'frequency' : 'delta'; syncControls(); render(); }
function setConservationScope(next) { scope = ['5', '8', 'combined'].includes(next) ? next : 'combined'; syncControls(); render(); }
function setConservationCompare(next) { compare = next === 'average' ? 'average' : 'raw'; syncControls(); render(); }
function setConservationSubject(next) { subject = next === 'releases' ? 'releases' : 'projects'; syncControls(); render(); }

function syncControls() {
  document.querySelectorAll('.conservation-tabs .endgames-tab').forEach(btn => btn.classList.toggle('active', btn.dataset.view === view));
  document.querySelectorAll('.conservation-mode button').forEach(btn => btn.classList.toggle('active', btn.dataset.mode === mode));
  document.querySelectorAll('.conservation-scope button').forEach(btn => btn.classList.toggle('active', btn.dataset.scope === scope));
  document.querySelectorAll('.conservation-compare button').forEach(btn => btn.classList.toggle('active', btn.dataset.compare === compare));
  document.querySelectorAll('.conservation-subject button').forEach(btn => btn.classList.toggle('active', btn.dataset.subject === subject));
  document.querySelector('.conservation-subject')?.classList.toggle('is-hidden', view !== 'projects');
  document.querySelector('.conservation-scope')?.classList.toggle('is-hidden', view !== 'cp_rewards');
  document.querySelector('.conservation-compare')?.classList.toggle('is-hidden', !['projects', 'cp_rewards'].includes(view));
  document.querySelector('.conservation-map-filter')?.classList.toggle('is-hidden', view === 'cp_rewards');
  document.querySelector('.conservation-map-divider')?.classList.toggle('is-hidden', view === 'cp_rewards');
  const showCompleted = view === 'cp_rewards' || (view === 'project_rewards' && mode === 'delta');
  document.querySelector('.conservation-completed-filter')?.classList.toggle('is-hidden', !showCompleted);
  document.querySelector('.conservation-completed-divider')?.classList.toggle('is-hidden', !showCompleted);
  document.querySelector('.conservation-switches')?.classList.toggle('is-cp-rewards', view === 'cp_rewards');
  document.querySelector('.conservation-switches')?.classList.toggle('is-projects', view === 'projects');
}

function params() {
  const value = id => document.getElementById(id)?.value ?? '';
  return {
    stats_page: 'conservation', conservation_view: view, is_mw: isMW,
    maps: view === 'cp_rewards' ? MAPS.map(([, , full]) => full) : selectedMaps,
    player_elo_min: value('playerEloMin') === '' ? 0 : Number(value('playerEloMin')),
    player_elo_max: value('playerEloMax') === '' ? null : Number(value('playerEloMax')),
    opponent_elo_min: value('opponentEloMin') === '' ? 0 : Number(value('opponentEloMin')),
    opponent_elo_max: value('opponentEloMax') === '' ? null : Number(value('opponentEloMax')),
    date_from: value('dateFrom') || '2025-01-01', date_to: value('dateTo') || null,
    completed_only: view === 'projects' ? null : (document.getElementById('conservationCompletedToggle')?.checked ? true : null),
  };
}
function isDefault(p) {
  return p.player_elo_min === 300 && p.player_elo_max === null && p.opponent_elo_min === 300 &&
    p.opponent_elo_max === null && p.date_from === '2025-01-01' && p.date_to === null &&
    p.completed_only === null && (view === 'cp_rewards' || selectedMaps.length === MAPS.length);
}
function snapshotUrl() { return `${API_ROOT}/${VIEW_SLUG[view]}/default-${isMW ? 'mw' : 'base'}.json`; }

async function loadData(activeToken) {
  renderLoading();
  try {
    const p = params();
    const payload = await loadStats(p, isDefault(p) ? snapshotUrl() : null);
    if (!mounted || activeToken !== token) return;
    rows = payload.data || []; render();
  } catch (error) { if (mounted && activeToken === token) renderError(error); }
}
function render() {
  document.getElementById('conservationMeta').textContent = '';
  if (view === 'projects') renderProjects();
  else if (view === 'project_rewards') renderProjectRewards();
  else renderCpRewards();
}

function renderProjects() {
  const subjectRows = rows.filter(row => (row.subject || 'projects') === subject);
  const mapFields = MAPS.map(([, key]) => key);
  const values = subjectRows.flatMap(row => mapFields.map(field => ({ value: projectValue(row, field), count: row[`count_${field}`] })));
  const mapRange = mode === 'delta'
    ? cappedNumericRange(values.filter(item => !isInsufficientObservationCount(item.count)), item => item.value)
    : numericRange(values, item => item.value);
  const avgRange = mode === 'delta' ? numericRange(subjectRows, row => row.avg) : numericRange(subjectRows, row => percentage(row.count_avg, row.denom_avg));
  document.getElementById('conservationContent').innerHTML = `<div class="table-wrap"><div class="table-scroll">
    <table class="maps-table conservation-projects-table ${mode === 'frequency' ? 'conservation-frequency-table' : ''}"><thead><tr><th style="width:12%;text-align:center;">Count</th>
      ${MAPS.map(([short,,full]) => `<th class="maps-custom-tip" data-tip="${escapeAttr(mapTooltipLabel(full))}" style="width:5.5%">${short}</th>`).join('')}
      <th style="width:5.5%;text-align:center;">Avg</th></tr></thead>
      <tbody>${subjectRows.map(row => `<tr><td class="sponsor-name-cell">${escapeHtml(row.count_value)}</td>
        ${MAPS.map(([,field]) => projectCell(row, field, mapRange)).join('')}${projectAvgCell(row, avgRange)}</tr>`).join('')}</tbody>
    </table></div></div>`;
}
function projectValue(row, field) {
  const raw = mode === 'frequency' ? percentage(row[`count_${field}`], row[`denom_${field}`]) : number(row[field]);
  if (compare === 'raw') return raw;
  const overall = mode === 'frequency' ? percentage(row.count_avg, row.denom_avg) : number(row.avg);
  return Number.isFinite(raw) && Number.isFinite(overall) ? raw - overall : Number.NaN;
}
function projectCell(row, field, range) {
  if (mode === 'frequency') {
    const value = projectValue(row, field);
    if (!Number.isFinite(value)) return unavailableTd();
    const raw = percentage(row[`count_${field}`], row[`denom_${field}`]);
    const text = compare === 'average' ? formatSignedPercentAdaptive(value) : fmtPct(raw);
    return `<td class="build-value-tooltip" data-value-tooltip="${fmtInt(row[`count_${field}`])} / ${fmtInt(row[`denom_${field}`])}" style="color:${frequencyColor(value, 50)}">${text}</td>`;
  }
  if (compare === 'average') {
    const value = projectValue(row, field);
    if (!Number.isFinite(value)) return unavailableTd();
    if (isInsufficientObservationCount(row[`count_${field}`])) return `<td class="delta sponsor-delta-insufficient build-value-tooltip" data-value-tooltip="${INSUFFICIENT_DATA_TOOLTIP}">${fmtSigned(value, 3, true)}</td>`;
    return `<td class="delta cp-map-comparison" style="color:${deltaRangeColor(value, range.min, range.max)}">${fmtSigned(value, 3, true)}</td>`;
  }
  return deltaTd(row, field, row[`count_${field}`], range);
}
function projectAvgCell(row, range) {
  if (mode === 'frequency') {
    const pct = percentage(row.count_avg, row.denom_avg);
    if (!Number.isFinite(pct)) return unavailableTd();
    return `<td class="build-value-tooltip" data-value-tooltip="${fmtInt(row.count_avg)} / ${fmtInt(row.denom_avg)}" style="color:${violetRangeColor(pct, range.min, range.max)}">${fmtPct(pct)}</td>`;
  }
  const value = number(row.avg);
  if (!Number.isFinite(value)) return unavailableTd();
  const n = Number(row.avg_ci95_n ?? row.count_avg);
  const display = fmtSigned(value, 3, true);
  if (isInsufficientObservationCount(n)) {
    return `<td class="delta cp-cell sponsor-delta-insufficient build-value-tooltip" data-value-tooltip="${INSUFFICIENT_DATA_TOOLTIP}">${display}</td>`;
  }
  return `<td class="delta cp-cell delta-ci-cell" data-ci-low="${escapeAttr(row.avg_ci95_low ?? '')}" data-ci-high="${escapeAttr(row.avg_ci95_high ?? '')}" data-ci-n="${escapeAttr(row.avg_ci95_n ?? '')}" data-ci-color-scale="orange-green" data-ci-color-min="${escapeAttr(range.min ?? '')}" data-ci-color-max="${escapeAttr(range.max ?? '')}" style="color:${orangeGreenRangeColor(value, range.min, range.max)}">${display}</td>`;
}

function sortConservationRewards(field) {
  const same = rewardSort.field === field;
  rewardSort = { field, direction: same && rewardSort.direction === 'desc' ? 'asc' : 'desc' };
  render();
}
function sortArrow(field) { return rewardSort.field === field ? (rewardSort.direction === 'asc' ? '\u2191' : '\u2193') : '\u2195'; }
function sortHeaderClass(field) { return rewardSort.field === field ? ' class="sorted"' : ''; }
function mapSortHeaderClass(field) { return `maps-custom-tip${rewardSort.field === field ? ' sorted' : ''}`; }
function sortArrowClass(field) { return rewardSort.field === field ? 'sort-arrow active' : 'sort-arrow'; }
function sortArrowHtml(field) { return `<span class="${sortArrowClass(field)}">${sortArrow(field)}</span>`; }
function sortedRewards(source, projectReward = false) {
  const compareRows = (a, b) => {
    let comparison;
    if (rewardSort.field === 'label') comparison = projectReward ? number(a.sort_order) - number(b.sort_order) : String(a.label).localeCompare(String(b.label));
    else comparison = sortableValue(a, rewardSort.field) - sortableValue(b, rewardSort.field);
    if (!Number.isFinite(comparison) || comparison === 0) comparison = number(a.sort_order) - number(b.sort_order);
    return rewardSort.direction === 'asc' ? comparison : -comparison;
  };
  if (!projectReward) return [...source].sort(compareRows);
  // Numeric sorting must not interleave generic and map-specific rewards: the
  // double rule represents a real gameplay distinction, not decorative striping.
  const generic = source.filter(row => row.group_name === 'generic').sort(compareRows);
  const mapped = source.filter(row => row.group_name !== 'generic').sort(compareRows);
  return [...generic, ...mapped];
}
function sortableValue(row, field) {
  const key = field.replace(/^delta_/, '');
  if (view === 'cp_rewards') return cpDisplayedValue(row, key);
  if (mode === 'frequency') return percentage(row[`freq_${key}_numer`], row[`freq_${key}_denom`]);
  return number(row[field]);
}

function renderProjectRewards() {
  const data = sortedRewards(rows, true);
  const orderFields = Array.from({ length: 7 }, (_, index) => `delta_order_${index + 1}`);
  const overallRange = cappedNumericRange(rows.map(row => ({ value: row.delta_overall, count: row.count_delta_overall })).filter(item => !isInsufficientObservationCount(item.count)), item => item.value);
  const orderRange = cappedNumericRange(rows.flatMap(row => orderFields.map(field => ({ value: row[field], count: row[`count_${field}`] }))).filter(item => !isInsufficientObservationCount(item.count)), item => item.value);
  const prefix = mode === 'delta' ? '\u0394' : 'f';
  document.getElementById('conservationContent').innerHTML = `<div class="table-wrap"><div class="table-scroll">
    <table class="sponsor-endgames-table conservation-rewards-table"><thead><tr>
      <th${sortHeaderClass('label')} style="width:28%;text-align:center;" onclick="sortConservationRewards('label')">Reward ${sortArrowHtml('label')}</th>
      <th${sortHeaderClass('delta_overall')} style="width:16%;text-align:center;" onclick="sortConservationRewards('delta_overall')">${prefix} (Overall) ${sortArrowHtml('delta_overall')}</th>
      ${Array.from({ length: 7 }, (_, index) => `<th${sortHeaderClass(`delta_order_${index + 1}`)} style="width:8%;text-align:center;" onclick="sortConservationRewards('delta_order_${index + 1}')">${prefix} (${ordinal(index + 1)}) ${sortArrowHtml(`delta_order_${index + 1}`)}</th>`).join('')}
      </tr></thead><tbody>${data.map((row, index) => `<tr class="${index > 0 && data[index - 1].group_name === 'generic' && row.group_name !== 'generic' ? 'conservation-group-separator' : ''}">
        <td class="sponsor-name-cell">${escapeHtml(row.label)}</td>${projectRewardMetricCell(row, 'overall', overallRange, true)}
        ${Array.from({ length: 7 }, (_, order) => projectRewardMetricCell(row, `order_${order + 1}`, orderRange, false)).join('')}</tr>`).join('')}</tbody>
    </table></div></div>`;
}
function projectRewardMetricCell(row, key, range, overall) {
  if (row.available === false) return unavailableTd();
  if (mode === 'frequency') return frequencyTd(row[`freq_${key}_numer`], row[`freq_${key}_denom`], overall ? 100 : 50, overall ? ' conservation-overall-cell' : '');
  return deltaTd(row, `delta_${key}`, row[`count_delta_${key}`], range, overall ? ' conservation-overall-cell' : '');
}

function renderCpRewards() {
  const scopedRows = rows.filter(row => row.scope === scope);
  const data = sortedRewards(scopedRows);
  const mapFields = MAPS.map(([,key]) => key);
  const displayed = scopedRows.flatMap(row => mapFields.map(field => ({ value: cpDisplayedValue(row, field), count: row[`count_delta_${field}`] })));
  const mapRange = mode === 'delta'
    ? cappedNumericRange(displayed.filter(item => !isInsufficientObservationCount(item.count)), item => item.value)
    : numericRange(displayed, item => item.value);
  const avgRange = mode === 'delta'
    ? numericRange(scopedRows, row => row.delta_overall)
    : numericRange(scopedRows, row => percentage(row.freq_overall_numer, row.freq_overall_denom));
  document.getElementById('conservationContent').innerHTML = `<div class="table-wrap"><div class="table-scroll">
    <table class="maps-table conservation-cp-table ${mode === 'frequency' ? 'conservation-frequency-table' : ''}"><thead><tr>
      <th${sortHeaderClass('label')} style="width:12%;text-align:center;" onclick="sortConservationRewards('label')">Reward ${sortArrowHtml('label')}</th>
      ${MAPS.map(([short,key,full]) => `<th class="${mapSortHeaderClass(`delta_${key}`)}" data-tip="${escapeAttr(mapTooltipLabel(full))}" style="width:5.5%;text-align:center;" onclick="sortConservationRewards('delta_${key}')">${short} ${sortArrowHtml(`delta_${key}`)}</th>`).join('')}
      <th class="conservation-avg-header${rewardSort.field === 'delta_overall' ? ' sorted' : ''}" style="width:5.5%;text-align:center;" onclick="sortConservationRewards('delta_overall')"><span class="conservation-avg-header-content">AVG${mode === 'frequency' ? '<span class="col-tip" data-tip="% (chosen when having full choice between all 3 options)">?</span>' : ''}${sortArrowHtml('delta_overall')}</span></th>
      </tr></thead><tbody>${data.map(row => `<tr><td class="sponsor-name-cell">${escapeHtml(row.label)}</td>
        ${MAPS.map(([,key]) => cpMetricCell(row, key, mapRange, false)).join('')}${cpAvgCell(row, avgRange)}</tr>`).join('')}</tbody>
    </table></div></div>`;
}
function cpDisplayedValue(row, key) {
  const raw = mode === 'frequency'
    ? percentage(row[`freq_${key}_numer`], row[`freq_${key}_denom`])
    : number(row[`delta_${key}`]);
  if (key === 'overall' || compare === 'raw') return raw;
  // Overall is the fixed reference. Comparison mode changes map cells only and
  // expresses Frequency differences in percentage points.
  const overall = mode === 'frequency'
    ? percentage(row.freq_overall_numer, row.freq_overall_denom)
    : number(row.delta_overall);
  return Number.isFinite(raw) && Number.isFinite(overall) ? raw - overall : Number.NaN;
}
function cpMetricCell(row, key, range, overall) {
  const value = cpDisplayedValue(row, key);
  if (!Number.isFinite(value)) return unavailableTd();
  const extra = overall ? ' conservation-overall-cell' : '';
  if (mode === 'frequency') {
    const raw = percentage(row[`freq_${key}_numer`], row[`freq_${key}_denom`]);
    const text = compare === 'average' && !overall ? formatSignedPercentAdaptive(value) : fmtPct(raw);
    return `<td class="build-value-tooltip${extra}" data-value-tooltip="${fmtInt(row[`freq_${key}_numer`])} / ${fmtInt(row[`freq_${key}_denom`])}" style="color:${frequencyColor(compare === 'average' && !overall ? value : raw)}">${text}</td>`;
  }
  if (compare === 'average' && !overall) return `<td class="delta cp-map-comparison${extra}" style="color:${deltaRangeColor(value, range.min, range.max)}">${fmtSigned(value, 3, true)}</td>`;
  return deltaTd(row, `delta_${key}`, row[`count_delta_${key}`], range, extra);
}
function cpAvgCell(row, range) {
  if (mode === 'frequency') {
    const pct = percentage(row.freq_overall_numer, row.freq_overall_denom);
    if (!Number.isFinite(pct)) return unavailableTd();
    return `<td class="build-value-tooltip conservation-overall-cell" data-value-tooltip="${fmtInt(row.freq_overall_numer)} / ${fmtInt(row.freq_overall_denom)}" style="color:${violetRangeColor(pct, range.min, range.max)}">${fmtPct(pct)}</td>`;
  }
  const value = number(row.delta_overall);
  if (!Number.isFinite(value)) return unavailableTd();
  if (isInsufficientObservationCount(row.count_delta_overall)) {
    return `<td class="delta sponsor-delta-insufficient build-value-tooltip conservation-overall-cell" data-value-tooltip="${INSUFFICIENT_DATA_TOOLTIP}">${fmtSigned(value)}</td>`;
  }
  return `<td class="delta delta-ci-cell conservation-overall-cell" data-ci-low="${escapeAttr(row.delta_overall_ci95_low ?? '')}" data-ci-high="${escapeAttr(row.delta_overall_ci95_high ?? '')}" data-ci-n="${escapeAttr(row.delta_overall_ci95_n ?? '')}" data-ci-color-scale="orange-green" data-ci-color-min="${escapeAttr(range.min ?? '')}" data-ci-color-max="${escapeAttr(range.max ?? '')}" style="color:${orangeGreenRangeColor(value, range.min, range.max)}">${fmtSigned(value, 3, true)}</td>`;
}

function deltaTd(row, field, count, range, extra = '') {
  const value = number(row[field]);
  if (!Number.isFinite(value)) return unavailableTd();
  if (isInsufficientObservationCount(count)) return `<td class="delta sponsor-delta-insufficient build-value-tooltip${extra}" data-value-tooltip="${INSUFFICIENT_DATA_TOOLTIP}">${fmtSigned(value)}</td>`;
  return `<td class="delta delta-ci-cell${extra}" data-ci-low="${escapeAttr(row[`${field}_ci95_low`] ?? '')}" data-ci-high="${escapeAttr(row[`${field}_ci95_high`] ?? '')}" data-ci-n="${escapeAttr(row[`${field}_ci95_n`] ?? '')}" data-ci-color-min="${escapeAttr(range.min ?? '')}" data-ci-color-max="${escapeAttr(range.max ?? '')}" style="color:${deltaRangeColor(value, range.min, range.max)}">${fmtSigned(value)}</td>`;
}
function frequencyTd(numerator, denominator, cap, extra = '') {
  const pct = percentage(numerator, denominator);
  if (!Number.isFinite(pct)) return unavailableTd();
  return `<td class="build-value-tooltip${extra}" data-value-tooltip="${fmtInt(numerator)} / ${fmtInt(denominator)}" style="color:${frequencyColor(pct, cap)}">${fmtPct(pct)}</td>`;
}
function unavailableTd() { return '<td class="unavailable-cell">-</td>'; }
function percentage(numerator, denominator) { const d = number(denominator); return d > 0 ? 100 * number(numerator || 0) / d : Number.NaN; }
function number(value) { const result = Number(value); return Number.isFinite(result) ? result : Number.NaN; }
function fmtSigned(value, decimals = 3, plusMinusZero = false) { return formatSignedDeltaAdaptive(value, plusMinusZero); }
function fmtPct(value) { return Number.isFinite(number(value)) ? `${number(value).toFixed(2)}%` : '-'; }
function fmtInt(value) { return Number(value || 0).toLocaleString('en-US'); }
function ordinal(value) { return value === 1 ? '1st' : value === 2 ? '2nd' : value === 3 ? '3rd' : `${value}th`; }

function renderLoading() { document.getElementById('conservationContent').innerHTML = '<div class="state-overlay"><div class="spinner"></div><div class="state-title">Fetching conservation statistics...</div></div>'; }
function renderError(error) { document.getElementById('conservationContent').innerHTML = `<div class="state-overlay"><div class="state-title">Could not load conservation statistics</div><div class="state-sub">${escapeHtml(error.message || error)}</div></div>`; }
function renderMapChips() { const host = document.getElementById('conservationMapChips'); if (host) host.innerHTML = MAPS.map(([short,,full]) => `<button class="chip ${selectedMaps.includes(full) ? 'active' : ''}" data-map="${escapeAttr(full)}" onclick="toggleConservationMap(this.dataset.map)">${short}</button>`).join(''); }
function toggleConservationMap(map) { selectedMaps = selectedMaps.includes(map) ? selectedMaps.filter(item => item !== map) : [...selectedMaps, map]; renderMapChips(); }
function selectAllConservationMaps() { selectedMaps = MAPS.map(([, , full]) => full); renderMapChips(); }
function selectNoneConservationMaps() { selectedMaps = []; renderMapChips(); }
function resetConservationFilters() {
  const set = (id, value) => { const element = document.getElementById(id); if (element) element.value = value; };
  set('playerEloMin', '300'); set('playerEloMax', ''); set('opponentEloMin', '300'); set('opponentEloMax', ''); set('dateFrom', '2025-01-01'); set('dateTo', '');
  const completed = document.getElementById('conservationCompletedToggle'); if (completed) completed.checked = false;
  selectedMaps = MAPS.map(([, , full]) => full); renderMapChips(); loadData(++token);
}
function applyConservationFilters() { loadData(++token); document.getElementById('sidebar')?.classList.remove('open'); document.getElementById('sidebarOverlay')?.classList.remove('active'); }
function escapeHtml(value) { return String(value ?? '').replace(/[&<>"']/g, char => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[char])); }
const escapeAttr = escapeHtml;

const tooltip = document.getElementById('col-tooltip');
function tooltipSource(event) { return event.target.closest?.('.build-value-tooltip, .maps-custom-tip') || event.target.closest?.('th')?.querySelector('.col-tip'); }
function positionTooltip(event) { if (!tooltip) return; tooltip.style.left = `${Math.max(8, Math.min(event.clientX + 12, window.innerWidth - tooltip.offsetWidth - 8))}px`; tooltip.style.top = `${event.clientY + 18}px`; }
function hideTooltip() { if (tooltip) tooltip.style.display = 'none'; }
document.addEventListener('mouseover', event => { if (!mounted || !tooltip) return; const source = tooltipSource(event); if (!source) return; tooltip.textContent = source.dataset.valueTooltip || source.dataset.tip || ''; tooltip.style.display = 'block'; positionTooltip(event); });
document.addEventListener('mousemove', event => { if (mounted && tooltip && tooltipSource(event)) positionTooltip(event); });
document.addEventListener('mouseout', event => { if (!mounted || !tooltip) return; const source = tooltipSource(event); const destination = event.relatedTarget ? tooltipSource({ target: event.relatedTarget }) : null; if (source && destination !== source) hideTooltip(); });
