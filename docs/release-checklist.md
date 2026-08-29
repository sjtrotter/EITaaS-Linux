# Manual release checklist

Do not use real profiles, account identifiers, callback URLs, or CAC output as
public test evidence.

- Confirm Azure US Government initial authentication with an authorized test account.
- Confirm CAC authentication is passed into the desktop.
- Run `certutil -scinfo` inside the Windows session.
- Test CAC removal and reinsertion, disconnect, and reconnect.
- Test GNOME Wayland/XWayland, KDE Wayland/XWayland, and an X11 session.
- Exercise X11, SDL, and native Wayland backends that are claimed as supported.
- Verify server certificate validation remains enabled.
- Verify clipboard redirection is disabled by default.
- Install, upgrade, and remove both DEB and RPM packages.
- Review the generated checksums and SBOM before approving publication.
