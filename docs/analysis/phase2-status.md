# Phase 2 prototype status

Phase 2 is in the representative-prototype stage. Production still serves the
existing Cloud Function and BigQuery-backed snapshots; the private generation
below is a local experiment and is excluded from deployment.

## Completed in the prototype

- One immutable Full Sample/Logs export is stored privately as Parquet.
- DuckDB stores reusable player-game, deduplicated normal-card play, and
  flattened in-hand/seen card facts.
- The default Cards scope has the expected 267 post-exclusion card groups and
  matching population counts against the currently published Cards snapshot.
- A focused Card + Card query calculates Actual, standalone components, Sum,
  Synergy, Elo, and Played.
- Ordinary table-clustered standalone component CI runs locally. Additive
  combination/Synergy CIs are intentionally out of scope.
- A filtered Players history query, strict MW action-card eligibility query,
  and four concurrent read-only readers have been measured.
- The prototype builder no longer materializes the quadratic all-card-pairs
  relation. Pair and Card + Action Card work should use focused joins or
  compact aggregate keys.
- A local Cards snapshot producer now emits the complete 267-row default
  payload, including played/in-hand/seen values, play rates, Elo, and ordinary
  component CIs. It writes through a temporary file and atomic rename.
- A local Card + Card producer now emits the complete 13,456-row default
  payload with point estimates, Actual/component intervals, and no additive
  Synergy intervals. It keeps pair facts temporary rather
  than materializing a permanent quadratic observation table.
- The narrow generation now also persists default-scope component-by-table
  moments and a compact pair-by-table relation for Card + Card. The pair
  relation has one row per observed player-game/card pair, not one row per log
  event.
- The currently published default pack is still data version 2026-09-14,
  while this private generation is 2026-09-15. Therefore production parity is
  freshness-blocked until a matching reference pack is available; the local
  same-generation producer checks pass.

## Current measurements

The benchmark report is `analysis/phase2-local-benchmark-report.json`. On the
current workstation, representative timings are:

| Operation | Time |
|---|---:|
| Initial narrow local build (before log-fact materialization) | 51.783 s |
| Full Sample count | 0.003 s |
| Distinct tables | 0.146 s |
| Logs count | 0.001 s |
| Filtered MW card-play shape | 2.817 s |
| Grouped MW card deltas | 4.362 s |
| Filtered Players history | 0.358 s |
| Card + Card Actual | 2.271 s |
| Ordinary card CI | 0.975 s |
| Strict MW action-card eligibility | 3.683 s |
| Four concurrent readers | 0.218 s |

The current rebuilt narrow slice took 161.340 seconds on the workstation. It
contains 431,641 player-log rows, 11,341,845 distinct in-hand facts, and
28,388,686 distinct seen facts. A raw-Logs parity check using the same player
join as the Cards query found zero missing or extra in-hand/seen facts.

The optimized local Cards snapshot producer took 29.776 seconds on the
workstation and produced 267 rows. Its population reconciliation has zero
card-group and `n_played` mismatches against the same local query contract.

The staged Card + Card producer now reads the persisted pair relation, took
28.591 seconds on the workstation, and produced 13,456 rows. The pair
relation contains 33,425,349 default-scope rows. This remains a point-estimate
prototype; additive Synergy interval work has been removed from the serving
design.

The generated files `analysis/phase2-local-cards-snapshot.json` and
`analysis/phase2-local-card-card-snapshot.json` are current private prototype
outputs for this generation. Card + Card retains standalone component and
Actual intervals but no additive Synergy interval fields.

The focused reconciliation is
`analysis/phase2-local-reconcile-card-card.json`. Bamboo Forest + Expert In
Herbivores has 1,191 local observations. Against the newly generated
same-generation prototype snapshot, the unrounded point estimates and counts
match; this is a producer self-check, not a production comparison.

## Constrained VM result

The same read benchmark was rerun on `ark-nova-duckdb-test` (`e2-small`, 2 GiB
RAM, 20 GB balanced disk, `europe-west1-c`) against its valid private
generation. Full-sample count took 0.012 seconds; grouped MW card deltas took
6.747 seconds; Players history took 0.578 seconds; Card + Card Actual took
2.786 seconds; ordinary standalone-card CI took 1.300 seconds; strict MW
action-card scope took 4.271 seconds; and four concurrent readers took 0.088
seconds with consistent results. The complete machine-readable report is
`analysis/phase2-vm-benchmark-report.json`.

The VM's separate optimized DuckDB file was truncated and could not be used.
The complete 3.80 GB generation was transferred directly to the VM and passed
the exact byte-size check. The VM was resized to `e2-medium` (4 GiB), and the
Cards snapshot builder was retried against that valid file. It was killed by
signal 9 after 21.47 seconds, reaching 3,642,224 KiB (about 3.64 GiB) resident
memory with no swap. This is a constrained-builder out-of-memory/resource-
pressure result, not a query correctness failure. The Card + Card builder was
not started after that result. The detailed result is in
`analysis/phase2-vm-benchmark-report.json`.

After the builder test, the VM was started once more for a serving smoke test
with the current benchmark script. On `e2-medium`, all representative
read-only operations completed against the full database, the slowest was the
MW card grouping read at 7.358 seconds, and four concurrent readers completed
in 0.093 seconds with consistent results. The VM was stopped immediately after
the test. The earlier stale benchmark copy had included the retired Synergy-CI
query; it was replaced before this final run.

The workstation uses Python 3.14 with a matching DuckDB 1.5.5 native extension
in `phase2_private_data/python314`. The extension was explicitly unblocked for
this private environment and the import/query smoke test passed. All Phase 2
scripts now prefer that directory and fall back to the older Python 3.12
directory only when a Python 3.14 package is absent. The VM is currently
stopped.

This is viable for a private prototype, but it is not a license to run these
large scans for every public request. The serving design must build compact
default/filter-scope aggregates during the daily import and reserve focused
DuckDB joins for exceptional or background work.

## Phase 2 result and deferred work

The representative same-generation local slice is complete for Cards, Players
history, MW point estimates, Card + Card, and ordinary standalone CI. The local
producer reports reconcile Cards and Card + Card counts and unrounded values;
the VM smoke test confirms the corresponding read paths. Additive Synergy CIs
are retired and are not an acceptance target. A direct production comparison
remains freshness-blocked while the public pack is still on an older data
version.

The first builder optimization is now complete as a private Phase 5
prototype. `analysis/phase2-local-vertical-slice.py` builds the narrow serving
relations sequentially, computes table concession state with a grouped lookup,
and enables explicit DuckDB disk spilling. On the 4-GiB `e2-medium`
`ark-nova-duckdb-test` VM, the full vertical-slice build completed in 344.421
seconds with two threads and a 2.8-GB DuckDB ceiling, without an OOM kill. The
post-build read benchmark, Cards snapshot shape, focused Card + Card
reconciliation, standalone EV CI, and four-reader consistency checks passed;
the machine-readable reports are in `analysis/phase5-*.json`. This validates
the memory-safe builder path, but production daily-build orchestration and
full end-to-end refresh integration remain Phase 5 work. MySQL is not
installed on the development workstation, so no MySQL result is claimed.

Phase 3 now supplies the private serving API, atomic generation/rollback
workflow, persistent generation-aware cache, bounded query concurrency,
capability inventory, and representative parity gate. Incremental porting and
reconciliation of the remaining page families is Phase 4. No public route,
BigQuery permission, scheduler, GitHub repository, or cloud snapshot has been
changed by this prototype work.
