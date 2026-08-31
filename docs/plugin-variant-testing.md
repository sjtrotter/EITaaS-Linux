# Testing the `remmina-plugin-rdp-piv` variant on Fedora 44 (host procedure)

This is the owner's host procedure for the AAD/PIV drop-in RDP plugin from
issue #101 (ADR-0003 Track 2). The agent builds and verifies everything inside
containers; **installing and hardware-testing is done here, on the host.**

## What you install and why

Both packages are built from the *same* pinned Remmina 1.4.43 source
(`030946c8`, recorded in `packaging/remmina/sources.json`) so they are
ABI-matched:

| Package | EVR | Role |
| --- | --- | --- |
| `remmina` (+ its subpackages) | `1.4.43^142.g030946c83-1.fc44` | Vanilla Remmina 1.4.43 base (Fedora's own packaging, source bumped). Replaces Fedora stock `remmina-1.4.41-2`. |
| `remmina-plugin-rdp-piv` | `1.4.43^142.g030946c83-1.fc44` | The AAD + smart card (PIV) RDP plugin. `Provides`/`Obsoletes`/`Conflicts remmina-plugins-rdp`, so it cleanly swaps the stock RDP plugin. |

FreeRDP is **not** rebuilt: Fedora 44 already ships `freerdp-libs 2:3.30.0-1.fc44`,
the version this project pins and above the 3.16 floor the AVD gateway APIs
require. The plugin links the distribution's FreeRDP 3.

### Version scheme (why `1.4.43^142.g030946c83`)

Our `sources.json` pins snapshot `030946c8`, which is `git describe =
v1.4.43-142-g030946c83` — 142 commits after the bare `v1.4.43` tag. The RDP AAD
web-authentication code the plugin extends (`plugins/rdp/rdp_web_auth.c`) does
**not** exist at the bare tag; it landed on master afterwards. Both packages are
therefore built from this snapshot, versioned `1.4.43^142.g030946c83`. The `^`
makes it a *post-release* snapshot: it sorts **above** Fedora stock (1.4.41-2)
**and** above any future real `1.4.43-1` (so a later Fedora build cannot silently
swap an ABI-different Remmina under the plugin), and **below** `1.4.44`. Verify:

```console
rpmdev-vercmp 1.4.43^142.g030946c83-1.fc44 1.4.41-2.fc44   # ->  >
rpmdev-vercmp 1.4.43^142.g030946c83-1.fc44 1.4.43-1.fc44   # ->  >
rpmdev-vercmp 1.4.43^142.g030946c83-1.fc44 1.4.44-1.fc44   # ->  <
```

The plugin `Requires: remmina = 1.4.43^142.g030946c83-1.fc44` **exactly**, so the
base and the plugin must always be built and released **together** (same PR, same
COPR build batch).

## 0. Prerequisites

- Fedora 44, x86_64.
- The built RPMs (see below). At minimum you need the base `remmina` and the
  1.4.43 build of **every** `remmina-*` subpackage you currently have installed,
  plus `remmina-plugin-rdp-piv`.
- A smart card reader with a PIV card, and `opensc` + `gnutls-utils` installed
  (the plugin `Recommends` both; `p11tool` from `gnutls-utils` lists the card's
  certificates, `opensc` provides the PKCS #11 module).

There is **no COPR yet** — standing one up is an ADR-0003 follow-up. For now
install the local RPMs directly. When the COPR exists, the equivalent first
step will be `sudo dnf copr enable <owner>/remmina-aad-piv` then
`sudo dnf install remmina remmina-plugin-rdp-piv` (dnf resolves the subpackage
upgrades automatically from one repo).

## 1. Install the base Remmina 1.4.43 and the PIV plugin — ONE transaction

> **Why one transaction matters.** Every stock `remmina-plugins-*` subpackage has
> `Requires: remmina = 1.4.41-2`. If you upgrade only the base `remmina` to
> 1.4.43, those installed subpackages break their dependency. So you must upgrade
> the base **and every installed remmina-* subpackage** to 1.4.43 in the *same*
> `dnf install`, with the PIV plugin (which obsoletes `remmina-plugins-rdp`) in
> the same command.

First check what you currently have, so you include a 1.4.43 RPM for each:

```console
rpm -qa 'remmina*' | sort
```

A default Fedora Remmina install has exactly: `remmina`, `remmina-plugins-exec`,
`remmina-plugins-rdp`, `remmina-plugins-secret`, `remmina-plugins-vnc`. For that
set, from the directory holding the RPMs:

```console
sudo dnf install \
  ./remmina-1.4.43^142.g030946c83-1.fc44.x86_64.rpm \
  ./remmina-plugins-exec-1.4.43^142.g030946c83-1.fc44.x86_64.rpm \
  ./remmina-plugins-secret-1.4.43^142.g030946c83-1.fc44.x86_64.rpm \
  ./remmina-plugins-vnc-1.4.43^142.g030946c83-1.fc44.x86_64.rpm \
  ./remmina-plugin-rdp-piv-1.4.43^142.g030946c83-1.fc44.x86_64.rpm \
  gnutls-utils opensc
```

This upgrades the base + exec/secret/vnc to 1.4.43 and **obsoletes**
`remmina-plugins-rdp`, installing the PIV plugin in its place — **no
`--allowerasing` needed**.

If `rpm -qa 'remmina*'` also shows any of `remmina-plugins-www`,
`remmina-plugins-spice`, `remmina-plugins-kwallet`, `remmina-plugins-python`, or
`remmina-plugins-x2go`, add the matching 1.4.43 RPM for each to the same command
(the base spec builds them all; they are staged alongside the others). Do **not**
leave any installed remmina-* subpackage at 1.4.41.

Confirm the result:

```console
rpm -qa 'remmina*' | sort          # everything at 1.4.43^142.g030946c83-1.fc44
rpm -q remmina-plugins-rdp         # -> "not installed"
rpm -qf /usr/lib64/remmina/plugins/remmina-plugin-rdp.so   # -> remmina-plugin-rdp-piv
```

## 2. Confirm Remmina loads the PIV RDP plugin

```console
remmina --full-version 2>/dev/null | grep -A2 '^RDP'
```

Expected: an `RDP` protocol row (plus `RDPF` file handler and `RDPS`
preferences), e.g.:

```
RDP    Protocol   RDP - Remote Desktop Protocol   RDP plugin: 1.4.43 ...
       Compiled with libfreerdp 3.30.0, Running with libfreerdp 3.30.0 ...
```

Confirm it is the AAD/PIV build:

```console
strings /usr/lib64/remmina/plugins/remmina-plugin-rdp.so | grep -m1 'smartcard-auth:'
ldd  /usr/lib64/remmina/plugins/remmina-plugin-rdp.so | grep -E 'freerdp3|webkit2gtk-4.1'
```

You should see `smartcard-auth: ...` and links to `libfreerdp3.so.3` and
`libwebkit2gtk-4.1.so.0`.

## 3. Hardware test — the real flow

Do this at a normal desktop session (not over SSH/headless), with the card
reader attached and the PIV card inserted.

1. **Import the AVD profile.** Launch Remmina, then **Menu ▸ Import** (or
   `remmina -i /path/to/your.rdpw`) and select the real `.rdpw` file. It should
   be accepted and appear in the connection list as a normal RDP connection.
   - Equivalent CLI: `remmina -c /path/to/your.rdpw` opens it directly.
2. **Confirm it is listed.** The imported connection shows in the main Remmina
   connection list with its name.
3. **Connect.** Double-click the connection. An embedded WebKit sign-in window
   opens against `login.microsoftonline.us` (Azure US Government).
4. **PIV sign-in.** When the web sign-in asks for a certificate, the plugin
   presents the PIV certificate picker; choose your PIV auth certificate and
   enter the card PIN when prompted. Certificate verification stays on.
5. **Reach the desktop.** After the token exchange and ARM gateway
   orchestration (up to 60 s for the AVD ARM response), the remote desktop
   should appear.
6. **In-session smart card.** If your profile redirects the smart card, confirm
   the card is usable inside the session.

If sign-in shows an empty certificate list, install `gnutls-utils` (provides
`p11tool`) and `opensc`, re-insert the card, and retry.

Privacy: the plugin logs only stable `smartcard-auth: <code>` reason codes,
counts, and the verified sign-in host. It never logs PINs, tokens, PKCS #11
URIs, certificate labels, or `.rdpw` contents. Do not paste real profile
contents or session logs into any report.

## 4. Revert to stock Fedora Remmina

Remove the variant and the 1.4.43 base, then reinstall Fedora's shipped Remmina
(1.4.41-2) with the subpackages you use:

```console
sudo dnf remove remmina-plugin-rdp-piv 'remmina*'
sudo dnf install remmina remmina-plugins-rdp remmina-plugins-exec \
                 remmina-plugins-secret remmina-plugins-vnc
```

(When a COPR is later used instead of local RPMs, also
`sudo dnf copr disable <owner>/remmina-aad-piv` before reinstalling stock.)

Verify the revert:

```console
rpm -qa 'remmina*' | sort              # all from fedora/updates, 1.4.41-2
rpm -q remmina-plugin-rdp-piv          # -> "not installed"
```
