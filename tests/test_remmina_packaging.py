import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = PROJECT_ROOT / "packaging" / "remmina"
SPEC = (PACKAGE_DIR / "eitaas-remmina.spec").read_text()


class RemminaPackagingComplianceTests(unittest.TestCase):
    def test_eitaas_license_copy_matches_repository_license(self):
        self.assertEqual(
            (PACKAGE_DIR / "EITaaS-LICENSE").read_bytes(),
            (PROJECT_ROOT / "LICENSE").read_bytes(),
        )

    def test_original_sources_have_spdx_identifiers(self):
        cac_sources = ("eitaas_cac_" "auth.c", "eitaas_cac_" "auth.h")
        for filename in (*cac_sources, "eitaas-remmina"):
            with self.subTest(filename=filename):
                beginning = (PACKAGE_DIR / filename).read_text().splitlines()[:4]
                identifier = "GPL-2.0-or-later" if filename in cac_sources else "MIT"
                self.assertTrue(
                    any(f"SPDX-License-Identifier: {identifier}" in line for line in beginning)
                )
                self.assertTrue(any("Copyright (c) 2026 Stephen Trotter" in line for line in beginning))

    def test_downstream_patches_declare_their_license(self):
        patches = sorted(PACKAGE_DIR.glob("*.patch"))
        self.assertEqual(len(patches), 4)
        for patch in patches:
            with self.subTest(patch=patch.name):
                self.assertIn("License: GPL-2.0-or-later", patch.read_text().split("---", 1)[0])

    def test_spec_declares_every_local_source_and_patch(self):
        declared = set(re.findall(r"^(?:Source|Patch)\d+:\s+(\S+)", SPEC, re.MULTILINE))
        expected = {
            "eitaas_cac_auth.c",
            "eitaas_cac_auth.h",
            "eitaas-remmina",
            "EITaaS-LICENSE",
            "THIRD_PARTY_NOTICES.md",
            *(path.name for path in PACKAGE_DIR.glob("*.patch")),
        }
        self.assertLessEqual(expected, declared)

    def test_binary_package_installs_all_required_notices(self):
        installed_names = {
            "FreeRDP-LICENSE",
            "FreeRDP-cpufeatures-NOTICE",
            "Remmina-COPYING",
            "Remmina-LICENSE",
            "Remmina-LICENSE.OpenSSL",
            "EITaaS-LICENSE",
            "THIRD_PARTY_NOTICES.md",
        }
        for name in installed_names:
            with self.subTest(name=name):
                self.assertIn(f'"$license_dir/{name}"', SPEC)

    def test_notice_names_pinned_upstreams_and_all_components(self):
        notice = (PACKAGE_DIR / "THIRD_PARTY_NOTICES.md").read_text()
        for value in (
            "3.31.0",
            "030946c83fe1b7218a21b6d32f9c975b243b7031",
            "Remmina",
            "FreeRDP",
            "CAC integration",
            "one-shot launcher",
        ):
            with self.subTest(value=value):
                self.assertIn(value, notice)

        self.assertIn("copyright 2026 Stephen Trotter", " ".join(notice.split()))
        self.assertIn("developed with AI assistance", notice)


if __name__ == "__main__":
    unittest.main()
