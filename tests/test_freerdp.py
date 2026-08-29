import unittest
from unittest.mock import Mock, patch

from eitaas.freerdp import CANDIDATES, Client, discover, identity_broker_available, select


class FreeRDPTests(unittest.TestCase):
    def test_isolated_webview_client_is_preferred(self):
        self.assertEqual(
            CANDIDATES["sdl"][0],
            "/usr/libexec/eitaas-freerdp/bin/sdl-freerdp",
        )

    @patch("eitaas.freerdp.subprocess.run")
    @patch("eitaas.freerdp.shutil.which", return_value="/usr/bin/gdbus")
    def test_broker_check_queries_bus_without_activating_broker(self, which, run):
        run.return_value = Mock(
            returncode=0,
            stdout="(['org.freedesktop.DBus', 'com.microsoft.identity.broker1'],)",
        )
        self.assertTrue(identity_broker_available())
        command = run.call_args.args[0]
        self.assertIn("org.freedesktop.DBus", command)
        self.assertNotIn("/com/microsoft/identity/broker1", command)

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

    @patch("eitaas.freerdp.identity_broker_available", return_value=True)
    @patch("eitaas.freerdp.discover")
    def test_selects_capable_v3_with_broker(self, mocked, broker):
        client = Client("/usr/bin/xfreerdp3", "x11", "3.30.0", True, True, True, False)
        mocked.return_value = [client]
        self.assertEqual(select(), client)

    @patch("eitaas.freerdp.identity_broker_available", return_value=False)
    @patch("eitaas.freerdp.discover")
    def test_selects_sdl_webview_without_broker(self, mocked, broker):
        client = Client("/usr/bin/sdl-freerdp", "sdl", "3.30.0", True, True, False, True)
        mocked.return_value = [client]
        self.assertEqual(select(), client)

    @patch("eitaas.freerdp.identity_broker_available", return_value=False)
    @patch("eitaas.freerdp.discover")
    def test_rejects_terminal_oauth_fallback(self, mocked, broker):
        mocked.return_value = [
            Client("/usr/bin/xfreerdp", "x11", "3.30.0", True, True, True, False)
        ]
        with self.assertRaisesRegex(RuntimeError, "secure non-terminal"):
            select()


if __name__ == "__main__":
    unittest.main()
