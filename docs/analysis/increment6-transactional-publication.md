# Transactional DuckDB release contract

This document describes the current release mechanism. It is an operational
contract for future agents, not a history of implementation changes.

## Candidate boundary

A refresh imports sources and builds derivatives into a new immutable DuckDB
generation. Adopting the candidate into the generations directory does not
activate it. The snapshot adapter is pinned to the candidate generation and has
its snapshot fast path disabled, so every validation query reads the candidate
database rather than the active generation or a partial candidate snapshot.

The active serving pointer changes only after the complete candidate artifact
set has been built and validated. A failed source import, derivative build,
snapshot query, artifact check, or release check leaves the prior generation
active. A lock left by a killed workflow is recoverable when its recorded
process no longer exists or its age exceeds four hours.

## Authoritative artifacts and versions

`phase5_snapshot_builder.py` writes `release-manifest.json` for each candidate.
The manifest is authoritative; publication never copies the member list from
the prior public pack. It includes:

- every route/dataset/mode snapshot produced by the current route inventory;
- both player autocomplete indexes;
- both Home snapshots and the parser-loaded `card-stats/home/defaults.js`;
- Arena latest, all-season, and season-manifest objects;
- the complete frontend default pack.

Each artifact records its exact public object key, size, SHA-256, and kind. The
release version binds the DuckDB data version to source-generation metadata,
moving-source fingerprints, route-contract hash, public contract schema, and
the relevant builder/serving code hashes. The pack separately marks its exact
snapshot members; ancillary artifacts remain mandatory even when they are not
embedded in the pack.

## Publication transaction

`phase5_publish_release.py` requires ownership of the global refresh lock. It
uploads immutable release-prefixed copies first and makes server-side rollback
copies of every stable destination. It then activates the local DuckDB and
snapshot pointers, publishes stable aliases, and uploads the default pack last.
If any step fails, it restores both local pointers and every public object that
was changed. The independent Elo-leaderboard publication path refuses to write
snapshots or the pack while the refresh lock is owned by this transaction.

The publisher persists `phase2_private_data/publication-transaction.json`
before activation and updates it after every public write. If the process is
killed, the worker invokes recovery; startup also recovers any surviving
journal before accepting another request. The three-hour refresh deadline
includes publication. A timeout therefore compensates an active transaction
instead of leaving the candidate live.

The refresh worker updates its committed source pointer and reports `100%`,
`last_completed_at`, and `completed_data_version` only after public publication
returns success. Failures retain the previous successful values.

## Verification

Run:

```text
python -m unittest tests.test_increment6_transactional_publication
python -m unittest tests.test_phase5_snapshot_builder tests.test_phase5_source_sync
python phase5_snapshot_validate.py <candidate snapshot manifest>
```

The fault suite verifies a failed final pack write, successful coordinated
activation, restart recovery, and stale workflow-lock recovery. Full candidate
snapshot generation remains part of the later release-rehearsal gate because it
is intentionally expensive.
