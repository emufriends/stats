# Public source review guide

This directory is the complete maintained backend **review source**, not an
automatically deployable or fully qualified production bundle. Begin with
`AUDITOR_GUIDE.md`, `README.md`, `contracts/dashboard-routes.v1.json`, and the
repository's `ark_nova_dashboard_handoff.md`.

## Operational state as of October 24, 2026

- The daily dashboard refresh is intentionally paused until the owner explicitly
  permits updates again. The separate Elo peak updater has its own schedule.
- Installed VM code remains `deploy-114e8d834a97b90f8640`. The retained serving
  generation is `phase5-refresh-5a42add2f59b590bd50f183f`; the last successful
  refresh was October 13. Publishing this repository changes none of those.
- The maintenance Cloud Function is `get-card-stats-00205-tax`, including the
  bounded source-export retry/private mismatch diagnostic repair deployed
  October 23. No refresh was run to qualify its full export/publication path.
- The updated merge source has 34 identity groups and 95 unique account names.
  S14's roster is also present in this repository. The installed VM's packaged
  merge input is older; repository synchronization does not update the installed
  release, materialized aliases, snapshots, or metadata caches.
- Editable backend files include numerical/EFF-08 work that is **not deployed**.
  Full native qualification stopped at a disk-safety floor; full fresh/reuse and
  public-output gates were not completed. Three retained duplicate-policy tests
  also fail on the baseline. Do not treat published source as rollout approval.

## Included and excluded

Included: maintained Python modules, tests, route contracts, systemd/service and
gateway source, source catalogs/rosters, Elo updater, deployment tools and current
runbooks. Three historical helper modules under `reports/` support synthetic
tests; they are not production commands to run blindly.

Excluded: source exports, player-game databases, serving pointers, live caches,
raw worker failures, private qualification outputs, deployment archives, native
Python extensions, operator coordination, credentials and personal budget email.
`budget_policy.json` is a public review example with its notification contact
redacted; the public frontend billing-audit JSON also omits that contact. No
production configuration was changed. Older local paths in the
runbooks describe the owner's deployment/evidence workspace, not files shipped
in this repository.

## Safe offline checks

From `backend/`, create your own virtual environment and install
`requirements-dev.txt`. Run targeted tests before considering broad discovery:

```sh
python -m unittest tests.test_merge_players tests.test_source_export_consistency tests.test_refresh_status tests.test_cost_containment
```

These tests use local/synthetic inputs. Private archived-sample checks require
operator-only fixtures and may skip; known held-policy failures are not test
passes. Full native memory, exact population, numerical, fresh/reuse, snapshot
and public-output qualification requires the separately retained evidence and
controlled inactive-generation workflow.

Do not run refresh/deployment/publication/cleanup scripts, invoke maintenance
endpoints, or change service/scheduler state as part of reviewing the code.
Production changes need explicit owner authorization and qualified immutable
deployment/rollback inventories.
