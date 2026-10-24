# Ark Nova Statistics

Statistics for Ark Nova games played on Board Game Arena.

Public dashboard: https://emufriends.github.io/stats/

## Repository layout

- `docs/` — GitHub Pages frontend, static assets, and current handoff documents.
- `backend/` — maintained backend review source, including the VM query service,
  builder, refresh/snapshot/deployment tooling, gateway, budget handler, Elo
  updater, tests, contracts and runbooks.
- `docs/tests/` — offline shared frontend regressions.
- `tools/` — explicit frontend/backend publication synchronizers.
- `ark_nova_dashboard_handoff.md` — canonical current architecture and product
  contract for future development sessions.

Default views load from versioned Cloud Storage snapshots. Filtered analytical
requests use the public DuckDB gateway backed by the private always-on VM. Public
traffic does not query BigQuery; BigQuery is a controlled refresh input only.

## Reviewing the backend

Start with [the publication/deployment boundary](backend/PUBLICATION_STATE.md),
[independent auditor onboarding](backend/AUDITOR_GUIDE.md), the
[backend overview](backend/README.md), and the
[route contract](backend/contracts/dashboard-routes.v1.json).

This repository contains the maintained implementation for review, but no
production databases, private source exports, credentials, caches, deployment
archives or operator qualification evidence. The budget configuration is a
public example with the notification contact redacted; the same contact is
omitted from the dated public billing-audit JSON. Historical workspace
paths in runbooks refer to operator-only data/evidence, not missing public data.

The source tree is **not the deployed production bundle**. Editable numerical
and EFF-08 work remains held pending complete native qualification. Three
known duplicate-policy regressions remain disclosed, not counted as passes.

As of October 24, 2026, daily dashboard refreshes remain intentionally paused.
The VM still uses `deploy-114e8d834a97b90f8640`; the maintenance Function uses
`get-card-stats-00205-tax`. Publishing this repository does not deploy either
component, replace serving data, or resume the scheduler. Updated merge mappings
need an authorized qualified VM deployment and generation rebuild to affect
materialized statistics; publishing the CSV alone is insufficient.

## Safe local checks

```sh
node --experimental-vm-modules --test --test-isolation=none docs/tests/shared-runtime.test.mjs
cd backend
python -m venv .venv
# Activate your environment, then:
pip install -r requirements-dev.txt
python -m unittest tests.test_merge_players tests.test_source_export_consistency tests.test_refresh_status tests.test_cost_containment
```

Tests use synthetic/local inputs. Private archived-sample checks require
separately retained operator fixtures. Native memory/full-builder/public-output
qualification is not established by these offline checks. Do not run operational
deployment, refresh, publication or cleanup scripts just to review the code.

Publication helpers default to the owner's adjacent working folders; use their
`--frontend-root`, `--backend-root` and `--repository` options for other layouts.
They do not push or deploy. Current CSV copies are synchronized; immutable
historical releases and rollback/evidence folders are intentionally unchanged.

Do not publish local changes or deploy backend components without explicit owner
authorization for the current task.
