import unittest
from unittest.mock import patch

from eitaas.freerdp import inspect_client


class FreeRDPReportingTests(unittest.TestCase):
    @patch("eitaas.freerdp._output")
    def test_warning_is_not_reported_as_version(self, output):
        output.side_effect = ["[deprecated] Wayland client has been deprecated", ""]
        client = inspect_client("/usr/bin/wlfreerdp", "wayland")
        self.assertEqual(client.version, "unknown")


if __name__ == "__main__":
    unittest.main()
