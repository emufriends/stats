import { mapTooltipLabel } from './table-cells.js?v=20260712-4';

// Canonical map catalogue shared by every sidebar map filter. Keep the three
// groups in gameplay order so pages cannot drift into different map defaults
// or present legacy/beginner maps as unnamed extras. Standard chips are visible
// initially; Legacy and Beginner use independent expandable rows with counts.
// Sidebar chips expose their full map label through maps-custom-tip/data-tip.
export const STANDARD_MAPS = [
  ['1a', 'map_1a', 'Map 1a: Observation Tower'], ['2a', 'map_2a', 'Map 2a: Outdoor Areas'],
  ['3a', 'map_3a', 'Map 3a: Silver Lake'], ['4a', 'map_4a', 'Map 4a: Commercial Harbor'],
  ['5a', 'map_5a', 'Map 5a: Park Restaurant'], ['6a', 'map_6a', 'Map 6a: Research Institute'],
  ['7a', 'map_7a', 'Map 7a: Ice Cream Parlors'], ['8a', 'map_8a', 'Map 8a: Hollywood Hills'],
  ['9', 'map_9', 'Map 9: Geographical Zoo'], ['10', 'map_10', 'Map 10: Rescue Station'],
  ['11', 'map_11', 'Map 11: Caves'], ['12', 'map_12', 'Map 12: Artificial Intelligence'],
  ['13', 'map_13', 'Map 13: Drawing Board'], ['14', 'map_14', 'Map 14: Lagoon'],
  ['T1', 'map_t1', 'Map T1: Tournament 1'],
];

export const LEGACY_MAPS = [
  ['1', 'map_1', 'Map 1: Observation Tower'], ['2', 'map_2', 'Map 2: Outdoor Areas'],
  ['3', 'map_3', 'Map 3: Silver Lake'], ['4', 'map_4', 'Map 4: Commercial Harbor'],
  ['5', 'map_5', 'Map 5: Park Restaurant'], ['6', 'map_6', 'Map 6: Research Institute'],
  ['7', 'map_7', 'Map 7: Ice Cream Parlors'], ['8', 'map_8', 'Map 8: Hollywood Hills'],
];

export const BEGINNER_MAPS = [
  ['A', 'map_a', 'Map A'], ['0', 'map_0', 'Map 0'],
];

export const MAP_GROUPS = [
  ['standard', 'Standard Maps', STANDARD_MAPS],
  ['legacy', 'Legacy Maps', LEGACY_MAPS],
  ['beginner', 'Beginner Maps', BEGINNER_MAPS],
];

export const ALL_MAPS = MAP_GROUPS.flatMap(([, , maps]) => maps);
export const DEFAULT_MAPS = STANDARD_MAPS;

function mapFilterGroupHtml([id, label], selectAllAction, selectNoneAction, { showLabel = true, showHeading = true } = {}) {
  return `<div class="map-filter-subgroup" data-map-group="${id}">
    ${showHeading ? `<div class="map-filter-subgroup-heading${showLabel ? '' : ' map-filter-subgroup-actions'}">${showLabel ? `<span class="filter-label">${label}</span>` : ''}<span class="map-select-all-none">(<span class="map-toggle-link" onclick="${selectAllAction}('${id}')">all</span> / <span class="map-toggle-link" onclick="${selectNoneAction}('${id}')">none</span>)</span></div>` : ''}
    <div class="chip-grid" data-map-group-chips="${id}"></div>
  </div>`;
}

function mapFilterExpandableGroupHtml([id, label, maps], selectAllAction, selectNoneAction) {
  return `<button type="button" class="map-filter-group-row" data-map-group-toggle="${id}" aria-expanded="false" aria-controls="map-filter-extra-${id}">
      <span class="map-filter-group-label-wrap"><span class="map-filter-group-label">${label}</span>
        <span class="map-filter-group-actions" aria-hidden="true">(<span class="map-toggle-link" onclick="event.stopPropagation(); ${selectAllAction}('${id}')">all</span> / <span class="map-toggle-link" onclick="event.stopPropagation(); ${selectNoneAction}('${id}')">none</span>)</span>
      </span>
      <span class="map-filter-group-count" data-map-group-count="${id}">0 / ${maps.length}</span>
      <span class="map-filter-group-mark" aria-hidden="true"></span>
    </button>
    <div class="map-filter-group-extra" id="map-filter-extra-${id}" data-map-group-extra="${id}" hidden>
      ${mapFilterGroupHtml([id, label], selectAllAction, selectNoneAction, { showHeading: false })}
    </div>`;
}

function mapFilterInnerHtml(selectAllAction = 'selectAllMaps', selectNoneAction = 'selectNoneMaps') {
  const [standard, ...additional] = MAP_GROUPS;
  return `<div class="map-filter-groups">
    ${mapFilterGroupHtml(standard, selectAllAction, selectNoneAction)}
    ${additional.map(group => mapFilterExpandableGroupHtml(group, selectAllAction, selectNoneAction)).join('')}
  </div>`;
}

export function mapFilterHtml({
  hostId = 'mapChips',
  selectAllAction = 'selectAllMaps',
  selectNoneAction = 'selectNoneMaps',
}) {
  return `<div id="${hostId}">${mapFilterInnerHtml(selectAllAction, selectNoneAction)}</div>`;
}

export function renderMapFilterChips(hostId, selectedMaps, toggleAction, selectAllAction = 'selectAllMaps', selectNoneAction = 'selectNoneMaps') {
  const host = typeof hostId === 'string' ? document.getElementById(hostId) : hostId;
  if (!host) return;
  const legacyHeading = host.previousElementSibling;
  if (legacyHeading?.querySelector('.map-select-all-none') &&
      legacyHeading.querySelector('.filter-label')?.textContent.trim() === 'Maps') {
    legacyHeading.remove();
  }
  host.classList.remove('chip-grid');
  host.classList.add('map-filter-host');
  if (!host.querySelector('[data-map-group-chips]')) host.innerHTML = mapFilterInnerHtml(selectAllAction, selectNoneAction);
  const groups = host.querySelector('.map-filter-groups');
  const updateGroupCounts = () => MAP_GROUPS.forEach(([groupId, , maps]) => {
    const count = host.querySelector(`[data-map-group-count="${groupId}"]`);
    if (count) count.textContent = `${host.querySelectorAll(`[data-map-group-chips="${groupId}"] .chip.active`).length} / ${maps.length}`;
  });
  if (groups && !groups.dataset.countBound) {
    groups.dataset.countBound = 'true';
    groups.addEventListener('click', () => requestAnimationFrame(updateGroupCounts), true);
  }
  groups?.querySelectorAll('[data-map-group-toggle]').forEach(toggle => {
    const groupId = toggle.dataset.mapGroupToggle;
    const extra = groups.querySelector(`[data-map-group-extra="${groupId}"]`);
    if (!extra || toggle.dataset.bound) return;
    toggle.dataset.bound = 'true';
    toggle.addEventListener('click', () => {
      const expanded = toggle.getAttribute('aria-expanded') !== 'true';
      toggle.setAttribute('aria-expanded', String(expanded));
      toggle.querySelector('.map-filter-group-actions')?.setAttribute('aria-hidden', String(!expanded));
      extra.hidden = !expanded;
      extra.classList.toggle('is-open', expanded);
    });
  });
  MAP_GROUPS.forEach(([groupId, , maps]) => {
    const chips = host.querySelector(`[data-map-group-chips="${groupId}"]`);
    if (!chips) return;
    chips.innerHTML = maps.map(([short, , full]) => {
      const escapedFull = String(full).replace(/&/g, '&amp;').replace(/"/g, '&quot;');
      const escapedTip = String(mapTooltipLabel(full)).replace(/&/g, '&amp;').replace(/"/g, '&quot;');
      return `<button class="chip maps-custom-tip ${selectedMaps.includes(full) ? 'active' : ''}" data-map="${escapedFull}" data-value="${escapedFull}" data-tip="${escapedTip}" onclick="${toggleAction}(this.dataset.map)">${short}</button>`;
    }).join('');
  });
  updateGroupCounts();
}

export function mapGroupNames(groupId) {
  return MAP_GROUPS.find(([id]) => id === groupId)?.[2].map(([, , full]) => full) || [];
}
