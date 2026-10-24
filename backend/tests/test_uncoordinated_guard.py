"""Legacy direct-switch scripts refuse to run without an explicit acknowledgement."""
import os
import unittest
from unittest import mock

import phase5_activate_optimized_generation as activate
import phase5_promote_candidate as promote
import phase5_publish_snapshot_pointer as pointer
from phase5_uncoordinated_guard import ACK_VARIABLE, require_uncoordinated_ack


class UncoordinatedGuardTests(unittest.TestCase):
    def test_scripts_refuse_without_acknowledgement(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ACK_VARIABLE, None)
            for module in (activate, promote, pointer):
                with self.assertRaises(SystemExit) as raised:
                    module.main()
                self.assertIn("Refusing to run", str(raised.exception))

    def test_acknowledgement_allows_the_guard_to_pass(self):
        with mock.patch.dict(os.environ, {ACK_VARIABLE: "yes"}):
            require_uncoordinated_ack("x.py")  # does not raise


if __name__ == "__main__":
    unittest.main()
