# Testing the `remmina-plugin-rdp-piv` variant on Fedora 44 (host procedure)

This is the owner's host procedure for the AAD/PIV drop-in RDP plugin from
issue #101 (ADR-0003 Track 2). The agent builds and verifies everything inside
containers; **installing and hardware-testing is done here, on the host.**

## What you install and why

Two packages, both built from the *same* pinned Remmina 1.4.43 source
(`030946c8`, recorded in `packaging/remmina/sources.json`) so they are
ABI-matched:

| Package | EVR | Role |
| --- | --- | --- |
| `remmina` | `1.4.43-1.fc44` | Vanilla Remmina 1.4.43 base (Fedora's own packaging, bumped source). Replaces Fedora stock `remmina-1.4.41-2`. |
| `remmina-plugin-rdp-piv` | `1.4.43-1.fc44` | The AAD + smart card (PIV) RDP plugin. `Provides`/`Obsoletes`/`Conflicts remmina-plugins-rdp`, so it cleanly swaps the stock RDP plugin. |

FreeRDP is **not** rebuilt: Fedora 44 already ships `freerdp-libs 2:3.30.0-1.fc44`,
which is the version this project pins and is above the 3.16 floor the AVD
gateway APIs require. The plugin links the distribution's FreeRDP 3.

> Note on the base version. Our sources.json labels the pinned snapshot
> `030946c8` as "1.4.43". It is `git describe = v1.4.43-142-g030946c83` — 142
> commits after the bare `v1.4.43` tag. The RDP AAD web-authentication code the
> plugin extends (`plugins/rdp/rdp_web_auth.c`) does **not** exist at the bare
> tag; it landed on master afterwards. That is why both packages are built from
> this snapshot rather than the tag.

## 0. Prerequisites

- Fedora 44, x86_64.
- The two RPMs (plus the base subpackages) from the build:
  `remmina-1.4.43-1.fc44.x86_64.rpm` and
  `remmina-plugin-rdp-piv-1.4.43-1.fc44.x86_64.rpm`.
- A smart card reader with a PIV card, and `opensc` + `gnutls-utils` installed
  (the plugin `Recommends` both; `p11tool` from `gnutls-utils` lists the card's
  certificates, `opensc` provides the PKCS #11 module).

There is **no COPR yet** — standing one up is an ADR-0003 follow-up. For now
install the local RPMs directly. When the COPR exists, the equivalent first
step will be:

```console
# (future COPR — does not exist yet)
sudo dnf copr enable <owner>/remmina-aad-piv
sudo dnf install remmina remmina-plugin-rdp-piv
```

## 1. Install the base Remmina 1.4.43 and the PIV plugin

From the directory holding the RPMs:

```console
# Base Remmina 1.4.43 (upgrades Fedora stock 1.4.41-2) + smart-card helpers.
sudo dnf install ./remmina-1.4.43-1.fc44.x86_64.rpm gnutls-utils opensc

# The drop-in PIV plugin. This automatically removes/obsoletes the stock
# remmina-plugins-rdp; no --allowerasing needed.
sudo dnf install ./remmina-plugin-rdp-piv-1.4.43-1.fc44.x86_64.rpm
```

If you had Fedora's stock `remmina-plugins-rdp` installed first, the second
command replaces it. You can confirm the swap:

```console
rpm -q remmina remmina-plugin-rdp-piv
rpm -q remmina-plugins-rdp        # -> "not installed"
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

Confirm it is the AAD/PIV build (the smart-card reason codes are compiled in):

```console
strings /usr/lib64/remmina/plugins/remmina-plugin-rdp.so | grep -m1 'smartcard-auth:'
ldd  /usr/lib64/remmina/plugins/remmina-plugin-rdp.so | grep -E 'freerdp3|webkit2gtk-4.1'
```

You should see `smartcard-auth: ...` and links to `libfreerdp3.so.3` and
`libwebkit2gtk-4.1.so.0`.

## 3. Hardware test — the real flow

Do this at a normal desktop session (not over SSH/headless), with the card
reader attached and the PIV card inserted.

1. **Import the AVD profile.** Launch Remmina, then
   **Menu ▸ Import** (or `remmina -i /path/to/your.rdpw`) and select the real
   `.rdpw` file. It should be accepted and appear in the connection list as a
   normal RDP connection.
   - Equivalent CLI: `remmina -c /path/to/your.rdpw` opens it directly.
2. **Confirm it is listed.** The imported connection shows in the main Remmina
   connection list with its name.
3. **Connect.** Double-click the connection. An embedded WebKit sign-in window
   opens against `login.microsoftonline.us` (Azure US Government).
4. **PIV sign-in.** When the web sign-in asks for a certificate, the plugin
   presents the PIV certificate picker; choose your PIV auth certificate and
   enter the card PIN when prompted. Certificate verification stays on.
5. **Reach the desktop.** After the token exchange and ARM gateway
   orchestration (the plugin allows up to 60 s for the AVD ARM response), the
   remote desktop should appear.
6. **In-session smart card.** If your profile redirects the smart card, confirm
   the card is usable inside the session (e.g. certificate operations in the
   remote OS).

If sign-in shows an empty certificate list, install `gnutls-utils` (provides
`p11tool`) and `opensc`, re-insert the card, and retry.

Privacy: the plugin logs only stable `smartcard-auth: <code>` reason codes,
counts, and the verified sign-in host. It never logs PINs, tokens, PKCS #11
URIs, certificate labels, or `.rdpw` contents. Do not paste real profile
contents or session logs into any report.

## 4. Revert to stock Fedora Remmina

Remove the variant and return to Fedora's shipped Remmina + RDP plugin:

```console
# Remove the PIV plugin and the 1.4.43 base.
sudo dnf remove remmina-plugin-rdp-piv 'remmina*'

# Reinstall Fedora stock (1.4.41-2) with its RDP plugin.
sudo dnf install remmina remmina-plugins-rdp
```

(When a COPR is later used instead of local RPMs, also
`sudo dnf copr disable <owner>/remmina-aad-piv` before reinstalling stock.)

Verify the revert:

```console
rpm -q remmina remmina-plugins-rdp     # both from the 'fedora'/'updates' repo, 1.4.41-2
rpm -q remmina-plugin-rdp-piv          # -> "not installed"
```
