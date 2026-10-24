# Public test-helper subset

The public backend mirror includes only three historical Python modules from
this directory because current synthetic tests import their helper functions:
`compare_snapshot_memory_20261002.py`, `profile_snapshot_pages_20261002.py`, and
`benchmark_refresh_builder_next_20261004.py`.

These are reference/testing helpers, not approved operator commands. Their CLI
entrypoints and hard-coded historical work directories must not be run against
production without a new scoped review. Private databases, output snapshots,
raw traces, qualification receipts, deployment archives and candidate trees
are intentionally excluded from the public repository. Their absence is not
evidence that a full qualification gate passed.
