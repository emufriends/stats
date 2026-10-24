import unittest

from phase5_increment8_cardcard_gate import _close, _rounded_match


class CardCardReferenceRoundingTests(unittest.TestCase):
    def test_display_difference_requires_a_real_midpoint(self):
        self.assertTrue(_rounded_match(1.234, 1.235, 1.2345, 3))
        self.assertTrue(_rounded_match(-1.234, -1.235, -1.2345, 3))
        self.assertFalse(_rounded_match(1.234, 1.235, 1.2341, 3))
        self.assertFalse(_rounded_match(1.234, 1.236, 1.2345, 3))
        self.assertFalse(_rounded_match(1.234, None, 1.2345, 3))

    def test_elo_does_not_get_a_relative_one_point_allowance(self):
        self.assertFalse(_rounded_match(1000, 1001, 1000.2, 0))
        self.assertTrue(_rounded_match(1000, 1001, 1000.5, 0))
        self.assertFalse(_close(1000, 1000.0001))


if __name__ == "__main__":
    unittest.main()
