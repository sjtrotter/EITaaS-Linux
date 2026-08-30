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
        self.assertIn("override_dh_installdocs:", rules)

    def test_debian_source_preparation_reads_shared_manifest(self):
        preparer = (PROJECT_ROOT / "scripts" / "prepare-remmina-deb-source.py").read_text()
        self.assertIn('package_dir / "sources.json"', preparer)
        self.assertIn('manifest["patches"]', preparer)
        self.assertIn('metadata["sha256"]', preparer)
        self.assertIn('remmina_dir / "data" / "reports"', preparer)

    def test_launcher_supports_rpm_and_debian_private_prefixes(self):
        launcher = (PACKAGE_DIR / "eitaas-remmina").read_text()
        self.assertIn("/usr/libexec/eitaas-remmina/bin/remmina", launcher)
        self.assertIn("/usr/lib/eitaas-remmina/bin/remmina", launcher)

    def test_native_arch_recipe_uses_private_prefix_and_embedded_auth(self):
        pkgbuild = (PACKAGE_DIR / "arch" / "PKGBUILD").read_text()
        self.assertIn("_prefix='/usr/lib/eitaas-remmina'", pkgbuild)
        self.assertIn("-DWITH_RDP_AUTH_AAD=ON", pkgbuild)
        self.assertIn("-DWITH_PCSC=ON", pkgbuild)
        self.assertIn("-DWITH_SSO_MIB=OFF", pkgbuild)
        self.assertIn("--parallel 1", pkgbuild)
        self.assertNotIn("https://github.com/FreeRDP", pkgbuild)

    def test_arch_builder_derives_version_and_checksum_from_shared_manifest(self):
        builder = (PROJECT_ROOT / "scripts" / "build-remmina-arch.sh").read_text()
        self.assertIn('package_dir/sources.json', builder)
        self.assertIn('prepare-remmina-deb-source.py', builder)
        self.assertIn('sha256sum "$archive"', builder)

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
        self.assertEqual(len(patches), 5)
        for patch in patches:
            with self.subTest(patch=patch.name):
                self.assertIn("License: GPL-2.0-or-later", patch.read_text().split("---", 1)[0])

    def test_cac_authentication_is_origin_bound_and_nonpersistent(self):
        source = (PACKAGE_DIR / "eitaas_cac_auth.c").read_text()
        for required in (
            "trusted_request_host",
            "webkit_authentication_request_is_for_proxy",
            "webkit_authentication_request_get_security_origin",
            'g_ascii_strcasecmp(protocol, "https")',
            '"rdp-authentication-host"',
            '"rdp-certificate-host"',
            "WEBKIT_CREDENTIAL_PERSISTENCE_NONE",
        ):
            self.assertIn(required, source)
        self.assertNotIn("g_str_has_suffix(host", source)

    def test_pkcs11_discovery_is_bounded_cancellable_and_uses_trusted_tool(self):
        source = (PACKAGE_DIR / "eitaas_cac_auth.c").read_text()
        for required in (
            '#define PKCS11_TOOL "/usr/bin/p11tool"',
            "PKCS11_TIMEOUT_SECONDS",
            "PKCS11_MAX_OUTPUT",
            "PKCS11_MAX_URI",
            "PKCS11_MAX_TOKENS",
            "PKCS11_MAX_CERTIFICATES",
            "G_SUBPROCESS_FLAGS_STDOUT_PIPE",
            "g_cancellable_cancel",
            "g_subprocess_force_exit",
            "g_atomic_int_compare_and_exchange",
        ):
            self.assertIn(required, source)
        self.assertNotIn("g_spawn_sync", source)
        self.assertNotIn("g_find_program_in_path", source)

    def test_oauth_patch_restricts_cloud_client_scope_and_redirect(self):
        patch = (PACKAGE_DIR / "0004-use-profile-avd-scope.patch").read_text()
        for required in (
            "avd_oauth_settings_are_safe",
            "a85cf173-4192-42f8-81fa-777a763e6e2c",
            "login.microsoftonline.com",
            "login.microsoftonline.us",
            "www.wvd.microsoft.com",
            "www.wvd.azure.us",
        ):
            self.assertIn(required, patch)

    def test_protected_profile_is_digest_bound_and_parsed_from_a_bounded_buffer(self):
        patch = (PACKAGE_DIR / "0005-bind-protected-rdpw-content.patch").read_text()
        for required in (
            "RDPW_MAX_SIZE",
            "O_NOFOLLOW",
            "fstat",
            "read(descriptor",
            "S_ISREG",
            "G_CHECKSUM_SHA256",
            "eitaas_rdpw_sha256",
            "freerdp_client_settings_parse_connection_file_buffer",
        ):
            self.assertIn(required, patch)
        self.assertNotIn("rf_process_event_queue", patch)

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
