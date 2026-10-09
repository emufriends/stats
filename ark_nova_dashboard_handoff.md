# Ark Nova Statistics Dashboard — Current Architecture and AI Handoff

This is the canonical onboarding document for the Ark Nova statistics dashboard.
It describes the system that exists now. It is not a changelog, migration diary,
or list of previously fixed defects.

The document is intentionally secret-free. Never add passwords, tokens, webhook
URLs, private keys, service-account JSON, or raw authenticated request headers.

## Start here

An independent auditor with no project history should first read
`C:\Users\ascri\Desktop\ark-nova-function\AUDITOR_GUIDE.md`. It explains Ark Nova
terminology, source ownership and observation grains, the three execution paths,
the implementation/evidence map, and a safe independent audit procedure. This
handoff supplies the detailed product contract; dated evidence does not replace
verification of the currently installed code and data generation.

The principal agent owns architecture, backend changes, new pages, integration
and deployment. The reviewer/frontend agent focuses on independent review,
frontend work and small obvious scoped fixes. Both use the private local notes
folder `C:\Users\ascri\Desktop\ark-nova-function\agent-coordination`; read its
`README.md` and unresolved notes before overlapping work. Notes supplement this
handoff and code annotations, never replace them, and do not grant authorization
for deployment, production pauses or other consequential actions.

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
  │                         └─ internal-network request to always-on VM
  │                            └─ VM HTTP API on 0.0.0.0:8787
  │                               └─ active immutable DuckDB generation
  └─ /refresh maintenance ─> Cloud Function maintenance endpoint

Daily refresh
  Cloud Scheduler at 00:00 UTC
    └─ authenticated maintenance endpoint queues private VM worker
       ├─ inspect controlled source metadata
       ├─ export changed BigQuery source families
       ├─ import changing spreadsheet/CSV sources
       ├─ build DuckDB derivatives and snapshots locally
       ├─ validate a complete candidate release
       └─ journaled, coordinated database/snapshot activation
```

Current public query endpoint:

```text
https://duckdb-gateway-ioetmehoha-ew.a.run.app/v1/query
```

The Cloud Function URL remains in `assets/js/pages/refresh.js` only for manual
refresh/status operations. Analytical page modules use the DuckDB gateway.

The serving VM is `ark-nova-duckdb-test` in `europe-west1-c`, configured as an
always-on e2-small with 2 GiB RAM and a 60 GiB persistent disk. The gateway is
the dashboard's public route to the private API. The gateway's VM hop uses
internal HTTP networking, not a per-request bearer-token protocol. The production
bind address is not loopback; VPC/firewall restrictions must be verified against
the installed deployment. CORS does not provide authentication. The VM API does not accept arbitrary
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
Database activation and snapshot publication are coordinated with a query pause,
pack-last writes, version validation and durable compensation journals. Individual
pointer replacements are atomic; this is not a single distributed transaction
across the VM and all public Storage objects. Validate both final version parity
and failure/recovery behavior.

The service uses a shared two-thread DuckDB execution pool and a shared
800-MB buffer-manager budget per database instance, admits at most two analytical
executions, shares identical in-flight requests, and interrupts public work
after 90 seconds. Distinct bursts wait in a bounded ten-second admission queue
before receiving `serving_busy`; the queue is intentionally not unbounded on
the 2-GiB VM. Responses are cached in memory and in a generation-aware
persistent SQLite cache. Cache keys include the generation/data version, route,
normalized scope, and response-contract version.

DuckDB thread/memory settings are global to the database instance, not
per-request reservations; total process RSS and refresh-time system headroom
are verified separately. The persistent refresh worker uses bounded HTTPS
control reads with an in-memory VM identity token, retries uncertain reads
without acknowledging pending work, and is restarted by systemd on failure.
Only HTTP 404 establishes a missing control object. Idle polling launches no
CLI processes. Bulk source transfers use the storage CLI; the refresh publisher
uses a persistent authenticated Storage SDK session with streaming gzip.
Installed immutable production code does not change merely because desktop
files change. Consult the backend refresh-efficiency acceptance report for
measured build, publication and resource evidence.

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
a bounded in-memory cache and a versioned Cache Storage cache. Retained payloads
are limited to 128 entries and a 64-MiB UTF-16 serialized-size estimate; this
estimate is not a browser heap limit. Initialization retains pack metadata,
not the complete parsed pack. The current
frontend default-pack schema is defined by `DEFAULT_PACK_SCHEMA_VERSION` in
`assets/js/snapshot-cache.js`; never duplicate that number in logic elsewhere.
The in-memory snapshot key ignores a snapshot URL's page-version `?v=` parameter
(`snapshotKeyUrl`), so every page finds the preloaded default-pack copy whatever `?v=`
it requests; the download itself still uses the original URL. All modules must import
`snapshot-cache.js` with one identical `?v=` string, otherwise the browser creates a
second module instance with its own cache. Pack schema, pack data version and
every member's data version must agree with the session's bootstrap version.
Older Cache Storage packs are not relabelled as current. Validated packs pin
subsequent artifact downloads to their immutable release prefix; stable-alias
responses are checked before caching. Invalid/mismatched snapshots can fall
back to the filtered service rather than displaying stale values.

`assets/js/filter-state.js` captures applied Arena, Tournament and Starting
position scope before the page's Apply or Reset handler runs. Editing controls
without Apply does not change this committed scope. Explicit API fields take
precedence over defaults; normalization does not read sidebar DOM. Reset clears
shared state synchronously, then the page restores its own defaults and submits
one request. Players restores the committed global scope when a proposed graph
filter change fails. Follow-up requests and ordinary CIs use that applied scope.
Map Reset reuses each page's initial selection: Standard-only except Home's
all-map default. Cards, Opening Hand and Endgames rebuild their grouped chips
from those defaults rather than activating every map chip.

## Refresh and publication

The hidden Refresh page distinguishes start acknowledgement from completion.
It correlates status by run ID, ignores the previous run while starting,
reconnects with bounded polling backoff after transport failures and invalidates
pending work on navigation. A late response cannot reopen its password modal.
Passwords remain in page memory only. A status connection failure does not
change the last successful completion time.
If a start acknowledgement is lost, status reconciliation precedes Retry.
After one minute without a matching run, Retry is offered without claiming that
the server refresh failed or treating the previous successful run as this one.

The editable frontend is canonical. `tools/sync-publication.py` stages declared
runtime assets, entry points and maintained handoffs into `_publish_repo/docs`,
or checks their content hashes without writing. It deliberately excludes private
evidence, backend data and repository-level documentation. Staging is not a push.

The scheduled refresh starts at 00:00 UTC and has a six-hour operational
window. A source-equality check can make a refresh a no-op. BigQuery is used only
to inspect and export controlled source families; all derivatives, analytics,
confidence intervals, and snapshots are calculated on the VM from local data.

Production resource settings come from the backend systemd units. The builder
uses two threads and an 800-MB engine allowance; source import has a separate
600-MB allowance. Serial offline snapshot queries use 800 MB and one thread.
Serving shares a two-thread pool and a
800-MB buffer budget per database instance across at most two concurrent
analytical executions. These are engine budgets, not per-request reservations
or total process-RSS caps. Standalone CLI defaults are not deployment settings.

Live analytical HTTP requests are paused for the complete refresh. Existing
requests drain before building starts; the API restarts into a lightweight
status-only mode to release analytical memory. Default snapshot-backed pages,
Arena assets, search indexes and frontend-local controls remain available.
Filtered requests and selected-player statistics receive a clear refresh/retry
message; no long-lived refresh queue is created. Success, failure or worker
termination releases process-owned locks, and the API automatically restarts
normally and resumes requests. Health/readiness/status/capabilities remain
available. Lock files must never be deleted to unlock the pause.
Publication recovery uses the same barrier. Compatible code updates retain exact
producer validation and code/data rollback pairing during the next publication.

The backend uses fresh serial refresh-stage processes (`--isolate-stages`,
selected by `REFRESH_ISOLATE_STAGES`) to release allocator memory between import,
metadata, analytical derivatives, Arena/Records preparation and snapshots. The
coordinator retains reports rather than native preparation allocations, and
resource reports distinguish coordinator and child peaks. Snapshot JSON is streamed, Arena history data is
spooled by season, and pack assembly retains one decoded snapshot at a time.
The serial snapshot builder uses a generation-scoped disk-only response cache,
avoiding duplicate decoded histories; the live API keeps its two-level cache.
Arena snapshots calculate roster statistics once and fill history arrays through
bounded player-ID batches, preserving all players, graph points and ordering.
Season spooling, bounded Arena histories, the disk-only offline cache and streamed
pack assembly are installed behavior. Arena remains automatically refreshed.
Fresh-stage isolation and source-builder batching are installed behavior.
Process-level memory qualification does not establish whole-machine headroom on
a smaller VM; the intended refresh-time interactive-query policy must be measured.
Canonical wide-table construction, seen-card deduplication, played-round summaries,
Cards' combined context joins, symmetric table/card moments and MW Draft ranking/selection joins use disjoint table-ID
batches with checkpoints; these are exact memory boundaries, not statistical
sampling. Batch configuration and qualification evidence live in the backend
resource documentation.
The source-import engine budget can be configured separately from the derivative
budget. Each bounded table/card aggregate keeps both players of a game in the
same bucket, including the ordinary CI sufficient statistics.
Home log features use per-row list reductions instead of population-wide
correlated element joins, retaining duplicate event counts, null handling and
Home's unrestricted population.
Opponent Proboscis detection uses a distinct-player per-table summary, preserving
duplicate/null handling without a correlated join over the full population.
Component-CI request batches deduplicate shared standalone populations before
calculating table-level moments and map the final intervals back to all pair
rows. Counts, filters and the public payload shape remain unchanged.
These mechanisms preserve all payload fields, ordinary CIs and populations.
Their presence in desktop code does not imply installation in the active bundle.
The API and worker share a persistent 1456-MiB memory ceiling with no swap.
The current full-fallback, snapshot, private publication/recovery and resumed
uncached-request workload passes a 2-GiB memory qualification, reserving 400 MiB
for OS/background working memory and 192 MiB for boot-reserved RAM. Process
limits or unit tests alone do not establish this qualification. Production uses
2-GiB e2-small hardware; the complete rehearsal ran under the shared ceiling on
e2-medium, so its duration is not an e2-small timing. Actual lower-CPU refresh
duration and future workload growth still require attention. See the backend resource
documentation and `reports/refresh-pause-2g-qualification-20261003.md`. Some
uncached queries exceed the five-second target; memory qualification is not a
latency pass.
Actual 2-GiB hardware restart, filtered requests, ordinary component CIs and
pause/resumption pass the focused check in
`reports/e2-small-restart-20261003.md`. That focused check does not perform a full
refresh. Complete native workflow timing is separately recorded in
`reports/refresh-duration-implementation-20261004.md`; neither an isolated reuse
measurement nor a previous full-fallback timing predicts the next scheduled
run. Use current private worker accounting to identify its actual workload,
reuse/fallback decisions and duration.

The source tables are unpartitioned and have no safe incremental cursor.
Metadata fingerprints avoid queries when a complete source family is unchanged.
When a family changed, the export is bounded and labelled, and local
reconciliation replaces complete changed `table_id` populations. Late rows,
corrections, duplicate multiplicity, and deletions are therefore preserved.

Metadata-based no-op detection and complete changed-family exports are the
supported import contract. Date or maximum-ID watermarks must not replace it
without a trustworthy source update/deletion cursor and reconciliation proof.

Unchanged source families can reuse checksum-validated local Parquet files.
The editable builder supports conservative reuse of 22 immutable log-scoped relations:
producer/input hashes, DuckDB version, Logs inventory/schema, complete canonical rows for all
logged tables and fresh numeric scope keys must match. Any correction, deletion,
eligibility change or key shift requires a rebuild. Home, Players and
full-population MW facts remain fresh. Missing dependency metadata requires a
full baseline build. The logged-fact producer inventory follows its actual
local import closure, including function-local imports; shared imported modules
remain conservatively whole-file-versioned. Snapshot/publication edits do not
by themselves invalidate these logged facts. Private builder reports record
the exact reuse/fallback reason.

The editable quick-win candidate omits unused sponsor-endgame, project-reward
and action-history event copies while retaining serving event facts. Independent
component/pair references are built on demand by the backend's
`phase5_cardcard_reconcile.py` in a disposable scratch database, with an inactive
source attached read-only. The command checks both datasets and all pairs in
its reported fixed scope and returns pass/fail; exact before/after public bytes
remain a separate acceptance gate. Existing Cards pooled construction and
serving fallbacks are retained. Qualification/deployment status is explicit in
`reports/cards-builder-followup-20261006/README.md`.

The editable backend's ordinary card-CI handler uses the complete request scope over canonical
player/card-play facts, with table clustering, rather than validation-only
component/pair relations. Isolated Cards-chain qualification and rollout
boundaries are recorded in the backend's
`reports/cards-chain-optimization-20261006/README.md`.

The root and installed Cards producer retains its persisted event copy and
builds paired-scope metadata in 65,536 globally indexed table-key batches.
Whole-population validation precedes batching; player-side ordering, nulls and
filter fields remain exact. This applies to fresh and reused-fact refreshes.
No frontend behavior, statistical population, ordinary-CI formula or API fields
change. Full-size evidence is in the backend's
`reports/cc7-rollout-20261006/README.md`: both scopes match exactly; six CI-only
last-bit differences are explicitly precision-qualified (identical through nine
decimal places), not claimed byte-perfect. Other held Cards-chain candidates
are not included in this installed release.

The canonical Cards log producer includes all normalized hand keys in seen,
supporting an opt-in shortcut for redundant hand-only core work. Main-caller
enablement is held by the native public-output gate; the main and generic
callers retain hand-only/null-key behavior. Complete scoped facts, downstream moments,
fallbacks and global cross-log card-set deduplication remain intact.

Private canonical Arena
season spools are copied into all-season/latest assets in bounded UTF-8 chunks;
JSON order, numeric formatting and every history point remain exact. Default-pack
validation is unchanged. The installed bundle does not follow desktop edits
automatically: qualification and rollout status are recorded in the backend's
`reports/quick-win-qualification-20261006/README.md`. INSERT-only and canonical
UPDATE checkpoints remain per bucket; any cadence change requires demonstrated
benefit plus full-size numeric and memory qualification. DuckDB 1.5.5 already prunes
unused fields in Cards pair scope, so explicit projection alone provides no
memory improvement.

Resource measurement is private diagnostics, with no behaviour or
published-data change. `ru_maxrss` is a process-lifetime maximum and cannot say
which step needed the memory, so each step runs in a "resource window"
(`phase5_refresh_metrics.ResourceSampler`: a best-effort daemon thread polling
every 0.5 s; numbers and fixed labels only, never SQL, values or player names;
every read is guarded, so measurement cannot fail or change the measured work).
A window reports peak process RSS, peak service and slice cgroup anon/file/current
bytes (the counters the 1456-MiB ceiling enforces), `memory.events` deltas
(high/max/oom/oom_kill) and peak spill bytes. Where to find it after a run:
(1) derivatives: each entry of `statement_timings` in the generation manifest's
`builder` report gains `peak_*` fields; (2) snapshots: the snapshot output
directory holds `resource-profile.jsonl` (written incrementally, survives a killed
run) and `resource-profile.json` with one record per snapshot (query/component-CI/
write seconds, peak memory, component-CI population queries and lookups), per
Arena season, `arena_bundle`, `player_indexes`, `home_bootstrap`, `default_pack`
and one record per distinct component-CI population; (3) the worker exports
`ARK_RESOURCE_TIMELINE_FILE`, so every stage process appends a memory sample about
every 30 s to `worker/<run-id>.memory-timeline.jsonl`; snapshot start/done events
are streamed to temporary `worker/<run-id>.workflow.stdout.log` during execution.
The worker consumes and removes stdout/stderr logs after completion; failed-run
log tails are retained in private diagnostics. Copy full logs while a run is
active if needed. Persistent resource profiles, timelines and accounting files
are the post-run evidence. These diagnostic files are
not release artifacts and never enter the public snapshot bucket. Read
"Private refresh measurements" in `phase5-source-sync.md` for interpretation:
0.5-second sampling can miss short spikes; cgroup counters include shared charged
cache; nested timings are inclusive. SQL-window memory covers execution, while
its elapsed time also includes fetches. The timeline covers VM processes, not
the separate controlled BigQuery exporter. On non-Linux hosts or without
cgroup v2 the cgroup fields are null. Because `phase5_refresh_metrics.py` is part
of the builder's import closure, deploying it changes the producer fingerprint:
the first run afterwards is a full derivative rebuild (the intended way to obtain
a complete profile), not a reuse night. Tests: `tests/test_resource_measurement.py`.
Audit findings that these measurements are meant to confirm or refute are in
`reports/backend-efficiency-audit-20261005.md`.

Snapshot generation pins the current candidate and retains all ordinary
component confidence intervals. Its private per-attempt SQLite cache computes
standalone component intervals once per normalized scope, telemetry eligibility
and component kind across compatible views. Only small final statistics are
cached; observations remain in DuckDB. Telemetry-restricted card baselines
remain separate, Actual/context intervals are unchanged, and additive Synergy
intervals remain absent. Interactive ordinary-CI requests are unchanged.
Cards and Opening Hand's four MW/Base default artifacts can reuse a parent only
after all logged relations were qualified under matching population,
engine/producer signatures and the complete artifact hash, envelope, contract
and schema validate. A new version envelope is written only after this proof.
Other snapshots, including all Arena statistics and histories, are regenerated
against the current candidate. No old interval is attached to a changed
statistical population.

Refresh timing distinguishes request queue delay from actual worker runtime.
Private reports record stage/query durations without SQL or parameters. RSS
counters are lifetime process peaks; sampled spill bytes are not peak spill.
The private snapshot profiler also samples current RSS per page. These samples
include retained buffers, so fresh-process repeats are needed to attribute a
page's own process peak. Process RSS, engine limits and cgroup memory (including
charged file cache) are distinct, and per-page peaks must not be added together.
Detailed worker failure reports remain on the private VM; a path named
"diagnostics" inside the anonymous-read snapshot bucket is not private storage.
Lossless gzip changes artifact transport only, not table values or populations.
Storage rewrites retain rollback metadata and source-generation preconditions;
the public pack remains the last object published. Detailed runtime and rollout
evidence lives in the backend reports, not in this onboarding contract.

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

VM startup metadata uses the verified backend `phase5_vm_bootstrap.sh` and the
private immutable deployment pointer. Publication dependencies are installed
for the `ascri` worker account. Desktop edits or an uploaded archive alone do
not update the reboot pointer or startup metadata; those must match the
successfully accepted paired release. No loose worker-file bootstrap is used.

Code/schema cutovers use the backend's coordinated publisher after numerical,
functional frontend, and recovery gates pass. The five-second latency target
is measured separately; explicitly accepted performance exceptions remain
documented and must not be presented as passing measurements. Performance
optimization continues independently and is not a functional release
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
producer's observation multiplicity without pooling their event lists. Routes whose
unit is a player-game (Build Enclosures, 2-CP Worker, Upgrade Order) keep only the
first physical log row per player-game (`SOURCE_LOGS_ONE_PER_PLAYER_GAME` in
`phase4_local_routes.py`), so a duplicated log is not counted twice.

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

Production has no legacy analytical BigQuery refresh, Synergy-CI or Card+Card
warming jobs, and no BigQuery analytical derivative tables. The empty
`dashboard_cache` dataset remains; do not recreate its retired derivatives or
re-enable legacy SQL refresh helpers. Keep the DuckDB midnight refresh and
separate Elo updater active. The importer uses upstream sources, and analytical
derivatives are built locally in DuckDB. Permanent cleanup requires an exact
inventory, dependency checks and owner approval; preserve upstream
sources/routines, current and rollback releases, and publication recovery
evidence. Guarded local retention remains the normal generation/export cleanup
mechanism.

Remote object deletion is a separate approval boundary. The
`phase5_remote_retention.py` planner does not yet protect every paired rollback
descriptor/publication journal or fail closed on an unreadable default pack.
Do not run its `--execute` mode until those references are protected and the
owner approves the exact deletion list; this does not disable guarded local
generation/source retention.

## Canonical data semantics

### Players default snapshots and selected-player queries

Players/General snapshots contain only the 65 metric rows for Experts, Masters,
Winners and All; the individual-player column is empty. Snapshot generation
reads the exact prepared cohort summaries and uses an explicitly empty
selected-player branch, rather than scanning all game facts again. The
cohort projection uses a single join and metric catalog; the default query does
not bind individual-player facts or identity metadata. Missing
cohorts preserve metric rows with null values and zero counts. Default-scope
player lookups reuse these cohorts; restrictive filters aggregate their own
matching population. Last X affects the selected identity, not the cohorts.
Comparison and Performance by map have empty initial snapshots. Individual
player statistics and graph histories are VM queries calculated on demand,
not daily per-player snapshots. Autocomplete snapshots contain player names
only. Arena's separate roster/history bundles are a different contract.

### Elo

The canonical focal-player rating is `pre_match_elo`. The opponent rating is
the unique opposing row's `pre_match_elo` for the same table. Malformed or
non-unique opponent pairings produce null opponent Elo rather than falling back
to another source field.

Visible table headers call Elo delta **EV**. Stable API field names may still
contain `delta` for compatibility. Player graph Elo is the one special metric
that uses `post_match_elo`: it combines MW and Base, includes all statuses, and
ignores sidebar filters for the selected merged player identity. Null Elo and
corrupted tables remain excluded.

### Completion

A completed table has exactly two rows and distinct players, no nonzero
`concede`, and true `end_game_triggered` on both rows. This table-wide rule is
evaluated before focal-player filters. Pages with a hard
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

Ordinary route intervals use the mean, sample deviation and non-null observation
count, with a Student-t critical value for small samples. Standalone Combo/MW
component intervals use a table-clustered standard error and mean ± 1.96 SE,
requiring at least two clusters. These are single-mean intervals, not an interval
for their sum or difference. The executable definitions are
`project_ordinary_ci_fields` in `phase3_duckdb_service.py` and
`component_ci_sql` in `phase4_combo_mw_contracts.py`; the auditor guide explains
the differing grains and scope/version checks. `cards/component_ci`
(`_ordinary_ci_sql`) applies every Cards filter in the request (Elo, maps, rounds,
dates, starting positions, completed/arena/tournament) to distinct player-game plays,
clustered by table; it has no hard-coded default scope.

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
| Cards | Eligible played Logs events joined to canonical Full Sample; repeated-play EV weighting, distinct-table Played/Seen counts; configured card catalogue and summary-project exclusions. |
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

The Date-from box starts at the page default (2025-01-01; Maps uses 2026-01-13). A blank
box means all time: pages send `date_from: null`, and a default-snapshot shortcut is used
only when the value equals the page default exactly.

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
The offline builder computes roster statistics once, fills complete histories in
bounded player-ID batches, and spools one season at a time. All-season and latest
compatibility assets preserve every player and rating point. Arena remains in the
automatic refresh; memory optimization does not make past seasons manual-only.

### Records

Tabs: `Elo Leaderboard | Fastest Games | Highest Scores | Biggest Turns | Most
Icons`. Records combines MW and Base. Elo Leaderboard is spreadsheet-owned,
loads once, has no Filter sidebar, and accepts `n/a` as a valid Peak Arena value
until a peak exists. Fastest Games and Biggest Turns retain their spreadsheet
contracts; other game-derived rows are enriched from the local database and
follow the corruption rule. A Biggest Turns row's map is the Full Sample's map when
the row matches a game there; otherwise it is the sheet's short map code translated to
the full map name. `players/arena_top_100` is a compatibility alias returning the Arena
roster (season, rank, player, player_id, end), filtered only by `arena_season`.

Scripts that change the live serving state outside the journaled publication workflow
(`phase5_activate_optimized_generation.py`, `phase5_promote_candidate.py`,
`phase5_publish_snapshot_pointer.py`) refuse to run unless
`ARK_ALLOW_UNCOORDINATED_PUBLICATION=yes` is set (`phase5_uncoordinated_guard.py`). The
request options `refresh_data`, `debug` and `refresh_default_pack` are retired (HTTP 410).
Unknown request fields are ignored; only a route's `request_fields` affect its result.

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

## Pending design exploration: zoo-themed redesign (October 2026)

The user finds the current theme too monochrome green, dark and cold and asked for a warm, lively, zoo/nature look that
stays serious and keeps the EV color gradients prominent. Six mockups live in `mockups/zoo-redesign/` (open `index.html`).
Round 1 was rejected by the user (too childish, serif type, low-contrast tables); round 2 is in `mockups/zoo-redesign-2/` (open `index.html`), built from
their feedback: keep the signpost nav with arrow signs, number chips, square-cornered buttons, colored dots on the header; avoid serif fonts (except maybe the logo),
Inter, glows, gradients, big rounding and an "AI-made" look; every page needs subpage tabs. Feedback details are in `mockups/zoo-redesign-2/README.md`.
Status: **awaiting the user's choice; nothing in `assets/` was changed and nothing was pushed.**
Constraints for whoever implements the chosen direction: keep the locked numeric color scales (`assets/js/color-scales.js`);
light themes need a "pill" rendering of value cells because those colors are tuned for dark backgrounds; the mockups cover
desktop only, so phone layouts (<= 600 px) still need designing; follow the restoration-archive pattern in `mockups/` before
replacing the current theme; deploy only with explicit authorization.
