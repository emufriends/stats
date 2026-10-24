# Phase 1–3 architecture review

> Historical decision record. Its green Phase 3/4 labels describe the state
> understood at that time and are not current parity certification. The
> 2026-09-22 migration review found contract and population regressions that
> must pass the newer increment gates before a replacement release is built.

## Decision

DuckDB remains the selected local analytical engine. Phases 1–3 establish a
cost-contained production boundary, a representative local-data prototype, and
a private generation-based serving process. Production has not been cut over;
the private Phase 4 route-by-route statistical migration and reconciliation are
now complete, and Phase 5 is the public cutover and rollout phase.

## Alignment with the plan

| Phase | Intended result | Current result | Status |
|---|---|---|---|
| 1 — contain BigQuery cost | Disable uncontrolled public scans and frequent expensive maintenance; label and cap remaining jobs; skip unchanged refreshes; preserve coherent publication order | Uncached public BigQuery work is disabled by default, optional high-cost schedules are paused or retired, jobs use the cost-controlled client, source fingerprints skip unchanged work, partial publication is refused, and refresh dependencies are ordered | Complete as a containment layer |
| 2 — representative prototype | Exercise a normal page, player history, a difficult combination page, ordinary CI, and the chosen local engine on affordable hardware | Cards, Players history, Card + Card, strict MW eligibility, and standalone EV intervals run from one immutable local generation; same-generation producer checks and VM read benchmarks pass | Complete |
| 3 — decide and harden the local engine | Choose the engine; define immutable import/publication, rollback, caching, observability, a private API, and a parity gate | DuckDB selected; atomic generation pointer and rollback, staged import, read-only store, two-level cache, sanitized JSONL audit, readiness, bounded loopback HTTP API, complete route inventory, and representative parity report implemented | Complete privately |

## Serving boundary

The private API now has 50 native contracts. Four are the Phase 3
representative contracts:

- Cards point estimates;
- ordinary standalone-card EV confidence intervals;
- Players history;
- Card + Card point estimates.

Phase 4 additionally serves Maps/Metrics, Endgames/General and both CP views,
Maps/Tournament H2H, both Sponsor Endgames views, all Predictors views,
Actions/Starting Position, all four Scoring views, three other Actions views,
both Build views, Icons, three Conservation views, both Workers views, Home,
Opening Hand, all remaining Combos views, and all remaining Players views.

The capability catalog records every current backend page/view contract, and
none remain marked `phase4_pending`. Private route implementation is complete
and the Phase 4 numerical, contract, performance, and metadata gates now pass.
Public cutover still requires the Phase 5 rollout validation described in the
current handoff. No route falls through to BigQuery.

## Verification result

`analysis/phase3-parity-report.json` is a same-generation, local-only check.
The current run reports:

- 267/267 Cards rows reconciled;
- the deterministic first 1,000 Card + Card API rows reconciled against the
  13,456-row producer snapshot;
- zero missing keys, unexpected keys, count mismatches, or point mismatches;
- matching active and snapshot data version
  `phase2-20260915-b57235ad65db`;
- no BigQuery query and no public mutation.

The Phase 4 route-contract audit is recorded in
`analysis/phase4-route-contract-audit.json`. It reports 50 registered native
contracts, 20 representative scoped executions with JSON serialization
success, complete imported metadata, and no pending route. The unrestricted
Card + Endgame and Card + Action Card projections remain explicitly deferred
for compact implementations because their full nested plans exceed the
private VM's safe resource envelope.

Standalone EV confidence intervals remain part of the design. Additive Synergy
confidence intervals are intentionally absent from frontend, backend, serving,
and acceptance criteria.

## Correctness properties

- Cards `n_played` counts card/table observation rows, while `delta_played_n`
  separately retains the EV denominator.
- Memory-cache reads and writes deep-copy nested payloads so one request cannot
  mutate a later cached response.
- A failed staged manifest publication removes its orphan database instead of
  leaving a half-generation.
- Activation validation, lock, and pointer-write failures produce sanitized
  audit events.
- The capability catalog includes the legacy Players `arena_top_100` backend
  contract and distinguishes every native versus Phase 4 route.
- Ordinary standalone-card CI requests can include card type, preventing a
  same-name cross-type collision.
- Analytical HTTP concurrency is bounded to protect the small VM.

## Deferred work and non-bugs

- The first optimized full vertical-slice builder now completes on the 4-GiB VM
  with a 2.8-GB DuckDB ceiling, two threads, and disk spilling; the private run
  completed in 344.421 seconds without OOM. Production daily-build integration,
  compact source pruning, and refresh orchestration remain Phase 5 work.
- The current Players-history prototype uses the narrow representative identity
  lookup. Full merged-identity, filter, and response-shape parity belongs to the
  Players Phase 4 port.
- The Phase 3 Cards and Card + Card routes intentionally expose a representative
  subset of the final public payload. Their full page and snapshot contracts
  remain producer and Phase 4 work.
- Phase 5 alone changes public routing or removes BigQuery query permissions.
  Until then, Phase 1 safeguards must remain enabled.
