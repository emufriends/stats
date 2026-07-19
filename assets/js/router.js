// Minimal hash router for a static GitHub Pages app.
//
// Routes look like #/cards or #/opening-hand. Unknown routes intentionally fall
// back to DEFAULT_PAGE_ID instead of showing a 404, because GitHub Pages serves
// the same index.html for the whole dashboard.
export function getRoutePageId(pages, defaultPageId) {
  const raw = window.location.hash.replace(/^#\/?/, '').trim();
  if (!raw) return defaultPageId;
  const pageId = raw.split('/')[0];
  return pages[pageId] ? pageId : defaultPageId;
}

export function onRouteChange(callback) {
  // Initial render is called explicitly from app.js; this only wires later route changes.
  window.addEventListener('hashchange', callback);
}
