# Ark Nova Statistics Dashboard Handoff

Date: 2026-06-21  
Last updated: 2026-07-03  
Project owner: pr0paganda-panda / Panda  
Current active development repo: https://github.com/emufriends/arknova-stats  
Public frozen repo: pr0paganda-panda/ark-nova-stats, maintained manually by the user

This handoff is for a future Codex/AI session continuing the Ark Nova statistics dashboard. It is intentionally comprehensive and secret-free. Do not add maintenance tokens, API keys, or service account JSON to this file.

## Executive Summary

The project is now a static GitHub Pages frontend backed by one Google Cloud Function. The frontend has been split from a single large HTML file into a reusable shell plus page modules. Current pages:

- Cards
- Opening Hand
- Endgames
- Maps
- Sponsor Endgames
- Combos

Cards, Opening Hand, Endgames, and Maps share the same shell, navigation rail, topbar, filter sidebar style, table behavior, and MW/Base dataset toggle. Cards and Opening Hand also share the attributes bar and type/search filters. Endgames and Maps use fixed in-page tab bars instead of an attributes bar. The backend serves Cards, Opening Hand, Endgames, and Maps via the same Cloud Function endpoint, selected with `stats_page`.

The current version is considered public-release-ready. Future work should happen in the `emufriends/arknova-stats` repo/working copy; the user will manually update the public repo when desired.

## Current Local Folders

Frontend working copy:

```text
C:\Users\ascri\Desktop\ark-nova-stats-dashboard
```

Backend Cloud Function source:

```text
C:\Users\ascri\Desktop\ark-nova-function
```

Backend folder is now cleaned down to:

```text
main.py
requirements.txt
cards_attributes.csv
```

Old temporary backup Python files (`main_backup_before_opening_hand.py`, `main_with_opening_hand.py`) can be removed once `main.py` is confirmed current.

## Local Preview Server

The user has a double-click preview launcher on the Desktop:

```text
C:\Users\ascri\Desktop\start-ark-nova-preview.bat
```

It serves:

```text
C:\Users\ascri\Desktop\ark-nova-stats-dashboard
```

at:

```text
http://127.0.0.1:8767/
```

The script appends a `?fresh=...` query when opening the browser to reduce stale browser-cache confusion. Keep the black server window open while previewing; close it or press `Ctrl+C` to stop the server. If the port is already in use, close the old preview-server window and start it again. If the normal browser still looks stale, press `Ctrl+F5` once.
## GitHub / Deployment Model

The working GitHub repo is:

```text
https://github.com/emufriends/arknova-stats
```

The user cloned the public repo into this quieter account so development can continue without changing the public live version. Treat `emufriends/arknova-stats` as the development repo from now on.

GitHub Pages should serve the static app from:

```text
Branch: main
Folder: /docs
```

The local folder `C:\Users\ascri\Desktop\ark-nova-stats-dashboard` contains the static frontend files. In GitHub, these live under `docs/`.

Root repo may also contain:

```text
README.md
backend/main.py
backend/requirements.txt
docs/
```

Keeping backend code public is acceptable because secrets are read from environment variables. Make sure no token, API key, private credential, or service account JSON is committed.

## Frontend File Layout

Current static frontend files:

```text
index.html
.nojekyll
favicon.png
logo.png
cards_altnames.csv
cards_attributes.csv
assets/
  css/
    app.css
  js/
    app.js
    layout.js
    router.js
    page-registry.js
    pages/
      home.js
      cards.js
      endgames.js
      maps.js
      opening-hand.js
      sponsor-endgames.js
      combos.js
```

In GitHub Pages `/docs`, keep this same structure.

### index.html

Small entry point only:

- Loads Google fonts.
- Loads `assets/css/app.css`.
- Has `<div id="app"></div>`.
- Loads `assets/js/app.js` as a module.

Do not turn this back into a giant single-file app.

### app.js

Owns the runtime shell and route rendering:

- Imports `PAGES`, router helpers, and layout helpers.
- Maintains `currentDataset` (`1` = Marine Worlds, `0` = Base).
- Renders the shell once.
- Loads the current page module dynamically.
- Calls `activePage.unmount()` before mounting the next page.
- Injects `page.mainHtml` into `#pageMain`.
- Injects `page.sidebarHtml` into `#sidebar`.
- Enhances text date inputs with a native calendar picker limited to 2023 onward. Visible values stay in `yyyy-mm-dd`; valid one-digit months/days are zero-padded automatically.
- Calls `page.mount({ dataset, pageId })`.
- Exposes global topbar handlers:
  - `window.setTab`
  - `window.toggleSidebar`
  - `window.toggleNavCollapse`

Important: page modules still use inline HTML `onclick` handlers, so each page module must bind its page-specific handlers onto `window` when mounted.

### router.js

Simple hash router:

```text
#/home
#/cards
#/endgames
#/opening-hand
#/maps
#/sponsor-endgames
#/combos
```

Unknown or empty hash falls back to `DEFAULT_PAGE_ID`.
`router.js` does not import the registry itself: `app.js` passes `PAGES` and
`DEFAULT_PAGE_ID` to `getRoutePageId()` so only one registry module instance is loaded.

### page-registry.js

Current registry:

```js
export const DEFAULT_PAGE_ID = 'home';

export const PAGES = {
  home: {
    id: 'home',
    title: 'Home',
    navLabel: 'Home',
    load: () => import('./pages/home.js'),
  },
  cards: {
    id: 'cards',
    title: 'Cards',
    navLabel: 'Cards',
    load: () => import('./pages/cards.js'),
  },
  'opening-hand': {
    id: 'opening-hand',
    title: 'Opening Hand',
    navLabel: 'Opening Hand',
    load: () => import('./pages/opening-hand.js'),
  },
  endgames: {
    id: 'endgames',
    title: 'Endgames',
    navLabel: 'Endgames',
    load: () => import('./pages/endgames.js'),
  },
  maps: {
    id: 'maps',
    title: 'Maps',
    navLabel: 'Maps',
    load: () => import('./pages/maps.js'),
  },
  combos: {
    id: 'combos',
    title: 'Combos',
    navLabel: 'Combos',
    load: () => import('./pages/combos.js'),
  },
  'sponsor-endgames': {
    id: 'sponsor-endgames',
    title: 'Sponsor Endgames',
    navLabel: 'Sponsor Endgames',
    load: () => import('./pages/sponsor-endgames.js'),
  },
};
```

To add a new subpage:

1. Add a module in `assets/js/pages/<page-id>.js`.
2. Export `id`, `title`, `mainHtml`, `sidebarHtml`, `mount`, `unmount`, and `setDataset`.
3. Add the page to `PAGES`.
4. Add the nav item in `layout.js`.
5. Add backend support if the page needs new aggregations.

### layout.js

Owns reusable shell HTML:

- Header/topbar
- Left navigation rail
- Sidebar/overlay containers
- `#pageMain`

Recent visual state:

- Header logo/wordmark from old design has been integrated.
- `Nova` wordmark color is `#BAFFE0`.
- Topbar filter button now uses an inline SVG funnel icon, not the hamburger/menu glyph.
- Navigation has Cards, Opening Hand, Maps, Combos, Endgames, Sponsor Endgames, Actions, Icons, Predictors, Build, Conservation, Workers, Players, and the Records placeholder. Home has no rail item; the topbar logo links to it. Build routes to `#/build`; Conservation routes to `#/conservation`; Workers routes to `#/workers`; Players routes to `#/players`. Scoring occupies a non-clickable placeholder position between Conservation and Workers. Scoring, Arena, and Records are placeholders; Players General and Comparison are active views.
- Endgames uses an hourglass icon; Maps uses a small cluster of board-game-style hexes.
- Rail icons are either complete inline `<svg>...</svg>` elements or the Build PNG mask span. Keep every inline SVG wrapper balanced when reordering nav items; paths/circles outside an opening SVG are silently discarded by the browser.
- Header topbar includes:
  - MW/Base switch
  - Ark Nova Statistics logo/wordmark
  - Filters button

### app.css

Central stylesheet for all pages. Important conventions:

- Static app uses a dark green Ark Nova themed dashboard style.
- Dominant UI palette uses deep green surfaces, mint accents, gold Base tab, and limited pale/bright accents.
- Navigation rail desktop width was adjusted to 112px.
- Main content gap was adjusted down during layout tuning.
- Filter button was aligned with the main content right edge.
- Filter sidebar remains a right-side overlay.
- Attributes bar on mobile is desktop-like but horizontally scrollable and forced into one row.
- Attribute chevron is deliberately large and uses down/up direction:
  - collapsed = down
  - expanded = up
- Phone table: outer `.table-wrap` is the framed table container, inner `.table-scroll` owns horizontal scrolling, and pagination sits outside `.table-scroll` so page buttons stay visible while columns scroll.
- Statistical tables use the thick 2px `.table-wrap` frame. Two-table layouts such as Build Enclosures and Actions Starting position/Upgrades use the same visual frame on each panel even when the DOM wrapper class is page-specific.
- Map header tooltips are a frontend display convention: backend map values remain `Map 1a: Observation Tower`, while tooltips show `Observation Tower (1a)`.
- Phone table fixed width is currently `755px`; phone Card column is `110px`. Rank columns are hidden on phone layouts only; desktop and tablet retain them.
- Avoid broad visual refactors unless requested. The user is happy with the current look.

## Current Pages

### Cards Page

File:

```text
assets/js/pages/cards.js
```

Purpose:

Shows performance of cards when played/in hand.

Key table columns:

- rank
- Card
- delta in hand
- delta played
- Elo
- Playrate
- n played
- n seen
- Type

Default sort:

```js
currentSort = { col: 'delta_in_hand', dir: 'desc' };
```

Backend request:

- Uses same Cloud Function endpoint.
- No `stats_page` param needed for Cards because backend defaults to `cards`.

Default snapshots:

```text
https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/default-mw.json
https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/default-base.json
```

Filters:

- MW/Base toggle
- Player Elo min/max
- Opponent Elo min/max
- Maps
- Round
- Date range
- Completed and incomplete games included
- Type filter, client-side
- Search, client-side
- Minimum plays, client-side
- Attributes bar, client-side

The `#` rank is global across every loaded card that meets the current Minimum
plays threshold. Search, Type, and Attributes filters do not renumber ranks.

Round filtering is Cards-only. When fewer than all rounds are selected:

- Backend aggregation changes.
- Some stats become unavailable/hidden/disabled because they are not meaningful in played-round context.

### Opening Hand Page

File:

```text
assets/js/pages/opening-hand.js
```

Purpose:

Shows performance of cards when dealt/kept in the opening hand.

Backend page id:

```js
const STATS_PAGE = 'opening_hand';
```

Key table columns:

- rank
- Card
- delta dealt
- delta kept
- Elo
- Keeprate
- Kept
- Dealt
- Type

Important naming mapping:

```text
Cards page              Opening Hand page
-----------------------------------------
delta in hand        -> delta kept
delta played         -> delta dealt
Playrate             -> Keeprate
n played             -> n kept
n seen               -> n dealt
Elo                  -> player Elo when card was kept
Type                 -> same card type
```

Default sort:

```js
currentSort = { col: 'delta_played', dir: 'desc' };
```

In Opening Hand, `delta_played` means delta dealt and `delta_in_hand` means delta kept, to reuse the shared rendering/sorting concepts.

Default snapshots:

```text
https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/opening-hand/default-mw.json
https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/opening-hand/default-base.json
```

Filters:

- MW/Base toggle
- Player Elo min/max
- Opponent Elo min/max
- Maps
- Date range
- Completed and incomplete games included
- Type filter, client-side
- Search, client-side
- Minimum keeps, client-side
- Attributes bar, client-side

Opening Hand intentionally has no Round filter because opening hand is before rounds occur.

### Endgames Page

File:

```text
assets/js/pages/endgames.js
```

Purpose:

Shows performance and scoring distributions for Ark Nova endgame cards. Endgames are separate from the normal deck. Players start with two, may sometimes acquire or swap additional endgames, and can score one or more at game end.

Backend page id:

```js
const STATS_PAGE = 'endgames';
```

In-page views:

- `General`
- `CP distribution` table
- `CP distribution` graph, toggled by the graph icon inside the CP distribution tab cell
- `CP by map` table
- `CP by map` graph, toggled by the graph icon inside the CP by map tab cell

General table columns:

- rank
- Endgame
- delta scored
- delta dealt
- Elo
- Keeprate
- Scored
- Dealt
- CP

Important field mapping:

```text
Endgames frontend field  Meaning
--------------------------------
delta_in_hand            delta scored
delta_played             delta dealt
n_played                 n scored
n_seen                   n dealt
playrate_pct             keeprate
avg_cp                   average CP scored
```

Default sort:

```js
currentSort = { col: 'delta_played', dir: 'desc' };
```

Important Endgames definitions:

- `Dealt` counts appearances in the starting `endgame` array from non-conceded games.
- `Scored` counts appearances in `endgame_scores`.
- `Keeprate` is `Scored / Dealt`, so it can exceed 100% due to effects such as Elephants and Adapt.
- Keeprate's numeric value is not capped; only the blue bar width is capped at 100%.
- Percentage cells reserve a fixed non-shrinking label width, including on phones, so
  two- and three-digit percentages retain identical bar-track lengths.
- General-view desktop widths are `5/20/12/12/8/15/9/9/10` percent for
  Rank/Endgame/Delta scored/Delta dealt/Elo/Keeprate/Scored/Dealt/CP.
- Scored/CP stats use non-conceded games only.
- `delta dealt` uses raw non-conceded dealt rows for Base.
- Some MW logs attach the two initial `endgame` arrays to the opposite player. For each complete table,
  the backend chooses the same/swapped dealt-array orientation that produces more dealt/scored matches.
  Tied/ambiguous tables are excluded from MW `delta dealt`.
- After correcting MW dealt ownership, `delta dealt` uses no-Adapt rows where at least one initially
  dealt endgame also appears in that player's `endgame_scores`.
- `delta scored` is based on scored endgames, independent of whether the scored card was initially dealt.

Endgames filters:

- MW/Base toggle
- Player Elo min/max
- Opponent Elo min/max
- Maps

### Home Page

`assets/js/pages/home.js` is the default route and renders 12 aggregate fact tiles. It uses MW/Base plus Elo, map, date, and Completed-only filters. Its defaults are intentionally unrestricted Elo, unrestricted dates, incomplete games included, and all 25 known maps. Map chips are grouped into current maps, original Maps 1-8, and beginner Maps A/0. Backend `stats_page` is `home`, with public snapshots under `card-stats/home/`.

The daily refresh also publishes `card-stats/home/defaults.js`, containing both MW and Base payloads in `window.__ARK_NOVA_HOME_DEFAULTS__`. `index.html` loads this small asset before the app so default Home and MW/Base switching render immediately. Filtered requests still use the API, while the JSON snapshots remain the fallback.

On phones, Home keeps the navigation rail expanded and reserves its width in the layout. Leaving Home automatically unlocks and collapses the rail so it returns to overlay behavior on other pages.

### Sponsor Endgames Page

`assets/js/pages/sponsor-endgames.js` has `Conservation Points` and `Appeal` tabs backed by `stats_page: "sponsor_endgames"` and `sponsor_endgames_view: "cp" | "appeal"`. It hard-filters to non-conceded games and supports Elo, map, and date filters. The backend starts from distinct sponsor plays, left-joins one maximum endgame value per table/player/sponsor, and treats a missing endgame entry as zero. Thus average points and delta buckets use the played-card population. Configured theoretical values determine valid delta buckets; impossible logged values remain in the overall point average but are excluded from delta buckets. MW-only sponsor cards are omitted client-side in Base. There is intentionally no Elo result column or `avg_elo` payload field. Snapshots live under `card-stats/sponsor-endgames/{cp|appeal}/`.

### Icons Page

`assets/js/pages/icons.js` is routed at `#/icons` and uses backend `stats_page: "icons"`. It reads only the prepared Full Sample and hard-filters to non-conceded tables. One observation is one table/player. The 16 rows are Birds, Herbivores, Predators, Primates, Reptiles, Sea Animals, Bears, Petting Zoo Animals, Africa, Americas, Asia, Australia, Europe, Rock, Water, and Science.

Amount is the mean non-null final icon count. Buckets `0` through `6` are exact counts and `7+` includes every value at least seven. Null icon fields are excluded rather than converted to zero. Each bucket's displayed Delta, sample SD, CI count, and prevalence count come from the same filtered icon/player population; frequency divides the bucket count by that icon's non-null `n_total`. Delta buckets below 1,000 observations use the Sponsor Endgames insufficient-data presentation. Default order is Amount descending.

The full-width icon selector uses the PNG artwork under `assets/img/icons` and groups icons into Species, Habitat, and Other. It has the same 45px structural height as other tab/attribute bars, with compact chips and separators so the table starts at the shared vertical position. It has no all/none control or decorative brackets. Individual icons toggle independently; a fully selected group-button click clears that group, while a partial/empty group-button click selects the whole group. A group remains visually active until all its members are deselected. Selected artwork is full-color and deselected artwork is greyed. Base omits Sea Animals from the selector, table, graph, ranges, and ranking universe. Attributes separators and Icons group separators share the same fixed 2px rule.

The enlarged graph toggle at the selector's right edge swaps the table for an Endgames-style SVG line chart. It is centered within a flexible zone spanning from the final selector separator to the bar's right border. The selector defines the available lines, while the graph legend independently shows/hides those lines. Each icon has a permanent palette position assigned from the complete MW/Base icon order before selector filtering, so hiding lines never recolors survivors. Delta mode plots `Delta (0)` through `Delta (7+)`, omitting missing, impossible, and sub-1,000 points and breaking paths across gaps. Frequency mode plots the same buckets as percentages. Axes scale dynamically; tooltips contain icon, bucket, and value but no observation count.

The graph and legend keep a fixed height with a stable scrollbar gutter, so reducing the available icon lines does not resize or shift the chart. Icon bucket headers use the same styled header-tooltip event path as Sponsor Endgames.

Petting Zoo Animals supports only buckets 0-4 in MW and 0-3 in Base; later table cells are tooltip-free dashes and are absent from graphs and color ranges. The `#` column follows the current sort. Delta-column sorting places valid values first, sub-1,000 values second, and impossible/missing values last while respecting numeric direction inside the first two tiers; only valid values receive ranks. Frequency sorting similarly leaves impossible/missing rows unranked. Unranked rows display an em dash.

The page supports MW/Base plus player/opponent Elo, maps, and date filters, with no Completed-only control. Default snapshots are `card-stats/icons/default-{mw|base}.json`.

### Chip Selection

Every chip UI uses independent toggling: clicking an active chip deselects only it, and clicking an inactive chip selects only it. There is no all-selected-to-isolated shortcut. This applies to sidebar Maps/Rounds, Home maps, table Type filters, Card/Open Hand attribute chips, Combo Type and header filters, Sponsor/Endgame maps, and Icons. Existing all/none controls, empty-selection behavior, and attribute/type dependency rules remain intact.

Cards and Opening Hand render Species and Habitat choices as the same PNG artwork used by Icons rather than text chips. Their styled hover tooltips show the complete label; the underlying `America` metadata value is deliberately presented as `Americas`. Selection semantics and the text summaries on the popup-opening buttons are unchanged.

The deliberate exception is line-chart selection in Endgames CP distribution, Endgames CP by map, and Icons: when every available graph line is selected, clicking one line or legend item isolates it. Subsequent graph clicks toggle normally. This exception does not change selector-bar chip behavior.
- The right-aligned `Delta Elo / Frequency` switch is frontend-only, defaults to Delta Elo on mount, and retains its state across CP/Appeal, dataset, and filter changes.
- Frequency mode changes bucket headers to `f (value)`, displays two-decimal percentages, and sorts bucket columns by the displayed frequency. Its denominator is the sum of the card's theoretically valid bucket counts, so impossible logged values are excluded and the displayed valid buckets total 100% apart from rounding. Hover shows the exact `bucket count / valid-bucket total`.
- In Delta Elo mode, valid buckets with at least 1,000 occurrences expose their 95% Elo-delta confidence interval on hover. Values below 1,000 occurrences remain visible in grey parentheses and show `Insufficient data (fewer than 1,000 observations).` instead of a CI.
- Low-sample values use muted grey at 70% opacity so they are visually subordinate;
  the shared tooltip remains full-opacity.
- Impossible and unavailable buckets remain tooltip-free dashes.
- When a Sponsor bucket is the active sort, valid values rank first; insufficient values remain numerically sorted below them and impossible/missing values remain last. Insufficient and impossible/missing rows display an em dash instead of a rank. Frequency sorting likewise leaves impossible/missing rows unranked.
- Desktop widths are `5/25/10/15/15/15/15` for CP and `5/25/10` plus seven `8.5714%` buckets for Appeal.
- No Round filter
- No Completed games toggle exposed to the user
- No attributes bar
- No endgame-name search UI

CP distribution:

- Table view has columns `0`, `1`, `2`, `3`, `4`, and `CP`.
- CP percentage cells use the shared blue frequency scale with a fixed 0–50% domain.
- Graph view renders the same data as custom SVG with x-axis `0..4` and y-axis `0..60%`.
- Graph legend supports all/none controls plus per-endgame selection. If all lines are selected, clicking one legend entry or graph line isolates it.
- Deselected graph lines remain visible but greyed out.
- Hover tooltips show only the CP point nearest the pointer, not the complete series.
- Graph mode removes the table header entirely, so no empty header strip remains above the chart.

CP by map:

- Rows are endgames; columns are the 15 maps plus final `CP`.
- Map cells show average CP on that map.
- Map cells use the red/neutral/green semantic scale, normalized across all visible map columns together across the complete filtered CP-by-map result.
- Final `CP` column keeps the normal CP color styling.
- Map filter is hidden and ignored in this view because all maps must be shown as columns.
- Graph mode uses the same payload, with maps ordered `1a` through `8a`, then `9` through `14`, then `T1` on the x-axis and average CP on a dynamically padded y-axis. Missing points break line segments. Legend selection and nearest-point tooltips match CP distribution.
- The `Raw / vs. avg` switch is frontend-only and applies to table and graph. Comparison values are `map CP - CP`, display signed to two decimals, use zero-anchored capped Delta colors with one shared range across all map columns, and retain raw `CP` as the final reference column.
- CP-distribution frequency columns use the shared blue frequency scale with the fixed 0–50% cap.

Default snapshots:

```text
https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/endgames/default-mw.json
https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/endgames/default-base.json
https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/endgames/cp-distribution/default-mw.json
https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/endgames/cp-distribution/default-base.json
https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/endgames/cp-by-map/default-mw.json
https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/endgames/cp-by-map/default-base.json
```

### Maps Page

File:

```text
assets/js/pages/maps.js
```

In-page views:

- `Metrics`
- `Tournament H2H`

Metrics:

- Uses map codes as columns and metric names as rows.
- Maps General has four `- / O / +` segmented controls in this order: Map Pack 1, Map Pack 2, Legacy Maps, and Beginner Maps. `-` excludes the category, `O` includes it with ordinary maps, and `+` shows only that category. Defaults are Map Pack 1 `O`, Map Pack 2 `O`, Legacy `-`, and Beginner `-`, producing columns 1a-8a, 9-14, and T1. Selecting `+` forces the other three controls to `-`; ordinary maps remain visible whenever no category is in `+` mode. Exclude/Include/Only labels use the shared dashboard tooltip, not native browser titles. A larger Reset button sits on the same Metrics control row and restores these switch defaults plus the default metric ordering without changing sidebar filters. These are client-side controls because the backend payload already contains all 25 maps.
- Default sort is by `Turns` ascending. `Rounds` also sorts ascending because lower values are better; other metric rows sort descending.
- Percentage metrics display one decimal. The rows after `$ gained` are `$ gained (income)`, `$ spent (Animals)`, `$ spent (Build)`, `$ spent (Donations)`, and `$ spent (Range)`. Income reads `Money_gained_through_income`. `$ gained per turn` is the average of the per-player-game ratio `Money_gained / Number_of_turns`; it is not a ratio of aggregate averages. The four spending rows remain category averages divided by total spending and therefore display percentages despite their concise labels. Their per-map tooltips show the absolute category average with two decimals and no currency symbol. Zero denominators display `-`. Map headers use the global `Map name (code)` tooltip wording, and compact Games footer values use the dashboard tooltip with the full comma-grouped integer.
- Filters are MW/Base, Elo ranges, and date range only. No map filter, no round filter, no Completed games toggle.
- Metrics default date is `2026-01-13` onward because Map Pack 2 was added on January 13th, 2026. Home and both active Players views are unrestricted by date by default; the remaining dated pages default to `2025-01-01`.
- The visible end-date input stays blank by default; blank means no upper date limit.
- Map Pack 1 consists of Maps 9 and 10. Map Pack 2 consists of Maps 11-14 and T1. Legacy maps are Maps 1-8 (the non-alternate versions); beginner maps are Maps A and 0. Fill% is calculated from `Empty_hexes`: total hexes default to 42, Maps 5/5a/10 use 43, and Map 0 uses 39.

Tournament H2H:

- Uses `maps_view: "tournament_h2h"`.
- Shows a row-map vs column-map crosstable for asymmetric tournament games only.
- Tournament tables come from `ark-nova-stats-dashboard.dashboard_cache.tournament_tables`, a native BigQuery cache of the Google Sheets-backed `freestyle-190711.ark_nova.tournament_tables`.
- Only MW/Base applies; H2H ignores Elo, date, concede, map, and completed-game filters.
- Winner is determined by Score, then `Conservation_project_association_tasks`, then `Starting_position_in_first_round = Second player`; unresolved malformed games are excluded.
- Toggle modes are Win% and Elo delta.
- Win% cells show percentage plus exact `wins-losses`; Elo cells show signed average delta plus `n = X`.
- The rightmost Overall column is wider and separated with a double border.
- Matchup cells and Overall use separate color populations. Win% matchups normalize
  across matchup rows; Elo matchups use the capped adaptive Delta scale. Overall
  normalizes independently across Overall rows and uses CP-style orange-to-green text
  in both modes, without a tinted background.
- Rows default to natural map order and can be ranked descending by the active Overall metric; missing Overall values remain last. H2H row height tracks the rendered map-column width through a scoped `ResizeObserver`.

### Combos Page

`assets/js/pages/combos.js` is routed at `#/combos` and uses backend `stats_page: "combinations"` with four equal-width views:

- `card_card`: unordered same-player card pairs. Card 1 is alphabetically first; actual delta is the player's delta when both were played, and Synergy is actual minus the sum of both individual card deltas.
- `card_map`: card/map rows for the 15 standard maps. Synergy is map-specific delta minus the card's general delta.
- `card_round`: card/round rows for rounds `1` through `5` and a `6+` bucket. Synergy is round-specific delta minus the card's general delta.
- `card_endgame`: a played card paired with an endgame scored by the same player in the same non-conceded game. Delta Sum is the filtered card-play baseline plus the scored-endgame baseline; Delta Actual is the exact pair mean and Synergy is Actual minus Sum.

Played cards are deduplicated per table/player/card/round before aggregation. All six type combinations are supported for Card + Card; self-pairs and unobserved pairs are omitted, and individual baselines use the same active filters as interaction rows. Frontend defaults to minimum 1000 plays and Synergy descending. Every card/endgame entity cell displays its general Delta beneath its name. Card + Card supports one-card or exact unordered-pair header filtering.

Sidebar filters are view-aware: Card + Card shows Map and Round, Card + Map hides Map and shows Round, and Card + Round shows Map and hides Round. Card + Map and Card + Round provide multi-select header filters for their represented dimension. Card + Map's Map header is filter-only; a narrowed selection replaces its filter icon with an `N/15` chip, and popup map chips expose styled full-name tooltips. Card selectors search both display names and aliases from `cards_altnames.csv`; their single-choice popup uses the same Inter 12px typography and row spacing as Attributes/Abilities. A selected card leaves the header label unchanged and replaces only the search icon with a muted-red clear X. Card + Map displays map names as `Observation Tower (1a)` while retaining raw full names for matching. Card + Card's six-value Type popup includes all/none controls and spans the Played plus Type columns exactly. Fixed-position Type popups are flush with their headers, follow layout/scroll changes, and close only after the complete popup leaves the viewport. Empty Type, Map, or Round selections return no rows, and `6+` means round 6 or later.
The Card + Round header uses the same active-filter treatment as Card + Map: the header and filter button receive the active state, and the button displays the selected-round count as `N/6` while narrowed.

Card + Card rows remain canonical unordered alphabetical pairs in the payload. When a
Card 1 or Card 2 header filter is selected, the frontend projects the matching card
and individual Delta into that chosen display slot. With no selection, body order
remains alphabetical; global rank calculation continues to use canonical pair
identity. Card/Card 1/Card 2 headers are filter-only and are deliberately not sortable.

The default combination snapshots are generated with `n_played >= 1000`. They retain
`combination_ranges`, calculated from the complete untrimmed population, so the
client-side color scale does not change merely because low-play rows were omitted.
While a default snapshot is active and Minimum plays is at least 1000, sorting,
pagination, card selection, and header filtering stay client-side. If a sidebar
filter is applied or Minimum plays is lowered below 1000, the page switches to the
server-paged API. Paged requests return at most 25, 50, or 100 rows, plus `page`,
`page_size`, `total_rows`, global ranks, `combination_ranges`, and the option metadata
needed by the visible filters. This keeps filtered responses small without changing
the displayed rank or color semantics.

The paged request fields are `combination_page`, `combination_page_size`,
`combination_sort`, `combination_sort_dir`, `combination_min_plays`,
`combination_pair_types`, `combination_card_types`, `combination_primary`,
`combination_secondary`, `combination_header_maps`, and
`combination_header_rounds`. The response marks this mode with
`combination_paged: true`; its `data` array contains only the requested page.
The page, page-size, and minimum-play request fields are optional and use the
backend defaults `1`, `50`, and `1000` when omitted; explicitly invalid values
are rejected.
Minimum-plays and multi-chip header changes are debounced by 250 ms, while sorting
and page changes request immediately. Stale responses are ignored by the existing
request-token guard.

All four tables use 100%-total desktop allocations and a `1080px` readability floor. Card + Card and Card + Endgame use `5/18/18/11/11/11/7/9/10`; Card + Endgame has independent non-sortable Card and Endgame searches, puts each general Delta beneath its name, uses only the card's three-value Type filter, and hides Completed-only because scored pairs are inherently complete. Its Round filter applies to the card play.

Default snapshots:

```text
card-stats/combinations/card-card/default-{mw|base}.json
card-stats/combinations/card-map/default-{mw|base}.json
card-stats/combinations/card-round/default-{mw|base}.json
card-stats/combinations/card-endgame/default-{mw|base}.json
```

Combo result metadata uses `combinations` on desktop and the shorter `combos` on phones.

### Build Page

`assets/js/pages/build.js` is routed at `#/build`; backend page id is `build`. The page has `Enclosures` and `Hexes` tabs. Enclosures uses joined Full/Log observations at one player/game row. Standard rows are sizes 1-5 with exact buckets 0-4 and `5+`; unique rows are Aviary, Reptile House, Petting Zoo, Large Aquarium, and Small Aquarium with No/Yes buckets. Only Petting Zoo has Empty, defined exactly as built once with `COALESCE(Petting_Zoo_icons, 0) = 0` and no Horse Whisperer in `played_sponsors`.

Elo Delta and Frequency share the two-table layout. Delta cells expose the usual CI and use the 1,000-observation sufficiency rule. Ordinary frequency denominators are non-null observations for that enclosure field. Empty Petting Zoo frequency uniquely divides empty Petting Zoos by built Petting Zoos and uses violet. Standard enclosures use one shared bucket color range across `0-5+`; unique enclosures use one shared range across No/Yes/Empty, except the violet Empty Petting Zoo frequency exception. Enclosures keep the Completed games only control; when enabled, `completed_only=true` limits the table to rows whose derived `table_conceded` value is zero. The default Delta view is unrestricted and the default Frequency view enables this control. Default snapshots live under `card-stats/build/enclosures/{delta|frequency}/default-{mw|base}.json`.

Hexes uses prepared Full Sample rows from non-conceded tables only; it has no Completed games only control. Collapsed `Empty_hexes` buckets are `0`, `1-5`, `6-11`, `12-17`, `18-23`, and `24+`. Each default and filtered response contains both the six collapsed rows and exact `0` through `23` plus `24+` in `expanded_data`, so the attached arrow changes the table locally without another request. The API has no expansion request flag; it always calculates both populations for Hexes. The arrow points down to expand and up to collapse. The state is shared across Elo Delta/Frequency and MW/Base switches. Columns are the 15 map columns plus a final raw `Avg` reference. It has `Elo Δ / Frequency` and `Raw / vs. avg` switches. In comparison mode, each map cell shows `map value - row Avg`; `Avg` remains the raw reference. Delta cells use CI and the 1,000-observation rule in raw mode. Frequency cells show exact `count / denominator` tooltips. Expanded Hexes blue frequency cells use a fixed `0–20%` color domain; collapsed Hexes uses the normal `0–50%` domain. The violet Avg frequency styling is unchanged. Default snapshots live under `card-stats/build/hexes/{delta|frequency}/default-{mw|base}.json` and contain both bucket modes.

Prepared Logs includes numeric fields for all five standard sizes plus `aviary_built`, `reptile_house_built`, `petting_zoo_built`, `large_aquarium_built`, and `small_aquarium_built`.

### Predictors Page

`assets/js/pages/predictors.js` is routed at `#/predictors`; backend page id is `predictors`. It has three equal tabs: General, Icon, and Specific.

General and Icon are backend-backed. One observation compares a player to their opponent in the same non-conceded table. A condition includes only rows where the player value is greater than the opponent value; ties do not count. Rows display the condition in the PDF-defined order plus Elo Delta with the normal CI tooltip and 1,000-observation sufficiency styling. Filters are player/opponent Elo, Maps, and Date Range. There is no Completed toggle for General/Icon.

Specific is backend-backed and has a client-side `Elo Δ / Frequency` switch. Delta uses the normal CI and 1,000-observation behavior. Frequency is `count / denominator`, where denominator is every filtered player-game observation for that condition; it uses exact count tooltips and the standard blue `0–50%` color domain. Switching metrics does not request data or alter the Completed games only toggle. Unchecked completion includes recorded values from conceded and non-conceded games, while checked applies `table_conceded = 0`. MW has 22 rows; Base omits More reefers and Round 1: Humphead Wrasse and therefore has 20. Insufficient Delta and Frequency value cells use the shared styled tooltip path.

Specific conditions are Triggered endgame; More endgame points; More endgame CP; More ingame CP; More reefers; More small/medium/large animals; Round 1 Upgrade, Project, Release, 2+ association actions, and Humphead Wrasse; Round 1/2 New Zealand Fur Seal; First to 5/8 CP with and without the exclusive university/partner-zoo bonus; No project/sponsor in the starting hand; No sponsor in the starting hand with Sponsors at 5; and that final condition further restricted to second player, Association at 2, and Sponsors at 5.

For Specific only, a checked Completed games only toggle sends `completed_only=true`, bypasses the default snapshot, and applies the completed-table predicate in the backend. General and Icon do not expose this toggle and remain hard-filtered to non-conceded tables.

Endgame CP is sponsor CP plus scored endgame-card CP. Endgame points value each CP at 3 and sponsor endgame appeal at 1. Ingame CP is `Conservation - endgame CP`. Threshold timing uses the first `cp_history.move` reaching the target; reaching it when the opponent never does counts as first. Sponsor endgame values are deduplicated per sponsor before summing.

Reefer, animal-size, Project, and Sponsor classifications come from the canonical `cards_attributes.csv`. The same file is packaged with the Cloud Function and its parsed groups are published to `card-stats/metadata/cards-attributes.json` during daily refresh. Keep the frontend and backend copies synchronized when changing card metadata; ordinary requests use the cached parsed copy and do not fetch the CSV repeatedly.

Default snapshots live under:

```text
card-stats/predictors/general/default-{mw|base}.json
card-stats/predictors/icon/default-{mw|base}.json
card-stats/predictors/specific/default-{mw|base}.json
```

### Actions Page

`assets/js/pages/actions.js` is routed at `#/actions`; backend page id is `actions`. It has four equal tabs: Starting position, Upgrades, Upgrade order, and Upgrades by map.

Starting position shows two non-sortable tables. The action-strength table compares Association, Build, Cards, and Sponsors at starting strengths 2-5. The comparison table covers Higher Association, Higher Build, Higher Cards, Higher Sponsors, and First player, with a double separator before First player. Delta cells use the usual CI and 1,000-observation rules, with one shared range across comparable Delta columns. Insufficient-data cells use the shared dashboard tooltip.

Upgrades has no metric switch. Its two equal-width tables cover number of upgrades (`0-5`) and action upgrades (Animals, Association, Build, Cards, Sponsors); each table has three equal columns for its label, Elo Delta, and Frequency. One non-conceded payload supplies both metrics. Delta keeps CI/insufficient styling, while Frequency shows percentages with exact count tooltips. The Upgrade-count table uses the standard blue `0-50%` domain; the action-upgrade table uses `0-100%` because its normal values frequently exceed 50%. Its only default snapshots are `actions/upgrades/delta/default-{mw|base}.json`.

Upgrade order has the same mode switch, one row per action, and columns for 1st through 4th upgrade. The left-side swap-axes button transposes the table locally into four timing rows and equal-width columns for Upgrade timing plus the five actions; it remains transposed across Elo Delta/Frequency and MW/Base changes, and resets on a new Actions mount. Elo values and CI metadata are unchanged. In the normal orientation, frequency divides by all upgrades of that action. In the transposed orientation, frequency divides by all upgrades occupying that timing slot. The tooltip always shows the applicable numerator and denominator, and swapping never requests data.

Upgrades by map uses the map-grid framework with `Elo Δ / Frequency` and `Raw / vs. avg` switches. Rows are the five action upgrades, map columns are `1a-8a, 9-14, T1`, and the final `Avg` column stays as the raw reference when comparison mode is active. Frequency denominators are the scoped non-conceded player-game observations for that action row: each map column divides upgraded observations on that map by all scoped observations on that map, while `Avg` divides upgraded observations overall by all scoped observations overall. Frequency `vs. avg` is calculated entirely in the browser as the map percentage minus the Avg percentage; changing only Raw/`vs. avg` must rerender the loaded payload and must not issue a request. Its tooltip continues to show the raw map numerator and denominator.

Default snapshots live under:

```text
card-stats/actions/starting_position/delta/default-{mw|base}.json
card-stats/actions/upgrades/delta/default-{mw|base}.json
card-stats/actions/upgrade_order/{delta|frequency}/default-{mw|base}.json
card-stats/actions/upgrades_by_map/{delta|frequency}/default-{mw|base}.json
```

### Conservation Page

`assets/js/pages/conservation.js` is routed at `#/conservation`; the backend page id is `conservation`. Its API subview is `conservation_view: "projects" | "project_rewards" | "cp_rewards"`. The page occupies the former Projects nav position because all three tabs describe different conservation mechanisms in Ark Nova.

#### Gameplay concepts

Conservation Points (CP) are the green-track points that eventually meet the opposing Appeal track to determine final score. Three related game events must not be conflated:

1. A player supports a conservation project through an Association action. This increments `Conservation_project_association_tasks` in Full Sample.
2. After supporting a project, the player takes one project reward. Log Sample records that event in `project_rewards`.
3. When the player's CP marker first reaches the 5 CP and 8 CP spaces, the player chooses a separate CP-track bonus from an offered pool. These choices are stored in the CP bonus fields and are not project rewards.

A player can support at most seven projects, so the Projects tab deliberately has the complete fixed domain `0-7`. A project reward event has `cp`, `round`, `reward`, `order`, and `project`, but this dashboard uses only `reward` and `order`. `order=1` means the reward taken after the player's first supported project; it does not mean round one. Likewise, orders 2-7 describe the sequence of that player's project rewards, not game rounds.

#### Prepared data and API flow

Source BigQuery tables are read-only. Daily refresh copies the required fields into backend-owned derived tables. Prepared Full Sample contains the complete source row plus derived table-level `table_conceded`. Prepared Logs includes `project_rewards`, source ``5cp_bonus`` as `five_cp_bonus`, source ``8cp_bonus`` as `eight_cp_bonus`, `chosen_5cp_bonus`, `chosen_8cp_bonus`, and `cp_history`. The two aliased availability fields are arrays of offered reward strings; the chosen fields are the one reward actually taken.

The flow is:

```text
read-only Full/Log Sample
  -> backend-owned prepared tables with table_conceded
  -> Conservation SQL aggregation
  -> MW/Base Cloud Storage snapshots or filtered Cloud Function response
  -> one frontend payload per tab
  -> client-side metric/scope/comparison switches
```

The switches do not issue requests. A tab, dataset, or applied sidebar-filter change loads a new payload. During daily maintenance, three worker threads generate the six Conservation snapshots concurrently with the existing sequential page refreshes; this prevents the new queries from extending the already long refresh beyond the Cloud Function timeout. Snapshot paths are:

```text
card-stats/conservation/projects/default-{mw|base}.json
card-stats/conservation/project-rewards/default-{mw|base}.json
card-stats/conservation/cp-rewards/default-{mw|base}.json
```

#### Projects

Projects is a fixed eight-row map table. `count_value` is the exact integer value of `Conservation_project_association_tasks`. Columns are Count, the 15 supported maps, and Avg. It uses a `12% / 15 x 5.5% / 5.5%` allocation.

All Projects observations are from non-conceded tables. There is consequently no Completed games only toggle. The filters are player/opponent Elo, Maps, and Date Range.

For a row `c` and map `m`:

```text
delta(m,c) = average elo_delta among scoped player-games on m with project count c
frequency numerator(m,c) = scoped player-games on m with project count c
frequency denominator(m,c) = all scoped player-games on m
```

Avg repeats these formulas across every selected map. Raw Delta uses its observation count for CI and the 1,000-observation rule. The Projects Avg Delta cell also exposes CI metadata, uses the special orange-green Avg scale, and shows the same insufficient-data tooltip when needed. Frequency has no CI or sufficiency suppression, shows the exact numerator/denominator tooltip, uses the standard blue `0-50%` domain, and reduces numerical body cells by 1px to keep dense percentage tables legible while leaving the Count label column at normal size. Avg keeps the special orange-green Delta and violet Frequency treatment.

Example: if 320 of 1,000 completed player-games on Map 1a supported exactly three projects, the Map 1a Frequency in row 3 is `320 / 1,000 = 32.00%`.

#### Project rewards

Project rewards contains six generic choices followed by map-specific choices. Generic rewards can normally occur across maps; map-specific choices exist only on their named map. The table always keeps the two sections contiguous and places a double separator before Marketing (1a). Sorting is performed within each section. Overall is the default descending sort; Reward uses the configured game order rather than alphabetical order.

The exact frontend/raw mappings are:

| Frontend | Log `project_rewards.reward` | Scope |
|---|---|---|
| Snapping | Snapping | generic; unavailable on T1 |
| 2-size | 2-size | generic; unavailable on Map 13 |
| 5 money | 5 Money | generic |
| Worker | Worker | generic |
| 12 money | 12 Money | generic |
| 3 X-tokens | 3 X Token | generic |
| Marketing (1a) | Marketing | Map 1a |
| 1 CP (2a) | 1 CP | Map 2a |
| Determination (3a) | Determination | Map 3a |
| University (4a) | University | Map 4a |
| Unique building (5a) | Aviary/Reptile House | Map 5a; one literal raw value |
| Clever (6a) | Clever | Map 6a |
| Pouching (7a) | Pouching | Map 7a |
| Partner zoo (8a) | Partner Zoo | Map 8a |
| Token (9) | Remove Continent Cube | Map 9 |
| 2 reputation (10) | 2 Reputation | Map 10 |
| Upgrade (11) | Upgrade | Map 11 |
| Animal magnet (12) | Animal Magnet | Map 12 |
| Adapt (13) | Adapt 3 | Map 13 |
| Person sponsor (14) | Play a person sponsor | Map 14 |
| Draw + ability (T1) | Draw from range | T1 |
| 3 reputation (T1) | 3 Reputation | T1 |

Delta Overall averages `elo_delta` whenever that reward was selected. Delta order columns average only reward events at that exact `project_rewards.order`. Overall Delta uses its own color range, separate from the order columns. Delta defaults to conceded and non-conceded games; its visible Completed games only toggle changes the Delta population to `table_conceded=0`.

Frequency uses a deliberately different, always non-conceded population. Overall asks “in how many applicable player-games was this reward taken?”:

```text
f Overall numerator = distinct applicable player-games containing the reward
f Overall denominator = all applicable scoped player-games
```

For a map-specific reward, “applicable” means only its map. Generic rewards use all selected maps. If Map 13 is the only selected map, 2-size is unavailable and displays `-`; if T1 is the only selected map, Snapping displays `-`. A map-specific row also displays `-` when its map is not selected. These are unavailable populations, not zero-percent observations.

Order Frequency answers a different question: “when this reward was taken, at which project number was it taken?” Its denominator is reward occurrences, not player-games:

```text
f nth numerator = completed-table occurrences of this reward with order=n
f nth denominator = all completed-table occurrences of this reward
```

Therefore orders 1-7 sum to 100% apart from display rounding. For example, if a reward has 100 occurrences split 60/30/10 across orders 1/2/3, the cells are 60%, 30%, 10%, and 0% thereafter. If 250 distinct player-games take that reward among 1,000 applicable player-games, f Overall is 25%; that calculation is independent of the order distribution.

Frequency cells remain visible at small denominators and have no CI. f Overall uses a blue `0-100%` domain; the seven order columns share the dashboard's `0-50%` domain. Delta cells use CI and become insufficient below 1,000 observations. Exact duplicate malformed reward events are deduplicated by table, player, normalized reward, and order before aggregation.

#### CP rewards

At both 5 CP and 8 CP the player sees three bonus options. `five_cp_bonus` and `eight_cp_bonus` record the two random alternatives; the fixed third option, 5 money, is implicit and is added by the query at both thresholds. `chosen_5cp_bonus` and `chosen_8cp_bonus` record the selected option. Availability and choice are intentionally separate: a non-money reward cannot enter a Frequency denominator merely because it exists in the game.

The exact mappings are:

| Frontend | Raw bonus string | Dataset |
|---|---|---|
| University | 1 University | MW + Base |
| Partner zoo | 1 Partner-Zoo | MW + Base |
| Posturing 3 | 3 bonus-kiosk-pavilion | MW only |
| x2 | 1 Multiplier | MW + Base |
| 10 money | 10 money | MW + Base |
| 2 reputation | 2 reputation | MW + Base |
| 3 X-tokens | 3 xtoken | MW + Base |
| 3-size | 1 size-3 | MW + Base |
| Marketing | 1 bonus-sponsor-gray | MW + Base |
| Extra Shift | 1 bonus-extra-shift | MW only |
| Bonus icon | 1 bonus-icon | MW only |
| 3 cards | 3 take-in-range-or-deck | MW + Base |
| Snap + Handsize | 1 bonus-increased-hand | MW only |
| Ignore 3 | 3 bonus-ignore-conditions | MW only |
| Adapt 3 | 3 bonus-scoring-cards | MW only |
| 5 money | 5 money | MW + Base |

MW has 16 configured rewards. Base omits the six MW-only rewards and has 10. Each reward has three backend rows, with `scope` equal to `5`, `8`, or `combined`; the frontend switches locally between them.

Delta includes a player-game when the matching chosen field contains the reward. Combined Delta includes a reward chosen at either threshold but deduplicates it to one player-game/reward observation because a reward cannot normally be claimed twice.

Frequency measures choice only when the player had full choice. Full choice means the player reached the threshold before the opponent. For each player and threshold, the backend finds the first `cp_history.move` where CP is at least 5 or 8. The player qualifies when their move is lower than the opponent's, or when the opponent never reaches the threshold. Equal moves do not qualify. A Frequency opportunity then exists only if the reward also appears in that threshold's availability array.

```text
frequency numerator = eligible offered opportunities where the reward was chosen
frequency denominator = eligible offered opportunities for the reward
```

The `5` and `8` modes use one threshold. `combined` unions the threshold opportunities rather than collapsing them by player-game. The always-offered 5 money can therefore contribute one 5 CP opportunity and one 8 CP opportunity in the same game. Other rewards are never offered at both thresholds. Example: if 5 money has 80 eligible 5 CP offers and 70 eligible 8 CP offers, with 30 and 20 choices respectively, combined Frequency is `(30+20)/(80+70) = 33.33%`.

The table uses the same map-grid allocation as Conservation Projects: Reward at 12%, each map at 5.5%, and a rightmost AVG column at 5.5%. AVG aggregates every map and uses the same special Avg styling as Projects: orange-green for Delta and violet for Frequency, with matching CI color metadata in Delta mode. AVG body values are normal weight rather than bold. Its header keeps the tooltip and sort indicator in a compact inline layout so it does not create horizontal overflow. Map columns aggregate only that map. Raw shows direct values. `vs. avg` displays `map value - AVG` while leaving AVG unchanged. For example, a Map 1a Delta of `+2.400` and AVG Delta of `+2.050` produces `+0.350` in comparison mode. The same subtraction applies to percentage points in Frequency mode.

Delta cells use their chosen-observation counts for CI and insufficiency. Frequency has no CI or small-denominator suppression, uses exact count tooltips and the blue `0-50%` domain, and labels its meaning with `% (chosen when having full choice between all 3 options)`. In Frequency mode only, CP Rewards reduces numerical body cells by 1px; the Reward label column keeps the normal body size. Frequency comparison cells remain blue rather than using Elo Delta red/green, because they are percentage-point differences. The CP rewards sidebar has player/opponent Elo, Date Range, and Completed games only; it intentionally has no map filter because all map columns remain comparable in one table. The completion toggle applies to both metrics.

### Workers Page

Workers is routed at `#/workers` and uses `stats_page: "workers"` with
`workers_view: "general" | "two_cp_worker"`. It uses the Actions → Upgrades by
map table framework: a fixed-order label column, all 15 map columns, a final
`Avg` reference column, `Raw / vs. avg`, and `Elo Δ / Frequency`. Worker rows
are deliberately not sortable because their order is part of the gameplay
meaning.

General reads `Association_workers` from prepared Full Sample. This is the
number of workers a player took overall, with valid values 1–4. It is always
restricted to non-conceded tables. The rows are exactly `1`, `2`, `3`, and `4`,
and the Frequency denominator is the valid 1–4 population for the selected
scope. Delta averages `elo_delta` among the matching worker-count observations;
CI sample size counts matching observations with non-null `elo_delta`.

The Workers header also documents the gameplay timing convention: `Last worker:
0 CP - 1 CP - 2 CP`, with 1 CP underlined once and 2 CP underlined twice. Map
headers use single underlines for 2a, 4a, 5a, 8a, 11, 12, 14, and T1, and
double underlines for 6a, 7a, and 10.

In General + Frequency, a separated `n (Avg)` row reports the arithmetic mean
of `Association_workers` among the valid 1–4 population for each map and for
the overall scope. It is prevalence rather than a percentage: map cells use a
muted light-blue scale and the overall cell uses a light-violet scale. In
`vs. avg`, map values subtract the overall mean while the overall cell remains
the raw reference. The row is hidden in Delta mode and on 2 CP Worker.

2 CP Worker reads prepared Logs’ `two_cp_worker` field. `false` means the player
chose the upgrade at the 2 CP decision and `true` means the player chose the
worker. Rows are always `Upgrade`, then `Worker`. Null or malformed values are
excluded because an early quit can leave the choice unset. The Frequency
denominator is the valid Boolean population. Unlike General, this tab exposes
the optional `Completed games only` toggle: unchecked includes valid conceded
and non-conceded tables, while checked adds `table_conceded = 0`.

For both tabs, the tabs are equal-width, map header tooltips use the global
`Map name (code)` wording, and the 2 CP Worker table header is shortened to
`2 CP`. Map cells use only that map’s player-game observations. Avg uses
the complete selected map scope. Raw Delta cells use the normal CI and
fewer-than-1,000 rule; Avg Delta uses the special orange-green Avg scale and
the same CI metadata. Raw Frequency uses the fixed 0–50% blue scale; Avg
Frequency uses the violet reference scale. Frequency cells expose the exact
count/denominator tooltip through the shared dashboard hover behavior.
`vs. avg` is `map value - Avg`, and its signed Frequency values remain blue
percentage-point comparisons. Signed
Frequency comparisons use two decimals below an absolute value of 10 and one
decimal at 10 or above so the sign and value fit dense cells.

Default snapshots are:

```text
card-stats/workers/general/default-{mw|base}.json
card-stats/workers/two-cp-worker/default-{mw|base}.json
```

General snapshots are hard-filtered to non-conceded tables. 2 CP Worker
snapshots include all valid Boolean choices with the completion toggle off.
Filtered requests include Elo bounds, date range, dataset, view, and the
optional completion flag in their cache key. Source Full Sample and Log tables
remain read-only; prepared tables and snapshots are backend-owned derived
data.

### Players Page

Players is routed at `#/players` and uses `stats_page: "players"` with
`players_view: "general" | "comparison" | "arena"`. Tabs are ordered General,
Comparison, Arena and are equal width. General and Comparison are active;
Arena remains a visual placeholder.

General displays six equal-width columns: Metric, Player, All, Winners, Experts,
and Masters. Its 64 rows are the Maps/Metrics rows from Turns through Science
icons, excluding Games and Rounds, with `Breaks triggered` and `Break%` inserted
after Turns. `Breaks triggered` reads `Number_of_breaks_triggered` and `Break%`
is `100 * Number_of_breaks_triggered / total_breaks`; an invalid or zero
denominator displays `-`. The displayed money metric is `$ gained per turn`,
calculated as the average of per-player-game `Money_gained / Number_of_turns`.

All populations are player-game rows from non-conceded tables. The Player
column is the selected exact `player` value. All is every scoped row. Winners
require the player row to have `Game_result = 1` while the other row in the same
table has `Game_result = 2`. A table where both rows have result 1 is a draw and
does not enter Winners, although it remains eligible for All, Experts, or
Masters. Experts use player `elo >= 500`; Masters use player `elo >= 700`.
Malformed result combinations do not qualify as wins.

Players filters are opponent Elo, maps, date range, and Last X games. The
opponent Elo minimum is visually empty and means `0`; this is a Players-specific
default. There is no player Elo filter and no completion toggle because
concession is always excluded. Last X selects the selected player's newest
qualifying rows by `game_ended_at DESC` and deterministic table-id order. Both
date fields are empty by default. Date Range and Last X are strictly mutually
exclusive: typing either date boundary disables both pointer and keyboard input
for Last X, while typing Last X disables both date inputs. Clearing the active
field re-enables the other control immediately. Disabled fields serialize as
`null`, and the backend rejects any manually constructed request that contains
both a date boundary and Last X. Reset clears both mechanisms, changes only
filters, and preserves selected players.

The General API accepts `players_player` and `last_x_games`; its payload includes
`player_game_count` and absolute tooltip fields for the four spending-share rows.
Body value tooltips are otherwise absent, and an empty Player value is `-` with
no tooltip. Player colors use the normal Elo-delta diverging family without a
fixed clamp; each metric row has its own range. `Turns` has
`lower_is_better: true`, so its color direction is reversed without changing its
number or sort behavior. The current card labels are `Cards drawn (deck)` and
`Cards drawn (Range)`.

Comparison accepts `players_players`, an ordered array of one to five unique
exact player names. It returns `players: [{name, game_count}]` plus metric rows
whose `values` arrays contain each selected player's value and spending tooltip
value. All selected players share the active filters, while Last X is applied
independently to each player's newest rows. Selecting from any search bar adds
the player to the leftmost available column; clearing a selection compacts the
remaining players. Comparison prevents duplicate selections and begins color
coding only after at least two players are selected. Its status text is
`Number of games considered: p1 (x1), p2 (x2), ...`.

Default snapshots are:

```text
card-stats/players/general/default-{mw|base}.json
```

The large player directory is separate and generated during daily refresh:

```text
card-stats/players/index/default-{mw|base}.json
```

It is a sorted, non-conceded, dataset-specific list. The frontend downloads it
when Players first opens, then reuses it through memory and versioned Cache
Storage; searches begin at three characters and show a bounded alphabetical
suggestion list. The public cache bucket allows cross-origin GET/HEAD requests
from the static site and local development servers. If direct snapshot delivery
fails, the frontend sends `players_index: true` with `stats_page: "players"` and
`is_mw`; the Cloud Function reads the same cache object and returns it through
its CORS/gzip response path. This fallback never queries BigQuery. Index loading,
failure, and retry states remain visible instead of becoming an empty directory.
Searching does not query BigQuery per keystroke.

Interactive statistics read the backend-owned
`dashboard_cache.players_stats_prepared` table, not Full Sample directly. The
daily refresh derives one narrow player-game row per source observation,
including table-level concession, winner status, all 64 metric values, the four
raw spending amounts, timestamp, and table ID. It is partitioned by game date and
clustered by player, dataset, map, and opponent Elo. Player leads because exact
player lookup is the latency-sensitive path. General uses one aggregate
for All/Winners/Experts/Masters and a separate exact-player aggregate. The player
filter is applied before `ROW_NUMBER()`, so Last X never ranks unrelated players.
When both components are missing they are submitted concurrently and merged into
the established payload shape.

Players component caches are data-versioned. A baseline key contains dataset,
maps, opponent-Elo bounds, and date bounds. A selected-player key adds the exact
player and Last X. The ordinary full-response filter cache remains the first
repeat-request layer; Comparison includes its normalized selected-player set and
Last X in its response cache key. With default filters, General takes its
comparison columns from the daily Players snapshot and queries only the selected
player. Changing a player under unchanged custom filters reuses the baseline
component. Exact repeats avoid BigQuery.

The same refresh also builds
`dashboard_cache.players_default_prepared`, one compact aggregate row per exact
player and dataset for the default population (valid maps, opponent Elo at least
0, no date restriction, non-conceded). Default-filter General selections and
default-filter Comparison lookups read this table, so they do not rescan the wide
player-game table. Last X and any custom filter intentionally fall back to
`players_stats_prepared` because they require game-level rows.

The suggestion list is a viewport-positioned overlay outside the table scroll
container, so it cannot be clipped by the sticky header or table frame. Player
names are selected through escaped data attributes rather than executable inline
strings. The table's inner scroll container owns the viewport height and vertical
scrollbar, exposing the complete metric catalog while the header remains sticky.
When no player is selected, null Player values display `-`; only real numerical
zero values display as zero. The player search popup is a viewport-positioned
overlay and closes immediately after selection.

Across the dashboard, signed Frequency comparison values use an adaptive
display precision: absolute values below 10 percentage points show two decimals;
absolute values of 10 or more show one decimal. This affects only signed
`vs. avg` percentage-point displays, not raw Frequency percentages or Elo
Delta values. The sign, including the `±` zero form, is preserved.

Elo Delta cells use a separate global precision rule: values with absolute
magnitude below 10 display three decimals; values at or above 10 display two
decimals. This applies to Elo Delta cells and insufficient-data cells across all
pages, but not to ordinary Maps metrics, money, CP, or Frequency values. Maps
Metrics ordinary numeric values with three integer digits retain two decimals
so values such as `114.24` remain visible.

#### Conservation null and malformed-data rules

- A missing numeric value does not enter a Delta mean or CI.
- A zero or missing Frequency denominator renders `-`, never an invented 0%.
- A missing CP threshold move cannot qualify as first to that threshold.
- A missing opponent threshold move qualifies only when the player has a valid threshold move.
- A non-money CP reward absent from the availability array cannot enter the Frequency numerator or denominator even if malformed chosen data claims it; 5 money is the documented fixed exception and is injected as an opportunity at both thresholds.
- Configured rewards remain present when they have no data, so MW/Base and filtered layouts do not shift.
- Explicitly impossible map/reward combinations render `-`.
- Source BigQuery tables are never updated; only prepared tables, cache blobs, and snapshots are replaceable derived artifacts.

### Shared Table UI

`app.js` observes rendered `.rank-cell` elements and reduces only overflowing rank text, down to a legible minimum; page modules do not need their own four-digit-rank handling. Card-header search buttons keep their compact glyph but use a larger invisible hit target extending mainly to the left. Sortable tables should add the shared `sorted` class to the active `<th>`; narrowed filters use `--accent-filter` instead.

Default sort highlighting is hidden during loading and applied only after data has loaded. Cards, Opening Hand, and Combos distinguish a genuine empty filter result from a Minimum plays/keeps threshold that removed otherwise-valid rows; only the latter temporarily pulses the minimum input, stopping after five seconds or immediately on focus.

Every Filter-bar player/opponent Elo minimum serializes a cleared input as numeric `0`. Initial and Reset values remain page-specific (normally 300); clearing a minimum deliberately prevents use of a 300-minimum default snapshot.

Cards, Opening Hand, and all Combo views calculate `#` globally among rows that
meet the current Minimum plays/keeps threshold. Secondary client-side filters
preserve those global ranks and therefore intentionally leave gaps.

On phones, the navigation rail overlays rather than resizes the main content and collapses after selecting a route. The rail remains `84px` wide. Only its attached collapse/expand control is enlarged: the button is `21px x 60px`, sits at `right: -21px`, and uses a `15px` arrow glyph. Rank columns (`#`) are hidden on phone layouts only. Maps and Combos do not freeze left-side data columns on phones; their full tables scroll horizontally. Maps Metrics receives a computed readable width (`110px` metric column plus `64px` per currently visible map), so enabling Map Pack 1, Map Pack 2, Legacy, or Beginner expands the scrollable table rather than compressing columns. Maps H2H uses a fixed `1025px` mobile table width. Combo result metadata hides only the `Showing` prefix on phones.

## Shared Page Module Pitfalls

This is very important.

The page modules currently contain HTML strings with inline handlers such as:

```html
onclick="sortBy('delta_played')"
onclick="applyFiltersFromSidebar()"
```

Because ES modules are evaluated only once and `window` handlers persist across pages, each page module must bind its handlers every time it mounts.

`cards.js`, `opening-hand.js`, and `endgames.js` now use:

```js
const PAGE_WINDOW_HANDLERS = { ... };

function bindWindowHandlers() {
  Object.assign(window, PAGE_WINDOW_HANDLERS);
}
```

And call `bindWindowHandlers()` at the start of `mount()`.

Do not remove this unless the inline handler architecture is replaced with proper event delegation.

### Stale Async Response Guard

A previous bug caused Cards numbers to be replaced by Opening Hand numbers or vice versa. Root causes:

1. Global window handlers from one page could remain active on another page.
2. A slow async request from a previous page could resolve after navigation and write into the current page DOM.

The data-fetching page modules now maintain:

```js
let isPageMounted = false;
let mountToken = 0;

function isCurrentMount(token) {
  return isPageMounted && token === mountToken;
}
```

Async work passes/uses the active mount token. Before writing data or UI state, it checks `isCurrentMount(token)`.

Keep this pattern for all future pages that fetch data asynchronously.

## Static CSV Metadata

### cards_altnames.csv

Used by search alias/nickname matching.

Expected columns:

```text
card_name,aliases
```

Aliases are semicolon-separated. Search is normalized case-insensitively and accent-insensitively.

### cards_attributes.csv

Used by the Attributes bar. Important columns include:

```text
Type
Name
Species
Continent
Water
Rock
Science
Strength
Size
Abilities
Reefer
Aviary
```

Notes:

- "Continent" is displayed as Habitat in the UI. User-facing conversation may use Habitat and Continent interchangeably; in code/CSV this field is named Continent, while the Attributes bar labels it Habitat because it is shorter.
- Conditions may exist in old CSV versions but are intentionally not exposed.
- The Attributes bar is client-side only and never triggers a backend query.
- Missing metadata should fail open so table rows are not accidentally hidden.
- For Sponsor rows with no Species or Continent/Habitat, the CSV stores `0` as an explicit no-tag value. Zooplankton also has `0` in Continent/Habitat. The UI does not show a `None` chip; clicking `none` in the Species/Habitat popup means an empty selected set, which filters for this explicit `0` no-tag value.

## Backend Overview

Backend source:

```text
C:\Users\ascri\Desktop\ark-nova-function\main.py
```

Cloud Function:

```text
get-card-stats
```

Region:

```text
europe-west1
```

Runtime:

```text
python312
```

Entry point:

```text
get_card_stats
```

Public endpoint:

```text
https://europe-west1-ark-nova-stats-dashboard.cloudfunctions.net/get-card-stats
```

Project:

```text
ark-nova-stats-dashboard
```

Service account:

```text
dashboard-backend@ark-nova-stats-dashboard.iam.gserviceaccount.com
```

Requirements:

```text
functions-framework==3.*
google-cloud-bigquery==3.*
google-cloud-storage==2.*
```

Important env vars:

```text
CACHE_BUCKET=ark-nova-stats-dashboard-cache
BIGQUERY_JOB_PROJECT=ark-nova-stats-dashboard
BIGQUERY_LOCATION=US
PREPARED_LOGS_TABLE=ark-nova-stats-dashboard.dashboard_cache.card_logs_prepared
MAINTENANCE_TOKEN=<secret, never commit or paste>
```

The Cloud Function is public because GitHub Pages must call normal query/default paths. Maintenance actions are protected by application-level token checks.

## Backend Data Sources

Primary source tables:

```text
freestyle-190711.ark_nova.all_games_stat
freestyle-190711.ark_nova.game_log_stat_v2
freestyle-190711.ark_nova.tournament_tables
```

Project terminology:

- `freestyle-190711.ark_nova.all_games_stat` is the **Full Sample**.
- `freestyle-190711.ark_nova.game_log_stat_v2` is the **Log Sample**.

Prepared table:

```text
ark-nova-stats-dashboard.dashboard_cache.card_logs_prepared
```

Prepared Full Sample and card interaction tables:

```text
ark-nova-stats-dashboard.dashboard_cache.full_stats_prepared
ark-nova-stats-dashboard.dashboard_cache.players_stats_prepared
ark-nova-stats-dashboard.dashboard_cache.players_default_prepared
ark-nova-stats-dashboard.dashboard_cache.card_plays_prepared
ark-nova-stats-dashboard.dashboard_cache.card_pairs_prepared
```

Filtered Home requests read the prepared Full Sample. Players reads its narrow prepared table. Combos reads the partitioned/clustered flattened card-play table; Card + Card additionally reads the prepared unordered pair table instead of rebuilding every pair per request. These are backend-owned derived tables rebuilt during daily refresh. The source Full Sample and Log Sample are read-only and are never altered by refresh, filtering, snapshots, or caches.

Tournament H2H cache table:

```text
ark-nova-stats-dashboard.dashboard_cache.tournament_tables
```

`freestyle-190711.ark_nova.tournament_tables` is a Google Sheets external table. The Cloud Function reads the native cache table instead, because the deployed service account does not have Drive-scoped credentials for external Sheets reads. If the tournament sheet changes, refresh the native cache from the sheet CSV before refreshing H2H snapshots.

Current sheet CSV export source:

```text
https://docs.google.com/spreadsheets/d/1wJnQFXgaWa3rCUTOZpNwVETCn5fMtGo6IhjzUKlOWCs/export?format=csv&gid=1099485726
```

The daily refresh rebuilds the prepared tables, then refreshes default snapshots. Full Sample and Prepared Logs derive `table_conceded` per table from the raw Full Sample `concede` field: a table is completed when no player conceded, and incomplete when any player conceded. `completed_only=true` applies the completed-table filter (`table_conceded = 0`) on pages that retain the Completed games only control. Default snapshots include both completed and incomplete games unless a page has a hard non-conceded rule. Build/Hexes is always hard-filtered to completed tables and does not expose that control.

Default date filter:

```text
2025-01-01 onward
```

Exceptions: Home and Players have no default date restriction. Maps Metrics defaults to `2026-01-13` onward. Tournament H2H ignores date filters entirely.

Maps excluded from standard card/endgame pages:

```text
Map A
Map 0
Maps 1-8
```

Valid maps include numbered maps 1-14 and tournament map T1.

Elo defaults:

```text
player_elo_min = 300
opponent_elo_min = 300
```

Completed games filter default:

```text
completed_only = null
```

## Concession and Completion Semantics

The source field is Full Sample `concede`. During prepared-table refresh, the backend derives `table_conceded` for every table: it is `1` when any player row has a non-zero `concede` value and `0` otherwise. Therefore a completed game/table means `table_conceded = 0`; an incomplete game/table means `table_conceded = 1`. `completed_only` is an API filter flag, not a database column. When true on a page that exposes the Completed games only control, the query filters to `table_conceded = 0`; null means both populations are included. Pages with an inherent non-conceded definition retain their hard `table_conceded = 0` predicate. Build/Hexes is always in that hard-filtered population and has no completion toggle.

## Backend API Shape

One Cloud Function handles Cards, Opening Hand, and Endgames.

Cards default request:

```json
{
  "is_mw": 1,
  "maps": ["..."],
  "completed_only": null,
  "player_elo_min": 300,
  "opponent_elo_min": 300,
  "date_from": "2025-01-01"
}
```

Opening Hand request adds:

```json
{
  "stats_page": "opening_hand"
}
```

Endgames request adds:

```json
{
  "stats_page": "endgames",
  "endgames_view": "general"
}
```

Accepted `endgames_view` values:

```text
general
cp_distribution
cp_by_map
```

Maps request adds:

```json
{
  "stats_page": "maps",
  "maps_view": "metrics"
}
```

Accepted `maps_view` values:

```text
metrics
tournament_h2h
```

Accepted stats pages:

```text
cards
home
opening_hand
endgames
maps
sponsor_endgames
combinations
icons
build
predictors
actions
conservation
workers
players
```

Backend also accepts `page` as a legacy alias, but frontend uses `stats_page`.

Maintenance-only request bodies:

```json
{"daily_refresh": true}
{"refresh_prepared": true}
{"refresh_players_prepared": true}
{"refresh_data": true}
```

These require header:

```text
X-Ark-Nova-Maintenance-Token: <secret>
```

Never expose this token in frontend code.

## Backend Caching Model

Cloud Storage bucket:

```text
ark-nova-stats-dashboard-cache
```

Cache prefix:

```text
card-stats
```

Default snapshots:

```text
card-stats/default-mw.json
card-stats/default-base.json
card-stats/home/default-mw.json
card-stats/home/default-base.json
card-stats/home/defaults.js
card-stats/opening-hand/default-mw.json
card-stats/opening-hand/default-base.json
card-stats/endgames/default-mw.json
card-stats/endgames/default-base.json
card-stats/endgames/cp-distribution/default-mw.json
card-stats/endgames/cp-distribution/default-base.json
card-stats/endgames/cp-by-map/default-mw.json
card-stats/endgames/cp-by-map/default-base.json
card-stats/maps/metrics/default-mw.json
card-stats/maps/metrics/default-base.json
card-stats/maps/tournament_h2h/default-mw.json
card-stats/maps/tournament_h2h/default-base.json
card-stats/sponsor-endgames/cp/default-mw.json
card-stats/sponsor-endgames/cp/default-base.json
card-stats/sponsor-endgames/appeal/default-mw.json
card-stats/sponsor-endgames/appeal/default-base.json
```

Data-version marker:

```text
card-stats/data-version.json
```

Filter cache version:

```text
v11
```

The daily combined snapshot asset is:

```text
card-stats/bootstrap/default-pack.json
```

Default snapshots are public gzip-encoded JSON files. Home additionally has
`card-stats/home/defaults.js`, a tiny parser-loaded JavaScript bootstrap containing
both Home datasets and the current data version. Home's blank Elo inputs map to
`null`, so an unfiltered mount recognizes this embedded payload and renders it
synchronously without an API request or loading overlay.

After Home paint, the frontend requests the combined pack immediately. The pack
contains every active MW/Base default statistics payload, including Combos, but
not the player-name indexes. It is parsed once and atomically seeds the shared
in-memory snapshot cache; in-flight sharing prevents duplicate work. A snapshot
already in memory is returned before a loading indicator can appear. If a
non-Home route opens before pack warmup, that route's individual snapshot is
requested directly after a short foreground priority window.

The pack itself is persisted in versioned Cache Storage. During a daily version
transition, the newest previously successful pack is hydrated first while the
current pack downloads. The current pack becomes active only after a complete,
valid parse, so displayed data never changes halfway through installation. Cache
Storage retains the current and immediately previous successful pack versions;
individual snapshot fetching remains the fallback where Cache Storage is absent.
The backend publishes a new pack only after every constituent default snapshot
refresh succeeds, preventing mixed-version packs.

Filtered requests always go through the Cloud Function and show an updating state
immediately. Memory/in-flight caching and Cloud Storage filter caches prevent
duplicate work. Large Function JSON responses are gzip-compressed when supported,
and data-versioned keys invalidate old results after refresh. The first-ever pack
download still requires network transfer; Home remains immediate, and subsequent
default navigation is memory-local or persistent-cache-local.

Performance budgets are: under 100 ms for a memory/default-pack hit with no visible
loader; under 500 ms for an exact repeated filtered Players request; under 3 seconds
target and 5 seconds maximum for an uncached default-filter player selection; and
5 seconds maximum for representative uncached filtered General or five-player
Comparison requests. Measure Function wall time, BigQuery wait, bytes processed,
and slot time separately before considering a paid minimum Function instance.

## Daily Refresh / Scheduler

Cloud Scheduler job:

```text
refresh-card-dashboard-daily
```

Location:

```text
europe-west1
```

Schedule:

```text
5 1 * * *
```

Timezone:

```text
UTC
```

This runs daily at:

```text
01:05 UTC
03:05 CEST during German summer time
02:05 CET during German winter time
```

It POSTs to:

```text
https://europe-west1-ark-nova-stats-dashboard.cloudfunctions.net/get-card-stats
```

With JSON body:

```json
{"daily_refresh":true}
```

And headers:

```text
Content-Type: application/json
X-Ark-Nova-Maintenance-Token: <secret>
```

### Scheduler Bug That Was Fixed

The Scheduler body once became:

```text
{daily_refresh:true}
```

This is not valid JSON. Because the backend uses `request.get_json(silent=True)`, invalid JSON became `{}`. The function treated the scheduler request as a normal public request, returned 200, and refreshed nothing. Scheduler showed `status: {}`, making it look successful.

The PowerShell quoting fix is to use escaped quotes:

```powershell
gcloud scheduler jobs update http refresh-card-dashboard-daily `
  --location=europe-west1 `
  --project=ark-nova-stats-dashboard `
  --message-body='{\"daily_refresh\":true}'
```

Verify body:

```powershell
$jobJson = gcloud scheduler jobs describe refresh-card-dashboard-daily `
  --location=europe-west1 `
  --project=ark-nova-stats-dashboard `
  --format=json

$job = $jobJson | ConvertFrom-Json
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($job.httpTarget.body))
```

Expected exact output:

```text
{"daily_refresh":true}
```

### Manual Scheduler Run

```powershell
gcloud scheduler jobs run refresh-card-dashboard-daily `
  --location=europe-west1 `
  --project=ark-nova-stats-dashboard
```

### Check Scheduler Config Safely

Do not paste command output if it includes the maintenance token. Prefer safe inspection:

```powershell
$jobJson = gcloud scheduler jobs describe refresh-card-dashboard-daily `
  --location=europe-west1 `
  --project=ark-nova-stats-dashboard `
  --format=json

$job = $jobJson | ConvertFrom-Json

[pscustomobject]@{
  Body = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($job.httpTarget.body))
  ContentType = $job.httpTarget.headers.'Content-Type'
  HasMaintenanceTokenHeader = ($job.httpTarget.headers.PSObject.Properties.Name -contains 'X-Ark-Nova-Maintenance-Token')
}
```

Expected:

```text
Body                    ContentType       HasMaintenanceTokenHeader
----                    -----------       -------------------------
{"daily_refresh":true}  application/json  True
```

## Routine Backend Deploy And Snapshot Refresh

Use this when the Python Cloud Function code changed and the user has already copied the desired backend file to:

```text
C:\Users\ascri\Desktop\ark-nova-function\main.py
```

Normal code-only deploy from PowerShell:

```powershell
cd "C:\Users\ascri\Desktop\ark-nova-function"

gcloud functions deploy get-card-stats `
  --gen2 `
  --runtime=python312 `
  --region=europe-west1 `
  --source=. `
  --entry-point=get_card_stats `
  --trigger-http `
  --allow-unauthenticated `
  --project=ark-nova-stats-dashboard
```

This deploy form should preserve the existing environment variables. If env vars need repair or rotation, use the fuller commands in the sections below.

After deploy, manually refresh prepared data and default snapshots so the public frontend sees the new defaults immediately. First read the currently deployed maintenance token without writing it into files:

```powershell
$token = gcloud functions describe get-card-stats `
  --gen2 `
  --region=europe-west1 `
  --project=ark-nova-stats-dashboard `
  --format="value(serviceConfig.environmentVariables.MAINTENANCE_TOKEN)"
```

Then run the refresh:

```powershell
$body = @{ daily_refresh = $true } | ConvertTo-Json
$headers = @{ "X-Ark-Nova-Maintenance-Token" = $token }

Invoke-RestMethod `
  -Uri "https://europe-west1-ark-nova-stats-dashboard.cloudfunctions.net/get-card-stats" `
  -Method POST `
  -ContentType "application/json" `
  -Headers $headers `
  -Body $body
```

Expected result: JSON with `status: ok`, `home_bootstrap: ok`, `default_pack: ok`, a successful `players` prepared-table entry, and refreshed entries for Home, Cards, Opening Hand, all Endgames views, both Maps views, both Sponsor Endgames views, Icons, both Build views, all four Combinations views, all Predictors and Actions views, all Conservation views, Workers General/2 CP Worker, Players General, and both Players indexes for MW/Base. Do not paste the token or command output if it includes secrets.
## Maintenance Token Rotation

If the maintenance token is exposed, rotate it immediately.

Generate local token:

```powershell
$bytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
$rng.Dispose()

$maintenanceToken = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
```

Redeploy/update Function env var:

```powershell
gcloud functions deploy get-card-stats `
  --gen2 `
  --runtime=python312 `
  --region=europe-west1 `
  --source=C:\Users\ascri\Desktop\ark-nova-function\ `
  --entry-point=get_card_stats `
  --trigger-http `
  --allow-unauthenticated `
  --project=ark-nova-stats-dashboard `
  --service-account=dashboard-backend@ark-nova-stats-dashboard.iam.gserviceaccount.com `
  --timeout=1200s `
  --update-env-vars="MAINTENANCE_TOKEN=$maintenanceToken" | Out-Null
```

Update Scheduler header and preserve valid JSON body:

```powershell
gcloud scheduler jobs update http refresh-card-dashboard-daily `
  --location=europe-west1 `
  --project=ark-nova-stats-dashboard `
  --update-headers="Content-Type=application/json,X-Ark-Nova-Maintenance-Token=$maintenanceToken" `
  --message-body='{\"daily_refresh\":true}' | Out-Null
```

Then verify body/header presence and manually run the job once.

## Backend Deploy Command

Full deploy, preserving required config:

```powershell
gcloud functions deploy get-card-stats `
  --gen2 `
  --runtime=python312 `
  --region=europe-west1 `
  --source=C:\Users\ascri\Desktop\ark-nova-function\ `
  --entry-point=get_card_stats `
  --trigger-http `
  --allow-unauthenticated `
  --project=ark-nova-stats-dashboard `
  --service-account=dashboard-backend@ark-nova-stats-dashboard.iam.gserviceaccount.com `
  --timeout=1200s `
  --set-env-vars="CACHE_BUCKET=ark-nova-stats-dashboard-cache,BIGQUERY_JOB_PROJECT=ark-nova-stats-dashboard,BIGQUERY_LOCATION=US,PREPARED_LOGS_TABLE=ark-nova-stats-dashboard.dashboard_cache.card_logs_prepared,MAINTENANCE_TOKEN=$maintenanceToken"
```

Important:

- `BIGQUERY_LOCATION=US` is required.
- `--timeout=1200s` is reserved for the authenticated daily refresh, which rebuilds all derived tables and 66 default payloads before atomically publishing the pack. Normal interactive requests are expected to finish within the page-specific performance budgets.
- `MAINTENANCE_TOKEN` must match Scheduler header.
- Do not run deploy from `C:\Windows\system32`; use the function folder or specify `--source`.

## Useful Diagnostics

Describe function:

```powershell
gcloud functions describe get-card-stats `
  --gen2 `
  --region=europe-west1 `
  --project=ark-nova-stats-dashboard `
  --format="yaml(serviceConfig.timeoutSeconds,serviceConfig.environmentVariables.CACHE_BUCKET,serviceConfig.environmentVariables.BIGQUERY_LOCATION,serviceConfig.environmentVariables.PREPARED_LOGS_TABLE)"
```

Read logs:

```powershell
gcloud functions logs read get-card-stats `
  --gen2 `
  --region=europe-west1 `
  --project=ark-nova-stats-dashboard `
  --limit=50
```

Inspect snapshot timestamps:

```powershell
$urls = @(
  'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/default-mw.json',
  'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/default-base.json',
  'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/opening-hand/default-mw.json',
  'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/opening-hand/default-base.json',
  'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/endgames/default-mw.json',
  'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/endgames/default-base.json',
  'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/endgames/cp-distribution/default-mw.json',
  'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/endgames/cp-distribution/default-base.json',
  'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/endgames/cp-by-map/default-mw.json',
  'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/endgames/cp-by-map/default-base.json',
  'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/maps/metrics/default-mw.json',
  'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/maps/metrics/default-base.json',
  'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/maps/tournament_h2h/default-mw.json',
  'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/maps/tournament_h2h/default-base.json',
  'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/players/general/default-mw.json',
  'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/players/general/default-base.json',
  'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/players/index/default-mw.json',
  'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/players/index/default-base.json',
  'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/data-version.json'
)

foreach ($url in $urls) {
  $res = Invoke-WebRequest -Uri $url -Method Head -UseBasicParsing
  [pscustomobject]@{
    Url = $url
    Status = $res.StatusCode
    LastModified = $res.Headers['Last-Modified']
    CacheControl = $res.Headers['Cache-Control']
    Age = $res.Headers['Age']
  }
}
```

## Frontend Validation Commands

Run JS syntax check after changing frontend JavaScript:

```powershell
Get-ChildItem -LiteralPath 'C:\Users\ascri\Desktop\ark-nova-stats-dashboard\assets\js' -Recurse -Filter '*.js' |
  ForEach-Object {
    node --check $_.FullName
    if ($LASTEXITCODE -ne 0) { throw "JS syntax failed: $($_.FullName)" }
  }
```

In Codex environment, Node may be at:

```text
C:\Users\ascri\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe
```

If the app is opened via `file://`, module loading works in the in-app browser context used so far. GitHub Pages serves normally from `/docs`.

## Current Visual / UX State

User is happy with the current look. Avoid unnecessary frontend changes.

Important visual decisions:

- Navigation rail on desktop is 112px.
- Navigation rail on mobile remains 84px; only the attached toggle is enlarged to 21px by 60px with a 15px glyph.
- Main content/filter button alignment was carefully tuned.
- Filter button uses a funnel icon.
- Filter sidebar closes automatically after Apply filters.
- Apply filters also closes the sidebar when everything is still default; it should not requery in that case.
- Attributes title uses label-like Inter styling rather than serif/accent display font.
- Attributes bar on mobile is horizontally scrollable and one-row.
- MW/Base switch text weight was softened.
- Opening Hand table has delta dealt before delta kept, and defaults to sorting by delta dealt.
- Endgames General has delta scored before delta dealt, but still defaults to sorting by delta dealt.
- Endgames has a fixed three-cell view bar instead of the collapsible Attributes bar.
- Endgames CP distribution graph uses selectable lines/legend items; deselected lines stay visible but greyed out.
- Mobile pagination stays visible because only `.table-scroll` scrolls horizontally; `.pagination` remains outside that inner scroller.

## Design/Implementation Preferences From User

- User prefers separate new files for major backend changes/backups, but the current backend has now been consolidated to `main.py`.
- User often manually copies/uploads files and asks which files changed.
- User is a self-described beginner in web/Git/GCP and appreciates careful step-by-step explanations.
- User likes preserving a public stable version while continuing development privately.
- User wants up to roughly 1k future subpages eventually, so structure should scale.

## Adding Future Subpages

Recommended approach:

1. Reuse the current static shell.
2. Add a new page module under `assets/js/pages/`.
3. Register it in `page-registry.js`.
4. Add nav link in `layout.js`.
5. Reuse page-level `mountToken` guard pattern.
6. Rebind page-specific inline handlers on every mount.
7. Use existing filter/sidebar style, but page-specific `sidebarHtml`.
8. Only add backend query support when data cannot be derived client-side.
9. If default data is expensive or common, add daily default snapshots for MW/Base.

Avoid copying huge page modules blindly forever. Cards, Opening Hand, and Endgames currently duplicate a lot of logic. If adding many pages, consider extracting shared helpers/components once patterns stabilize:

- table sorting/pagination rendering
- attributes bar logic
- type filter logic
- filter sidebar helpers
- mount token guard
- API/default snapshot loader

Do not abstract too early if the next page has unique needs, but the duplication is real.

## Known Technical Debt

- `cards.js`, `opening-hand.js`, and `endgames.js` are large and duplicate some table/filter logic.
- Many handlers are inline HTML attributes requiring `window` binding.
- Header/nav HTML in `layout.js` is one long string, making small edits tricky.
- The logo uses embedded base64 SVG/image mask content inside `layout.js`, making the file noisy.
- Frontend has no build step and no automated browser test suite.
- There are global document listeners in page modules for popups/tooltips. They have not caused data bugs, but a future cleanup could centralize or guard them.
- CSS is large and monolithic.
- Elo-delta confidence intervals currently use observation-level Student's t
  intervals. A future statistical review may replace them with game-clustered
  or bootstrap intervals to account for within-game dependence.

## Elo Delta Confidence Intervals

The dashboard exposes two-sided 95% confidence intervals for only these displayed
Elo-delta means:

- Cards: delta played and delta in hand
- Opening Hand: delta kept and delta dealt
- Endgames General: delta scored and delta dealt
- Combos: delta actual (Card + Card), delta on map, and delta round
- Sponsor Endgames: every valid CP/Appeal delta bucket

Maps, Synergy, combo component/general deltas, and all other statistics do not
have confidence intervals.

Each interval is:

```text
unrounded mean +/- t(0.975, n - 1) * sample_sd / sqrt(n)
```

The backend uses `STDDEV_SAMP` and `COUNT(elo_delta)` on the exact rows used by
the corresponding `AVG(elo_delta)`. It uses Student's t critical values through
200 degrees of freedom and the normal limit `1.959963984540054` above that.
Intervals require at least two non-null observations. CI tooltips display a fixed-width
gradient line whose endpoint colors are continuously interpolated from the same Delta
scale as visible values, with signed lower/upper labels beneath it. The fixed line length does not encode
interval width. Tooltips do not display the internal `n` or a low-sample warning.

The CI count is deliberately separate from visible table counts:

- Cards played: non-null played-row deltas, not distinct-table `Played`.
- Cards in hand: distinct table/player/card in-hand rows, not `Seen`.
- Opening Hand: non-null dealt or kept entries, respectively.
- Endgames scored: scored events from non-conceded games.
- Endgames dealt: the exact non-conceded dealt-delta population, including corrected
  MW dealt-array ownership, ambiguous-table exclusion, and the MW no-Adapt restriction;
  this can differ from visible `Dealt`.
- Combos: the exact pair, card/map, or card/round observations for the displayed mean.
- Sponsor Endgames: distinct sponsor-play observations in that exact valid bucket.

Public payload field names use:

```text
<delta_field>_ci95_low
<delta_field>_ci95_high
<delta_field>_ci95_n
```

All MW/Base default snapshots include these fields. Filtered requests recompute
mean, sample SD, count, and interval after applying the active filters; cached
filtered responses are keyed by that complete filter set and data version.

### Continuous Numeric Color Scales

`assets/js/color-scales.js` is the shared source for value-dependent frontend colors.
All numeric scales use continuous RGB interpolation; categorical badges and graph-series
identity colors remain discrete.

Elo Delta is zero-anchored independently for every displayed Delta statistic. Its range
comes from that statistic's complete backend payload after Filter-bar filters and before
pagination. Observed endpoints, displayed means, and CI endpoints are clamped to
`[-2.0, +2.0]`. Negative values interpolate from the statistic's negative minimum in
red (`#c0432a`) through the original red/neutral/green palette to its neutral midpoint
at zero (`#7a9e80`); positive values continue through the green half to the statistic's
positive maximum (`#4caf72`). No yellow anchor is used. The two
sides are independent, so a positive value can never become red merely because the
positive and negative ranges are asymmetric. CI cells carry the corresponding mean
column's range metadata and therefore use exactly the same scale in their fixed-width
tooltip gradient. CI cells and Sponsor/Icons frequency values retain their hover
tooltips but use the normal cursor rather than the browser's question-mark help cursor.

Combo Synergy is likewise zero-anchored per Synergy column and clamped to `[-2, +2]`.
Its negative endpoint is the existing orange (`#ff6027`), its positive endpoint the
existing green (`#7cba43`), and zero uses their existing 50/50 blended midpoint
(`#be8d35`). Negative and positive sides interpolate independently.

Color ranges are tied to the fetched backend payload, not to rows left visible by
frontend-only filtering. Filter-bar changes (Elo range, maps, rounds, dates, completed
games, and other server filters) fetch a new payload and recalculate all relevant
ranges. Search, Attributes, Type, Minimum plays/keeps, Combo card selection, and Combo
header Map/Round filters only hide payload rows and do not recolor survivors. Cards and
Opening Hand use their complete current page payload; each Combo view uses its complete
active-view payload. Pagination never affects a range.

There are deliberate exceptions:

- Sponsor Endgames use one shared range across all bucket columns for each CP/Appeal
  table and mode. Delta ranges exclude greyed buckets with fewer than 1,000 observations;
  those insufficient cells cannot distort the colors of valid buckets.
- Icons use one shared range across all `0` through `7+` bucket columns for each mode.
- Build Enclosures standard buckets share one range across `0` through `5+`; unique
  buckets share one range across No/Yes/Empty, except Empty Petting Zoo frequency keeps
  its fixed violet exception.
- Maps Metrics treats each metric row as its own variable and recalculates across the
  maps currently visible. The Map Pack 1, Map Pack 2, Legacy Maps, and Beginner Maps three-state
  controls therefore do recolor the remaining/added maps even though they are frontend
  controls.
- Maps H2H matchup cells and Overall cells have separate populations. Matchup Win%
  uses its own continuous range; matchup Elo Delta uses the zero-anchored capped Delta
  scale. Overall is normalized independently and uses the CP-style orange-to-green text
  scale with no heatmap background.

Other numeric scales use the minimum and maximum for that variable from the complete
applicable payload: Elo uses `#2a5a5a` through `#2a8a7a` to `#4acfb0`;
Cards Playrate, Opening Hand Keeprate, and Endgames Keeprate retain their payload-range
blue scale. Other blue frequency cells use the fixed `0–50%` domain from
`#2a4a6a` through `#3a7abf` to `#6bb5f0`; values above 50% saturate at the high endpoint
while displayed percentages and tooltips remain exact. Expanded Build/Hexes map-frequency
cells use a page-specific fixed `0–20%` domain instead. Violet Avg/special cells retain
their own scales. CP and other orange-to-green measures use `#ff6027` to `#7cba43`.
Maps metric/H2H
scales retain their metric-specific endpoint colors. Equal minimum/maximum values use
the scale midpoint, and null/missing values retain the muted fallback.

Bars are different from text color normalization: playrate and keeprate bar lengths
represent the absolute percentage, with values above 100% visually capped at a full
track. This render-time color calculation adds no API request or payload cost.

The Maps H2H and Sponsor mode switches use normal font weight; Sponsor labels its
default mode `Elo Delta`. Combo Elo body cells use the standard Inter table typography,
and Combo Card headers retain filtering/clearing controls without sorting behavior.

## Important Bugs Fixed Recently

### Filter Sidebar Apply

Behavior now:

- Clicking Apply filters closes sidebar.
- If filters are default and cached default data is already available, it closes without requerying.
- This gives the user feedback that the button worked even if no filters changed.

### Search Bar After Architecture Split

Card search bar initially opened/closed but did not filter after modularization. Fixed by ensuring handlers/state are correctly bound/restored.

### Page Data Bleed

Symptoms:

- Sorting Cards could render Opening Hand numbers.
- Cards and Opening Hand stats appeared to swap.

Fixes:

- Rebind page-specific `window` handlers on every mount.
- Add `mountToken`/`isCurrentMount` stale async guard to page modules that fetch data.

### Scheduler Did Not Refresh

Root cause:

- Scheduler body was invalid JSON: `{daily_refresh:true}`.
- Function silently parsed `{}` and returned 200 as a normal request.

Fix:

- Update Scheduler body to valid escaped JSON via PowerShell:

```powershell
--message-body='{\"daily_refresh\":true}'
```

### Maintenance Token Exposed

The token was accidentally pasted in chat via gcloud output. It has been rotated. Future outputs from scheduler update commands can include headers; pipe to `Out-Null` or avoid pasting raw output.

## Current Backend Behavior Details

### Cards Stats

Cards stats come from prepared logs table. Metrics include:

- average elo delta when played
- average elo delta while in hand / available according to existing Cards logic
- average Elo
- n played
- n seen
- playrate

Round filter changes backend aggregation and makes some metrics unavailable in frontend.

### Opening Hand Stats

Opening Hand uses `opening_cards` and `opening_keep` arrays from `game_log_stat_v2`, incorporated into the prepared table.

Definitions:

- A card in `opening_cards` was dealt.
- A card in `opening_keep` was kept.
- Every kept card was also dealt.
- `n_dealt` = count in `opening_cards`.
- `n_kept` = count in `opening_keep`.
- `keeprate` = kept / dealt.
- `delta_dealt` = average elo delta when card was dealt.
- `delta_kept` = average elo delta when card was kept.
- `Elo` = player's Elo when card was kept.

Opening Hand data exists only through the Log Sample joined with all-games data, not the full all-games-only sample.

### Endgames Stats

Endgames use the `endgame` array for initial dealt endgames and `endgame_scores` for scored endgames/CP. These are separate populations because MW Adapt can replace the initially dealt endgames.

Definitions:

- `Dealt` = count of appearances in the initial `endgame` array from non-conceded games.
- `Scored` = count of appearances in `endgame_scores`.
- `Keeprate` = scored / dealt; it can exceed 100% because extra/scored endgames can come from Adapt or Elephants.
- The Keeprate number remains uncapped. Its blue visualization bar is clamped to 100%.
- `Delta scored` = average elo delta when the endgame appeared in `endgame_scores`.
- `Delta dealt` = average elo delta when the endgame was initially dealt. Base uses raw non-conceded
  dealt rows. For MW, the backend first corrects table-level dealt-array ownership by choosing the
  same/swapped player orientation with more dealt/scored matches, excludes tied/ambiguous tables,
  then excludes players for whom none of their corrected initially dealt cards was scored.
- `Elo` = average player Elo when scored.
- `CP` = average conservation points from `endgame_scores.cp`.

Endgames CP-focused views:

- `cp_distribution` returns percentage columns for CP 0, 1, 2, 3, and 4 plus average CP.
- `cp_by_map` returns average CP per map plus average CP overall, and intentionally ignores the map filter.

### Maps Metrics

Maps Metrics uses the partitioned and clustered prepared Full Sample table
`ark-nova-stats-dashboard.dashboard_cache.full_stats_prepared`. It stores `game_date`
and a precomputed table-level concession flag, allowing the 63 metrics to be produced
by one aggregation/unpivot query instead of repeatedly scanning the raw Full Sample.

Definitions:

- Maps are columns; metrics are rows.
- Backend returns standard maps plus hidden legacy maps `1`-`8`, `A`, and `0`.
- Frontend defaults are Legacy Maps excluded, Beginner Maps excluded, and Map Pack 2 included. Each category uses `-` Exclude, `O` Include, and `+` Only; Only forces the other categories to Exclude and requires no new API request.
- Extra maps retain the standard map-column width, so the table scrolls horizontally when either group is enabled.
- Natural order is `1a`-`8a`, `9`-`14`, `T1`, `1`-`8`, `A`, `0`.
- `Turns` and `Rounds` are lower-is-better and sort ascending; `Turns` is the default sort.
- Other metrics sort descending and color higher values greener.
- `Games` counts distinct `table_id`; other rows average player-level values.

### Frontend Card Name Display

Backend card/endgame names must stay raw and case-sensitive for matching, joins, filters, aliases, and API requests. The frontend only prettifies names at render time through duplicated `titleCase()` helpers in `assets/js/pages/cards.js`, `assets/js/pages/opening-hand.js`, and `assets/js/pages/endgames.js`.

Current display rules:

- Lowercase backend names are title-cased for the table display.
- Small words stay lowercase unless they are the first word: `on`, `in`, `of`, `the`, `a`.
- Explicit display exceptions are applied after title-casing: `Waza` renders as `WAZA`; `Galapagos` renders as `Galápagos`.
- Keep these helpers in sync until the page-specific table logic is extracted into a shared module.

## Safe Public Repo Cleanup

If Pages serves from `/docs`, root can contain only:

```text
README.md
docs/
backend/
```

Root old files that can be removed if duplicated under docs or backend:

```text
index.html
index0.html
cards_attributes.csv
main.py
```

Exception: if keeping backend open-source, move `main.py` to `backend/main.py`, not root.

## What To Do Next

Likely next product step: continue responsive/mobile polish for the newer pages or revisit the deferred Action Cards page.

Before adding many pages, decide whether to:

- Continue copy-modifying page modules for 1-2 more pages to learn patterns.
- Or extract shared frontend utilities first.

Recommended near-term path:

1. Add one more subpage with current architecture.
2. Note duplicated areas.
3. Then extract shared table/filter/attribute helpers once the third page confirms the reusable shape.

Be careful with backend changes:

- Keep `stats_page` routing clean.
- Add daily snapshots for default MW/Base if the page has common default data.
- Update scheduler daily refresh to include new page snapshots.
- Ensure all new maintenance paths require token.

## Secret Handling Reminder

Never put these in chat, code, GitHub, handoff files, or screenshots:

- `MAINTENANCE_TOKEN`
- service account JSON
- private keys
- API keys
- OAuth tokens

If exposed, rotate immediately:

1. Generate new token locally.
2. Redeploy Cloud Function env var.
3. Update Scheduler header.
4. Verify body/header safely.
5. Run Scheduler once manually.

## Frontend review notes (2026-07-10)

- Bucketed Elo-delta pages now share the `assets/js/table-cells.js` threshold and tooltip constants. The observation population and exact count remain page-specific, but the presentation rule is consistent: fewer than 1,000 observations is insufficient data.
- The Icons page no longer wraps insufficient delta values in parentheses; it uses the same muted styling and tooltip wording as the other bucketed tables.
- Cache-busting was advanced for the shared helper and affected page modules.
- A visual audit found the reviewed desktop CP-by-Map and Actions table geometries aligned. Wide map tables on phones intentionally retain horizontal scrolling rather than compressing columns.
- Backend verification (read-only) confirmed Maps Fill% is based on `Empty_hexes` with the documented 42/43/39 map totals, and Empty Petting Zoo requires a built petting zoo, zero Petting Zoo icons, and no Horse Whisperer sponsor. No backend changes were made during this review.





