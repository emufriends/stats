# Canonical local population contract

Analytical routes read the physical wide `prepared_full_sample_narrow` table,
the compact `game_player_narrow` canonical fact, or qualified page-specific
derivatives of those boundaries. The immutable raw `source_full_sample` import
is retained for source reconciliation and evidence; source `elo` and
`opponent_elo` values are not analytical inputs. The prepared wide table is
materialized during refresh, not joined through a view at request time.

The prepared player-game boundary provides:

- player Elo from `pre_match_elo` and post-game Elo from `post_match_elo`;
- opponent Elo from the unique opposing row's `pre_match_elo`, or null when a
  unique opponent cannot be established;
- normalized `First player` / `Second player` starting position;
- table-wide corruption and valid-completion flags;
- Arena season and tournament membership imported before derivative building;
- exact player names plus the dashboard's merged player identity;
- strict two-player Marine Worlds action-card telemetry eligibility.

Corrupted tables remain available only to Home. Other routes exclude them at
the shared prepared boundary. Completion is computed before focal-player Elo,
map, date, Arena, tournament, and starting-position filters. Pair-oriented
routes apply those filters to the focal player and obtain the opponent from the
unfiltered row of the already eligible table.

The refresh retains event-grain relations for normal card plays, opening-hand
dealt/kept cards, endgame scores, sponsor endgames, project rewards, action
history, and MW action-card selections. Page derivatives may aggregate these
relations but must not reconstruct them from already aggregated facts.

`phase2_population_contract_gate.py` is the fail-closed verification command
for this boundary. Its compatibility filename is stable; passing this source
population gate does not replace route-level response and numerical checks.
