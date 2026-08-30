import unittest
import threading
from unittest.mock import patch

from eitaas.api import Application


class ApplicationAPITests(unittest.TestCase):
    @patch("eitaas.api.smartcard.status")
    @patch("eitaas.api.doctor.report")
    def test_doctor_includes_smartcard_readiness(self, report, status):
        report.return_value = {
            "platform": "Linux",
            "session_type": "wayland",
            "display": True,
            "wayland_display": True,
            "pcsc_socket": True,
            "tools": {},
            "remmina": {
                "launcher": True,
                "client": False,
                "client_path": None,
                "remmina_version": "unknown",
                "freerdp_version": "unknown",
                "sso_mib": None,
            },
            "identity_broker": False,
        }
        status.return_value = {
            "reader": {"available": True, "ok": True, "summary": "command completed"}
        }
        result = Application().doctor()
        self.assertTrue(result.ok)
        self.assertTrue(result.value.smartcard.ready)
        self.assertFalse(result.value.ready)
        self.assertTrue(result.value.remmina.launcher)
        self.assertFalse(result.value.remmina.client)
        self.assertIsNone(result.value.remmina.sso_mib)

    @patch("eitaas.api.smartcard.status")
    def test_smartcard_async_runs_on_worker(self, status):
        caller = threading.get_ident()
        worker = []

        def result():
            worker.append(threading.get_ident())
            return {}

        status.side_effect = result
        report = Application().smartcard_status_async().result(timeout=2)
        self.assertTrue(report.ok)
        self.assertNotEqual(worker, [caller])

    @patch("eitaas.api.inspect_profile")
    def test_errors_are_redacted_at_boundary(self, inspect):
        inspect.side_effect = ValueError("code=very-secret-value")
        result = Application().inspect_profile("example.rdpw")
        self.assertFalse(result.ok)
        self.assertNotIn("very-secret-value", result.error.message)

    def test_profile_result_uses_basename_only(self):
        with patch("eitaas.api.inspect_profile") as inspect:
            inspect.return_value = {
                "size": 1,
                "mode": "0600",
                "cloud": "azure_government",
                "fields": [],
            }
            result = Application().inspect_profile("/sensitive/location/example.rdpw")
        self.assertTrue(result.ok)
        self.assertEqual(result.value.display_name, "example.rdpw")
        self.assertFalse(hasattr(result.value, "path"))

    def test_diagnostics_do_not_expose_profile_path(self):
        with patch("eitaas.api.inspect_profile") as inspect:
            inspect.return_value = {
                "size": 1,
                "mode": "0600",
                "cloud": "azure_government",
                "fields": [],
            }
            report = Application().diagnostics("/sensitive/location/example.rdpw")
        self.assertTrue(report.ok)
        self.assertEqual(report.value.profile.display_name, "example.rdpw")
        self.assertNotIn("/sensitive/location", str(report.value))


if __name__ == "__main__":
    unittest.main()
