import { DEFAULT_PAGE_ID, PAGES } from './page-registry.js?v=20260922-filter-contract';
import { deltaColor, deltaRangeColor, orangeGreenRangeColor, synergyRangeColor } from './color-scales.js?v=20260812-9';
import { getRoutePageId, isRefreshPath, onRouteChange } from './router.js?v=20260819-1';
import {
  initializeDefaultSnapshots,
  preloadDefaultSnapshots,
  prioritizeSnapshotGroup,
  waitForDefaultSnapshotWarmup,
} from './snapshot-cache.js?v=20260921-filter-performance';
import {
  closeSidebarIfOpen,
  renderShell,
  scrollSideNav,
  setActiveNav,
  setNavHomeLock,
  setTopbarDataset,
  toggleNavCollapse,
  toggleSidebar,
} from './layout.js?v=20260819-4';

document.addEventListener('click', event => {
  if (!event.target.closest('#sidebar .apply-btn')) return;
  document.querySelectorAll('#sidebar .date-input[type="text"]').forEach(normalizeIsoDateInput);
}, true);

document.addEventListener('click', event => {
  if (!event.target.closest('#sidebar .reset-btn')) return;
  window.setTimeout(() => {
    const arena = document.getElementById('globalArenaOnly');
    const tournament = document.getElementById('globalTournamentOnly');
    if (arena) arena.checked = false;
    if (tournament) tournament.checked = false;
    window.resetGlobalStartingPositions?.();
    activeEloRangeLinkController?.reset();
  }, 0);
});

function prioritizeNavigationSnapshot(event) {
  const link = event.target.closest?.('.side-nav-link[data-page-id]');
  if (link) prioritizeSnapshotGroup(link.dataset.pageId);
}

document.addEventListener('pointerover', prioritizeNavigationSnapshot, { passive: true });
document.addEventListener('focusin', prioritizeNavigationSnapshot, { passive: true });

// App controller for the static multi-page dashboard.
//
// index.html only provides <div id="app">. This module renders the persistent
// shell once, chooses the active page from the hash route, injects that page's
// main/sidebar HTML, and calls the page lifecycle hooks.
//
// Page modules are loaded dynamically so future pages can be added without a
// build step. They still use inline onclick attributes inside their HTML strings,
// so each page is responsible for rebinding its own window handlers in mount().
const appRoot = document.getElementById('app');
const refreshPath = isRefreshPath();
let activePage = null;
let activePageId = null;
let currentDataset = 1;
let routeRenderToken = 0;
let rankFitFrame = 0;
let rankFitTimer = 0;
const minimumWarningTimers = new WeakMap();
const ELO_RANGE_LINK_SESSION_KEY = 'arknova:elo-range-link:v1';
const ELO_RANGE_WARNING = 'Using different player and opponent elo ranges can substantially skew results. Select asymmetric ranges with caution.';
let activeEloRangeLinkController = null;
let eloWarningReturnFocus = null;
let eloRangeLinkMemory = true;
const GLOBAL_MODE_FILTER_PAGES = new Set([
  'home', 'cards', 'opening-hand', 'endgames', 'maps', 'sponsor-endgames',
  'combos', 'actions', 'mw-action-cards', 'icons', 'predictors', 'build', 'conservation',
  'scoring', 'workers', 'players',
]);
const GLOBAL_FPA_FILTER_PAGES = new Set([
  ...GLOBAL_MODE_FILTER_PAGES,
  'records',
]);
const INITIAL_COMPLETED_FILTER_MODES = {
  home: 'optional',
  cards: 'optional',
  'opening-hand': 'optional',
  combos: 'optional',
  'mw-action-cards': 'optional',
  endgames: 'locked',
  'sponsor-endgames': 'locked',
  maps: 'locked',
  actions: 'locked',
  icons: 'locked',
  predictors: 'locked',
  build: 'optional',
  conservation: 'locked',
  scoring: 'locked',
  workers: 'locked',
  players: 'locked',
  records: 'hidden',
};

function globalModeToggle(id, label, kind) {
  return `<div class="toggle-row global-mode-toggle-row"><span class="toggle-label">${label}</span><label class="toggle"><input type="checkbox" id="${id}" data-mode-kind="${kind}" /><span class="toggle-track"></span></label></div>`;
}

function readEloRangeLinkPreference() {
  try {
    const stored = window.sessionStorage.getItem(ELO_RANGE_LINK_SESSION_KEY);
    if (stored === 'false') return false;
    if (stored === 'true') return true;
  } catch (_) {
    // sessionStorage can be unavailable in privacy-restricted contexts.
  }
  return eloRangeLinkMemory;
}

function writeEloRangeLinkPreference(linked) {
  eloRangeLinkMemory = Boolean(linked);
  try {
    window.sessionStorage.setItem(ELO_RANGE_LINK_SESSION_KEY, linked ? 'true' : 'false');
  } catch (_) {
    // The memory fallback still preserves the setting across route changes.
  }
}

function ensureEloRangeWarningModal() {
  let modal = document.getElementById('eloRangeWarningModal');
  if (modal) return modal;
  modal = document.createElement('div');
  modal.className = 'elo-range-warning-modal';
  modal.id = 'eloRangeWarningModal';
  modal.hidden = true;
  modal.setAttribute('role', 'alertdialog');
  modal.setAttribute('aria-modal', 'true');
  modal.setAttribute('aria-labelledby', 'eloRangeWarningMessage');
  modal.innerHTML = `<div class="elo-range-warning-card">
    <div id="eloRangeWarningMessage">${ELO_RANGE_WARNING}</div>
    <button type="button" id="eloRangeWarningOk">OK</button>
  </div>`;
  document.body.appendChild(modal);
  modal.querySelector('#eloRangeWarningOk')?.addEventListener('click', closeEloRangeWarningModal);
  modal.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      event.preventDefault();
      closeEloRangeWarningModal();
    } else if (event.key === 'Tab') {
      event.preventDefault();
      modal.querySelector('#eloRangeWarningOk')?.focus();
    }
  });
  return modal;
}

function openEloRangeWarningModal(returnFocus) {
  const modal = ensureEloRangeWarningModal();
  eloWarningReturnFocus = returnFocus || null;
  modal.hidden = false;
  window.requestAnimationFrame(() => modal.querySelector('#eloRangeWarningOk')?.focus());
}

function closeEloRangeWarningModal() {
  const modal = document.getElementById('eloRangeWarningModal');
  if (!modal || modal.hidden) return;
  modal.hidden = true;
  const returnFocus = eloWarningReturnFocus;
  eloWarningReturnFocus = null;
  returnFocus?.focus?.();
}

function findEloFilterGroup(sidebar, labelText) {
  const normalized = labelText.toLowerCase();
  return [...sidebar.querySelectorAll('.filter-label')]
    .find(label => label.textContent.trim().toLowerCase() === normalized)
    ?.closest('.filter-group') || null;
}

function installEloRangeLinking() {
  activeEloRangeLinkController?.destroy();
  activeEloRangeLinkController = null;

  const sidebar = document.getElementById('sidebar');
  if (!sidebar) return;
  const playerGroup = findEloFilterGroup(sidebar, 'player elo');
  const opponentGroup = findEloFilterGroup(sidebar, 'opponent elo');
  const playerInputs = [...(playerGroup?.querySelectorAll('.range-row input') || [])].slice(0, 2);
  const opponentInputs = [...(opponentGroup?.querySelectorAll('.range-row input') || [])].slice(0, 2);
  if (playerInputs.length !== 2 || opponentInputs.length !== 2) return;

  const row = document.createElement('label');
  row.className = 'elo-range-link-row';
  row.innerHTML = '<input type="checkbox" class="elo-range-link-checkbox" id="eloRangeLinkCheckbox" /><span>Use same Elo range for player and opponent</span>';
  opponentGroup.appendChild(row);
  const checkbox = row.querySelector('input');
  let synchronizing = false;

  const copyRange = (source, target) => {
    synchronizing = true;
    target.forEach((input, index) => { input.value = source[index].value; });
    synchronizing = false;
  };
  const onPlayerInput = event => {
    if (!checkbox.checked || synchronizing) return;
    const index = playerInputs.indexOf(event.target);
    if (index >= 0) opponentInputs[index].value = event.target.value;
  };
  const onOpponentInput = event => {
    if (!checkbox.checked || synchronizing) return;
    const index = opponentInputs.indexOf(event.target);
    if (index >= 0) playerInputs[index].value = event.target.value;
  };
  const onLinkChange = () => {
    writeEloRangeLinkPreference(checkbox.checked);
    if (checkbox.checked) copyRange(playerInputs, opponentInputs);
    else openEloRangeWarningModal(checkbox);
  };

  playerInputs.forEach(input => input.addEventListener('input', onPlayerInput));
  opponentInputs.forEach(input => input.addEventListener('input', onOpponentInput));
  checkbox.addEventListener('change', onLinkChange);
  checkbox.checked = readEloRangeLinkPreference();
  if (checkbox.checked) copyRange(playerInputs, opponentInputs);

  activeEloRangeLinkController = {
    reset() {
      checkbox.checked = true;
      writeEloRangeLinkPreference(true);
      copyRange(playerInputs, opponentInputs);
    },
    synchronize() {
      if (checkbox.checked) copyRange(playerInputs, opponentInputs);
    },
    destroy() {
      playerInputs.forEach(input => input.removeEventListener('input', onPlayerInput));
      opponentInputs.forEach(input => input.removeEventListener('input', onOpponentInput));
      checkbox.removeEventListener('change', onLinkChange);
    },
  };
}

function installGlobalModeFilters(pageId) {
  if (!GLOBAL_MODE_FILTER_PAGES.has(pageId)) return;
  const sidebar = document.getElementById('sidebar');
  const actions = sidebar?.querySelector('.filter-action-stack');
  if (!sidebar || !actions) return;
  const players = pageId === 'players';
  const wrapper = document.createElement('div');
  wrapper.className = 'global-mode-filter-shell';
  // Page sidebars reserve their final filter section immediately before the
  // last divider and Apply button. Keeping this group there means it can sit
  // directly below a visible Completed-games toggle without an extra divider,
  // while pages without that toggle still get one normal final section.
  wrapper.innerHTML = `<div class="filter-group global-mode-filter-group">
    ${players ? '' : globalModeToggle('globalArenaOnly', 'Arena games only', 'arena')}
    ${globalModeToggle('globalTournamentOnly', 'Tournament games only', 'tournament')}
  </div>`;
  let finalDivider = actions.previousElementSibling?.matches('hr.divider')
    ? actions.previousElementSibling
    : null;
  if (!finalDivider) {
    finalDivider = document.createElement('hr');
    finalDivider.className = 'divider global-mode-final-divider';
    actions.parentNode.insertBefore(finalDivider, actions);
  }
  const anchor = finalDivider || actions;
  const leadingDivider = document.createElement('hr');
  leadingDivider.className = 'divider global-mode-filter-divider';
  anchor.parentNode.insertBefore(leadingDivider, anchor);
  anchor.parentNode.insertBefore(wrapper, anchor);
  wrapper.addEventListener('change', event => {
    const input = event.target.closest('input[data-mode-kind]');
    if (!input) return;
    if (input.checked && input.dataset.modeKind === 'arena') {
      const other = document.getElementById('globalTournamentOnly');
      if (other) other.checked = false;
    }
    if (input.checked && input.dataset.modeKind === 'tournament') {
      const other = document.getElementById('globalArenaOnly');
      if (other) other.checked = false;
    }
    window.dispatchEvent(new CustomEvent('arknova:global-mode-filter-change', {
      detail: { kind: input.dataset.modeKind, checked: input.checked },
    }));
  });
  window.requestAnimationFrame(() => window.syncGlobalModeFilterGrouping?.());
}

function installGlobalFpaFilter(pageId) {
  if (!GLOBAL_FPA_FILTER_PAGES.has(pageId)) return;
  const sidebar = document.getElementById('sidebar');
  const actions = sidebar?.querySelector('.filter-action-stack');
  if (!sidebar || !actions || sidebar.querySelector('.global-fpa-filter-shell')) return;

  // The public filter label is "Starting position"; FPA remains the internal
  // shorthand/API concept. Players places this section after Last X games so
  // the sidebar follows the same population-then-window order as the query.
  const dateLabel = [...sidebar.querySelectorAll('.filter-label')].find(label => (
    label.textContent.trim().toLowerCase() === 'date range'
  ));
  const dateGroup = dateLabel?.closest('.filter-group') || null;
  const lastXLabel = [...sidebar.querySelectorAll('.filter-label')].find(label => (
    label.textContent.trim().toLowerCase() === 'last x games'
  ));
  const lastXGroup = lastXLabel?.closest('.filter-group') || null;
  const orderAnchorGroup = lastXGroup || dateGroup;
  const fallbackAnchor = sidebar.querySelector('.global-mode-filter-shell')
    || sidebar.querySelector('.records-mode-filters')
    || actions;

  const shell = document.createElement('div');
  shell.className = 'global-fpa-filter-shell';
  shell.innerHTML = `<div class="filter-group global-fpa-filter-group">
    <span class="filter-label">Starting position</span>
    <div class="global-fpa-buttons" role="group" aria-label="Starting position">
      <button type="button" class="chip global-fpa-button active" data-starting-position="First player" aria-pressed="true">First player</button>
      <button type="button" class="chip global-fpa-button active" data-starting-position="Second player" aria-pressed="true">Second player</button>
    </div>
  </div>`;

  let leadingDivider = orderAnchorGroup?.nextElementSibling?.matches('hr.divider')
    ? orderAnchorGroup.nextElementSibling
    : null;
  if (!leadingDivider) {
    leadingDivider = document.createElement('hr');
    leadingDivider.className = 'divider global-fpa-leading-divider';
    // Some pages own a Completed group immediately after Date Range rather
    // than an explicit divider. Insert Starting position before that group so
    // it cannot split the Completed/Arena/Tournament block.
    const insertionTarget = orderAnchorGroup?.nextElementSibling || fallbackAnchor;
    insertionTarget.parentNode.insertBefore(leadingDivider, insertionTarget);
  } else {
    leadingDivider.classList.add('global-fpa-leading-divider');
  }
  const parent = leadingDivider.parentNode;
  parent.insertBefore(shell, leadingDivider.nextSibling);
  const trailingDivider = document.createElement('hr');
  trailingDivider.className = 'divider global-fpa-trailing-divider';
  parent.insertBefore(trailingDivider, shell.nextSibling);

  shell.addEventListener('click', event => {
    const button = event.target.closest('.global-fpa-button');
    if (!button) return;
    const buttons = [...shell.querySelectorAll('.global-fpa-button')];
    const activeCount = buttons.filter(item => item.classList.contains('active')).length;
    if (button.classList.contains('active') && activeCount === 1) return;
    button.classList.toggle('active');
    button.setAttribute('aria-pressed', button.classList.contains('active') ? 'true' : 'false');
  });
}

function collapseAdjacentSidebarDividers() {
  const sidebar = document.getElementById('sidebar');
  if (!sidebar) return;
  const dividers = [...sidebar.querySelectorAll('hr.divider')];
  dividers.forEach(divider => {
    const previous = divider.previousElementSibling;
    if (!previous?.matches('hr.divider')) return;
    const previousVisible = !previous.hidden && window.getComputedStyle(previous).display !== 'none';
    const currentVisible = !divider.hidden && window.getComputedStyle(divider).display !== 'none';
    if (previousVisible && currentVisible) divider.remove();
  });
}

// The Apply control is its own sticky footer and supplies the visual boundary
// above itself. Remove any page-owned or injected divider immediately before
// it so the mode-toggle section does not acquire a redundant final separator.
function removeFilterFooterDivider() {
  const actions = document.querySelector('#sidebar .filter-action-stack');
  const divider = actions?.previousElementSibling;
  if (divider?.matches('hr.divider')) divider.remove();
}

window.collapseAdjacentSidebarDividers = collapseAdjacentSidebarDividers;
window.removeFilterFooterDivider = removeFilterFooterDivider;

function completedFilterGroup() {
  const label = [...document.querySelectorAll('#sidebar .toggle-label')].find(item => (
    item.textContent.trim() === 'Completed games only'
  ));
  return label?.closest('.filter-group') || null;
}

// Keep the compact table-header label consistent with the dashboard's
// user-facing EV terminology while leaving the underlying elo_delta field and
// explanatory tooltip attributes unchanged. Elo-delta headers are presented as
// bare "EV" (so source labels such as "Elo Δ" become "EV"). Headers are
// rendered by both the static card tables and many async page modules, so
// observe the shared canvas instead of duplicating replacements in each module.
let eloHeaderObserver = null;
let tableViewportObserver = null;
let tableViewportFrame = 0;

function isVisibleTableScroll(scroll) {
  if (!scroll?.querySelector(':scope > table')) return false;
  if (scroll.closest('[hidden]')) return false;
  return scroll.getClientRects().length > 0
    && window.getComputedStyle(scroll).display !== 'none';
}

function syncTableViewportLayout() {
  const main = document.getElementById('pageMain');
  if (!main) return;

  const scrolls = [...main.querySelectorAll('.table-scroll')].filter(isVisibleTableScroll);
  const desiredScrolls = new Set(scrolls);
  const desiredHosts = new Set();
  const desiredColumns = new Set();

  scrolls.forEach(scroll => {
    let node = scroll.parentElement;
    while (node && node !== main) {
      desiredHosts.add(node);
      const display = window.getComputedStyle(node).display;
      if (node.classList.contains('dashboard-table-column') || display === 'block' || display === 'flow-root') {
        desiredColumns.add(node);
      }
      node = node.parentElement;
    }
  });

  main.querySelectorAll('.dashboard-table-scroll').forEach(scroll => {
    if (!desiredScrolls.has(scroll)) scroll.classList.remove('dashboard-table-scroll');
  });
  main.querySelectorAll('.dashboard-table-host').forEach(host => {
    if (!desiredHosts.has(host)) {
      host.classList.remove('dashboard-table-host', 'dashboard-table-column');
    }
  });
  scrolls.forEach(scroll => scroll.classList.add('dashboard-table-scroll'));
  desiredHosts.forEach(host => host.classList.add('dashboard-table-host'));
  desiredColumns.forEach(host => host.classList.add('dashboard-table-column'));

  const active = scrolls.length > 0;
  document.documentElement.classList.toggle('dashboard-table-viewport', active);
  document.body.classList.toggle('dashboard-table-viewport', active);
}

function scheduleTableViewportLayout() {
  window.cancelAnimationFrame(tableViewportFrame);
  tableViewportFrame = window.requestAnimationFrame(syncTableViewportLayout);
}

function resetTableViewportLayout() {
  tableViewportObserver?.disconnect();
  tableViewportObserver = null;
  window.cancelAnimationFrame(tableViewportFrame);
  tableViewportFrame = 0;
  document.documentElement.classList.remove('dashboard-table-viewport');
  document.body.classList.remove('dashboard-table-viewport');
  document.querySelectorAll('.dashboard-table-scroll').forEach(scroll => scroll.classList.remove('dashboard-table-scroll'));
  document.querySelectorAll('.dashboard-table-host').forEach(host => {
    host.classList.remove('dashboard-table-host', 'dashboard-table-column');
  });
}

function installTableViewportLayout() {
  tableViewportObserver?.disconnect();
  const main = document.getElementById('pageMain');
  if (!main) return;
  scheduleTableViewportLayout();
  tableViewportObserver = new MutationObserver(scheduleTableViewportLayout);
  tableViewportObserver.observe(main, {
    subtree: true,
    childList: true,
    attributes: true,
    attributeFilter: ['class', 'hidden', 'style'],
  });
}

function normalizeEloDeltaHeaders(root = document) {
  root.querySelectorAll?.('#pageMain th').forEach(header => {
    const walker = document.createTreeWalker(header, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
      if (node.nodeValue.includes('Δ')) node.nodeValue = node.nodeValue.replaceAll('Δ', 'EV');
      if (/\bElo\s+EV\b/i.test(node.nodeValue)) {
        node.nodeValue = node.nodeValue.replace(/\bElo\s+EV\b/gi, 'EV');
      }
      if (/\bEV\s+Elo\b/i.test(node.nodeValue)) {
        node.nodeValue = node.nodeValue.replace(/\bEV\s+Elo\b/gi, 'EV');
      }
      node = walker.nextNode();
    }
  });
}

const SORT_ARROW_PATHS = {
  asc: 'M4 11V1M1.5 3.5 4 1l2.5 2.5',
  desc: 'M4 1v10M1.5 8.5 4 11l2.5-2.5',
  none: 'M4 1v10M1.5 3.5 4 1l2.5 2.5M1.5 8.5 4 11l2.5-2.5',
};

function sortArrowDirection(glyph) {
  if (/[↑▲]/u.test(glyph)) return 'asc';
  if (/[↓▼]/u.test(glyph)) return 'desc';
  return 'none';
}

function normalizeSortableHeaders(root = document) {
  root.querySelectorAll?.('#pageMain th .sort-arrow').forEach(arrow => {
    const header = arrow.closest('th');
    if (!header) return;

    // Older tables render the label as a text node followed by a direct arrow.
    // Wrap that pair so both elements are centred by one flex container rather
    // than independently following font baselines. Any popup after the arrow
    // remains a direct child of the header and keeps its positioning context.
    if (arrow.parentElement === header) {
      const content = document.createElement('span');
      content.className = 'sortable-header-content';
      const label = document.createElement('span');
      label.className = 'sortable-header-label';
      while (header.firstChild && header.firstChild !== arrow) {
        label.appendChild(header.firstChild);
      }
      header.insertBefore(content, arrow);
      content.append(label, arrow);
    }

    const glyph = arrow.textContent.trim();
    if (!glyph && arrow.querySelector('svg')) return;
    const direction = sortArrowDirection(glyph);
    arrow.classList.add('vector-sort-arrow');
    arrow.setAttribute('aria-hidden', 'true');
    arrow.innerHTML = `<svg viewBox="0 0 8 12" focusable="false"><path d="${SORT_ARROW_PATHS[direction]}" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  });
}

function normalizeTableHeaders(root = document) {
  normalizeEloDeltaHeaders(root);
  normalizeSortableHeaders(root);
}

function installEloDeltaHeaderNormalization() {
  eloHeaderObserver?.disconnect();
  const main = document.getElementById('pageMain');
  if (!main) return;
  normalizeTableHeaders(main);
  eloHeaderObserver = new MutationObserver(() => normalizeTableHeaders(main));
  eloHeaderObserver.observe(main, { subtree: true, childList: true, characterData: true });
}

function createCompletedFilterGroup() {
  const sidebar = document.getElementById('sidebar');
  if (!sidebar) return null;
  const modeAnchor = sidebar.querySelector('.global-mode-filter-shell')
    || sidebar.querySelector('.records-mode-filters')
    || sidebar.querySelector('.filter-action-stack');
  if (!modeAnchor?.parentNode) return null;
  const group = document.createElement('div');
  group.className = 'filter-group global-completed-filter-group';
  group.dataset.completedInjected = 'true';
  group.innerHTML = `<div class="toggle-row"><span class="toggle-label">Completed games only</span>
    <label class="toggle"><input type="checkbox" id="globalCompletedOnly" /><span class="toggle-track"></span></label></div>`;
  modeAnchor.parentNode.insertBefore(group, modeAnchor);
  return group;
}

function setCompletedLock(group, locked) {
  const row = group?.querySelector('.toggle-row');
  const input = group?.querySelector('input[type="checkbox"]');
  const toggle = group?.querySelector('.toggle');
  if (!row || !input || !toggle) return;
  let lock = row.querySelector('.completed-lock-indicator');
  if (locked && !lock) {
    lock = document.createElement('span');
    lock.className = 'completed-lock-indicator';
    lock.setAttribute('role', 'img');
    lock.setAttribute('aria-label', 'This view always uses completed games.');
    lock.title = 'This view always uses completed games.';
    lock.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 10V7a5 5 0 0 1 10 0v3m-11 0h12v10H6V10Zm3 0h6V7a3 3 0 0 0-6 0v3Z" fill="currentColor"/></svg>';
    toggle.before(lock);
  } else if (!locked) {
    lock?.remove();
  }
  if (locked && !input.disabled) input.dataset.optionalChecked = input.checked ? 'true' : 'false';
  if (!locked && input.disabled && input.dataset.optionalChecked) {
    input.checked = input.dataset.optionalChecked === 'true';
  }
  input.checked = locked ? true : input.checked;
  input.disabled = locked;
  toggle.classList.toggle('is-locked', locked);
}

window.setCompletedFilterMode = mode => {
  const normalized = ['optional', 'locked', 'hidden'].includes(mode) ? mode : 'optional';
  let group = completedFilterGroup();
  if (!group && normalized !== 'hidden') group = createCompletedFilterGroup();
  if (!group) return;
  const hidden = normalized === 'hidden';
  group.hidden = hidden;
  group.classList.toggle('is-hidden', hidden);
  if (!hidden) setCompletedLock(group, normalized === 'locked');
  window.syncGlobalModeFilterGrouping?.();
};

window.getGlobalStartingPositions = () => [...document.querySelectorAll('.global-fpa-button.active')]
  .map(button => button.dataset.startingPosition)
  .filter(Boolean);

window.resetGlobalStartingPositions = () => {
  document.querySelectorAll('.global-fpa-button').forEach(button => {
    button.classList.add('active');
    button.setAttribute('aria-pressed', 'true');
  });
};

window.syncGlobalModeFilterGrouping = () => {
  const wrapper = document.querySelector('.global-mode-filter-shell');
  const leadingDivider = document.querySelector('.global-mode-filter-divider');
  if (!wrapper || !leadingDivider) return;
  // Match the exact toggle label before resolving its group. Some sidebars
  // nest the Performance-only Completed toggle inside an Arena-season group;
  // searching group descendants made that outer group look completed even
  // while the actual toggle was hidden.
  const completedLabel = [...document.querySelectorAll('#sidebar .toggle-label')].find(label => (
    label.textContent.trim() === 'Completed games only'
  ));
  const completedGroup = completedLabel?.closest('.filter-group') || null;
  const completedVisible = Boolean(completedGroup)
    && !completedGroup.hidden
    && !completedGroup.classList.contains('is-hidden')
    && window.getComputedStyle(completedGroup).display !== 'none';
  const existingSectionDivider = completedGroup?.previousElementSibling?.matches('hr.divider')
    && !completedGroup.previousElementSibling.classList.contains('is-hidden')
    && window.getComputedStyle(completedGroup.previousElementSibling).display !== 'none';
  completedGroup?.classList.toggle('global-mode-completed-host', completedVisible);
  wrapper.classList.toggle('is-joined', completedVisible);
  const injectedCompleted = completedGroup?.dataset.completedInjected === 'true';
  leadingDivider.hidden = injectedCompleted && completedVisible
    ? false
    : wrapper.hidden || completedVisible || Boolean(existingSectionDivider);
};

window.setGlobalModeFilterVisibility = ({ arena = true, tournament = true } = {}) => {
  const arenaRow = document.getElementById('globalArenaOnly')?.closest('.global-mode-toggle-row');
  const tournamentRow = document.getElementById('globalTournamentOnly')?.closest('.global-mode-toggle-row');
  if (arenaRow) arenaRow.hidden = !arena;
  if (tournamentRow) tournamentRow.hidden = !tournament;
  const group = document.querySelector('.global-mode-filter-shell');
  if (group) group.hidden = !arena && !tournament;
  window.syncGlobalModeFilterGrouping?.();
};

window.setGlobalTournamentOnly = value => {
  const input = document.getElementById('globalTournamentOnly');
  if (!input) return;
  input.checked = Boolean(value);
  if (input.checked) {
    const arena = document.getElementById('globalArenaOnly');
    if (arena) arena.checked = false;
  }
};

window.hasActiveGlobalModeFilter = () => Boolean(
  document.getElementById('globalArenaOnly')?.checked
  || document.getElementById('globalTournamentOnly')?.checked
  || window.getGlobalStartingPositions?.().length === 1
);

// Home owns a tiny synchronous bootstrap. All other defaults begin warming as
// soon as the shell module loads, without delaying Home's first paint.
if (!refreshPath) void initializeDefaultSnapshots().catch(() => {});

async function renderCurrentRoute() {
  // Dynamic imports can resolve out of order if the hash changes quickly.
  // Only the newest render token is allowed to touch the DOM.
  const renderToken = ++routeRenderToken;
  renderShell(appRoot);

  const pageId = getRoutePageId(PAGES, DEFAULT_PAGE_ID);
  const pageDef = PAGES[pageId] || PAGES[DEFAULT_PAGE_ID];
  if (pageDef.id !== 'home' && pageDef.id !== 'refresh') {
    await waitForDefaultSnapshotWarmup(120);
  }
  const page = await pageDef.load();
  if (renderToken !== routeRenderToken) return;

  // Always let the outgoing page detach listeners / invalidate async work before
  // the new page's DOM is injected. This is what prevents cross-page state bleed.
  if (activePage && activePage.unmount) activePage.unmount();
  resetTableViewportLayout();
  activeEloRangeLinkController?.destroy();
  activeEloRangeLinkController = null;
  activePageId = pageDef.id;
  document.body.classList.toggle('refresh-route-active', activePageId === 'refresh');
  setActiveNav(activePageId);
  setNavHomeLock(activePageId === 'home');
  closeSidebarIfOpen();
  activePage = page;

  document.title = page.title ? `${page.title} | Ark Nova Statistics` : 'Ark Nova Statistics';
  document.getElementById('pageMain').innerHTML = page.mainHtml || '';
  document.getElementById('sidebar').innerHTML = page.sidebarHtml || '';
  if (activePageId !== 'refresh') {
    enhanceIsoDateInputs();
    installGlobalModeFilters(activePageId);
    installGlobalFpaFilter(activePageId);
    installEloRangeLinking();
    const initialCompletedMode = INITIAL_COMPLETED_FILTER_MODES[activePageId];
      if (initialCompletedMode) window.setCompletedFilterMode(initialCompletedMode);
      collapseAdjacentSidebarDividers();
      removeFilterFooterDivider();
      setTopbarDataset(currentDataset);
  }

  if (page.mount) page.mount({ dataset: currentDataset, pageId: activePageId });
  installEloDeltaHeaderNormalization();
  installTableViewportLayout();
  window.requestAnimationFrame(() => activeEloRangeLinkController?.synchronize());
  // Let the active page claim the network first; background warmup begins from
  // an idle callback after its foreground request has been started.
  if (activePageId !== 'refresh') preloadDefaultSnapshots(pageDef.id);
  scheduleRankCellFit();
}

// Rank columns are intentionally narrow. Preserve their normal typography until
// a large rank would clip, then reduce only that cell enough to fit.
function scheduleRankCellFit() {
  window.cancelAnimationFrame(rankFitFrame);
  rankFitFrame = window.requestAnimationFrame(() => {
    // Dynamic table rows and their percentage widths settle one frame after
    // insertion. Measuring on the following frame avoids a zero/old cell width.
    rankFitFrame = window.requestAnimationFrame(() => {
      document.querySelectorAll('#pageMain .rank-cell').forEach(cell => {
        cell.style.removeProperty('font-size');
        if (!cell.clientWidth || cell.scrollWidth <= cell.clientWidth) return;
        let size = Number.parseFloat(window.getComputedStyle(cell).fontSize) || 13;
        while (size > 8 && cell.scrollWidth > cell.clientWidth) {
          size -= 0.5;
          cell.style.fontSize = `${size}px`;
        }
      });
    });
  });
}

const rankObserver = new MutationObserver(() => {
  scheduleRankCellFit();
  window.clearTimeout(rankFitTimer);
  rankFitTimer = window.setTimeout(scheduleRankCellFit, 80);
});
rankObserver.observe(appRoot, { childList: true, subtree: true });
window.addEventListener('resize', scheduleRankCellFit);

function enhanceIsoDateInputs() {
  document.querySelectorAll('#sidebar .date-input[type="text"]').forEach(input => {
    if (input.closest('.date-input-shell')) return;
    const shell = document.createElement('div');
    shell.className = 'date-input-shell';
    input.parentNode.insertBefore(shell, input);
    shell.appendChild(input);

    const picker = document.createElement('input');
    picker.type = 'date';
    picker.className = 'date-picker-native';
    picker.tabIndex = -1;
    picker.min = '2023-01-01';
    picker.setAttribute('aria-label', 'Open calendar');

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'date-picker-btn';
    button.title = 'Open calendar';
    button.setAttribute('aria-label', 'Open calendar');
    button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="5" width="16" height="15" rx="2"></rect><path d="M8 3v4M16 3v4M4 10h16"></path></svg>';

    const syncPicker = () => {
      picker.value = /^\d{4}-\d{2}-\d{2}$/.test(input.value) ? input.value : '';
    };
    let normalizeTimer = null;
    input.addEventListener('input', () => {
      syncPicker();
      window.clearTimeout(normalizeTimer);
      normalizeTimer = window.setTimeout(() => normalizeIsoDateInput(input), 500);
    });
    input.addEventListener('blur', () => normalizeIsoDateInput(input));
    picker.addEventListener('change', () => {
      input.value = picker.value;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
    });
    button.addEventListener('click', () => {
      normalizeIsoDateInput(input);
      syncPicker();
      if (picker.showPicker) picker.showPicker();
      else picker.click();
    });

    shell.appendChild(picker);
    shell.appendChild(button);
  });
}

function normalizeIsoDateInput(input) {
  const value = input.value.trim();
  if (!value) return;
  const match = value.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  if (!match) return;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (month < 1 || month > 12 || day < 1 || day > 31) return;
  const parsed = new Date(Date.UTC(year, month - 1, day));
  if (parsed.getUTCFullYear() !== year
      || parsed.getUTCMonth() !== month - 1
      || parsed.getUTCDate() !== day) return;
  input.value = `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

function setDataset(value, button) {
  // Dataset is global topbar state shared by every page: 1 = Marine Worlds,
  // 0 = Base. The active page decides how to reload/render its own data.
  currentDataset = Number(value) === 0 ? 0 : 1;
  setTopbarDataset(currentDataset);
  if (activePage && activePage.setDataset) activePage.setDataset(currentDataset);
}

// Static Arena seasons carry their own ruleset. The Players module requests a
// global dataset change through this event so the topbar and app controller
// stay authoritative without coupling the page module back to this file.
window.addEventListener('arknova:set-dataset', event => {
  if (event?.detail?.value === undefined) return;
  setDataset(event.detail.value);
});

function setMinimumPlaysWarning(input, shouldWarn) {
  if (!input) return;
  const existing = minimumWarningTimers.get(input);
  if (existing) window.clearTimeout(existing);
  input.classList.toggle('minimum-plays-warning', Boolean(shouldWarn));
  if (!shouldWarn) return;
  const timer = window.setTimeout(() => {
    input.classList.remove('minimum-plays-warning');
    minimumWarningTimers.delete(input);
  }, 5000);
  minimumWarningTimers.set(input, timer);
}

document.addEventListener('focusin', event => {
  if (!event.target.matches('.min-plays-input')) return;
  setMinimumPlaysWarning(event.target, false);
});

function renderDeltaCiTooltip(cell) {
  const tooltip = document.getElementById('col-tooltip');
  if (!tooltip) return;
  const count = cell.dataset.ciN === '' ? Number.NaN : Number(cell.dataset.ciN);
  const low = cell.dataset.ciLow === '' ? Number.NaN : Number(cell.dataset.ciLow);
  const high = cell.dataset.ciHigh === '' ? Number.NaN : Number(cell.dataset.ciHigh);
  const colorMin = cell.dataset.ciColorMin === '' ? Number.NaN : Number(cell.dataset.ciColorMin);
  const colorMax = cell.dataset.ciColorMax === '' ? Number.NaN : Number(cell.dataset.ciColorMax);
  const appendPopulation = () => {
    if (!cell.dataset.ciPopulation) return;
    const note = document.createElement('div');
    note.className = 'ci-tooltip-population';
    note.textContent = cell.dataset.ciPopulation;
    tooltip.appendChild(note);
  };
  if (!Number.isFinite(low) || !Number.isFinite(high) || !Number.isFinite(count) || count < 2) {
    tooltip.innerHTML = '<strong>95% confidence interval unavailable</strong>';
    appendPopulation();
    return;
  }
  const signed = value => `${value >= 0 ? '+' : ''}${value.toFixed(3)}`;
  const color = value => Number.isFinite(colorMin) && Number.isFinite(colorMax)
    ? (cell.dataset.ciColorScale === 'orange-green'
      ? orangeGreenRangeColor(value, colorMin, colorMax)
      : cell.dataset.ciColorScale === 'synergy'
        ? synergyRangeColor(value, colorMin, colorMax)
        : deltaRangeColor(value, colorMin, colorMax))
    : deltaColor(value);
  const synergyCrossesZero = cell.dataset.ciColorScale === 'synergy' && low < 0 && high > 0;
  const zeroPosition = synergyCrossesZero ? (-low / (high - low)) * 100 : 50;
  tooltip.innerHTML = `
    <div class="ci-tooltip-title">95% confidence interval</div>
    <div class="ci-tooltip-visual">
      <div class="ci-tooltip-line${synergyCrossesZero ? ' ci-tooltip-line-crosses-zero' : ''}"
           style="--ci-low-color:${color(low)};--ci-high-color:${color(high)};--ci-zero-color:${color(0)};--ci-zero-position:${zeroPosition}%"></div>
      <div class="ci-tooltip-bounds">
        <span>${signed(low)}</span>
        <span>${signed(high)}</span>
      </div>
    </div>`;
  appendPopulation();
}

function positionDeltaCiTooltip(event) {
  const tooltip = document.getElementById('col-tooltip');
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

document.addEventListener('mouseover', event => {
  const cell = event.target.closest?.('#pageMain .delta-ci-cell');
  const tooltip = document.getElementById('col-tooltip');
  if (!cell || !tooltip) return;
  renderDeltaCiTooltip(cell);
  tooltip.style.display = 'block';
  positionDeltaCiTooltip(event);
});

document.addEventListener('mousemove', event => {
  const tooltip = document.getElementById('col-tooltip');
  if (!tooltip || tooltip.style.display === 'none') return;
  const cell = event.target.closest?.('#pageMain .delta-ci-cell');
  if (!cell) return;
  positionDeltaCiTooltip(event);
});

document.addEventListener('mouseout', event => {
  const cell = event.target.closest?.('#pageMain .delta-ci-cell');
  if (!cell || cell.contains(event.relatedTarget)) return;
  const tooltip = document.getElementById('col-tooltip');
  if (tooltip) tooltip.style.display = 'none';
});

// Sidebar map chips use the same custom tooltip surface as Maps table headers.
// Keep this shell-level handler so shared filter markup works on pages whose
// table module does not otherwise bind a maps-custom-tip listener.
document.addEventListener('mouseover', event => {
  const source = event.target.closest?.('.map-filter-host .maps-custom-tip, .records-map-filter .maps-custom-tip');
  const tooltip = document.getElementById('col-tooltip');
  if (!source || !tooltip || !source.dataset.tip) return;
  tooltip.textContent = source.dataset.tip;
  tooltip.style.display = 'block';
  positionDeltaCiTooltip(event);
});

document.addEventListener('mousemove', event => {
  const source = event.target.closest?.('.map-filter-host .maps-custom-tip, .records-map-filter .maps-custom-tip');
  const tooltip = document.getElementById('col-tooltip');
  if (!source || !tooltip || tooltip.style.display === 'none') return;
  positionDeltaCiTooltip(event);
});

document.addEventListener('mouseout', event => {
  const source = event.target.closest?.('.map-filter-host .maps-custom-tip, .records-map-filter .maps-custom-tip');
  if (!source || source.contains(event.relatedTarget)) return;
  const tooltip = document.getElementById('col-tooltip');
  if (tooltip) tooltip.style.display = 'none';
});

// Header controls live in layout.js markup, so they are intentionally global.
// Page-specific globals are rebound by each page module on mount().
window.setTab = setDataset;
window.toggleSidebar = toggleSidebar;
window.toggleNavCollapse = toggleNavCollapse;
window.scrollSideNav = scrollSideNav;
window.setMinimumPlaysWarning = setMinimumPlaysWarning;

onRouteChange(renderCurrentRoute);
renderCurrentRoute();
