# Phase 1 BigQuery cost containment

## Current backend contract

The production function and backend working copy at
`C:\Users\ascri\Desktop\ark-nova-function` use the same authoritative Phase 1
implementation. It is intentionally conservative while
the fixed-cost serving database is being built:

- `PUBLIC_BIGQUERY_QUERIES_ENABLED=false` by default. Default snapshots and
  exact persistent filter/history/CI cache hits remain available. An uncached
  public analytical request returns HTTP 503 and never submits SQL.
- `CARD_CARD_WARMING_ENABLED=false` by default. Additive Synergy-CI
  maintenance no longer exists; standalone component intervals use the normal
  component-CI path.
- `PARTIAL_BIGQUERY_REFRESH_ENABLED=false` by default. Legacy endpoints that
  replace only selected prepared tables are refused because they cannot publish
  one coherent generation. The tracked complete refresh remains available.
- Every BigQuery SQL job goes through `_CostControlledBigQueryClient`. Public
  jobs have a 2 GiB per-job ceiling; maintenance jobs have a 64 GiB ceiling.
  Jobs carry `ark_workload`, `ark_component`, and, during a tracked refresh,
  `ark_run` labels.
- Daily maintenance fingerprints BigQuery source metadata and all dashboard
  inputs. An identical source generation performs no analytical rebuild and
  does not advance the last atomic-publication time. If only the standalone Elo
  Leaderboard sheet changed, only its two dataset-neutral snapshot paths and
  the default pack are republished.
- Card moments are rebuilt before the card-play aggregate that reads them.

These defaults can be overridden only through deployment environment variables.
A zero byte-ceiling value deliberately removes that ceiling and must not be used
on the public deployment.

## Production state on 2026-09-15

The safeguards are deployed to `get-card-stats` in `europe-west1`.
`warm-card-card-default-scopes` and `refresh-card-dashboard-daily` are paused;
the former Synergy-CI scheduler has been retired because additive Synergy CIs
are no longer calculated. The independent
`update-elo-peaks-daily` remains enabled. The project-level
BigQuery `Query usage per day` quota is `0.1 TiB`. Default snapshot delivery is
available and a deliberately uncached public request returns HTTP 503 before
SQL.

The controlled run `d62491f30dc4480eb5973835cf715003` reached 60%, submitted
78 labeled jobs, and processed 73,304,696,183 bytes (68.2703 GiB). It stopped
before atomic publication because the first Cards snapshot needed at least
4,386,193,408 bytes while snapshot queries were accidentally classified under
the 2 GiB public ceiling. The previous pack and `last_completed_at` were
preserved. Snapshot publication now passes an explicit
`maintenance_snapshot` workload and receives the 64 GiB maintenance ceiling.
Do not repeat the legacy full refresh in the same quota day.

All maintenance Scheduler targets use `Content-Type: application/json`; without
that header, Flask ignores the JSON body and the schedule merely returns the
default Cards payload instead of invoking maintenance.

Maintenance credentials belong only in deployment configuration and Scheduler
headers. Commands and diagnostics must select individual non-secret environment
fields because a full function description or deployment result can print
plaintext environment values. Rotate a credential immediately if it appears in
terminal, CI, or agent output.

## Completed rollout and remaining controlled-refresh step

1. Pause the optional expensive schedules before deploying or manually running
   anything:

   ```powershell
   gcloud scheduler jobs pause warm-card-card-default-scopes --location=europe-west1 --project=ark-nova-stats-dashboard
   ```

2. Leave the independent `update-elo-peaks-daily` schedule active. Its query use
   remains part of the temporary BigQuery allowance until Phase 2 moves it to
   the imported source generation.
3. Deploy the backend while preserving all existing secrets and configuration.
   Explicitly retain these values:

   ```text
   PUBLIC_BIGQUERY_QUERIES_ENABLED=false
   CARD_CARD_WARMING_ENABLED=false
   PARTIAL_BIGQUERY_REFRESH_ENABLED=false
   PUBLIC_BIGQUERY_MAX_BYTES_BILLED=2147483648
   MAINTENANCE_BIGQUERY_MAX_BYTES_BILLED=68719476736
   ```

4. In BigQuery quota administration, set a temporary project-level **Query
   usage per day** ceiling no higher than `0.1 TiB` (approximately 102.4 GiB).
   This is a containment ceiling, not a promise that the legacy complete refresh
   fits beneath it. It limits a 31-day month to approximately 3.1 TiB before
   caching/free allowances, so a failed legacy refresh cannot silently return
   to the former usage level. Recalculate the quota after Phase 2 measurements.
5. Run no forced rebuild initially. Invoke the normal tracked refresh and inspect
   its result, labels, billed bytes, and status. The first post-deployment run
   will rebuild because no successful source fingerprint exists yet. If it
   exceeds a ceiling, measure the blocked job rather than removing safeguards.
   The controlled run has completed this measurement and exposed the snapshot
   workload-classification issue described above. Keep the main refresh paused
   until the next refresh design avoids repeating a non-publishing legacy cycle.
6. Verify that default snapshots still load and an uncached filter returns the
   intentional fixed-cost migration message. Verify an exact persistent cache
   hit remains available.

## Operational escape hatches

- An authenticated `daily_refresh` request may include `force_rebuild: true`.
  This bypasses only the unchanged-source gate; query ceilings remain active.
- Re-enabling public BigQuery or either optional maintenance workload requires
  an explicit environment change and must be temporary, measured, and reversed.
- Never configure the frontend to fall back directly to BigQuery. It has no
  credentials and the backend must remain the sole cost-control boundary.

## Verification

The focused and complete backend suite contains `test_cost_containment.py` and
passes 110 tests. Production verification status:

- The two optional high-cost Scheduler jobs are paused.
- Function environment values match this document.
- Default snapshots load and an uncached public filter is rejected with HTTP 503.
- Maintenance query jobs contain the `ark_workload`, `ark_component`, and
  `ark_run` labels.
- The byte ceiling stopped an oversized snapshot query before it was billed.
- A failed refresh preserved the prior atomic pack and completion timestamp.
- An unchanged normal refresh returns `reason: source_unchanged` without query
  jobs or a changed `last_completed_at`.
- An Elo-sheet-only refresh returns
  `refresh_scope: external_snapshots_only` and starts no analytical query.
