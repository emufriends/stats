# Phase 4 private port contract

> Historical implementation record. The 2026-09-22 migration review supersedes
> this file's former parity/completion conclusions. A route being registered,
> executable, or shape-compatible is not proof of population or numerical
> equivalence. Use `duckdb-migration-review-2026-09-22.md` and the current
> contract gates for release decisions.

The dashboard’s public Cloud Function and Cloud Storage snapshots remain the
production path. Phase 4 is an incremental private DuckDB port; no public route
is switched until its output has been reconciled against the existing contract.

## Current progress

All Phase 4 route batches are implemented in the private adapter:

- `maps/metrics` uses the shared local scope and reproduces the current 65-row
  Maps metric catalogue, including `Reputation actions` and map-specific
  tooltip fields.
- `endgames/general` projects the local Logs `endgame` and `endgame_scores`
  arrays into the current Endgames table shape, including dealt/scored counts,
  keep rate, average CP, and EV values.
- `scoring/*` implements Final Score, Appeal, Conservation Points, and
  Reputation using fixed buckets, map projections, and ordinary EV fields.
- `actions/upgrades`, `actions/upgrade_order`, and
  `actions/upgrades_by_map` use the Full Sample/Logs upgrade fields and expose
  their existing EV and frequency projections.
- `build/enclosures` and `build/hexes` provide the fixed bucket tables with
  map projections; `icons/default` provides the grouped icon distributions.
- `conservation/projects` and `conservation/project_rewards` preserve their
  count/reward projections, while `workers/general` and `workers/two_cp_worker`
  provide the worker bucket tables.
- `endgames/cp_distribution` and `endgames/cp_by_map` expose endgame CP
  distributions; `maps/tournament_h2h` uses imported tournament metadata.
- `sponsor_endgames/cp` and `sponsor_endgames/appeal` expose sponsor-endgame
  event projections; `predictors/general`, `predictors/icon`, and
  `predictors/specific` expose predictor comparison contracts.
- `actions/starting_position` and `conservation/cp_rewards` expose their
  starting-strength and conservation-reward projections.
- Home and Opening Hand are available from local source relations. The four
  additional Combos views use narrow card-play/log projections, and the four
  remaining Players views expose general, comparison, map-performance, and
  Arena-top-player aggregates.

All routes exclude corrupted tables and use table-level completion eligibility.
Dataset, map, Elo, date, and Starting position filters are parameterized and
cached by the existing generation-aware response cache. Arena-season and
tournament filters are evaluated from the metadata relations in the active
private generation; they are never silently ignored.

Each activated route uses page-specific source fields, bucket rules, map
denominators, player/record projections, and ordinary EV interval fields; no
route falls back to a generic Full Sample average. The final batch covers
Arena, all Records views, and all MW Action Cards views.

## Completion criteria for each family

Before activation, a family must have a page-shaped local query, the shared
scope, corruption and completion rules, its existing response fields, and a
focused reconciliation against the current producer. Default snapshot use and
filtered requests must be tested separately. Point values and standalone EV
intervals remain in scope; additive combination/Synergy intervals remain
retired.

The private API advertises route status through `/v1/capabilities`: all 50
routes have executable DuckDB query builders. “Native” describes executable
local routing; the separate route, contract, numerical, and performance reports
are the cutover evidence. Those private gates now pass, but the public
frontend is not connected to this API.

## Read-only readiness audit

`phase4_local_audit.py` checks the active immutable generation without changing
it. The current generation contains every required source and narrow relation,
including the imported Arena-season and tournament metadata. The audit now
reports route completeness; public cutover remains separate and requires the
numerical reconciliation and rollout gates below.

`phase4_route_contract_audit.py` records the current read-only audit in
`analysis/phase4-route-contract-audit.json`. It validates and executes all 50
registered routes with a bounded restrictive scope, confirms JSON-serializable
response payloads, and records the two formerly expensive nested routes for
the performance increment. The benchmark is recorded
in `analysis/phase4-performance-benchmark.json`: Build/Hexes now aggregates by
bucket once and completes in under one second warm, while the compact grouped
Card + Endgame and Card + Action Card projections pass fresh-process default
benchmarks. The active generation contains 8,988
corrupted tables; Home retains their 17,976 source rows, while the shared
non-Home scope excludes them. The active `card_play_narrow` relation is now
physically pruned of all such rows; Home retains the source rows by design.

`phase4_combo_equivalence.py` records the compact Card + Endgame equivalence
check. Its older Card + Action Card result is superseded: the contract oracle
found that the former local query collapsed 20 individual action cards into
five action types and weighted the standalone action-card baseline by paired
card observations. The current query uses the 20-card catalog, matches the
stored numeric suffix per type, and calculates the action-card baseline once
per selected action card/player-game. A fresh independent numerical reference
is complete and passes as part of the 50-route numerical gate.

`phase4-frontend-contract-audit.json` validates the common response envelope
and a representative subset of row fields for 20 routes. It is a smoke test,
not proof of public-contract compatibility. The authoritative shape oracle is
`phase4-legacy-contract-audit.json`, generated by
`phase4_legacy_contract_audit.py` from the immutable September 14 legacy
default pack. The audit plans each private query with `LIMIT 0`, so it compares
column contracts without scanning route populations or querying BigQuery.
Additive Synergy CI fields are excluded because that feature is intentionally
retired; standalone EV CI fields remain required.

The contract oracle maps 43 snapshot-backed routes and all 43 expose the
required legacy public fields. Additive Synergy CI fields are intentionally
retired; ordinary EV CI endpoints are projected centrally from each route's
mean, sample deviation, and count. Cards, Opening Hand, MW By-map, MW
Synergies, Conservation CP Rewards, Players/General, all Records views, and
the nested Arena season bundle now have page-shaped contracts. Arena is backed
by `arena_roster_narrow` (6,236 imported roster rows) and joins game facts by
player ID. Automatic Records populations are local, and the current Fastest
Games, Biggest Turns, and Elo Leaderboard spreadsheet exports are imported into
generation-local narrow relations with source hashes. Fastest Games retains
its sheet-owned extrapolated values while matching metadata is joined from
local Full Sample where available. The route audit passes and the active
generation has no pending route registrations. Numerical reconciliation and
performance gates still remain separate from shape compatibility.

`phase4-decision-gate.json` is the current private readiness record. Card +
Card remains reconciled against its same-generation reference. The independent
route reconciliation now covers the other 49 contracts, and all 49 pass their
direct source or generation-local moving-source checks. The Cards route now
applies the shared filter scope to its played, in-hand, and seen populations;
the earlier Cards discrepancy was a real route-scoping defect and is fixed. The
comparison is intentionally not counted against the stale producer snapshot:
the available local Cards snapshot has the same nominal source version but an
older population (267 rows versus the active source population), so it is not
a valid oracle. The legacy pack supplies independent public shape contracts but
is not used for numerical claims because its data version predates the active
DuckDB generation. Independent same-generation numerical references are
generated locally from frozen raw source relations rather than by reusing
private route SQL or running a full BigQuery refresh. The detailed report is
`analysis/phase4-independent-reconciliation.json`; it records the common
bounded scope (MW, completed, Map 1a, both starting positions), observed and
reference counts, and an unrounded numeric probe where the route has a stable
probe field. The full 50-route private numerical gate therefore passes.

`phase4_metadata.py` provides the import boundary for Arena and Tournament
metadata, while `phase4_records_source.py` imports the three moving Records
exports:
the repository's `arena/arena_settings.csv` and the live Tournament Google
Sheet CSV export. It validates timestamps, modes, season IDs, positive table
IDs, required fields, and conflicting duplicate IDs, and returns SHA-256
provenance. `materialize_metadata_tables()` creates
`arena_seasons_metadata` and `tournament_tables_metadata` only in a writable
staging generation. The live import validated 3,174 tournament rows and 14
Arena seasons through S14 before the metadata-backed generation was atomically
activated. The active Records generation contains 39 Fastest Games, 100
Biggest Turns, and 100 Elo Leaderboard rows; future spreadsheet changes must
be imported into the next immutable generation rather than mutating the active
database.

The route adapters are private page-shaped contracts. A generic aggregate over
`source_full_sample` is not equivalent for pages whose observation unit comes
from nested Logs, fixed buckets, map denominators, player identity joins, or
record spreadsheets; those differences remain explicit in each adapter and
must be reconciled before public cutover. Build/Hexes and the two combination
routes now use compact grouped plans, the moving Records sources are imported,
and the Phase 4 route-specific producer-reference reconciliation is complete.

## Phase 5 builder increment

The first builder optimization is implemented in
`analysis/phase2-local-vertical-slice.py`. It constructs the narrow serving
relations sequentially, computes table-level concession state with a grouped
lookup instead of a partition window, and enables DuckDB disk spilling. Its
safe VM defaults are two threads and a 2.8-GB execution ceiling; the spill
directory is explicit and can be placed on the builder disk. On the private
`e2-medium` `ark-nova-duckdb-test` VM, the complete vertical-slice build
finished in 344.421 seconds without an OOM kill. The post-build benchmark kept
the expected source and narrow-relation counts, Cards produced all 267 rows,
Card + Card reconciled against its local fixture, and four concurrent readers
returned consistent results. This validates the memory-safe builder prototype;
the daily refresh orchestrator and public cutover remain separate Phase 5
increments. `phase5_local_refresh.py` now provides the corresponding private
copy-on-write generation runner: it copies the active file, runs the bounded
builder, validates the report, renames the completed file into the generation
store, and activates it through the existing atomic pointer. Its end-to-end
VM test completed successfully; health/readiness, a Cards request, rollback,
and reactivation all passed. The runner preserves the active pointer on
builder or validation failure, but it is not yet wired to source import or a
production scheduler.
