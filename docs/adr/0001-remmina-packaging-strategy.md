# ADR 0001: Deliver the enhanced Remmina client as native packages

- Status: accepted
- Date: 2026-08-30
- Tracks: issue #35

## Context

The working client is a downstream Remmina build linked to a pinned private
FreeRDP build. It needs host PC/SC services and sockets, PKCS #11 middleware,
WebKitGTK, graphics libraries, the desktop session, and hardware access. Those
interfaces are not made portable merely by placing a Fedora binary in a
self-mounting archive.

The Python `eitaas-linux` helper packages and the enhanced `eitaas-remmina`
client are separate deliverables. A distribution is not supported for the
enhanced client just because its helper package builds there.

## Decision

Native RPM, DEB, and Arch `PKGBUILD` outputs are the baseline delivery model.
Each native recipe will:

1. build the same pinned Remmina and FreeRDP sources from
   `packaging/remmina/sources.json`;
2. apply the patches in the manifest's declared order;
3. install into a private prefix so distribution Remmina and FreeRDP packages
   are not replaced;
4. use host PC/SC, PKCS #11, WebKitGTK, GTK, graphics, and desktop libraries;
5. publish the binary package with its native source package, license notices,
   checksums, an artifact SBOM, and build provenance; and
6. remain a prototype until its automated and hardware gates pass on that
   exact distribution release and architecture.

The initial architecture boundary is `x86_64`. `aarch64` and other
architectures remain unsupported until they have native builders and CAC/AVD
hardware results. Support is release-specific: passing on one Fedora, Ubuntu,
Debian, or Arch snapshot does not imply support for another.

### Product boundary

EITaaS is distributed only as distribution-native packages containing the
setup/diagnostic wrapper and the isolated one-shot Remmina/FreeRDP pair. A
connection always starts with `eitaas-remmina PROFILE.rdpw`; an enhanced
connection manager, replacement or side-by-side Remmina plugin, AppImage,
Flatpak, and independent RDP client are intentionally outside scope.

## Support boundary

| Target | Architecture | Enhanced client status | Boundary |
| --- | --- | --- | --- |
| Fedora 44 | x86_64 | Working prototype | RPM tested with GNOME Wayland through XWayland, Azure Government CAC login, passthrough, removal/reinsertion, disconnect, and reconnect; display performance remains tracked in #29 and #36. |
| Ubuntu 24.04 LTS | x86_64 | Candidate | Native DEB must build and pass every gate; no support claim yet. |
| Debian 13 | x86_64 | Candidate | Native DEB must build and pass every gate; no support claim yet. |
| Arch Linux rolling | x86_64 | Candidate snapshot | Record repository snapshot/date, build a native package, and pass every gate; results do not automatically carry to later snapshots. |
| Ubuntu 22.04 LTS | x86_64 | Unsupported | Distribution dependency path provides FreeRDP 2; it is not a native enhanced-client target. |
| Any target | aarch64 or other | Unsupported | Requires a native builder and complete hardware validation. |

Candidate versions are implementation targets, not compatibility claims. A
target moves to supported only after its exact package artifact completes the
matrix and the result is recorded in release evidence. Support ends when the
distribution release is end-of-life or can no longer receive security fixes
for required host components.

## CI and runtime matrix

`A` means an automated gate. `H` means a manual hardware/AVD gate. Every cell
is required for a support claim unless marked not applicable.

| Gate | Fedora RPM | Ubuntu DEB | Debian DEB | Arch package |
| --- | --- | --- | --- | --- |
| Manifest pins and SHA-256 verification | A | A | A | A |
| Reproducible source/recipe inputs | A | A | A | A |
| Clean build on declared baseline | A | A | A | A |
| Install, upgrade, remove | A | A | A | A |
| Private-prefix and dependency audit | A | A | A | A |
| License and corresponding-source contents | A | A | A | A |
| Artifact SBOM and provenance | A | A | A | A |
| `eitaas doctor` and isolated launcher smoke test | A | A | A | A |
| Azure Government initial CAC authentication | H | H | H | H |
| Smart-card passthrough inside AVD | H | H | H | H |
| Card removal/reinsertion | H | H | H | H |
| Disconnect/reconnect | H | H | H | H |
| Cancel during certificate discovery | H | H | H | H |
| GNOME/KDE X11 and Wayland/XWayland rendering | H | H | H | H |
| Multimonitor, scaling, input alignment, and responsiveness | H | H | H | H |
| Host middleware/socket compatibility | H | H | H | H |

Hardware evidence must not contain real profiles, identities, certificate
details, PINs, OAuth callbacks, or tokens. Failures remain failures; certificate
validation, sandboxing, or smart-card access controls must not be disabled to
make a matrix cell pass.

## Release consequences

- The current Fedora RPM is downloadable proof of concept, not evidence that
  Ubuntu, Debian, or Arch is supported.
- DEB (#40) and PKGBUILD (#41) recipes for the enhanced client are required
  before those native targets can enter hardware validation.
- Release automation must generate an SBOM for the actual enhanced-client
  artifact, not only for the Python build environment.
- The binary and corresponding source package must be published together for
  every supported artifact.
- Performance work (#36), display correctness (#29), upstream contributions
  (#33), and release/SBOM hardening (#10) remain independent gates and are not
  hidden by the packaging decision.

### Note (2026-08-30, #69)

The direct-FreeRDP launcher that predated this decision (`eitaas connect
--backend`, `packaging/freerdp-webview/`) has been removed; the last tree
containing it is tagged `archive/freerdp-webview`. `eitaas connect` now only
validates the profile and runs `eitaas-remmina`. Display-performance follow-up
for the bundled client is tracked in #36 (display correctness remains #29).
