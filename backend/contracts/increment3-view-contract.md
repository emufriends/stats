# Cards, Opening Hand, and Players response contract

This is the current implementation contract for these local routes.

## Cards

- Card plays retain legitimate repeated play events. Only exact duplicate log
  events are removed by the refresh-owned event relation.
- Africa, Americas, Asia, Australia, Birds, Europe, Habitat Diversity,
  Herbivores, Predators, Primates, Reptiles, Sea Animals, and Species Diversity
  are summary-project labels and never appear as Cards rows.
- `delta_played` averages event-grain played-card Elo deltas. `n_played` counts
  distinct tables containing the card, matching the established dashboard
  contract.
- `delta_in_hand` uses distinct table/player/card drawn-card observations.
  `n_seen` counts distinct tables where the card was drawn or displayed.
- A restrictive Round filter applies only to played events. In Hand, Seen, and
  Playrate are unavailable in that mode and are returned as null.
- Ordinary confidence intervals retain mean, sample deviation, and valid count.

## Opening Hand

- Population comes exclusively from `opening_cards` and `opening_keep` on
  valid, non-corrupted Logs player-games in the active shared filter scope.
- The public shared card-row names retain their established meanings:
  `delta_played`/`n_seen` are dealt EV/count and
  `delta_in_hand`/`n_played` are kept EV/count.
- Keeprate is `100 * kept / dealt`. Average Elo is the kept population's player
  pre-match Elo. Dealt and kept ordinary CI moments remain separate.
- The card universe comes from normal played cards and excludes the summary
  project labels listed above.

## Players

- General and Comparison always use completed, non-corrupted player-games.
  Performance by map keeps its optional completion control.
- The Players metric catalog is independent of Maps. It starts `Turns`,
  `Breaks triggered`, `Break%`; it contains neither `Games` nor `Rounds`, and it
  includes `Reputation actions` after Partner zoos.
- General compares the selected merged identity with All, Winners, Experts
  (pre-match Elo at least 500), and Masters (pre-match Elo at least 700).
  Last X applies only to the selected identity after the active scope.
- Comparison returns the same metric catalog with ordered `values` for up to
  five requested aliases. Each alias resolves through merged identity metadata;
  two aliases resolving to one identity are rejected.
- General and Comparison expose exact selected-account and associated-account
  game counts in the public response metadata.
- Performance by map supports up to eight requested aliases. Last X is ranked
  separately per merged identity and map before null EVs are removed. Each map
  value carries the ordinary mean/sample-deviation/count 95% CI fields.
- Normal history metrics apply the active dataset/sidebar scope and completion
  rule before Last X. Values are trailing 100-game rolling averages.
- Graph-only Elo uses `post_match_elo`, combines MW and Base, includes all game
  statuses, ignores sidebar filters and Last X, excludes null Elo and corrupted
  tables, and cannot be selected with another history metric.
- History responses use the public envelope
  `players_history`, `window_size`, `metrics`, and `players`; every player item
  contains `game_count`, `game_numbers`, `timestamps`, and metric `series`.

## Delivery safety

- The response-cache schema and public snapshot contract version change with
  these semantics. A snapshot is reusable only when both its data version and
  contract schema version match.
- Cards and Opening Hand assign every state transition a request generation.
  Starting another request, restoring a cached default, switching dataset, or
  unmounting aborts/invalidates prior work so a late filtered response cannot
  overwrite the current table.
- The public gateway has separate upload and response bounds: requests remain
  limited to 1 MiB while legitimate analytical responses may use the configured
  16 MiB default ceiling.

Run the focused gate with:

```text
python increment3_view_contract_gate.py
```

The broader `phase5_contract_regression_gate.py` checks the complete current
public pack. A green focused gate is not permission to publish a partial pack;
all route, snapshot, release, and rollback validations still apply.
