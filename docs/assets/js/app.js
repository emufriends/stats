import { DEFAULT_PAGE_ID, PAGES } from './page-registry.js?v=20260713-1';
import { deltaColor, deltaRangeColor, orangeGreenRangeColor } from './color-scales.js?v=20260710-3';
import { getRoutePageId, onRouteChange } from './router.js?v=20260629-13';
import {
  initializeDefaultSnapshots,
  preloadDefaultSnapshots,
  prioritizeSnapshotGroup,
  waitForDefaultSnapshotWarmup,
} from './snapshot-cache.js?v=20260713-1';
import {
  closeSidebarIfOpen,
  renderShell,
  scrollSideNav,
  setActiveNav,
  setNavHomeLock,
  setTopbarDataset,
  toggleNavCollapse,
  toggleSidebar,
} from './layout.js?v=20260712-3';

document.addEventListener('click', event => {
  if (!event.target.closest('#sidebar .apply-btn')) return;
  document.querySelectorAll('#sidebar .date-input[type="text"]').forEach(normalizeIsoDateInput);
}, true);

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
let activePage = null;
let activePageId = null;
let currentDataset = 1;
let routeRenderToken = 0;
let rankFitFrame = 0;
let rankFitTimer = 0;
const minimumWarningTimers = new WeakMap();

// Home owns a tiny synchronous bootstrap. All other defaults begin warming as
// soon as the shell module loads, without delaying Home's first paint.
void initializeDefaultSnapshots().catch(() => {});

async function renderCurrentRoute() {
  // Dynamic imports can resolve out of order if the hash changes quickly.
  // Only the newest render token is allowed to touch the DOM.
  const renderToken = ++routeRenderToken;
  renderShell(appRoot);

  const pageId = getRoutePageId(PAGES, DEFAULT_PAGE_ID);
  const pageDef = PAGES[pageId] || PAGES[DEFAULT_PAGE_ID];
  if (pageDef.id !== 'home') await waitForDefaultSnapshotWarmup(120);
  const page = await pageDef.load();
  if (renderToken !== routeRenderToken) return;

  // Always let the outgoing page detach listeners / invalidate async work before
  // the new page's DOM is injected. This is what prevents cross-page state bleed.
  if (activePage && activePage.unmount) activePage.unmount();
  activePageId = pageDef.id;
  setActiveNav(activePageId);
  setNavHomeLock(activePageId === 'home');
  closeSidebarIfOpen();
  activePage = page;

  document.title = page.title ? `${page.title} | Ark Nova Statistics` : 'Ark Nova Statistics';
  document.getElementById('pageMain').innerHTML = page.mainHtml || '';
  document.getElementById('sidebar').innerHTML = page.sidebarHtml || '';
  enhanceIsoDateInputs();
  setTopbarDataset(currentDataset);

  if (page.mount) page.mount({ dataset: currentDataset, pageId: activePageId });
  // Let the active page claim the network first; background warmup begins from
  // an idle callback after its foreground request has been started.
  preloadDefaultSnapshots(pageDef.id);
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
  if (!Number.isFinite(low) || !Number.isFinite(high) || !Number.isFinite(count) || count < 2) {
    tooltip.innerHTML = '<strong>95% confidence interval unavailable</strong>';
    return;
  }
  const signed = value => `${value >= 0 ? '+' : ''}${value.toFixed(3)}`;
  const color = value => Number.isFinite(colorMin) && Number.isFinite(colorMax)
    ? (cell.dataset.ciColorScale === 'orange-green'
      ? orangeGreenRangeColor(value, colorMin, colorMax)
      : deltaRangeColor(value, colorMin, colorMax))
    : deltaColor(value);
  tooltip.innerHTML = `
    <div class="ci-tooltip-title">95% confidence interval</div>
    <div class="ci-tooltip-visual">
      <div class="ci-tooltip-line"
           style="--ci-low-color:${color(low)};--ci-high-color:${color(high)}"></div>
      <div class="ci-tooltip-bounds">
        <span>${signed(low)}</span>
        <span>${signed(high)}</span>
      </div>
    </div>`;
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

// Header controls live in layout.js markup, so they are intentionally global.
// Page-specific globals are rebound by each page module on mount().
window.setTab = setDataset;
window.toggleSidebar = toggleSidebar;
window.toggleNavCollapse = toggleNavCollapse;
window.scrollSideNav = scrollSideNav;
window.setMinimumPlaysWarning = setMinimumPlaysWarning;

onRouteChange(renderCurrentRoute);
renderCurrentRoute();
