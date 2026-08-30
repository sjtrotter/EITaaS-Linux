# Manual release checklist

Do not use real profiles, account identifiers, callback URLs, or CAC output as
public test evidence.

- Confirm Azure US Government initial authentication with an authorized test account.
- Confirm authentication uses an identity broker or embedded WebView and never
  emits or requests an authorization URL, callback URL, code, or token.
- Confirm CAC authentication is passed into the desktop.
- Run `certutil -scinfo` inside the Windows session.
- Test CAC removal and reinsertion, disconnect, and reconnect.
- Test GNOME Wayland/XWayland, KDE Wayland/XWayland, and an X11 session.
- Exercise the bundled client under X11 and XWayland sessions that are claimed as supported.
- Verify server certificate validation remains enabled.
- Verify clipboard redirection follows the profile's `redirectclipboard` field.
- Install, upgrade, and remove both DEB and RPM packages.
- Confirm the release tag exactly matches the version in `pyproject.toml`.
- Run `scripts/check-version-consistency.py --tag vX.Y.Z` before creating the tag.
- Generate the canonical source tarball twice and confirm byte-for-byte output.
- Verify the source tarball contains exactly the tagged Git tree and no private profiles, certificates, captures, or agent state.
- Approve the protected tag workflow and verify its GitHub provenance attestations.
- Review the complete artifact set, generated checksums, and SBOM before publication.
- Sign `SHA256SUMS` locally and publish its detached ASCII signature.
