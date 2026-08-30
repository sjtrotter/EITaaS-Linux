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

Do not build a separate EITaaS Remmina protocol plugin now. It would need to
copy or link against private implementation details from `plugins/rdp`, then
track the full RDP plugin ABI and lifecycle. That is a disguised fork with a
less reliable integration boundary.

Instead, reduce the downstream build through small generic Remmina changes:

1. make the RDP file importer preserve all settings needed by FreeRDP's native
   protected `.rdpw` parser;
2. make the AAD WebKit flow consume the AVD scope and redirect format already
   held in `rdpSettings`; and
3. add generic asynchronous PKCS #11 client-certificate and PIN handling to
   the embedded WebKit flow.

After those capabilities are upstream, EITaaS should be a launcher, isolated
configuration, packaging policy, and optional file/entry integration—not a
second RDP implementation. A thin plugin may then be reconsidered for manager
integration, but it must use public APIs only and remain optional.

## Patch disposition

| Current change | Disposition | Reason |
| --- | --- | --- |
| Accept `redirectsmartcards`, map `enablerdsaadauth`, and preserve protected `.rdpw` data | Upstream Remmina | These are generic Microsoft RDP/AVD profile semantics. The upstream implementation should avoid an `eitaas_*` field name and should test both singular and plural smart-card keys. |
| Select Azure Government authority, scope, redirect format, and tenant behavior from the protected profile/endpoint | Upstream Remmina where generic; downstream policy only as a temporary fallback | FreeRDP already models these settings. Remmina should consume parsed values instead of embedding either commercial or government constants. EITaaS-specific endpoint inference should disappear once parsing is sufficient. |
| Consume `FreeRDP_GatewayAvdScope` and `FreeRDP_GatewayAvdAccessAadFormat` in `rdp_web_auth.c` | Upstream Remmina | This fixes a generic mismatch between Remmina and the FreeRDP settings contract. Validate null/format inputs before formatting a URI. |
| Handle WebKit client-certificate and certificate-PIN challenges with asynchronous PKCS #11 discovery | Upstream Remmina | WebKit exposes these generic authentication schemes and explicitly supports asynchronous handling by retaining the request. Certificate filtering should be configurable or show all usable client-auth certificates; DoD label policy is not appropriate upstream. |
| Filter labels to PIV/authentication/identity certificates | Downstream policy until replaced by certificate-purpose inspection | It is EITaaS usability policy and label matching is heuristic. Do not propose the heuristic as a general Remmina rule. |
| Disable core dumps/process dumpability | Downstream launcher or documented hardening | This affects the entire Remmina process and should not be hidden inside an authentication callback. |
| Quit the application after one-shot cancellation | Downstream launcher/mode integration | This is EITaaS lifecycle policy tracked by #38, not generic WebKit behavior. |
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

- The enhanced native packages remain the working prototype until the required
  upstream changes are released and validated.
- We continue carrying four downstream patches for now, but new EITaaS policy
  must not be added to Remmina's RDP internals without first evaluating a
  generic upstream form.
- A standalone plugin is not a near-term packaging simplification.
- Once upstream support lands, packaging can prefer distribution Remmina and
  FreeRDP versions that contain it; the private bundled pair remains necessary
  for older distributions and reproducible prototype artifacts.

## Primary references

- [Remmina plugin API at the reviewed master commit](https://gitlab.com/Remmina/Remmina/-/blob/c620366ed85def5c3de2549eec7fcbef577281d8/src/include/remmina/plugin.h)
- [Remmina RDP Web authentication at the reviewed master commit](https://gitlab.com/Remmina/Remmina/-/blob/c620366ed85def5c3de2549eec7fcbef577281d8/plugins/rdp/rdp_web_auth.c)
- [Remmina RDP file importer at the reviewed master commit](https://gitlab.com/Remmina/Remmina/-/blob/c620366ed85def5c3de2549eec7fcbef577281d8/plugins/rdp/rdp_file.c)
- [Remmina plugin-development documentation](https://gitlab.com/Remmina/Remmina/-/wikis/Development/Plugin-Development)
- [FreeRDP 3.31.0 settings keys](https://github.com/FreeRDP/FreeRDP/blob/3.31.0/include/freerdp/settings_keys.h)
- [WebKitGTK authentication request API](https://webkitgtk.org/reference/webkit2gtk/stable/class.AuthenticationRequest.html)
- [Remmina contribution guide](https://gitlab.com/Remmina/Remmina/-/blob/master/CONTRIBUTING.md)
