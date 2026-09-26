# Increment 8 cutover rehearsal

This is the current release-candidate evidence for the DuckDB migration. It is
an operational contract, not a changelog.

## Verified candidate

- Immutable application release: `deploy-04d635035c9667e15b54`
- Data generation: `phase5-refresh-9086145ea79c7db43deb5752`
- Data version: `phase5-source-sync-7efb47511584a75bd22e-20260924001145`
- Rollback data parent: `phase5-hotfix-20260922-filter-performance-v2`
- Snapshot catalog: 98 expected and 98 present
- Complete release inventory: 102 artifacts, zero missing or invalid
- Default-pack release version:
  `ce396e942482ffe8b56383835402858bf76cd1514feda84d7ca613e4d7a89fae`

## Numerical and contract gates

- `phase4-independent-reconciliation.json` passes all 49 historical route
  contracts against direct generation-local source aggregates.
- `increment8-cardcard-gate.json` reconciles all 13,456 Card + Card rows with no
  missing, unexpected, or raw-statistic mismatches. Unrounded means and moments
  use a strict `1e-9` tolerance. Three-decimal presentation fields allow one
  display unit (`0.0010001`) because separate parallel floating reductions can
  fall on opposite sides of an exact half-thousandth.
- `increment8-contract-regression.json` passes all 11 adversarial contract
  fixtures, including routing, catalogs, populations, and dataset scope.
- `increment8-special-gate.json` passes six ordinary component-CI batches,
  Players General/Comparison/combined-Elo graph histories, and the Arena graph
  bundle.
- `increment8-coverage-inventory.json` is the authoritative nonduplicated
  coverage list. It contains 63 IDs: 49 route contracts, Card + Card, six
  component batches, three graph endpoints, and four ancillary artifact checks.

Synergy itself has no confidence interval. The six component batches above
cover the retained standalone card/action-card EV intervals shown inside
Synergy views; they do not restore covariance-aware Synergy intervals.

## Publication and rollback

`increment8-rollback-drill.json` records a real two-way rehearsal. The serving
pointer and public default pack were moved to the paired parent generation and
verified there. The complete current 102-artifact release was then republished,
the current generation reactivated, and readiness plus pack/data-version
alignment verified. Both `rollback_error` and `restore_error` are null.

The publication helper currently starts one `gcloud` process per artifact for
existence checks and uploads. This is correct but slow: the full rollback and
forward-restore rehearsal took roughly half an hour. Batching those remote
operations is a future deployment-speed optimization, not a cutover blocker.

## Frontend contract repair

Players omits `players_arena_seasons` when no Arena season is selected. An
explicit empty array remains invalid at the API boundary. This restores player
selection and prevents the table from entering an error state with undefined
metrics. Frontend publication remains subject to explicit GitHub authorization.

## Final verification

- The complete local backend suite passes 227 tests.
- JavaScript syntax checks pass in both the working frontend and publication
  tree.
- Desktop and phone-width browser checks pass for representative Cards, Arena,
  and Players table/graph flows. Players selection returns defined statistics
  without a synthetic Games row, and its combined Elo graph completes.
- The installed VM release is `deploy-04d635035c9667e15b54`; both services are
  active, `/readyz` reports `ready: true` and `rollback_ready: true`, and a real
  filtered Cards request through the public gateway returns the certified
  generation and data version.

## Release boundary

Increment 8 is technically complete. The corrected frontend publication tree is
staged locally, but this evidence does not authorize a GitHub write. Backend and
frontend publication remain one reviewed release decision.
