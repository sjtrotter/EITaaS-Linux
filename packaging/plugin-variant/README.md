# packaging/plugin-variant — Fedora COPR variant (issue #101, ADR-0003 Track 2)

Two additive RPM recipes that ship the AAD/PIV RDP support as a **drop-in
plugin** on top of stock-style Remmina, instead of the private-prefix bundle
(`packaging/remmina/`, ADR-0002). This is the lighter form ADR-0003 prescribes
where the distribution's FreeRDP is already >= 3.16 (Fedora 44 ships 3.30.0).

| File | Builds | Notes |
| --- | --- | --- |
| `remmina.spec` | `remmina` 1.4.43 (+ subpackages) | Fedora's `remmina-1.4.41-2.fc44` spec with **only** the source bumped to the pinned 1.4.43 snapshot `030946c8` from `packaging/remmina/sources.json`. Vanilla — no EITaaS patches. The clean, ABI-defining base. |
| `remmina-plugin-rdp-piv.spec` | `remmina-plugin-rdp-piv` | The EITaaS downstream RDP series applied to the *same* source, built `WITH_RDP_AUTH_AAD=ON WITH_SSO_MIB=OFF`. Ships only the patched `remmina-plugin-rdp.so`; `Provides`/`Obsoletes`/`Conflicts remmina-plugins-rdp` for a clean swap. |

Both are built from the identical Remmina source, which is what makes the plugin
ABI-matched to the base `remmina`. The plugin links the distribution's FreeRDP 3
and WebKit2GTK 4.1; it does not vendor either.

## Why the pinned snapshot and not the `v1.4.43` tag

`git describe 030946c8` = `v1.4.43-142-g030946c83`. The RDP AAD web-auth code
the plugin extends (`plugins/rdp/rdp_web_auth.c`) does not exist at the bare
`v1.4.43` tag (`7be0cf2`); it landed on master afterwards and is present in this
snapshot. The downstream series therefore applies cleanly to `030946c8` with **no
rebase** (it was authored against it) and cannot apply to the bare tag. See
`sources.json` and the PR description.

## Sources the plugin spec consumes

- `Source0`: the pinned Remmina snapshot tarball (sha256 in `sources.json`).
- `Source1/2`: `eitaas_smartcard_auth.c` / `.h` from `packaging/remmina/`
  (compiled into the plugin by patch `0002`, which `#include`s the `.c`).
- `Source3`: `THIRD_PARTY_NOTICES.md` from `packaging/remmina/`.
- `Patch0..6`: the seven `packaging/remmina/00NN-*.patch` files, verbatim.

The patch series and smart-card sources are **shared** with the bundle in
`packaging/remmina/`; per CLAUDE.md's SSOT rule a change to one must be applied
to the other (and to `upstream/remmina/`) in the same PR. This directory adds
no second copy of them.

## Local build (containerized; see docs/plugin-variant-testing.md for host use)

```console
# in a fedora:44 container with the RPM tools + build deps installed:
rpmbuild -bb packaging/plugin-variant/remmina.spec
RPM_BUILD_NCPUS=1 rpmbuild -bb packaging/plugin-variant/remmina-plugin-rdp-piv.spec
```

The plugin spec's `%check` greps the built `.so` for `libfreerdp3.so.3`,
`libwebkit2gtk-4.1`, and the `smartcard-auth:` reason codes.

## Not yet done (ADR-0003 follow-ups)

- Stand up the COPR that hosts these two packages.
- AUR / PPA equivalents for Arch and Ubuntu 26.04.
