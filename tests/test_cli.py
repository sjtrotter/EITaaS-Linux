import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from eitaas.api import Application, ConnectionRequest
from eitaas.cli import main
from eitaas.freerdp import Client


class ConnectTests(unittest.TestCase):
    def profile(self) -> Path:
        handle = tempfile.NamedTemporaryFile(suffix=".rdpw", delete=False)
        path = Path(handle.name)
        handle.write(
            b"redirectsmartcards:i:1\n"
            b"full address:s:synthetic.wvd.azure.us\n"
        )
        handle.close()
        path.chmod(0o600)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    @patch("eitaas.api.subprocess.Popen")
    @patch("eitaas.api.select")
    def test_secure_connection_defaults(self, select_client, popen):
        select_client.return_value = Client("/usr/bin/xfreerdp3", "x11", "3.30.0", True, True)
        popen.return_value = Mock(poll=Mock(return_value=0), returncode=0)
        result = Application().connect(ConnectionRequest(str(self.profile())))
        self.assertTrue(result.ok)
        command = popen.call_args.args[0]
        self.assertIn("/smartcard", command)
        self.assertIn("-clipboard", command)
        self.assertTrue(any("www.wvd.azure.us" in item for item in command))
        self.assertTrue(any("use-tenantid:on" in item for item in command))
        insecure_switch = "/cert:" + "ignore"
        self.assertNotIn(insecure_switch, command)
        self.assertEqual(popen.call_args.kwargs["stdin"], -3)
        self.assertEqual(popen.call_args.kwargs["stdout"], -3)
        self.assertEqual(popen.call_args.kwargs["stderr"], -3)
        self.assertIsNone(popen.call_args.kwargs["env"])

    @patch("eitaas.api.subprocess.Popen")
    @patch("eitaas.api.select")
    def test_isolated_webview_client_uses_xwayland(self, select_client, popen):
        select_client.return_value = Client(
            "/usr/libexec/eitaas-freerdp/bin/sdl-freerdp",
            "sdl",
            "3.31.0",
            True,
            True,
            True,
            True,
        )
        popen.return_value = Mock(poll=Mock(return_value=0), returncode=0)
        result = Application().connect(ConnectionRequest(str(self.profile())))
        self.assertTrue(result.ok)
        self.assertEqual(popen.call_args.kwargs["env"]["SDL_VIDEODRIVER"], "x11")

    @patch("eitaas.api.subprocess.Popen")
    @patch("eitaas.api.select")
    def test_clipboard_is_explicit(self, select_client, popen):
        select_client.return_value = Client("/usr/bin/xfreerdp3", "x11", "3.30.0", True, True)
        popen.return_value = Mock(poll=Mock(return_value=0), returncode=0)
        result = Application().connect(ConnectionRequest(str(self.profile()), clipboard=True))
        self.assertTrue(result.ok)
        self.assertIn("+clipboard", popen.call_args.args[0])

    @patch("eitaas.api.subprocess.Popen")
    @patch("eitaas.api.select")
    def test_connection_can_be_cancelled(self, select_client, popen):
        select_client.return_value = Client("/usr/bin/xfreerdp3", "x11", "3.30.0", True, True)
        process = Mock(poll=Mock(return_value=None), returncode=-15)
        process.wait.return_value = -15
        popen.return_value = process
        cancel = threading.Event()

        def progress(event):
            if event.phase == "connecting":
                cancel.set()

        result = Application().connect(ConnectionRequest(str(self.profile())), progress, cancel)
        self.assertTrue(result.ok)
        self.assertTrue(result.value.cancelled)
        process.terminate.assert_called_once()

    @patch("eitaas.cli.Application.doctor")
    def test_cli_uses_application_api(self, doctor):
        from eitaas.api import DoctorReport, Result

        doctor.return_value = Result(
            DoctorReport("Linux", "x11", True, False, True, {}, (), False, True)
        )
        with redirect_stdout(StringIO()):
            self.assertEqual(main(["doctor", "--json"]), 0)


if __name__ == "__main__":
    unittest.main()
