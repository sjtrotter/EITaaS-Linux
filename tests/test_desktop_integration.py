"""Desktop integration metadata for the EITaaS Connect helper GUI."""

import configparser
import shutil
import subprocess
import unittest
import xml.etree.ElementTree as ElementTree
from pathlib import Path

import eitaas


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DESKTOP_FILE = DATA_DIR / "org.eitaas.Helper.desktop"
METAINFO_FILE = DATA_DIR / "org.eitaas.Helper.metainfo.xml"
MIME_FILE = DATA_DIR / "eitaas-rdpw.xml"
ICON_FILES = (
    DATA_DIR / "icons/hicolor/scalable/apps/org.eitaas.Helper.svg",
    DATA_DIR / "icons/hicolor/symbolic/apps/org.eitaas.Helper-symbolic.svg",
)

APP_ID = "org.eitaas.Helper"
MIME_TYPE = "application/x-eitaas-rdpw"
SVG_NS = "{http://www.w3.org/2000/svg}"
MIME_NS = "{http://www.freedesktop.org/standards/shared-mime-info}"
FORBIDDEN_MARKS = ("Microsoft", "Windows")


def load_desktop_entry() -> configparser.SectionProxy:
    parser = configparser.RawConfigParser(strict=True, interpolation=None)
    parser.optionxform = str
    with DESKTOP_FILE.open(encoding="utf-8") as handle:
        parser.read_file(handle)
    return parser["Desktop Entry"]


class DesktopFileTests(unittest.TestCase):
    def setUp(self):
        self.entry = load_desktop_entry()

    def test_launch_metadata(self):
        self.assertEqual(self.entry["Type"], "Application")
        self.assertEqual(self.entry["Name"], "EITaaS Connect")
        self.assertEqual(self.entry["Exec"], "eitaas-gui %f")
        self.assertEqual(self.entry["Icon"], APP_ID)

    def test_mime_association(self):
        self.assertIn(f"{MIME_TYPE};", self.entry["MimeType"])

    def test_desktop_file_validate(self):
        tool = shutil.which("desktop-file-validate")
        if tool is None:
            self.skipTest("desktop-file-validate not installed")
        result = subprocess.run(
            [tool, str(DESKTOP_FILE)], capture_output=True, text=True, check=False, timeout=60
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), "", result.stdout)


class MetainfoTests(unittest.TestCase):
    def setUp(self):
        self.root = ElementTree.parse(METAINFO_FILE).getroot()

    def test_component_identity(self):
        self.assertEqual(self.root.tag, "component")
        self.assertEqual(self.root.get("type"), "desktop-application")
        self.assertEqual(self.root.findtext("id"), APP_ID)
        self.assertEqual(self.root.findtext("project_license"), "MIT")
        self.assertEqual(self.root.findtext("launchable"), DESKTOP_FILE.name)

    def test_provides(self):
        self.assertEqual(self.root.findtext("provides/binary"), "eitaas-gui")
        self.assertEqual(self.root.findtext("provides/mediatype"), MIME_TYPE)

    def test_newest_release_matches_package_version(self):
        releases = self.root.findall("releases/release")
        self.assertTrue(releases)
        self.assertEqual(releases[0].get("version"), eitaas.__version__)
        # AppStream lists releases newest first.
        versions = [
            tuple(int(part) for part in release.get("version").split("."))
            for release in releases
        ]
        self.assertEqual(versions, sorted(versions, reverse=True))

    def test_name_and_summary_carry_no_third_party_marks(self):
        for field in ("name", "summary"):
            text = self.root.findtext(field)
            self.assertTrue(text)
            for mark in FORBIDDEN_MARKS:
                self.assertNotIn(mark, text, f"{field} contains {mark!r}")

    def test_appstreamcli_validate(self):
        tool = shutil.which("appstreamcli")
        if tool is None:
            self.skipTest("appstreamcli not installed")
        result = subprocess.run(
            [tool, "validate", "--no-net", str(METAINFO_FILE)],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class MimeInfoTests(unittest.TestCase):
    def test_mime_type_and_glob(self):
        root = ElementTree.parse(MIME_FILE).getroot()
        self.assertEqual(root.tag, f"{MIME_NS}mime-info")
        mime_types = root.findall(f"{MIME_NS}mime-type")
        self.assertEqual(len(mime_types), 1)
        self.assertEqual(mime_types[0].get("type"), MIME_TYPE)
        glob = mime_types[0].find(f"{MIME_NS}glob")
        self.assertIsNotNone(glob)
        self.assertEqual(glob.get("pattern"), "*.rdpw")
        self.assertLess(int(glob.get("weight")), 50)


class IconTests(unittest.TestCase):
    def test_icons_are_svg_documents(self):
        for icon in ICON_FILES:
            with self.subTest(icon=icon.name):
                root = ElementTree.parse(icon).getroot()
                self.assertEqual(root.tag, f"{SVG_NS}svg")
                self.assertIsNotNone(root.get("viewBox"))

    def test_icons_carry_no_third_party_marks(self):
        for icon in ICON_FILES:
            text = icon.read_text(encoding="utf-8")
            for mark in FORBIDDEN_MARKS:
                self.assertNotIn(mark, text, f"{icon.name} contains {mark!r}")


if __name__ == "__main__":
    unittest.main()
