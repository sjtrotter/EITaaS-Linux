import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
# The bundle inputs (pinned manifest, ordered patch series, smart-card integration
# sources, launcher, notices) live here; every packaging format consumes them.
PACKAGE_DIR = PROJECT_ROOT / "packaging" / "remmina"
UPSTREAM_DIR = PROJECT_ROOT / "upstream" / "remmina"
# Issue #80: one recipe per distribution builds one binary package.
SPEC = (PROJECT_ROOT / "packaging" / "rpm" / "eitaas-linux.spec").read_text()
RULES = (PROJECT_ROOT / "packaging" / "debian" / "rules").read_text()
CONTROL = (PROJECT_ROOT / "packaging" / "debian" / "control").read_text()
PKGBUILD = (PROJECT_ROOT / "packaging" / "arch" / "PKGBUILD").read_text()
RECIPES = {
    "packaging/rpm/eitaas-linux.spec": SPEC,
    "packaging/debian/rules": RULES,
    "packaging/arch/PKGBUILD": PKGBUILD,
}
MANIFEST = json.loads((PACKAGE_DIR / "sources.json").read_text())
CHANGELOG = (PROJECT_ROOT / "packaging" / "debian" / "changelog").read_text()
WORKFLOW = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text()
PYPROJECT = (PROJECT_ROOT / "pyproject.toml").read_text()


def project_version():
    """Return the version in pyproject.toml, the single package version stream."""
    match = re.search(r'(?m)^version = "([^"]+)"$', PYPROJECT)
    assert match, "unparsable pyproject version"
    return match.group(1)


def debian_version():
    """Return the version of the newest packaging/debian/changelog entry."""
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
        self.assertIn("PREFIX = /usr/lib/eitaas-remmina", RULES)
        self.assertIn("-DWITH_RDP_AUTH_AAD=ON", RULES)
        self.assertIn("-DWITH_PCSC=ON", RULES)
        self.assertIn("-DWITH_SSO_MIB=OFF", RULES)
        self.assertIn("--parallel 1", RULES)
        self.assertIn("override_dh_installdocs:", RULES)

    def test_bundle_source_preparation_reads_shared_manifest(self):
        preparer = (PROJECT_ROOT / "scripts" / "prepare-bundle-source.py").read_text()
        self.assertIn('"sources.json"', preparer)
        self.assertIn('manifest["patches"]', preparer)
        self.assertIn('metadata["sha256"]', preparer)
        self.assertIn('remmina_dir / "data" / "reports"', preparer)
        # Both formats that assemble a source tree share the one preparer.
        for script in ("build-deb.sh", "build-arch.sh", "build-rpm.sh"):
            with self.subTest(script=script):
                builder = (PROJECT_ROOT / "scripts" / script).read_text()
                self.assertIn("prepare-bundle-source.py", builder)

    def test_split_package_recipes_and_builders_are_gone(self):
        # One spec, one debian/ tree, one PKGBUILD, one builder per format.
        for relative in (
            "packaging/remmina/eitaas-remmina.spec",
            "packaging/remmina/debian",
            "packaging/remmina/arch",
            "packaging/debian/eitaas-linux-gui.install",
            "scripts/build-remmina-deb.sh",
            "scripts/build-remmina-arch.sh",
            "scripts/prepare-remmina-deb-source.py",
            "scripts/test-remmina-deb-lifecycle.sh",
            "scripts/test-remmina-arch-lifecycle.sh",
        ):
            with self.subTest(path=relative):
                self.assertFalse((PROJECT_ROOT / relative).exists())
        self.assertEqual(
            sorted(p.name for p in (PROJECT_ROOT / "packaging" / "rpm").glob("*.spec")),
            ["eitaas-linux.spec"],
        )

    def test_launcher_supports_rpm_and_debian_private_prefixes(self):
        launcher = (PACKAGE_DIR / "eitaas-remmina").read_text()
        self.assertIn("/usr/libexec/eitaas-remmina/bin/remmina", launcher)
        self.assertIn("/usr/lib/eitaas-remmina/bin/remmina", launcher)

    def test_native_arch_recipe_uses_private_prefix_and_embedded_auth(self):
        self.assertIn("_prefix='/usr/lib/eitaas-remmina'", PKGBUILD)
        self.assertIn("-DWITH_RDP_AUTH_AAD=ON", PKGBUILD)
        self.assertIn("-DWITH_PCSC=ON", PKGBUILD)
        self.assertIn("-DWITH_SSO_MIB=OFF", PKGBUILD)
        self.assertIn("--parallel 1", PKGBUILD)
        # The corresponding-source tarball is complete; nothing is downloaded
        # while the package builds.
        self.assertNotIn("https://github.com/FreeRDP", PKGBUILD)
        self.assertNotIn("https://gitlab.com/Remmina", PKGBUILD)

    def test_rpm_recipe_uses_private_prefix_and_embedded_auth(self):
        self.assertIn(
            "%global private_prefix %{_libexecdir}/eitaas-remmina", SPEC
        )
        self.assertIn("-DWITH_RDP_AUTH_AAD=ON", SPEC)
        self.assertIn("-DWITH_PCSC=ON", SPEC)
        self.assertIn("--parallel 1", SPEC)

    def test_arch_builder_derives_checksum_from_the_assembled_source(self):
        builder = (PROJECT_ROOT / "scripts" / "build-arch.sh").read_text()
        self.assertIn("prepare-bundle-source.py", builder)
        self.assertIn('sha256sum "$archive"', builder)
        self.assertIn("@SHA256@", builder)
        self.assertIn("sha256sums=('@SHA256@')", PKGBUILD)

    def test_sso_mib_is_disabled_in_every_recipe(self):
        # The identity-broker (SSO-MIB) route is not part of the product (#77):
        # the validated path is the embedded WebKitGTK smart-card WebView, so every
        # recipe builds FreeRDP and Remmina with the broker compiled out and
        # declares no sso-mib build or runtime dependency.
        for name, recipe in RECIPES.items():
            with self.subTest(recipe=name):
                # Both the FreeRDP and the Remmina configure lines opt out.
                self.assertEqual(recipe.count("-DWITH_SSO_MIB=OFF"), 2)
                self.assertNotIn("-DWITH_SSO_MIB=ON", recipe)
                self.assertNotIn("sso-mib", recipe.replace("-DWITH_SSO_MIB=OFF", ""))
                # Every recipe still builds the browser/smart-card authentication path.
                self.assertIn("-DWITH_RDP_AUTH_AAD=ON", recipe)
                self.assertIn("-DWITH_PCSC=ON", recipe)

    def test_freerdp_floor_and_tested_line_are_documented(self):
        # The patches bind FreeRDP_GatewayAvdScope/FreeRDP_GatewayAvdAccessAadFormat
        # (FreeRDP 3.16.0); the bundle pins and tests the 3.30 line.
        pinned = MANIFEST["sources"]["freerdp"]["version"]
        self.assertTrue(pinned.startswith("3.30."), pinned)
        for path in (
            PACKAGE_DIR / "README.md",
            PROJECT_ROOT / "docs" / "supported-platforms.md",
            UPSTREAM_DIR / "README.md",
        ):
            with self.subTest(document=path.name):
                text = path.read_text()
                self.assertIn("3.16", text)
                self.assertIn("3.30", text)
                self.assertNotIn("-DWITH_SSO_MIB=ON", text)
                self.assertNotIn("3.31.0 is", text)
                self.assertNotIn("3.31.0 or newer", text)

    def test_single_version_stream_is_derived_from_pyproject(self):
        """Issue #80: one package version stream, taken from pyproject.toml.

        The pinned Remmina and FreeRDP versions belong to sources.json and the
        notices; they are not part of the package version any more.
        """
        version = project_version()
        self.assertRegex(
            SPEC, rf"(?m)^Version:\s+{re.escape(version)}$"
        )
        release = re.search(r"(?m)^Release:\s+(\S+?)%\{\?dist\}$", SPEC)
        self.assertIsNotNone(release)
        self.assertRegex(release.group(1), r"^[1-9]\d*$")
        self.assertIn(f"- {version}-{release.group(1)}\n", SPEC.split("%changelog", 1)[1])

        # The Debian package is native: <project version>, no revision.
        self.assertEqual(debian_version(), version)
        self.assertIn(
            "3.0 (native)",
            (PROJECT_ROOT / "packaging" / "debian" / "source" / "format").read_text(),
        )

        self.assertIn(f"pkgver={version}\n", PKGBUILD)
        pkgrel = re.search(r"(?m)^pkgrel=(\S+)$", PKGBUILD)
        self.assertIsNotNone(pkgrel)
        self.assertRegex(pkgrel.group(1), r"^[1-9]\d*$")

        # The bundled Remmina version never becomes the package version.
        self.assertNotEqual(MANIFEST["package_version"], version)
        self.assertNotIn(f"Version:        {MANIFEST['package_version']}", SPEC)
        self.assertNotIn(f"pkgver={MANIFEST['package_version']}", PKGBUILD)

    def test_one_binary_package_named_eitaas_linux_per_distribution(self):
        self.assertRegex(SPEC, r"(?m)^Name:\s+eitaas-linux$")
        self.assertEqual(len(re.findall(r"(?m)^Name:\s", SPEC)), 1)
        self.assertNotIn("%package", SPEC)
        self.assertEqual(
            re.findall(r"(?m)^Package:\s*(\S+)$", CONTROL), ["eitaas-linux"]
        )
        self.assertIn("pkgname=eitaas-linux\n", PKGBUILD)
        self.assertNotIn("pkgbase=", PKGBUILD)

    def test_upgrade_path_from_the_split_packages_is_declared(self):
        version = project_version()
        superseded = ("eitaas-remmina", "eitaas-linux-gui")

        # RPM: every Provides sits at or above its Obsoletes bound so the
        # package can never obsolete itself.
        obsoletes = dict(re.findall(r"(?m)^Obsoletes:\s+(\S+) < (\S+)$", SPEC))
        provides = dict(re.findall(r"(?m)^Provides:\s+(\S+) = (\S+)$", SPEC))
        self.assertEqual(sorted(obsoletes), sorted(superseded))
        for name in superseded:
            with self.subTest(package=name):
                self.assertEqual(provides[name], obsoletes[name])
        self.assertEqual(obsoletes["eitaas-linux-gui"], "%{version}-%{release}")
        self.assertEqual(obsoletes["eitaas-remmina"], "%{remmina_version}-1")

        # DEB: Breaks + Replaces + Provides retire both names on upgrade.
        for field in ("Provides", "Breaks", "Replaces"):
            with self.subTest(field=field):
                declared = re.search(rf"(?m)^{field}: (.+)$", CONTROL)
                self.assertIsNotNone(declared)
                names = [
                    re.sub(r"\(.*\)", "", name).strip()
                    for name in declared.group(1).split(",")
                ]
                self.assertEqual(sorted(names), sorted(superseded))
        # The Provides carries this package's version so a versioned
        # dependency on either retired name still resolves.
        self.assertIn(
            "Provides: eitaas-remmina (= ${binary:Version}), "
            "eitaas-linux-gui (= ${binary:Version})",
            CONTROL,
        )

        # Arch: conflicts + replaces + provides.
        for field in ("provides", "conflicts", "replaces"):
            with self.subTest(field=field):
                declared = re.search(rf"(?m)^{field}=\((.+)\)$", PKGBUILD)
                self.assertIsNotNone(declared)
                self.assertEqual(
                    sorted(declared.group(1).replace("'", "").split()),
                    sorted(superseded),
                )

        # The lifecycle tests exercise the upgrade where the tooling allows it,
        # against the EVRs the retired packages really last shipped, so a
        # narrowed Obsoletes/Breaks bound fails the test instead of silently
        # stranding an installed system.
        deb = (PROJECT_ROOT / "scripts" / "test-deb-lifecycle.sh").read_text()
        rpm = (PROJECT_ROOT / "scripts" / "test-rpm-lifecycle.sh").read_text()
        for script, body in (("test-deb-lifecycle.sh", deb), ("test-rpm-lifecycle.sh", rpm)):
            with self.subTest(script=script):
                self.assertIn("is still installed after the upgrade", body)
                for name in ("eitaas-linux", *superseded):
                    self.assertIn(f"stub {name}", body)
        self.assertIn("LAST_EITAAS_LINUX=0.1.0-1", deb)
        self.assertIn("LAST_EITAAS_REMMINA=1.4.43+eitaas0.15", deb)
        self.assertIn("stub eitaas-linux 0.1.0 7", rpm)
        self.assertIn("stub eitaas-remmina 1.4.43 0.15", rpm)
        self.assertIn("stub eitaas-linux-gui 0.1.0 7", rpm)
        self.assertIn(str(version), CHANGELOG)

    def test_runtime_dependencies_are_consolidated_without_internal_recommends(self):
        """One Requires/Depends/depends set per distribution, no weak links.

        The GUI, the CLI, and the bundled client are one package now, so no
        recipe may depend on -- or recommend -- another package this project
        ships.
        """
        expectations = (
            (
                "packaging/rpm/eitaas-linux.spec",
                re.findall(r"(?m)^Requires:\s+(\S+)$", SPEC),
                ("python3-gobject", "gtk4", "libadwaita", "pcsc-lite",
                 "gnutls-utils", "opensc", "python3"),
            ),
            (
                "packaging/debian/control",
                [
                    name.strip()
                    for name in re.search(
                        r"(?s)\nDepends:\n(.+?)\nSuggests:", CONTROL
                    ).group(1).replace("\n", "").split(",")
                ],
                ("python3-gi", "gir1.2-gtk-4.0", "gir1.2-adw-1", "libpcsclite1",
                 "gnutls-bin", "opensc", "pcscd"),
            ),
            (
                "packaging/arch/PKGBUILD",
                re.search(
                    r"(?s)^depends=\((.+?)\)$", PKGBUILD, re.MULTILINE
                ).group(1).replace("'", "").split(),
                ("python-gobject", "gtk4", "libadwaita", "pcsclite",
                 "gnutls", "opensc", "python"),
            ),
        )
        for name, declared, required in expectations:
            with self.subTest(recipe=name):
                self.assertTrue(declared)
                for dependency in required:
                    self.assertIn(dependency, declared)
                # No dependency on a package this project ships.
                for ours in ("eitaas-remmina", "eitaas-linux-gui", "eitaas-linux"):
                    self.assertNotIn(ours, declared)
        self.assertNotIn("Recommends:", SPEC)
        self.assertNotIn("Recommends:", CONTROL)
        self.assertNotIn("optdepends=", PKGBUILD)

    def test_usb_redirection_ships_with_libusb_declared_everywhere(self):
        """USB device redirection is part of the product (owner decision).

        FreeRDP builds its urbdrc channel whenever libusb is present, so the
        payload is deterministic only if every recipe and package CI job
        declares the dependency. No recipe may set a CHANNEL_URBDRC flag in
        either direction; the declared dependency is the guarantee.
        """
        for name, recipe in RECIPES.items():
            with self.subTest(recipe=name):
                self.assertNotIn("CHANNEL_URBDRC", recipe)
                self.assertIn("-DWITH_PCSC=ON", recipe)
        # The dependency lives where each distro declares build inputs.
        self.assertIn("libusb1-devel", SPEC)
        self.assertIn("libusb-1.0-0-dev", CONTROL)
        self.assertIn("'libusb'", PKGBUILD)
        def job_section(name):
            body = WORKFLOW.split(f"  {name}:", 1)[1]
            # A job body ends where the next top-level job key begins.
            for marker in ("\n  deb-package:", "\n  rpm-package:",
                           "\n  arch-package:", "\n  remmina-upstream-series:"):
                body = body.split(marker, 1)[0]
            return body
        for job, token in (
            ("deb-package", "libusb-1.0-0-dev"),
            ("rpm-package", "libusb1-devel"),
            ("arch-package", " libusb"),
        ):
            with self.subTest(job=job, dependency=token.strip()):
                self.assertIn(token, job_section(job))

    def test_remmina_configure_flags_match_across_recipes(self):
        """One Remmina feature set, so the three payloads cannot drift apart."""
        flags = (
            "-DWITH_FREERDP3=ON", "-DWITH_RDP_AUTH_AAD=ON", "-DWITH_SSO_MIB=OFF",
            "-DWITH_GCRYPT=OFF", "-DWITH_VTE=OFF", "-DHAVE_LIBAPPINDICATOR=OFF",
            "-DWITH_CUPS=OFF", "-DWITH_AVAHI=OFF", "-DWITH_LIBVNCSERVER=OFF",
            "-DWITH_SPICE=OFF", "-DWITH_NEWS=OFF", "-DWITH_STATS=OFF",
            "-DWITH_TIP=OFF", "-DWITH_MANPAGES=OFF", "-DWITH_ICON_CACHE=OFF",
            "-DWITH_WWW=OFF", "-DWITH_GVNC=OFF", "-DWITH_X2GO=OFF",
            "-DWITH_KF5WALLET=OFF", "-DWITH_ST=OFF", "-DWITH_XDMCP=OFF",
            "-DWITH_NX=OFF", "-DWITH_PYTHONLIBS=OFF",
        )
        for name, recipe in RECIPES.items():
            for flag in flags:
                with self.subTest(recipe=name, flag=flag):
                    self.assertIn(flag, recipe)

    def test_every_recipe_ships_the_whole_product(self):
        """One package carries the private client, the CLI, and the GUI."""
        for name, recipe in RECIPES.items():
            with self.subTest(recipe=name):
                self.assertIn("eitaas-remmina", recipe)
                self.assertIn("org.eitaas.Helper.desktop", recipe)
                self.assertIn("org.eitaas.Helper.metainfo.xml", recipe)
                self.assertIn("eitaas-rdpw.xml", recipe)
                self.assertIn("org.eitaas.Helper-symbolic.svg", recipe)
                self.assertIn("docs/eitaas.1", recipe)
                self.assertIn("docs/eitaas-gui.1", recipe)
                self.assertIn("completions/eitaas.bash", recipe)
                self.assertIn("completions/_eitaas", recipe)
                self.assertIn("THIRD_PARTY_NOTICES.md", recipe)
                self.assertIn("sources.json", recipe)

    def test_build_scripts_and_ci_derive_versions_instead_of_hard_coding_them(self):
        builder = (PROJECT_ROOT / "scripts" / "build-deb.sh").read_text()
        lifecycle = (PROJECT_ROOT / "scripts" / "test-deb-lifecycle.sh").read_text()
        rpm_lifecycle = (PROJECT_ROOT / "scripts" / "test-rpm-lifecycle.sh").read_text()
        arch_builder = (PROJECT_ROOT / "scripts" / "build-arch.sh").read_text()

        self.assertIn("dpkg-parsechangelog", builder)
        self.assertIn('source_root="$build_root/eitaas-linux-$version"', builder)
        self.assertIn("dpkg-parsechangelog", WORKFLOW)
        self.assertIn("DEB_VERSION", WORKFLOW)
        # Debian artifact file names carry no epoch; both consumers strip one.
        self.assertIn("version=${version#*:}", builder)
        self.assertIn("DEB_VERSION=${deb_version#*:}", WORKFLOW)
        # The lifecycle scripts pin the retired packages' real last-shipped
        # EVRs on purpose (asserted separately), so they are exempt from the
        # bundled-Remmina-version rule below but not from the other pins.
        exempt = {
            "scripts/test-deb-lifecycle.sh",
            "scripts/test-rpm-lifecycle.sh",
        }
        # The RPM and Arch builders read the project version from pyproject.
        for name, script in (
            ("scripts/build-rpm.sh", (PROJECT_ROOT / "scripts" / "build-rpm.sh").read_text()),
            ("scripts/build-arch.sh", arch_builder),
        ):
            with self.subTest(script=name):
                self.assertIn('"$project_root/pyproject.toml"', script)
                self.assertIn("version = ", script)

        pinned = {
            "project version": project_version(),
            "bundled remmina version": MANIFEST["package_version"],
            "freerdp version": MANIFEST["sources"]["freerdp"]["version"],
            "remmina commit": MANIFEST["sources"]["remmina"]["commit"],
        }
        consumers = {
            "scripts/build-deb.sh": executable_lines(builder),
            "scripts/build-arch.sh": executable_lines(arch_builder),
            "scripts/build-rpm.sh": executable_lines(
                (PROJECT_ROOT / "scripts" / "build-rpm.sh").read_text()
            ),
            "scripts/test-deb-lifecycle.sh": executable_lines(lifecycle),
            "scripts/test-rpm-lifecycle.sh": executable_lines(rpm_lifecycle),
            "scripts/test-arch-lifecycle.sh": executable_lines(
                (PROJECT_ROOT / "scripts" / "test-arch-lifecycle.sh").read_text()
            ),
            ".github/workflows/ci.yml": executable_lines(WORKFLOW),
            "packaging/debian/rules": executable_lines(RULES),
        }
        for label, value in pinned.items():
            for name, consumer in consumers.items():
                if label == "bundled remmina version" and name in exempt:
                    continue
                with self.subTest(pinned=label, consumer=name):
                    self.assertNotIn(value, consumer)
    def test_pinned_manifest_matches_rpm_spec(self):
        freerdp = MANIFEST["sources"]["freerdp"]
        remmina = MANIFEST["sources"]["remmina"]
        self.assertIn(f"%global freerdp_version {freerdp['version']}", SPEC)
        self.assertIn(f"%global remmina_version {MANIFEST['package_version']}", SPEC)
        self.assertIn(f"%global remmina_commit {remmina['commit']}", SPEC)
        self.assertIn(f"Source1:        {freerdp['url']}".replace(
            freerdp["version"], "%{freerdp_version}"), SPEC)
        self.assertIn("Remmina-%{remmina_commit}.tar.gz", SPEC)

    def test_no_recipe_repeats_the_ordered_patch_series(self):
        """sources.json owns the series; each recipe reads it or is fed by it."""
        for name, recipe in RECIPES.items():
            with self.subTest(recipe=name):
                for patch in MANIFEST["patches"]:
                    self.assertNotIn(patch, recipe)
        self.assertNotIn("Patch0:", SPEC)
        # The RPM applies the manifest's series in %prep.
        prep = SPEC.split("%prep", 1)[1].split("%build", 1)[0]
        self.assertIn('["patches"]', prep)
        self.assertIn('patch --fuzz=0 -p1 -d "$remmina"', prep)
        # DEB and Arch consume a source tree the preparer already patched.
        preparer = (PROJECT_ROOT / "scripts" / "prepare-bundle-source.py").read_text()
        self.assertIn('["patch", "--fuzz=0", "-p1", "-d", str(remmina_dir)]', preparer)

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
        plugin_sources = tuple(MANIFEST["downstream_sources"][:2])
        for filename in (*plugin_sources, "eitaas-remmina"):
            with self.subTest(filename=filename):
                beginning = (PACKAGE_DIR / filename).read_text().splitlines()[:4]
                identifier = "GPL-2.0-or-later" if filename in plugin_sources else "MIT"
                self.assertTrue(
                    any(f"SPDX-License-Identifier: {identifier}" in line for line in beginning)
                )
                self.assertTrue(any("Copyright (c) 2026 Stephen Trotter" in line for line in beginning))

    def test_downstream_patches_declare_their_license(self):
        patches = sorted(PACKAGE_DIR.glob("*.patch"))
        self.assertEqual(len(patches), 7)
        for patch in patches:
            with self.subTest(patch=patch.name):
                self.assertIn("License: GPL-2.0-or-later", patch.read_text().split("---", 1)[0])

    def test_smartcard_authentication_is_origin_bound_and_nonpersistent(self):
        source = (PACKAGE_DIR / "eitaas_smartcard_auth.c").read_text()
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
        source = (PACKAGE_DIR / "eitaas_smartcard_auth.c").read_text()
        for required in (
            "#define REMMINA_P11TOOL",
            "g_file_test(REMMINA_P11TOOL, G_FILE_TEST_IS_EXECUTABLE)",
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
        # Every recipe pins the tool this build runs; the PATH lookup exists
        # for a build that does not pin one, and never overrides a pinned path.
        for name, recipe in (("spec", SPEC), ("rules", RULES), ("PKGBUILD", PKGBUILD)):
            with self.subTest(recipe=name):
                self.assertIn("-DREMMINA_P11TOOL=/usr/bin/p11tool", recipe)

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
        upstream = (UPSTREAM_DIR / "0004-RDP-bind-and-own-OAuth-callback-results.patch").read_text()
        helpers = []
        for patch in (downstream, upstream):
            added = self._added_web_auth_lines(patch)
            start = added.index("#define OAUTH_TRANSACTION_TIMEOUT (5 * G_TIME_SPAN_MINUTE)")
            close = added.index("static void oauth_transaction_close(RemminaOAuthTransaction *transaction)")
            end = added.index("}", close)
            # The upstream series is formatted with Remmina's uncrustify profile
            # (tab alignment); compare tokens, not whitespace.
            helpers.append(["".join(line.split()) for line in added[start:end + 1] if line.strip()])
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
        source = (PACKAGE_DIR / "eitaas_smartcard_auth.c").read_text()
        for required in (
            "load_certificate_async",
            "certificate_load_thread",
            "g_task_run_in_thread",
            "rdp-certificate-transaction",
            "webkit_authentication_request_is_retry",
            "G_TIME_SPAN_MINUTE",
        ):
            self.assertIn(required, source)

    def test_challenge_host_relationship_is_defined_once_in_both_trees(self):
        downstream = (PACKAGE_DIR / "eitaas_smartcard_auth.c").read_text()
        upstream = (UPSTREAM_DIR / "0005-RDP-handle-PKCS11-client-certificates-in-WebKit.patch").read_text()
        for source in (downstream, upstream):
            self.assertEqual(source.count('#define CERTAUTH_HOST_PREFIX "certauth."'), 1)
            self.assertIn("host_is_authority_or_certauth(host, authority)", source)
            self.assertIn("g_strconcat(CERTAUTH_HOST_PREFIX, authority, NULL)", source)
            self.assertNotIn("g_str_has_suffix(host", source)
            self.assertNotIn("strstr(host", source)
        self.assertNotIn("microsoftonline", downstream)

    def test_toplevel_is_held_across_nested_certificate_dialogs(self):
        downstream = (PACKAGE_DIR / "eitaas_smartcard_auth.c").read_text()
        upstream = (UPSTREAM_DIR / "0005-RDP-handle-PKCS11-client-certificates-in-WebKit.patch").read_text()
        for source in (downstream, upstream):
            self.assertIn("auth_toplevel_hold(&toplevel, parent_data)", source)
            self.assertIn('g_signal_connect(toplevel->held, "destroy"', source)
            self.assertNotIn("GtkWindow *parent = GTK_WINDOW(parent_data)", source)
            self.assertIn("Loading the smart-card certificate timed out", source)
            self.assertIn("load->abandoned = abandoned", source)
        handler = downstream[downstream.index("gboolean eitaas_webview_authenticate("):]
        self.assertEqual(
            handler.count("auth_toplevel_release(&toplevel)"),
            handler.count("return TRUE;"),
        )

    def test_certauth_host_matching_is_exact(self):
        cc = shutil.which("cc")
        pkg_config = shutil.which("pkg-config")
        if not cc or not pkg_config:
            reason = "SKIP: tests/c/test_smartcard_challenge_host.c not compiled because cc or pkg-config is missing"
            print(reason, file=sys.stderr)
            self.skipTest(reason)
        module = next(
            (
                name
                for name in ("webkit2gtk-4.1", "webkit2gtk-4.0")
                if subprocess.run([pkg_config, "--exists", name]).returncode == 0
            ),
            None,
        )
        if module is None:
            reason = (
                "SKIP: tests/c/test_smartcard_challenge_host.c not compiled because no "
                "webkit2gtk-4.1 or webkit2gtk-4.0 pkg-config module was found"
            )
            print(reason, file=sys.stderr)
            self.skipTest(reason)
        flags = subprocess.run(
            [pkg_config, "--cflags", "--libs", module],
            check=True, capture_output=True, text=True,
        ).stdout.split()
        harness = PROJECT_ROOT / "tests" / "c" / "test_smartcard_challenge_host.c"
        with tempfile.TemporaryDirectory() as workdir:
            binary = Path(workdir) / "test_smartcard_challenge_host"
            subprocess.run(
                [cc, "-std=gnu11", "-Wall", "-Werror", str(harness), "-o", str(binary), *flags],
                check=True, timeout=120,
            )
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_spec_declares_the_repository_and_both_upstream_archives(self):
        declared = re.findall(r"^Source\d+:\s+(\S+)", SPEC, re.MULTILINE)
        self.assertEqual(len(declared), 3)
        self.assertTrue(all(url.startswith("https://") for url in declared), declared)
        self.assertIn("EITaaS-Linux/archive", declared[0])
        self.assertIn("FreeRDP", declared[1])
        self.assertIn("Remmina", declared[2])

    def test_spec_consumes_every_downstream_input_from_the_repository_source(self):
        # The repository tarball is Source0, so the smart-card integration,
        # launcher, notices, and manifest are referenced by path, not as SourceN.
        plugin_sources = tuple(MANIFEST["downstream_sources"][:2])
        for filename in (*plugin_sources, "eitaas-remmina", "THIRD_PARTY_NOTICES.md"):
            with self.subTest(filename=filename):
                self.assertIn(f"packaging/remmina/{filename}", SPEC)
        self.assertIn("%global manifest packaging/remmina/sources.json", SPEC)
        self.assertIn("install -Dpm 0644 LICENSE ", SPEC)

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
            MANIFEST["sources"]["freerdp"]["version"],
            "030946c83fe1b7218a21b6d32f9c975b243b7031",
            "Remmina",
            "FreeRDP",
            "smart card (PIV) integration",
            "one-shot launcher",
        ):
            with self.subTest(value=value):
                self.assertIn(value, notice)

        self.assertIn("copyright 2026 Stephen Trotter", " ".join(notice.split()))
        self.assertIn("developed with AI assistance", notice)


class ArmGatewayTimeoutTests(unittest.TestCase):
    """Issue #84: the ARM gateway response wait is extended in both trees."""

    DOWNSTREAM = "0007-extend-arm-configuration-timeout.patch"
    UPSTREAM = "0006-RDP-extend-ARM-gateway-response-timeout.patch"

    @classmethod
    def setUpClass(cls):
        cls.downstream = (PACKAGE_DIR / cls.DOWNSTREAM).read_text()
        cls.upstream = (UPSTREAM_DIR / cls.UPSTREAM).read_text()

    @staticmethod
    def _added_lines(patch):
        return [
            line[1:]
            for line in patch.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        ]

    def test_patch_is_registered_in_the_manifest_series(self):
        # sources.json is the only registry; every recipe applies that series.
        self.assertEqual(MANIFEST["patches"][-1], self.DOWNSTREAM)
        self.assertTrue((PACKAGE_DIR / self.DOWNSTREAM).is_file())

    def test_profile_timeout_reaches_both_tcp_timeouts(self):
        # Remmina applied the profile "timeout" only to FreeRDP_TcpAckTimeout;
        # gateway responses are read under FreeRDP_TcpConnectTimeout.
        for name, patch in (("downstream", self.downstream), ("upstream", self.upstream)):
            with self.subTest(tree=name):
                added = "\n".join(self._added_lines(patch))
                self.assertIn("FreeRDP_TcpConnectTimeout, (UINT32)val", added)

    def test_arm_default_applies_only_without_a_profile_timeout(self):
        for name, patch in (("downstream", self.downstream), ("upstream", self.upstream)):
            with self.subTest(tree=name):
                added = "\n".join(self._added_lines(patch))
                self.assertIn("#define ARM_GATEWAY_RESPONSE_TIMEOUT 60000u", added)
                self.assertIn("#ifdef WITH_RDP_AUTH_AAD", added)
                self.assertIn("cs == NULL || cs[0] == '\\0'", added)
                self.assertIn("FreeRDP_GatewayArmTransport", added)
                self.assertIn("< ARM_GATEWAY_RESPONSE_TIMEOUT", added)
                self.assertIn(
                    'REMMINA_PLUGIN_DEBUG("avd-arm: response-timeout-ms=%u", ARM_GATEWAY_RESPONSE_TIMEOUT)',
                    added,
                )

    def test_downstream_and_upstream_changes_are_equivalent(self):
        down = ["".join(l.split()) for l in self._added_lines(self.downstream) if l.strip()]
        up = ["".join(l.split()) for l in self._added_lines(self.upstream) if l.strip()]
        self.assertEqual(down, up)

    def test_launcher_never_raises_the_freerdp_log_level(self):
        # At DEBUG, com.freerdp.utils.http logs the full OAuth token request
        # body and the full token-endpoint response (access, refresh, and id
        # tokens). The timeout evidence this fix needs is already an ERROR
        # ("timeout [<n>ms] exceeded", com.freerdp.core.gateway.http), so the
        # launcher must leave WinPR at its default INFO level.
        launcher = (PACKAGE_DIR / "eitaas-remmina").read_text()
        for line in launcher.splitlines():
            if line.lstrip().startswith("#"):
                continue
            self.assertNotIn("WLOG_LEVEL", line, line)
            self.assertNotIn("WLOG_FILTER", line, line)

    def test_arm_reason_line_is_documented(self):
        for path in (
            PROJECT_ROOT / "README.md",
            PACKAGE_DIR / "README.md",
            PROJECT_ROOT / "docs" / "eitaas.1",
        ):
            with self.subTest(path=str(path.relative_to(PROJECT_ROOT))):
                self.assertIn("avd-arm: response-timeout-ms=60000", path.read_text())


class RemminaUpstreamSeriesTests(unittest.TestCase):
    """Structural guarantees for the generic series in upstream/remmina."""

    REMMINA_BASE = "c620366ed85def5c3de2549eec7fcbef577281d8"

    @classmethod
    def setUpClass(cls):
        cls.patches = sorted(UPSTREAM_DIR.glob("*.patch"))
        cls.texts = {patch.name: patch.read_text() for patch in cls.patches}

    def test_every_patch_is_exported_from_a_real_commit(self):
        for patch in self.patches:
            with self.subTest(patch=patch.name):
                header = self.texts[patch.name].splitlines()[0]
                match = re.fullmatch(r"From ([0-9a-f]{40}) Mon Sep 17 00:00:00 2001", header)
                self.assertIsNotNone(match, header)
                self.assertNotEqual(match.group(1), "0" * 40)

    def test_patch_numbering_is_contiguous_and_matches_file_names(self):
        self.assertGreater(len(self.patches), 0)
        total = len(self.patches)
        for index, patch in enumerate(self.patches, start=1):
            with self.subTest(patch=patch.name):
                self.assertTrue(patch.name.startswith(f"{index:04d}-RDP-"))
                subject = re.search(r"^Subject: \[PATCH (\d+)/(\d+)\] (.+)$", self.texts[patch.name], re.MULTILINE)
                self.assertIsNotNone(subject)
                self.assertEqual((int(subject.group(1)), int(subject.group(2))), (index, total))
                self.assertTrue(subject.group(3).startswith("RDP: "))

    def test_every_commit_explains_why_and_discloses_ai_assistance(self):
        for patch in self.patches:
            with self.subTest(patch=patch.name):
                body = self.texts[patch.name].split("\n---\n", 1)[0]
                body = body.split("\n\n", 1)[1]
                self.assertGreater(len(body.split()), 40, "commit body must explain the change")
                self.assertIn("AI assistance", body)
                self.assertIn("Tested with FreeRDP 3.30.0", body)
                self.assertIn("FreeRDP 3.16.0 or", body)
                self.assertNotIn("SSO-MIB", body)

    # Outside plugins/rdp/ the series may only register what the plugin needs:
    # the .rdpw file association, the two new sources for translation, and the
    # opt-in test build. Widen this deliberately.
    ALLOWED_OUTSIDE_THE_PLUGIN = {
        "data/desktop/org.remmina.Remmina-mime.xml",
        "po/POTFILES.in",
        "CMakeLists.txt",
    }

    def test_series_touches_only_the_rdp_plugin(self):
        for patch in self.patches:
            with self.subTest(patch=patch.name):
                for path in re.findall(r"^\+\+\+ b/(\S+)$", self.texts[patch.name], re.MULTILINE):
                    if path in self.ALLOWED_OUTSIDE_THE_PLUGIN:
                        continue
                    self.assertTrue(path.startswith("plugins/rdp/"), path)

    def test_rdpw_files_are_associated_with_remmina(self):
        """Issue #79: a downloaded .rdpw opens with Remmina from a file manager."""
        mime = self.texts["0001-RDP-preserve-protected-RDPW-settings.patch"]
        self.assertIn("+++ b/data/desktop/org.remmina.Remmina-mime.xml", mime)
        for glob in ('+        <glob pattern="*.rdpw"/>', '+        <glob pattern="*.RDPW"/>'):
            self.assertIn(glob, mime)

    def test_import_rejects_arm_without_a_gateway(self):
        """Issue #79: an ARM profile that names no gateway is not an AVD file."""
        first = self.texts["0001-RDP-preserve-protected-RDPW-settings.patch"]
        self.assertIn("REMMINA_RDPW_AVD_WITHOUT_GATEWAY", first)
        self.assertIn("not an Azure Virtual Desktop connection file", first)

    def test_a_build_without_aad_refuses_to_connect_an_avd_profile(self):
        """Issue #79: import may succeed, connecting says why it cannot."""
        first = self.texts["0001-RDP-preserve-protected-RDPW-settings.patch"]
        self.assertIn("+#ifndef WITH_RDP_AUTH_AAD", first)
        self.assertIn("lacks Azure AD support", first)

    def test_invalid_profile_content_never_aborts_remmina(self):
        """REMMINA_PLUGIN_ERROR calls g_error(): untrusted content must not reach it."""
        added = "\n".join(line for text in self.texts.values() for line in text.splitlines()
                          if line.startswith("+") and not line.startswith("+++"))
        self.assertNotIn("REMMINA_PLUGIN_ERROR", added)

    def test_new_user_visible_strings_are_translatable(self):
        """Issue #79: both new sources are listed for translation."""
        joined = "\n".join(self.texts.values())
        for source in ("plugins/rdp/rdp_web_auth.c", "plugins/rdp/rdp_web_auth_pkcs11.c"):
            self.assertIn(f"+{source}", joined)
        pkcs11 = self.texts["0005-RDP-handle-PKCS11-client-certificates-in-WebKit.patch"]
        for dialog in ("Reading smart card", "Select client certificate for %s",
                       "Client certificate PIN for %s"):
            self.assertIn(f'_("{dialog}")', pkcs11)

    def test_cloud_constants_live_in_one_table(self):
        """Issue #79: one authority/scope/redirect table serves selection and validation."""
        joined = "\n".join(self.texts.values())
        self.assertEqual(joined.count("static inline const RemminaAvdCloud *remmina_avd_clouds("), 1)
        for constant in ("https%3A%2F%2Fwww.wvd.azure.us%2F.default",
                         "https%3A%2F%2Fwww.wvd.microsoft.com%2F.default",
                         "login.microsoftonline.us\"",
                         "REMMINA_AVD_REDIRECT_DYNAMIC \""):
            added = [line for line in joined.splitlines()
                     if line.startswith("+") and constant in line]
            self.assertEqual(len(added), 1, constant)

    def test_the_series_ships_a_ctest_for_the_rdpw_helpers(self):
        """Issue #79: the allowlist and import helpers are exercised by a test."""
        tests = self.texts["0007-RDP-test-the-protected-connection-file-helpers.patch"]
        self.assertIn("+++ b/plugins/rdp/test/test_rdp_rdpw.c", tests)
        self.assertIn("+++ b/plugins/rdp/test/synthetic-avd.rdpw", tests)
        self.assertIn("add_test(NAME rdp-rdpw", tests)
        self.assertIn("if(BUILD_TESTING)", tests)
        self.assertNotRegex(tests, r"(?i)eitaas")

    def test_series_carries_no_downstream_branding(self):
        for patch in self.patches:
            with self.subTest(patch=patch.name):
                self.assertNotRegex(self.texts[patch.name], r"(?i)eitaas")

    def test_later_patches_do_not_touch_up_earlier_ones(self):
        # The series is squashed: the OAuth transaction and scope handling
        # are each introduced once, and the token path never carries the
        # hard-coded commercial scope that the settings lookup replaced.
        added = {name: "\n".join(l[1:] for l in text.splitlines() if l.startswith("+") and not l.startswith("+++"))
                 for name, text in self.texts.items()}
        joined = "\n".join(added.values())
        self.assertEqual(joined.count("#define OAUTH_TRANSACTION_TIMEOUT"), 1)
        self.assertEqual(joined.count("static BOOL avd_oauth_settings_are_safe("), 1)
        self.assertEqual(joined.count("gsize *filtered_length)\n{"), 1)
        self.assertNotIn('scope = "https%3A%2F%2Fwww.wvd.microsoft.com%2F.default";', joined)
        removed = "\n".join(l[1:] for text in self.texts.values() for l in text.splitlines()
                            if l.startswith("-") and not l.startswith("---"))
        for symbol in ("rdpw_path", "rdpw_sha256", "OAUTH_TRANSACTION_TIMEOUT", "oauth_transaction_"):
            self.assertNotIn(symbol, removed, f"{symbol} is introduced and then reworked within the series")

    def test_readme_documents_the_base_commit_and_git_am(self):
        readme = (UPSTREAM_DIR / "README.md").read_text()
        self.assertIn(self.REMMINA_BASE, readme)
        self.assertIn(f"git checkout {self.REMMINA_BASE}\ngit am /path/to/EITaaS-Linux/upstream/remmina/*.patch", readme)
        for patch in self.patches:
            self.assertIn(patch.name, readme)
        self.assertIn("tested with FreeRDP 3.30.0", readme)
        self.assertIn("FreeRDP 3.16.0", readme)

    def test_ci_applies_and_builds_the_series_on_the_pinned_base(self):
        self.assertIn("remmina-upstream-series:", WORKFLOW)
        job = WORKFLOW.split("remmina-upstream-series:", 1)[1]
        self.assertIn(self.REMMINA_BASE, job)
        self.assertIn("git am", job)
        self.assertIn("-DWITH_RDP_AUTH_AAD=$1", job)
        self.assertIn("rev-list --reverse", job)
        self.assertIn("build ON", job)
        self.assertIn("build OFF", job)
        self.assertIn("--target remmina-plugin-rdp", job)
        self.assertIn("-DBUILD_TESTING=ON", job)
        self.assertIn("ctest --test-dir remmina-build-test", job)
        # Remmina's find_suggested_package() is fatal unless WITH_<PKG>=OFF.
        for flag in ("-DWITH_AVAHI=OFF", "-DWITH_CUPS=OFF", "-DWITH_PYTHONLIBS=OFF"):
            self.assertIn(flag, job)


class RemminaSpecCheckTests(unittest.TestCase):
    def test_recipe_check_literals_exist_in_final_downstream_sources(self):
        """Every string a recipe's build-time check greps out of the built plugin must
        be introduced by the final patch series or the downstream sources, or the
        package cannot build."""
        literals = []
        for name, recipe in (
            ("packaging/rpm/eitaas-linux.spec", SPEC.split("%check", 1)[1]),
            ("packaging/debian/rules", RULES),
            ("packaging/arch/PKGBUILD", PKGBUILD),
        ):
            found = re.findall(r"grep -a -q '([^']+)'", recipe)
            self.assertTrue(found, f"expected build-check grep literals in {name}")
            literals.extend(found)
        # The same two plugin strings are verified by every format.
        self.assertEqual(len(set(literals)), 2, sorted(set(literals)))
        self.assertEqual(len(literals), 6, literals)
        added_lines = []
        for filename in MANIFEST["patches"]:
            for line in (PACKAGE_DIR / filename).read_text(errors="replace").splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    added_lines.append(line[1:])
        for filename in MANIFEST["downstream_sources"]:
            added_lines.extend((PACKAGE_DIR / filename).read_text(errors="replace").splitlines())
        removed_lines = [
            line[1:]
            for filename in MANIFEST["patches"]
            for line in (PACKAGE_DIR / filename).read_text(errors="replace").splitlines()
            if line.startswith("-") and not line.startswith("---")
        ]
        for literal in literals:
            with self.subTest(literal=literal):
                introduced = [line for line in added_lines if literal in line]
                self.assertTrue(introduced, f"{literal!r} is not introduced by any patch or source")
                # A later patch must not remove the last introduction of the literal.
                self.assertGreaterEqual(
                    len(introduced),
                    len([line for line in removed_lines if literal in line]) + 1,
                    f"{literal!r} is removed by a later patch",
                )


class SmartcardDiagnosticsTests(unittest.TestCase):
    """Issue #82: both trees log every stage with the same stable reason codes."""

    REASON_CODES = (
        "challenge-received",
        "challenge-accepted",
        "origin-rejected",
        "discovery-start",
        "discovery-finished",
        "discovery-busy",
        "discovery-empty",
        "discovery-timeout",
        "discovery-cancelled",
        "discovery-token-empty",
        "discovery-token-skipped-trust",
        "certificate-selected",
        "certificate-submitted",
        "selection-cancelled",
        "load-start",
        "load-finished",
        "load-timeout",
        "load-error",
        "load-cancelled",
        "pin-requested",
        "pin-submitted",
        "pin-rejected",
        "pin-cancelled",
    )

    @classmethod
    def setUpClass(cls):
        cls.downstream = (PACKAGE_DIR / "eitaas_smartcard_auth.c").read_text()
        cls.upstream = (UPSTREAM_DIR / "0005-RDP-handle-PKCS11-client-certificates-in-WebKit.patch").read_text()

    def test_reason_codes_exist_in_both_trees(self):
        for source in (self.downstream, self.upstream):
            self.assertIn('#define SMARTCARD_AUTH_LOG "smartcard-auth: "', source)
            for code in self.REASON_CODES:
                with self.subTest(code=code):
                    self.assertIn(f'"{code}', source)
            # Dialogs and warnings share one code: show_error takes it explicitly.
            self.assertIn("static void show_error(", source)
            self.assertIn("const gchar *code, const gchar *message)", source)
            self.assertIn("REMMINA_PLUGIN_WARNING(SMARTCARD_AUTH_LOG", source)
            self.assertIn("REMMINA_PLUGIN_DEBUG(SMARTCARD_AUTH_LOG", source)
            # Loader errors are cut before any embedded PKCS #11 URI.
            self.assertIn('strstr(message, "pkcs11:")', source)

    def test_only_counts_and_hosts_are_formatted_into_log_lines(self):
        for source in (self.downstream, self.upstream):
            for line in source.splitlines():
                if "SMARTCARD_AUTH_LOG" not in line:
                    continue
                for forbidden in ("label", "certificate_uri", "private_key_uri", "gtk_entry_get_text", "uri)"):
                    self.assertNotIn(forbidden, line, line)

    def test_downstream_logs_label_filter_counts_and_application_id(self):
        self.assertIn("label-filter kept=%u dropped=%u", self.downstream)
        self.assertIn("stats->dropped++", self.downstream)
        self.assertIn("g_application_get_is_remote", self.downstream)
        self.assertIn("oneshot-quit", self.downstream)
        self.assertNotIn("label-filter", self.upstream)

    def test_label_filter_keeps_opensc_piv_authentication_labels(self):
        """OpenSC's PIV emulation labels (pkcs15-piv.c) must pass the downstream filter."""
        match = re.search(r"static gboolean authentication_label\(const gchar \*label\)\n\{(.*?)\n\}", self.downstream, re.S)
        self.assertIsNotNone(match)
        needles = re.findall(r'strstr\(lower, "([^"]+)"\)', match.group(1))
        self.assertTrue(needles)

        def kept(label):
            return any(needle in label.lower() for needle in needles)

        self.assertTrue(kept("Certificate for PIV Authentication"))
        self.assertTrue(kept("Certificate for Card Authentication"))
        self.assertFalse(kept("Certificate for Digital Signature"))
        self.assertFalse(kept("Certificate for Key Management"))
        self.assertFalse(kept("Retired Certificate for Key Management 1"))

    def test_discovery_tolerates_empty_tokens_in_both_trees(self):
        for source in (self.downstream, self.upstream):
            self.assertNotIn("g_subprocess_wait_check", source)
            self.assertIn('#define PKCS11_TRUST_MODEL "p11-kit-trust"', source)
            self.assertIn("stats->empty_tokens++", source)
            self.assertIn("stats->trust_skipped++", source)
            # A token whose listing exits non-zero without printing a URL is
            # empty; a non-zero status and a tool killed by a signal stay
            # fatal. The message wording differs between the trees because the
            # upstream strings are translated; the reported status does not.
            self.assertIn("if (certs->len == 0) {", source)
            self.assertIn("status < 0", source)
            self.assertEqual(source.count("(exit status %d)"), 2)

    def test_p11tool_is_resolved_at_run_time_in_both_trees(self):
        """Issue #79: no hard-coded /usr/bin/p11tool, and a clear error when absent."""
        for source in (self.downstream, self.upstream):
            self.assertIn('g_find_program_in_path("p11tool")', source)
            self.assertIn("#define REMMINA_P11TOOL", source)
            # the diff body, so a commit message may still name the old path
            self.assertNotIn('"/usr/bin/p11tool"', source.split("\n---\n", 1)[-1])
            self.assertIn("discovery-tool-missing", source)
            self.assertIn("gnutls-bin or gnutls-utils", source)

    def test_discovery_against_a_fake_p11tool(self):
        """Compile the discovery harness with a scratch shell script as REMMINA_P11TOOL."""
        cc = shutil.which("cc")
        pkg_config = shutil.which("pkg-config")
        if not cc or not pkg_config:
            self.skipTest("cc or pkg-config missing")
        module = next(
            (name for name in ("webkit2gtk-4.1", "webkit2gtk-4.0")
             if subprocess.run([pkg_config, "--exists", name]).returncode == 0),
            None,
        )
        if module is None:
            self.skipTest("no webkit2gtk pkg-config module")
        flags = subprocess.run([pkg_config, "--cflags", "--libs", module],
                               check=True, capture_output=True, text=True).stdout.split()
        harness = PROJECT_ROOT / "tests" / "c" / "test_pkcs11_discovery.c"
        with tempfile.TemporaryDirectory() as workdir:
            tool = Path(workdir) / "p11tool"
            shutil.copy(PROJECT_ROOT / "tests" / "c" / "fake-p11tool.sh", tool)
            tool.chmod(0o700)
            binary = Path(workdir) / "test_pkcs11_discovery"
            subprocess.run(
                [cc, "-std=gnu11", "-Wall", "-Werror", f'-DREMMINA_P11TOOL="{tool}"',
                 str(harness), "-o", str(binary), *flags],
                check=True, timeout=120,
            )
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_launcher_uses_a_private_gapplication_id(self):
        launcher = (PACKAGE_DIR / "eitaas-remmina").read_text()
        self.assertIn("--gapplication-app-id=org.eitaas.Remmina --no-tray-icon --connect=", launcher)
        self.assertIn("does not share an application id", (PACKAGE_DIR / "README.md").read_text())

    def test_reason_codes_are_documented(self):
        for path in (PROJECT_ROOT / "README.md", PROJECT_ROOT / "docs" / "eitaas.1", PROJECT_ROOT / "docs" / "eitaas-gui.1"):
            with self.subTest(path=path.name):
                self.assertIn("smartcard-auth", path.read_text())
        self.assertIn("G_MESSAGES_DEBUG=remmina eitaas-remmina", (PROJECT_ROOT / "README.md").read_text())


if __name__ == "__main__":
    unittest.main()
