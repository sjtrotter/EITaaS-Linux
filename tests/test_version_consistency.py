"""The single package version and its per-distribution spellings (issue #95).

`scripts/check-version-consistency.py` maps one canonical PEP 440 version from
pyproject.toml onto the string each packaging format must carry: RPM and
Debian take a `~` pre-release marker so a candidate sorts below its final
release, everything else keeps the canonical spelling.
"""

import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHECKER = PROJECT_ROOT / "scripts/check-version-consistency.py"


def _load_checker():
    """Import the checker so the mapping is asserted, never re-implemented."""
    spec = importlib.util.spec_from_file_location("check_version_consistency", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCHEME = _load_checker()


def project_version() -> str:
    text = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return re.search(r'^version = "([^"]+)"$', text, re.MULTILINE).group(1)


class VersionMappingTests(unittest.TestCase):
    """The canonical -> distribution mapping itself."""

    def test_final_release_is_spelled_identically_everywhere(self):
        for canonical in ("1.0.0", "0.2.0", "12.3.45"):
            with self.subTest(canonical=canonical):
                self.assertEqual(SCHEME.native_version(canonical), canonical)
                self.assertEqual(
                    set(SCHEME.expected_versions(canonical).values()), {canonical}
                )

    def test_pre_release_gets_a_tilde_only_on_rpm_and_debian(self):
        expected = SCHEME.expected_versions("1.0.0rc1")
        self.assertEqual(expected["RPM"], "1.0.0~rc1")
        self.assertEqual(expected["Debian"], "1.0.0~rc1")
        for name in ("pyproject", "python package", "RPM upstream_version",
                     "Arch", "manual page", "GUI manual page",
                     "AppStream metainfo", "release tag"):
            with self.subTest(declaration=name):
                self.assertEqual(expected[name], "1.0.0rc1")

    def test_every_pre_release_marker_maps(self):
        for canonical, native in (
            ("1.0.0a1", "1.0.0~a1"),
            ("1.0.0b2", "1.0.0~b2"),
            ("2.1.0rc10", "2.1.0~rc10"),
        ):
            with self.subTest(canonical=canonical):
                self.assertEqual(SCHEME.native_version(canonical), native)

    def test_unsupported_canonical_shapes_are_rejected(self):
        for canonical in (
            "1.0.0.dev1",
            "1.0.0.post1",
            "1!1.0.0",
            "1.0.0+local",
            "1.0",
            "1.0.0rc",
            "1.0.0-rc1",
            "1.0.0~rc1",
        ):
            with self.subTest(canonical=canonical):
                with self.assertRaises(ValueError) as raised:
                    SCHEME.native_version(canonical)
                self.assertIn("unsupported canonical version", str(raised.exception))


class VersionConsistencyTests(unittest.TestCase):
    def run_checker(self, *arguments: str, project_root: Path = PROJECT_ROOT):
        return subprocess.run(
            [sys.executable, str(CHECKER), "--project-root", str(project_root), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )

    def write_project(self, canonical: str, native: str, **overrides: str) -> Path:
        """Write a throwaway tree carrying every version declaration."""
        values = {
            "pyproject": canonical,
            "python": canonical,
            "upstream": canonical,
            "rpm": native,
            "debian": native,
            "arch": canonical,
            "man": canonical,
            "gui_man": canonical,
            "appstream": canonical,
        }
        unknown = set(overrides) - set(values)
        assert not unknown, f"unknown declaration(s): {sorted(unknown)}"
        values.update(overrides)

        root = Path(tempfile.mkdtemp(prefix="eitaas-version-"))
        self.addCleanup(shutil.rmtree, root, True)
        files = {
            "pyproject.toml": f'[project]\nname = "eitaas-linux"\nversion = "{values["pyproject"]}"\n',
            "src/eitaas/__init__.py": f'__version__ = "{values["python"]}"\n',
            "packaging/rpm/eitaas-linux.spec": (
                f"%global upstream_version {values['upstream']}\n"
                f"Name:           eitaas-linux\n"
                f"Version:        {values['rpm']}\n"
                f"Release:        1%{{?dist}}\n"
            ),
            "packaging/debian/changelog": (
                f"eitaas-linux ({values['debian']}) unstable; urgency=medium\n"
            ),
            "packaging/arch/PKGBUILD": f"pkgver={values['arch']}\npkgrel=1\n",
            "docs/eitaas.1": f'.TH EITAAS 1 "" "EITaaS-Linux {values["man"]}" ""\n',
            "docs/eitaas-gui.1": (
                f'.TH EITAAS-GUI 1 "" "EITaaS-Linux {values["gui_man"]}" ""\n'
            ),
            "data/org.eitaas.Helper.metainfo.xml": (
                "<component><releases>"
                f'<release version="{values["appstream"]}" date="2026-08-30"/>'
                "</releases></component>\n"
            ),
        }
        for name, text in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return root

    def test_all_version_declarations_match(self):
        result = self.run_checker("--tag", "v" + project_version())
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_mismatched_release_tag_is_rejected(self):
        result = self.run_checker("--tag", "v9.9.9-not-a-real-tag")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("release tag=9.9.9-not-a-real-tag", result.stderr)

    def test_final_release_uses_one_string_everywhere(self):
        root = self.write_project("1.0.0", "1.0.0")
        result = self.run_checker("--tag", "v1.0.0", project_root=root)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_pre_release_maps_to_native_tilde_forms(self):
        root = self.write_project("1.0.0rc1", "1.0.0~rc1")
        result = self.run_checker("--tag", "v1.0.0rc1", project_root=root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1.0.0~rc1", result.stdout)

    def test_pre_release_without_the_tilde_is_rejected_on_rpm_and_debian(self):
        for declaration, label in (("rpm", "RPM"), ("debian", "Debian")):
            with self.subTest(declaration=declaration):
                root = self.write_project(
                    "1.0.0rc1", "1.0.0~rc1", **{declaration: "1.0.0rc1"}
                )
                result = self.run_checker(project_root=root)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    f"{label}=1.0.0rc1 (expected 1.0.0~rc1)", result.stderr
                )

    def test_native_spelling_is_rejected_where_it_is_invalid(self):
        """`~` is not legal in an Arch pkgver, a PEP 440 version, or the tag."""
        for declaration, label in (
            ("arch", "Arch"),
            ("upstream", "RPM upstream_version"),
            ("python", "python package"),
        ):
            with self.subTest(declaration=declaration):
                root = self.write_project(
                    "1.0.0rc1", "1.0.0~rc1", **{declaration: "1.0.0~rc1"}
                )
                result = self.run_checker(project_root=root)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    f"{label}=1.0.0~rc1 (expected 1.0.0rc1)", result.stderr
                )
        root = self.write_project("1.0.0rc1", "1.0.0~rc1")
        result = self.run_checker("--tag", "v1.0.0~rc1", project_root=root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("release tag=1.0.0~rc1 (expected 1.0.0rc1)", result.stderr)

    def test_unmappable_canonical_version_is_reported(self):
        root = self.write_project("1.0.0.dev1", "1.0.0.dev1")
        result = self.run_checker(project_root=root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsupported canonical version '1.0.0.dev1'", result.stderr)


if __name__ == "__main__":
    unittest.main()
