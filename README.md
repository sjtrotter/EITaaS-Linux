# EITaaS-Linux

Community tooling for connecting to an Azure Virtual Desktop (AVD) workspace
from Linux with Common Access Card (CAC) redirection through a bundled
one-shot Remmina/FreeRDP client.

The project began as documentation for the Sonic Boom pilot. It is independent
community work and is not endorsed by Microsoft, the Department of Defense,
the Department of the Air Force, or the operators of Enterprise IT as a
Service. See `NOTICE` for the complete statement.

> [!WARNING]
> This repository is under active development. Microsoft does not provide a
> supported native Linux Windows App client. Confirm that your organization
> permits FreeRDP before using it.

## Why this exists

The AVD web client works on Linux but does not redirect smart cards. Smart-card
redirection is needed for CAC-authenticated sites and signing applications
inside a remote session. EITaaS-Linux checks the local system and starts the
bundled `eitaas-remmina` client with a profile manually exported from the AVD
web client.

## Security defaults

- Server certificate verification remains enabled. The project does not use a
  certificate-bypass switch in its normal connection path.
- No all-users pcsc-lite or polkit override is installed or recommended.
- The tool never asks for or records a CAC PIN.
- Real `.rdp` and `.rdpw` profiles, OAuth callbacks, keys, certificates, packet
  captures, and local agent state are excluded from Git.
- Connection profiles should be owned by the current user and mode `0600`.
- Clipboard redirection follows the connection profile; the launcher does not
  override it. The bundled client honors the profile's `redirectclipboard`
  field through Remmina's RDPW importer, and a profile that omits the field
  gets the RDP default (enabled). This is by design: the exported profile is
  the policy source. The field is not among the keys forwarded to FreeRDP's
  native profile parser (allowlist in `packaging/remmina/0006-*.patch`).

On a shared computer, another process running as the same Linux account may be
able to access an inserted smart card. Polkit cannot isolate mutually
untrusted processes belonging to one user. Remove the CAC when it is not in use.

## Current workflow

1. Sign in to the authorized Azure US Government web client supplied by your
   organization and manually export the desktop `.rdpw` profile. Microsoft does
   not document a supported public API for automating this export.
2. Import it into the private profile store:

   ```bash
   eitaas profile import Desktop.rdpw
   ```

   This moves the file out of the download directory into
   `$XDG_DATA_HOME/eitaas-remmina/profiles/`, restricts it to your user
   (mode `0600`), and makes it the default profile for `eitaas connect`.
   `eitaas profile list`, `select NAME`, and `remove NAME` manage the store.
   The manual alternative still works: `chmod 600 Desktop.rdpw` and pass the
   explicit path to `eitaas connect Desktop.rdpw`.

3. Install this project and distribution-provided dependencies once packaging
   for your distribution is available. Upstream packaging definitions are
   provided for Debian/Ubuntu, Fedora, and Arch Linux; these are not official
   distribution or AUR packages.
4. Diagnose the system:

   ```bash
   eitaas doctor
   eitaas smartcard status
   eitaas inspect-profile Desktop.rdpw
   ```

5. Connect with the isolated one-shot GovCloud client:

   ```bash
   eitaas-remmina Desktop.rdpw
   ```

   `eitaas connect` with no argument uses the imported default profile and
   fails closed when none has been imported. `eitaas connect Desktop.rdpw`
   uses an explicit path instead. Either form is a thin wrapper: it validates
   the profile (ownership, mode `0600`, size, extension) and then runs
   `eitaas-remmina PROFILE.rdpw` with no other arguments.

The EITaaS suite combines the `eitaas` setup/diagnostic tool with a pinned,
privately installed Remmina and FreeRDP pair. It does not replace the system
Remmina installation, and it does not provide an enhanced connection-manager
mode. The exact upstream versions and downstream CAC/GovCloud patches are
recorded in `packaging/remmina/sources.json` and shipped with corresponding
source.

Do not publish, attach, or commit the exported profile. Treat it as
user/resource-specific connection material even when it does not contain a
password.

## Graphical helper

The optional `eitaas-linux-gui` package (the same name on Debian/Ubuntu,
Fedora, and Arch) installs **EITaaS Connect** (`eitaas-gui`), a
GTK 4/Libadwaita window with three pages:

- **Readiness** shows the `eitaas doctor` result as plain-language rows
  (bundled client, desktop session, smart-card service, reader, card
  middleware, identity broker, diagnostic tools) with a Re-check button.
- **Profile** lists the export steps, imports a downloaded `.rdpw` through the
  file chooser (the same move-and-restrict as `eitaas profile import`), and
  lists imported profiles with a selector for the one Connect uses and a
  Remove action.
- **Connect** starts `eitaas-remmina` with the selected profile, shows the
  phase with a Cancel button while the client runs, and shows redacted errors
  in place.

Double-clicking a `.rdpw` file in the file manager (MIME type
`application/x-eitaas-rdpw`) opens the Profile page with an "Import
FILE into your private profile store?" banner. Nothing is imported or
connected until you press Import and then Connect.

The screenshots below were captured with a synthetic readiness report and
the synthetic test fixture; they contain no real profile, host, or account.

![EITaaS Connect readiness page](docs/images/helper-readiness.png)
![EITaaS Connect profile page](docs/images/helper-profile.png)
![EITaaS Connect connect page](docs/images/helper-connect.png)

The helper keeps the ADR-0002 boundary: it is not a connection manager,
sign-in and the smart card (PIV) PIN prompt happen in the Remmina window, and it runs no
privileged commands. Fixes such as `systemctl enable --now pcscd.socket` are
shown with a copy button for you to run yourself.

## Bundled client and desktop support

Connections use only the bundled `eitaas-remmina` package: Remmina and
FreeRDP 3 built from the pins in `packaging/remmina/sources.json` with AAD and
PC/SC support, installed under a private prefix. Distribution FreeRDP or
Remmina packages are neither required nor used, so distribution FreeRDP
versions (for example FreeRDP 2 on Ubuntu 22.04) no longer determine support;
see `docs/supported-platforms.md` for the packaging and hardware status.

Authentication uses the Microsoft Identity Broker (only where the bundle was
built with SSO-MIB, currently the Fedora RPM) or the embedded CAC WebView.
Endpoint allowlisting, the RDPW native-settings allowlist, and refusal of
FreeRDP's terminal URL/callback fallback are enforced inside the bundled client
by the Remmina patches (see #51 and #58), not by the Python tool. Do not capture
OAuth callbacks with browser developer tools or paste them into a terminal.

The connection profile supplies the signed resource, tenant, and endpoint
settings; `eitaas inspect-profile` classifies only allowlisted endpoint
suffixes and rejects mixed or unknown clouds. Nothing modifies the signed
profile.

The `doctor` command reports whether `eitaas-remmina` is on `PATH`, whether
the private client binary is installed, the pinned Remmina/FreeRDP versions
from the installed `sources.json`, whether the bundle links SSO-MIB, and the
identity-broker, PC/SC, and smart-card tool status.

## Smart-card permissions

First use your distribution's default pcsc-lite policy. Do not run smart-card
tests with `sudo`. If access is denied, diagnose the daemon, socket, session,
reader, and middleware separately before changing authorization policy.

EITaaS-Linux does not install a policy override. A future optional policy must
use exact action identifiers, a dedicated group, and active local sessions; it
must never authorize every account or inactive sessions.

## Certificates

DoD PKI trust is separate from AVD gateway certificate verification. Never work
around an AVD certificate error by disabling verification.

Certificate tooling will use official HTTPS sources, show fingerprints, keep
self-signed trust anchors distinct from intermediates, and require explicit
confirmation before changing a user or system trust store. Package installation
will not download or trust certificates automatically.

## Licensing

Project code is licensed under the MIT License. FreeRDP, OpenSC, pcsc-lite,
distribution packages, certificates, documentation, services, and trademarks
remain subject to their respective terms. See `LICENSE` and `NOTICE`.

Release candidates include SHA-256 manifests and, for approved tag builds,
keyless GitHub provenance attestations. The release signing and verification
procedure is documented in `docs/release-signing.md`.

## Frontends

The CLI and the GTK 4/Libadwaita helper share one presentation-neutral
application API (`docs/application-api.md`). The interaction and accessibility
specification for the helper is documented under `docs/frontend/`. The
graphical design uses original EITaaS-Linux branding; it does not copy or
impersonate Windows App.
