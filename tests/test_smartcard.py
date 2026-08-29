import unittest
from unittest.mock import patch

from eitaas.smartcard import status


class SmartcardTests(unittest.TestCase):
    @patch("eitaas.smartcard._run")
    @patch("eitaas.smartcard.shutil.which", return_value="/usr/bin/tool")
    def test_reader_check_is_one_shot_and_avoids_card_data(self, which, run):
        run.return_value = {"available": True, "ok": True, "summary": "command completed"}
        status()
        commands = [call.args[0] for call in run.call_args_list]
        self.assertIn(["pcsc_scan", "-r"], commands)
        self.assertNotIn(["pcsc_scan", "-c"], commands)
        self.assertFalse(any("--login" in command for command in commands))


if __name__ == "__main__":
    unittest.main()
