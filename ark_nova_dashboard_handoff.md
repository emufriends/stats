Exit code: 0
Wall time: 0.9 seconds
Total output lines: 2462
Output:
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

Static module cache-busters form a dependency chain and must be advanced all
the way back to `index.html`. When a lazy page module changes, bump that module's
URL in `page-registry.js`, bump the registry URL in `app.js`, and bump the
`app.js` URL in `index.html`. When `snapshot-cache.js` or its manifest changes,
bump its URL in `app.js` and in any page module that imports it, then bump the
root `app.js` URL as well. Stylesheet changes require a new `app.css` URL in
`index.html`. Reusing a previous URL can leave returning browsers on an older
page implementation even when the source file and live snapshots are current.

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
#/actions
#/icons
#/predictors
#/build
#/conservation
#/workers
#/players
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
- Navigation has Cards, Opening Hand, Maps, Combos, Endgames, Sponsor Endgames, Actions, Icons, Predictors, Build, Conservation, Scoring, Workers, Players, and Records. Home has no rail item; the topbar logo links to it. Scoring is active at `#/scoring` between Conservation and Workers. Only MW Action Cards remains a placeholder; all Records and Players views are active.
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

Petting Zoo Animals supports only buckets 0-4 in MW and 0-3 in Base; later table cells are tooltip-free dashes and are absent from graphs and color ranges. The `#` column follows the current sort. Delta-column sorting places valid values first, sub-1,000 values second, and impossible/missing values last while respecting numeric direction inside the first two tiers; only valid values receive ranks. Frequency sorting simil…21104 tokens truncated…k content inside `layout.js`, making the file noisy.
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
blue scale. Other blue frequency cells use the fixed `00-50%` domain from
`#2a4a6a` through `#3a7abf` to `#6bb5f0`; values above 50% saturate at the high endpoint
while displayed percentages and tooltips remain exact. Expanded Build/Hexes map-frequency
cells use a page-specific fixed `00-20%` domain instead. Violet Avg/special cells retain
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
- Explicit display exceptions are applied after title-casing: `Waza` renders as `WAZA`; `Galapagos` renders as `GalGalapagos`.
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

## Conservation page (current behavior)

The Conservation route is `#/conservation`, with `stats_page: "conservation"`
and `conservation_view: "projects" | "project_rewards" | "cp_rewards"`.
Conservation Points are Ark Nova's green scoring track. Completing a
conservation project through the Association action increases the tracked
project count; releasing an animal is a special kind of conservation project.
The Projects tab can therefore compare two related but distinct Full Sample
fields without changing its table structure:

- `Projects` uses `Conservation_project_association_tasks`.
- `Releases` uses `Released_animals`.

The Projects snapshot carries both populations in one `data` array. Every row
has `subject: "projects" | "releases"` and `count_value` from 0 through 7.
Seven is the gameplay maximum represented by this analysis. A null, malformed,
negative, or greater-than-seven count is excluded from that subject's
denominator. This matters because the same player-game may be valid for one
subject and invalid for the other; their denominators are intentionally
independent. Both subjects hard-filter to non-conceded tables.

For each subject/count/map, Delta is the mean `elo_delta` among player-games
with exactly that count. Frequency is `exact-count observations / all valid
scoped observations`, calculated separately per map and across all maps. The
Projects/Releases, Raw/vs. avg, and Elo Delta/Frequency controls are all local:
they never trigger another request. In `vs. avg`, each map displays its map
value minus that row's all-map `Avg`; `Avg` remains the raw reference. Delta
map cells use the normal Delta scale and CI/1,000-observation rules. Delta Avg
uses the separate orange-green Avg scale and matching CI metadata. Frequency
map cells use the fixed 0-50% blue scale and exact numerator/denominator hover;
Frequency Avg is violet. Only numerical Frequency cells use the one-pixel
smaller body font.

The shared snapshot paths remain:

```text
card-stats/conservation/projects/default-{mw|base}.json
card-stats/conservation/project-rewards/default-{mw|base}.json
card-stats/conservation/cp-rewards/default-{mw|base}.json
```

The Projects path includes both Projects and Releases; there is deliberately no
second Releases asset. Filter-bar Elo, maps, and date predicates apply before
both subjects are aggregated.

## Scoring page (current behavior)

The active Scoring route is `#/scoring`. Its backend interface is
`stats_page: "scoring"` and `scoring_view: "final_score" | "appeal" |
"conservation_points" | "reputation"`. The four equal-width tabs describe the
four end-of-game tracks: Final score, Appeal, Conservation points, and
Reputation. Every Scoring observation must satisfy both
`table_conceded = 0` and `end_game_triggered = TRUE`. The first predicate uses
the dashboard-wide table-level concession definition; the second is an
additional Scoring eligibility rule proving that these final-track values came
from a triggered endgame. It does not redefine "completed game" elsewhere.

The sidebar has Player Elo, Opponent Elo, and Date Range only. Defaults are
300+, 300+, and 2025-01-01 onward. Every table has the Build/Hexes map grid:
the value bucket is 10%, each of the 15 maps is 5.5%, and Avg is 7.5%, on the
shared 900px table canvas. Rows have fixed gameplay order and are not sortable.

Each response contains collapsed `data` and exact `expanded_data`, so
Raw/vs. avg, Elo Delta/Frequency, and expansion are browser-only operations.
`vs. avg` is `map value - row Avg`; Avg remains raw. Each bucket/map returns the
Delta mean, observation count, CI fields, Frequency numerator, and valid-value
denominator. Delta map cells use the normal Delta/CI/insufficient-data rules;
Delta Avg uses the orange-green Avg scale and matching CI scale. Frequency map
cells use blue with a 0-50% domain while collapsed and 0-20% while expanded;
the displayed number and numerator/denominator tooltip are never clamped.
Frequency Avg is violet. Numerical Frequency cells are one pixel smaller. The
compact arrow is attached below the framed table and swaps row sets locally.
Reputation has no arrow because both row sets are already exact and identical.

Bucket contracts are exact:

- Final score collapsed: `<100`, `100-109`, `110-119`, `120-129`,
  `130-139`, `140-149`, `150+`; expanded: `<100`, each integer 100-149,
  `150+` (7/52 rows).
- Appeal collapsed: `<40`, decade buckets 40-99, `100-112`, `113`;
  expanded: `<40` and each integer 40-113 (9/75 rows).
- Conservation points collapsed: `0-10`, then five-point buckets through
  `36-40`, and `41`; expanded: each integer 0-41 (8/42 rows).
- Reputation: each integer 1-15 in both modes (15 rows).

Null/non-numeric values never enter a denominator. Appeal must be 0-113,
Conservation 0-41, and Reputation 1-15. Score deliberately has open lower and
upper tails because `<100` and `150+` are valid buckets. For example, Score 99
belongs to `<100`, 100 belongs to `100-109` or exact `100`, 149 belongs to
`140-149` or exact `149`, and 150 belongs to `150+`. Appeal 113 and
Conservation 41 are explicit maximum rows.

Default snapshots are:

```text
card-stats/scoring/final-score/default-{mw|base}.json
card-stats/scoring/appeal/default-{mw|base}.json
card-stats/scoring/conservation-points/default-{mw|base}.json
card-stats/scoring/reputation/default-{mw|base}.json
```

All eight assets are refreshed daily and included in default-pack schema 5.
The backend reads the source Full Sample through the backend-owned prepared
table, performs the aggregations, and writes derived snapshots. Source BigQuery
tables remain read-only.

## Records page (current behavior)

The Records route is `#/records` and is backed by `stats_page: "records"` with
`records_view` set to one of `elo_leaderboard`, `fastest_games`,
`highest_scores`, `biggest_turns`, or `most_icons`. All five views are
functional.

`elo_leaderboard` is the default Records parser and frontend view. Its header
message always reads `Top 100 players (for full leaderboard, click here).`,
with `here` opening `https://emufriends.pet/leaderboard` in a new tab. Local
player search may narrow the displayed rows, but the message continues to
describe the underlying Top 100 source.

Elo Leaderboard is a dataset-neutral static view sourced from the public
Google Sheet `1NG3FPP70riMzhHPJ6Suz30bhJxUocFd_rKDKxn0kZbM`, worksheet
`Masters`. The daily refresh reads country from column B, player from C, Peak
Elo from F, and Peak Arena from H. Rows are validated, sorted by Peak Elo
descending, truncated to the Top 100, and assigned permanent displayed ranks
1–100. Blank Peak Arena values display as `n/a`. Country codes render through
the dashboard's FlagCDN flag treatment with accessible country names. The
sheet has no MW/Base field, so the identical validated leaderboard is published
under both dataset paths; switching MW/Base does not change it. The table is
not sortable and does not query BigQuery. The frontend treats the two paths as
one shared dataset-neutral payload and reuses the same cached table when the
global MW/Base switch changes.

Automatic Records rows are individual player-game observations from the
backend-owned `full_stats_prepared` table. Fastest Games also unions manually
extrapolated rows, and Biggest Turns is entirely manual; both use the derived
`records_manual_prepared` table described below. Source BigQuery tables remain
read-only. Automatic Fastest, Highest Scores, and Most Icons rows hard-filter
`table_conceded = 0` and `end_game_triggered = TRUE`. `table_conceded` is
derived from Full Sample `concede` at table level: any concession makes the
table incomplete. The visible default opponent-Elo minimum is 300. Records
defaults to the 15 current maps plus legacy maps 1-8; beginner maps A and 0
remain selectable but are off by default. These are browser defaults only:
every functional Records snapshot contains the complete eligible population
for all 25 known maps, with no player, opponent-Elo, date, Arena, or Tournament
restriction.

Automatic Fastest Games keeps won rows (`Game_result = 1` for the player and
exactly one opponent row with `Game_result = 2`) with `Number_of_turns <= 23`.
The manual Fastest sheet is an explicit exception for conceded games whose
Turns and final Score were extrapolated. Manual values override an automatic
row with the same ID and player. The combined table sorts by Turns ascending,
Score descending, player name ascending, and ID. Highest scores
uses the same won-game rule, keeps `Score >= 170` and
`Number_of_turns <= 100`, and sorts by Score descending, turns ascending, and
player name ascending. Most icons expands the valid icon fields into one row
per icon and player-game, keeps counts of at least 10, and sorts by count
descending, turns ascending, and player name ascending. Its table ID displays a
result suffix: `(W)`, `(D)`, or `(L)`, derived from the two player results.
Bears and Petting Zoo Animals are not valid Most-icons record types. These
tables are deliberately not user-sortable.

The displayed automatic columns are direct record values: Player is `player`, Score is
`Score`, Turns is `Number_of_turns`, Map is rendered as `Map name (code)`, ID
links to the corresponding Board Game Arena table, and Date is a `YYYY-MM-DD`
date from `game_ended_at`. Automatic Fastest rows use EPT zero; manual Fastest
rows use the spreadsheet's EPT value, where EPT means extrapolated turns.

The canonical Fastest supplement is the first worksheet of Google Sheet
`1RSOjQdZcGmOY7PBsDY7erGz--dtPJLc3ydNArr9bV48`. Its columns are Turns, Player,
Score, Map code, ID, Date, EPT, and Mode. Mode is `MW` or `Base`, so separate
dataset sheets are neither required nor supported. Biggest Turns uses the first
worksheet of `1SfWmRUo3c2jHbezJDVwXxi3zqEm5RdiZxp4hbHfEl0Q`; the consumed
columns are Flat A, End B, Total C, Player D, Score E, Turns F, Map G, Move H,
Actions I, ID K, Result L, Date M, and Mode N. Result must be W, D, or L and
Total must equal Flat plus End.

The daily refresh downloads both public CSV exports once and validates every
nonblank row. When an exact ID/player pair exists in Full Sample, that match
supplies opponent Elo, exact timestamp, and Arena metadata; Mode and Map must
agree or the refresh fails. Date remains the sheet-owned display value and is
not an identity field because UTC/local boundaries and historical manual dates
can differ from the source timestamp. For matched rows, date filtering and Arena
classification still use the exact source timestamp. Some manually extrapolated early concessions
are absent from Full Sample by definition. Those rows remain valid with their
sheet-native dataset, map, player, and date, while unavailable enrichment fields
are stored as null (`source_enriched = false`). They therefore participate in
the default, player, map, date, and dataset populations. Elo bounds apply only
to enriched manual rows, because treating unknown Elo as a failed range check
would silently erase the exact early concessions the sheet exists to restore.
Source-absent rows cannot satisfy Arena-only, whose required rating metadata is
unavailable. Tournament filtering remains possible because it is an independent
table-ID lookup. A contradictory upstream match is never treated as
source-absent.

Only after all rows validate is the backend-owned
`records_manual_prepared` table atomically replaced. A valid source is cached in
`card-stats/metadata/records-manual-source.json`. Temporary delivery errors or
invalid edits reuse the last fully validated source; without a valid cached
source, the refresh fails instead of publishing partial data.

Biggest Turns contains only spreadsheet rows and has fixed Total-descending
ordering, preserving spreadsheet row order for equal Total values. Its columns
are Flat, End, Total, Player, Score, Turns, Map, Move, Actions, ID, and Date,
with widths `6/6/6/18/6/6/15/6/6/15/10%`. Numeric values are whole numbers;
ID is a BGA link with the spreadsheet W/D/L suffix. It uses the normal Records
search, filters, row selector, pagination, and `games` count.

Each view has an always-visible centered Player search field with a search icon
on its left, backed by the daily MW/Base player-index snapshots. Search
suggestions are alphabetical, begin after three characters, are limited to 50
visible matches, and selecting a name filters the already-loaded snapshot to
that exact player value. Most Icons has a client-side `TYPE` popup with all 14
valid icon types shown in three unlabeled six-slot rows (species, habitats, then
Rock/Water/Science). An active filter displays `selected/14`. The popup is a
body-level overlay clamped to the visible table frame, so table scrolling cannot
clip it. Its all/none controls and icon selections filter the already-loaded
payload without another request. Arena-only means a valid
configured Arena season assignment: the observation has a non-null Arena
rating delta and falls within a configured UTC season interval with the
matching MW/Base mode. Tournament-only joins the backend-owned tournament
table cache used by Maps' Tournament H2H. The two switches are mutually
exclusive in both the UI and API. The Filter bar also has an empty-by-default
Date Range between Maps and these switches. Its inclusive local predicate is
`date_from <= game_date <= date_to`; either endpoint may be omitted, while a
From date after To is rejected.

The Records header includes the shared Rows selector with options 25, 50, 100,
and All. It defaults to 50 and controls client-side pagination. The result
count uses the noun `games` and retains the existing displayed-row semantics,
including the one-row-per-icon behavior of Most Icons.

Records and every Players table (General, Comparison, and Arena Top 100) use the
same 40px rendered table-header height as Workers and Conservation. Their 25px
player-search inputs use 7px vertical cell padding so the controls fit inside
that shared slot; search inputs must never increase the row height or move the
table when switching pages.

Records widths are view-specific: Fastest and Highest use Player 20% and EPT
10%; Most Icons uses Player 20% and ID 15%; Biggest Turns uses the exact widths
documented above.

Records player search inputs use a dashboard-owned clear button. Browser-native
search cancel controls are disabled so that a second, browser-colored X is not
shown beside the dashboard control. In Arena Top 100, the active sortable header
uses the accent color for both the complete header text and its sort arrow.

Complete Records payloads are written daily under:

```text
card-stats/records/elo-leaderboard/default-{mw|base}.json
card-stats/records/fastest-games/default-{mw|base}.json
card-stats/records/highest-scores/default-{mw|base}.json
card-stats/records/biggest-turns/default-{mw|base}.json
card-stats/records/most-icons/default-{mw|base}.json
```

All ten assets participate in the atomic default snapshot pack. The Elo
Leaderboard source is cached separately as a last-known-good validated source;
a temporary Google Sheets delivery or validation failure reuses that source and
does not publish a partial leaderboard. Each remaining row
carries `opponent_elo`, `source_enriched`, `is_arena`, `is_tournament`, and the
available sheet `source_row`, in addition to the displayed fields. The browser
loads a view snapshot once and performs Player, Maps, Opponent Elo, Date Range,
Arena-only, Tournament-only, Type, pagination, and row-count changes locally;
applying or resetting Records filters never calls the Cloud Function or
BigQuery. An empty Elo minimum means zero and an empty maximum means no upper
bound. Rows with unavailable opponent Elo deliberately survive any Elo range,
because excluding them would erase the manual exceptions the sheet exists to
restore.

The pack has a
schema version; a frontend may reuse the previous successful pack only when its
schema matches, preventing an older payload contract from masquerading as the
current one. A warm browser
therefore renders default Records data from memory/cache and every Records
filter is an immediate in-memory operation.

## Current cross-page polish rules

- Normal single statistics tables use `width: 100%` with a shared `900px`
  minimum canvas on desktop and mobile. Below 900px their `.table-scroll`
  wrapper scrolls horizontally. The only shrinkable `min-width: 0` exceptions
  are the compact side-by-side Actions Starting position, Actions Upgrades, and
  Build Enclosures tables.
- Clearing any Player/Opponent minimum-Elo input means zero; a blank maximum is
  unrestricted. Home serializes blank minima as zero so its unrestricted
  bootstrap payload still renders synchronously without an API request.
- Map tooltips use `Map name (code)`, for example `Observation Tower (1a)`;
  backend filter values retain the full `Map 1a: Observation Tower` string.
- Records, Players, Conservation, and Cards map chips use the same five-column
  chip geometry and padding so changing pages does not change their visual
  scale.
- Players Arena Top 100 graph hover is line-specific. Pointer coordinates are
  transformed through the SVG screen matrix, then matched against the exact
  plotted points for that player inside the active Day X-Y range. Only the
  stored rating is shown above the cursor; off-screen observations are never
  eligible.
- Players' General and Comparison selections are analysis context and persist
  when switching MW/Base. The selected player is not a global filter and is
  intentionally independent between the two views. Suggestion overlays open
  only from active typing and are cleared immediately after selection.
- Workers' Last worker annotation is normal (not italic). `1 CP` has a single
  underline and `2 CP` has a double underline; the General Frequency `n (Avg)`
  label uses the ordinary label size, while only its numerical map/Avg cells are
  one pixel larger than ordinary body values.

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
