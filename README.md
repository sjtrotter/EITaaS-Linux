# EITaaS-Linux

Community Linux tooling for reaching an Azure Virtual Desktop (AVD) workspace
in the US Government cloud with **smart card (PIV)** authentication and
redirection.

One package per distribution — `eitaas-linux` — installs three things that work
together:

- **the bundled client**, `eitaas-remmina`: a private, one-shot Remmina and
  FreeRDP 3 pair built from the pins in `packaging/remmina/sources.json` and
  installed under its own prefix. It never replaces or uses the distribution's
  Remmina or FreeRDP packages.
- **EITaaS Connect** (`eitaas-gui`): a GTK 4/Libadwaita helper that checks the
  system, walks you through exporting your profile from the AVD web client,
  imports it, and connects. No terminal required.
- **`eitaas`**: the same operations on the command line, plus read-only
  diagnostics.

The project began as documentation for the Sonic Boom pilot. It is independent
community work and is not endorsed by Microsoft, the Department of Defense, the
Department of the Air Force, or the operators of Enterprise IT as a Service.
See `NOTICE` for the complete statement.

> [!WARNING]
> This repository is under active development. Microsoft does not provide a
> supported native Linux Windows App client. Confirm that your organization
> permits this client before using it.

## Why this exists

The AVD web client works on Linux but does not redirect smart cards. Smart-card
redirection is what lets a PIV-authenticated site or a signing application
*inside* the remote session see your card. The bundled client provides it; the
`.rdpw` profile you export from the web client tells it where to connect.

USB device redirection is included as well: every recipe declares libusb as a
build dependency and leaves FreeRDP's `urbdrc` channel at its default, so the
channel is compiled into the bundle on all three distributions. What is
actually redirected in a session still depends on your profile and on the host
policy.

## Install

There is no distribution repository yet. Build the package for your
distribution from this checkout, or take the artifact the release workflow
produced, and install it with one command:

```bash
# Fedora
sudo dnf install ./eitaas-linux-<version>.x86_64.rpm

# Debian / Ubuntu
sudo apt install ./eitaas-linux_<version>_amd64.deb

# Arch Linux
sudo pacman -U ./eitaas-linux-<version>-x86_64.pkg.tar.zst
```

To build the artifact yourself, run the builder for your distribution —
`scripts/build-rpm.sh`, `scripts/build-deb.sh`, or `scripts/build-arch.sh`.
Each one verifies both pinned upstream archives against their SHA-256 digests,
applies the same ordered patch series, and writes the binary package and its
corresponding source to `dist/`.

Upgrading from the earlier split packages needs no extra step: `eitaas-linux`
obsoletes and replaces `eitaas-remmina` and `eitaas-linux-gui`.

Submitting the package to Fedora, Debian, and the AUR is a possible later goal,
most likely once Remmina upstream carries the patches this bundle applies. It
is not a commitment, and these are not official distribution or AUR packages
today.

## First run

Launch **EITaaS Connect** from your application menu (or run `eitaas-gui`). It
opens on **Readiness** the first time.

![EITaaS Connect readiness page](docs/images/helper-readiness.png)

Each row says what was checked, what it proves, and — where something is
missing — which package to install or command to run. Commands such as
`systemctl enable --now pcscd.socket` are shown with a copy button; the helper
never runs anything privileged for you. Press **Re-check** (Ctrl+R) after
fixing one.

Next, get your profile on the **Profile** page.

![EITaaS Connect profile page](docs/images/helper-profile.png)

Pick your cloud (Azure US Government by default, or Azure commercial) and press
**Open web client**; those two public web-client addresses are the only URLs
the helper ever opens. The six numbered steps then follow the web client's own
interface: sign in with your organization account — the browser may ask for
your smart card (PIV) certificate and PIN — click the settings cog in the top
right, choose "Download the rdp file", and click your desktop, which saves a
file such as `Desktop.rdpw` to your Downloads folder. Come back, press **I
downloaded the RDP file** (Ctrl+O), and pick it.

Importing *moves* the file out of Downloads into
`$XDG_DATA_HOME/eitaas-remmina/profiles/` (directory mode 0700, file mode
0600) and makes it the profile Connect uses, so the profile no longer depends
on whatever permissions your download directory happens to have. The "Why do I
need this file?" expander explains what the `.rdpw` is. Imported profiles are listed
with a selector for the one Connect uses and a Remove action; double-clicking a
`.rdpw` file in your file manager opens this page with an offer to import it,
and nothing is imported or connected until you press the button.

Finally, **Connect** (Ctrl+Return).

![EITaaS Connect connect page](docs/images/helper-connect.png)

The button is disabled only on hard failures — the launcher or its private
client binary missing, or no imported profile. Warnings never disable it. While
the client runs the page shows the phase and a **Cancel** button; closing the
window asks whether to disconnect and quit or keep working.

Once the checks have passed and a profile is imported, later starts open
straight on **Connect** while the checks re-run in the background. If a check
that passed before now fails, a dialog names it and switches you to Readiness.

The screenshots above were captured with a synthetic readiness report and the
synthetic test fixture; they contain no real profile, host, or account.

## What happens when you connect

Connect (and `eitaas connect`) does exactly one thing: it validates the profile
and runs `eitaas-remmina PROFILE.rdpw` with no other arguments. Everything
after that belongs to the bundled client.

Sign-in happens in **Remmina's embedded WebKitGTK view**, inside the client
window:

- the view opens only on an HTTPS Microsoft sign-in host
  (`login.microsoftonline.com` or `login.microsoftonline.us`), and certificate
  and PIN challenges are accepted only from that verified authority or its
  `certauth.` sibling host — proxy, mismatched-origin, and standalone PIN
  challenges are refused;
- when the site asks for a client certificate, the client lists your card's
  authentication, identity, and PIV-labelled certificates through GnuTLS'
  `p11tool` and shows a chooser;
- the **PIN prompt is the client's own dialog**, and its entry submits only
  through the explicit confirmation button — pressing Enter does not confirm
  it, deliberately, so a partly typed PIN cannot be spent against the card's
  retry limit (#85);
- FreeRDP's fallback of printing an authorization URL and asking you to paste a
  callback into a terminal is refused. Never capture an OAuth callback with
  browser developer tools or paste one into a terminal.

Cancelling authentication ends the whole one-shot client rather than dropping
you into a connection manager: this is not a connection manager, by design
(ADR-0002).

Do not publish, attach, or commit an exported profile. Treat it as
user- and resource-specific connection material.

## Security defaults

These are the defaults as implemented today, not intentions:

- **Server certificate verification stays on.** Nothing in this project passes
  a certificate-bypass switch, and `scripts/check-repository-artifacts.sh`
  fails the build if such guidance is ever committed.
- **Your PIN is never captured.** The PIN is typed into the bundled client's
  dialog and is never logged, persisted, or passed across the Python API
  (`docs/application-api.md`).
- **Imported profiles are private.** `eitaas profile import` and the helper
  accept only a regular, user-owned `.rdpw` of at most 1 MiB, refuse symlinks,
  and store it mode 0600 in a 0700 directory. `eitaas connect` re-validates
  ownership, mode, size, and extension before every launch.
- **Session logs are redacted.** Every line of the client's output passes
  through `redaction.redact` before it is written (JWTs, `Bearer` values,
  quoted-JSON token fields, `Set-Cookie`/`ARRAffinity` cookie values, sensitive
  `key=value` pairs, and URL query values). Certificate labels, PKCS #11 URIs,
  PINs, and tokens are never logged by the client in the first place — only
  counts, stable reason codes, and the verified sign-in host.
- **Clipboard redirection follows your profile.** The bundled client honours
  the profile's `redirectclipboard` field through Remmina's RDPW importer, and
  a profile that omits it gets the RDP default (enabled). The launcher does not
  override it, and the field is not among the keys forwarded to FreeRDP's
  native profile parser. The exported profile is the policy source, by design.
- **Untrusted profile content is allowlisted.** Only a fixed set of AVD and
  gateway keys from the profile reaches FreeRDP's native parser; everything
  else is dropped before parsing (`packaging/remmina/0006-*.patch`).
- **Nothing privileged is installed or changed.** No pcsc-lite or polkit
  override, no trust-store modification, no `sudo` anywhere in diagnostics.
- Real profiles, OAuth callbacks, keys, certificates, packet captures, and
  local agent state are excluded from Git.

On a shared computer, another process running as the same Linux account may be
able to use an inserted smart card. Polkit cannot isolate mutually untrusted
processes belonging to one user. Remove the card when it is not in use.

## Command line

The same operations, for people who prefer a terminal:

```bash
eitaas doctor                    # read-only system checks; --json for detail
eitaas smartcard status          # PC/SC service, reader, and middleware
eitaas inspect-profile FILE.rdpw # safe summary; sensitive fields redacted
eitaas profile import FILE.rdpw  # move into the private store, make default
eitaas profile list|select NAME|remove NAME
eitaas connect [FILE.rdpw]       # default profile when no path is given
```

`eitaas connect` fails closed when no profile has been imported and no path is
given. `eitaas` exits 0 on success, 1 when diagnostics complete with unmet
requirements, and 2 on invalid input or an operation error; a connection
otherwise returns the client's own exit status. See `eitaas(1)` and
`eitaas-gui(1)`.

## Troubleshooting

Start with `eitaas doctor` (or the helper's Readiness page). It reports the
desktop session, the PC/SC socket, the smart-card tools, whether the
`eitaas-remmina` launcher and its private client binary are installed, and the
pinned Remmina and FreeRDP versions taken from the installed manifest.

Every connection writes the client's output, redacted line by line, to
`$XDG_STATE_HOME/eitaas-remmina/logs/session-<timestamp>-<pid>.log`
(`~/.local/state/...` by default; directory 0700, files 0600, about 2 MiB each,
the newest five kept). The first lines record the version, the profile
basename, and how many `remmina` processes were already running; the last line
is `exit=<code>`. Logging is best effort: a log that cannot be created is
skipped rather than allowed to stop the connection.

- **In the helper:** after a failed run the Connect page shows the last
  `smartcard-auth:` reason-code and Remmina warning lines from that log, names
  the log, and offers **Copy diagnostic log**, which puts the whole redacted
  log on the clipboard for a support request.
- **On the command line:** `eitaas doctor --json` reports
  `latest_session_log`. To watch the stages live, run the client directly:
  `G_MESSAGES_DEBUG=remmina eitaas-remmina PROFILE.rdpw`. The launcher already
  sets that default, so plain `eitaas-remmina PROFILE.rdpw` prints them too.

Each smart-card stage is logged as `smartcard-auth: <code>` with a stable code,
and the Azure Virtual Desktop ARM gateway phase as `avd-arm:` — a profile that
sets no timeout of its own logs `avd-arm: response-timeout-ms=60000`, the
raised wait for the gateway's connection response. The full table of codes and
what each one means is in
[`packaging/remmina/README.md`](packaging/remmina/README.md) under
"Diagnostics", and `eitaas(1)` lists the codes.

Remmina also appends its own debug lines to `$TMPDIR/remmina_log_file.log`
(upstream behaviour, not redacted by this project). A distribution Remmina that
is already running is a known way to lose a connection request, which is why
the session log counts `remmina` processes in its header.

**Older logs are not cleaned retroactively.** Logs written by the
`eitaas-linux` 0.1.x CLI, by the split-package installs that preceded it, or by
bundle releases up to `1.4.43+eitaas0.15` may still contain unredacted Azure
`ARRAffinity` routing cookies; the cookie rules ship in `eitaas-linux` 0.2.x.
They are load-balancer routing values, not credentials, but they are
server-issued and session-scoped: review a log before attaching it to a support
request, or delete `$XDG_STATE_HOME/eitaas-remmina/logs/` and let the next
connection recreate it.

## Support boundary

Supported combinations are exactly those the CI matrix and the manual release
checklist exercise. The per-artifact gate table — which distributions are built
and linted automatically, and which have passed smart-card/AVD hardware
validation — is in
[`docs/supported-platforms.md`](docs/supported-platforms.md). A passing
`eitaas doctor` does not mean your organization permits this client.

This is community-supported software, not an official Microsoft or United
States Government client; see `SUPPORT.md`. Report security issues privately as
described in `SECURITY.md`, and never attach a real profile, callback URL, or
card output to a public issue.

## Licensing

Project code is licensed under the MIT License. The `eitaas-linux` package is a
composite: Remmina and the smart card (PIV) integration compiled into its RDP
plugin are GPL-2.0-or-later, FreeRDP is Apache-2.0, and the EITaaS Python
tooling and launcher are MIT. `packaging/remmina/THIRD_PARTY_NOTICES.md` maps
every component to its licence and pinned source, and each package ships
corresponding source. Distribution packages, certificates, documentation,
services, and trademarks remain subject to their own terms. See `LICENSE` and
`NOTICE`.

Release candidates include SHA-256 manifests and, for approved tag builds,
keyless GitHub provenance attestations; the procedure is in
`docs/release-signing.md`.

## Documentation

| Document | Contents |
| --- | --- |
| [`docs/supported-platforms.md`](docs/supported-platforms.md) | Target distributions and the CI/hardware gate table |
| [`packaging/remmina/README.md`](packaging/remmina/README.md) | The bundled client: pins, patches, build flags, reason codes |
| [`docs/application-api.md`](docs/application-api.md) | The presentation-neutral API both frontends use |
| [`docs/frontend/`](docs/frontend/) | EITaaS Connect interaction and accessibility specification |
| [`docs/adr/`](docs/adr/) | Architecture decisions, including the product boundary (ADR-0002) |
| [`docs/audits/`](docs/audits/) | Security reviews of the Remmina changes |
| [`upstream/remmina/README.md`](upstream/remmina/README.md) | The unbranded upstream-candidate patch series |
| `CONTRIBUTING.md`, `SECURITY.md`, `SUPPORT.md` | Contribution, disclosure, and support policy |

The CLI and the helper share one presentation-neutral application API; the
helper's graphical design is original EITaaS-Linux branding and does not copy
or impersonate Windows App.
