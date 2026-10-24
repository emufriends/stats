# Current corrupted-game audit

This is a read-only source audit using the canonical corruption predicate in
`corrupted-current-audit.sql`. It reads the current Full Sample source once,
requires all seven inputs to be non-null, groups by `table_id`, and marks a
table corrupted when any losing-player row has an action-count gap of at least
two.

## Current result

The direct source audit on 2026-09-16 returned:

| Measure | Current source |
|---|---:|
| Full Sample rows | 5,542,094 |
| Distinct tables | 2,771,047 |
| Corrupted tables | 9,021 |
| Base corrupted tables | 3,726 |
| MW corrupted tables | 5,295 |

The query processed 914,763,319 bytes in a dry run (about 0.85 GiB). It did
not create or modify a BigQuery table. The executed job was
`bqjob_r49dff414fed731d5_000001a0a7222ad4_1`.

The minimum qualifying gap is exactly 2 for 1,892 tables; the remaining 7,129
tables have a larger gap. Corrupted tables occur throughout the source date
range, from 2023-05 through 2026-09, and across standard, legacy, and beginner
maps. This is not evidence of a single-map ingestion problem.

## Export comparison

The private export created at 2026-09-15T21:02:04Z contained 5,531,256 rows,
2,765,628 tables, and 8,988 corrupted tables. The current source therefore
has 10,838 additional rows, exactly 5,419 additional two-player tables, and
33 additional corrupted tables. This makes new source games the leading
explanation for the difference between the export and the current audit.

The earlier 7,663 figure was only retained as a count; its table-ID set was
not saved. Therefore the complete 7,663-to-9,021 set reconciliation cannot be
proven retrospectively. The 1,325-table difference includes whatever source
growth or historical source corrections occurred between that earlier audit
and the private export.

## Reproducible sample

The query selects ten deterministic pseudo-random IDs using a fingerprint of
the table ID. They are intended for manual validation, not as fixed test
fixtures.

| table_id | dataset | map | date | losing player | turns | counted actions | gap |
|---:|---:|---|---|---|---:|---:|---:|
| 825349819 | MW | Map 5a: Park Restaurant | 2026-03-23 | Rhea35 | 44 | 11 | 33 |
| 833890693 | Base | Map A | 2026-04-09 | Sylvia_Enid | 38 | 21 | 17 |
| 763280654 | MW | Map 2a: Outdoor Areas | 2025-11-20 | generaf | 21 | 19 | 2 |
| 405914448 | Base | Map A | 2023-08-10 | Artemka 123 | 33 | 30 | 3 |
| 734209966 | MW | Map 7a: Ice Cream Parlors | 2025-09-24 | salieri12138 | 30 | 28 | 2 |
| 660614770 | MW | Map 5a: Park Restaurant | 2025-04-18 | Gurugutt | 18 | 13 | 5 |
| 637700518 | Base | Map 1a: Observation Tower | 2025-03-02 | Birmingham Winery | 14 | 12 | 2 |
| 407514696 | Base | Map 4: Commercial Harbor | 2023-08-15 | 2win9 | 12 | 8 | 4 |
| 508549989 | Base | Map 3: Silver Lake | 2024-05-05 | brolero | 11 | 8 | 3 |
| 588313043 | Base | Map 1a: Observation Tower | 2024-11-13 | Kidy17 | 27 | 21 | 6 |

The authoritative SQL remains the executable source of this report. Counts
must be recomputed for each source fingerprint and must not be hard-coded into
tests or used as a static publication gate.
