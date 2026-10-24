# Controlled Source Synchronization

This runbook describes the current BigQuery-to-DuckDB source import and local
refresh workflow. The phase-prefixed script names are stable operational names,
not indicators of incomplete work.

## Source boundary

The controlled BigQuery source families are:

```text
freestyle-190711.ark_nova.all_games_stat_raw
freestyle-190711.ark_nova.game_log_stat_v2
```

The Full Sample metadata family is rooted in `all_games_stat_raw`, but the
export reads the canonical `all_games_stat` view, not the raw physical table.
That view and `calculatePreMatchElo` routine participate in its fingerprint.
Logs has a separate fingerprint and native extraction. `last_x_games` is not
imported as an authoritative source field because histories are calculated
locally.

The source tables are unpartitioned/unclustered and have no trustworthy
ingestion or update timestamp. Date windows and maximum table IDs can miss late
imports, corrections, and deletions and do not guarantee a smaller billed scan.
The workflow therefore detects unchanged source families from metadata and, when
a family changed, exports the complete family before reconciling changed game
tables locally.

## Cost controls

The maintenance function's October 23 fingerprint repair adds a three-second
metadata quiet check and at most one fresh export retry when exact metadata
comparison fails. It does not change fingerprint fields or waive byte-count,
row-count, schema, view, routine, or unknown-field changes. Every rejected
attempt remains uncommitted; a retry uses a different immutable output prefix.
Private before/after metadata, exact field differences, timestamps and job IDs
are written to the private source bucket under
`phase5/source-sync-diagnostics/<operation>/attempt-<n>.json`, not to the public
snapshot bucket. A diagnostic-write failure cannot authorize an inconsistent
export.

Each query remains capped at 8 GiB or the smaller remaining maintenance budget.
At most two query exports can be submitted (16 GiB maximum reserved, still
within the existing configured 64-GiB maintenance ceiling). Known billed bytes
reduce the reservation; missing billing statistics retain the full reservation.
The export coordinator has a 900-second work deadline, bounded SDK calls and
best-effort cancellation of interrupted jobs. Short diagnostic/cancellation
calls can follow that work deadline; the existing 3,600-second function timeout
is unchanged. Arbitrary query, permission, storage and timeout errors are not
retried as source changes. Manifest writes retain generation preconditions.
The standalone source-sync CLI remains unchanged.

This is a code-only repair: it does not run an export or refresh, publish data,
update VM code, or re-enable the paused daily scheduler. Deployment evidence and
offline tests are in `reports/fingerprint-investigation-20261023/`.

- An unchanged source family performs no BigQuery query, including no dry run.
- A changed Full Sample performs one bounded dry run and one labelled
  `EXPORT DATA` job.
- Logs uses a controlled native table extraction.
- BigQuery jobs are billed to `ark-nova-stats-dashboard` and carry the
  `ark_workload=source_sync` label.
- The Full Sample export has an 8 GiB maximum-bytes-billed ceiling.
- The project-level 0.1 TiB/day query quota is a safety boundary shared by all
  jobs, not a monthly budget guarantee.

The serving identity has no need for BigQuery import permissions. Import and
publication identities remain separate from request serving.

## Planning and export

`phase5_source_sync.py` plans by default:

```powershell
python phase5_source_sync.py --previous PATH_TO_PRIOR_SOURCE --report PLAN.json
```

Execute into a new source directory:

```powershell
python phase5_source_sync.py `
  --previous PATH_TO_PRIOR_SOURCE `
  --output NEW_SOURCE_DIR `
  --execute `
  --report RESULT.json
```

Use Application Default Credentials on the importer. `--cli-auth` is available
on the development desktop for the signed-in Cloud CLI account. Tokens stay in
memory and must not be written to reports.

Deterministic export job IDs attach safe retries to existing jobs. A source
change during export rejects the candidate instead of committing mixed data.
Streaming buffers block commit until ingestion settles. Concurrent writes to a
candidate directory are refused.

`manifest.json` is written last and commits the local source directory. It
contains source fingerprints, job identifiers/bytes, and SHA-256 hashes and
sizes for every Parquet object. A failed transfer or validation leaves no
committed manifest. Remote exports use the private `phase5/source-sync/` prefix.

## Local reconciliation

`phase5_source_reconcile.py` copies the immutable parent database and modifies
only the staging copy:

```powershell
python phase5_source_reconcile.py `
  NEW_SOURCE_DIR `
  CURRENT_DATABASE.duckdb `
  NEW_STAGING_DATABASE.duckdb
```

For each `table_id`, the reconciler compares sorted SHA-256 multisets of complete
source rows. Row order is irrelevant; duplicate multiplicity, nulls, and nested
Logs values remain meaningful.

- Changed tables are replaced in full, including both players and all Logs rows.
- Missing tables are deleted.
- Late low-ID tables are added.
- Unknown schema changes fail explicitly.
- Both source families reconcile in one local transaction.

A failure removes the staging candidate and preserves the parent database and
serving pointer.

## Complete refresh

This is the current workflow contract, not proof that the editable desktop code
matches the installed immutable bundle. Read `AUDITOR_GUIDE.md` for source
ownership, statistical grain, deployed/local boundaries and independent checks.

The normal workflow imports sources, rebuilds local derivatives, generates
snapshots, validates a complete release, and activates it transactionally:

```powershell
python phase5_refresh_workflow.py `
  NEW_SOURCE_DIR `
  NEW_GENERATION `
  --root ROOT `
  --builder phase2_local_vertical_slice.py
```

Production sets `PHASE5_INCREMENTAL_SOURCE=false`: it rematerializes the exact
source tables from committed local Parquet, avoiding a fragmented copy of a
database containing old derivatives. `--incremental-source` is an optional
measured mode, not the deployed default.

"Incremental source" means source tables are reconciled at table grain. It does
not by itself accelerate derivative construction. The source-only staging
database contains stale derivatives and must never become active.

The worker reuses checksum-validated immutable Parquet files for an unchanged
family instead of downloading it again when the other family changes. Hard
links are preferred, with a copy fallback; the candidate inventory commits last.

The editable builder's separate dependency cache may copy 22 log-scoped relations from
the read-only parent. Reuse requires identical producer/input hashes, the Logs
file inventory and schema, DuckDB version, complete wide and compact canonical rows for every
logged table, and unchanged numeric keys in freshly constructed two-player
scopes. Sorted SHA-256 row multisets preserve duplicate multiplicity and nulls.
Full Sample corrections, deletions, changed corruption/completion/identity or
telemetry, and late arrivals that shift keys invalidate reuse. A changed builder
also invalidates it. Missing prior dependency metadata requires a full baseline
build; first deployment therefore does not promise an immediate build speedup.
Signature schema 2 records the engine version and hashes the local import
closure rooted in `phase2_local_vertical_slice.py`,
`phase3_cards_pair_contracts.py` and `cards_attributes.csv`. Function-local
imports participate. Shared imported catalogue/route modules remain
conservatively whole-file-versioned; snapshot/publication code is not a root
of this logged-fact dependency proof. `log_reuse_decision` records the fallback
reason and changed signature fields, or the number of reused relations.

Independent Card+Card references are validation-only, not nightly/reuse inputs.
`python phase5_cardcard_reconcile.py <inactive-generation.duckdb>` constructs
them in a disposable disk-backed scratch database with canonical source facts
attached read-only. Its reported fixed scope is Standard maps, date-from
2025-01-01, both Elo minima 300 and optional completion off. The command exits
nonzero on mismatched counts, keys, nulls or unrounded statistics outside the
tight reduction-roundoff bound. Exact before/after public bytes remain a
separate mandatory gate. Run full-size audits serially under the pause/resource
policy, not alongside live queries. Qualification/deployment status is explicit
in `reports/cards-builder-followup-20261006/README.md`. Cards pooled construction
and compatibility fallbacks are unchanged.

The editable ordinary card-CI handler derives its table-clustered component means from
canonical player/card-play facts under the complete request scope; the omitted
diagnostic relations are not serving dependencies. Current isolated Cards-chain
qualification is recorded in `reports/cards-chain-optimization-20261006/README.md`.
Experimental files are not part of the installed producer until the complete
numeric, artifact and memory gates pass and a verified rollout installs them.
The isolated event-copy and bounded-scope contract is documented in
`reports/cards-events-scope-optimization-20261006/README.md`. Event-grain
deduplication remains mandatory. A bounded scope must validate the whole eligible
population before batching and assign keys globally, not per batch. Retiring a
raw event copy requires coordinated logged-reuse/worker/population inventories
and producer-signature invalidation. The persisted event copy remains in the
root and installed workflow. Paired scopes use 65,536 globally indexed key
batches after the complete eligibility check, for both fresh and reused facts.
`batch_size=None` is the independent qualification control. Full-scope parity,
complete-builder memory and the narrowly bounded CI precision exception are
documented in `reports/cc7-rollout-20261006/README.md`; raw-byte failures remain
available. No schema, population, formula or public API change is involved.

Canonical Cards core construction supports an opt-in normalized hand-in-seen
fast path that omits only the redundant hand-only anti-join. Main-caller
enablement is held while its native public-output gate is unresolved. The
generic helper and current main caller use the complete union, preserving
hand-only and null-key behavior.
Dataset splitting/enrichment, complete fallback facts, downstream moments and
global cross-log card-set deduplication retain their existing contracts.

The canonical builder drops its three TEMP rating/concession lookups directly
after constructing `game_player_narrow`; subsequent canonical enrichment and
page facts use that persisted player-game relation. Releasing these dead
lookups bounds retained working memory without changing rows or formulas.
Cards in-hand deduplication uses the full-population DISTINCT statement.
An alternative physical construction must preserve displayed EV and ordinary
CI reductions, not only schemas and row multisets. The isolated EFF-03 range
prototype remains excluded from the installed source for this reason.

Full Sample, Home, Players and full-population MW facts are rebuilt. Snapshot
generation pins the current candidate. Only the four MW/Base Cards and Opening
Hand default artifacts can reuse a parent after all 22 logged relations were
qualified for reuse, both signatures match, the engine/producer/contract/schema
match and the complete parent artifact's size/hash/envelope validate. The
statistical population must be identical before a current-version envelope is
written. Reused payloads are materialized in a fresh candidate directory;
failure of any proof falls through to the ordinary calculation. Broad-context
pages are not admitted by this proof. All other page
snapshots, including Arena, are regenerated. No stale point estimates or
ordinary intervals are attached to changed populations. The full-build fallback
remains the numerical reference, not a reduced-data approximation.

Refresh identity includes:

- normalized source manifests;
- Arena, Tournament, and Records moving sources;
- `cards_attributes.csv` and `merge_players.csv`;
- builder and route code;
- route contracts; and
- serving/snapshot schema inputs.

Volatile fetch/status timestamps are excluded. A matching active identity is a
zero-build no-op. A matching inactive candidate may be reused only after every
artifact is revalidated by key, size, and SHA-256.

Snapshot construction pins the inactive candidate explicitly. The private API,
database pointer, and public snapshot pointer stay on the parent until all
release artifacts pass validation.

## Publication transport and accounting

`phase5_storage_io.py` uses one authenticated Storage SDK client/HTTP session
instead of a separate CLI process per artifact. Server-side rollback rewrites
pin the source generation; uploads verify CRC32C. Only an explicit NotFound
means absence: permission, timeout and transport errors fail closed.
Publication/recovery/rollback share a process-owned lock whose file is never
unlinked. Stable writes record an original object generation and transaction
owner in the durable journal. Compensation verifies ownership and uses a
destination generation precondition, so it cannot overwrite another release.
Persistent source-sync lock inodes likewise permit retry after process death
without weakening concurrent-attempt exclusion.

JSON/JavaScript artifacts and the default pack use deterministic streaming
gzip with the original Content-Type and Content-Encoding: gzip. Local release
hashes describe the uncompressed canonical files. Browser decoding preserves
every value and the public JSON schemas; compression is not data aggregation.
The pack is compressed once, not wrapped in another gzip layer. Refresh status
and locks remain uncompressed/no-store. Immutable prefixes, inverse journals,
recovery and pack-last publication coordinate activation. The default pack
is written after its snapshot members and before successful refresh status.

Private accounting distinguishes queued time from worker execution. The worker
writes moving-source, download, local-workflow and publication durations to
`worker/<run-id>.accounting.json`, including workflow and publisher sub-stages.
Failed runs also write accounting with the completed worker and workflow stages.
The worker appends each finished stage to
`worker/<run-id>.worker-timings.jsonl`, so completed-stage timings survive a
later failure. A failed candidate's snapshot resource journal is copied to a
bounded private `worker/<run-id>.snapshot-resource-profile.jsonl` before the
candidate snapshot tree is removed. The private workflow failure report retains
the stage timings and measurement paths alongside its error details.
Builder reports include per-statement operation/relation durations; snapshots
include total and standalone-component-CI build seconds. Reports never store
SQL, parameters, credentials or raw authenticated request bodies. RSS is the
process lifetime high-water mark, not a stage-local allocation or an engine
memory limit. The private snapshot profiler additionally samples current RSS
within each page phase. Those samples include buffers retained from earlier
phases; fresh-process repeats distinguish a page's own process peak from that
retention. Cgroup memory includes charged file cache and is not process RSS.
Spill bytes are sampled after statements, not peak spill usage.
Accounting-write failure cannot mark an already published release as failed.
Detailed failure reports remain under the VM's private worker directory. Never
upload them to the snapshot bucket: its anonymous-read policy also covers any
path named "diagnostics". The VM has only read access to the source bucket, so
failure logging must not assume it can upload there as a private fallback.

These optimizations do not change BigQuery's billed scan for a changed Full
Sample export. The worker remains serial for analytical snapshot queries and
keeps the configured background priorities and engine memory budgets. Production
uses e2-small with 2 GiB RAM and a 60-GiB disk; analytical requests pause during
refresh so serving work does not compete with the builder.

The VM startup metadata must use `phase5_vm_bootstrap.sh`, not a loose-file
legacy worker bootstrap. It checks publication dependencies in the `ascri`
worker account and installs the immutable bundle named by the private
`phase5/deployments/current.json` pointer. Updating desktop files or publishing
an archive alone does not update startup metadata. Advance the boot pointer
after a successfully validated deployment. Update startup metadata
only when the bootstrap script itself changes. A compatible code-only deployment
may preserve the active data generation and published snapshot timestamp. Do not
reboot to test persistence during a candidate build.

## Moving sources

The refresh-owned `moving_sources` directory contains:

- `arena_settings.csv`;
- required ended-season Arena rosters;
- Records CSV exports;
- Tournament metadata/cache; and
- `source-status.json`.

An ongoing Arena season may appear before its Elite League roster exists. A
roster is mandatory once the season has ended. Missing or invalid end timestamps
fail closed.

Each run marks inputs `fresh` or `last_known_good`. A failed download preserves
the validated previous input. Missing both a fresh and fallback input aborts the
candidate. Source states and fingerprints are recorded in the candidate
manifest.

## Scheduling and resource limits

Cloud Scheduler job `refresh-private-duckdb-daily` runs at 00:00 UTC and calls
the authenticated maintenance endpoint with the dedicated scheduler identity.
The maintenance token comes from Secret Manager. Never print raw request headers
or secret values while diagnosing the job.

The VM remains running after refresh. Source equality does not imply that Arena,
Tournament, Records, or Elo spreadsheet inputs are unchanged; each follows its
own refresh contract. The Elo peak updater is a separate schedule and does not
affect the dashboard refresh completion timestamp.

Resource boundaries:

- at least 8 GiB free disk or 120% of active database size before refresh;
- two builder threads;
- 600 MB source-import and 800 MB derivative-builder engine budgets, supplied by the production worker;
- a shared two-thread serving pool and 800-MB buffer budget per database instance;
- at most two public analytical executions;
- 90-second public query deadline; and
- a separate 800-MB allowance, one query thread and 600-second deadline for
  serial offline snapshot queries.

`REFRESH_PAUSE_ANALYTICS=true` pauses HTTP analytical requests for the entire
refresh, including source preparation, candidate validation and publication.
The worker's operational deadline is six hours; the maintenance request lock
allows seven hours before stale recovery, including its one-hour recovery margin.
The daily start remains 00:00 UTC. These are upper bounds, not a refresh delay.
Both services use `PHASE5_QUERY_PAUSE_LOCK`. An intent lock prevents new queries
while admitted requests drain; the worker then takes the exclusive work lock.
It waits for the API to restart in lightweight mode before allocating refresh
memory. Kernel-owned locks release on normal failure or process death. The
worker's systemd control-group stop kills descendants; startup publication
recovery uses the same barrier. Do not unlink the lock files to resume traffic.
The API resumes automatically after the barrier releases. Published snapshots,
Home bootstrap, Arena assets and local frontend controls remain available;
filtered/selected-player HTTP requests return a clear `refresh_in_progress`
retry message. No requests queue for the duration of a refresh.

The installed `ark-analytics.slice.conf` limits all API/worker descendants to
1456 MiB combined, with no swap. Current full-fallback, publication/recovery and
resumed-request memory evidence is in
`reports/refresh-pause-2g-qualification-20261003.md`. The current workload passes
the 2-GiB memory gate with OS/boot reserves; this does not resize the VM or
establish refresh duration on a lower-CPU machine.

Offline publication warming uses the worker's 800-MB serving-engine allowance;
the live API uses its independent 800-MB allowance outside refresh.
After a compatible code-only installation, the worker passes the installed
candidate code version and the active release's prior code version explicitly
to the publisher. The CLI validates both immutable inventories and the candidate
snapshot producer/contract hashes before any upload. Code/data rollback pairing
is preserved rather than bypassing the publication version guard.

DuckDB thread and buffer settings are shared engine limits, not per-request
reservations or total process-RSS caps. Production values come from
`ark-nova-duckdb-api.service` and `ark-nova-duckdb-refresh-worker.service`;
standalone CLI defaults may differ and must not be treated as deployment values.

`REFRESH_ISOLATE_STAGES=true` adds `--isolate-stages` to the worker workflow.
`REFRESH_SOURCE_MEMORY_LIMIT` supplies an independent import/reconciliation
engine budget through `--source-memory-limit`; when omitted it inherits the
builder budget. Full imports and incremental reconciliation use the same
setting in both isolated and non-isolated execution modes.
Import, derivatives and snapshots run as serial fresh processes through
`phase5_offline_stage.py`; each stage must return a successful private result
before the existing workflow validation and publication gates can advance.
Process exit releases allocator arenas between stages. Metadata and autocomplete
connections receive explicit offline budgets too. The Linux worker launches the
workflow in its own process session; a deadline kills the whole session so no
stage child continues writing after the workflow has failed. JSON serialization
is streamed; Arena season spools and one-member-at-a-time pack assembly avoid retaining all
decoded artifacts together. Public schemas, ordinary CIs and populations are
unchanged.
Installed Arena envelope assembly copies each writer-owned canonical private
season spool into all-season/latest JSON in bounded 1-MiB UTF-8 chunks. It
preserves key order, escaping, numeric formatting and every history point;
boundary checks are not a general-purpose external JSON validator. Release
and default-pack validation stay independent. Default-pack members are still
decoded and version-checked before atomic replacement; upload compression has
its own unchanged path. The deployed release is `deploy-114e8d834a97b90f8640`,
with current release/boot evidence in `reports/eff09-canonical-20261013/` and
Arena exact artifact/memory evidence in
`reports/eff11-arena-assembly-20261012/README.md`. Serialization-replay peaks
must not be reported as complete Arena-query or refresh peaks.
Fresh-process isolation also includes metadata and Arena/Records preparation,
not only source, builder and snapshots. The coordinator retains small reports
instead of native allocator state; stage reports separate child and coordinator
resource measurements. All stages remain serial and publication remains gated.
The offline snapshot response cache is disk-only: reads create fresh decoded
objects, avoiding redundant retained/deep-copied histories without changing
generation-scoped reuse. The public API uses its separate byte-bounded two-level
cache described in `phase3-duckdb-serving.md`; snapshot cache savings and API
cache savings must not be counted twice.
Records/Most Icons snapshots execute the complete ordered query once per
dataset. The private writer consumes 1,024-row cursor batches into a temporary
JSON spool and assembles the canonical envelope without retaining every row.
All observations, nulls, tie ordering and public field values are preserved.
Only this trusted offline path omits SQL pagination; public Records requests
retain their existing limits and offsets. Other Records snapshot views retain
their normal writer. The cursor owns its generation, read-only connection and
query deadline until consumption ends, including early-exit cleanup.
`phase5_component_ci.py` additionally computes ordinary standalone component
statistics once per normalized filter scope, telemetry eligibility and component
kind (`card`, `action_card`, `endgame`) across snapshot views. Its private SQLite
cache stores only final means, interval endpoints, standard errors and counts;
each build attempt clears it, so interrupted/retried candidates cannot inherit
unqualified intervals. Game observations and cluster moments stay in DuckDB.
Telemetry-restricted card populations remain distinct. Map/Round context
intervals already present in point responses are retained without calculating
discarded second-component intervals. Interactive ordinary-CI requests retain
their public endpoint and formulas; additive Synergy intervals remain absent.
The release manifest records unique component-population query counts and time.
Arena history construction batches selected player IDs (`DUCKDB_ARENA_SERIES_BATCH`,
512 by default, range 1-50000), while calculating roster statistics only once.
The trusted history-only SQL shares the existing population joins and order;
every player, empty history and rating point remains in the original schema.
Season spooling, bounded history queries, the disk-only offline cache and
streamed pack assembly are installed production behavior. Arena remains part
of automatic refresh; there is no manual-only season policy or history sampling.
Fresh-stage isolation and source-builder batching are installed behavior.
The complete source, derivative and snapshot qualification is recorded in
`reports/derivative-builder-memory-qualification-20261002.md`. These process
measurements do not qualify whole-machine headroom on a 2-GiB VM.
Canonical UPDATE transactions and seen-card DISTINCT construction are bounded
by disjoint table-ID batches, checkpointed individually. Quantiles are only
transaction boundaries; the statistics remain exact. The seen relation reuses
normalized drawn cards and unions display cards without concatenating the full
population's nested arrays. Batch counts default to 32 and can be configured
between 1 and 256 through `DUCKDB_CANONICAL_UPDATE_BATCHES` and
`DUCKDB_SEEN_CARD_BATCHES`.
The production refresh worker explicitly sets the canonical UPDATE count to
16; the standalone CLI and seen-card count retain their defaults of 32. This
changes transaction boundaries only, retaining a checkpoint after every UPDATE.
Full-size qualification matched every prepared value, schema and multiplicity
and measured this construction stage at 454.81 versus 542.36 seconds, with
about 30.6 MiB less service anonymous memory. The compact canonical join and
other derivatives are unchanged. This is not a whole-refresh peak measurement;
see `reports/eff09-canonical-20261013/README.md` for scope and resource counters.
Played-round LIST/DISTINCT summaries use `DUCKDB_CARD_PLAY_SUMMARY_BATCHES`
(default 32, range 1–256), preserving sorted round lists, nulls and every
repeated-event/per-round count in disjoint table-ID buckets.
The combined Cards core uses `DUCKDB_CARD_FILTER_CORE_BATCHES` (32, range
1-256), applying the same table-ID bucket to seen, hand, played and game inputs.
This bounds joins and correlated existence checks without altering union,
overlap, orphan-row or null behavior.
Symmetric Cards table/card moments use `DUCKDB_CARD_TABLE_BATCHES` (32,
range 1-256). Game eligibility and card moments share disjoint table-ID buckets,
so both players and all card observations of each table stay together. The
ordinary clustered CI sufficient statistics are unchanged; only temporary
aggregate/join state and spill volume are bounded.
MW Draft uses `DUCKDB_MW_DRAFT_BATCHES` (32, range 1-256) to bound its
table-level ranking, paired aggregation and selected-card joins. Only consumed
columns cross the ranking boundary. Eligibility and first-player orientation
remain exact and each table is processed wholly in one bucket.
INSERT-only loops checkpoint every bucket, retaining the qualified production
boundary. There is no reduced-cadence production control. Changing that policy
requires identical complete row multisets, a demonstrated overall benefit and
full-size memory qualification; checkpoint count alone is not a speed measure.
Canonical UPDATE checkpoints and the other batching policies are independent
and unchanged. Experimental evaluation belongs in isolated test code, not the
release candidate.
Home log features reduce each row's arrays with scalar list operations rather
than correlated population-wide UNNEST joins. Duplicate Emu events, null
arrays/elements, exact card names and the inclusion of corrupted/incomplete
Home observations are preserved. This bounds temporary join/spill work without
sampling logs or changing Home's population.
Opponent Proboscis detection joins a small table-level distinct-player summary;
duplicate own-player rows and null names cannot become an opponent match.
The summary preserves malformed multi-player-table behavior without a
population-wide correlated existence join.
Component-CI batches calculate each shared standalone population once per
component role and expand only the resulting statistics back onto pair rows;
they do not duplicate table observations for every repeated paired component.

Players default snapshots serialize the builder's already prepared
All/Winners/Experts/Masters cohorts, not statistics for individual players.
The empty identity branch does not scan player facts; selected-player results
do not appear in the default snapshot. A single cohort join projects all metric
rows without binding the individual-player fact or identity tables. Player results
and histories remain on-demand VM queries. Restrictive filters calculate their
own cohorts, while missing cohorts retain null values and zero counts.

The inactive memory benchmark uses existing local exports and never queries
BigQuery, activates a generation or changes hardware. Its full-build numerical
gate and separate snapshot/live-query qualification are prerequisites for any
smaller VM. Reports must distinguish engine limits, process RSS, cgroup memory
(including charged file cache), and total machine headroom. Lowering the engine
limit alone does not qualify a downgrade.
The Arena/snapshot qualification report is
`reports/arena-snapshot-memory-qualification-20261002.md`. Snapshot-only success
does not qualify the import/derivative builder or a smaller production API budget;
production uses 2 GiB with the complete refresh-pause qualification and resource
boundaries above. That complete rehearsal ran under the shared ceiling on
e2-medium; actual e2-small refresh duration must be measured independently.

Retention always protects active, rollback, journal-referenced generations and
the configured newest completed releases.

## Legacy resource retirement

Production has no legacy BigQuery analytical refresh, additive Synergy-CI or
Card+Card warming schedules. The dashboard-owned BigQuery analytical derivative
tables are absent; the empty `dashboard_cache` dataset remains. Do not recreate
those tables or re-enable legacy SQL refresh helpers. Keep
`refresh-private-duckdb-daily` and the independent `update-elo-peaks-daily`
enabled. The controlled importer reads upstream source tables/views/routines,
and the VM builds analytical derivatives in DuckDB.

Before permanently removing legacy schedules, derivative tables or exported
objects, inventory their identities, sizes and references. Preserve schedule
configuration and required recovery evidence, and confirm that the importer,
maintenance endpoint, Elo updater, active release, rollback release and pending
publication journals do not reference them. Never delete upstream source tables,
views or source routines as dashboard cleanup. Local generation/export retention
continues through the guarded retention tools rather than ad hoc file deletion.
Permanent resource removal requires the owner's approval of the exact resource
list. Cloud Storage release/rollback archives, active services, upstream sources
and source exports are not covered by analytical-derivative retirement.

`phase5_remote_retention.py` is not yet safe for unattended remote deletion.
Its plan considers recent prefixes and the default pack, but not all VM paired
rollback descriptors or publication journals; an unreadable default pack also
does not fail that plan closed. Do not use its `--execute` option until these
references are protected and the exact deletion inventory is approved. This
restriction is separate from the guarded local generation/source retention.

## Confidence intervals

Snapshot enrichment computes each distinct displayed standalone component EV
interval once per scope and reuses it across rows. Card + Map and Card + Round
reuse the ordinary interval carried by their contextual EV component where the
population is identical. Additive Synergy intervals are not generated.

## Private refresh measurements

`phase5_refresh_metrics.ResourceSampler` samples process RSS and Linux cgroup-v2
service/slice counters every 0.5 seconds while resource windows are open. The
worker, coordinator and offline stage processes also append a coarse sample
about every 30 seconds to
`phase2_private_data/worker/<run-id>.memory-timeline.jsonl`. Fixed stage labels
and process IDs identify the source-import, metadata, derivative, preparation,
snapshot and publication processes. Controlled BigQuery export work happens
outside this VM timeline; its byte/job accounting remains in the import reports.

Derivative `statement_timings` carry sampled execution-window maxima, spill
bytes and memory-event deltas. Their elapsed time includes subsequent fetches,
but fetch-only memory peaks are not attributed to that SQL execution window.
The lifetime `ru_maxrss` field remains separate. Snapshot directories contain
private `resource-profile.jsonl` and, after a full successful build,
`resource-profile.json`: per-snapshot query/ordinary-component-CI/write timing,
rows and bytes, per-season Arena windows, indexes, Home bootstrap, default-pack
assembly, and distinct ordinary-CI population costs/cache lookups.
Statement telemetry records complete qualified relation names such as
`main.card_log_narrow`, without storing the SQL text.

Sampling reports observed maxima, not guaranteed detection of sub-0.5-second
spikes. Cgroup memory includes charged file cache and other processes in that
group; nested windows have inclusive timings. Do not add their peaks or times
as though they were disjoint work. Spill polling is shared between nested
windows and runs roughly every two seconds, plus finalization.

These files are not release-manifest artifacts, are never uploaded to the
public snapshot bucket, and contain no SQL, parameters, player names or secrets.
Diagnostic setup, reads, writes and finalization are best effort: failures must
neither skip analytical work nor mask its exception. Partial JSONL files remain
useful after interruption. Tests live in `tests/test_resource_measurement.py`.
Measurement code participates in conservative producer fingerprints, so its
deployment can require a complete first rebuild. It does not change statistical
contracts, resource limits, query-pause policy, schedules or query volume.

## Verification

Focused source-sync tests:

```powershell
python -m unittest discover -s tests -p test_phase5_source_sync.py
```

Before activating a refreshed candidate, verify:

- source manifests and hashes;
- source-family equality/change decisions;
- moving-source status and fallbacks;
- complete derivative and snapshot inventories;
- snapshot/default-pack data-version consistency;
- active and rollback readiness;
- representative independent numerical reconciliation; and
- snapshot/service health during refresh, explicit rejection of analytical
  requests, and automatic request resumption after success or failure.

Never use a successful export, structural audit, or snapshot shape check alone as
proof that analytical populations are correct.
