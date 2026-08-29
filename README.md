# EITaaS-Linux

Community tooling for connecting to an Azure Virtual Desktop (AVD) workspace
from Linux with Common Access Card (CAC) redirection through FreeRDP.

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
inside a remote session. EITaaS-Linux checks the local system and safely invokes
a compatible FreeRDP 3 client using a profile manually exported from the AVD
web client.

## Security defaults

- Server certificate verification remains enabled. The project does not use a
  certificate-bypass switch in its normal connection path.
- No all-users pcsc-lite or polkit override is installed or recommended.
- The tool never asks for or records a CAC PIN.
- Real `.rdp` and `.rdpw` profiles, OAuth callbacks, keys, certificates, packet
  captures, and local agent state are excluded from Git.
- Connection profiles should be owned by the current user and mode `0600`.
- Clipboard redirection is off unless the user explicitly requests it.

On a shared computer, another process running as the same Linux account may be
able to access an inserted smart card. Polkit cannot isolate mutually
untrusted processes belonging to one user. Remove the CAC when it is not in use.

## Current workflow

1. Sign in to the authorized Azure US Government web client supplied by your
   organization and manually export the desktop `.rdpw` profile. Microsoft does
   not document a supported public API for automating this export.
2. Restrict it before use:

   ```bash
   chmod 600 Desktop.rdpw
   ```

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

5. Connect:

   ```bash
   eitaas connect Desktop.rdpw
   ```

   For profiles whose multimonitor settings produce incorrect scaling or
   pointer alignment under XWayland, start with a single-monitor window:

   ```bash
   eitaas connect Desktop.rdpw --single-monitor
   ```

Do not publish, attach, or commit the exported profile. Treat it as
user/resource-specific connection material even when it does not contain a
password.

## FreeRDP and desktop support

AVD authentication requires a FreeRDP 3 build with AAD support; CAC redirection
also requires PC/SC support. Ubuntu 22.04's standard repository supplies
FreeRDP 2 and is therefore not currently a supported target.

Authentication must use either a live Microsoft Identity Broker through
FreeRDP's SSO-MIB support or an SDL FreeRDP client built with WebView support.
EITaaS-Linux refuses FreeRDP's terminal URL/callback fallback. Do not capture
OAuth callbacks with browser developer tools or paste them into a terminal.

The connection profile supplies the signed resource, tenant, and endpoint
settings. EITaaS-Linux classifies only allowlisted endpoint suffixes, rejects
mixed or unknown clouds, and supplies the matching AVD token audience. It does
not modify the signed profile.

The session type alone does not determine the correct client. Automatic
selection considers authentication capability before backend preference. The
`doctor` command reports the session, broker status, and each client's
authentication mode; `connect` supports an explicit backend override.

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

The CLI, planned GTK 4/Libadwaita frontend, and planned Qt 6 frontend share one
presentation-neutral application API. The shared interaction and accessibility
specification is documented under `docs/frontend/`. The graphical design uses
a familiar resource-card workflow with original EITaaS-Linux branding; it does
not copy or impersonate Windows App.
