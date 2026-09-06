// Minimal router for a static GitHub Pages app.
//
// Routes look like #/cards or #/opening-hand. Unknown routes intentionally fall
// back to DEFAULT_PAGE_ID instead of showing a 404, because GitHub Pages serves
// the same index.html for the whole dashboard.
export function getRoutePageId(pages, defaultPageId) {
  // The private maintenance UI is the sole path-based route. A real
  // refresh/index.html entry keeps direct /refresh navigation compatible with
  // GitHub Pages without exposing the page in the dashboard navigation.
  if (isRefreshPath() && pages.refresh) return 'refresh';
  const raw = window.location.hash.replace(/^#\/?/, '').trim();
  if (!raw) return defaultPageId;
  const pageId = raw.split('/')[0];
  if (pageId === 'refresh') return defaultPageId;
  return pages[pageId] ? pageId : defaultPageId;
}

export function isRefreshPath() {
  return /\/refresh(?:\/|\/index\.html)?$/i.test(window.location.pathname);
}

export function onRouteChange(callback) {
  // Initial render is called explicitly from app.js; this only wires later route changes.
  window.addEventListener('hashchange', callback);
}
