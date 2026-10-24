import unittest
from unittest import mock
from google.api_core.exceptions import NotFound, Forbidden, ServiceUnavailable

from phase5_publish_release import _remote_exists, _restore_aliases


class PublicationExistenceTests(unittest.TestCase):
    @mock.patch('phase5_storage_io.blob')
    def test_only_explicit_missing_object_is_absent(self, cloud):
        self.assertTrue(_remote_exists("gs://bucket/key"))
        cloud.return_value.reload.side_effect = NotFound('missing')
        self.assertFalse(_remote_exists("gs://bucket/key"))

    @mock.patch('phase5_storage_io.blob')
    def test_permissions_and_transport_errors_fail_closed(self, cloud):
        for error in (Forbidden('denied'), ServiceUnavailable('unavailable'), OSError('reset')):
            cloud.return_value.reload.side_effect = error
            with self.assertRaisesRegex(RuntimeError, "could not verify"):
                _remote_exists("gs://bucket/key")

    @mock.patch('phase5_publish_release.storage_io.delete_object', side_effect=OSError('delete failed'))
    def test_failed_delete_requires_proven_absence(self, cloud):
        with self.assertRaisesRegex(RuntimeError, "failed to restore"):
            _restore_aliases("bucket", {}, ["key"])


if __name__ == "__main__":
    unittest.main()
