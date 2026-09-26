# Increment 4: Combos and MW Action Cards contract

This document describes the current private DuckDB implementation. It is a
serving contract, not a changelog and not evidence of public deployment.

## Combos

All five views derive their filtered population from the canonical,
non-corrupted player-game relation and the deduplicated normal-card event
relation. Dataset, map, Player/Opponent pre-match Elo, date, completion, Arena,
Tournament, Starting position, and Round filters are applied before component
and Actual means are calculated.

- Card + Card uses one observation per player-game and unordered pair of
  distinct played cards. Base and MW are separate populations.
- Card + Map compares the card's scoped mean with its mean on the displayed
  map.
- Card + Round compares the card's scoped mean with its mean in the displayed
  round bucket; repeated source log events are deduplicated by event identity.
- Card + Endgame pairs a scoped played card with a scored endgame in the same
  player-game.
- Card + Action Card is MW-only. It first requires the strict action-card
  telemetry contract, then pairs each deduplicated played normal card with both
  selected action cards. Its normal-card baseline is restricted to that same
  telemetry-complete population.

Minimum plays, directional searches, Type selections, map/round header
selections, sorting, permanent ranks, and pagination are response-projection
controls. They never redefine a statistical component population. Numeric
color ranges are calculated from the complete active backend payload before
those local visibility controls.

`EV (Actual)` and context-specific EV values retain their ordinary intervals.
Standalone component values beneath card/action-card names use a separate
visible-row batch keyed by data version, full filter scope, view, and canonical
row key. These component intervals cluster by `table_id`. Additive Synergy
intervals do not exist.

## MW Action Cards

The authoritative catalog contains exactly twenty cards: four numbered cards
for each of Animals, Association, Build, Cards, and Sponsors. All four views
require tables with exactly two players, five selection numbers in `0..4`,
three valid draft identifiers, and exactly two selected nonzero action types
per player.

General and Draft expose one shared twenty-row payload. Player-oriented EV,
upgrade split, and Elo fields use selected-card observations. Availability,
picked, draft-position, and undrafted fields use one table-card observation.
By map additionally requires both players to use the same Standard map and
ignores the sidebar map selection because maps are the table columns.
Synergies uses the one selected action-card pair per player-game. Its two
standalone action-card means have table-clustered component intervals; Actual
has its ordinary interval; Synergy remains a point estimate.

## Prepared relations and publication

The refresh builder owns a fixed catalog, strict eligible-table relation,
enriched selection observations, table-level draft facts, and action-card pair
facts. Default Card + Card aggregates carry `is_mw`, preventing Base/MW
leakage. Default snapshots contain component intervals for the same data
version. Card + Action Card has no Base snapshot.

Increment 4 is verified privately with real-schema source samples, direct
same-source aggregate comparisons, the exact twenty-card catalog assertion,
component-CI cluster checks, and response-projection tests. No Increment 4
candidate or snapshot is public until the complete restoration release gate is
green and publication is separately authorized.
