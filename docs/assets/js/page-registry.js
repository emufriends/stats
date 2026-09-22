export const DEFAULT_PAGE_ID = 'home';

// Central page registry.
//
// Add every new dashboard subpage here. The object key must match the first hash
// route segment (for example "#/opening-hand"), and the page module should export
// the lifecycle shape used by app.js: id/title/mainHtml/sidebarHtml plus optional
// mount(), unmount(), and setDataset().
export const PAGES = {
  home: {
    id: 'home',
    title: 'Home',
    navLabel: 'Home',
    load: () => import('./pages/home.js?v=20260921-filter-performance'),
  },
  cards: {
    id: 'cards',
    title: 'Cards',
    navLabel: 'Cards',
    load: () => import('./pages/cards.js?v=20260921-filter-performance'),
  },
  'card-details': {
    id: 'card-details',
    title: 'Card details',
    navLabel: null,
    load: () => import('./pages/card-details.js?v=20260921-filter-performance'),
  },
  'opening-hand': {
    id: 'opening-hand',
    title: 'Opening Hand',
    navLabel: 'Opening Hand',
    load: () => import('./pages/opening-hand.js?v=20260921-filter-performance'),
  },
  maps: {
    id: 'maps',
    title: 'Maps',
    navLabel: 'Maps',
    load: () => import('./pages/maps.js?v=20260921-filter-performance'),
  },
  combos: {
    id: 'combos',
    title: 'Combos',
    navLabel: 'Combos',
    load: () => import('./pages/combos.js?v=20260921-filter-performance'),
  },
  endgames: {
    id: 'endgames',
    title: 'Endgames',
    navLabel: 'Endgames',
    load: () => import('./pages/endgames.js?v=20260921-filter-performance'),
  },
  'sponsor-endgames': {
    id: 'sponsor-endgames',
    title: 'Sponsor Endgames',
    navLabel: 'Sponsor Endgames',
    load: () => import('./pages/sponsor-endgames.js?v=20260921-filter-performance'),
  },
  icons: {
    id: 'icons',
    title: 'Icons',
    navLabel: 'Icons',
    load: () => import('./pages/icons.js?v=20260921-filter-performance'),
  },
  actions: {
    id: 'actions',
    title: 'Actions',
    navLabel: 'Actions',
    load: () => import('./pages/actions.js?v=20260921-filter-performance'),
  },
  'mw-action-cards': {
    id: 'mw-action-cards',
    title: 'MW Action Cards',
    navLabel: 'MW Action Cards',
    load: () => import('./pages/mw-action-cards.js?v=20260921-filter-performance'),
  },
  predictors: {
    id: 'predictors',
    title: 'Predictors',
    navLabel: 'Predictors',
    load: () => import('./pages/predictors.js?v=20260921-filter-performance'),
  },
  build: {
    id: 'build',
    title: 'Build',
    navLabel: 'Build',
    load: () => import('./pages/build.js?v=20260921-filter-performance'),
  },
  conservation: {
    id: 'conservation',
    title: 'Conservation',
    navLabel: 'Conservation',
    load: () => import('./pages/conservation.js?v=20260921-filter-performance'),
  },
  scoring: {
    id: 'scoring',
    title: 'Scoring',
    navLabel: 'Scoring',
    load: () => import('./pages/scoring.js?v=20260921-filter-performance'),
  },
  workers: {
    id: 'workers',
    title: 'Workers',
    navLabel: 'Workers',
    load: () => import('./pages/workers.js?v=20260921-filter-performance'),
  },
  players: {
    id: 'players',
    title: 'Players',
    navLabel: 'Players',
    load: () => import('./pages/players.js?v=20260921-filter-performance'),
  },
  arena: {
    id: 'arena',
    title: 'Arena',
    navLabel: 'Arena',
    load: () => import('./pages/arena.js?v=20260921-filter-performance'),
  },
  records: {
    id: 'records',
    title: 'Records',
    navLabel: 'Records',
    load: () => import('./pages/records.js?v=20260921-filter-performance'),
  },
  // Path-only maintenance page. router.js never resolves #/refresh, and the
  // navigation rail deliberately has no corresponding link.
  refresh: {
    id: 'refresh',
    title: 'Refresh',
    navLabel: null,
    load: () => import('./pages/refresh.js?v=20260921-filter-performance'),
  },
};
