# ADR 0002: Upstream Remmina integration before an EITaaS plugin

- Status: accepted
- Date: 2026-08-30
- Tracks: issue #33
- Upstream reviewed: Remmina `c620366ed85def5c3de2549eec7fcbef577281d8`

## Context

The working client applies four patches to Remmina 1.4.43. We would prefer a
small EITaaS extension over maintaining a downstream Remmina build, but that is
only useful if the extension can reuse Remmina's existing RDP implementation.

This review compared our pinned source with current Remmina master and the
public plugin API. Remmina plugins register complete protocol, file, entry,
tool, preference, secret, or language-wrapper implementations. A protocol
plugin owns its connection lifecycle. The plugin service does not provide a
supported way to:

- find and decorate the registered `RDP` protocol plugin;
- modify its `freerdp` settings after the native `.rdpw` parser runs;
- observe or replace its embedded AAD WebKit view; or
- handle WebKit authentication challenges on that view.

A file plugin can recognize and import `.rdpw` files, but the resulting
`RemminaFile` contains Remmina profile fields, not the live `rdpSettings`
instance owned by the RDP plugin. An entry plugin can start another command,
but cannot embed or delegate a connection to the existing RDP plugin.

These limits remain present in current master. Its RDP Web authentication code
also still supplies a commercial-cloud scope and constructs the redirect URI
locally rather than consuming the corresponding FreeRDP settings.

## Decision

EITaaS-Linux is the setup/diagnostic wrapper plus an isolated, one-shot Remmina
1.4.43 client linked to the pinned private FreeRDP 3.31.0 libraries. It opens a
user-supplied protected GovCloud `.rdpw` profile directly and exits when that
connection or its authentication flow ends. It does not replace, decorate, or
extend the distribution Remmina installation.

Do not build or distribute a separately named EITaaS protocol plugin, a
replacement system RDP plugin, or an independent FreeRDP frontend. Those are
outside the selected product boundary.

Instead, reduce the downstream build through small generic Remmina changes:

1. make the RDP file importer preserve all settings needed by FreeRDP's native
   protected `.rdpw` parser;
2. make the AAD WebKit flow consume the AVD scope and redirect format already
   held in `rdpSettings`; and
3. add generic asynchronous PKCS #11 client-certificate and PIN handling to
   the embedded WebKit flow.

These generic changes will be offered to Remmina upstream so native Remmina can
eventually support GovCloud profiles and CAC/PIN authentication. Upstream work
does not change the EITaaS delivery model: released EITaaS artifacts continue
to pin, build, and test the complete one-shot pair selected by their manifest.

## Adversarial review of delivery options

The private enhanced client is both the selected EITaaS product and the
reference artifact. Native upstream Remmina support is a contribution to the
broader community, not a prerequisite for or alternate EITaaS distribution.

| Option | Strongest argument for it | Failure mode that controls the decision | Verdict |
| --- | --- | --- | --- |
| Patch Remmina's built-in RDP plugin and build a private client | Reuses Remmina's complete, proven RDP integration while pinning the tested Remmina/FreeRDP pair | We must rebuild promptly for security updates and carry a larger artifact | Selected product architecture |
| Replace a distro's separately packaged RDP plugin with an exact-version patched build | Small download and native Remmina UI | Couples EITaaS to every distro Remmina ABI and package transaction; unavailable as the same model on Arch | Reject as outside product scope |
| Install a renamed `EITAAS-RDP` beside the native RDP plugin | Does not remove the native plugin and can claim a distinct protocol | Copies roughly 9,800 lines, duplicates file handlers, and loads both RDP implementations and their FreeRDP dependencies into one process | Reject |
| Ship one portable plugin binary with private FreeRDP libraries | Appears to minimize packaging and insulate the plugin from distro versions | ELF libraries with the same FreeRDP SONAME share a process namespace; load order can silently select the wrong implementation despite RUNPATH | Reject |
| Reimplement RDP directly on libfreerdp | Maximum control and no Remmina RDP source dependency | Recreates rendering, input, scaling, channels, reconnection, clipboard, audio, and monitor integration; becomes a new RDP client | Reject unless the product intentionally leaves Remmina |
| Wait for upstream and distribute no EITaaS client | Zero downstream maintenance | Leaves current users without a controlled, tested solution for an unbounded review/release/distro cycle | Reject |

The existing RDP plugin is not a small authentication adapter: the reviewed
source is approximately 9,800 lines before generated code and links directly
to `libfreerdp-client`, `libfreerdp`, and `libwinpr`. Remmina loads native
plugins with `GModule` and passes a service structure of function pointers; the
API has no ABI version field or capability negotiation. These facts make exact
package coupling a safety requirement, not merely conservative packaging.

The suite must make its composition visible: `eitaas` owns setup, diagnostics,
profile inspection, and support information; `eitaas-remmina PROFILE.rdpw`
owns the one-shot connection. The private Remmina and FreeRDP versions, patch
set, licenses, corresponding source, and security-update status are release
metadata rather than hidden implementation details.

## Patch disposition

| Current change | Disposition | Reason |
| --- | --- | --- |
| Accept `redirectsmartcards`, map `enablerdsaadauth`, and preserve protected `.rdpw` data | Upstream Remmina | These are generic Microsoft RDP/AVD profile semantics. The upstream implementation should avoid an `eitaas_*` field name and should test both singular and plural smart-card keys. |
| Select Azure Government authority, scope, redirect format, and tenant behavior from the protected profile/endpoint | Upstream Remmina where generic; downstream policy only as a temporary fallback | FreeRDP already models these settings. Remmina should consume parsed values instead of embedding either commercial or government constants. EITaaS-specific endpoint inference should disappear once parsing is sufficient. |
| Consume `FreeRDP_GatewayAvdScope` and `FreeRDP_GatewayAvdAccessAadFormat` in `rdp_web_auth.c` | Upstream Remmina | This fixes a generic mismatch between Remmina and the FreeRDP settings contract. Validate null/format inputs before formatting a URI. |
| Handle WebKit client-certificate and certificate-PIN challenges with asynchronous PKCS #11 discovery | Upstream Remmina | WebKit exposes these generic authentication schemes and explicitly supports asynchronous handling by retaining the request. Certificate filtering should be configurable or show all usable client-auth certificates; DoD label policy is not appropriate upstream. |
| Filter labels to PIV/authentication/identity certificates | Downstream policy until replaced by certificate-purpose inspection | It is EITaaS usability policy and label matching is heuristic. Do not propose the heuristic as a general Remmina rule. |
| Disable core dumps/process dumpability | Downstream launcher or documented hardening | This affects the entire Remmina process and should not be hidden inside an authentication callback. |
| Quit the application after one-shot cancellation | Downstream launcher integration | This is permanent EITaaS one-shot lifecycle policy, not generic WebKit behavior. |
| Private-prefix RPATH | Downstream packaging | It exists only to isolate the bundled Remmina/FreeRDP pair. |

## Proposed upstream sequence

Keep each proposal independently reviewable and avoid EITaaS branding in
generic code:

1. **RDPW import correctness.** Add fixtures covering protected AVD fields,
   `redirectsmartcard(s)`, and `enablerdsaadauth`; preserve a source reference
   or parsed settings through a neutral API. Do not include cloud hardcoding.
2. **Settings-driven AAD Web authentication.** Replace the hardcoded scope and
   locally constructed redirect format with validated FreeRDP setting values,
   retaining safe defaults for ordinary profiles. Include commercial and US
   Government unit cases.
3. **Generic WebKit client-certificate authentication.** Add async discovery,
   cancellation, certificate selection, PIN prompting, secret clearing, and
   no credential persistence. Keep PKCS #11 enumeration behind a small helper
   boundary so it can later use a native library rather than spawning
   `p11tool`.
4. **Optional extension hooks only if needed.** If maintainers do not want the
   certificate UI in the RDP plugin, first propose a narrowly typed Web-auth
   provider interface. Do not expose `rdpSettings` wholesale or depend on
   private RDP plugin symbols.

Before opening merge requests, rebase each change onto current master, follow
Remmina's contribution process, add automated tests where its test harness
allows, and reference a sanitized reproducer. CAC hardware, identities,
certificate data, PINs, tokens, and protected production profiles must never be
attached.

## Consequences

- The enhanced native packages are the EITaaS delivery model; support remains
  release- and hardware-matrix-specific.
- We continue carrying four downstream patches for now, but new EITaaS policy
  must not be added to Remmina's RDP internals without first evaluating a
  generic upstream form.
- Plugin-only, manager-mode, and independent-client variants are not roadmap
  items.
- When changes land upstream, the downstream patch queue should shrink, but an
  EITaaS release still selects and validates its complete bundled pair.

## Primary references

- [Remmina plugin API at the reviewed master commit](https://gitlab.com/Remmina/Remmina/-/blob/c620366ed85def5c3de2549eec7fcbef577281d8/src/include/remmina/plugin.h)
- [Remmina RDP Web authentication at the reviewed master commit](https://gitlab.com/Remmina/Remmina/-/blob/c620366ed85def5c3de2549eec7fcbef577281d8/plugins/rdp/rdp_web_auth.c)
- [Remmina RDP file importer at the reviewed master commit](https://gitlab.com/Remmina/Remmina/-/blob/c620366ed85def5c3de2549eec7fcbef577281d8/plugins/rdp/rdp_file.c)
- [Remmina plugin-development documentation](https://gitlab.com/Remmina/Remmina/-/wikis/Development/Plugin-Development)
- [FreeRDP 3.31.0 settings keys](https://github.com/FreeRDP/FreeRDP/blob/3.31.0/include/freerdp/settings_keys.h)
- [WebKitGTK authentication request API](https://webkitgtk.org/reference/webkit2gtk/stable/class.AuthenticationRequest.html)
- [Remmina contribution guide](https://gitlab.com/Remmina/Remmina/-/blob/master/CONTRIBUTING.md)
- [Fedora `remmina-plugins-rdp` package](https://packages.fedoraproject.org/pkgs/remmina/remmina-plugins-rdp/)
- [Fedora `remmina-devel` package](https://packages.fedoraproject.org/pkgs/remmina/remmina-devel/)
- [Ubuntu 24.04 `remmina-plugin-rdp` package](https://packages.ubuntu.com/noble/remmina-plugin-rdp)
- [Debian 13 `remmina-dev` package](https://packages.debian.org/trixie/remmina-dev)
- [Arch Linux Remmina package contents](https://archlinux.org/packages/extra/x86_64/remmina/files/)
