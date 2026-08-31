# Manual release checklist

## Version scheme

`pyproject.toml` holds the **canonical** version and is the only place a bump is
authored. It is a PEP 440 string in one of two shapes: `X.Y.Z` for a final
release, or `X.Y.Z(a|b|rc)N` for a pre-release. Anything else (an epoch,
`.devN`, `.postN`, a local version) is rejected by
`scripts/check-version-consistency.py`, which owns the mapping below.

| Declaration | Spelling | `1.0.0rc1` | `1.0.0` |
| --- | --- | --- | --- |
| `pyproject.toml`, `src/eitaas/__init__.py` | canonical | `1.0.0rc1` | `1.0.0` |
| `docs/eitaas.1`, `docs/eitaas-gui.1` | canonical | `1.0.0rc1` | `1.0.0` |
| AppStream `<release version=>` | canonical | `1.0.0rc1` | `1.0.0` |
| git tag | `v` + canonical | `v1.0.0rc1` | `v1.0.0` |
| `packaging/arch/PKGBUILD` `pkgver=` | canonical | `1.0.0rc1` | `1.0.0` |
| RPM `%global upstream_version` | canonical | `1.0.0rc1` | `1.0.0` |
| RPM `Version:` and its `%changelog` | native | `1.0.0~rc1` | `1.0.0` |
| `packaging/debian/changelog` (native package, no revision) | native | `1.0.0~rc1` | `1.0.0` |

**The `~` rule.** rpm and dpkg both sort a `~` segment *below* the bare
version, so `1.0.0~rc1 < 1.0.0` and the eventual final release upgrades over
its candidates without an `Epoch:`. `~` is invalid in a PEP 440 version and in
an Arch `pkgver`, so those two keep the canonical spelling. For a final
release the canonical and native strings are identical, so one string appears
everywhere and this whole distinction disappears.

**The Arch guarantee.** pacman's `vercmp` sorts an alphabetic suffix below the
bare version on its own — `vercmp 1.0.0rc1 1.0.0` is negative — so Arch needs
no marker and no `epoch=`. That is not documentation to trust: it is asserted
against a real `vercmp` by `scripts/test-arch-lifecycle.sh`, which runs in the
Arch CI container on every pre-release build.

**The RPM tarball name.** The release tarball and its top-level directory are
named after the *tag*, so the spec's `Source0` and `%setup -n` use
`%{upstream_version}`, not `%{version}`. Keep them that way.

Bumping a version means editing the canonical string in every canonical-spelling
file, the native string in the RPM `Version:`/`%changelog` and the Debian
changelog, and then running `scripts/check-version-consistency.py`.

## Checks

Do not use real profiles, account identifiers, callback URLs, or smart-card
output as public test evidence.

- Confirm Azure US Government initial authentication with an authorized test account.
- Confirm authentication uses the embedded WebView and never
  emits or requests an authorization URL, callback URL, code, or token.
- Confirm smart card (PIV) authentication is passed into the desktop.
- Run `certutil -scinfo` inside the Windows session.
- Test card removal and reinsertion, disconnect, and reconnect.
- Test GNOME Wayland/XWayland, KDE Wayland/XWayland, and an X11 session.
- Exercise the bundled client under X11 and XWayland sessions that are claimed as supported.
- Verify server certificate validation remains enabled.
- Verify clipboard redirection follows the profile's `redirectclipboard` field
  and that a profile without it gets the RDP default (enabled).
- Install, upgrade from the split packages, and remove the `eitaas-linux` DEB,
  RPM, and Arch packages.
- Confirm the release tag is `v` + the canonical version in `pyproject.toml`.
- Run `scripts/check-version-consistency.py --tag vX.Y.Z` before creating the tag;
  it enforces the whole mapping above, including the native `~` forms.
- For a pre-release, confirm `rpmdev-vercmp X.Y.Z~rcN X.Y.Z` and
  `dpkg --compare-versions X.Y.Z~rcN lt X.Y.Z` both report the candidate as lower.
- Generate the canonical source tarball twice and confirm byte-for-byte output.
- Verify the source tarball contains exactly the tagged Git tree and no private profiles, certificates, captures, or agent state.
- Approve the protected tag workflow and verify its GitHub provenance attestations.
- Review the complete artifact set, generated checksums, and SBOM before publication.
- Sign `SHA256SUMS` locally and publish its detached ASCII signature.
