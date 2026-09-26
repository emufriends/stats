# DuckDB migration review and repair plan

Review date: 2026-09-22. Status: review only; no fixes, deployment, refresh, cloud configuration changes, or GitHub publication performed.

## Executive conclusion

The production read path has moved to DuckDB, but the migration is **not functionally or statistically complete**. The reported Cards and Players problems are real. They are not isolated rendering problems: important parts of the original population, metric, API, and publication contracts were not preserved.

The overall architecture remains reasonable: controlled BigQuery imports, a private DuckDB serving generation, a public HTTPS gateway, and static default snapshots. There is no evidence here that replacing DuckDB with another engine would solve the identified defects. The implementation and its acceptance criteria need repair.

The earlier statements that all route contracts had been independently reconciled, and that Phase 5 was complete, were too strong. Existing gates do not establish the numerical and behavioral equivalence they were used to claim.

Do not treat current analytical outputs as a certified replacement for the pre-migration dashboard. Do not reactivate public BigQuery queries or the expensive legacy refresh pipeline as an automatic workaround.

## Evidence and review boundaries

The review used:

- Current frontend request producers, rendering code, filters, caches, and page catalogs.
- Current DuckDB source materialization, derivative builders, route SQL, request normalization, CI projection, gateway, refresh worker, publication scripts, and acceptance tests.
- Preserved original query semantics in `C:/Users/ascri/Desktop/ark-nova-function/main.py`.
- Pre-migration Git revision `9cfe7cb` in `_publish_repo`, including the earlier backend and frontend.
- The immutable legacy pack `C:/Users/ascri/Desktop/ark-nova-function/phase2_private_data/reference_snapshots/legacy-default-pack-20260914.json`, version `2026-09-14T01:16:09.085507+00:00`.
- The current captured pack `C:/Users/ascri/Desktop/ark-nova-function/phase2_private_data/current-default-pack.json`, version `phase5-source-sync-3c6031ddbc8d09dea83f-20260921092543`.
- The route catalog and the purported 49-route independent reconciliation, plus the separate Card + Card implementation/gate.
- Read-only production VM, gateway, Scheduler, and budget observations, and representative public browser checks.

The September 8 Git baseline predates some authorized work. Recovery must retain later approved changes, including Reputation actions, the special Players Elo graph, and removal of additive Synergy CIs. It must not blindly restore the entire old checkout.

Older and current snapshot values come from different source dates. A changed mean alone is not proof of a regression. Findings below rely on incompatible definitions, fields, catalogs, impossible values, identical cross-dataset outputs, or reproducible request/UI failures. No paid BigQuery analytical reconciliation was run during this review.

All analytical page families were examined at the source/contract level. This was not a fresh numerical reconciliation of every cell against the same-source legacy query, nor an exhaustive interactive test of every filter combination. Those are explicit repair acceptance gates, not work represented as already complete.

Paths below are relative to `C:/Users/ascri/Desktop/ark-nova-function/` unless prefixed with `frontend/`; that prefix means `C:/Users/ascri/Desktop/ark-nova-stats-dashboard/`. Line numbers identify the inspected local revision and may move during repair.

## Directly observed examples

| Check | Original contract / preserved reference | Current result |
|---|---|---|
| Cards catalog | 267 configured cards | 280; the 13 excluded project cards are back |
| Opening Hand, Sun Bear | Opening cards dealt/kept | Uses played/drawn-card data; `n_played=39010`, `n_seen=33735`, `playrate_pct=115.64` |
| Players/General first row | Turns; no Games or Rounds table rows | Games is first, and Rounds is included |
| Selected player `portgard` in public Players UI | Selected-player metric table | `Could not update player statistics: upstream response is too large` |
| Card + Card MW versus Base | Different dataset populations | Both current snapshot `data` arrays are exactly equal, with 13,456 rows each |
| MW Action Cards/General | 20 individual special action cards | 25 rows, including the non-special values |
| Build/Hexes snapshot | Six hex-count buckets | Ten enclosure rows under the Hexes snapshot path |
| Actions/Starting Position | Nine configured rows | Four rows |
| Conservation/Project Rewards | 22 named rewards | Eight ordinal/overall rows |

These catalog and response-shape discrepancies cannot be explained by a few additional games arriving.

## Phase-by-phase assessment

| Phase | Assessment | What is established / what is missing |
|---|---|---|
| 1: Contain BigQuery costs | Substantially implemented, with remaining gaps | Public reads use the gateway; old analytical/CI/warming schedules are paused. Controlled source export has a byte ceiling. Source-family reuse and complete spending shutdown semantics are not implemented as claimed. |
| 2: Representative prototype | Useful engine/performance evidence, not application equivalence | Prototype execution and resource measurements are useful. Its simplified Cards, Players, and pair contracts were not adequate production specifications. |
| 3: Choose serving engine | DuckDB remains a reasonable choice | Immutable databases, parameterized SQL, private serving, and caching are sound building blocks. Serving/refresh memory, cancellation, and retention need hardening. |
| 4: Port all pages | Not complete | Native route availability was mistaken for preserved behavior. Numerous queries calculate different things; request and response contracts are incomplete. |
| 5: Cut over | Infrastructure cutover happened; acceptance is incomplete | The public gateway and continuous VM are live. Numerical acceptance, reliable public publication, refresh failure handling, and several operational safeguards remain incomplete. |

## Findings

Priority terminology: **P0** means a release-blocking correctness or publication defect; **P1** means a substantial functional/operational defect; **P2** means hardening or maintainability work. Priority does not imply that changes have been authorized by this review.

### R01 — P0: Common request normalization discards real frontend filters

Evidence: `phase3_duckdb_service.py:1126`, `phase4_local_scope.py:83`, `frontend/assets/js/snapshot-cache.js:214`, and Players' parameter builder.

The production frontend sends fields including `arena_only`, `rounds`, `players_arena_seasons`, `players_arena_only`, `players_players`, `last_x_games`, `players_history`, and `players_history_metrics`. The migrated normalization does not preserve/interpret the complete contract. For example, the scope layer recognizes `arena_seasons`, not the Players field name; the generic Arena-only switch is not applied.

Requests can therefore succeed while ignoring visible controls. Different requests also normalize to the same backend cache key, masking the problem on repeated reads.

Repair: define the full accepted request contract per route, including existing aliases; normalize it once; include every result-affecting field in the cache scope. Reject unsupported combinations instead of silently dropping them. Keep UI-only filters local where that was the original contract.

### R02 — P0: Opponent Elo reverted to the wrong rating moment

Evidence: `phase4_local_scope.py:157` and `main.py:3205`.

The shared DuckDB filter uses raw `opponent_elo`. The original prepared layer deliberately discarded that field because it mixes rating moments, deriving the opponent's pre-game Elo from the unique opposing player's `pre_match_elo` instead. Arena and Records also reference raw opponent Elo.

This changes which observations pass Elo filters, and consequently EVs, counts, and related metrics across page families. Direct comparisons also change the old null/minimum-zero behavior.

Repair: derive the canonical opponent pre-match rating in the local prepared layer with the original unique-opponent and malformed-table rules. Use it everywhere and restore documented null semantics. Do not change the user-approved ability to set asymmetric ranges.

### R03 — P0: Cards population and observation semantics were changed

Evidence: `phase2_local_vertical_slice.py:189`, `phase3_duckdb_service.py:1270`, original Cards query in `main.py:5625`, and both captured packs.

- The exclusion catalog is missing. Africa, Americas, Asia, Australia, Birds, Europe, Habitat Diversity, Herbivores, Predators, Primates, Reptiles, Sea Animals, and Species Diversity reappear.
- The new play derivative and query deduplicate at different levels from the original event-based mean. In particular, repeated played-round observations are collapsed into player/game/card observations.
- Round filters and the associated unavailable-column metadata are not preserved through normalization.
- Played/seen/in-hand counts and EV moments do not consistently preserve their intentionally different original observation units and null handling.

Repair: port the original Cards formulas and catalog exactly, with explicit tests for repeated rounds, duplicate log rows, both player rows, null EV, drawn/displayed observations, and each count definition. The reported EV drift has concrete causes; this review does not claim to have apportioned every numerical difference between them.

### R04 — P0: Opening Hand calculates the wrong statistic

Evidence: `phase4_local_routes.py:1096`, original Opening Hand query in `main.py:5888`, current Sun Bear payload.

The route uses played cards and the general drawn/in-hand derivative, not `opening_cards` and `opening_keep`. It effectively supplies Cards-like statistics under Opening Hand's labels. The 115.64% example is a direct symptom. The same excluded-card catalog is missing.

Repair: rebuild the opening dealt/kept observations with their original deduplication, eligibility, EVs, and counts. Add invariants for valid kept/dealt rates.

### R05 — P0: Selecting a player routes a table request to history

Evidence: `phase3_duckdb_service.py:1018` and `:1359`; public reproduction on September 22.

Any Players request containing `players_player` is classified as `history`, even when it is a General table request. The history implementation returns game records rather than the metric rows or graph envelope the frontend expects.

The public `portgard` reproduction fails at the gateway response-size ceiling. Smaller responses can reach table rendering with missing metric fields, explaining the user's `Undefined` rows.

Repair: route by the explicit view/history contract, not merely the presence of a selected player; validate the response envelope before rendering/caching.

### R06 — P0: Players tables and graphs are incomplete ports

Evidence: `phase4_local_routes.py:1380`, `phase3_duckdb_service.py:1359`, `main.py:6557`, and `frontend/assets/js/pages/players.js`.

- General uses the Maps metric catalog, introducing Games and Rounds and dropping the Players-specific Breaks triggered / Break% treatment.
- Comparison returns player-oriented rows rather than the expected selected-player metric matrix; selected players are not preserved in the normalized request.
- Performance by map does not preserve the selected-player and optional-completion contract.
- Histories do not implement the expected merged identities, requested metric series, Last X ordering, and rolling-history response.
- The graph-only Elo exception—selected identity, all statuses, both datasets, ignoring sidebar filters—is not implemented by the raw exact-alias/dataset history route.
- Counts, tooltip metadata, and graph eligibility information are missing or placeholders.

Repair: restore Players' own metric catalog, envelopes, merged identities, per-view completion rules, graph selection rules, and the authorized Elo exception. Retain Reputation actions in the approved position.

### R07 — P0: Card + Card ignores scope and serves MW aggregates for Base

Evidence: pair builder in `phase2_local_vertical_slice.py:235`, `phase3_duckdb_service.py:1381`, and equal current MW/Base snapshot arrays.

The pair aggregates are built for a fixed MW/default-like population. The serving query reads those aggregates without applying requested dataset, map, Elo, date, round, completion, Starting position, or tournament scope. Normalization bypasses the common scope for this route.

Repair: retain a fast exact-default aggregate, but provide sufficient filter-ready local facts/moments for every supported non-default scope. Never reuse an aggregate outside the scope that produced it. Test MW/Base inequality on a fixture deliberately containing different results.

### R08 — P1: Combos paging/search response contract is missing

Evidence: frontend Combos request construction versus `phase3_duckdb_service.py:1126` and the pair route SQL.

The frontend's `combination_paged`, page/page-size, sort/direction, primary/secondary search, type, and header-filter fields are not fully interpreted. Expected totals, full-result ranges, and permanent ranks are not supplied. Large complete result sets are returned instead.

The current compact-JSON Card + Card payload is about 15 MB per dataset, exceeding the gateway's 1 MiB response limit before any browser rendering.

Repair: preserve the existing server/client division of labor, paging envelope, directional/projection search semantics, global ranges, ranks, and minimum-play behavior. Do not fix this solely by increasing a body-size limit.

### R09 — P0: Other Combos lack the original population guarantees

Evidence: `phase4_local_routes.py:1148`, `:1221`, and `:1293`.

Card + Map/Round depend on a rounds field that normalization drops. Card + Action Card does not enforce the original strict table-level MW telemetry validation; it can include non-special or otherwise invalid selections and repeated played-round observations. Its normal-card baseline is not constrained to the specified eligible telemetry population. The omitted exclusions and wrong common Elo scope also apply.

Card + Endgame and the other component baseline aggregations require exact restoration of original weighting; their current joined/count-based implementation must not be certified from group counts alone.

Repair: reconstruct each view's Actual, standalone components, counts, and projection invariance from its original population contract. Enforce MW-only Card + Action Card at the API and snapshot catalog, not just the UI.

### R10 — P1: Standalone component CI batches are not compatible

Evidence: frontend component-CI request producers, `phase3_duckdb_service.py:1018`, normalization, and ordinary CI projection at `:865`.

The frontend requests component batches through Combos and MW Action Cards scopes. The adapter recognizes the special component route only for Cards and expects a single card name/type. The actual batch descriptors and row-key response contract are missing, so a component request can execute a normal point-estimate route instead.

Several ported component calculations also use ordinary observation SD/count rather than preserving the documented table-clustered standalone-card mean interval.

Repair: retain single-value CIs, including the correct observation/cluster treatment for each existing mean, and implement only the supported component-batch contract. Validate version/scope matching and repeated-card reuse. **Do not reintroduce additive Synergy CIs; their removal was intentional.**

### R11 — P0: MW Action Cards catalog, names, telemetry, and Draft are wrong

Evidence: `phase4_local_routes.py:1753` and current snapshots.

- Any non-null action number is accepted, including non-special values; General has 25 rows instead of 20.
- Ordering/naming is based on the action type rather than each of the 20 individual cards. Different Animals cards can receive the same name.
- Required availability, pick-rate, draft-position, and undrafted fields are null placeholders.
- Draft is generated as a separate shape rather than retaining the shared General/Draft payload contract.
- Strict two-selection table eligibility and By-map same-map eligibility are not preserved.

Repair: reuse the authoritative 20-card catalog and original telemetry validator; restore the shared General/Draft schema, By-map population, and Synergies pair semantics.

### R12 — P0: Predictors/Specific labels do not describe their calculations

Evidence: `phase4_local_routes.py:882`, especially the Specific catalog and common comparison expression.

Examples of current substitutions:

- Round 1 Upgrade / Project / Release compare total `Number_of_turns`.
- More reefers / small / medium / large animals all compare total `Played_animals`.
- More endgame / ingame CP compare final `Conservation`.
- First to 5/8 CP compare final `Conservation` rather than event order.
- No sponsor/project in starting hand uses unrelated draw/strength fields.

These are not approximations that preserve meaning. They are different questions shown under the old labels.

Repair: port each original predicate and its required Logs events, eligibility, and timing. Remove placeholder substitutes. Keep the two explicitly removed animal conditions absent.

### R13 — P0: Paired predictor filtering loses the opponent

Evidence: `_next_predictor_sql` creates one filtered `scoped` relation and self-joins it for `me` and `opp`.

A first-player-only scope removes the second player before pairing, leaving no opponent. Asymmetric Elo ranges can do the same. This violates the focal-player interpretation of these filters.

Repair: construct/validate the pair before focal-player filtering, preserving the original either-or behavior where applicable. Test first-only, second-only, both, and asymmetric ranges explicitly.

### R14 — P0: Sponsor Endgames EV buckets contain the wrong variable

Evidence: `phase4_local_routes.py:850`.

Bucket point values use `AVG(value)`—the scored CP/appeal value—where the existing delta/EV columns expect mean `elo_delta`. Their CI moments use Elo delta, so point and interval can describe different quantities. The supported sponsor catalogs/applicable buckets are also replaced by a broad all-sponsor set.

Repair: restore named sponsor eligibility, supported value ranges, and the correct point/CI variable. Check that each displayed interval is centered on the statistic it describes.

### R15 — P1: Actions rows and By-map aliases are incompatible

Evidence: `phase4_local_routes.py:950` and the Upgrades-by-map builder near `:505`; captured packs.

Starting Position has four rows instead of the original nine, omitting configured strength/comparison rows. Upgrades by map emits aliases such as `animals_map_1a` where the frontend expects the common map field, and its common scope does not force the completed population.

Repair: restore all configured rows, sections, common map aliases, frequencies/denominators, and completion rules across all four Actions tabs.

### R16 — P0: Build/Hexes snapshots contain Enclosures data

Evidence: `phase5_snapshot_builder.py:86`; Hexes snapshot comparison.

The snapshot request field map omits `build_view`. A requested Hexes snapshot therefore executes the default Enclosures route and writes it to the Hexes path. The live Hexes route also inherits an optional-completion scope despite its locked-completed UI.

Enclosures' empty-petting-zoo treatment is not the original built-but-unoccupied observation; empty EV output is left null.

Repair: make the snapshot manifest explicit and test the exact request and schema for each member. Restore Hexes eligibility and Enclosures' empty/special-building semantics.

### R17 — P0: Conservation rewards and frequency denominators changed

Evidence: `phase4_local_routes.py:648`, `:698`, and `:990`.

- Projects' per-bucket denominator construction can make frequency numerator and denominator identical rather than measuring the original population frequency.
- Project Rewards replaces named rewards/applicability with ordinal overall/first-through-seventh rows (22 reference rows versus 8 current rows).
- CP Rewards returns null frequency numerators/denominators.
- Combined CP-reward scope contains original events plus copies tagged as combined, then joins both, duplicating observations and distorting counts/uncertainty.

Repair: restore the three separate reward/project contracts, denominators, reward catalogs, applicability, combined-scope union semantics, and mode-dependent completion.

### R18 — P1: Scoring bins and overall frequencies changed

Evidence: `phase4_local_routes.py:294` and `:318`.

The original grouped Final Score/Appeal/CP display buckets were replaced by many exact-value buckets without authorization. `denom_avg` equals the bucket count instead of the full valid comparison population, producing 100% overall frequency per nonempty bucket. Some value ranges are hard-limited differently as well.

Repair: restore bucket boundaries, overflow/missing handling, and separate bucket counts from population denominators for all four views.

### R19 — P0: Locked completion is not enforced consistently

Evidence: `_simple_scope` at `phase4_local_routes.py:396`, its callers, and snapshot defaults.

Several routes use optional-completion scope while their frontend always shows a locked completed-only control: Icons, Workers/General, Build/Hexes, Conservation/Projects, and Actions/Upgrades by map are concrete examples. Snapshot requests do not supply a route-specific completion policy to compensate. Frequency modes requiring completion are not represented separately in snapshot generation.

Repair: define completion policy by view/mode, not by a generic helper default. Add an incomplete/conceded fixture that must never enter each hard-completed output. Preserve optional completion where authorized.

### R20 — P0: Home no longer implements Home's contract

Evidence: `phase4_local_routes.py:1073` and `frontend/assets/js/pages/home.js:129` / `:270`.

The route returns five generic Games/Turns/Score/Appeal/Conservation metrics. The frontend expects twelve specifically keyed totals such as `games_indexed` and `emus_played`. The Games branch ignores requested scope, and the route excludes corrupted games even though Home is explicitly the sole exception.

Home is absent from the inspected pack members; the separate embedded Home bootstrap can conceal the broken live route while continuing to show stale values.

Repair: restore all twelve original measures and scoped behavior, including the Home corruption exception; integrate both default Home snapshots and its bootstrap into publication.

### R21 — P1: Arena's backend-derived metrics do not all match the old definitions

Evidence: `phase4_local_routes.py:1701`; original Arena PR implementation in `main.py:5356` onward.

PR is now the same average raw opponent Elo as the opponent column, not the original performance-rating calculation. Win-rate handling does not preserve the original paired draw scoring. Turns/PPT use a single row's `end_game_triggered` instead of the canonical eligibility path and need reconciliation against the original completed population.

The roster's ID-based join is retained, which is correct. This does not validate all joined statistics.

Repair: keep rank/name/End spreadsheet ownership and ID joins, while restoring PR, opponent rating, win/draw, completion, and rating-history definitions.

### R22 — P1: Records enrichment and combined-dataset behavior have regressions

Evidence: `phase4_local_routes.py:1526` and `frontend/assets/js/pages/records.js:485` onward.

- Manual rows can be emitted into both dataset snapshots while the frontend concatenates them, causing duplicates.
- Enrichment flags do not reliably describe whether the selected source player was found; player/dataset selection needs the original exact rules.
- Arena classification uses season date/dataset without consistently requiring actual Arena-game telemetry.
- Most Icons names use singular forms incompatible with the frontend's icon catalog.
- Timestamp strings replace date-only values; local string-based upper-date filtering can exclude games on the selected final day.

Repair: preserve one combined Records population without duplicating manual rows; restore enrichment and icon/date contracts. Do not change the spreadsheet's authority over its five manually maintained values. Keep non-game Elo Leaderboard and valid missing Peak Arena values distinct from game eligibility.

### R23 — P1: Refresh downloads new Arena files but materializes a different directory

Evidence: `phase5_refresh_worker.py:200`, `phase5_refresh_workflow.py:187`, `phase4_materialize_route_derivatives.py:22`.

The worker downloads season CSVs into its moving-source directory. Arena materialization is called with the general root and reads `root/arena/s*.csv` instead. New season rosters/IDs can therefore be downloaded successfully but never enter the serving generation.

External-source fallback also lacks a complete, surfaced freshness/last-known-good report.

Repair: pass the committed moving-source generation consistently to settings, rosters, Records, and tournament consumers; include all content fingerprints and stale/fallback status in the generation manifest.

### R24 — P0: A successful daily/manual refresh does not guarantee public publication

Evidence: `phase5_refresh_worker.py:291-360`, deployed worker inspection, and separate `phase5_publish_pack.sh`.

The worker builds/activates a private generation, updates the local/source pointers, then writes `succeeded`, 100%, and `last_completed_at`. It does not invoke the public pack publication script. No separate application timer was found performing that step.

This allows filtered responses and public snapshots to diverge while `/refresh` reports success. It also violates the explicit definition of Last update: successful public atomic pack publication.

Repair: put verified public publication in the tracked workflow, and only then advance completion time. A local build alone must not be reported as a completed public refresh.

### R25 — P0: Candidate activation and failure recovery are not publication-safe

Evidence: `phase5_refresh_workflow.py:221-258`, `phase5_refresh_worker.py:318`, and `phase5_publish_pack.sh`.

The candidate becomes the serving generation before snapshot generation/validation. Live requests can observe unaccepted data while the public pack remains old. Exception rollback does not handle a killed subprocess in the same way; the three-hour timeout kills the workflow and can bypass its rollback/finally logic.

The publisher overwrites stable individual snapshot objects before replacing the pack. Clients taking individual fallback paths can see a partially published generation. Concurrent standalone Elo publication also needs an explicit serialization/CAS policy.

Repair: build and query candidates without changing the active serving pointer; validate all artifacts first; use immutable artifact paths plus coordinated generation/pack activation and compare-and-swap protection. Recover safely from process kill/restart, not only caught Python exceptions.

### R26 — P1: Snapshot versions and catalogs are insufficient cache boundaries

Evidence: `phase5_snapshot_builder.py:86`, `:131`, `:297`, `phase5_publish_pack.sh`, and frontend snapshot caching.

- Build routing is incomplete (R16).
- Card + Action Card receives an unnecessary Base snapshot because dataset selection is page-wide.
- Mode-specific defaults/populations are flattened; one payload is copied into multiple mode paths.
- Existing-file reuse checks data version but not query/schema/code version. Hotfixes can produce different meanings under the same source-derived version.
- Public pack membership is inherited from the previous pack rather than a complete authoritative release manifest; ancillary Home, indexes, and aliases have separate freshness risks.
- The captured pack is approximately 95 MB uncompressed versus approximately 48 MB for the legacy pack. Unneeded raw moments and changed row catalogs contribute; removing information is not the first remedy.

Repair: version source content, external metadata, query contracts, and snapshot schema; use explicit per-view requests and required artifacts. Invalidate both browser and server caches when semantics change, even if source rows do not.

### R27 — P1: Gateway limits and missing query cancellation cause failures

Evidence: `cloudrun-duckdb-gateway/gateway.py`, selected-player browser reproduction, and serving API resource configuration.

The gateway reuses a 1 MiB request-body limit as a response limit. Legitimate current Combos/history outputs exceed it, causing `upstream response is too large`. One wake/retry error branch also lacks the equivalent over-limit check; it can forward truncated JSON if that branch is enabled.

Client/gateway timeout does not guarantee interruption of the underlying DuckDB query. Duplicate in-flight backend work can occupy the bounded serving slots, while new requests fail or wait.

Repair: separate request and response policies, honor paging/compact envelopes, add bounded query execution and cancellation, and coalesce identical in-flight work. Do not indiscriminately raise limits around an incorrect response contract.

### R28 — P1: Cards Reset/default restoration has a frontend race and a no-op path

Evidence: `frontend/assets/js/pages/cards.js:446` / `:488`, `frontend/assets/js/snapshot-cache.js:228`.

- Apply with default parameters returns immediately even if the page-local default snapshot cache is empty; it does not load the missing default.
- Cards checks a mount token, not a distinct token for every filter request. Restoring a cached default does not invalidate an already-running filtered request.
- Shared cancellation occurs when starting another filtered fetch, not when switching to a cached snapshot. A late response can overwrite the restored default.

These defects explain intermittent restoration and can be amplified by slower migrated queries. Some mechanics predate the migration; this review does not label every frontend race as newly introduced.

Repair: assign a request/scope generation to every state transition, including local default restoration, and ignore/abort stale results. Fetch a missing default instead of silently returning. Apply the same pattern to sibling pages where present.

### R29 — P1: Production source sync does not use its advertised efficient path

Evidence: `main.py:1493`, `phase5_source_sync.py`, and the worker's workflow arguments.

The production entry point skips export when all fingerprints match, which is good. When anything changes, however, it exports Full Sample and Logs together rather than following the helper's changed-family reuse plan. It creates a new attempt-specific job/destination on retry rather than reusing successful work. A Logs-only change can still trigger a Full Sample query.

The worker does not pass the workflow's incremental-source option, so the tested reconciliation helper is not the normal worker import path. Controlled-export manifests also bypass the richer file/checksum validation used by other modes.

Repair: wire one tested source-sync implementation into production, reuse unchanged families and completed stages, validate exported objects/schema, and report actual processed/billed bytes. Preserve correction/deletion detection: these unpartitioned sources lack a trustworthy change timestamp, so an unproven append-only assumption is not acceptable.

### R30 — P1: Refresh status is written too late at startup

Evidence: `main.py:1590-1612`.

The new running status is constructed, but written only after synchronous source export finishes. During export, polling or a concurrent attach request can still see the preceding success. This is a concrete path back to the earlier immediate-100% symptom.

Repair: publish the new run ID/running phase before export, heartbeat every long stage, and make frontend attachment require that run identity. Keep last successful publication time unchanged until R24 succeeds.

### R31 — P1: Serving, rebuilding, and retained generations can exceed VM capacity

Evidence: read-only VM inspection on September 22; workflow memory default and serving connection setup.

The 4 GiB VM serves requests while building with a 2800 MB builder limit. The serving and worker systemd units have no `MemoryMax`; serving DuckDB connections have no coordinated global memory budget. Four concurrent requests plus refresh can exceed physical RAM even though each process works in isolation.

The 40 GiB disk had about 12 GiB available. Five retained database generations occupied about 14 GB. No complete automatic generation/source/spill retention policy was found.

Repair: budget serving and building together, constrain concurrency and memory, reserve disk before a build, and retain a tested active/rollback set while safely retiring unreferenced generations. Test under simultaneous reads and refresh, not only sequential benchmarks.

### R32 — P1: Budget safeguards differ from the requested dollar cap

Evidence: live read-only Cloud Billing budget configuration and `budget_shutdown_service/app.py`.

The configured thresholds are **EUR 20** and **EUR 40**, with credits included, not USD 20/40. The warning uses a notification channel; the shutdown budget also publishes to a shutdown topic. The receiver stops the VM only. It does not shut down every billable service, and it is not a literal account-wide spending ceiling. The gateway currently has auto-start disabled, which correctly avoids immediately restarting the stopped VM.

Repair: explicitly agree the billing-currency interpretation, document that VM shutdown is not complete project shutdown, verify notification delivery, and add a persistent administrative stop policy for relevant work. Validate incoming budget identity/period and avoid unintended restart/retry behavior. Do not silently promise an exact hard $40 ceiling from this implementation.

### R33 — P2: Deployment is not a complete immutable application release

Evidence: `phase5_vm_bootstrap.sh` and local/VM generation differences.

Startup downloads three mutable worker/builder files without a full versioned application manifest/hash set. Other route/service modules are maintained separately. A restart can combine mismatched versions or overwrite a hotfix. The local active database pointer is not the live VM generation, so an unspecified local test can validate the wrong data/code pair.

Repair: package all serving/building modules and dependencies as one versioned release, record hashes in generation manifests, and make tests identify the exact release and data generation. Keep rollback pairs explicit.

### R34 — P0: Acceptance gates certify the new implementation, not the old contract

Evidence: `phase4_independent_reconciliation.py`, `phase4_legacy_contract_audit.py`, `phase4_frontend_contract_audit.py`, and `frontend/analysis/phase4-progress.md`.

- Most independent checks are fixed group counts or one scalar probe, using one MW/Map 1a/completed scope and a 100-row limit.
- Several reference calculations reuse the same narrowed derivatives as the implementation under test; they share its population mistakes.
- Constants explicitly expect the incorrect new catalogs: four Starting Position rows, eight Project Rewards rows, and the new Scoring bucket counts.
- Home's test comment says corrupted games remain visible, while its check only expects five rows and cannot detect the opposite behavior.
- Field-presence checks and `LIMIT 0` schema inspection do not validate labels, values, denominator meanings, paging, or UI rendering.
- The old 267 versus new 280 Cards catalog was dismissed as population age, missing the exclusion regression.
- Default-route benchmarks accelerated by snapshot shortcuts do not establish non-default filter latency.

Repair: derive references independently from the original contract and common frozen raw input. Compare full keyed outputs, nulls, counts, ordinary CIs, metadata, and the actual frontend request/response envelope. Add adversarial fixtures before accepting any repaired route. Do not use passing current tests as evidence these findings are false.

### R35 — P1: Documentation and annotations overstate parity and operational completion

Evidence: `frontend/analysis/phase5-cutover-status.md`, Phase 4 progress/gate documents, and comments in the reviewed builders.

Examples include claims that filtered requests retain existing semantics, that 49 routes establish independent reconciliation, and that the efficient source reconciliation/publication workflow is the normal production path. Other annotations describe intended behavior contradicted by code (Home corruption and Records dataset neutrality are examples).

Repair: after implementation, rewrite the onboarding contract and operations runbook to match tested behavior, not a success narrative. Keep this review and verification evidence as separate audit artifacts. Record unresolved limitations explicitly; remove obsolete prototype assumptions from active guidance.

## Coverage by dashboard family

The table records review coverage, not certification. Common filter/Elo/CI/version defects apply even where no additional page-specific error was established.

| Family and views examined | Principal findings / remaining acceptance work |
|---|---|
| Home | R20, R24-R26, R30; twelve measures and corruption exception |
| Cards, standalone component route | R01-R03, R10, R28; original event/count semantics |
| Opening Hand | R04; dealt/kept data rather than general card plays |
| Maps: Metrics, Tournament H2H | R01-R02 and publication; reconcile map/table orientation and metric denominators; preserve H2H's absent sidebar |
| Endgames: General, CP Distribution, CP by map | Shared scope/CI defects; reconcile exact scored eligibility and distributions; no additional stand-alone numerical equivalence claim |
| Sponsor Endgames: CP, Appeal | R14 |
| Combos: Card + Card, Card + Map, Card + Round, Card + Endgame, Card + Action Card | R07-R10; all scopes and component populations |
| Predictors: General, Icons, Specific | R12-R13; actual predicate and paired filtering |
| Actions: Starting Position, Upgrades, Upgrade Order, Upgrades by map; EV/frequency modes | R15, R19, R26 |
| Build: Enclosures, Hexes; EV/frequency modes | R16, R19, R26 |
| Icons | R19 plus original per-icon validity, map, and denominator acceptance |
| Conservation: Projects, Project Rewards, CP Rewards; scopes/modes | R17, R19 |
| Scoring: Final Score, Appeal, Conservation Points, Reputation | R18 |
| Workers: General, 2 CP Worker | R19; restore per-view optional/hard completion and observation semantics |
| Players: General, Comparison, Performance by map, histories and legacy Arena alias | R05-R06, R21, R27-R28 |
| Arena: Elite League table, selected-player histories, all/latest bundles | R21, R23-R26 |
| Records: Elo Leaderboard, Fastest Games, Highest Scores, Biggest Turns, Most Icons | R22-R26; independent Elo updater remains separate |
| MW Action Cards: General, Draft, By map, Synergies | R10-R11; shared General/Draft response and strict telemetry |
| Card Details placeholder, Refresh, shell and global filters | No new card metadata required; R24-R30 affect Refresh; no redesign of the retained shell is called for |

## Production observations that are positive

- Public analytical requests use the HTTPS gateway/private VM rather than intentionally falling through to public BigQuery queries.
- The VM is continuously running as selected; gateway auto-start is false.
- Legacy analytical daily refresh, frequent CI scheduling, and warming jobs were paused when inspected.
- The private daily refresh is scheduled for 00:00 UTC; the independent Elo update remains separately scheduled.
- Parameterized query construction, read-only serving databases, source fingerprints, and immutable generation files provide useful foundations.
- The controlled Full Sample export has an 8 GiB single-query ceiling and checks metadata again after export.
- A previous generation exists. Its existence/readiness flag is useful, but is not equivalent to a complete failure/recovery rehearsal of public publication.
- Additive Synergy CIs remain intentionally removed. The repair must not recreate that expensive feature.

## Repair plan

### Increment 1 — Establish a trustworthy baseline and release gate

1. Freeze/reference the legacy query contracts and the latest authorized frontend contract; record the approved post-baseline exceptions.
2. Create a machine-readable per-view specification: request fields, default filters, mandatory eligibility, observation unit, labels/catalog, output fields, counts/denominators, CI method, paging, and sort metadata.
3. Build small adversarial source fixtures plus a same-source representative real-data fixture from already imported data.
4. Translate original reference calculations for offline comparison without invoking the migrated builders under test. No new BigQuery scan is inherently required for this work.
5. Make the current implementation fail those tests where defects are known. Remove false acceptance assumptions before fixing outputs.

Gate: the test suite detects the 13 extra cards, wrong Opening Hand source, unwanted Games row, Players misrouting, incorrect predictor predicates, wrong Hexes snapshot, and Card + Card dataset leakage.

### Increment 2 — Repair canonical local facts and scope

1. Derive canonical player/opponent pre-match Elo, exact/merged player identities, normalized Starting position, valid completion, table-level corruption, Arena membership, tournament membership, and strict MW telemetry.
2. Preserve raw source tables; build these as local prepared relations.
3. Preserve original card/round, opening-hand, endgame, reward, and action events at the observation units needed by each view.
4. Apply pair/focal-player filters in the correct order; implement all API field aliases and cache keys.

Gate: fixture-based and sampled real-data scope parity for MW/Base, maps, rounds, dates, completion, Arena, tournament, Starting position, asymmetric Elo, nulls, and malformed tables. Home must remain the corruption exception.

### Increment 3 — Restore Cards, Opening Hand, and all Players contracts

1. Repair Cards exclusions, moments, counts, round mode, and default/Reset state transitions.
2. Restore opening dealt/kept statistics.
3. Restore Players General/Comparison/Performance matrices, identity merging, counts, metadata, histories, and graph metric selection.
4. Implement the graph-only all-status, dataset-neutral Elo series exactly as approved.
5. Fix gateway response envelopes and limits in conjunction with routing, not in isolation.

Gate: the reported public failures are reproduced in candidate tests and then resolved; real frontend requests produce complete, correctly labeled results. Rapid Apply/Reset/dataset changes cannot display stale responses.

### Increment 4 — Restore Combos, MW Action Cards, and retained CIs

1. Restore all five Combos populations, components, counts, default aggregates, and arbitrary-scope queries.
2. Restore the 20-card MW catalog, telemetry validation, General/Draft schema, By-map population, and pair semantics.
3. Honor paging/search/projection/rank/range contracts; preserve local controls where intended.
4. Repair ordinary/component CIs and versioned component batches; leave additive Synergy CIs absent.

Gate: same-source keyed numerical comparisons for every component and Actual value, counts, retained CIs, default versus filtered parity, and pair projection invariance. Card + Card must no longer leak MW into Base.

### Increment 5 — Restore the remaining analytical and external-source pages

1. Port actual Predictors predicates, Actions configurations, and Sponsor Endgames EVs.
2. Restore Build, Conservation, Scoring, Icons, Workers, Maps, and Endgames catalogs, denominators, completion, and CI semantics.
3. Restore Home's twelve measures and explicit population exception.
4. Restore Arena PR/history/completion and Records enrichment, deduplication, icons, and date behavior.
5. Wire current external-source directories/fingerprints and last-known-good reporting consistently.

Gate: all route families pass full contract comparisons, including display catalogs and unrounded numerical results where applicable. Differences must be documented intentional contracts, not unexplained tolerated deviations.

### Increment 6 — Make refresh and publication transactional

1. Build candidates without activating them; allow snapshot/query validation against an explicit candidate generation.
2. Generate the authoritative full artifact manifest, including mode-specific snapshots, Home bootstrap, player indexes, Arena latest/all-season bundles, and the pack.
3. Version code/contracts and moving sources as well as source data.
4. Publish immutable artifacts and coordinate public pack/serving activation; guard concurrent Elo publication.
5. Advance public Last update only after successful publication.
6. Handle source/export failure, snapshot failure, subprocess timeout/kill, restart, concurrent refresh, and retry without partial activation or stale success.

Gate: fault-injection on a private candidate proves previous public success stays intact; the next successful run advances all required artifacts coherently. A three-hour timeout must not leave a candidate accidentally live.

### Increment 7 — Finish efficiency and operational safeguards

1. Use the tested changed-family source-sync/reconciliation path, with idempotent stage reuse and validated object manifests.
2. Avoid rebuilding unchanged artifacts where source, external metadata, and code/contracts are unchanged.
3. Add aggregate memory/concurrency budgets, query deadlines/cancellation, in-flight deduplication, and disk/retention controls.
4. Package a complete immutable deployment and exact rollback pair.
5. Reconcile EUR versus USD budget expectations, verify alerts, and document/enforce the actual shutdown policy.

Gate: genuine non-default filter performance and mixed read/refresh concurrency on the current 4 GiB VM. Measure memory, disk headroom, latency, and source bytes; do not substitute cached-default benchmarks.

Implementation state (2026-09-25): the deterministic refresh identity/no-op
path, checksum-validated candidate reuse, per-query aggregate resource controls,
90-second public deadline, exact in-flight request sharing, protected retention,
disk preflight, immutable code packaging, exact data/code rollback pairing, and
EUR-denominated budget policy are active in production. The real mixed
read/refresh gate passed on the 4-GiB VM against generation
`phase5-refresh-9086145ea79c7db43deb5752`; uncached Actions, Cards, and Card +
Card requests completed in 32.952, 73.807, and 25.791 seconds. The complete
refresh succeeded in 2 hours 24 minutes 40 seconds, and immutable application
release `deploy-04d635035c9667e15b54` is installed through `current-app` with a
rollback-ready data parent. The authenticated EUR 40 shutdown handler is live as
revision `budget-shutdown-00006-ttz`.

### Increment 8 — Rehearse and approve the corrected cutover

1. Run full local unit tests, contract fixtures, independent same-source reconciliation, snapshot validation, and representative desktop/phone UI flows against a private release candidate.
2. Verify all 49 historical contract entries plus Card + Card, component batches, graph endpoints, and ancillary artifacts; maintain one explicit non-duplicated coverage inventory.
3. Rehearse end-to-end rollback, not only a readiness flag.
4. Update current handoff/annotations to the verified architecture and remaining limitations.
5. Present the evidence and obtain publication authorization for the corrected release. This review does not authorize GitHub writes or cloud changes.

Final gate: backend migration changes infrastructure, not the questions answered by the dashboard. Every visible behavior change must be either a previously approved change or explicitly approved separately.

Implementation state (2026-09-25): Increment 8 is complete except for the
deliberately separate GitHub publication decision. The full local suite passes
227 tests. Independent same-source reconciliation passes all 49 historical
route contracts. The Card + Card gate reconciles all 13,456 rows; the special
gate passes six retained ordinary component-CI batches, three Players graph
endpoints, and the Arena graph bundle; the adversarial contract suite passes all
11 fixtures. The nonduplicated inventory records 63 covered entries. Snapshot
validation finds all 98 expected snapshots and all 102 release artifacts.

The rollback drill actually activated and verified the paired parent generation
and public pack before republishing and reactivating the current release. The
current immutable application release is `deploy-04d635035c9667e15b54`, with
generation `phase5-refresh-9086145ea79c7db43deb5752` and data version
`phase5-source-sync-7efb47511584a75bd22e-20260924001145`. `/readyz` reports
`ready: true` and `rollback_ready: true`, and a filtered Cards request through
the public gateway returns the same generation and data version.

Representative desktop and phone-width checks verify Cards, Arena, and Players
table/graph behavior. The corrected Players frontend omits
`players_arena_seasons` when no season is selected; player selection returns
defined metric rows without a synthetic Games row, and combined Elo history
renders. The remaining frontend files are staged locally. Publishing them is an
external change and still requires explicit GitHub authorization.

## Continuing operational limits

- The publication helper performs one `gcloud` process per artifact. It is
  correct but makes a complete rollback-and-restore rehearsal take roughly half
  an hour; batching is a deployment-speed optimization, not a parity blocker.
- The evidence certifies the frozen current generation and contract set. A new
  data or code generation must run the same validators before activation.
- Long-term public workload trends remain an operations concern monitored by
  latency, memory, disk, refresh, and budget alerts; they do not alter the
  statistical contracts certified here.
