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
    load: () => import('./pages/home.js?v=20260704-9'),
  },
  cards: {
    id: 'cards',
    title: 'Cards',
    navLabel: 'Cards',
    load: () => import('./pages/cards.js?v=20260704-9'),
  },
  'opening-hand': {
    id: 'opening-hand',
    title: 'Opening Hand',
    navLabel: 'Opening Hand',
    load: () => import('./pages/opening-hand.js?v=20260704-9'),
  },
  maps: {
    id: 'maps',
    title: 'Maps',
    navLabel: 'Maps',
    load: () => import('./pages/maps.js?v=20260704-9'),
  },
  combos: {
    id: 'combos',
    title: 'Combos',
    navLabel: 'Combos',
    load: () => import('./pages/combos.js?v=20260704-9'),
  },
  endgames: {
    id: 'endgames',
    title: 'Endgames',
    navLabel: 'Endgames',
    load: () => import('./pages/endgames.js?v=20260704-9'),
  },
  'sponsor-endgames': {
    id: 'sponsor-endgames',
    title: 'Sponsor Endgames',
    navLabel: 'Sponsor Endgames',
    load: () => import('./pages/sponsor-endgames.js?v=20260704-9'),
  },
  icons: {
    id: 'icons',
    title: 'Icons',
    navLabel: 'Icons',
    load: () => import('./pages/icons.js?v=20260704-9'),
  },
};
