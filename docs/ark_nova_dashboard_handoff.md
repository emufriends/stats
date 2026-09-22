# Ark Nova Statistics Dashboard Handoff

Date: 2026-06-21  
Last updated: 2026-09-21  
Project owner: pr0paganda-panda / Panda  
Current repository: https://github.com/emufriends/stats

This handoff is for a future Codex/AI session continuing the Ark Nova statistics dashboard. It is intentionally comprehensive and secret-free. Do not add maintenance tokens, API keys, or service account JSON to this file.

## Executive Summary

The project is a static GitHub Pages frontend backed by a public read-only DuckDB gateway, with the Cloud Function retained for maintenance and refresh control. The frontend uses a reusable shell plus lazy page modules for Home, Cards, the unlinked Card Details route, Opening Hand, Endgames, Maps, Sponsor Endgames, Combos, Actions, Predictors, Icons, MW Action Cards, Build, Conservation, Scoring, Workers, Players, Arena, Records, and the hidden Refresh page. Shared controls, snapshot loading, filters, and table behavior live in the shell; every page's population exceptions are documented below and in the executable parity contract.

The current public version is served from GitHub Pages and sends filtered reads
to `https://duckdb-gateway-ioetmehoha-ew.a.run.app/v1/query`; default views continue to
use the atomic Cloud Storage snapshot pack. The pack pointer is published with
mandatory revalidation and individual snapshots use a short cache lifetime, so
an updated object at the stable URL cannot remain pinned by an old immutable
browser response. The Cloud Function remains the
maintenance boundary for refresh status, manual refresh authentication, and
controlled source operations; it is no longer the public analytical read path.
The public/private cutover was completed on 2026-09-21 after gateway health,
filtered-query, frontend publication, and live-site checks passed. Future work
should happen in the `emufriends/stats` repository and its local working copies.

### Operating budget and architecture assessment

The operating budget target is USD 20 per month for the complete dashboard
service. The [data architecture assessment](analysis/dashboard-cost-architecture-review.md)
contains measured source/derivative sizes, source-import dry runs, identified
refresh/cache inefficiencies, and a proposed local analytical serving workflow.
Its [evidence file](analysis/cost-architecture-evidence.json) records the
2026-09-15 metadata and distinguishes historical usage from estimates.
The production backend and local working copy use the Phase 1 cost-containment
contract. Public requests may read default snapshots and exact persistent cache
hits, but an uncached analytical request receives a clear 503 response instead
of starting BigQuery. Optional Synergy-CI refresh and Card + Card warming are
disabled by default. Partial prepared-table maintenance is also disabled because
it cannot publish a coherent complete generation. Every remaining SQL query uses a cost-controlled client
with workload/component labels and a hard byte ceiling. Daily refresh first
fingerprints free BigQuery metadata plus external inputs; unchanged sources do
not rebuild or advance the successful publication time, while an Elo-sheet-only
change republishes only that snapshot and the existing pack. Card moments are
rebuilt before the card aggregate that consumes them.

Phases 2 and 3 are complete as a private prototype and serving decision. The local-data bootstrap is at
`analysis/phase2-local-import.py`; it does not change production serving or
refresh schedules. One coherent private generation now contains reusable
Cards/Players facts and focused pair and standalone-EV reads. Cards and Card +
Card producer outputs reconcile locally, and a read-only VM smoke test confirms
representative queries and concurrent readers. Full quadratic pair materialization
is not part of the design because the exploratory build expanded unnecessarily.
The first private generation is now exported and materialized locally as
`phase2-20260915-b57235ad65db.duckdb`: 5,531,256 Full Sample rows and 436,526
Logs rows were materialized in 146.894 seconds; the source-only DuckDB stage
was about 848 MB. The current immutable file is approximately 4.44 GB because
an exploratory full-pair materialization was interrupted; that expansion is
not part of the serving design and must be removed when the next compact
generation is built.
The representative local MW card-play aggregation completed in 6.745 seconds.
The narrow local serving slice contains 5,531,256 player-game rows and
7,797,585 deduplicated normal-card play rows across 280 card/type groups. A
focused Cards comparison matches the expected 267 post-exclusion card groups
and local default-scope counts. The Phase 3 same-generation parity gate passes
all 267 Cards rows and the deterministic first 1,000 Card + Card API rows with
zero point/count mismatches. Its report is `analysis/phase3-parity-report.json`;
it reads no BigQuery data and is not used by production snapshots.
This generation is excluded from source control and Function deployment.

The current corruption audit is documented in
`analysis/phase2-corrupted-current-audit.md`. The authoritative 2026-09-16
source scan found 9,021 corrupted tables (5,295 MW and 3,726 Base). The private
2026-09-15 export found 8,988; it also had exactly 5,419 fewer two-player
tables, so the 33-table difference is consistent with source growth. The older
7,663 figure has no saved table-ID set and is historical context only. The
predicate is always recomputed from the current source fingerprint and counts
are never hard-coded.

The protected maintenance backend is deployed in `europe-west1`. The recurring
Synergy-CI, Card + Card warming, legacy main dashboard-refresh, and Base/MW
snapshot Scheduler jobs are paused; the private DuckDB daily refresh and
independent Elo update remain enabled. The project-level BigQuery
`Query usage per day` quota is set to `0.1 TiB`. Default snapshot delivery has
been verified, and an uncached filtered request is rejected before SQL. The
controlled tracked refresh reached snapshot generation, processed
73,304,696,183 bytes (68.2703 GiB), then stopped without publishing because a
snapshot query was incorrectly assigned the 2 GiB public ceiling. Snapshot
queries now explicitly use the 64 GiB maintenance ceiling. The previous atomic
pack and successful completion timestamp remain intact. Do not restart the
legacy full refresh within the same quota day. The Phase 2 local benchmark now
covers filtered Cards, player history, Card + Card actuals, ordinary card CI,
standalone component CIs, strict MW action-card eligibility, and four
concurrent readers; see `analysis/phase2-local-benchmark-report.json` and the
focused Card + Card report. The Phase 2 representative prototype is complete:
the same benchmark passes on the private VM with consistent concurrent readers,
and the local Cards producer emits all 267 rows with zero card-group or
`n_played` mismatches against its local query contract. At that prototype
checkpoint no production route had been switched. The first Phase 5 builder optimization now completes the full
vertical slice on the 4-GiB `ark-nova-duckdb-test` VM using two threads, a
2.8-GB DuckDB memory ceiling, and disk spilling; it completed in 344.421
seconds without OOM. Its build and post-build read reports are
`analysis/phase5-optimized-builder-benchmark.json` and
`analysis/phase5-postbuild-read-benchmark.json`. This is a successful private
builder benchmark and the basis of the production daily-refresh pipeline. The
private `phase5_local_refresh.py` runner now adds a copy-on-write generation
boundary around that builder: it validates the result before atomic
activation, preserves the active pointer on failure, and has passed a private
end-to-end build, Cards API smoke test, rollback, and reactivation test. It is
connected to the private daily scheduler. A Cloud Run service named
`duckdb-gateway` was added on 2026-09-18 with direct
VPC egress and a dedicated service account. It exposes only the bounded
read-only DuckDB API allowlist over HTTPS and successfully passed health,
CORS, query, and unknown-path tests against the private VM. The published
frontend now uses this gateway for filtered reads. A fresh controlled
BigQuery source export was materialized into a new DuckDB candidate on the VM
(5,949,676 Full Sample rows and 436,526 Logs rows). Card + Card was then
optimized: the builder now materializes compact component and pair aggregates
(267 and 35,511 rows) from the table-level relations, so requests no longer
regroup 33.4 million pair rows and 4.2 million component rows. Direct in-VM
requests take about 0.25–0.41 seconds uncached, and the staging gateway
returns the same values. A direct reconciliation for a representative pair
matches the table-level source sums exactly. The optimized candidate is
private and rollback-ready; production routing now uses the gateway while the
Cloud Function remains available for maintenance rollback. The
read-only serving contract, atomic generation/rollback
primitives, persistent cache, bounded private HTTP API, route capability
inventory, sanitized audit log, and readiness checks are documented in
`phase3-duckdb-serving.md` and implemented privately in
`phase3_duckdb_service.py` and `phase3_api.py`.
DuckDB is the selected local engine. All 50 private routes have executable
local query builders: four
representative Phase 3 routes plus Maps/Metrics, both additional Endgames
views, Maps/Tournament H2H, both Sponsor Endgames views, all Predictors views,
Actions/Starting Position, the four Scoring views, three other Actions views,
two Build views, Icons, three Conservation views, two Workers views, Home,
Opening Hand, all remaining Combos views, and all remaining Players views
from Phase 4. No recognized route falls back to BigQuery. The immutable legacy
default-pack oracle now passes all 43 mapped snapshot-backed public row
contracts; it ignores only the intentionally retired additive Synergy CI fields.
Cards and Opening Hand emit complete card-row contracts, including both EV
columns, counts, play rate, average Elo, and ordinary CI source moments. MW
By-map emits one wide row per action card; MW Synergies emits catalog keys,
names, component EVs, and actual-pair moments. Conservation CP Rewards emits
the full reward/scope/map field matrix, and Players/General emits the complete
65-row metric matrix expected by the frontend. Ordinary standalone EV CI
endpoints are projected from compact mean/sample-deviation/count fields at the
private adapter boundary. Card + Action Card preserves all 20 individual
action cards and counts the action-card baseline once per selected
card/player-game. Arena now has a nested season-bundle producer backed by the
6,236 imported roster rows and ID-based Full Sample joins; Records exposes all
five public row contracts, with automatic populations local and the three
validated moving spreadsheet exports imported into generation-local narrow
relations. Phase 4 progress and its scope contract are documented in
`analysis/phase4-progress.md`. The independent numerical reconciliation covers
the remaining 49 routes, and all 49 pass direct source or moving-source checks.
The Cards route applies the shared filter scope to its played, in-hand, and seen
populations. The detailed report is
`analysis/phase4-independent-reconciliation.json`; it is authoritative for
this bounded numerical gate. The private readiness, route-contract,
frontend-contract, legacy-contract, and decision-gate reports remain
authoritative for the other cutover gates. The production read route now uses
the public DuckDB gateway; the Cloud Function remains the maintenance and
rollback boundary.

### Phase 5 private serving state

DuckDB is the selected serving engine. The public gateway is
`https://duckdb-gateway-ioetmehoha-ew.a.run.app`; it exposes only the bounded
read-only API. The serving VM is
`ark-nova-duckdb-test` in `europe-west1-c`, using an e2-medium with 4 GiB RAM.
The selected serving mode keeps this VM running continuously; its resident
worker handles the daily refresh request without powering the VM off. The
worker is a `Type=simple` systemd service with no startup timeout, because its
normal state is to remain resident while waiting for the next request.
The refresh function never starts the VM from a request; if it is stopped by the
€40 safety rail, scheduled and manual refreshes fail safely until the VM is
manually restarted.

The current private generation is
`phase5-hotfix-20260922-filter-performance-v2`, with data version
`phase5-source-sync-3c6031ddbc8d09dea83f-20260921092543`. It contains 6,074,924 Full Sample
rows and 436,526 Logs rows from the controlled Full Sample/Logs
source, compact route derivatives, current Arena/Records metadata, a
table-level `completed_tables_narrow` eligibility relation, and the
completed/non-corrupted `players_metrics_narrow` serving fact. Its rollback
parent is `phase5-hotfix-20260921-filter-performance`.
The private pack contains 96 ordinary route files
plus Arena all-season, latest-season, and manifest assets. All files have the
same data version; the atomic private snapshot pointer is under
`phase2_private_data/snapshots/current.json` on the VM.
The ordinary pack includes Card + Card for both datasets; component CI and
player-history endpoints remain interactive-only.

This generation was produced by the rollback-safe workflow in 3,988.728
seconds (about 66 minutes 29 seconds) and retains
`phase5-refresh-20260919-02` as its rollback parent. The VM has a 40 GiB disk;
the completed baseline leaves about 14 GiB free. The serving and snapshot
pointers both reference the completed generation. The VM is kept running for
the selected always-on serving mode; its €20/€40 monthly budget rails limit
unexpected cost growth.

The established private numerical and shape gates pass for the bounded cases
already reconciled. The first current-generation route smoke returned 41 of
46 routes within the 120-second per-route budget because five default requests
repeated large scans. The adapter now serves those exact default-scope routes
from matching immutable generation-local snapshots, and the rerun passed all
46 routes; the five optimized routes returned in 0.006–0.244 seconds. Filtered
requests continue to use the SQL builders. Arena's private bundle contains 13
seasons and 38,032 roster rows, and table/history entries align by numeric
player ID. Card + Card uses refresh-time compact aggregates, and Arena history
is built one season at a time to stay within the 4 GiB memory budget.

The public/private snapshot comparison uses one data version: the public pack
and private generation use
`phase5-source-sync-3c6031ddbc8d09dea83f-20260921092543`, with pack schema version
23. Individual objects are published before the default
pack pointer, which is the coherent-generation boundary.

`phase5_refresh_workflow.py` is the private daily/manual workflow. Given a
versioned controlled Parquet export, it imports source data, builds narrow
derivatives, imports Tournament/Arena/Records moving sources, activates one
immutable generation, builds the complete snapshot pack, atomically advances
the private snapshot pointer, and rolls back the generation on failure. It
does not publish GitHub, public Cloud Storage, or production API changes.

The import contract is defined in the backend's `phase5-source-sync.md` and
implemented by `phase5_source_sync.py` and `phase5_source_reconcile.py`.
The external sources are unpartitioned and have no trustworthy change cursor.
A maximum table ID or recent-game-date filter is therefore not a complete or
necessarily cheaper incremental sync. Free source metadata checks skip unchanged
families; changed Full Sample uses one canonical export with an 8 GiB hard
query ceiling. The current measured scan is 4.62 GiB. Logs uses native
extraction only when its own metadata changes. Per-file checksums and a final
manifest commit protect transfer completeness, and metadata is checked again
after export to reject a moving source. Raw-table, view and Elo-routine changes
all invalidate the Full Sample fingerprint.

The local reconciler compares complete game-table row fingerprints and replaces
only added, corrected or deleted tables in a copy of the active database.
It handles late historical imports and duplicate multiplicity. The workflow's
`--incremental-source` option consumes this copy and then rebuilds derivatives
and snapshots locally. A staging source copy must never be served before that
build completes. The private importer is scheduled by Cloud Scheduler job
`refresh-private-duckdb-daily` at 00:00 UTC. The scheduler queues a refresh;
the fixed always-on VM performs the moving-source downloads, source import,
local build, snapshot generation, and atomic activation. Arena CSVs
and Records spreadsheet exports are refreshed on every run with last-known-good
fallbacks. The refresh status object exposes only sanitized state/progress and
the last successful completion. A Monitoring alert notifies
`hlmichel.vo@gmail.com` on refresh failures. The project quota is 0.1 TiB/day
and expensive legacy BigQuery schedules remain paused.

The bounded September 21 rehearsal generated source candidate
`sync-3c6031ddbc8d09dea83f5dee`. The Full Sample export billed 4,966,055,936
bytes; Logs used native extraction and incurred no analysis-query bytes. An
immediate repeat was a zero-query no-op. Local reconciliation took 793.229
seconds, added 21,205 game tables, replaced one corrected two-row game, and
produced 6,074,924 Full Sample rows across 3,037,462 games. Logs remained at
436,526 rows across 218,221 games. The source was reconciled locally, all
derivatives and the complete 99-file snapshot pack were rebuilt, validated, and
activated. The current serving/snapshot generation is
`phase5-refresh-20260921-155111-phase5`, and the VM is kept running for serving. The source-sync query accounts for only 4,966,055,936 billed
bytes; reaching the project-wide daily quota in the same accounting window does
not mean this single sync consumed the full allowance.

Phase 5's private baseline and default-route performance gate are complete, and
the coherent default pack has been promoted. The serving choice is the
always-on e2-medium VM. Billing safety rails are configured on the project:
the €20 monthly budget sends an email to `hlmichel.vo@gmail.com`, and the €40
monthly budget sends the same alert while publishing to a private handler that
stops only `ark-nova-duckdb-test`. Budget notifications are delayed estimates,
not an instantaneous spending cap; stopping the VM does not reverse accrued
charges or disable unrelated project services. Gateway health and filtered-read
checks, frontend publication, legacy-scheduler review, and the rollback
rehearsal have passed. The active generation reports a valid rollback parent
and `/readyz` returns `rollback_ready: true`; the serving pointer remains
unchanged. BigQuery roles still required by controlled source export and Elo
maintenance remain in place; public BigQuery reads and legacy analytical
schedules remain disabled.

### Start here for Elo spreadsheet / leaderboard work

The daily Elo/Arena spreadsheet updater and standalone full leaderboard are
adjacent systems, not part of the dashboard runtime. For those tasks, read
`elo_system_handoff.md` first. It contains the current Cloud deployment,
spreadsheet schema, updater rules, Discord behavior, idempotency/date fixes,
standalone leaderboard layout, tests, diagnostics, and safe deployment commands.
Reading this entire dashboard handoff is unnecessary unless the request also
touches the dashboard's Records Elo Leaderboard or another dashboard feature.

## Canonical Completed-Game Population

Every dashboard feature uses one definition whenever it says a game is
completed:

```text
completed game =
  table_conceded = 0
  AND end_game_triggered = TRUE
```

`table_conceded` is derived at table level from Full Sample `concede`: a
concession by either player makes the table incomplete. `end_game_triggered` is
the normalized Boolean prepared from the canonical source field. Null,
malformed, and false trigger values are incomplete. The backend helper
`_completed_game_sql()` is the single SQL source for this predicate in Full
Sample, Logs, Players, card/combo aggregates, and page-specific queries.

An optional `completed_only` request flag applies both conditions. If its
filter-bar toggle is off, that page keeps its documented broader population.
Hard-completed views apply the predicate regardless of request input. These
include Players General/Comparison, Maps/Metrics, Endgames, Sponsor Endgames,
Icons, Build/Hexes, the completed Actions views, Workers/General, Conservation
Projects/Releases, Project Rewards Frequency, all Predictors views, Scoring,
and the completed subsets used by Arena. Automatic Records use the same
predicate. Manual Fastest Games remain an explicit spreadsheet exception;
Biggest Turns and Elo Leaderboard remain spreadsheet-only.

Every Filter sidebar where completion is meaningful shows `Completed games
only` immediately above the Arena/Tournament controls. Optional populations
use the normal editable switch. Hard-completed views show the switch checked,
disabled, and accompanied by a current-color lock whose accessible explanation
is `This view always uses completed games.` Switching tabs does not overwrite
an optional tab's prior value. The control is omitted for Records/Elo
Leaderboard, Fastest Games, and Biggest Turns; Maps/Tournament H2H; Arena; and
Refresh. Predictors/Specific remains hard-completed; frequency is condition
observations divided by all completed observations in the current scope. The
current row counts are 21 for MW and 19 for Base.

## Canonical Corrupted-Game Exclusion

Every game-derived analytical population except Home excludes abandoned tables
that can inflate one player's statistics. A table is flagged when a losing row
(`Game_result = 2`) has non-null values for turns, all five action counts, and
`X_Tokens_gained_instead_of_action`, and the following deficit is at least two:

```text
Number_of_turns - (
  Animals_actions + Association_actions + Build_actions +
  Cards_actions + Sponsors_actions + X_Tokens_gained_instead_of_action
) >= 2
```

One qualifying losing row flags the complete `table_id`; both players and all
matching Logs observations receive `is_corrupted_game = TRUE`. Missing inputs
are not converted to zero and leave a table unclassified. Prepared Full Sample
and Logs retain the flag, while Players, Cards, Opening Hand, Maps, Combos,
Endgames, Sponsor Endgames, Actions, MW Action Cards, Icons, Predictors, Build,
Conservation, Scoring, Workers, Arena, Records, player indexes, Tournament H2H,
and component-CI source derivatives exclude flagged tables at their first
analytical boundary. Home and `home_observations_prepared` deliberately retain
them. Source BigQuery tables are read-only.

## Population Contract Matrix

Do not infer statistical parity from matching labels alone. The canonical,
machine-readable inventory is `ark-nova-function/audit_population_parity.py`;
it records every active route/view family, source derivative, observation unit,
completion behavior, and special eligibility. Its snapshot audit fails mixed
data versions; additive Synergy intervals are not a supported payload feature.

| Family | Observation unit | Population contract |
|---|---|---|
| Home | table/player moments | all 25 configured maps; completion optional; includes corrupted tables |
| Cards | player-game-card | Full Sample card plays; corrupted tables excluded |
| Opening Hand | player-game-card | Log Sample dealt/kept observations |
| Endgames / Sponsor Endgames | player-game-event | view-specific dealt, scored, and reward eligibility |
| Combos except Card + Action Card | player-game combination | component scope defined by the selected pairing view |
| Card + Action Card | player-game-card-action-card | strict telemetry-complete MW tables only |
| MW Action Cards | player-game-action-card or table-card | strict telemetry-complete MW tables only; By map additionally requires both players on the same map |
| Players General / Comparison | completed player-game | merged analytical identity |
| Players Performance by map | player-game-map | merged identity; completion optional; Last X is per map |
| Arena Elite League | exact-alias Arena game | Games and most metrics use all matched Arena games; only Turns/PPT use completed games |
| Records | ranked or record row | combined MW/Base; spreadsheet populations remain view-specific; Elo Leaderboard has no filter sidebar |

Intentional differences are reported rather than failed: Home's all-map scope,
Opening Hand's Log Sample, table-level versus player-level counts, merged
Players identities versus exact Arena aliases, Records' combined datasets and
manual spreadsheet rows, and spreadsheet-owned leaderboards. Supposedly equal
populations must match in unrounded means and counts under identical filters.
Unless a row explicitly says otherwise, every game-derived family after Home
inherits the canonical corrupted-table exclusion above.

## Current Local Folders

Frontend working copy:

```text
C:\Users\ascri\Desktop\ark-nova-stats-dashboard
```

Backend Cloud Function source:

```text
C:\Users\ascri\Desktop\ark-nova-function
```

Daily Elo/Arena peak updater source:

```text
C:\Users\ascri\Desktop\ark-nova-function\elo_peak_updater
```

Standalone full Elo leaderboard source:

```text
C:\Users\ascri\Desktop\arknova-leaderboard-main
```

Backend folder contains the deployable Function and packaged metadata fallbacks:

```text
main.py
requirements.txt
cards_attributes.csv
merge_players.csv
arena/
tests/
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
https://github.com/emufriends/stats
```

Treat `emufriends/stats` as the canonical GitHub repository.

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
      card-details.js
      endgames.js
      maps.js
      opening-hand.js
      sponsor-endgames.js
      combos.js
    map-catalog.js
    card-catalog.js
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
#/card-details/<card-slug>
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

Visual identity contract:

- Header logo/wordmark from old design has been integrated.
- The dashboard identity is the 1.0 deep marine-green theme. A thin decorative
  multicolor line runs beneath the topbar and the page body has a subtle
  ambient gradient; neither encodes data.
- The `Nova` wordmark and navigation use the established 1.0 treatment.
- Topbar filter button now uses an inline SVG funnel icon, not the hamburger/menu glyph.
- Navigation has Cards, Opening Hand, Maps, Combos, Endgames, Sponsor Endgames, Actions, MW Action Cards, Icons, Predictors, Build, Conservation, Scoring, Workers, Players, Arena, and Records. Home has no rail item; the topbar logo links to it. MW Action Cards is active at `#/mw-action-cards`; all four tabs are functional.
- Endgames uses an hourglass icon; Maps uses a small cluster of board-game-style hexes.
- Rail icons are either complete inline `<svg>...</svg>` elements or the Build PNG mask span. Keep every inline SVG wrapper balanced when reordering nav items; paths/circles outside an opening SVG are silently discarded by the browser.
- Each rail item presents its existing icon inside a compact rounded outline tile. Tile and active-indicator accents are stable per route group (jade, water blue, orchid, or amber); labels remain neutral, and the active tile/left blade receives a restrained matching glow.
- Header topbar includes:
  - MW/Base switch
  - Ark Nova Statistics logo/wordmark
  - Filters button

### app.css

Central stylesheet for all pages. Important conventions:

- Static app uses a dark, deep marine-green Ark Nova theme. Identity accents are
  separate from statistical table colors: value gradients, frequency colors,
  Elo colors, and Type badges must not be recolored with the theme.
- Navigation icons and active indicator blades use stable route colors drawn
  from jade, water blue, orchid, and amber. Rail labels remain neutral.
- MW and Base retain their established ultramarine and gold switch colors.
  Filter-sidebar labels and the Attributes chevron remain neutral rather than
  inheriting the multicolor identity accents.
- The exact pre-trial visual identity is stored in
  `mockups/visual-identity-1.0.zip`, with restoration notes beside it.
- Navigation rail desktop width is 112px; phone layouts use an 84px overlay rail with compact 58px logo tiles.
- Main content gap was adjusted down during layout tuning.
- Filter button was aligned with the main content right edge.
- Filter sidebar remains a right-side overlay.
- Every applicable Filter sidebar ends with a sticky Apply filters footer. The
  footer has an opaque panel background, stays inside the drawer viewport on
  phones (including the safe-area inset), and uses a 3px double top rule as
  the only separator above the action, with 16px breathing room after the last
  filter row. There is no standalone divider between the final mode-toggle
  section and the footer.
- Expanded Cards and Opening Hand Attributes bars use intrinsic-width desktop flex groups with 22px gaps, explicit separators, and 20px horizontal edge padding. Strength and Size remain on one row. On mobile the same intrinsic groups retain the compact one-row layout and scroll horizontally.
- Attribute chevron is deliberately large and uses down/up direction:
  - collapsed = down
  - expanded = up
- Every statistics-table route is viewport-bound: the document itself does not scroll vertically while a table is visible. The shared `.table-scroll` region owns vertical and horizontal scrolling, and the table header remains sticky at its top. Headers, tab bars, other controls above the table, and pagination below it retain their intrinsic height and remain visible; only the marked table-host chain may shrink.
- `app.js` discovers visible `.table-scroll > table` regions after each route/render and marks their ancestor chain with `dashboard-table-*` layout classes. Keep new table views inside `.table-scroll`; do not add page-specific viewport-height offsets. Graph-only, Home, card-details, and Refresh layouts are intentionally unaffected.
- The outer `.table-wrap` is the framed table container. Pagination sits outside `.table-scroll`, so page buttons stay fixed while rows or columns scroll. The shared pagination footer is a compact 40px single-row strip with 24px buttons and 8px vertical breathing room; avoid restoring oversized controls or container padding. The same runtime contract also supports compact side-by-side table panels that do not use `.table-wrap`.
- At the 600px phone breakpoint, the nine-column fixed-width/sticky schema is scoped strictly to `.cards-stats-table` and `.opening-hand-table`. Never attach those `nth-child` rules to bare `#statsTable`: many unrelated routes reuse that ID.
- Wide map matrices retain the 900px canvas, use 11px numerical body text with compact horizontal padding, and keep only the descriptive row-label column frozen. Rank-bearing CP/Action-Card map tables hide the rank and freeze their second column. Combo columns intentionally all scroll.
- Two-column Predictors tables are the exception to the 900px canvas on phones: Condition and Value fit the viewport and use `min-width: 0`.
- Map-pack visibility controls scroll horizontally inside their header on phones so Map Pack 1/2, Legacy, Beginner, and Reset remain reachable without creating page-level overflow.
- Dense compact Build Standard Enclosures and Actions Starting-position tables remain shrinkable in desktop side-by-side layouts, but receive a small internal phone-only scroll canvas so signed values are never ellipsized.
- At 360px and below, five-tab labels may wrap within their equal-width cells. The tab bar itself must remain one row.
- Statistical tables use the thick 2px `.table-wrap` frame. Two-table layouts such as Build Enclosures and Actions Starting position/Upgrades use the same visual frame on each panel even when the DOM wrapper class is page-specific.
- Map header tooltips are a frontend display convention: backend map values remain `Map 1a: Observation Tower`, while tooltips show `Observation Tower (1a)`.
- Normal tables use the shared 900px minimum canvas and scroll horizontally below
  that width. Compact side-by-side tables are the only `min-width: 0` exception.
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
- Minimum plays, client-side; default and Reset value `1000`
- Attributes bar, client-side

The `#` rank is global across every loaded card that meets the current Minimum
plays threshold. Search, Type, and Attributes filters do not renumber ranks.

Round filtering is Cards-only. When fewer than all rounds are selected:

- Backend aggregation changes.
- Some stats become unavailable/hidden/disabled because they are not meaningful in played-round context.

### Card Details Page

Card details is a reusable, unlinked route for every card represented by the
Cards page. Its route is `#/card-details/<card-slug>`, for example
`#/card-details/explorer`. The page keeps the ordinary dashboard shell and
sidebar, and currently contains only a card selector plus an intentionally
empty placeholder for future card-specific content. Card slugs and the
card-to-type lookup come from `cards_attributes.csv` through
`assets/js/card-catalog.js`; no per-card route modules are created. Cards,
Opening Hand, Sponsor Endgames, and the card columns in Combos link their card
names to this route. The selector changes the URL, so a selected card survives reloads
and can be bookmarked. Type-specific sections and optional per-card widgets
will be added inside the shared module later.

Map filter structure is centralized in `assets/js/map-catalog.js`. Every
sidebar that offers map filtering renders the three groups Standard Maps,
Legacy Maps, and Beginner Maps. Standard chips are visible initially; Legacy
and Beginner each use an independent expandable row with a selected/total
count, and their own all/none controls appear when opened. Standard maps are
the default selection for analytical pages; Home deliberately starts with all
25 maps selected. The shared catalog stores both display codes and the full
backend map names, so new map-filtering pages should reuse it rather than
define another local map list.

### MW Action Cards Page

Files:

```text
assets/js/pages/mw-action-cards.js
backend: main.py (`stats_page: "mw_action_cards"`)
```

The route is `#/mw-action-cards`. It is permanently locked to Marine Worlds;
Base is disabled while the page is mounted. The four equal tabs are General,
Draft, By map, and Synergies. General and Draft render one combined payload
locally. By map and Synergies each have a complete daily snapshot.

Marine Worlds can replace two of the five normal action cards with enhanced
special cards. Each player begins the draft with three: choose one and pass two,
choose one of the two received and pass the remaining card, then receive the
last returned card. The player chooses two of those resulting three cards for
the game, and the two cannot share an action type.

`MW_ACTION_CARD_CATALOG` in backend `main.py` is the canonical mapping. Draft
telemetry uses backend identifiers such as `Sponsors 1`, while selected cards
are represented by the action-specific numeric fields (for example,
`Sponsors_Action_Card_Number = 1`). The frontend presents the catalog's
colloquial name, so `Sponsors 1` is displayed as `Trade`.

General has one fixed 20-card catalog and displays global rank, Type, colloquial
Card name, overall picked-player Delta Elo, Delta Elo when the corresponding
action was upgraded, Delta Elo when it remained basic, selected-player Elo, and
Picked%. Only the overall Delta Elo body value is bold. Each Delta population
has its own 95% CI and +/-2-clamped zero-centered color range. Upgrade state is
read from the matching `Upgraded_*_action_card` field; a null flag is treated as
false, matching Actions.

Draft displays global rank, Type, Card, Picked%, Drafted% (1st), Drafted% (2nd),
and Undrafted%. Picked is its default sort. General and Draft retain independent
sort state. The Type header filter is local and does not recalculate global
ranks or color ranges. Picked percentages use the Cards blue playrate bars;
draft-stage percentages use the same bars with a violet-blue scale.

Telemetry completeness is deliberately strict. An eligible table must be MW,
contain exactly two distinct player observations, and both observations must
have valid values for all five `*_Action_Card_Number` fields and all three draft
fields. Numeric values must be integers 0-4 (zero is the normal action card),
and draft strings must be canonical special-card names such as `Animals 2`.
One null, blank, malformed, or out-of-range value on either player excludes the
whole table from every MW Action Cards metric. The derivative tables are rebuilt
daily, so repaired source telemetry becomes eligible automatically. Source
BigQuery tables remain read-only.

By map has the CP-by-map 18-column framework: rank, colloquial Action Card,
the 15 Standard Maps, and overall `Avg`. Only games where both players used the
same map enter this view. Every map and overall cell is an average `elo_delta`
with sample count, sample standard deviation, and 95% CI. Individual map cells
use the regular Elo-delta scale; only the overall `Avg` cell is bold and uses the
Synergy/Actions Avg scale. Raw shows the estimate; vs. avg subtracts that card's
raw overall Avg from each map while leaving the final Avg column raw. The table
defaults to overall Avg descending. Its graph
plots maps on the x-axis, supports local line search/selection and hover values,
and makes no request when graph mode or Raw/vs. avg changes. The sidebar Maps
section is hidden because maps are the table dimensions.

Synergies uses one unordered pair per eligible player-game. The two selected
special cards must have distinct action types and are canonicalized in
`MW_ACTION_CARD_CATALOG` order, producing 160 possible combinations. The values
under each card name are its standalone filtered average `elo_delta`.
`Delta (Sum) = Delta Card 1 + Delta Card 2`, `Delta (Actual)` is the observed
pair average, and `Synergy = Delta (Actual) - Delta (Sum)`. Elo is average
`pre_match_elo`; Picked is the player-game observation count. Delta Actual has a
95% mean CI. The standalone Delta values beneath both card names also have
table-clustered 95% mean CIs. Additive Synergy values remain point estimates
only; no covariance-aware Synergy CI is calculated or displayed. Searches
 may project either pair member into the requested display slot without changing
 the canonical pair or its Synergy point estimate. MW Synergy uses the same
orange-ochre-green, zero-centered, +/-2-clamped color scale as Combos Synergy.

Synergies defaults Minimum picks to 1000 and keeps Type, both card
searches, Minimum, sorting, Rows, and pagination entirely local. Its Type popup
keeps all/none fixed, shows exactly five complete options before internal
scrolling, and is fixed/clamped within the viewport. Global ranks
are recalculated after Minimum picks, then retained while Type/search filters
hide rows. The Minimum control uses the shared warning animation when matching
rows exist below the threshold. Its compact daily rollup retains rating, map,
date, completion, Arena, and Tournament dimensions plus count, sum, squared-sum,
and Elo moments, so filtered requests reconstruct weighted averages and CIs
without scanning raw gameplay rows.

Player-level Delta uses source `elo_delta`, while the visible `Elo` column uses
the selected player's `pre_match_elo`. For game-level draft rates, Player and
Opponent Elo form an unordered pairing: a table qualifies when either player can
occupy the Player role and the other can occupy the Opponent role while satisfying
their respective bounds. Map filters still require both player rows to use a
selected map. Every table contributes at most once per card and category. The
default MW snapshots are:

```text
card-stats/mw-action-cards/general/default-mw.json
card-stats/mw-action-cards/by-map/default-mw.json
card-stats/mw-action-cards/synergies/default-mw.json
```

The General asset contains every General and Draft field. All three assets are
included in the atomic default pack; no Base snapshots exist. Sidebar defaults
are Elo minimum 300, Date From `2025-01-01`, all 15 Standard Maps, and
Completed/Arena/Tournament off. All views use separate 300+ Player and Opponent ranges.
Completed means non-conceded and triggered endgame; Arena and Tournament are
mutually exclusive.

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
- Minimum keeps, client-side; default and Reset value `1000`
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

- `Dealt` counts appearances in the starting `endgame` array from completed games.
- `Scored` counts appearances in `endgame_scores`.
- `Keeprate` is `Scored / Dealt`, so it can exceed 100% due to effects such as Elephants and Adapt.
- Keeprate's numeric value is not capped; only the blue bar width is capped at 100%.
- Percentage cells reserve a fixed non-shrinking label width, including on phones, so
  two- and three-digit percentages retain identical bar-track lengths.
- General-view desktop widths are `5/20/12/12/8/15/9/9/10` percent for
  Rank/Endgame/Delta scored/Delta dealt/Elo/Keeprate/Scored/Dealt/CP.
- Scored/CP stats use completed games only.
- `delta dealt` uses raw completed-game dealt rows for Base.
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

`assets/js/pages/home.js` is the default route and renders 12 aggregate fact tiles. It uses MW/Base plus Elo, map, date, and Completed-only filters. Its defaults are intentionally unrestricted Elo, unrestricted dates, incomplete games included, and all 25 known maps. Map chips are grouped into Standard Maps (1a-14 and T1), Legacy Maps (1-8), and Beginner Maps (A and 0); every group has independent all/none controls and starts fully active. Home passes `exclude_invalid_maps=False`, so the Full Sample and Log Sample aggregates include every configured Home map. Other map-filtered analytical pages use the same three groups but start with Standard Maps active and Legacy/Beginner Maps inactive. Home counts distinct `table_id` values after row-level map/dataset filtering; it does not add per-map counts. A Full Sample table can contain different Map or `is_mw` values for its player rows, so grouped `(Map, is_mw)` counts overlap and are not expected to sum to the Home total. Backend `stats_page` is `home`, with public snapshots under `card-stats/home/`.

The daily refresh also publishes `card-stats/home/defaults.js`, containing both MW and Base payloads in `window.__ARK_NOVA_HOME_DEFAULTS__`. `index.html` loads this small asset before the app so default Home and MW/Base switching render immediately. Filtered requests still use the API, while the JSON snapshots remain the fallback.

Home's backend-owned observation table is partitioned by game date and clustered
by dataset, map, Arena season, and Tournament state. Canonical Elo values remain
`FLOAT64`; they are never rounded merely to make them clustering dimensions.

The Home map selector uses the same grouped map UI: Standard Maps are visible
initially, while Legacy Maps and Beginner Maps each appear as a compact expandable
row with its selected/total count. Opening either row reveals its own chips; all 25
map values remain selected by default.

Every active dashboard Filter bar also exposes a separate `Starting position`
section immediately below Date Range, or immediately below `Last X games` on
Players; when neither control exists, it follows the last common section.
`First player` and `Second player` are
independent multi-select chips, both active by default; the last active chip
cannot be cleared. The restrictive API field is `starting_positions`. It is
omitted when both chips are active, preserving default-snapshot eligibility.
The canonical prepared value is the normalized Full Sample
`Starting_position_in_first_round`; invalid/null values remain in unfiltered
populations but cannot match a one-position filter. Player- and pair-oriented
statistics apply FPA to the focal player before Last X and rolling-history
selection. A table-level distinct-game statistic may remain numerically
unchanged because a valid two-player game contains both positions.

Elo range filtering follows one dashboard-wide missing-value rule. A null
`pre_match_elo` or `opponent_pre_match_elo` is evaluated as `0` only while testing minimum and
maximum bounds. Consequently, a blank/zero minimum retains observations with
missing Elo metadata, a positive minimum excludes them, and a maximum-only
filter includes them as zero. Prepared/source values remain null: Elo averages,
display values, Elo delta calculations, and Experts/Masters classification are
never populated with synthetic zeroes. Once an upstream Elo value is restored,
the next refresh naturally places that observation in its real range.

Pages that expose both Player Elo and Opponent Elo ranges also expose `Use same
Elo range for player and opponent`, checked by default. While linked, editing
either side's minimum or maximum immediately mirrors the corresponding value to
the other side. Unlinking preserves both current ranges and warns that asymmetric
ranges can substantially skew results. The linked preference follows navigation
and reloads in the current browser-tab session through `sessionStorage`; a new
session starts linked. Restoring the link copies the Player range to Opponent,
and Reset restores the linked state. Pages with only Opponent Elo, including
Players and Records, do not show this control. The request schema remains the
same and intentionally continues to accept asymmetric ranges.

### Canonical Elo semantics

Unless a label explicitly says otherwise, `Elo` everywhere in the dashboard
means the player's `pre_match_elo`: their rating before that game. `Opponent
Elo` is derived from the unique opposing player row's `pre_match_elo`; the
legacy same-row `opponent_elo` is not used. Tables without one unambiguous
opponent receive a null opponent rating, with the null-filter behavior above.
The legacy Full Sample fields `elo` and `opponent_elo` are excluded at the
prepared Full Sample boundary and must not be used by executable analytical
code or backend-owned derivatives.

The source `elo_delta` remains canonical. Source reconciliation verifies
`elo_delta = post_match_elo - pre_match_elo` whenever all three fields exist.
Public request names such as `player_elo_min`, visible Elo labels, and response
keys such as `avg_elo` remain stable; their values follow these pre-match
semantics. Spreadsheet-owned Peak Elo leaderboards are independent historical
metrics and are not changed by this Full Sample migration.

On phones, Home keeps the navigation rail expanded and reserves its width in the layout. Leaving Home automatically unlocks and collapses the rail so it returns to overlay behavior on other pages.

### Sponsor Endgames Page

`assets/js/pages/sponsor-endgames.js` has `Conservation Points` and `Appeal` tabs backed by `stats_page: "sponsor_endgames"` and `sponsor_endgames_view: "cp" | "appeal"`. It hard-filters to completed games and supports Elo, map, and date filters. The backend starts from distinct sponsor plays, left-joins one maximum endgame value per table/player/sponsor, and treats a missing endgame entry as zero. Thus average points and delta buckets use the played-card population. Configured theoretical values determine valid delta buckets; impossible logged values remain in the overall point average but are excluded from delta buckets. MW-only sponsor cards are omitted client-side in Base. There is intentionally no Elo result column or `avg_elo` payload field. Snapshots live under `card-stats/sponsor-endgames/{cp|appeal}/`.

### Icons Page

`assets/js/pages/icons.js` is routed at `#/icons` and uses backend `stats_page: "icons"`. It reads only the prepared Full Sample and hard-filters to completed tables. One observation is one table/player. The 16 rows are Birds, Herbivores, Predators, Primates, Reptiles, Sea Animals, Bears, Petting Zoo Animals, Africa, Americas, Asia, Australia, Europe, Rock, Water, and Science.

Amount is the mean non-null final icon count. Buckets `0` through `6` are exact counts and `7+` includes every value at least seven. Null icon fields are excluded rather than converted to zero. Each bucket's displayed Delta, sample SD, CI count, and prevalence count come from the same filtered icon/player population; frequency divides the bucket count by that icon's non-null `n_total`. Delta buckets below 1,000 observations use the Sponsor Endgames insufficient-data presentation. Default order is Amount descending.

The full-width icon selector uses the PNG artwork under `assets/img/icons` and groups icons into Species, Habitat, and Other. It has the same 45px structural height as other tab/attribute bars, with compact chips and separators so the table starts at the shared vertical position. It has no all/none control or decorative brackets. Individual icons toggle independently; a fully selected group-button click clears that group, while a partial/empty group-button click selects the whole group. A group remains visually active until all its members are deselected. Selected artwork is full-color and deselected artwork is greyed. Base omits Sea Animals from the selector, table, graph, ranges, and ranking universe. Attributes separators and Icons group separators share the same fixed 2px rule.

The enlarged graph toggle at the selector's right edge swaps the table for an Endgames-style SVG line chart. It is centered within a flexible zone spanning from the final selector separator to the bar's right border. The selector defines the available lines, while the graph legend independently shows/hides those lines. Each icon has a permanent palette position assigned from the complete MW/Base icon order before selector filtering, so hiding lines never recolors survivors. Delta mode plots `Delta (0)` through `Delta (7+)`, omitting missing, impossible, and sub-1,000 points and breaking paths across gaps. Frequency mode plots the same buckets as percentages. Axes scale dynamically; tooltips contain icon, bucket, and value but no observation count.

The graph and legend keep a fixed height with a stable scrollbar gutter, so reducing the available icon lines does not resize or shift the chart. Icon bucket headers use the same styled header-tooltip event path as Sponsor Endgames.

Petting Zoo Animals supports only buckets 0-4 in MW and 0-3 in Base; later table cells are tooltip-free dashes and are absent from graphs and color ranges. The `#` column follows the current sort. Delta-column sorting places valid values first, sub-1,000 values second, and impossible/missing values last while respecting numeric direction inside the first two tiers; only valid values receive ranks. Frequency sorting similarly leaves impossible/missing rows unranked. Unranked rows display an em dash. The page supports MW/Base plus player/opponent Elo, maps, and date filters, and always uses completed games; its Completed-only control is shown checked and locked. Default snapshots are `card-stats/icons/default-{mw|base}.json`.
- Frontend has no build step and no automated browser test suite.
- There are global document listeners in page modules for popups/tooltips. They have not caused data bugs, but a future cleanup could centralize or guard them.
- CSS is large and monolithic.
- Ordinary displayed Elo-delta means use observation-level Student's t
  intervals. Additive combination values are point estimates only; they do not
  have confidence intervals.

## Elo Delta Confidence Intervals

The dashboard exposes two-sided pointwise 95% confidence intervals for these
displayed Elo-delta statistics:

- Cards: delta played and delta in hand
- Opening Hand: delta kept and delta dealt
- Endgames General: delta scored and delta dealt
- Combos: standalone card/general deltas, delta actual (Card + Card), delta on
  map, delta round, and other single-mean Elo-delta values
- Sponsor Endgames: every valid CP/Appeal delta bucket
- MW Action Cards: General/By-map Delta means, standalone Synergy card deltas,
  and Synergies Delta Actual

User-facing table headers abbreviate Elo-delta statistics as `EV` (for example,
`EV (played)` and `EV (in hand)`); the underlying statistic remains the source
`elo_delta` described above.

The standalone component intervals are ordinary table-clustered mean intervals
shown when hovering the parenthetical Delta beneath a card name. Additive
combination/Synergy intervals are intentionally not part of the dashboard.
Other statistics not listed above do not have confidence intervals.

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

Additive Synergy values are deliberately point estimates only. The dashboard
does not calculate, request, cache, stage, or display covariance-aware
combination intervals. This avoids presenting a complex derived interval for
which the maintenance and query cost is disproportionate to its value.

Standalone component CIs remain ordinary table-clustered mean intervals. They
use the exact component population behind the displayed parenthetical card,
action-card, or endgame EV and are loaded from default snapshots or a small
component-only background request for filtered visible rows. Each payload
continues to carry `data_version`; component results are merged only into rows
from the matching displayed request scope.

The refresh passes its newly created data version directly into every snapshot
builder; snapshot workers never rediscover the version from mutable external
state. Atomic pack validation rejects any BigQuery-derived member whose version
does not match that publication. Pack assembly reloads each Cloud Storage
object and downloads its exact generation, bypassing the public browser-cache
lifetime that otherwise could expose the immediately preceding body. The
data-version marker itself is `no-store` and is also read by exact generation.
Component batches are keyed by data version, full backend filter scope, view,
and canonical row identifiers; identical batches use module and persistent
caches. Component CI loading never blocks or reruns the main table query.

The CI count is deliberately separate from visible table counts:

- Cards played: non-null played-row deltas, not distinct-table `Played`.
- Cards in hand: distinct table/player/card in-hand rows, not `Seen`.
- Opening Hand: non-null dealt or kept entries, respectively.
- Endgames scored: scored events from completed games.
- Endgames dealt: the exact completed-game dealt-delta population, including corrected
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

Combination rows do not expose an interaction/Synergy CI. Standalone component
CI fields use the same `<delta_field>_ci95_*` naming and are included in default
snapshots or returned by the component-only filtered request.

### Continuous Numeric Color Scales

`assets/js/color-scales.js` is the shared source for value-dependent frontend colors.
All numeric scales use continuous RGB interpolation; categorical badges and graph-series
identity colors remain discrete.

Elo Delta is zero-anchored independently for every displayed Delta statistic. Its range
 comes from that statistic's complete backend payload after Filter-bar filters and before
 pagination. Observed endpoints, displayed means, and standalone CI endpoints are clamped to
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
Additive Synergy values use this point-estimate palette only; there are no
 additive Synergy CI endpoints. MW Action Cards/Synergies uses the same Synergy scale;
its other Delta columns retain the ordinary Elo-delta palette.

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

### Hidden refresh page and completion status

The unlinked path `/refresh/` is a path-based GitHub Pages entry point, not a
hash route and not a navigation item. It reuses the dashboard topbar/logo while
hiding the dataset switch, Filters button, nav rail, and sidebar. It does not
initialize or preload dashboard snapshots.

The page reads the public, sanitized
`card-stats/refresh/status.json` object and can start the normal main daily
refresh through `manual_refresh: true`. Starting a manual refresh requires the
dedicated `X-Ark-Nova-Refresh-Password` header. The password is supplied through
the page modal and retained only in JavaScript memory until reload; its value
must live in the backend `REFRESH_PAGE_PASSWORD` secret and never in static
assets or documentation.

Scheduled and manual daily refreshes share one tracked runner and a Cloud
Storage lock. The public status contains only state, run ID, monotonic progress,
the current user-facing phase, timestamps, and completed data version. A second
request attaches to the active run instead of starting another rebuild. The
lock becomes replaceable after 90 minutes to recover from a terminated request.

`last_completed_at` advances only after the main refresh reports success and
the atomic default pack has been published. Its frontend format is
`YY-MM-DD, hh:mm:ss UTC`. A failed refresh retains the prior completion time and
the prior snapshots. The status is initially seeded from the canonical default
pack object's publication timestamp. Separate Synergy-CI staging and Card +
Card warming do not change this timestamp.

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

- `Dealt` = count of appearances in the initial `endgame` array from completed games.
- `Scored` = count of appearances in `endgame_scores`.
- `Keeprate` = scored / dealt; it can exceed 100% because extra/scored endgames can come from Adapt or Elephants.
- The Keeprate number remains uncapped. Its blue visualization bar is clamped to 100%.
- `Delta scored` = average elo delta when the endgame appeared in `endgame_scores`.
- `Delta dealt` = average elo delta when the endgame was initially dealt. Base uses raw completed-game
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
and a precomputed table-level concession flag, allowing the 64 metrics to be produced
by one aggregation/unpivot query instead of repeatedly scanning the raw Full Sample.

Definitions:

- Maps are columns; metrics are rows.
- Backend returns standard maps plus hidden legacy maps `1`-`8`, `A`, and `0`.
- Frontend defaults are Legacy Maps excluded, Beginner Maps excluded, and Map Pack 2 included. Each category uses `-` Exclude, `O` Include, and `+` Only; Only forces the other categories to Exclude and requires no new API request.
- Extra maps retain the standard map-column width, so the table scrolls horizontally when either group is enabled.
- In filter sidebars that show grouped map chips, Standard Maps remain visible while Legacy and Beginner use compact expandable rows with selected/total counts. The outer Maps section keeps the normal 2px divider; no dotted subgroup lines are used.
- When horizontal scrolling is active, the sticky `Games` footer has a bottom
  border so it remains visually separated from the scrollbar.
- Natural order is `1a`-`8a`, `9`-`14`, `T1`, `1`-`8`, `A`, `0`.
- `Turns` and `Rounds` are lower-is-better and sort ascending; `Turns` is the default sort.
- Other metrics sort descending and color higher values greener.
- `Games` counts distinct `table_id`; other rows average player-level values.
- `Reputation actions` is the average `Reputation_association_tasks` value. It
  appears after `Partner zoos` and before `X-token gained`, and is also part of
  the Players association-bonus metric group.

Predictors/Specific is a fixed catalog of the currently supported conditions.
The obsolete `Round 1: Humphead Wrasse` and `Round 1/2: New Zealand Fur Seal`
conditions are not part of that catalog or its prepared/snapshot data.

### Build page

The Build route is `#/build`, with `build_view: "enclosures" | "hexes"`.
Enclosures uses the shared standard-map filter. Hexes already displays the map
breakdown in its table, so its sidebar hides the redundant Maps control and the
request uses the complete standard-map set. Hexes is always completed-only;
Enclosures keeps its optional Completed-games control.

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
independent. Both subjects hard-filter to completed tables.

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
second Releases asset. Filter-bar Elo and date predicates apply before both
subjects are aggregated. Projects always uses the complete map universe because
its table already displays the map columns; Project Rewards applies its selected
map filter.

## Scoring page (current behavior)

The active Scoring route is `#/scoring`. Its backend interface is
`stats_page: "scoring"` and `scoring_view: "final_score" | "appeal" |
"conservation_points" | "reputation"`. The four equal-width tabs describe the
four end-of-game tracks: Final score, Appeal, CP, and Reputation. The CP
header has a `Conservation Points` tooltip. Every Scoring observation uses the
dashboard-wide completed-game predicate: `table_conceded = 0 AND
end_game_triggered = TRUE`.

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

All eight assets are refreshed daily and included in the current default pack.
The backend reads the source Full Sample through the backend-owned prepared
table, performs the aggregations, and writes derived snapshots. Source BigQuery
tables remain read-only.

## Combinations performance architecture

Combos has five equal-width, single-row views: Card + Card, Card + Map, Card + Round,
Card + Endgame, and Card + Action Card. Card + Action Card is Marine
Worlds-only. Entering it temporarily selects and locks MW; leaving it restores
the dataset that was active beforehand. Its snapshot is
`card-stats/combinations/card-action-card/default-mw.json`; no Base asset is
generated.

Card + Action Card uses only tables passing the strict MW action-card telemetry
validation. Each deduplicated normal card played by a player is paired once
with each of that player's two selected special action cards. Its formulas are
`Sum = Card Delta + Action Card Delta`, `Actual = the observed pair mean`, and
`Synergy = Actual - Sum`; Elo is the holder's pre-match Elo and Played counts
unique player-game/card/action-card observations. Round filtering accepts a
normal card if it appeared in any selected round. The two directional searches
are independent: normal-card aliases apply only to Card, while colloquial names
and canonical identifiers such as `Animals 2` apply only to Action Card. The
15 Type combinations stack the normal card type above the MW action-card type.
Minimum plays defaults to 1,000; search, Type, sorting, pagination, and minimum
changes are local after the compact payload is loaded.

Its component values are deliberately scoped. The parenthetical normal-card
Delta uses telemetry-complete MW player-games in which that card was played,
not the broader Cards page population. The action-card component uses
telemetry-complete MW player-games in which that action card was selected and
therefore matches MW Action Cards under identical filters and data versions.
The component CI tooltips state these populations explicitly.

Daily maintenance builds `card_action_card_observations` by joining prepared
card plays to `mw_action_card_player_observations` on exact table and player,
then writes `card_action_card_daily_aggregates` with filter dimensions, played
round sets, counts, sums, squared sums, and Elo moments. It publishes point
estimates plus ordinary standalone component/Actual EV intervals; its
additive Synergy remains a point estimate without a CI.

The Actions page has exactly four equal-width tabs: Starting position,
Upgrades, Upgrade order, and Upgrades by map. Combos uses five 20% tracks and
Actions uses four 25% tracks; neither tab bar creates an unused or wrapped row.

Card + Card interactive requests never scan one physical row per pair at query
time. Daily maintenance first builds `card_pairs_prepared`, then collapses it
into `card_pair_daily_aggregates`. The aggregate dimensions preserve dataset,
date, map, Player/Opponent Elo, completion, Arena season, Tournament status,
both cards/types, and both played-round sets. Each group stores observation
counts, Elo counts/sums, and Elo-delta counts/sums/squared sums. Weighted
averages, interactions, sample standard deviations, CIs, and play counts are
therefore reconstructed exactly from moments.

The standalone normal-card components in Card + Card, Card + Map, Card + Round,
and Card + Endgame use the same played-card moment population as Cards under an
identical filter scope. Card + Endgame's endgame component uses the scored
Endgames population. The pair-specific Actual population remains view-specific;
Card + Action Card retains its explicitly telemetry-complete component scope.

Component CI enrichment is a small post-query stage. It reads only requested
canonical rows and never calculates an additive combination interval. There is
no Synergy-CI scheduler, staging promotion, or Synergy-CI cache contract.

Ordinary Card + Card requests use the narrower
`card_pair_scope_daily_aggregates`, which removes the played-round JSON
dimension. Round-filtered requests retain the full aggregate. A cold scope
returns its requested page and range/count metadata first; complete-scope cache
materialization is queued after the response and can never delay that first
page. Until the background scope exists, subsequent controls may issue another
small paged query rather than waiting for the entire population.

The complete default-filter Card + Card scope can be warmed for MW and Base by
the separate authenticated `warm_card_card_defaults` operation. Phase 1 keeps
it disabled unless `CARD_CARD_WARMING_ENABLED=true`, and the
`warm-card-card-default-scopes` Scheduler must remain paused. When deliberately
enabled, its BigQuery jobs use batch priority.
The operation refuses to warm an older data version and returns a retryable
response until the current UTC day's version is published. Scheduler retries
therefore handle an unusually long refresh without warming stale data. This
work is deliberately outside snapshot/default-pack publication: a failed or
slow warm-up can never delay the dashboard's daily assets, and no visitor's
browser sends warm-up traffic.

The default table snapshot contains only rows meeting 1,000 plays, while the
separate versioned scope cache retains every matching pair for the default
standard-map, default Elo/date, unrestricted Arena/Tournament scope. Lowering
Minimum plays, sorting, pagination, pair-type changes, and card-header filters
then use that warmed scope immediately. A non-default filter-bar scope is
materialized into the same `card-card-scopes` cache on its first request.
Minimum plays, sort, page, pair type, and selected cards are deliberately absent
from the scope key: changing those table controls reads the scope cache and
starts no BigQuery job.
The response still contains at most the selected page size. It also returns:

```text
candidate_count_before_minimum
visible_count
highest_matching_play_count
```

The frontend uses these fields to mark Minimum plays when matching combinations
exist but the current threshold hides all of them. When a selected Card + Card
header card has no row in the thresholded snapshot, the frontend consults the
daily-warmed complete scope once to obtain this metadata; it then keeps that
scope active for later Minimum, type, sort, and page changes. During a
scope-cache update, the existing table remains visible in a lightweight
updating state. The compact scope artifact is stored as newline-delimited row
arrays with low-overhead gzip; it is decoded only inside the Function and never
sent wholesale to the browser.

Players default General is snapshot-backed and does not query DuckDB. Filtered
General reads `players_metrics_narrow` and evaluates the all, winner, expert,
and master cohorts as separate compact aggregates; combining all 65 metrics in
one 260-state aggregate caused disk spilling and gateway timeouts. The current
representative full 65-row filtered request takes 5.36-5.75 seconds directly on
the e2-medium VM, and a public one-map/one-starting-position request completes
successfully through the gateway. Exact repeats use the persistent response
cache.

## Filter-performance architecture

Interactive filters read generation-owned DuckDB observation tables rather
than querying BigQuery or repeatedly expanding Logs arrays and reconstructing
opponent/card roles.
Current tables include flattened endgame events, sponsor rewards, Actions
starting-position observations, Projects/Releases counts, Specific predictor
flags, played/in-hand/seen card moments, deduplicated project rewards, CP reward
opportunities, Card + Endgame moments, and Home observations. The Home table
pre-resolves Emu, Petting Zoo, CP-bonus, and Proboscis Monkey checks. Card +
Endgame is additionally collapsed into daily count/sum/squared-sum moments.

Every observation source retains dataset, date, map, exact Player/Opponent Elo,
completion, Arena season, and Tournament classification. This preserves the
existing filter semantics and lets average, sample SD, CI, count, and frequency
results be reconstructed without querying the read-only source tables.

Filtered responses use the in-process LRU and the VM's persistent SQLite
response cache. Immutable DuckDB generations are atomically activated; the
generation/data version and normalized route scope are part of cache keys, so
old results cannot cross a refresh. Endgames, Sponsor Endgames, Maps, and every
other multi-view page include the selected subview in their cache key.

Normal responses expose `Server-Timing` and `X-Request-Id`. The read-only
`benchmark_filters.py` script in the Function project exercises every dynamic
view without invoking maintenance operations. Gateway timeouts must not be
used as a substitute for route optimization: a public request must finish
inside the gateway budget, and any expensive shared population property belongs
in a refresh-time derivative.

The deployed reference matrix places ordinary cold filtered views at roughly
2.4–4.9 seconds and exact repeats at roughly 0.4–1.0 seconds. Card + Card is the
one documented cold-scope exception: an arbitrary new exact scope scans about
8 GB of pair moments and has measured around 8.5–10.6 seconds. Its requested
page is still capped at 100 rows, complete-scope warming is asynchronous, and an
exact repeat or warmed scope returns in about one second without a new query.

While filtered work runs, affected pages keep the previous table visible, dim
it with the shared `stats-updating` state, and replace it atomically after a
successful response. The shared loader aborts a superseded request for the same
page, and request tokens prevent stale responses from winning; an error
preserves the previous table. Client-only switches, sorting, pagination,
expansion, searches, and documented minimum controls remain network-free.

## Players page (current behavior)

The Players route is `#/players`. Its three equal tabs are General, Comparison,
and Performance by map. General and Comparison use `stats_page: "players"` with
`players_view: "general" | "comparison"`; General sends one exact
`players_player`, while Comparison sends up to five exact names in
`players_players`. The selected names remain the visible column labels even when
the backend resolves them to a merged analytical identity. Arena Elite League is a
standalone static page and never participates in account merging.

General and Comparison always use the canonical completed-game population.
Their map filter is grouped into Standard Maps (1a-14 and T1), Legacy Maps
(1-8), and Beginner Maps (A and 0). Each group has independent all/none
controls. The default and Reset state selects every Standard Map and no Legacy
or Beginner Map; an explicit empty selection remains empty rather than silently
restoring Standard Maps. The Players request parser and prepared/default
aggregates accept the same 25-map catalog. The standalone Arena page is
unaffected by these controls.

Performance by map uses `players_view: "performance_by_map"` and sends zero to
eight exact aliases in `players_players`. Eight persistent search rows remain
visible, selected aliases compact toward the top, and aliases belonging to an
already selected merged identity are removed by the private server-filtered
autocomplete. Empty selections render locally. Selected aliases remain the row
labels while all associated accounts contribute to the statistics.

The table copies Maps/Metrics geometry: Player uses the former Metric width and
the visible maps use the same computed map width. Its Map Pack 1, Map Pack 2,
Legacy, and Beginner include/exclude/only controls are local and default to
include/include/exclude/exclude. The backend returns all 25 maps in fixed order;
rows are never sortable and no footer is rendered. Each cell is the selected
identity's average `elo_delta` on that map. Values with fewer than 50 non-null
observations use the tooltip `Insufficient data (fewer than 50 observations).`
The Player and map headers are centered, and the map-control Reset button is
anchored at the far right of the full-width control row. Sufficient visible
cells share one zero-centered table color range, with intensity and CI metadata
clamped to -2/+2.

Performance includes incomplete games by default. Its sidebar has Opponent Elo,
Date Range, Last X, Starting position, Arena Seasons, Completed games only, and
Tournament games only. Starting position is a separate section after Last X;
Arena Seasons is separated from the final mode-filter section, while Completed
and Tournament remain consecutive within that section. Tournament and Arena
seasons remain mutually exclusive while completion is independent. Last X is
applied after the other predicates separately for every
merged identity/map pair, before null Elo deltas are removed from the average
and CI count. A requested 100 therefore uses all 83 qualifying games when only
83 exist on a map. The daily `players_map_performance_rollup` stores count, sum,
and squared sum for the ordinary path; Last X uses the identity-partitioned
recent player-game table. No default Performance snapshot is required.

`merge_players.csv` is the canonical manual account-identity source. In the
local dashboard folder it corresponds to `docs/merge_players.csv` in the
`emufriends/stats` repository. Every non-empty CSV row is one person and
contains at least two exact BGA account names; empty trailing cells are ignored.
Names must be unique across the complete file, case-insensitively, and UTF-8
spelling is preserved. The Cloud Function refreshes the published GitHub copy,
keeps a validated last-known-good Cloud Storage copy, and packages a local copy
for first-deployment/GitHub-outage fallback. A local dashboard edit becomes
automatic for future daily refreshes after it is published to GitHub; otherwise
the backend's packaged fallback changes only after redeployment.

The backend-owned `players_stats_prepared` table assigns every player-game row
a `player_identity`. Listed aliases share a stable merge identity; unlisted
players retain an individual identity. This identity is the first clustering
field, followed by dataset, map, and opponent Elo. The daily
`players_default_prepared` table aggregates the original player-game rows by
identity and retains exact per-account game counts. Metrics are therefore
calculated from all qualifying observations, never by averaging already
averaged account values. All/Winners/Experts/Masters remain ordinary
player-game baselines and are unchanged by identity merging.

General and Comparison filters—including maps, opponent Elo, dates, and Arena
seasons—apply before merged aggregation. `Last X games` ranks the complete
identity by `game_ended_at DESC` and table ID, then keeps the newest X rows
across all associated accounts together. Comparison forbids two aliases from
the same CSV row without publishing those relationships. After three
characters, Comparison autocomplete sends `players_search: true`,
`players_search_term`, the current `players_players`, and `is_mw` to a cached
Cloud Function search that reads the player-index snapshot and in-memory merge
metadata only; it never queries BigQuery. The response contains at most 50
alphabetical eligible aliases and omits all aliases of identities already
selected. The API independently rejects an invalid duplicate identity with a
neutral selection error.
General and Comparison selections still persist across MW/Base changes.

The public MW/Base player-index snapshots contain only `players`; merge groups
and exact associated-account names are never published. If any member of a
group has qualifying observations in a dataset, every alias remains searchable,
allowing a deleted account name to resolve to its associated historical
accounts. General responses expose:

```text
player_game_count
player_selected_game_count
player_associated_game_count
player_is_merged
```

Comparison returns the equivalent fields in each `players` summary entry.
Merged counts display as `selected+associated`; ordinary players display one
number and never show `+0`. Changing the selected alias within a group leaves
metric values unchanged but changes which account contributes the first count.
Identity-aware component caches are keyed by data version, dataset, filters,
Arena seasons, Last X, and resolved identity. Source BigQuery tables remain
read-only; prepared Players tables, indexes, and caches are backend-owned
derivatives.

Players uses `players_metrics_narrow`, rebuilt in each immutable generation
from completed tables after excluding corrupted games. It retains the exact
filter dimensions, `elo_delta`, and the 65 metric inputs but omits unrelated
Full Sample columns.
The refresh also materializes `completed_tables_narrow`; no public query may
regroup the full source table merely to rediscover completed tables. General
computes each cohort in its own aggregate CTE to remain inside the e2-medium's
memory budget, then projects the stable 65-row response contract. Comparison
and Performance by map use the same prepared population. Default General still
comes from the static Players snapshot; selected-player history remains a
separate bounded route.

A Last X value may remain in the sidebar while no General or Comparison player
is selected. In that state the frontend omits it from the statistics request,
the backend returns any applicable baselines, and the retained value is
automatically reapplied when a player is selected again.

General and Comparison also have Arena-style table/graph toggles. History is a
separate cached request (`players_history: true` plus
`players_history_metrics`) against the exact prepared player-game rows. It
resolves aliases to merged identities, applies the canonical completed-game
population and every active Players filter for ordinary metrics, applies Last X
across the merged identity, and orders observations by UTC timestamp plus table
ID. The first point is filtered game 100; each point is the trailing 100-game
average. Null metric values are ignored inside that fixed 100-game frame, while
an entirely null window creates a gap. Responses are compact columnar arrays of
game numbers, timestamps, and rolling values and are cached by data version,
dataset, identity, filters, Last X, and requested group.

The graph-only `Elo` metric is the deliberate exception. It uses
`post_match_elo`, combines MW and Base rows, includes incomplete and conceded
games, and ignores the sidebar filters; only the selected merged player
identity remains in scope. It is a singleton graph group and therefore cannot
be selected together with another history metric. Missing post-match Elo stays
null and does not become zero. Its cache scope is dataset-neutral and excludes
the ignored filter values.

History request ownership is isolated per Players tab. Repeated renders for the
same pending request reuse one promise, while a changed request key cancels only
the prior request owned by that tab. Cancellation, graph closure, navigation,
and stale responses always clear their loading state, so the loading label can
exist only while a live request is attached. History requests do not share
abortable in-flight fetch promises. A 15-second defensive timeout replaces the
loading label with an inline Retry action; successful responses still enter the
normal filtered-response memory cache.

General opens an empty graph after one selected identity has at least 250
filtered games. Its metric legend has no visible group headings: the first
metric activates its compatibility group, compatible unselected metrics gain a
white dot, and other groups stay muted but selectable. Clicking a different
group replaces the current General selection; clicking the active metric
clears the current General selection. The
groups are Elo; action-upgrade percentages; action counts;
Universities/Partner zoos/Reputation actions; X-token gained/spent;
Kiosks/Pavilions; all icon metrics; and singleton groups for every other metric.
The first selection asks
the backend for its complete group, so later compatible selections are local.
Every General metric has a deterministic group-local color; legend dots and
lines use the same resolver, and selecting or removing another metric never
reassigns colors. The palette contains 16 distinct colors so every icon metric
can remain unique. General and Comparison remember their legend scroll
positions independently across selection rerenders and completed requests.
Comparison requires two to five identities, each with at least 250 filtered
games, permits exactly one metric, and draws one color-coded line per player.
Player colors are retained by identity during the mounted comparison graph,
so removing or adding another selected identity does not shift existing colors.
Its unselected metrics remain muted but selectable, and its selected metric has
no colored marker, so it cannot be mistaken for a player-line color.
Both graphs default to game-count x coordinates, can switch locally to UTC date
coordinates, and show only the hovered line's formatted rolling value. In
game-count mode the final filtered game is `0`, earlier games are negative, and
the shared domain starts at the negative largest player game count. A
1,500-game history therefore spans `-1500` to `0`; its line begins at `-1400`
because games 1-99 do not yet have a complete rolling window. Date mode remains
timestamp-based. The footer reads `Rolling average over 100 games` and
underlines the active axis choice; General displays the selected alias above
the plot.

Percent-formatted histories use a hard 100% labeled ceiling, including the four
spending-share metrics whose labels omit `%`. If any plotted value falls below
20%, the lower domain is exactly 0%; otherwise it retains normal padding without
crossing zero. When values reach 100%, an unlabeled 12%-of-plot-height gutter
keeps the lines clear of the Comparison player legend without distorting narrow
percentage ranges. Plot paths are clipped
to the chart. Turns always includes an emphasized horizontal gridline and tick
at 30, while Break% always includes the same treatment at 50%. Each reference
is generated as part of the ordinary six-tick sequence, so no neighboring
automatic label can collide with it. These are the only fixed reference lines.

The 250-game restriction applies only to opening or retaining graph mode; table
filters remain unrestricted. While a graph is active, a proposed filter is
first evaluated by the ordinary aggregate request. If General falls below 250,
or any Comparison player does, the graph and its history remain unchanged, the
sidebar is restored to its last committed values, and no history request is
sent. Superseded aggregate/history requests are aborted and successful changes
replace graph data atomically. The graph shell is viewport-bound and only its
metric legend scrolls vertically.

The standalone Arena route is `#/arena`, uses `stats_page: "arena"` with
`arena_view: "top_100"` for API compatibility, and has one full-width
`Elite League` tab. It owns the season selector, table/graph toggle, day
controls, static-bundle preload, dataset locking, sorting, rating graph, and
controls, static-bundle preload, dataset locking, sorting, rating graph, Arena
Player-header search/autocomplete, and five-player legend. The Player search is
local to the loaded season, uses the shared Players `.players-search-wrap` and
`.players-suggestions` styling, and filters the paginated table without a new
request. The old
`players_view: "arena_top_100"` backend alias remains only for cached-client
compatibility. The Filter button is disabled on Arena, and every season/view/
graph interaction is local after the unchanged bundle has been cached.

Arena metadata is read from `docs/arena/arena_settings.csv` in
`emufriends/stats`, with the backend-packaged `arena/` folder and validated
Cloud Storage metadata as fallbacks. If the public source is temporarily
behind the deployed package, a packaged settings file with more seasons or a
packaged ranking file with the newer ID schema is preferred for that refresh;
otherwise remote-first loading preserves automatic source updates. Each row provides the official
`start_utc`, official `end_utc`, and MW/Base mode. The backend derives
`effective_end_utc = end_utc + 2 hours`: an Arena player-game must have a
non-null `arena_rating_delta`, match the season mode, and satisfy
`start_utc <= game_ended_at < effective_end_utc`. The end-exclusive grace
period includes games started before the official deadline but completed up to
two hours later. Effective intervals are validated against the next season to
prevent overlap.

General and Comparison Arena filters use the prepared row's exact
`arena_season`, with partition-pruning bounds extended through the effective
end. The Elite League uses the same effective interval for Games, Winrate, Peak,
Opp. Elo, PR, Turns, PPT, and rating histories. Peak and graph progression use
`post_match_arena_rating`; Opp. Elo and the opponent component of PR use the
opponent player's canonical pre-match Elo. Games, Winrate, Peak, Opp. Elo, PR,
and rating histories retain all matched Arena games, including concessions
or games without a triggered endgame. Only Turns and PPT use the canonical
completed-game subset. Public day numbering and
official season dates remain based on `end_utc`; the final graph day extends
through `effective_end_utc`. A season is computationally complete after the
effective end, while Elite League availability is controlled by the presence
of a validated `sN.csv` ranking file.

The Arena graph assigns colors by player identity within the mounted season,
not by the current row order. Adding, removing, or searching for another
player therefore never recolors a player who remains selected. The standalone
Arena graph and Players Comparison history graph use this identity-first rule;
metric-history graphs use deterministic metric colors, and other charts use
stable row/card/icon identities.

The Arena graph legend keeps selected players above unselected players while
preserving the source order within each group. Search filtering preserves this
selected-first order. Selecting a player directly from the legend resets the
legend scroll position to the top, so the newly selected player remains visible
after the selected group is moved above the remaining players.

Arena ranking files are CSVs with exactly these columns: `#`, `BGA Name`, `ID`,
and `Rating`. The parser accepts the complete contiguous rank list, not just
the first 100 rows. Nonblank IDs must be positive integers; a blank ID keeps
the spreadsheet row visible but receives no database-derived statistics, and
duplicate source rows are preserved because rank, displayed BGA name, player
ID, and ending rating come directly from the CSV. All other Arena columns are
database aggregates. The prepared Players table retains the source
`player_id`; the Arena bundle queries by that numeric ID rather than by the
display name, which prevents a name change or duplicate name from joining the
wrong account. The payload retains the ID in table rows and graph-series
metadata for internal joins and graph identity, but the Arena table does not
display this implementation detail. Valid player names are rendered as links to
the corresponding Board Game Arena profile; rows with blank or invalid IDs stay
plain text.

S14 is the newest configured and currently ongoing MW Arena season. The Players
Arena Seasons filter exposes every started configured season from the manifest,
even when no ranking sheet exists. The Elite League bundle includes every
player from each season with a validated `sN.csv` ranking file, so S13 is the
newest available Elite League season while S14 has no ranking sheet. The daily
refresh validates all available ranks, rebuilds prepared Arena assignments,
recalculates every available season, and atomically publishes
`card-stats/players/arena-top-100/all-seasons.json`. Season switching,
table/graph switching, graph search, Day X-Y zoom, row-count selection, and
pagination remain client-side after that bundle is cached. The Elite League
table defaults to 100 rows and shows a centered season selector, a left-side
`Showing 1-100 of N players` range, and shared bottom pagination controls; the
row selector also offers 25, 50, and All. All sortable Arena columns use the
displayed `#` rank as an ascending tie-breaker. The current ranked season is
also published as `card-stats/players/arena/latest.json` and included in the
atomic default pack, so the initial table renders from the small bootstrap
snapshot while the all-season bundle loads in the background for older seasons
and complete graph histories.

## Records page (current behavior)

The Records route is `#/records` and is backed by `stats_page: "records"` with
`records_view` set to one of `elo_leaderboard`, `fastest_games`,
`highest_scores`, `biggest_turns`, or `most_icons`. All five views are
functional.

`elo_leaderboard` is the default Records parser and frontend view. Its header
message always reads `Top 100 players (for full leaderboard, click here).`,
with `here` opening `https://emufriends.github.io/leaderboard/` in a new tab. Local
player search may narrow the displayed rows, but the message continues to
describe the underlying Top 100 source.

Elo Leaderboard is a dataset-neutral static view sourced from the public
Google Sheet `1NG3FPP70riMzhHPJ6Suz30bhJxUocFd_rKDKxn0kZbM`, worksheet
`Masters`. The daily refresh reads country from column B, player from C, Peak
Elo from F, and Peak Arena from H. Rows are validated, sorted by Peak Elo
descending, truncated to the Top 100, and assigned permanent displayed ranks
1–100. Peak Arena may be blank or the literal `n/a` when a player has never
played an Arena game; both are stored as missing and display as `n/a`. Once a
peak Arena rating exists, the next valid sheet refresh replaces that value.
Country codes render through the dashboard's FlagCDN flag treatment with
accessible country names. The
sheet has no MW/Base field, so the identical validated leaderboard is published
under both dataset paths. The table is not sortable and does not query BigQuery;
the frontend loads this shared leaderboard only once.

Records as a whole is dataset-neutral in the interface. While `#/records` is
mounted, both MW and Base buttons are active and disabled; the previously
selected global dataset remains internal and becomes active again after leaving
Records. Game-derived views load their MW and Base snapshots in parallel,
attach an internal source-dataset marker, de-duplicate by record identity, and
then apply ordering, search, Type filtering, pagination, and sidebar filters to
the combined population. Records player autocomplete unions and de-duplicates
both player indexes. Elo Leaderboard is loaded once rather than concatenating
its identical assets. FPA filtering is local for the four game-derived Records
views using each focal player's `starting_position`; it does not alter Elo
Leaderboard because that spreadsheet ranking is not a player-game population.
Elo Leaderboard has no active Filter UI: the shared Filters button and drawer
are disabled and hidden while that tab is selected.

Automatic Records rows are individual player-game observations from the
backend-owned `full_stats_prepared` table. Fastest Games also unions manually
extrapolated rows, and Biggest Turns is entirely manual; both use the derived
`records_manual_prepared` table described below. Source BigQuery tables remain
read-only. Automatic Fastest, Highest Scores, and Most Icons rows use the
shared completed-game predicate. The visible default opponent-Elo minimum is
300. Records labels its map groups Standard Maps, Legacy Maps, and Beginner
Maps, with independent all/none controls. Standard starts active; Legacy and
Beginner start inactive. These are browser defaults only:
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

The canonical Fastest supplement is the `Games to add` worksheet (`gid=1836311698`)
of Google Sheet `1RSOjQdZcGmOY7PBsDY7erGz--dtPJLc3ydNArr9bV48`. Only its five
columns Turns, Player, Score, ID, and EPT are consumed; `IDs to check` is not a
dashboard input. Turns, Score, and EPT are authoritative manually extrapolated
values. Dataset, map, date, opponent Elo, Arena status, Tournament status, and
all other filter metadata come from Full Sample. An exact ID/player row is used
when available; because Player is sheet-owned, a spelling difference does not
invalidate the record. In that case map, date, mode, and table-level status are
derived from consistent rows for the table ID, while unavailable player-specific
Elo enrichment remains null. Biggest
Turns uses the first
worksheet of `1SfWmRUo3c2jHbezJDVwXxi3zqEm5RdiZxp4hbHfEl0Q`; the consumed
columns are Flat A, End B, Total C, Player D, Score E, Turns F, Map G, Move H,
Actions I, ID K, Result L, Date M, and Mode N. Result must be W, D, or L and
Total must equal Flat plus End.

The daily refresh downloads both public CSV exports once and validates every
nonblank row. A Fastest table ID must exist in Full Sample because that source
owns every field except the five spreadsheet columns. The maintained Player
value is displayed exactly as entered; an exact player match enriches its Elo,
while a spelling mismatch falls back to unambiguous table-level map, date, mode,
and status metadata. Spreadsheet Turns, Score, and EPT are never compared with
or replaced by Full Sample values. Biggest Turns retains its separate sheet-owned dataset, map, and
date fields; exact upstream matches must agree with its dataset and map, while
source-absent Biggest Turns rows retain their maintained metadata and null
enrichment fields.

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

Records and Arena Elite League body rows use the shared table line-height and
vertical padding; neither has a fixed 43px row height. Their compact
player-search controls must not increase header geometry or move the table when
switching pages.

The global Arena-games-only and Tournament-games-only toggles are inserted in
the final filter section immediately before the Apply control. The exact
Completed-games-only label owns grouping; hidden nested toggles never cause an
outer Arena-season group to be treated as Completed. When a page has a visible
Completed-games-only toggle, the three controls form one consecutive stack with
20px toggle rows, the same 12px row spacing, and no divider between them. Pages
without that toggle use the same reserved bottom section with one divider separating it
  from the preceding filter section; the sticky footer supplies the boundary
  before Apply. A standalone
 mode section has equal 16px clearance from its first and last toggle row to the
 adjacent separators. Existing page
 exceptions remain: Players exposes Arena Seasons in a separate section followed
 by Tournament-only because Arena is selected through season chips,
  Maps/Tournament H2H exposes neither and disables the global Filters button
  entirely; Records uses its own equivalent mode controls. Players and Records table headers use the shared 39.1667px
header geometry; their search inputs are constrained inside that row so search
controls cannot change table positioning.

Records widths are view-specific: Fastest and Highest use Player 20% and EPT
10%; Most Icons uses Player 20% and ID 15%; Biggest Turns uses the exact widths
documented above.

Records player search inputs use a dashboard-owned clear button. Browser-native
search cancel controls are disabled so that a second, browser-colored X is not
shown beside the dashboard control. In Arena Elite League, the active sortable header
uses the accent color for both the complete header text and its sort arrow.
All sortable headers are normalized by the shared shell into a centred flex
pair consisting of a trimmed label box and a fixed 8x12 vector arrow. The arrow
path is geometrically centred for neutral, ascending, and descending states;
header alignment must not be implemented with padding or translate offsets.

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
does not publish a partial leaderboard. Every leaderboard row must include a
non-empty valid two-letter country code; a blank country is a
validation failure, so a later corrected sheet replaces the fallback only after
the entire worksheet validates successfully. The population parity audit reports
the external source and cache metadata so last-known-good use is visible.
Each game-derived Records row
carries `opponent_elo`, `starting_position`, `source_enriched`, `is_arena`, `is_tournament`, and the
available sheet `source_row`, in addition to the displayed fields. The browser
loads both dataset snapshots once and performs Player, Maps, Opponent Elo, Date
Range, FPA, Arena-only, Tournament-only, Type, pagination, and row-count changes locally;
applying or resetting Records filters never calls the Cloud Function or
BigQuery. An empty Elo minimum means zero and an empty maximum means no upper
bound. Missing opponent Elo is compared as zero locally, exactly matching the
backend rule; the stored snapshot value remains null.

The pack has a
schema version; a frontend may reuse the previous successful pack only when its
schema matches, preventing an older payload contract from masquerading as the
current one. A warm browser
therefore renders default Records data from memory/cache and every Records
filter is an immediate in-memory operation.

## Current cross-page polish rules

- Normal single statistics tables use `width: 100%` with a shared `900px`
  minimum canvas on desktop and mobile. Below 900px their `.table-scroll`
  wrapper scrolls horizontally. The only shrinkable `min-width: 0` desktop
  exceptions are the compact side-by-side Actions Starting position, Actions
  Upgrades, and Build Enclosures tables. On phones, the especially dense
  Starting-position and Standard-enclosure children use a small local scroll
  canvas rather than truncating their signed values.
- Clearing any Player/Opponent minimum-Elo input means zero; a blank maximum is
  unrestricted. Home serializes blank minima as zero so its unrestricted
  bootstrap payload still renders synchronously without an API request.
- Where both Player and Opponent Elo ranges are present, the shared linking
  preference sits below the Opponent Elo inputs with deliberate vertical space,
  while remaining part of the same Elo filter section.
- Generic filtered requests accept `arena_only` and `tournament_only`. Both
  default false and are mutually exclusive. Arena means a non-null validated
  `arena_season`, including the configured two-hour end grace period;
  Tournament means membership in the backend-owned tournament table cache.
  Missing classification is false. The fields are materialized once in
  prepared Full Sample and Logs and propagated to Players/card derivatives.
- Arena and Tournament switches appear on Home, Cards, Opening Hand, Endgames,
  Sponsor Endgames, Combos, Actions, Icons, Predictors, Build, Conservation,
  Scoring, Workers, Maps/Metrics, and Records. Maps/Tournament H2H has neither.
  Players General/Comparison has Tournament only because Arena is selected by
  season chips; choosing Tournament clears Arena seasons, and choosing a season
  clears Tournament. Arena Elite League remains static and unfiltered. Reset turns
  both generic switches off. Default snapshots are eligible only while both are
  off.
- Completion controls remain visible on every applicable Filter sidebar.
  Optional views retain their editable value across tab switches; hard-completed
  views display the same control checked and locked. The control is omitted only
  where completion is not a coherent filter, as listed in the canonical
  completed-game section.
- Restrictive FPA requests send `starting_positions` with exactly one of
  `First player` or `Second player`; both selected is represented by omitting
  the field. Every prepared analytical derivative and cache key carries this
  dimension. Frontend Reset restores both chips, and switching tabs within a
  page preserves the current choice. Arena and Refresh have no Filter
  bar and therefore no FPA control. Records applies FPA entirely in memory to
  its combined snapshots.
- Main-header metric/comparison segmented controls use one `24.6667px` slot
  across Predictors, Icons, Sponsor Endgames, Actions, Build, Conservation,
  Scoring, Workers, and Maps. A view change must keep the tab bar and table top
  offset within one pixel.
- Map tooltips use `Map name (code)`, for example `Observation Tower (1a)`;
  backend filter values retain the full `Map 1a: Observation Tower` string.
 - Every applicable sidebar map filter uses three grouped sections in this order:
   Standard Maps, Legacy Maps, Beginner Maps. Standard Maps are visible initially.
   Legacy Maps and Beginner Maps each use an independent compact expandable row
   showing selected/total count; opening a row reveals that group’s chips and its
   own all/none controls. Analytical page defaults and Reset select all Standard
   Maps while leaving Legacy and Beginner inactive; Home is the sole exception and
   starts with all 25 maps active. Build/Hexes and Conservation/Projects have
  no map control because their tables already contain the relevant map
  breakdown. Every map chip exposes its full map name through the shared
  dashboard tooltip (`maps-custom-tip`/`data-tip`) without a visible marker.
- Records/Elo Leaderboard is a filter-free static leaderboard; the shared Filters
  button and drawer are disabled and hidden only for that Records tab.
- Records, Players, Conservation, and Cards map chips use the same five-column
  chip geometry and padding so changing pages does not change their visual
  scale.
- Arena Elite League graph lines retain a player-specific palette assignment for the
  mounted season, so adding or removing selected players does not recolor
  existing lines. Graph hover is line-specific. Pointer coordinates are
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
- `REFRESH_PAGE_PASSWORD`
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
