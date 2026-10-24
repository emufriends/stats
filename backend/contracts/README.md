# Dashboard behavior contracts

`dashboard-routes.v1.json` is the authoritative current contract for all 50
public API contracts, including helper/compatibility routes rather than 50
visible pages. It records each route's dataset behavior, completion
rule, map behavior, observation unit, eligibility, accepted request fields, and
required response fields.

Change this contract whenever a public population or response meaning changes.
Do not use similarly named metrics, response shape, or SQL execution alone as
evidence that two routes use the same population.

The other JSON files in this directory and `tests/fixtures/` are pinned
regression evidence. They help independent tests detect accidental drift, but
they are not instructions to reproduce an earlier architecture or data version.

The independent oracle in `tests/contract_oracle.py` deliberately avoids the
production route builders. Run its foundation suite with:

```text
python -m unittest tests.test_migration_contract_foundation
```

Run the complete current-artifact gate with:

```text
python phase5_contract_regression_gate.py --pack PATH_TO_CANDIDATE_PACK
```

A route is release-ready only when its population, unrounded numerical output,
response contract, snapshot, and filtered-query behavior all pass. Field-count,
schema-only, or SQL-compilation audits are supporting checks, not substitutes.
