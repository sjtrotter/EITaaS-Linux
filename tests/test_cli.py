import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from eitaas.cli import main
from eitaas.freerdp import Client


class ConnectTests(unittest.TestCase):
    def profile(self) -> Path:
        handle = tempfile.NamedTemporaryFile(suffix=".rdpw", delete=False)
        path = Path(handle.name)
        handle.write(b"redirectsmartcards:i:1\n")
        handle.close()
        path.chmod(0o600)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    @patch("eitaas.cli.subprocess.run")
    @patch("eitaas.cli.select")
    def test_secure_connection_defaults(self, select_client, run):
        select_client.return_value = Client("/usr/bin/xfreerdp3", "x11", "3.30.0", True, True)
        run.return_value = Mock(returncode=0)
        self.assertEqual(main(["connect", str(self.profile())]), 0)
        command = run.call_args.args[0]
        self.assertIn("/smartcard", command)
        self.assertIn("-clipboard", command)
        insecure_switch = "/cert:" + "ignore"
        self.assertNotIn(insecure_switch, command)

    @patch("eitaas.cli.subprocess.run")
    @patch("eitaas.cli.select")
    def test_clipboard_is_explicit(self, select_client, run):
        select_client.return_value = Client("/usr/bin/xfreerdp3", "x11", "3.30.0", True, True)
        run.return_value = Mock(returncode=0)
        main(["connect", str(self.profile()), "--clipboard"])
        self.assertIn("+clipboard", run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
