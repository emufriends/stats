const headerHtml = "<header class=\"topbar\">\n  <div class=\"topbar-left\">\n    <div class=\"tabs\">\n      <button class=\"tab-btn tab-mw active\" onclick=\"setTab(1, this)\">Marine Worlds</button>\n      <button class=\"tab-btn tab-base\" onclick=\"setTab(0, this)\">Base</button>\n    </div>\n  </div>\n  <div class=\"topbar-logo\" aria-label=\"Ark Nova Statistics\">\n    <div class=\"topbar-wordmark\">\n      <div class=\"topbar-wordmark-top\">\n        <span class=\"wm-ark\">Ark</span>\n        <span class=\"wm-rhino\" aria-hidden=\"true\">\n          <svg width=\"22\" height=\"26\" viewBox=\"70 30 370 430\" xmlns=\"http://www.w3.org/2000/svg\">\n            <defs>\n              <mask id=\"wmEmuMask\" maskUnits=\"userSpaceOnUse\" x=\"70\" y=\"30\" width=\"370\" height=\"430\" mask-type=\"luminance\">\n                <image href=\"data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAfQAAAH0CAMAAAD8CC+4AAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAACBUExURez///P//93///r//////97//+L///7//+n//9z///v//+///9n//+b//9j//+r///X//9///+H///n///T///H//+X//+D///L//+v//+T///D///j///z//+3//9v//9r///b//+f//+7///3///f//+j//////v///f///AAAAAFNPpcAAAArdFJOU////////////////////////////////////////////////////////wAjyafQAAAACXBIWXMAAA7DAAAOwwHHb6hkAAAAGXRFWHRTb2Z0d2FyZQBQYWludC5ORVQgNS4xLjEyEwFHdAAAALhlWElmSUkqAAgAAAAFABoBBQABAAAASgAAABsBBQABAAAAUgAAACgBAwABAAAAAgAAADEBAgARAAAAWgAAAGmHBAABAAAAbAAAAAAAAABgAAAAAQAAAGAAAAABAAAAUGFpbnQuTkVUIDUuMS4xMgAAAwAAkAcABAAAADAyMzABoAMAAQAAAAEAAAAFoAQAAQAAAJYAAAAAAAAAAgABAAIABAAAAFI5OAACAAcABAAAADAxMDAAAAAA2aealcm3C18AABIzSURBVHhe7d3rets2FoXhuGGbRmkn7jjOtE3cmbQ52Ln/C5xHokwBiwAJitgbh73ePzOlAFjEF9myTn7xncx5gQeof4xuEKMbxOgGMbpBjG4QoxvE6AYxukGMbhCjG8ToBjG6QYxuEKMbxOgGMbpBjG4QoxvE6AYxukGMbhCjG8ToBjG6QYxuEKMbxOgGMbpBjG4QoxvE6AYxukGMbhCjG8ToBjG6QYxuEKMbxOgGMbpBjG4Qo5fy4uYHPKSF0Qt5OQzDj3hQCaOX8dMwDMMrPKqE0cv4+Rh9wKNKGL2M18fmBzyqhNELeTMMwy94UAmjl/L6VzyihtENYnSDGL2Uf5Xb+nJf2bpheIuHtDB6KcNwi4e0MHohv5V7bIbRS3k7DMO/8aASRi/kbij3Q53RCzk+DPsOD05kn3dldEE/3sdvy4tPuAg/78rocn4Y4vfQj/fjhuE9Hh5JP+/K6HKOt9fhP3h09Psp+g0eHkk/78rock7p/sCjo9NlsbDSz7sy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\" x=\"0\" y=\"0\" width=\"500\" height=\"500\" />\n              </mask>\n            </defs>\n            <rect x=\"70\" y=\"30\" width=\"370\" height=\"430\" fill=\"currentColor\" mask=\"url(#wmEmuMask)\" />\n          </svg>\n        </span>\n        <span class=\"wm-nova\">Nova</span>\n      </div>\n      <div class=\"wm-stats\">Statistics</div>\n    </div>\n  </div>\n  <div class=\"topbar-actions\">\n    <button class=\"mobile-filter-btn filter-toggle-highlight\" onclick=\"toggleSidebar()\" id=\"filterToggleBtn\">\n    <svg class=\"filter-btn-icon\" viewBox=\"0 0 24 24\" aria-hidden=\"true\">\n      <path d=\"M4 6h16l-6.2 7.1v4.2l-3.6 1.8v-6L4 6Z\" />\n    </svg>\n    <span>Filters</span>\n    </button>\n  </div>\n</header>";
const navHtml = "\u003cnav class=\"side-nav\" id=\"sideNav\" aria-label=\"Dashboard navigation\"\u003e\n  \u003cbutton class=\"nav-collapse-btn\" id=\"navCollapseBtn\" onclick=\"toggleNavCollapse()\" aria-label=\"Toggle navigation\"\u003e\u003c/button\u003e\n  \u003ca class=\"side-nav-link active\" href=\"#/cards\" data-page-id=\"cards\" aria-current=\"page\"\u003e\n    \u003csvg class=\"nav-icon\" viewBox=\"0 0 24 24\"\u003e\n      \u003crect x=\"11.5\" y=\"1.8\" width=\"11\" height=\"14.5\" rx=\"2\" /\u003e\n      \u003crect x=\"8\" y=\"4\" width=\"11\" height=\"14.5\" rx=\"2\" style=\"fill:#050d0c\" /\u003e\n      \u003crect x=\"4.5\" y=\"6.2\" width=\"11\" height=\"14.5\" rx=\"2\" style=\"fill:#050d0c\" /\u003e\n    \u003c/svg\u003e\n    \u003cspan\u003eCards\u003c/span\u003e\n  \u003c/a\u003e\n  \u003cdiv class=\"nav-divider\"\u003e\u003c/div\u003e\n  \u003ca class=\"side-nav-link\" href=\"#/opening-hand\" data-page-id=\"opening-hand\"\u003e\n    \u003csvg class=\"nav-icon nav-icon-hand\" viewBox=\"0 0 24 24\"\u003e\n      \u003cpath d=\"M9.7 20.7c-1.35-.55-2.35-1.45-3.1-2.72L3.7 13.1c-.42-.72-.18-1.59.51-1.98.67-.38 1.45-.16 1.9.53l1.05 1.58V7.05c0-.72.52-1.25 1.2-1.25.7 0 1.2.53 1.2 1.25v4.45h.58V4.65c0-.72.52-1.25 1.2-1.25.7 0 1.2.53 1.2 1.25v6.85h.58V4.95c0-.72.52-1.25 1.2-1.25.7 0 1.2.53 1.2 1.25v6.75h.58V6.35c0-.72.52-1.25 1.2-1.25.7 0 1.2.53 1.2 1.25v8.35c0 3.7-2.08 5.82-5.52 5.82h-1.72c-.58 0-1.1-.06-1.56-.2Z\" /\u003e\n    \u003c/svg\u003e\n    \u003cspan\u003eOpening\u003cbr /\u003ehand\u003c/span\u003e\n  \u003c/a\u003e\n  \u003cdiv class=\"nav-divider\"\u003e\u003c/div\u003e\n  \u003ca class=\"side-nav-link\" href=\"#/endgames\" data-page-id=\"endgames\"\u003e\n    \u003csvg class=\"nav-icon nav-icon-endgames\" viewBox=\"0 0 24 24\" aria-hidden=\"true\" fill=\"none\"\u003e\n      \u003cpath d=\"M6 3h12\" /\u003e\n      \u003cpath d=\"M6 21h12\" /\u003e\n      \u003cpath d=\"M8 3v4.5c0 1.1.5 2.1 1.3 2.8L12 12l2.7-1.7c.8-.7 1.3-1.7 1.3-2.8V3\" /\u003e\n      \u003cpath d=\"M8 21v-4.5c0-1.1.5-2.1 1.3-2.8L12 12l2.7 1.7c.8.7 1.3 1.7 1.3 2.8V21\" /\u003e\n    \u003c/svg\u003e\n    \u003cspan\u003eEndgames\u003c/span\u003e\n  \u003c/a\u003e\n  \u003cdiv class=\"nav-divider\"\u003e\u003c/div\u003e\n    \u003ca class=\"side-nav-link\" href=\"#/maps\" data-page-id=\"maps\"\u003e\n    \u003csvg class=\"nav-icon nav-icon-maps\" viewBox=\"0 0 24 24\" aria-hidden=\"true\" fill=\"none\"\u003e\n      \u003cpolygon points=\"8 3.5 12 5.8 12 10.4 8 12.7 4 10.4 4 5.8\" /\u003e\n      \u003cpolygon points=\"16 3.5 20 5.8 20 10.4 16 12.7 12 10.4 12 5.8\" /\u003e\n      \u003cpolygon points=\"12 10.4 16 12.7 16 17.3 12 19.6 8 17.3 8 12.7\" /\u003e\n    \u003c/svg\u003e\n    \u003cspan\u003eMaps\u003c/span\u003e\n  \u003c/a\u003e\n\u003c/nav\u003e";

const sideNavContentHtml = `
  <button class="nav-collapse-btn" id="navCollapseBtn" onclick="toggleNavCollapse()" aria-label="Toggle navigation"></button>
  <button class="side-nav-scroll-btn side-nav-scroll-up" id="navScrollUp" onclick="scrollSideNav(-1)" aria-label="Scroll navigation up"><span aria-hidden="true">&#9650;</span></button>
  <div class="side-nav-scroll-area" id="sideNavScrollArea">
    <a class="side-nav-link active" href="#/cards" data-page-id="cards" aria-current="page">
      <svg class="nav-icon" viewBox="0 0 24 24"><rect x="11.5" y="1.8" width="11" height="14.5" rx="2" /><rect x="8" y="4" width="11" height="14.5" rx="2" style="fill:#050d0c" /><rect x="4.5" y="6.2" width="11" height="14.5" rx="2" style="fill:#050d0c" /></svg>
      <span>Cards</span>
    </a>
    <div class="nav-divider"></div>
    <a class="side-nav-link" href="#/opening-hand" data-page-id="opening-hand">
      <svg class="nav-icon nav-icon-hand" viewBox="0 0 24 24"><path d="M9.7 20.7c-1.35-.55-2.35-1.45-3.1-2.72L3.7 13.1c-.42-.72-.18-1.59.51-1.98.67-.38 1.45-.16 1.9.53l1.05 1.58V7.05c0-.72.52-1.25 1.2-1.25.7 0 1.2.53 1.2 1.25v4.45h.58V4.65c0-.72.52-1.25 1.2-1.25.7 0 1.2.53 1.2 1.25v6.85h.58V4.95c0-.72.52-1.25 1.2-1.25.7 0 1.2.53 1.2 1.25v6.75h.58V6.35c0-.72.52-1.25 1.2-1.25.7 0 1.2.53 1.2 1.25v8.35c0 3.7-2.08 5.82-5.52 5.82h-1.72c-.58 0-1.1-.06-1.56-.2Z" /></svg>
      <span>Opening<br />hand</span>
    </a>
    <div class="nav-divider"></div>
    <a class="side-nav-link" href="#/maps" data-page-id="maps">
      <svg class="nav-icon nav-icon-maps" viewBox="0 0 28 24" aria-hidden="true" fill="none"><polygon points="10 3 13.5 5 13.5 9 10 11 6.5 9 6.5 5" /><polygon points="18 3 21.5 5 21.5 9 18 11 14.5 9 14.5 5" /><polygon points="6 10 9.5 12 9.5 16 6 18 2.5 16 2.5 12" /><polygon points="14 10 17.5 12 17.5 16 14 18 10.5 16 10.5 12" /><polygon points="22 10 25.5 12 25.5 16 22 18 18.5 16 18.5 12" /></svg>
      <span>Maps</span>
    </a>
    <div class="nav-divider"></div>
    <a class="side-nav-link" href="#/combos" data-page-id="combos">
      <svg class="nav-icon nav-icon-combinations" viewBox="0 0 30 24" aria-hidden="true" fill="none">
        <rect x="1.5" y="4" width="8" height="15" rx="1.5" />
        <path d="M12 11.5h6M15 8.5v6" />
        <rect x="20.5" y="4" width="8" height="15" rx="1.5" />
      </svg>
      <span>Combos</span>
    </a>
    <div class="nav-divider"></div>
    <a class="side-nav-link" href="#/endgames" data-page-id="endgames">
      <svg class="nav-icon nav-icon-endgames" viewBox="0 0 24 24" aria-hidden="true" fill="none"><path d="M6 3h12" /><path d="M6 21h12" /><path d="M8 3v4.5c0 1.1.5 2.1 1.3 2.8L12 12l2.7-1.7c.8-.7 1.3-1.7 1.3-2.8V3" /><path d="M8 21v-4.5c0-1.1.5-2.1 1.3-2.8L12 12l2.7 1.7c.8.7 1.3 1.7 1.3 2.8V21" /></svg>
      <span>Endgames</span>
    </a>
    <div class="nav-divider"></div>
    <a class="side-nav-link" href="#/sponsor-endgames" data-page-id="sponsor-endgames">
      <svg class="nav-icon nav-icon-sponsor-endgames" viewBox="0 0 24 24" aria-hidden="true" fill="none"><rect x="6" y="3" width="12" height="18" rx="2" /><text x="12" y="14.4" text-anchor="middle" aria-hidden="true">@</text></svg>
      <span>Sponsor<br />endgames</span>
    </a>
    <div class="nav-divider"></div>
    <a class="side-nav-link" href="#/actions" data-page-id="actions">
      <svg class="nav-icon" viewBox="0 0 30 24" aria-hidden="true" fill="none">
        <rect x="1" y="6" width="5" height="12" rx="1" /><rect x="7" y="5" width="5" height="13" rx="1" />
        <rect x="13" y="4" width="5" height="14" rx="1" /><rect x="19" y="5" width="5" height="13" rx="1" />
        <rect x="25" y="6" width="4" height="12" rx="1" />
      </svg>
      <span>Actions</span>
    </a>
    <div class="nav-divider"></div>
    <a class="side-nav-link" href="#/predictors" data-page-id="predictors">
      <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true" fill="none">
        <circle cx="12" cy="10" r="6.5" /><path d="M7 17h10l2 4H5l2-4Z" /><path d="M9 9c1.5-2 4-2.5 6-1" />
      </svg>
      <span>Predictors</span>
    </a>
    <div class="nav-divider"></div>
    <a class="side-nav-link" href="#/icons" data-page-id="icons">
      <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true" fill="none">
        <circle cx="12" cy="12" r="9" /><path d="M8 14c0-3 2-5 4-5s4 2 4 5c-1 2-2.5 3-4 3s-3-1-4-3Z" />
        <circle cx="10.5" cy="12" r=".6" fill="currentColor" stroke="none" /><circle cx="13.5" cy="12" r=".6" fill="currentColor" stroke="none" />
      </svg>
      <span>Icons</span>
    </a>
    <div class="nav-divider"></div>
    <button type="button" class="side-nav-link nav-placeholder">
      <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true" fill="none">
        <rect x="5" y="2.5" width="14" height="19" rx="2" />
        <path d="M8 12c2-3 5-3 7 0-2 3-5 3-7 0Zm7 0 2-2v4l-2-2Z" />
        <circle cx="11" cy="11.5" r=".6" fill="currentColor" stroke="none" />
      </svg>
      <span>MW Action<br />Cards</span>
    </button>
    <div class="nav-divider"></div>
    <a class="side-nav-link" href="#/build" data-page-id="build">
      <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true" fill="none">
        <path d="m7 3 10 10M15.5 11.5l3-3M5 19l6-6 3 3-6 6H5v-3Z" />
      </svg>
      <span>Build</span>
    </a>
    <div class="nav-divider"></div>
    <button type="button" class="side-nav-link nav-placeholder">
      <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true" fill="none">
        <path d="M12 2.5 20 6v5c0 5-3.2 8.3-8 10.5C7.2 19.3 4 16 4 11V6l8-3.5Z" />
      </svg>
      <span>Projects</span>
    </button>
    <div class="nav-divider"></div>
    <button type="button" class="side-nav-link nav-placeholder">
      <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true" fill="none">
        <circle cx="12" cy="7" r="3.5" /><path d="M5.5 21c.5-5 2.7-8 6.5-8s6 3 6.5 8" />
      </svg>
      <span>Workers</span>
    </button>
    <div class="nav-divider"></div>
    <button type="button" class="side-nav-link nav-placeholder">
      <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true" fill="none">
        <path d="M3 20h18M5 13h5v7H5v-7Zm9-3h5v10h-5V10Zm-7-2h10" />
        <text x="12" y="7" text-anchor="middle" aria-hidden="true">1</text>
      </svg>
      <span>Records</span>
    </button>
    <div class="nav-divider"></div>
    <button type="button" class="side-nav-link nav-placeholder">
      <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true" fill="none">
        <circle cx="12" cy="7" r="2.5" /><circle cx="6" cy="9" r="2" /><circle cx="18" cy="9" r="2" />
        <path d="M7 20c.3-4 2-7 5-7s4.7 3 5 7M1.5 20c.2-3.2 1.7-5.5 4.5-5.5 1 0 1.8.3 2.5.8M22.5 20c-.2-3.2-1.7-5.5-4.5-5.5-1 0-1.8.3-2.5.8" />
      </svg>
      <span>Players</span>
    </button>
  </div>
  <button class="side-nav-scroll-btn side-nav-scroll-down" id="navScrollDown" onclick="scrollSideNav(1)" aria-label="Scroll navigation down"><span aria-hidden="true">&#9660;</span></button>`;

// Render the persistent app shell once. Route changes only replace #pageMain
// and #sidebar; the header, nav rail, overlays, and shared tooltip nodes stay
// stable so subpages cannot accidentally duplicate global layout elements.
export function renderShell(root) {
  if (root.dataset.shellRendered === 'true') return;

  root.innerHTML = `
    <div id="map-tooltip"></div>
    <div id="col-tooltip"></div>
    ${headerHtml}
    ${navHtml}
    <div class="sidebar-overlay" id="sidebarOverlay" onclick="toggleSidebar()"></div>
    <div class="layout" id="mainLayout">
      <main class="main" id="pageMain"></main>
      <aside class="sidebar" id="sidebar"></aside>
    </div>
  `;
  root.dataset.shellRendered = 'true';

  const nav = document.getElementById('sideNav');
  if (nav) nav.innerHTML = sideNavContentHtml;
  const navCollapseBtn = document.getElementById('navCollapseBtn');
  if (navCollapseBtn) navCollapseBtn.textContent = '\u2039';
  const logo = document.querySelector('.topbar-logo');
  if (logo) {
    logo.setAttribute('role', 'link');
    logo.setAttribute('tabindex', '0');
    logo.addEventListener('click', () => {
      location.hash = '';
    });
    logo.addEventListener('keydown', event => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      location.hash = '';
    });
  }
  initSideNavScroll();
}

// Highlight the nav entry belonging to the active page-registry id.
export function setActiveNav(pageId) {
  document.querySelectorAll('.side-nav-link[data-page-id]').forEach(link => {
    const isActive = link.dataset.pageId === pageId;
    link.classList.toggle('active', isActive);
    if (isActive) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
  updateSideNavScrollState();
}

// The MW/Base switch is global UI, but each page module decides how changing
// dataset reloads its own statistics.
export function setTopbarDataset(value) {
  document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
  const active = document.querySelector(value === 1 ? '.tab-mw' : '.tab-base');
  if (active) active.classList.add('active');
}

// Shared sidebar drawer behaviour. The sidebar contents themselves are owned
// by the active page module, because filters differ slightly per page.
export function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  if (!sidebar || !overlay) return;
  sidebar.classList.toggle('open');
  overlay.classList.toggle('active');
}

// Close the filter drawer after route changes or successful Apply actions.
export function closeSidebarIfOpen() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  if (!sidebar || !sidebar.classList.contains('open')) return;
  sidebar.classList.remove('open');
  if (overlay) overlay.classList.remove('active');
}

// Shared nav collapse state. CSS controls the rail's dimensions at each breakpoint.
export function toggleNavCollapse() {
  if (isNavHomeLocked) return;
  const nav = document.getElementById('sideNav');
  const btn = document.getElementById('navCollapseBtn');
  if (!nav || !btn) return;
  setNavCollapsed(!nav.classList.contains('nav-collapsed'));
}

// The Home page keeps the nav rail permanently expanded and non-collapsible,
// unlike every other page where it collapses after a route is chosen on
// mobile. Called once per route render with whether the newly active page is
// Home. Locking also force-expands the rail immediately, so arriving at Home
// (e.g. via the topbar logo) always shows the full rail even if it was left
// collapsed on a previous page.
let isNavHomeLocked = false;

export function setNavHomeLock(isHome) {
  const wasHomeLocked = isNavHomeLocked;
  isNavHomeLocked = Boolean(isHome);
  const nav = document.getElementById('sideNav');
  if (!nav) return;
  nav.classList.toggle('nav-home-locked', isNavHomeLocked);
  if (isNavHomeLocked) {
    setNavCollapsed(false);
  } else if (wasHomeLocked && window.matchMedia('(max-width: 600px)').matches) {
    // The route-link click happens while Home is still locked, so its normal
    // mobile auto-collapse is skipped. Collapse once the new route unlocks it.
    setNavCollapsed(true);
  }
}

function setNavCollapsed(isCollapsed) {
  const nav = document.getElementById('sideNav');
  const btn = document.getElementById('navCollapseBtn');
  if (!nav || !btn) return;
  nav.classList.toggle('nav-collapsed', isCollapsed);
  btn.textContent = isCollapsed ? '\u203a' : '\u2039';
  if (isCollapsed) {
    document.documentElement.style.setProperty('--side-nav-width', '0px');
  } else {
    document.documentElement.style.removeProperty('--side-nav-width');
  }
  updateSideNavScrollState();
}

let sideNavScrollInitialized = false;

function getSideNavScrollArea() {
  return document.getElementById('sideNavScrollArea');
}

function getSideNavStep() {
  const area = getSideNavScrollArea();
  const links = area ? Array.from(area.querySelectorAll('.side-nav-link')) : [];
  if (links.length > 1) return links[1].offsetTop - links[0].offsetTop;
  return links[0]?.offsetHeight || 60;
}

export function scrollSideNav(direction) {
  const area = getSideNavScrollArea();
  if (!area) return;
  area.scrollBy({ top: direction * getSideNavStep(), behavior: 'smooth' });
  window.setTimeout(updateSideNavScrollState, 180);
}

export function updateSideNavScrollState() {
  const area = getSideNavScrollArea();
  const up = document.getElementById('navScrollUp');
  const down = document.getElementById('navScrollDown');
  if (!area || !up || !down) return;

  const canOverflow = area.scrollHeight > area.clientHeight + 1;
  up.classList.toggle('visible', canOverflow);
  down.classList.toggle('visible', canOverflow);

  const atTop = area.scrollTop <= 1;
  const atBottom = area.scrollTop + area.clientHeight >= area.scrollHeight - 1;
  up.disabled = !canOverflow || atTop;
  down.disabled = !canOverflow || atBottom;
}

function initSideNavScroll() {
  const area = getSideNavScrollArea();
  if (!area) return;
  area.addEventListener('scroll', updateSideNavScrollState, { passive: true });
  area.addEventListener('click', event => {
    if (!event.target.closest('.side-nav-link')) return;
    if (isNavHomeLocked) return;
    if (window.matchMedia('(max-width: 600px)').matches) setNavCollapsed(true);
  });
  updateSideNavScrollState();

  if (sideNavScrollInitialized) return;
  sideNavScrollInitialized = true;
  window.addEventListener('resize', updateSideNavScrollState);
}








