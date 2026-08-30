import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from eitaas import doctor, remmina

MANIFEST = {"sources": {"remmina": {"version": "1.4.43"}, "freerdp": {"version": "3.31.0"}}}


def make_prefix(case: unittest.TestCase, *, client: bool = True, sso_mib: bool | None = None) -> Path:
    """Build a fake private prefix: optional bin/remmina and client library."""
    root = Path(tempfile.mkdtemp(prefix="eitaas-remmina-"))
    case.addCleanup(shutil.rmtree, root, True)
    if client:
        binary = root / "bin" / "remmina"
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"\x7fELF")
    if sso_mib is not None:
        library = root / "lib64" / "libfreerdp-client3.so.3"
        library.parent.mkdir(parents=True)
        needed = b"libssh.so.4\0" + (b"libsso-mib.so.0\0" if sso_mib else b"")
        library.write_bytes(b"\x7fELF" + needed)
    return root


class RemminaBundleTests(unittest.TestCase):
    def test_launcher_is_resolved_from_path_without_execution(self):
        with patch("eitaas.remmina.shutil.which", return_value="/usr/bin/eitaas-remmina") as which:
            self.assertEqual(remmina.find_launcher(), "/usr/bin/eitaas-remmina")
        which.assert_called_once_with("eitaas-remmina")

    def test_private_client_uses_first_existing_candidate(self):
        first = make_prefix(self) / "bin" / "remmina"
        second = make_prefix(self) / "bin" / "remmina"
        missing = make_prefix(self, client=False) / "bin" / "remmina"
        with patch("eitaas.remmina.PRIVATE_CLIENTS", (first, second)):
            self.assertEqual(remmina.private_client(), first)
        with patch("eitaas.remmina.PRIVATE_CLIENTS", (missing, second)):
            self.assertEqual(remmina.private_client(), second)
        with patch("eitaas.remmina.PRIVATE_CLIENTS", (missing,)):
            self.assertIsNone(remmina.private_client())

    def test_pinned_versions_come_from_installed_manifest(self):
        manifest = make_prefix(self) / "sources.json"
        manifest.write_text(json.dumps(MANIFEST))
        self.assertEqual(remmina.pinned_versions(manifest), {"remmina": "1.4.43", "freerdp": "3.31.0"})

    def test_pinned_versions_fall_back_to_unknown(self):
        unknown = {"remmina": "unknown", "freerdp": "unknown"}
        manifest = make_prefix(self) / "sources.json"
        self.assertEqual(remmina.pinned_versions(manifest), unknown)
        manifest.write_text("not json")
        self.assertEqual(remmina.pinned_versions(manifest), unknown)
        manifest.write_text(json.dumps({"sources": {"remmina": {"version": ""}}}))
        self.assertEqual(remmina.pinned_versions(manifest), unknown)

    def test_sso_mib_is_read_from_client_library_linkage(self):
        self.assertTrue(remmina.sso_mib_builtin(make_prefix(self, sso_mib=True) / "bin" / "remmina"))
        self.assertFalse(remmina.sso_mib_builtin(make_prefix(self, sso_mib=False) / "bin" / "remmina"))
        self.assertIsNone(remmina.sso_mib_builtin(make_prefix(self) / "bin" / "remmina"))
        self.assertIsNone(remmina.sso_mib_builtin(None))

    @patch("eitaas.remmina.subprocess.run")
    @patch("eitaas.remmina.shutil.which", return_value="/usr/bin/gdbus")
    def test_broker_check_queries_bus_without_activating_broker(self, which, run):
        run.return_value = Mock(
            returncode=0,
            stdout="(['org.freedesktop.DBus', 'com.microsoft.identity.broker1'],)",
        )
        self.assertTrue(remmina.identity_broker_available())
        command = run.call_args.args[0]
        self.assertIn("org.freedesktop.DBus", command)
        self.assertNotIn("/com/microsoft/identity/broker1", command)


class DoctorTests(unittest.TestCase):
    def report(self, launcher: str | None, prefix: Path | None, manifest: Path) -> dict:
        clients = (prefix / "bin" / "remmina",) if prefix else ()
        with patch("eitaas.remmina.find_launcher", return_value=launcher), patch(
            "eitaas.remmina.PRIVATE_CLIENTS", clients
        ), patch("eitaas.remmina.INSTALLED_MANIFEST", manifest), patch(
            "eitaas.remmina.identity_broker_available", return_value=False
        ), patch("eitaas.doctor.shutil.which", return_value=None):
            return doctor.report()

    def test_report_describes_installed_bundle(self):
        root = make_prefix(self, sso_mib=True)
        manifest = root / "sources.json"
        manifest.write_text(json.dumps(MANIFEST))
        data = self.report("/usr/bin/eitaas-remmina", root, manifest)
        self.assertEqual(
            data["remmina"],
            {
                "launcher": True,
                "client": True,
                "client_path": str(root / "bin" / "remmina"),
                "remmina_version": "1.4.43",
                "freerdp_version": "3.31.0",
                "sso_mib": True,
            },
        )
        self.assertNotIn("freerdp", data)
        self.assertFalse(data["identity_broker"])
        self.assertTrue(doctor.healthy(data))

    def test_missing_launcher_or_client_is_unhealthy(self):
        root = make_prefix(self)
        manifest = root / "sources.json"
        self.assertFalse(doctor.healthy(self.report(None, root, manifest)))
        data = self.report("/usr/bin/eitaas-remmina", None, manifest)
        self.assertFalse(doctor.healthy(data))
        self.assertEqual(data["remmina"]["remmina_version"], "unknown")
        self.assertIsNone(data["remmina"]["client_path"])
        self.assertIsNone(data["remmina"]["sso_mib"])
        self.assertFalse(doctor.healthy({}))


if __name__ == "__main__":
    unittest.main()
