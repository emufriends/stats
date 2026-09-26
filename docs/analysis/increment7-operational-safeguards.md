# Increment 7 operational contract

This is the current operational contract for efficient refresh and bounded
DuckDB serving. It is not a feature changelog.

## Refresh identity and reuse

One refresh identity covers the committed Full Sample/Logs manifest, normalized
Arena/Records/tournament source files, merged-player metadata, builder code,
route SQL/contracts, serving projection code, and snapshot construction code.
`cards_attributes.csv`, `merge_players.csv`, and every file under `contracts/`
are fingerprinted inputs and members of the immutable deployment bundle.
Fetch timestamps and status-report timestamps do not participate. Tournament
metadata is fetched and validated before this identity is calculated.

- If the active generation has the same identity, the refresh is successful but
  performs no build or publication and preserves `last_completed_at`.
- If an inactive generation has the same identity, it is reusable only when its
  database, release manifest, complete object-key set, byte counts, and SHA-256
  values validate. Publication then resumes from that candidate.
- Changed source families continue through the complete-export/table-fingerprint
  reconciler. Source and moving inputs remain immutable for the candidate.

## Serving limits

The e2-medium API is configured for two concurrent analytical executions, one
DuckDB thread and an 800 MB DuckDB memory limit per query. Public queries are
interrupted after 90 seconds. Exact concurrent requests share one execution and
response; they do not occupy separate DuckDB slots. Saturated unrelated requests
receive `serving_busy` and expired work receives `query_deadline`. Offline
snapshot construction uses a separate 600-second deadline while pinned to the
inactive candidate. The refresh builder uses two threads and a 2,000 MB DuckDB
memory limit.

These are aggregate safety rails, not performance claims. The production gate
must disable snapshot/persistent-cache shortcuts and measure non-default Cards,
Actions, and Combos filters while a real refresh runs.

## Disk and retention

A build begins only with at least 8 GiB free or 120% of the active database
size, whichever is larger. Cleanup protects the active generation, rollback
parent, publication-journal generations, and three newest completed generations.
It removes old snapshot directories together with their generation and removes
staging debris older than 24 hours only while no local refresh lock exists.

## Deployment and rollback

Code/config is one immutable tar archive containing a checksum inventory. The
archive is installed under `/home/ascri/releases/<version>` and `current-app` is
an atomic symlink. The deployment pointer advances only after archive,
descriptor, and installer publication. The API and worker systemd units execute
from `current-app`.

A production bundle cannot be created until the active data generation records
the exact prior public-object backups, prior snapshot pointer, and prior serving
generation. `phase5_rollback_release.py` restores that data/publication pair;
`phase5_install_deployment.py --rollback` restores the preceding code bundle.

The active application symlink is
`/home/ascri/current-app -> /home/ascri/releases/deploy-04d635035c9667e15b54`.
Both systemd units execute through that symlink. The corresponding active data
generation is `phase5-refresh-9086145ea79c7db43deb5752`, and readiness reports
`rollback_ready: true` with
`phase5-hotfix-20260922-filter-performance-v2` as the rollback parent.

## Billing policy

Google bills the account in EUR. The active policy is EUR 20 warning and EUR 40
hard stop; historical `$20/$40` language is planning shorthand, not a live FX
conversion. Both budgets apply to project `413312054512`. The EUR 40 topic has
an active OIDC push subscription to the private shutdown service. It stops only
`ark-nova-duckdb-test` in `europe-west1-c`, does not restart it, and does not
disable unrelated services. Budget data can arrive late, so EUR 40 is a safety
rail rather than a guaranteed maximum invoice.

## Verification commands

Run focused logic checks:

```text
python -m unittest tests.test_phase3_duckdb_service tests.test_phase3_api tests.test_increment6_transactional_publication tests.test_increment7_operational_controls
python phase5_verify_budget_policy.py
```

Run the production gate only against a corrected private candidate and include
the real refresh command:

```text
python phase5_increment7_gate.py --report phase2_private_data/increment7-gate.json --refresh-command <refresh command and arguments>
```

An `incomplete` result means the mixed read/refresh portion was not run and is
not permission to deploy.

The production gate passed against the exact inactive candidate while its real
refresh was generating snapshots. Uncached non-default requests completed in
32.952 seconds for Actions, 73.807 seconds for Cards, and 25.791 seconds for
Card + Card. Peak gate-process RSS was 983,552,000 bytes; minimum system
available memory was 710,447,104 bytes. The refresh completed successfully in
2 hours 24 minutes 40 seconds, the transaction published 102 objects, and the
40-GB disk retained 14,158,503,936 bytes free after cleanup. The bundle was then
installed atomically and both normal services passed readiness.

The 00:00 UTC scheduler sends valid JSON with the dedicated
`dashboard-refresh-scheduler` OIDC identity. Arena settings may name an ongoing
season before its roster is published; only ended seasons require a roster, and
an invalid end timestamp fails closed. Standalone component CIs remain available,
but snapshot generation deduplicates repeated card/action-card identities before
calculating them. Additive Synergy CIs do not exist.
