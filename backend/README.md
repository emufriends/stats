# Ark Nova Dashboard Backend

This directory contains the production DuckDB query service, controlled source
refresh, snapshot publisher, maintenance Cloud Function, gateway, budget safety
handler, and Elo peak updater.

For a public repository checkout, read `PUBLICATION_STATE.md` first. The mirrored
review source includes locally implemented work that is not deployed or fully
qualified. Private operator evidence/databases are intentionally not included;
publishing the repository does not deploy code, refresh data or resume schedules.

Start with these current-state documents:

- `AUDITOR_GUIDE.md` - zero-history domain/architecture onboarding, implementation
  atlas, evidence limits and independent audit procedure.
- `..\ark-nova-stats-dashboard\ark_nova_dashboard_handoff.md` — product,
  population, page, and frontend contract.
- `phase3-duckdb-serving.md` — production serving and immutable-generation
  operations.
- `phase5-source-sync.md` — BigQuery source import and local reconciliation.
- `contracts\dashboard-routes.v1.json` — authoritative machine-readable route
  and population contract.
- `elo_peak_updater\README.md` - separate Elo/Arena peak updater.

Agent coordination lives in `agent-coordination/README.md`: the principal owns
architecture, backend, new pages, integration and deployment; the counterpart
focuses on review/frontend and small scoped fixes. Read unresolved notes before
overlapping work. These notes supplement, never replace, current documentation
and annotations and do not grant deployment authority.

Phase-prefixed filenames are stable module identifiers retained to avoid risky
import and deployment churn. They do not describe unfinished project phases.

## Runtime boundaries

- Public default views load from Cloud Storage snapshots/default pack.
- Public filtered requests use the anonymous HTTPS Cloud Run DuckDB gateway.
- The gateway forwards allow-listed requests to the private VM API.
- The VM hop is internal HTTP protected by network/firewall configuration, not
  per-request gateway authentication. CORS is not an access-control substitute.
- The VM serves one immutable DuckDB generation read-only.
- Its in-process response cache retains immutable serialized payloads within
  32-MiB total and 8-MiB per-entry limits; larger responses use SQLite fallback.
  These limits do not bound total API memory. See the serving runbook for
  environment overrides, mutation isolation and eviction semantics.
- Executable code is resolved from `/home/ascri/current-app`; persistent source,
  generations, snapshots, and worker state live under
  `/home/ascri/phase2_private_data`. `ARK_ROOT` names the persistent data root
  and must never be used to locate deployed Python modules.
- Dashboard analytics use BigQuery only in the controlled source-import workflow;
  the independently deployed Elo peak updater has its separate BigQuery job.
- `main.py` remains the maintenance/snapshot compatibility boundary; it is not
  the public filtered-query engine.
- The Elo updater is independently scheduled and deployed.

## Important entry points

| File or directory | Responsibility |
|---|---|
| `phase3_api.py` | Private HTTP API and concurrency boundary |
| `phase3_duckdb_service.py` | Generation manager, request adapter, caches, readiness |
| `phase4_local_scope.py` | Canonical shared filter normalization and predicates |
| `phase4_local_routes.py` | Page-specific DuckDB query builders and projectors |
| `phase4_combo_mw_contracts.py` | Combos and MW Action Cards SQL contracts |
| `phase3_cards_pair_contracts.py` | Exact two-sided Cards moments and compact Combo pair facts |
| `phase2_local_vertical_slice.py` | Complete local generation builder |
| `phase5_source_sync.py` | Controlled BigQuery metadata check/export |
| `phase5_source_reconcile.py` | Table-grain local source reconciliation |
| `phase5_refresh_workflow.py` | End-to-end candidate build and validation |
| `phase5_offline_stage.py` | Serial fresh-process import/metadata/builder/preparation/snapshot boundary |
| `phase5_refresh_worker.py` | Scheduled/manual worker orchestration |
| `phase5_query_pause.py` | Process-owned analytical admission/drain barrier |
| `phase5_snapshot_builder.py` | Snapshot/default-pack generation |
| `phase5_publish_release.py` | Transactional immutable publication |
| `phase5_storage_io.py` | Persistent authenticated Storage transport and streaming gzip |
| `phase5_refresh_dependencies.py` | Exact dependency checks for immutable log-fact reuse |
| `phase5_refresh_metrics.py` | Private stage/query timing and bounded resource counters |
| `phase5_coordinated_publication.py` | Gated code/schema cutover with paired code/data rollback |
| `ark-analytics.slice.conf` | Shared API/worker memory ceiling, installed by the verified deployment installer |
| `phase5_order_cards_facts.py` | Inactive-candidate storage ordering with exact multiset checks; requires release revalidation |
| `cloudrun-duckdb-gateway/` | Public HTTPS query gateway with internal-network VM forwarding |
| `budget_shutdown_service/` | Hard-budget VM stop handler |
| `elo_peak_updater/` | Separate daily peak updater |

Internal view identifiers containing `phase3_` or `phase4_` are compatibility
keys. Do not rename them casually: cache keys, tests, saved manifests, and route
dispatch may depend on them.

The compact `game_player_narrow` canonical fact and the wide canonical
`prepared_full_sample_narrow` player-game relation are materialized during a
build. The wide relation deliberately duplicates the imported source fields:
ordinary filtered routes need both source metrics and canonical opponent,
completion, corruption, Arena, tournament, and identity fields, and a runtime
join is too slow for the five-second cache-miss budget. Expensive route work and
Logs arrays are additionally materialized at their compact event grain,
including conservation-bonus milestones and opportunities.

Refresh efficiency preserves the statistical contract. The editable builder's reuse
set contains 22 immutable log-scoped relations; this is not a claim that held
local builder changes are installed. Use the deployment boundary in
`AUDITOR_GUIDE.md` and `agent-coordination/CARDS_CHAIN_STATUS.md` when assessing
production. Reuse occurs only when its producer/input hash, DuckDB version,
Logs inventory/schema and complete canonical rows for logged tables match.
Fresh two-sided scopes must retain every logged table's numeric key. Any
correction, deletion, eligibility change or key shift falls back to rebuilding.
Full Sample, Home, Players and full-population MW facts are rebuilt from current
data. Source import remains a controlled complete changed-family export, not an
ID/date cursor. The producer inventory follows the local import closure of the
actual logged-fact producers; snapshot/publication edits do not by themselves
invalidate these facts. Private builder reports include the exact reuse/fallback
reason. A missing or older signature requires a complete baseline build.

The editable ordinary card-CI handler uses filter-scoped canonical player/card-play facts,
with repeated matching plays deduplicated at player-game grain and table-level
clustering. They do not depend on validation-only component/pair relations.
Candidate Cards-chain qualification and measured decisions are recorded in
`reports/cards-chain-optimization-20261006/README.md`; isolated candidate files
are not production deployment evidence.
CC-5/CC-6 rollout is held by the combined native public-output gate: all counts
match, but CI last bits and eight Card + Card display rounding boundaries differ.
The full-builder memory gate passes. A matched fresh baseline control is still
required; consult `agent-coordination/CARDS_CHAIN_STATUS.md` before deployment.

The root and installed Cards paired-scope producer uses 65,536-key batches for
fresh builds and reusable-fact refreshes. It validates the whole eligible
population before batching and preserves globally ordered table keys, player-side
ordering, nulls and filter fields. The persisted event copy remains required.
`batch_size=None` retains an independent unbounded qualification control.
CC-7 release evidence is in `reports/cc7-rollout-20261006/README.md`: both full
scopes match exactly; 12 of 13 native public artifacts are byte-identical. Six
ordinary-CI fields differ only within documented floating-point propagation
bounds (identical through nine decimal places); the raw byte failure is retained.
This acceptance does not clear CC-4 or held CC-5/CC-6 displayed-EV differences.
CC-3's isolated numeric TEMP-fact join encoding is not used: it increased paired
construction time, anonymous memory and spill. Evidence and its bounded scope
are in `reports/cc3-prototype-20261007/README.md`; current builders retain the
original repeated paired-fact joins, with CC-7's bounded scope producer.

The editable canonical Cards log producer includes every normalized hand key in its
seen set. The helper supports an opt-in hand-subset fast path for bounded core
construction, but the main caller retains the full union while its native
public-output gate is held. Generic helpers keep their hand-only/null-key union
by default. Complete MW/Base
facts, table moments, paired capabilities and compatibility fallbacks remain
materialized. List normalization retains global cross-log set semantics.

Canonical player-game construction releases `opponent_ratings_narrow`,
`player_ratings_narrow` and `table_conceded_narrow` immediately after their last
consumer, `game_player_narrow`. Downstream facts read the canonical relation.
Cards in-hand DISTINCT retains its full-population statement; changing its
physical row order requires qualification of floating-point means and ordinary
CIs as well as observation parity. Installed source and the full-size memory
evidence are identified in `AUDITOR_GUIDE.md` and
`reports/eff03-eff04-20261011/README.md`.

Serial snapshots calculate ordinary standalone component intervals once per
normalized scope, telemetry eligibility and component kind. The private SQLite
cache contains only small final statistics, never game observations, and is
cleared for every build attempt. Actual/context intervals are unchanged;
additive Synergy intervals remain absent. Cards and Opening Hand can reuse a
parent snapshot only after exact logged-population, engine, producer, contract
and artifact-hash proof. The four MW/Base reused payloads are written into
fresh candidate directories; failed proof uses the normal calculation. Failed
refreshes retain private stage accounting and bounded snapshot measurements.
Other page snapshots, including Arena's statistics and
histories, are regenerated against the current candidate. See
`phase5-source-sync.md` for the publication/reuse contracts and private reports
for measured deployment acceptance; local implementation is not automatically
installed on the VM.

The editable builder does not materialize unused sponsor-endgame, project-reward
or action-history event copies. Page-specific serving facts remain required.
Independent component/pair references are built only on demand by
`python phase5_cardcard_reconcile.py <inactive-generation.duckdb>` in disposable
disk-backed scratch space. The input is attached read-only. The command reports
pass/fail for both datasets and all pairs in the fixed Standard-map, 2025-01-01,
300/300-Elo scope with optional completion off. Counts, keys and nulls are exact;
unrounded independent reductions have a tight roundoff bound. Exact before/after
public bytes remain a separate mandatory optimization gate. Do not run this
full-size audit alongside live queries on the 2-GiB VM without qualification.
Installed Arena bundle assembly copies bounded 1-MiB UTF-8 chunks from
writer-owned canonical season spools. Object key order, numeric formatting,
escaping and complete history arrays are preserved. Boundary checks reject
incomplete spools but are not a validator for externally supplied JSON.
Default-pack validation and compression retain their independent paths.
The deployed source is the reviewed `candidate-code/` tree under
`reports/eff09-canonical-20261013/`, deployment
`deploy-114e8d834a97b90f8640`. The refresh worker uses 16 canonical UPDATE
batches, each retaining its checkpoint; the builder's standalone default is 32.
Exact full-size prepared-value and isolated resource evidence is in that
report's README. Arena assembly evidence remains in
`reports/eff11-arena-assembly-20261012/README.md`. Neither isolated test establishes
a new whole-refresh memory peak. Other editable-root optimizations remain subject to
their own installed-release boundary, as recorded in
`reports/cards-builder-followup-20261006/README.md` and
`reports/quick-win-qualification-20261006/README.md`. Use the verified immutable
release source for deployment; do not package the editable backend root.

Installed production bundles do not update automatically when desktop files
change. Refresh-efficiency rollout and measured production acceptance are
tracked separately in the private implementation reports, including
`reports/refresh-duration-implementation-20261004.md` and
`reports/refresh-builder-next-20261004.md`;
local tests are not production performance evidence.

Low-memory refresh tooling is described under "Builder and resource limits" in
`phase3-duckdb-serving.md`. Fresh serial stage processes and streamed snapshot
serialization preserve the data contract. Use the inactive, local-source-only
`phase5_builder_memory_benchmark.py` to qualify budgets before changing hardware;
passing unit tests or source import alone is not a 2-GiB serving qualification.

Log eligibility is not shared across page families. Endgames, Sponsor
Endgames, and Project Rewards use page-specific flattened filter-event facts
from matching player logs; they must not inherit Cards' two-log-row restriction.
Project Rewards' frequency denominator is the matching Log Sample population.
Home's compact feature fact retains corrupted games and existing log-row
multiplicity. Numerical reconciliation must pin the same source generation
and bypass both snapshot and response caches.

Outside refresh, the private API permits two simultaneous analytical executions.
Identical requests share one execution; distinct bursts wait for a bounded
10-second query slot before returning `serving_busy`. Do not use an unbounded
queue or raise concurrency without measuring peak memory.

During refresh, `phase5_query_pause.py` blocks new analytical requests, lets
admitted requests finish, and holds a process-owned Linux lock through building,
validation and publication. The API restarts into a lightweight mode to release
native memory; snapshot/default-pack pages remain available. HTTP query requests
receive `503 refresh_in_progress` with a user-facing retry message. Successful,
failed and killed refreshes release the barrier; the API then restarts normally
and resumes requests. Health, readiness, status and capabilities stay available.
The files are never deleted to unlock them. Systemd kills refresh descendants
as a control group so a service stop cannot leave an orphaned builder behind.

Arena publication has two related but distinct contracts. Arena table/graph
bundles contain only seasons with a roster CSV. The Players Arena-season
manifest is generated from `arena_seasons_metadata`, so an ongoing configured
season appears as a Players filter before its roster exists.

## Local Python and DuckDB

The desktop keeps a Python 3.14-compatible DuckDB extension bundle under:

```text
phase2_private_data\python314
```

When the system interpreter cannot import DuckDB, set:

```powershell
$env:DUCKDB_PYTHON_PATH = "C:\Users\ascri\Desktop\ark-nova-function\phase2_private_data\python314"
```

Then run checks from this directory. The loader adds that directory explicitly;
do not copy native extensions into unrelated Python installations.

## Safe change workflow

1. Locate the route in `contracts/dashboard-routes.v1.json`.
2. Confirm observation unit, population, completion, dataset, and request scope.
3. Change the route builder/projector and focused tests together.
4. Keep snapshot and filtered response contracts identical.
5. Bump the relevant route/cache/snapshot schema for semantic changes.
6. Build and validate an immutable candidate; never mutate the active database.
7. Reconcile representative values and counts independently.
8. Publish database and snapshot pointers transactionally.
9. Update current-state docs and annotations in the same change.

Useful checks:

```powershell
python -m py_compile main.py phase3_api.py phase3_duckdb_service.py phase4_local_routes.py
python -m unittest tests.test_migration_contract_foundation
python phase5_contract_regression_gate.py --pack PATH_TO_CANDIDATE_PACK
python phase5_snapshot_validate.py --help
```

The regression gate intentionally has no default pack. Always pass the
candidate or freshly downloaded published pack; workstation files named
`current-default-pack.json` are not authoritative release inputs.

Compatibility-named scripts and tests remain active release gates; their names
alone do not make them obsolete.

## Workspace retention

Keep runtime modules, contracts, tests, operational/deployment tools, current
documentation, and numerical/memory qualification evidence. Some test helpers
live in `reports/`; that directory is not uniformly disposable. Private source
exports, the local active/previous generations, the original comparison
generation and hash-pinned reference snapshots support offline verification.
The desktop generation pointer is local comparison state, not production state.

Intermediate generation database copies and completed duplicate staging
databases are disposable once no active, rollback, test or release input uses
them. Preserve their small manifests as provenance; a historical parent ID does
not require retaining every intermediate database forever. Never prune the VM
or Cloud Storage as part of desktop-folder cleanup.

Python bytecode, abandoned temporary test children, spill files and downloaded
diagnostic payloads are regenerable. Keep `.test-temp/` available as an empty
scratch root when `TEMP`/`TMP` point to it. Git and maintenance deployment ignore
rules exclude private data and scratch output; deployment archives still use
their explicit source inventory.

The refresh headroom gate normally reserves 120% of the active database file.
`PHASE5_CANDIDATE_ALLOWANCE_GIB` may replace that estimate only after a measured
builder run establishes a smaller safe candidate peak; the independent
`PHASE5_MIN_FREE_GIB` floor still applies. This override changes admission only,
not retention, publication, or active/rollback protection.
`PHASE5_INCREMENTAL_SOURCE=false` makes a recovery build rematerialize from the
already-local immutable export instead of copying the active database; it does
not initiate a BigQuery export.

The installed refresh worker runs source import, metadata, analytical building,
Arena/Records preparation and snapshots as fresh serial processes. Source import
uses a 600-MB engine budget; derivatives use 800 MB and two threads; snapshots
use 800 MB and one thread. Bounded complete-table batches preserve populations,
ordinary CIs and output schemas. Serving uses a separate 800-MB/two-thread
budget. Engine limits are not process-RSS caps. Complete qualification evidence
is in `reports/derivative-builder-memory-qualification-20261002.md` and
`reports/refresh-pause-2g-qualification-20261003.md`. The measured workload passes
the combined 2-GiB refresh-pause memory gate. Production uses an always-on
e2-small VM with 2 GiB RAM and a 60-GiB disk. The API and refresh services share `ark-analytics.slice` with
a persistent 1456-MiB ceiling and no swap. Qualification reserves 400 MiB for
OS/background working memory and 192 MiB for boot-reserved RAM. This is not a
latency guarantee; actual lower-CPU refresh duration and future growth still need attention.
Actual hardware restart and representative request evidence is in
`reports/e2-small-restart-20261003.md`; that check does not run another full refresh.

Private refresh profiling records sampled per-statement/per-snapshot resource
windows, ordinary-CI population reuse and a ~30-second worker/stage timeline.
Diagnostic failures cannot fail analytical work; diagnostics never enter public
snapshot manifests. Read "Private refresh measurements" in
`phase5-source-sync.md` for locations, sampling limitations and interpretation.

## Non-negotiable invariants

Deployment packages are assembled from an explicit installed baseline plus a
named repair overlay using `phase5_release_source.py`. `phase5_package_deployment.py`
requires `release-source-manifest.json` and rejects changed or unlisted inputs.
The immutable archive contains code inventory only; the external descriptor
records the active data generation and rollback pairing. Repackaging identical
code after a data refresh therefore preserves the archive identity.
The assembled source is kept in an isolated Git repository; it is not the
editable workspace containing held experiments. Consult the release evidence
and installed pointers before claiming a repair is deployed.

Publication, recovery and rollback share `phase5_process_lock.py`. Lock files
are persistent; kernel ownership releases when a process exits. Never delete
their files or reclaim a live owner based on elapsed time. Recovery verifies
transaction ownership and destination-generation preconditions before restoring
remote aliases. The source-sync helper uses the same lock primitive so a killed
attempt can attach to deterministic export jobs on retry.

HTTP admission bounds body readers and waiting requests independently of the
two analytical execution slots. Defaults are 16 admitted VM connections, 24
gateway connections and a 15-second socket read timeout. The gateway forwards
application errors once and preserves numeric Retry-After values. Always-on
deployment disables VM auto-start; source defaults also disable it. Identical
coalesced requests share their final successful or failing response.

- Public analytical traffic never queries BigQuery.
- Active generations are immutable and read-only.
- Unknown result-affecting request fields fail closed.
- Corrupted tables are excluded everywhere except Home.
- `pre_match_elo` is the canonical analytical Elo.
- Standalone EV confidence intervals remain supported; Synergy intervals do not.
- A candidate cannot advance one public pointer without the matching database,
  snapshots, default pack, manifests, and rollback descriptor.
- External-source failures preserve the validated last-known-good input.
- Logs and status responses never contain SQL, credentials, raw request payloads,
  passwords, or stack traces.
