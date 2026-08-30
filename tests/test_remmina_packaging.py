import json
import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = PROJECT_ROOT / "packaging" / "remmina"
SPEC = (PACKAGE_DIR / "eitaas-remmina.spec").read_text()
MANIFEST = json.loads((PACKAGE_DIR / "sources.json").read_text())


class RemminaPackagingComplianceTests(unittest.TestCase):
    def test_native_debian_recipe_uses_private_prefix_and_embedded_auth(self):
        rules = (PACKAGE_DIR / "debian" / "rules").read_text()
        self.assertIn("PREFIX = /usr/lib/eitaas-remmina", rules)
        self.assertIn("-DWITH_RDP_AUTH_AAD=ON", rules)
        self.assertIn("-DWITH_PCSC=ON", rules)
        self.assertIn("-DWITH_SSO_MIB=OFF", rules)
        self.assertIn("--parallel 1", rules)

    def test_debian_source_preparation_reads_shared_manifest(self):
        preparer = (PROJECT_ROOT / "scripts" / "prepare-remmina-deb-source.py").read_text()
        self.assertIn('package_dir / "sources.json"', preparer)
        self.assertIn('manifest["patches"]', preparer)
        self.assertIn('metadata["sha256"]', preparer)

    def test_launcher_supports_rpm_and_debian_private_prefixes(self):
        launcher = (PACKAGE_DIR / "eitaas-remmina").read_text()
        self.assertIn("/usr/libexec/eitaas-remmina/bin/remmina", launcher)
        self.assertIn("/usr/lib/eitaas-remmina/bin/remmina", launcher)

    def test_pinned_manifest_matches_rpm_spec(self):
        freerdp = MANIFEST["sources"]["freerdp"]
        remmina = MANIFEST["sources"]["remmina"]
        self.assertIn(f"%global freerdp_version {freerdp['version']}", SPEC)
        self.assertIn(f"%global remmina_commit {remmina['commit']}", SPEC)
        self.assertRegex(SPEC, rf"(?m)^Version:\s+{re.escape(MANIFEST['package_version'])}$")

        declared_patches = re.findall(r"^Patch\d+:\s+(\S+)", SPEC, re.MULTILINE)
        self.assertEqual(declared_patches, MANIFEST["patches"])

    def test_manifest_has_https_sources_and_sha256_digests(self):
        for name, source in MANIFEST["sources"].items():
            with self.subTest(source=name):
                self.assertTrue(source["url"].startswith("https://"))
                self.assertRegex(source["sha256"], r"^[0-9a-f]{64}$")

    def test_manifest_names_existing_downstream_inputs(self):
        inputs = [*MANIFEST["patches"], *MANIFEST["downstream_sources"]]
        for filename in inputs:
            with self.subTest(filename=filename):
                self.assertTrue((PACKAGE_DIR / filename).is_file())

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
            "sources.json",
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
