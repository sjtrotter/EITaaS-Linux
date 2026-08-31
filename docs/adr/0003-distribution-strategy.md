# ADR 0003: Distribution strategy — upstream contribution plus a community-repo AAD/PIV build

- Status: accepted
- Date: 2026-08-31
- Tracks: issue #33 (upstream), ADR-0001 (packaging), ADR-0002 (extension boundary)
- FreeRDP survey: issue #77 (comment, 2026-08-30)

## Context

The product's user story is: import an Azure Virtual Desktop `.rdpw`, have it appear
as a normal Remmina connection, click it, sign in through the embedded web view with a
smart card (PIV) certificate and PIN, and reach the desktop. The question this ADR
settles is **how that reaches users**, given that most of the machinery already exists
in the ecosystem.

### What each layer already owns

- **FreeRDP** (the RDP engine) owns the protocol, the AVD gateway / ARM transport, the
  Entra/AAD token exchange, and **smart-card redirection into the session** (using the
  card after connecting). None of this is ours.
- **Remmina** (the GUI over FreeRDP) owns the connection list / config area, saving
  profiles, click-to-open, and the embedded WebKit sign-in window shell. The
  connection-manager experience the user wants is Remmina core.
- **Our patches** are a small addition inside Remmina's RDP plugin. Only three things
  are genuinely novel:
  1. importing a signed AVD `.rdpw` as a first-class Remmina profile;
  2. selecting the Azure US Government authority/scope/redirect from the profile; and
  3. **the PIV certificate picker and PIN entry during the Entra web sign-in** — the one
     piece missing from both FreeRDP and stock Remmina, because certificate-based web
     sign-in needs a PKCS #11 client-certificate handler in the sign-in window.

Everything else in the flow is FreeRDP + Remmina that already exists.

### Why upstreaming alone does not deliver the feature

The code path lives inside Remmina's own `WITH_RDP_AUTH_AAD` option, which is **default
OFF** and, when enabled, makes **WebKit2GTK and libsoup hard dependencies** of
`remmina-plugin-rdp` — a package everyone with RDP installs. Distributions decline to
pull a browser engine into their base RDP plugin for a feature most users do not need.
This is structural, not an oversight.

Measured state (2026-08-31):

- **Fedora 44** ships `remmina-plugin-rdp` with **AAD OFF** — verified locally: the
  installed `.so` has no WebKit/libsoup linkage and no AAD code.
- **Arch** almost certainly OFF: WebKit2GTK is present only for the WWW plugin, and
  `libsoup` (also required by the AAD block) is not a dependency at all.
- **Debian/Ubuntu** show no evidence of ON; AAD is still an open upstream request
  (Remmina issues #1793, #2960).
- **`remmina-next`** (the Remmina team's PPA and Hubbitus's COPR) ships *newer* Remmina
  with the *same* build options — AAD still OFF; the Ubuntu PPA even still pairs with
  FreeRDP 2, which cannot do AVD/AAD at all.
- **Flatpak** cannot do smart-card passthrough in its sandbox (Flathub Remmina issue
  #97), so it is a dead end for this feature (consistent with ADR-0001 rejecting it).

Therefore **no distribution channel available today delivers this flow**, and merging
the patches upstream would not change that on stock distros, because their Remmina is
built AAD-off.

### FreeRDP version floor

The patches use FreeRDP settings added in **3.16.0** (`GatewayAvdScope`,
`GatewayAvdAccessAadFormat`). Distro FreeRDP meets that on Fedora, Ubuntu 26.04, and
Arch; **Debian 13 (3.15) and Ubuntu 24.04 (3.5) do not** (issue #77 survey).

## Decision

Pursue two tracks.

### Track 1 — Contribute the patches to Remmina upstream (long game)

Submit the generic series (`upstream/remmina/`, GitLab `contrib/eitaas-series-v5`) to
the Remmina project. Value: it ends fork drift, gets the code reviewed and blessed, and
lets any packager enable the feature with a build flag instead of a patch. It is **not**
a distribution solution — acceptance is uncertain (expect pushback on `gtk_dialog_run`,
the `p11tool` subprocess, and base64 `rdpw_data` storage), and even once merged the
feature stays default-off in distro builds. Do not gate distribution on it.

### Track 2 — Distribute an AAD/PIV-enabled build through a community repository

This is how the feature actually reaches users, and it mirrors how `remmina-next` and
ungoogled-chromium already ship (a well-established, accepted model): a COPR (Fedora),
an AUR PKGBUILD (Arch), and a PPA/OBS (Debian/Ubuntu), consumed the same way as
`copr enable hubbitus/remmina-next`.

The packaged artifact is shaped to the target, not one-size-fits-all:

- **Where distro FreeRDP is >= 3.16** (Fedora, Ubuntu 26.04, Arch): prefer a lean
  **variant RDP plugin** — a drop-in `remmina-plugin-rdp` built with AAD + the PIV
  patches, linked against the distro FreeRDP, that `Conflicts`/`Provides`/`Replaces`
  the stock plugin. The user installs stock Remmina plus this one plugin — no duplicate
  GTK/Remmina/FreeRDP. (This is a packaging-level swap of the `.so`, not a Remmina
  plugin-API extension, which ADR-0002 established is not possible.)
- **Where distro FreeRDP is too old** (Debian 13, Ubuntu 24.04): fall back to the
  existing **private-prefix bundle** (`eitaas-remmina`) that vendors Remmina + FreeRDP,
  as today.

The current single `eitaas-linux` bundle (ADR-0001) remains correct as the portable
fallback and the reference build; the variant plugin is the lighter, more idiomatic
form to add where it is feasible.

## Consequences

- Shipping our own build is not an anomaly — it is the only way this flow reaches anyone
  today, and it matches ecosystem precedent.
- Adds packaging surface: a variant `remmina-plugin-rdp-piv` recipe per supported
  distro, plus community-repo hosting (COPR/AUR/PPA), on top of the bundle.
- Requires ABI/version tracking against each distro's Remmina and FreeRDP for the
  variant plugin; the bundle avoids that at the cost of size.
- The upstream track must still land the pre-MR cleanups (issue #96: license headers,
  README) before merge requests are opened; no MR before developer-attested
  verification and hardware validation, per `upstream/remmina/README.md`.

## Follow-ups

- Prototype `remmina-plugin-rdp-piv` on Fedora against stock Remmina and validate the
  drop-in replacement end to end (tracked as a new research issue).
- Stand up a COPR (and later AUR/PPA) for the AAD/PIV build.
- Open the Remmina merge requests once #96 and the attestation/hardware gates clear.
