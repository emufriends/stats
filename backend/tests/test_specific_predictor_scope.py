"""Specific Predictors retain the opponent when scoping the focal player."""
import unittest
from phase4_local_routes import _next_predictor_sql
from phase4_local_scope import normalize_scope


class SpecificPredictorScopeTests(unittest.TestCase):
    def test_starting_position_is_applied_after_pairing(self):
        query, parameters = _next_predictor_sql({
            'is_mw': 1, 'starting_positions': ['First player'],
            'player_elo_min': 700, 'opponent_elo_min': 300,
        }, 'specific')
        base = query.split('), stats AS (')[0]
        self.assertNotIn('WHERE', base)
        self.assertIn('me.starting_position IN (?)', query)
        self.assertIn('me.pre_match_elo >= ?', query)
        self.assertNotIn('opp.starting_position IN', query)
        self.assertIn('First player', parameters)

    def test_base_does_not_emit_the_mw_only_reefer_condition(self):
        query, _ = _next_predictor_sql({'is_mw': 0}, 'specific')
        self.assertNotIn("'More reefers' AS condition", query)


if __name__ == '__main__':
    unittest.main()
