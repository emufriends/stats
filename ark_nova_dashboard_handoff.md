# Ark Nova Statistics Dashboard — Current Architecture and AI Handoff

This is the canonical onboarding document for the Ark Nova statistics dashboard.
It describes the system that exists now. It is not a changelog, migration diary,
or list of previously fixed defects.

The document is intentionally secret-free. Never add passwords, tokens, webhook
URLs, private keys, service-account JSON, or raw authenticated request headers.

## Start here

The system has four operational boundaries:

1. The static frontend in `C:\Users\ascri\Desktop\ark-nova-stats-dashboard`.
2. The public DuckDB query gateway and private VM service in
   `C:\Users\ascri\Desktop\ark-nova-function`.
3. Cloud Storage snapshots and the atomic default pack used for unfiltered page
   loads.
4. BigQuery and external spreadsheets, which are controlled refresh inputs and
   are never queried by public analytical requests.

For a statistical or API change, read this file, then read:

- `C:\Users\ascri\Desktop\ark-nova-function\README.md`
- `C:\Users\ascri\Desktop\ark-nova-function\contracts\dashboard-routes.v1.json`
- `C:\Users\ascri\Desktop\ark-nova-function\phase3-duckdb-serving.md`
- `C:\Users\ascri\Desktop\ark-nova-function\phase5-source-sync.md`

The phase-prefixed backend filenames are stable module names. They do not imply
that the production architecture is temporary or unfinished.

For Elo peak spreadsheet or standalone leaderboard work, use
`elo_system_handoff.md` instead.

## Repositories and source of truth

| Purpose | Local path |
|---|---|
| Frontend working tree | `C:\Users\ascri\Desktop\ark-nova-stats-dashboard` |
| Publishable Git repository | `C:\Users\ascri\Desktop\ark-nova-stats-dashboard\_publish_repo` |
| Backend and DuckDB tooling | `C:\Users\ascri\Desktop\ark-nova-function` |
| Elo peak updater | `C:\Users\ascri\Desktop\ark-nova-function\elo_peak_updater` |
| Standalone Elo leaderboard | `C:\Users\ascri\Desktop\arknova-leaderboard-main` |

The GitHub repository is `https://github.com/emufriends/stats`. GitHub Pages is
served from `main:/docs`. The root frontend working tree is the convenient local
editing copy; files intended for publication must be synchronized into
`_publish_repo/docs`. Do not push unless the user explicitly authorizes it for
the current task.

The local preview server normally serves the frontend at
`http://127.0.0.1:8767/`. A `?fresh=...` query or `Ctrl+F5` helps distinguish a
real code problem from stale browser modules.

## Production topology

```text
Browser
  ├─ default page load ──> Cloud Storage default pack / snapshots
  ├─ filtered analytics ─> Cloud Run duckdb-gateway
  │                         └─ authenticated request to always-on VM
  │                            └─ private HTTP API on 127.0.0.1:8787
  │                               └─ active immutable DuckDB generation
  └─ /refresh maintenance ─> Cloud Function maintenance endpoint

Daily refresh
  Cloud Scheduler at 00:00 UTC
    └─ authenticated refresh worker on the VM
       ├─ inspect controlled source metadata
       ├─ export changed BigQuery source families
       ├─ import changing spreadsheet/CSV sources
       ├─ build DuckDB derivatives and snapshots locally
       ├─ validate a complete candidate release
       └─ atomically activate database and snapshot pointers
```

Current public query endpoint:

```text
https://duckdb-gateway-ioetmehoha-ew.a.run.app/v1/query
```

The Cloud Function URL remains in `assets/js/pages/refresh.js` only for manual
refresh/status operations. Analytical page modules use the DuckDB gateway.

The serving VM is `ark-nova-duckdb-test` in `europe-west1-c`, configured as an
always-on e2-medium with 4 GiB RAM and a 60 GiB persistent disk. The gateway is
the only public route to the private API. The VM API does not accept arbitrary
SQL, filesystem paths, credentials, publication commands, or generation
management requests.

## Serving contract

The private API exposes:

- `GET /healthz`
- `GET /readyz`
- `GET /v1/status`
- `GET /v1/capabilities`
- `POST /v1/query`

Requests are allow-listed by page and view. Unknown result-affecting fields are
rejected instead of silently ignored. Public requests never fall back to
BigQuery.

The active generation is immutable and opened read-only. A small atomic pointer
selects the active generation and retains a validated rollback generation.
Database activation and snapshot publication are coordinated so the browser
never receives a pack whose data version disagrees with the active database.

The service uses a shared two-thread DuckDB execution pool and a shared
1300-MB buffer-manager budget per database instance, admits at most two analytical
executions, shares identical in-flight requests, and interrupts public work
after 90 seconds. Distinct bursts wait in a bounded ten-second admission queue
before receiving `serving_busy`; the queue is intentionally not unbounded on
the 4-GiB VM. Responses are cached in memory and in a generation-aware
persistent SQLite cache. Cache keys include the generation/data version, route,
normalized scope, and response-contract version.

DuckDB thread/memory settings are global to the database instance, not
per-request reservations; total process RSS and refresh-time system headroom
are verified separately. The persistent refresh worker uses bounded HTTPS
control reads with an in-memory VM identity token, retries uncertain reads
without acknowledging pending work, and is restarted by systemd on failure.
Only HTTP 404 establishes a missing control object. Idle polling launches no
CLI processes; bulk transfers and publication still use the storage CLI.

The builder materializes the compact `game_player_narrow` canonical fact once
per generation. It also materializes `prepared_full_sample_narrow`, a canonical
wide table combining imported source metrics with opponent Elo, completion,
corruption, Arena, tournament, starting-position, and merged-player facts. This
intentional physical copy avoids a six-million-row join on every filtered cache
miss. Expensive route work and Logs arrays are additionally materialized into
compact, route-specific facts.

Page-specific Log Sample eligibility must remain distinct. Cards and Combos
use their stricter two-log-row card population; Endgames, Sponsor Endgames, and
Project Rewards use matching player logs without inheriting that restriction.
Project Rewards' frequency denominator counts matching log rows, not all Full
Sample observations. Compact event facts preserve event multiplicity and must
not be joined back to repeated log rows. Numerical release checks use identical
source versions and bypass snapshots and response caches.

Cards accelerators must preserve each focal player's map, Elo, starting position,
and other filter dimensions separately. Opponents may use different maps: an
arbitrary table-wide map is not a valid substitute. Paired Cards facts combine
side-specific moments only after filtering, count Played/Seen once per table,
and retain repeated played-event weights for EV and ordinary confidence
intervals. Refresh-expanded Combo pairs use canonical numeric card IDs and
independent round masks for both cards; the component baseline remains its
own eligible player-game population. Capability flags come from the generation
manifest and fall back to canonical SQL when a derivative is absent.
Card + Card components reuse the numeric player-side scope where paired Cards
facts are available. They count each eligible played player-game/card once,
including when the card appears in several selected rounds; Cards' own EV
retains its separate repeated-play weighting.


Default-scope snapshots are served before filtered requests. The browser keeps
a bounded in-memory cache and a versioned Cache Storage cache. The current
frontend default-pack schema is defined by `DEFAULT_PACK_SCHEMA_VERSION` in
`assets/js/snapshot-cache.js`; never duplicate that number in logic elsewhere.

## Refresh and publication

The scheduled refresh starts at 00:00 UTC and has a three-hour operational
window. A source-equality check can make a refresh a no-op. BigQuery is used only
to inspect and export controlled source families; all derivatives, analytics,
confidence intervals, and snapshots are calculated on the VM from local data.

The source tables are unpartitioned and have no safe incremental cursor.
Metadata fingerprints avoid queries when a complete source family is unchanged.
When a family changed, the export is bounded and labelled, and local
reconciliation replaces complete changed `table_id` populations. Late rows,
corrections, duplicate multiplicity, and deletions are therefore preserved.

A candidate release is publishable only when:

- source and moving-source manifests are valid;
- the DuckDB database and all required derivatives are complete;
- every required snapshot exists and matches the candidate data version;
- the default pack passes schema and route validation;
- active and rollback descriptors are valid; and
- immutable object sizes and SHA-256 hashes match their manifests.

Any failure leaves the active database, active snapshot pointer, and last
successful completion timestamp unchanged. Arena, Records, and Tournament
inputs use validated last-known-good files if a fresh download fails. Their
status is recorded in `moving_sources/source-status.json` and the generation
manifest.

On the VM, deployed modules are loaded from the immutable
`/home/ascri/current-app` release. `ARK_ROOT=/home/ascri` identifies persistent
data only (`phase2_private_data`, serving pointers, and worker state); refresh
code is never resolved from that directory.

Code/schema cutovers use the backend's coordinated publisher after numerical,
functional frontend, and recovery gates pass. The five-second latency target
is measured separately; explicitly accepted performance exceptions remain
documented and must not be presented as passing measurements. Performance
optimization during rebuilding is deferred and is not a functional release
blocker. The publisher verifies the immutable producer
inventory and stops serving across the code/data transition. Rollback restores
the matched code, database, and snapshot release, not just the database pointer.
Crash recovery uses the write-ahead publication and code-cutover journals;
failed restoration retains its journal for retry. Permission and network
failures when checking a public object never count as proof that it is absent;
publication records are durably synced before their associated writes.
Snapshot producer hashes and
player-alias assets resolve from the installed code bundle, not the data root.
Refresh fingerprints include runtime dependencies and input contracts, while
changes to audit-only scripts do not force a data rebuild.
Reusing snapshot files also requires identical producer/input versions and
verified artifact hashes; the data version alone does not establish freshness.

Specific Predictor event thresholds and opening-hand features are evaluated
within each source-log row. Duplicate player-game log keys retain the raw
producer's observation multiplicity without pooling their event lists.

The hidden `/refresh/` page is a maintenance interface, not a navigation item.
It keeps the top bar but hides dataset, Filters, rail, and sidebar controls. A
manual refresh requires the backend secret and follows the same tracked,
single-run workflow as the scheduler. Its public status object is sanitized and
contains only state, run ID, monotonic progress, phase, timestamps, completed
data version, and the last successful completion time.

## Cost and security boundaries

- Public analytical requests have no BigQuery query permission or fallback.
- The project BigQuery query-usage safety quota is 0.1 TiB/day.
- Source imports have explicit maximum-bytes-billed limits and workload labels.
- The serving identity is distinct from identities that import or publish data.
- The manual refresh password and maintenance token live in Secret Manager.
- The maintenance endpoint is authenticated and must never echo secrets.
- Budget notifications go to the configured owner at the warning threshold.
- The hard budget handler stops only the serving VM at the configured hard
  threshold; it does not delete data and does not automatically restart the VM.
- Budget reports are delayed estimates, not instantaneous spending caps.

## Canonical data semantics

### Elo

The canonical focal-player rating is `pre_match_elo`. The opponent rating is
the unique opposing row's `pre_match_elo` for the same table. Malformed or
non-unique opponent pairings produce null opponent Elo rather than falling back
to another source field.

Visible table headers call Elo delta **EV**. Stable API field names may still
contain `delta` for compatibility. Player graph Elo is the one special metric
that uses `post_match_elo`: it combines MW and Base, includes all statuses, and
ignores sidebar filters for the selected merged player identity.

### Completion

A completed game is non-conceded and has a triggered endgame. Pages with a hard
completed population show `Completed games only` checked, disabled, and locked.
Pages with optional completion keep an editable control. Views where completion
is not a coherent filter omit the control.

### Corrupted games

Every game-derived analytical population except Home excludes a table when a
losing row (`Game_result = 2`) has all required values and:

```text
Number_of_turns - (
  Animals_actions + Association_actions + Build_actions +
  Cards_actions + Sponsors_actions + X_Tokens_gained_instead_of_action
) >= 2
```

One qualifying losing row flags the complete `table_id`, including both players
and matching Logs observations. Missing inputs are not converted to zero and do
not classify a table as corrupted. Source BigQuery tables remain read-only.

### Maps

Analytical pages that offer a map filter show Standard, Legacy, and Beginner
groups. The default is all Standard maps and no Legacy/Beginner maps. Home is the
exception and defaults to all maps. Legacy and Beginner groups are collapsible;
map chips use dashboard-styled full-name tooltips.

### Starting position

The filter is named `Starting position` and accepts `First player` and `Second
player`. Both are selected by default and the final selected option cannot be
removed. The request omits `starting_positions` when both are active. A
restrictive selection applies to the focal player side of an observation.

### Player and opponent Elo ranges

`Use same Elo range for player and opponent` is checked by default and stored in
tab-scoped `sessionStorage`. While checked, min/max edits mirror in both
directions. Rechecking copies the complete Player range to Opponent. Explicitly
unchecking shows the asymmetric-range warning every time; restoring an
unchecked session state does not show it.

### Confidence intervals

Standalone EV means retain their ordinary 95% confidence intervals and shared
hover tooltip. This includes parenthetical card/action-card component values in
Combos and MW Action Cards/Synergies. Component intervals use the exact active
population of the displayed component.

Synergy is a point estimate only. Additive/covariance-aware Synergy confidence
intervals are not part of the frontend, API, snapshots, derivatives, tests, or
documentation contract.

## Population contract matrix

The exact machine-readable route contract is
`ark-nova-function/contracts/dashboard-routes.v1.json`. Treat it as the source
of truth for request fields, response fields, observation units, completion,
dataset behavior, and eligibility. The summary below is for orientation.

| Family | Observation unit and population |
|---|---|
| Home | Table/player moments; all configured maps; completion optional; sole corrupted-game exception. |
| Cards | Card-play observations from Full Sample; configured card catalogue; summary projects excluded. |
| Opening Hand | Dealt/kept opening-card observations from Logs; never substituted with general draws or plays. |
| Maps / Metrics | Completed focal player-games; maps are table columns, not a sidebar filter. |
| Maps / Tournament H2H | Valid two-player tournament tables; no Filter sidebar. |
| Endgames | Valid scored endgame events; completion is mandatory. |
| Sponsor Endgames | Sponsor-specific scored CP or appeal events; completion is mandatory. |
| Combos | Unique player-game pairing units defined by each view; Card + Action Card additionally requires strict MW telemetry. |
| MW Action Cards | Strict telemetry-complete MW player-games; By map requires both players to use the same map. |
| Predictors | Completed paired games with the sidebar scope applied to the focal player. |
| Actions | Completed player-game or action-log observations. |
| Icons | Completed player-game icon observations with the fixed display catalogue. |
| Build | Enclosures may use optional completion; Hexes is completed-only and has no map sidebar filter. |
| Conservation | Projects and Project rewards are completed-only and have no map sidebar filter; CP rewards follows its route contract. |
| Scoring | Completed player-game distributions with route-specific valid values. |
| Workers | General is completed-only; 2 CP Worker follows its optional-completion contract. |
| Players | Merged analytical identities; General/Comparison are completed; Performance by map can include incomplete games and applies Last X per map. |
| Arena | Exact roster aliases joined by numeric BGA player ID; most metrics use all matched Arena games; Turns/PPT use completed games. |
| Records | Combined MW/Base presentation with view-specific database or spreadsheet populations; Elo Leaderboard has no Filter sidebar. |

Matching labels do not guarantee matching populations. Important intentional
differences include Home's all-map/corruption scope, Opening Hand's Logs source,
table-level versus player-level counts, merged Players identities versus exact
Arena aliases, strict MW telemetry, and spreadsheet-owned Records populations.

## Frontend architecture

`index.html` loads the shared shell and cache-busted root modules. `assets/js/app.js`
owns global dataset state, navigation, the shared filter sidebar, global tooltips,
table sizing, and lifecycle transitions. `assets/js/router.js` resolves routes.
`assets/js/page-registry.js` is the only page registry. Every page module exports
the lifecycle contract expected by `app.js` and must clean up listeners,
in-flight requests, timers, popups, and graph state in `unmount()`.

The navigation pages, in order, are:

```text
Home, Cards, Opening Hand, Maps, Combos, Endgames, Sponsor Endgames,
Icons, Actions, MW Action Cards, Predictors, Build, Conservation,
Scoring, Workers, Players, Arena, Records
```

`Card details` and `Refresh` are path-only pages and have no nav item.

The global visual rules include:

- a fixed shell with page scrolling confined to table bodies;
- 40 px table headers;
- 37 px ordinary body rows;
- 52 px Combos and MW Synergies body rows;
- a 40 px pagination footer with 24 px controls and 8 px vertical padding;
- a sticky Apply filters footer separated from content and preceded by 16 px;
- viewport-safe fixed search/type popups; and
- the established EV, count, percentage, CP, and Synergy color scales.

Do not alter numerical color scales as part of general palette work.

Combos pair-Type popups on phones (up to 600 px viewport width) show five
complete 32 px option rows with 5 px gaps in a 180 px internal scroll viewport.
All/none stays outside that viewport. Fixed positioning and the 8 px viewport
margin remain in the page module; tablet and desktop popup sizing is unchanged.

### Shared filter order

Use this order whenever the controls exist:

```text
Player/Opponent Elo → Maps → Round → Date range → Last X games →
Starting position → Arena seasons → Completed/Arena/Tournament toggles
```

The three final game-mode toggles remain one consecutive group. The filter body
scrolls independently; Apply filters remains visible on phone layouts. Reset
restores the page's documented defaults and re-enables linked Elo ranges.

### Dataset behavior

Most pages respect the MW/Base switch. MW Action Cards and Card + Action Card are
MW-only and temporarily lock MW. Records combines MW and Base; both switch
buttons are active and disabled while Records is mounted, and the previous
dataset is restored on exit. Arena follows its page-specific snapshot behavior.

## Page contracts

### Home

Shows the twelve configured overview metrics. It deliberately includes every
configured map and corrupted tables. It is not evidence for the filtered
analytical population used by other pages.

### Cards

Displays card-play EV, opening-hand EV where applicable, Elo, play/seen counts,
play rate, and card type. The configured catalogue excludes the thirteen
summary project rows (Africa, Americas, Asia, Australia, Birds, Europe, Habitat
Diversity, Herbivores, Predators, Primates, Reptiles, Sea Animals, Species
Diversity). Card names link to the reusable Card details route. Search, Type,
Minimum played, sorting, and pagination are client-side over the returned scope.

### Card details

A reusable path-only page keyed by the selected card. The infrastructure and
card route exist; card-type and card-specific content can be added without
creating one page module per card.

### Opening Hand

Uses dealt and kept opening-card observations. Its table interaction mirrors
Cards, but the population is Log-based and must not be replaced with general
draw/play fields.

### Maps

Tabs: `Metrics | Tournament H2H`. Metrics uses completed games and includes
Reputation actions between Partner zoos and X-token gained. Map columns are the
subject of the table, so there is no map filter. Tournament H2H has no Filter
sidebar.

### Combos

Five equal tabs: `Card + Card | Card + Map | Card + Round | Card + Endgame |
Card + Action Card`. Synergy is `Actual - Sum` (or the corresponding contextual
baseline difference). It is shown as a point estimate without a Synergy CI.
Standalone parenthetical EVs and Actual EV retain ordinary intervals. Card +
Action Card is MW-only, directional, and restricted to telemetry-complete games
with exactly two selected action cards. Pair Type keys use canonical title-case
labels. Card + Card types are unordered (`Animal + Sponsor` is the only key,
regardless of card-name order); Card + Action Card keeps the normal-card type
first and the action-card family second. Snapshot and filtered payloads follow
the same Type contract, while matching is case-insensitive for compatibility.

### Endgames

Tabs: `General | CP distribution | CP by map`. All use valid scored endgames and
completed games. Distribution and by-map payloads can render as tables or
graphs without changing the statistical population.

### Sponsor Endgames

Tabs: `Conservation Points | Appeal`. Uses fixed sponsor catalogues and
sponsor-specific valid-value rules. EV moments come from `elo_delta`.

### Icons

Uses the fixed icon catalogue and completed player-game observations. Frequency
and EV sorting operate over the same filtered payload and preserve route-specific
denominators.

### Actions

Tabs: `Starting position | Upgrades | Upgrade order | Upgrades by map`. All are
completed-only. Upgrades by map uses the same map-column/table conventions as
the public module.

### MW Action Cards

Four equal tabs: `General | Draft | By map | Synergies`. All views require
strict MW telemetry. By map keeps regular map-cell EV
coloring and uses the zero-centred Synergy/Avg scale for its bold `Avg` column.
Synergies uses directional card pairs, ordinary standalone component intervals,
and no Synergy interval.

### Predictors

Tabs: `General | Icon | Specific`. They are completed, paired focal-player
comparisons. Specific uses the configured event/timing predicate catalogue.
Sidebar predicates apply to the focal player after pairing with the completed,
non-corrupted opponent; a single starting-position selection must not remove
that opponent. Specific contains 19 MW conditions and 18 Base conditions;
`More reefers` is MW-only.

### Build

Tabs: `Enclosures | Hexes`. Hexes is completed-only and does not expose a map
filter because maps are represented in the table. Keep expanded rows separate
from compact aggregate rows so presentation never changes the population.

### Conservation

Tabs: `Projects | Project rewards | CP rewards`. Projects and Project rewards
do not expose map filters because maps are table dimensions. Completion and
valid-value rules follow the route contract.

### Scoring

Tabs: `Final score | Appeal | Conservation points | Reputation`. Completed
player-game distributions use fixed buckets and route-specific valid-value
denominators. Expanded rows are presentation data, not a second population.

### Workers

Tabs: `General | 2 CP Worker`. General is completed-only. The 2 CP Worker view
uses its own eligibility and optional-completion contract.

### Players

Tabs: `General | Comparison | Performance by map`. Player identities are merged
with `merge_players.csv`. General and Comparison are completed-game metric
matrices and support graph history. Performance by map can include incomplete
games and applies Last X separately per map. `Reputation actions` follows
Partner zoos. Graph-only Elo is first, standalone, combined MW/Base
`post_match_elo`, all statuses, and independent of sidebar filters.

All three player-name controls search the already-loaded, dataset-specific
player-index snapshot in the browser after three typed characters. Comparison
and Performance by map omit names already selected in that view. Their
statistics request remains authoritative for merged identities and rejects two
aliases that resolve to the same person; autocomplete never queries DuckDB.

### Arena

The tab is named `Elite League`. Season rosters come from the maintained Arena
CSV files; player ID is the database join key and is not displayed. Player names
link to `https://boardgamearena.com/player?id=ID`. The table defaults to 100 rows
with pagination. Selected graph players remain at the top and keep stable colors.
Sorting by End uses rank as the tie-breaker. Ongoing seasons may be available as
Players filters before they have an Arena roster. The Players Arena manifest is
metadata-driven, while Arena's all-season/latest bundles remain roster-driven;
a metadata-only season does not displace the newest roster season in Arena.

### Records

Tabs: `Elo Leaderboard | Fastest Games | Highest Scores | Biggest Turns | Most
Icons`. Records combines MW and Base. Elo Leaderboard is spreadsheet-owned,
loads once, has no Filter sidebar, and accepts `n/a` as a valid Peak Arena value
until a peak exists. Fastest Games and Biggest Turns retain their spreadsheet
contracts; other game-derived rows are enriched from the local database and
follow the corruption rule.

## External and moving sources

- Full Sample and Logs originate in BigQuery and are imported through the
  controlled source-sync workflow.
- Tournament metadata is fetched from its maintained Google Sheet and cached as
  a validated last-known-good input.
- `arena/arena_settings.csv` defines seasons. Ended seasons require a valid
  roster; an ongoing season may omit one.
- Arena roster CSVs contain rank, BGA name, player ID, and end rating. ID is the
  canonical join key.
- Records moving-source CSVs are imported and fingerprinted during refresh.
- `cards_attributes.csv` and `merge_players.csv` are release inputs and therefore
  participate in the refresh identity.

Never edit source BigQuery tables as part of a dashboard change.

## Development workflow

1. Read the relevant page module, route entry in
   `contracts/dashboard-routes.v1.json`, and backend adapter before changing a
   statistic.
2. State the observation unit and population explicitly.
3. Keep snapshot and filtered response fields compatible.
4. Add or update focused tests and route-contract fixtures.
5. Run syntax checks and only the tests proportional to the change.
6. Test the unfiltered snapshot path and at least one restrictive filtered path.
7. If response semantics changed, bump the appropriate route/cache/snapshot
   schema and build a new immutable generation.
8. Validate the candidate and rollback descriptors before activation.
9. Synchronize current documentation and code annotations in the same change.
10. Publish or push only with explicit user authorization.

Useful checks:

```powershell
node --check assets/js/app.js
node --check assets/js/snapshot-cache.js

python -m py_compile main.py phase3_api.py phase3_duckdb_service.py phase4_local_routes.py
python -m unittest tests.test_migration_contract_foundation
python phase5_contract_regression_gate.py --pack PATH_TO_CANDIDATE_PACK
python -m unittest discover -s elo_peak_updater/tests -v
```

Use the Python executable and `DUCKDB_PYTHON_PATH` documented in the backend
README when the system interpreter cannot import the bundled DuckDB extension.

## Documentation policy

- This handoff and backend runbooks describe only current behavior.
- Machine-generated reports in `analysis/` are verification evidence, not
  onboarding instructions or architecture authority.
- Do not add “recently fixed,” “used to,” migration-phase progress, dated
  benchmark anecdotes, or completed task lists to current-state manuals.
- Record evolving route semantics in `dashboard-routes.v1.json`, tests, and
  nearby code annotations.
- Keep annotations focused on why a rule exists and what invariant must remain;
  do not narrate the sequence of edits that produced it.
- Whenever behavior changes, update the working handoff and both publishable
  copies: `_publish_repo/ark_nova_dashboard_handoff.md` and
  `_publish_repo/docs/ark_nova_dashboard_handoff.md`.
