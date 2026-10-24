# DuckDB Production Serving and Operations

This runbook describes the current private DuckDB service behind the Ark Nova
dashboard. The filename is retained for operational compatibility; this is not
a phase-status document.

For domain terminology, the code/evidence atlas and independent verification,
start with `AUDITOR_GUIDE.md`. This runbook describes implemented operational
contracts; confirm installed bundle/pointer/unit state before assuming any
desktop change is deployed. The own-schema canonical cleanup/extracted helper
is explicitly local-only in `reports/refresh-builder-next-20261004.md`.

## Topology

```text
Static frontend
  +-- default views: Cloud Storage snapshots/default pack
  +-- filtered views: Cloud Run duckdb-gateway
       +-- internal-network HTTP call to always-on VM
            +-- phase3_api.py on port 8787
                 +-- phase3_duckdb_service.py
                      +-- active immutable DuckDB generation
```

The gateway is the dashboard's public query boundary. The production systemd
unit binds the VM API to `0.0.0.0:8787`; its network exposure is controlled by
deployment/firewall configuration. The CLI development default is loopback.
Do not infer network isolation from the CLI default. The API does not accept
arbitrary SQL, paths, credentials, publication commands, or
generation-management operations. No public route falls back to BigQuery.

The public gateway accepts anonymous dashboard readers; its VM hop does not
implement per-request bearer-token authentication. Firewall/VPC configuration
is the access boundary, and CORS is not authentication. Inspect installed
network, IAM and auto-start settings separately from source-code defaults.

## Generation layout

Generations live below `phase2_private_data/generations`. Each complete
generation contains:

- a read-only DuckDB database;
- generation-local snapshots and default-pack inputs;
- source and moving-source manifests;
- route/cache/schema identifiers;
- immutable object hashes and sizes; and
- lineage pointing to its validated parent.

`phase3_private_serving/current.json` is the small atomic serving pointer. It
selects an active generation and a rollback generation. Readers resolve the
pointer for each request and open the selected database read-only. Activation
uses an atomic replace; a partial pointer is never valid.

Use `GenerationManager` for activation, rollback, readiness, and pointer
validation. Do not edit an active generation in place. A source-only database
or partially built derivative set is staging data, not a serving candidate.

## Private API

`phase3_api.py` exposes:

- `GET /healthz` — read-only database health;
- `GET /readyz` — active and rollback readiness;
- `GET /v1/status` — sanitized active-pointer state;
- `GET /v1/capabilities` — route inventory; and
- `POST /v1/query` — allow-listed dashboard requests.

Request bodies are capped at 1 MiB and successful responses at 16 MiB unless a
deployment explicitly changes those limits. Production sets the gateway's
`MAX_RESPONSE_BODY_BYTES=16777216` explicitly; the complete Arena season bundle
requires this response allowance and must not inherit a smaller image default.
Responses are cache-disabled at the HTTP boundary. Request payloads are not logged.

The service uses a shared two-thread DuckDB execution pool, a shared 800 MB
buffer-manager budget per database instance, at most two concurrent analytical
executions, and a 90-second public deadline. These global engine settings are
not per-request reservations or limits on total process RSS. Identical in-flight requests share one execution. Snapshot
construction pins an inactive generation and uses its separate offline deadline.

HTTP admission is bounded before reader threads are created: the API default is
16 connections and the gateway default is 24, with configurable 15-second socket
idle-read timeouts. This is separate from the two analytical execution slots;
it bounds partial-body readers and queued requests rather than reserving DuckDB
memory per connection. It is not an absolute deadline against a client that
continually sends bytes. Capacity rejection returns 503 with `Retry-After`.
Identical callers receive the same mapped success or failure response.

In always-on mode the gateway forwards application errors once, including
refresh pauses and analytical deadlines. It preserves numeric `Retry-After`;
it does not resubmit 503/504 queries. Its default upstream timeout is 110 seconds,
covering the API's 10-second admission wait and 90-second query deadline.
The installed Cloud Run ingress concurrency is four and its request timeout is
120 seconds; the gateway's internal 24-reader cap is a separate limit. Verify
environment overrides and these service settings before deployment. Auto-start
remains disabled.

## Request and route contract

`contracts/dashboard-routes.v1.json` is the authoritative inventory. It defines
all 50 public API contracts (including helpers/compatibility routes), request
fields, required response fields,
observation units, completion rules, and special eligibility.

`Phase3RequestAdapter` is the compatibility-named public adapter. It:

1. validates page/view and request fields;
2. normalizes shared filters through `phase4_local_scope.py`;
3. dispatches to route-specific SQL/projectors;
4. verifies response shape and data version; and
5. caches the serialized public payload.

Internal route/view keys with phase-prefixed names are stable compatibility
identifiers. They are not architecture status. Renaming one requires a full
audit of dispatch maps, snapshots, cache keys, manifests, tests, and clients.

The shared scope covers dataset, maps, rounds where supported, Player and
Opponent Elo, date, Starting position, completion, Arena season, Tournament,
and corrupted-table exclusion. Completion eligibility is materialized once per
refresh. Corruption is table-wide and excluded by every game-derived route
except Home.

Page-specific builders live in `phase4_local_routes.py` and
`phase4_combo_mw_contracts.py`. Generic aggregation is not a substitute when a
route has distinct observation semantics.

Combos pair Types are public contract keys, not raw source values. Card + Card
uses the unordered canonical labels `Animal`, `Project`, and `Sponsor`; Card +
Action Card uses that normal-card label followed by the canonical action-card
family. Snapshot rows, filtered rows, and request filters serialize the same
title-case labels. The response projector normalizes defensively so historical
lowercase source values cannot silently remove otherwise valid rows.

Generations advertising `card_play_filter_fact_*_narrow` and
`card_catalog_narrow` support compact played-card serving across all Combos
views. Card IDs are ordered by canonical card name so numeric pair ordering
preserves the public pair direction. Distinct raw played rounds are retained:
rounds 6 and 7 both display as `6+` but retain their existing observation grain.
Capability detection is internal, never a public request field.

Cards' table/card moment shortcut is valid only without a map restriction and
with its symmetric Elo/both-position conditions. Opponents can use different
maps; a table-level `ANY_VALUE(Map)` must never substitute for focal-player
map filtering. Generations with `cards_pair_scope_*_narrow` and
`cards_pair_fact_*_narrow` filter both focal sides independently before pooling
their moments. Played/Seen count tables once; EV retains played-event weights.
Unknown paired-grain invariants omit that capability rather than dropping
observations. The canonical player-grain query remains the fallback.
Dense table/player keys are generation-local acceleration identifiers, not
public IDs. Paired-fact capabilities require schema version 2 in the builder
manifest; name-only detection must not run dense-key SQL against another schema.
Log-fact reuse also checks every logged table's numeric key against a fresh
scope. Identical Logs alone cannot establish reuse: the complete joined
canonical population and producer hashes must match. See
`phase5-source-sync.md` for the dependency cache and full-build fallback.
`cards_pair_pooled_fact_*_narrow` accelerates tables for which both focal rows
pass every active predicate. It carries numeric keys and exact precomputed
moments, not an arbitrary table map. Partially qualifying tables use separate
side moments; the two disjoint populations are combined only after filtering.

`combo_card_pair_fact_*_narrow` stores narrow canonical card-ID pairs with one
round mask per card. Both masks must independently match selected rounds;
the cards need not have been played in the same round. Component means use
their separate played-card populations. Card + Action Card's compact pair fact
similarly preserves its telemetry-restricted normal-card baseline, while its
action-card baseline includes all eligible selected-action player-games.

Event eligibility is page-specific. Cards/Combos facts enforce their existing
two-log-row rule. Endgames, Sponsor Endgames, and Project Rewards instead use
their matching player-log population through `*_filter_event_narrow` and
`log_player_filter_fact_narrow`. Applying Cards' stricter telemetry condition
to these views loses valid observations. Project Rewards' frequency denominator
counts matching log rows, not the broader Full Sample. Event facts must not be
joined back to repeated log rows, which would multiply their observations.

Players' filtered cohort summaries combine at most six winner/Elo-band buckets.
Each metric retains its own non-null count; money shares remain ratios of
population means, not averages of player-game percentages. Last X applies to
the selected identity, not to the global cohort columns. Arena rosters use a
single typed bulk insert so growing Elite League lists do not incur per-row
autocommit overhead during refresh.

Players/General default snapshots contain the 65 metric rows for All, Winners,
Experts and Masters, with an empty selected-player column. They read the exact
generation-local `players_default_cohorts_narrow` summaries; the no-player
identity branch is explicitly empty and does not scan individual game facts.
It binds no individual fact/identity relation and projects metrics through one
cohort join plus a lateral values catalog, rather than 65 repeated join trees.
Default-scope selected-player requests reuse these same cohorts and calculate
only the selected identity. Restrictive filters use scoped cohort aggregation.
Missing cohorts retain all metric rows with null means and zero counts.
Comparison and Performance by map snapshots contain empty initial results;
individual statistics and graph histories are calculated on demand. Separate
autocomplete snapshots contain player names only, not player statistics.

Predictor comparison flags, icon counts, action starting strengths, and Home
log features can be prepared once as compact filter facts. Home retains its
corrupted-game exception. An available fast fact is not evidence of parity:
validate the same filter scope against an independent same-source producer.

## Caching

`Phase3ResponseCache` retains immutable UTF-8 JSON bytes in process, capped at
32 MiB total, 8 MiB per entry and 128 entries. Override the byte limits with
`PHASE3_RESPONSE_CACHE_MAX_BYTES` and
`PHASE3_RESPONSE_CACHE_MAX_ENTRY_BYTES`; zero disables in-process retention.
Eviction follows insertion/update order, not access order. Replacement, byte
accounting and eviction are synchronized, including promotion from disk.
`Phase3PersistentResponseCache` provides the SQLite-backed second level shared
by API processes. Oversized responses bypass RAM retention but remain available
from SQLite. Each read returns a fresh caller-owned object; mutations cannot
affect a subsequent hit. The byte ceiling bounds retained encoded payloads,
not native query memory, decoded responses or the entire API process. Large
disk-backed hits include JSON decoding and may be slower than retained hits.

Keys include:

- active generation/data version;
- page and view;
- canonical normalized request; and
- response-contract/cache schema.

Generation activation therefore makes stale results unreachable without
requiring destructive cache deletion. A bounded amount of rollback-generation
data may remain warm. Cached values contain only serialized public responses,
never credentials or SQL.

## Snapshots and default scope

Unfiltered default requests are normally loaded by the browser from the atomic
default pack. The private adapter can also serve validated generation-local
snapshots for heavy routes when the request exactly matches the default scope.
Any player selection, Last X value, restrictive filter, custom threshold,
missing asset, stale data version, or schema mismatch uses the route's SQL
builder.

Snapshot and filtered payloads must implement the same public field contract.
The snapshot's `data_version` must equal the active generation. Confidence
intervals or fields from another generation must never be merged into a current
payload.

Standalone EV confidence intervals are supported. Additive Synergy confidence
interval fields are not supported and must not appear in responses or snapshots.

## External metadata inside a generation

The refresh materializes changing metadata into the inactive generation:

- Tournament sheet data;
- `arena_settings.csv`;
- ended-season Arena roster CSVs;
- Records spreadsheet exports;
- `cards_attributes.csv`; and
- `merge_players.csv`.

`phase4_metadata.py`, `phase4_materialize_route_derivatives.py`, and
`phase4_records_source.py` validate and import these sources. The refresh worker
writes `moving_sources/source-status.json` with `fresh` or `last_known_good` for
each input. Missing both a fresh and validated fallback source aborts the
candidate before activation.

An ongoing Arena season may exist in settings without a roster. Once a season
has ended, its roster is required. Arena database joins use numeric BGA player
ID; names are display values.

## Observability

`Phase3AuditLog` writes secret-free JSONL events for readiness, activation,
rollback, cache results, query completion, and query failure. Events may include
generation/data-version IDs, route, request fingerprint, duration, row count,
cache status, and error type. They must not include SQL, request payload values,
credentials, passwords, stack traces, or player/card search terms.

Logging failure must not take down serving. Status and readiness responses are
sanitized.

## Builder and resource limits

`phase2_local_vertical_slice.py` is the complete generation builder despite its
compatibility filename. The production worker supplies two builder threads and
an 800-MB DuckDB engine memory limit; source import has a separate 600-MB limit.
Serial offline snapshot queries use an 800-MB allowance and one thread.
Public serving shares a two-thread execution pool
and an 800-MB buffer budget per database instance; neither is multiplied by the
number of concurrent requests. These engine budgets are not process-RSS caps.
Temporary spill uses the configured spill directory. The checked-in API and
refresh-worker systemd units define production settings; standalone CLI defaults
are not production resource settings.

The API and refresh worker belong to `ark-analytics.slice`. The verified
deployment installer installs `ark-analytics.slice.conf` as the application's
owned slice drop-in: 1456 MiB combined memory and no swap. This ceiling covers
the API, idle worker, refresh coordinator, stage descendants and charged file
cache/kernel memory; it is not multiplied by the number of processes. A 2-GiB
memory qualification reserves a further 400 MiB for OS/background working
memory and 192 MiB for boot-reserved RAM. Production runs on an e2-small VM
with 2 GiB RAM and a 60-GiB disk. The complete memory qualification was measured
under the shared ceiling on e2-medium; do not treat its refresh duration as an
e2-small measurement. Hardware restart verification and subsequent scheduled
refresh evidence are separate from that rehearsal.

Complete native workflow timing is separately recorded in
`reports/refresh-duration-implementation-20261004.md`. Distinguish full fallback,
isolated dependency reuse and the next scheduled workload; only its private
worker accounting establishes that run's duration.

The refresh workflow supports `--isolate-stages`, selected by the worker's
`REFRESH_ISOLATE_STAGES` setting. Source import, derivative construction and
snapshot construction then run serially in fresh child processes. Their private
result files include each child's RSS high-water mark; the coordinator's lifetime
RSS must not be mistaken for the child peaks. This mode does not change serving
connections, query semantics or the atomic publication/rollback boundary.
The Linux worker starts a dedicated workflow process session; deadline expiry
stops its stage children as well, rather than leaving an orphaned candidate
writer after the coordinator exits.
Isolation covers source import, Arena/tournament metadata, analytical building,
Arena/Records derivative preparation and snapshots. No native preparation stage
retains its allocator in the coordinator while the next child runs. Reports
distinguish coordinator RSS, child high-water marks and preparation-stage peaks.
Snapshot JSON is streamed, Arena histories are spooled one season at a time,
and the default pack retains only one decoded member at a time.
Serial snapshot generation uses a generation-scoped disk-only response cache;
each cache read is freshly decoded, so caller mutation isolation is preserved
without retaining or deep-copying large Arena responses. Live serving retains
its normal two-level cache.
Offline Arena history reads use `DUCKDB_ARENA_SERIES_BATCH` (default 512,
range 1-50000). Full-roster statistics are computed once; trusted history-only
queries reuse the same season/dataset/corruption joins and retain every ordered
rating point. These are internal queries, not new public filters or routes.
The season-spooled Arena, history batching, disk-only offline cache and streamed
pack paths are installed. Automatic Arena freshness and every public field remain
unchanged. Fresh-stage isolation and source-builder batching are installed.
The combined refresh-pause qualification is recorded in
`reports/refresh-pause-2g-qualification-20261003.md`. It includes the full
fallback build and snapshots, private publication/recovery, OS/boot headroom,
and uncached serving after automatic resumption. Requalify this complete policy
after material workload or resource changes; a builder-only RSS sample is
not a replacement.
Home uses scalar nested-list reductions and a distinct-player Proboscis summary
to avoid correlated array/opponent joins. Duplicate events, nulls, exact names
and Home's unrestricted population remain unchanged.
Standalone component-CI queries deduplicate shared component identities inside
each request batch before calculating table-level moments, then map the small
final statistics to the requested rows. They preserve means, observation and
cluster counts, intervals, filtering and the existing public response shape.
Serial snapshot generation shares these small ordinary-component results across
views with the same normalized scope, telemetry eligibility and component kind.
`phase5_component_ci.py` stores final statistics in a private per-attempt SQLite
cache; game observations stay in DuckDB and every retry clears the cache.
Telemetry-restricted normal-card baselines do not share with broader card
populations. Map/Round context intervals from point responses remain intact;
unused context-component calculations are not repeated. Interactive requests
are unchanged. The manifest reports unique population-query counts and seconds.
Canonical wide-table construction copies the source columns, adds explicitly
typed canonical columns, and fills them in disjoint table-ID transactions with
checkpoints. Approximate quantiles balance transaction sizes but never
approximate values. Source multiplicity and unmatched null rows remain intact;
column collisions fail rather than silently shadowing a derived field.
Relation cleanup is confined to the builder's own `main` schema, not attached
immutable references. The builder reports `canonical_build_strategy`;
qualification evidence and installed release identity are recorded separately
in `reports/refresh-builder-next-20261004.md`.
Seen-card construction unions normalized drawn cards with display cards in
disjoint table-ID hash buckets, retaining exact DISTINCT/null/trim semantics.
The batch counts are bounded by `DUCKDB_CANONICAL_UPDATE_BATCHES` and
`DUCKDB_SEEN_CARD_BATCHES` (both default to 32, permitted range 1–256).
Played-card round summaries are controlled by `DUCKDB_CARD_PLAY_SUMMARY_BATCHES`
(32 by default, 1–256). Disjoint table-ID buckets bound native LIST/DISTINCT
aggregate state without splitting any player/card group, preserving exact
sorted round lists, nulls, repeated-play weights and per-round counters.
Cards' seen/hand/played core joins use `DUCKDB_CARD_FILTER_CORE_BATCHES`
(32 by default, 1-256). Matching table-ID buckets bound all join/anti-join
inputs together, preserving overlaps, orphan observations and null semantics
without repeatedly spilling the entire seen-card population.
Symmetric Cards table/card moments use matching game/card table-ID buckets
(`DUCKDB_CARD_TABLE_BATCHES`, default 32, range 1-256). No table or cluster
is split, preserving ordinary CI counts, means and second moments while
bounding population-wide aggregate/join spill.
MW Draft ranks only the columns consumed by its output and builds complete
table groups in disjoint hash buckets (`DUCKDB_MW_DRAFT_BATCHES`, default 32,
range 1-256). First-player orientation, telemetry eligibility, selected-card
lists and draft flags are unchanged; no game is split across buckets.
Home's nested-log flags/counts use scalar per-row list operations, preserving
duplicates, nulls and exact names without population-wide correlated element
joins. Home retains its unrestricted corruption/completion population.

Smaller resource settings require qualification, not just a lower DuckDB
`memory_limit`. `phase5_builder_memory_benchmark.py` builds an inactive file
from the already committed local source export and reconciles its relations.
It checks all derivative counts/schemas and exact multisets for the changed
canonical, seen-card and played-round serving facts in bounded buckets; separate full snapshot
comparison covers public values. Count-only checks must not be described as
full numerical reconciliation of every internal aggregate.
Exact comparison uses null-safe row joins when key uniqueness is verified,
with duplicate-preserving `EXCEPT ALL` fallback otherwise. Validation budgets
and partition counts are independent of the builder's measured memory budget.
Regrouped table/card moments additionally require exact keys, counts and filter
dimensions plus tightly reconciled floating-point sums after the underlying
observation facts match exactly. Their unused `ANY_VALUE(Map)` representative
may differ for mixed-map tables, but must be an actual map for that table and
dataset. Map-filtered serving must use player-grain facts, never that representative.
The test must cover the full fallback, snapshots, validation/publication and
the configured request policy with OS/cgroup headroom before a 2-GiB VM is
considered safe. Analytical requests are paused during refresh; uncached reads
must be tested after automatic resumption, not simultaneously with building.
The production
VM and installed budgets remain authoritative until a measured rollout.
For the snapshot-specific qualification and fresh-process page peaks, see
`reports/arena-snapshot-memory-qualification-20261002.md`. Per-page RSS samples
can contain buffers retained from earlier pages; they are not additive allocations.
Cgroup peaks include charged file cache. A hardware downgrade requires measured
headroom during both building and snapshots with the lightweight API, then
representative uncached serving after refresh.

The refresh requires free disk headroom of at least 8 GiB or 120% of the active
database size, whichever is larger. Retention protects active, rollback, and
journal-referenced generations plus the configured newest completed releases.
Run retention only through the provided operational scripts. Local generation
retention keeps the two newest releases plus explicit active, rollback, parent,
candidate, and publication-journal references. Source-export cleanup protects
all retained generation references, the committed source, in-flight input, and
the newest complete export. Unreferenced exports older than one day can be
removed before download/build, preventing repeated failed refreshes from
filling the disk. Malformed reference metadata fails cleanup closed.

These guarantees apply to the guarded local generation/source tools. The remote
`phase5_remote_retention.py` planner does not yet resolve every paired rollback
or journal reference, and does not fail closed when the default pack is
unreadable. Its `--execute` mode must not be used for production cleanup until
those protections are implemented and an exact deletion list is approved.

## Publication and rollback

The release publisher uploads immutable generation-prefixed objects, validates
their hashes and sizes, writes a complete release descriptor, and then advances
the public pointers. The database and snapshot/default-pack pointers are one
coordinated release. A process crash before pointer advancement leaves the
current release untouched; journal recovery completes or compensates an
interrupted publication.

Code/schema cutovers use `phase5_coordinated_publication.py` after numerical,
functional frontend, and recovery acceptance. Measured latency exceptions need
explicit owner acceptance and remain recorded as failures, not converted into
passes. Rebuild-time performance optimization is deferred and does not block
the functional release. The publisher checks snapshot producer hashes against the installed bundle,
verifies the previous code inventory, and stops serving/refresh services across
the code/data transition. The rollback descriptor binds the previous code,
database, and snapshot release. `phase5_rollback_release.py` verifies that code
before restoring data and restarts the matched bundle afterwards. Do not
synthesize rollback from loose files or a local working database. Ordinary
same-code daily refreshes use the regular transactional publisher.
The code cutover also records `code-cutover.json`; use the coordinator's
`--recover` operation after a killed cutover. Recovery refuses to overwrite a
newer unrelated serving generation and restores the recorded code/data pair.
The publication journal records pointer changes and attempted alias uploads
before they happen. If a publisher is interrupted before its final rollback
descriptor exists, the coordinator compensates that journal first. Failed
inverse uploads retain the journal for retry; recovery must never report
success while a public alias still needs restoration. Only an
explicit missing-object response establishes absence. Journal records and
their atomic rename are synced to durable storage before publication writes.
Object-listing permission or transport failures retain the recovery journal.

Snapshot reuse requires a complete hashed artifact manifest with identical
producer, source, moving-source, and contract versions. A matching data version
alone is insufficient after producer code changes. The four MW/Base Cards and
Opening Hand default snapshots also support exact parent reuse: all logged
relations must have been qualified under matching population, producer and
engine signatures, and parent artifact hashes, producer/contract/schema and
envelopes must validate before writing the new generation/data-version envelope.
Other page snapshots are not covered by this narrower proof. Arena statistics
and complete histories continue to refresh automatically using bounded batches
and season spools. The refresh worker runs at
lower CPU/I/O priority than serving and uses a separate 800-MB allowance and
one thread for serial offline snapshot queries; interactive limits remain separate.
The worker's canonical derivative builder is limited to 800 MB, with a separate
600-MB source-import budget and fresh serial stage processes. These are engine
limits rather than promises about total process RSS. Candidate validation must
exercise the real refresh-pause/resumption policy with the deployed limits and
preserve numerical, functional and recovery acceptance. Measured latency
failures remain failures; publication with a deferred performance target requires
explicit owner acceptance rather than relabeling the timing gate as passed.

The persistent refresh worker polls small storage control objects over bounded
authenticated HTTPS reads, caching the VM metadata-server token in memory.
Only an explicit HTTP 404 means that no request/object exists; authorization,
transport and malformed-response errors preserve pending work and retry polling.
Tokens and HTTP bodies are not logged. Idle polling launches no CLI processes.
Bulk export downloads use the storage CLI. Artifact publication uses the
persistent authenticated Storage SDK transport with lossless streaming gzip;
rewrites preserve cache and encoding metadata for exact rollback. Systemd
restarts the worker on an unhandled failure, and durable publication recovery
still runs before another request is accepted.

Specific Predictor features that count events or inspect an opening hand are
computed separately for each imported log row, using a generation-local row ID.
Duplicate `(table_id, player)` source keys retain the raw producer's observation
multiplicity; their event lists are not pooled before a threshold is tested.
The temporary row ID is not part of public payloads or filter/cache identities.
Cards facts are ordered by dense table/card keys for selective scan pruning.
Card+Card component means can share the filtered numeric player-side scope
with pair moments when the generation contains schema-v2 paired Cards facts.
Each eligible played player-game/card contributes once to the component mean;
repeated log rounds do not multiply that baseline. A selected round matches
the corresponding side's played-round presence. Generations without this
capability retain the canonical played-card query.
Candidate-only physical reordering uses bounded, bidirectional `EXCEPT ALL`
checks and invalidates release eligibility before any writes.

## Verification

Structural audits prove only structure. Numerical release readiness requires
the independent route contract and source-grain reconciliation.

Primary checks:

```powershell
python -m unittest tests.test_migration_contract_foundation
python phase5_contract_regression_gate.py --pack PATH_TO_CANDIDATE_PACK
python phase4_local_audit.py
python phase4_route_contract_audit.py
python phase4_independent_reconciliation.py
python phase5_native_route_smoke.py
```

Before activation, also validate:

- every route serializes to the frontend response shape;
- representative unrounded means and counts match independent formulas;
- default snapshots and filtered responses agree under identical scope;
- active/candidate/rollback data versions do not mix;
- cold and warm filtered requests stay inside the public deadline; and
- snapshots and read-only status endpoints remain available during refresh,
  analytical requests are rejected with the refresh message, and serving
  resumes automatically afterward.

Install an experimental immutable code bundle with
`phase5_install_deployment.py --stage-only`; this verifies its inventory without
advancing `current-app`, deployment pointers, or restarting production services.
The refresh-pause gate receives the workflow's atomic `--progress-file`, measures
the combined API/worker/stage memory, and verifies rejection throughout rebuilding
and snapshots plus uncached reads after resumption. A no-op refresh or a
builder-only process sample does not satisfy the combined memory gate.
The latency target is five seconds; the report records the actual serving
thread/memory limits alongside measured refresh overlap and system headroom.
Candidate numerical and route-smoke tools accept `--generation-id` and disable
snapshot/cache shortcuts. They must not change the production pointer to test
an inactive release. Build identities cover runtime producer modules and their
local import closure; diagnostic/audit script edits do not force a data rebuild.
Snapshot code/contract hashes and player-alias assets are resolved from the
installed executable bundle, never from the persistent data root. The release
identity therefore describes the actual producer even when old standalone
scripts remain beside the databases.

## Operational cautions

- Do not grant the serving process BigQuery import permissions.
- Do not add a Cloud Function analytical-query fallback.
- Do not change a population rule without updating the route contract, tests,
  cache schema, snapshots, and dashboard handoff.
- Do not infer equality from similarly named metrics across pages; compare their
  observation units and eligibility first.
- Do not describe shape-only audits as numerical parity.
