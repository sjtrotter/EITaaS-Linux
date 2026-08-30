import json
import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = PROJECT_ROOT / "packaging" / "remmina"
UPSTREAM_DIR = PROJECT_ROOT / "upstream" / "remmina"
SPEC = (PACKAGE_DIR / "eitaas-remmina.spec").read_text()
MANIFEST = json.loads((PACKAGE_DIR / "sources.json").read_text())
CHANGELOG = (PACKAGE_DIR / "debian" / "changelog").read_text()
WORKFLOW = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text()


def debian_version():
    """Return the version of the newest packaging/remmina/debian/changelog entry."""
    match = re.match(r"^\S+ \(([^)]+)\)", CHANGELOG)
    assert match, "unparsable Debian changelog header"
    return match.group(1)


def executable_lines(text):
    """Drop whole-line shell/YAML comments so prose cannot trip the SSOT guards."""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


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

    def test_sso_mib_is_enabled_only_for_the_hardware_tested_rpm(self):
        # Intentional per-distribution policy, documented in
        # packaging/remmina/README.md ("SSO-MIB per distribution") and
        # docs/supported-platforms.md: the RPM is the hardware-tested baseline
        # and carries the identity-broker path, while the DEB and Arch
        # candidates ship only the embedded WebKitGTK CAC WebView path.
        rules = (PACKAGE_DIR / "debian" / "rules").read_text()
        pkgbuild = (PACKAGE_DIR / "arch" / "PKGBUILD").read_text()

        # Both the FreeRDP and the Remmina configure lines of the spec opt in.
        self.assertEqual(SPEC.count("-DWITH_SSO_MIB=ON"), 2)
        self.assertNotIn("-DWITH_SSO_MIB=OFF", SPEC)
        self.assertIn("BuildRequires:  sso-mib-devel", SPEC)

        for name, recipe in (("debian/rules", rules), ("arch/PKGBUILD", pkgbuild)):
            with self.subTest(recipe=name):
                self.assertEqual(recipe.count("-DWITH_SSO_MIB=OFF"), 2)
                self.assertNotIn("-DWITH_SSO_MIB=ON", recipe)
                self.assertNotIn("sso-mib", recipe.replace("-DWITH_SSO_MIB=OFF", ""))

        # Every recipe still builds the browser/CAC authentication path.
        for name, recipe in (
            ("eitaas-remmina.spec", SPEC),
            ("debian/rules", rules),
            ("arch/PKGBUILD", pkgbuild),
        ):
            with self.subTest(recipe=name):
                self.assertIn("-DWITH_RDP_AUTH_AAD=ON", recipe)

    def test_sso_mib_policy_is_documented_where_support_is_declared(self):
        for path in (
            PACKAGE_DIR / "README.md",
            PROJECT_ROOT / "docs" / "supported-platforms.md",
        ):
            with self.subTest(document=path.name):
                text = path.read_text()
                self.assertIn("-DWITH_SSO_MIB=ON", text)
                self.assertIn("-DWITH_SSO_MIB=OFF", text)
                self.assertIn("identity-broker", text)

    def test_recorded_downstream_revisions_agree_with_the_shared_manifest(self):
        package_version = MANIFEST["package_version"]

        # RPM: Version is the pinned upstream Remmina version and Release is
        # the downstream revision.
        release = re.search(r"(?m)^Release:\s+(\S+?)%\{\?dist\}$", SPEC)
        self.assertIsNotNone(release)
        release = release.group(1)
        self.assertRegex(release, r"^\d+\.\d+$")
        self.assertIn(f"- {package_version}-{release}\n", SPEC.split("%changelog", 1)[1])

        # Debian native package: <upstream version>+eitaas<downstream revision>.
        self.assertEqual(debian_version(), f"{package_version}+eitaas{release}")

        # Arch: pkgver is substituted from the manifest by
        # scripts/build-remmina-arch.sh, and pkgrel is Arch's own packaging
        # revision, which no manifest field records; only check it is a plain
        # positive integer.
        pkgbuild = (PACKAGE_DIR / "arch" / "PKGBUILD").read_text()
        self.assertIn("pkgver=@PKGVER@", pkgbuild)
        self.assertNotIn(f"pkgver={package_version}", pkgbuild)
        pkgrel = re.search(r"(?m)^pkgrel=(\S+)$", pkgbuild)
        self.assertIsNotNone(pkgrel)
        self.assertRegex(pkgrel.group(1), r"^[1-9]\d*$")

    def test_debian_build_and_ci_derive_versions_instead_of_hard_coding_them(self):
        builder = (PROJECT_ROOT / "scripts" / "build-remmina-deb.sh").read_text()
        lifecycle = (PROJECT_ROOT / "scripts" / "test-remmina-deb-lifecycle.sh").read_text()

        self.assertIn("dpkg-parsechangelog", builder)
        self.assertIn('source_root="$build_root/eitaas-remmina-$version"', builder)
        self.assertIn("dpkg-parsechangelog", WORKFLOW)
        self.assertIn("DEB_VERSION", WORKFLOW)
        # Debian artifact file names carry no epoch; both consumers strip one.
        self.assertIn("version=${version#*:}", builder)
        self.assertIn("DEB_VERSION=${deb_version#*:}", WORKFLOW)
        # The lifecycle downgrade target is derived from the package under test.
        self.assertIn('prior_version="$expected_version~0"', lifecycle)

        pinned = {
            "debian version": debian_version(),
            "package version": MANIFEST["package_version"],
            "freerdp version": MANIFEST["sources"]["freerdp"]["version"],
            "remmina commit": MANIFEST["sources"]["remmina"]["commit"],
        }
        consumers = {
            "scripts/build-remmina-deb.sh": executable_lines(builder),
            "scripts/test-remmina-deb-lifecycle.sh": executable_lines(lifecycle),
            ".github/workflows/ci.yml": executable_lines(WORKFLOW),
        }
        for label, value in pinned.items():
            for name, text in consumers.items():
                with self.subTest(pinned=label, consumer=name):
                    self.assertNotIn(value, text)

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
        self.assertEqual(len(patches), 6)
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
            '"rdp-certificate-transaction"',
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

    def test_protected_profile_is_single_buffer_and_native_settings_are_allowlisted(self):
        bounded = (PACKAGE_DIR / "0005-bind-protected-rdpw-content.patch").read_text()
        patch = (PACKAGE_DIR / "0006-Harden-RDPW-and-OAuth-transaction-boundaries.patch").read_text()
        for required in (
            "RDPW_MAX_SIZE",
            "O_NOFOLLOW",
            "fstat",
            "read(descriptor",
            "S_ISREG",
        ):
            self.assertIn(required, bounded)
        for required in (
            "rdpw_data",
            "rdpw_native_settings_allowlist",
            "rdpw_native_key_allowed",
            "freerdp_client_settings_parse_connection_file_buffer",
        ):
            self.assertIn(required, patch)
        self.assertNotIn("g_io_channel_new_file(from_file", patch.split("return remminafile;", 1)[0])
        self.assertNotRegex(patch, r"(?m)^\+.*eitaas_rdpw_sha256")
        self.assertNotIn("rf_process_event_queue", patch)

    def test_oauth_callback_is_owned_transaction_bound_and_uses_pkce(self):
        patch = (PACKAGE_DIR / "0006-Harden-RDPW-and-OAuth-transaction-boundaries.patch").read_text()
        for required in (
            "g_object_set_data_full",
            "oauth_callback_matches",
            "oauth-transaction",
            "g_cond_wait_until",
            "G_TIME_SPAN_MINUTE",
            "code_challenge_method=S256",
            "code_verifier",
            "winpr_RAND",
        ):
            self.assertIn(required, patch)

    @staticmethod
    def _added_web_auth_lines(patch: str) -> list[str]:
        """Return the lines a patch adds to plugins/rdp/rdp_web_auth.c."""
        sections = re.split(r"^diff --git ", patch, flags=re.MULTILINE)
        section = next(s for s in sections if s.startswith("a/plugins/rdp/rdp_web_auth.c"))
        return [line[1:] for line in section.splitlines() if line.startswith("+") and not line.startswith("+++")]

    def test_oauth_dialog_is_bound_to_its_transaction_in_downstream_and_upstream(self):
        downstream = (PACKAGE_DIR / "0006-Harden-RDPW-and-OAuth-transaction-boundaries.patch").read_text()
        upstream = (UPSTREAM_DIR / "0009-RDP-synchronize-OAuth-completion.patch").read_text()
        helpers = []
        for patch in (downstream, upstream):
            added = self._added_web_auth_lines(patch)
            start = added.index("#define OAUTH_TRANSACTION_TIMEOUT (5 * G_TIME_SPAN_MINUTE)")
            close = added.index("static void oauth_transaction_close(RemminaOAuthTransaction *transaction)")
            end = added.index("}", close)
            helpers.append([line for line in added[start:end + 1] if line.strip()])
            joined = "\n".join(added)
            # The transaction is reference counted; every dialog and idle owns a reference.
            self.assertIn("static RemminaOAuthTransaction *oauth_transaction_ref(", joined)
            self.assertIn('g_signal_connect(dialog, "destroy", G_CALLBACK(oauth_dialog_destroy_cb),', joined)
            self.assertIn("oauth_transaction_ref(transaction), oauth_transaction_unref);", joined)
            # Callbacks receive the transaction that created the dialog, never a lookup on gp.
            self.assertIn("GdkEvent *event, RemminaOAuthTransaction *transaction)", joined)
            self.assertIn("WebKitPolicyDecisionType type, RemminaOAuthTransaction *transaction)", joined)
            self.assertNotIn('g_object_get_data(G_OBJECT(gp), "oauth-transaction");', joined)
            # Timeout tears the dialog down on the GTK thread and cleanup clears the transaction.
            self.assertIn("static gboolean oauth_transaction_close_idle(gpointer data)", joined)
            self.assertEqual(joined.count("oauth_transaction_close(transaction);"), 2)
            self.assertEqual(joined.count('g_object_set_data(G_OBJECT(gp), "oauth-transaction", NULL);'), 2)
            self.assertNotIn("SET_AUTH_URI", joined)
        self.assertEqual(helpers[0], helpers[1])

    def test_certificate_loading_and_pin_state_are_asynchronous_and_bounded(self):
        source = (PACKAGE_DIR / "eitaas_cac_auth.c").read_text()
        for required in (
            "load_certificate_async",
            "certificate_load_thread",
            "g_task_run_in_thread",
            "rdp-certificate-transaction",
            "webkit_authentication_request_is_retry",
            "G_TIME_SPAN_MINUTE",
        ):
            self.assertIn(required, source)

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
