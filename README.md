# Ark Nova Statistics

Statistics for Ark Nova games played on Board Game Arena.

Public dashboard: https://emufriends.github.io/stats/

## Repository layout

- `docs/` — GitHub Pages frontend, static assets, and current handoff documents.
- `backend/` — packaged maintenance-function source kept with the published
  repository.
- `ark_nova_dashboard_handoff.md` — canonical current architecture and product
  contract for future development sessions.

Default views load from versioned Cloud Storage snapshots. Filtered analytical
requests use the public DuckDB gateway backed by the private always-on VM. Public
traffic does not query BigQuery; BigQuery is a controlled refresh input only.

The complete backend, generation builder, refresh tooling, and route contracts
live in the separate local backend workspace documented by the handoff.

Do not publish local changes or deploy backend components without explicit owner
authorization for the current task.
