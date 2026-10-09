// Minimal router for a static GitHub Pages app.
//
// Routes look like #/cards or #/opening-hand. Unknown routes intentionally fall
// back to DEFAULT_PAGE_ID inside the loaded app. Normal pages use hashes and
// share index.html; this does not imply a host-side fallback for arbitrary paths.
export function getRoutePageId(pages, defaultPageId) {
  // The unlinked maintenance UI is the sole path-based route. Hiding its route
  // is not authentication; refresh authorization is enforced by the backend. A real
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
