import unittest
from unittest.mock import patch

from eitaas.freerdp import Client, discover, select


class FreeRDPTests(unittest.TestCase):
    @patch("eitaas.freerdp.inspect_client")
    @patch("eitaas.freerdp.shutil.which")
    def test_auto_prefers_x11_even_on_wayland(self, which, inspect):
        which.side_effect = lambda name: f"/usr/bin/{name}" if name in {"xfreerdp3", "wlfreerdp3"} else None
        inspect.side_effect = lambda path, backend: Client(path, backend, "3.30.0", True, True)
        self.assertEqual(discover()[0].backend, "x11")

    @patch("eitaas.freerdp.discover")
    def test_rejects_missing_aad(self, mocked):
        mocked.return_value = [Client("/usr/bin/xfreerdp3", "x11", "3.0.0", False, True)]
        with self.assertRaises(RuntimeError):
            select()

    @patch("eitaas.freerdp.discover")
    def test_selects_capable_v3(self, mocked):
        client = Client("/usr/bin/xfreerdp3", "x11", "3.30.0", True, True)
        mocked.return_value = [client]
        self.assertEqual(select(), client)


if __name__ == "__main__":
    unittest.main()
