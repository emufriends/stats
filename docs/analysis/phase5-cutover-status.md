# Phase 5 operating state

This file is the concise current operating contract for the DuckDB production
architecture. Detailed statistical and rollback evidence lives in
`increment8-cutover-rehearsal.md`; the architecture and population contracts
live in the root handoff.

Updated: 2026-09-25

## Serving release

The frontend uses immutable Cloud Storage snapshots for default views and the
bounded public gateway at
`https://duckdb-gateway-ioetmehoha-ew.a.run.app/v1/query` for filtered reads.
The gateway forwards only validated read-only requests to the always-on private
DuckDB VM. BigQuery is not a public analytical fallback.

The VM is `ark-nova-duckdb-test` in `europe-west1-c`, using an e2-medium with
4 GiB RAM and a 40 GiB disk. The active immutable code release is
`deploy-04d635035c9667e15b54`; `/home/ascri/current-app` points to that release.
Both `ark-nova-duckdb-api.service` and
`ark-nova-duckdb-refresh-worker.service` run through this pointer.

The active generation is `phase5-refresh-9086145ea79c7db43deb5752`, its data
version is `phase5-source-sync-7efb47511584a75bd22e-20260924001145`, and its
rollback parent is `phase5-hotfix-20260922-filter-performance-v2`. Readiness
reports `ready: true` and `rollback_ready: true`. The snapshot catalog has 98
expected objects; the complete release inventory has 102 valid artifacts. The
default-pack release version is
`ce396e942482ffe8b56383835402858bf76cd1514feda84d7ca613e4d7a89fae`.

## Refresh and publication

Cloud Scheduler requests one private refresh daily at 00:00 UTC. The VM worker
imports changed source families, refreshes moving spreadsheet sources, builds
narrow DuckDB derivatives, creates and validates an inactive candidate, and
publishes individual immutable objects before atomically replacing the pack and
serving pointers. A failure leaves the previous successful generation active.
The three-hour scheduler window is an orchestration limit, not permission to
activate partial output.

Source metadata checks avoid BigQuery work when a family is unchanged. Changed
Full Sample data uses one controlled canonical export with an 8 GiB query cap;
the measured scan is approximately 4.62 GiB. Logs uses native extraction only
when its fingerprint changes. Late corrections and deletions are reconciled by
table ID in a staging copy before any derivative is built. Arena, tournament,
and Records spreadsheet inputs use validated refresh-owned caches with explicit
`fresh` or `last_known_good` status.

The public API admits at most two analytical executions, uses one DuckDB thread
and an 800 MB per-query memory limit, applies a 90-second public deadline, and
deduplicates identical in-flight work. Refresh builds use two threads and a
2,000 MB DuckDB memory limit. Exact default scopes use generation-local
snapshots; restrictive scopes use local SQL.

## Certified evidence

The current generation passes:

- 227 local backend tests;
- all 49 independent same-source route reconciliations;
- all 13,456 Card + Card rows with strict raw-statistic comparison;
- 11 adversarial request/population/catalog fixtures;
- six retained standalone component-CI batches;
- Players General, Comparison, and combined-Elo graph histories;
- Arena graph artifacts;
- all 98 snapshots and all 102 release artifacts;
- representative desktop and phone-width Cards, Arena, and Players flows.

The explicit coverage inventory contains 63 unique entries. Additive Synergy
CIs do not exist; only ordinary standalone component EV CIs are retained.

The rollback evidence is a real two-way rehearsal: the paired parent generation
and public pack were activated and verified, then the current 102-artifact
release was republished and reactivated. The final restored generation and data
version match the pack, serving pointer, and public gateway response.

## Operational safeguards and limits

The project retains a 0.1 TiB/day BigQuery query quota. Legacy analytical and
Synergy-CI schedules remain disabled. Refresh-failure monitoring notifies the
configured operator address. The authenticated EUR 40 budget-shutdown handler
can stop the VM; a stopped VM causes refreshes and filtered reads to fail safely
until it is deliberately restarted.

The publication helper currently performs remote artifact operations one object
at a time. This is correct but makes a full rollback-and-forward rehearsal slow;
batching is a future deployment-speed optimization. Every new code or data
generation must rerun the same validation gates. Frontend files staged in the
publication tree are not public until an explicitly authorized GitHub push.
