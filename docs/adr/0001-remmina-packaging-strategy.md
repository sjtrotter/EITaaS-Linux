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

### Portable formats

AppImage is a secondary experiment, not the primary release format. An
evaluation must be built on the oldest selected glibc baseline, must not bundle
or replace the host PC/SC daemon or PKCS #11 middleware, and must record:

- compressed and unpacked size;
- glibc and graphics compatibility on every target host;
- WebKitGTK authentication behavior;
- discovery of host OpenSC/vendor modules and the PC/SC socket; and
- the complete native matrix below.

An AppImage built from the Fedora artifact is explicitly not a supported
portable deliverable.

Flatpak is deferred. Before it can become a candidate, a documented design
must demonstrate least-privilege access to the PC/SC socket, required devices,
host PKCS #11 middleware, WebKit authentication, and desktop integration. A
broad filesystem or device escape is not an acceptable substitute. Until that
design and the hardware matrix pass, no Flatpak is published as supported.

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

| Gate | Fedora RPM | Ubuntu DEB | Debian DEB | Arch package | AppImage evaluation | Flatpak evaluation |
| --- | --- | --- | --- | --- | --- | --- |
| Manifest pins and SHA-256 verification | A | A | A | A | A | A |
| Reproducible source/recipe inputs | A | A | A | A | A | A |
| Clean build on declared baseline | A | A | A | A | A | A |
| Install, upgrade, remove | A | A | A | A | A | A |
| Private-prefix and dependency audit | A | A | A | A | A | A |
| License and corresponding-source contents | A | A | A | A | A | A |
| Artifact SBOM and provenance | A | A | A | A | A | A |
| `eitaas doctor` and isolated launcher smoke test | A | A | A | A | A | A |
| Azure Government initial CAC authentication | H | H | H | H | H | H |
| Smart-card passthrough inside AVD | H | H | H | H | H | H |
| Card removal/reinsertion | H | H | H | H | H | H |
| Disconnect/reconnect | H | H | H | H | H | H |
| Cancel during certificate discovery | H | H | H | H | H | H |
| GNOME/KDE X11 and Wayland/XWayland rendering | H | H | H | H | H | H |
| Multimonitor, scaling, input alignment, and responsiveness | H | H | H | H | H | H |
| Host middleware/socket compatibility | H | H | H | H | H | H |

Hardware evidence must not contain real profiles, identities, certificate
details, PINs, OAuth callbacks, or tokens. Failures remain failures; certificate
validation, sandboxing, or smart-card access controls must not be disabled to
make a matrix cell pass.

## Release consequences

- The current Fedora RPM is downloadable proof of concept, not evidence that
  Ubuntu, Debian, Arch, AppImage, or Flatpak is supported.
- DEB (#40) and PKGBUILD (#41) recipes for the enhanced client are required
  before those native targets can enter hardware validation.
- AppImage feasibility is tracked in #42; Flatpak confinement feasibility is
  tracked in #43. Neither format is currently supported.
- Release automation must generate an SBOM for the actual enhanced-client
  artifact, not only for the Python build environment.
- The binary and corresponding source package must be published together for
  every supported artifact.
- Performance work (#36), display correctness (#29), plugin/upstream design
  (#33), launch modes (#38), and release/SBOM hardening (#10) remain independent
  gates and are not hidden by the packaging decision.
