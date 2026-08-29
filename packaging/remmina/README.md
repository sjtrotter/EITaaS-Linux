# Isolated Remmina prototype

This package combines a private Remmina 1.4.43 build with private FreeRDP
3.31.0 libraries under `/usr/libexec/eitaas-remmina`. It does not replace the
distribution packages.

The downstream changes preserve the original protected RDPW profile through
FreeRDP's parser, select ARM/AAD transport, honor smart-card redirection, and
handle WebKitGTK client-certificate and PIN challenges with PKCS #11-backed
CAC credentials. Only authentication, identity, and PIV-labelled certificates
are shown. Core dumps are disabled before opening the authentication view.

Pinned Remmina source:

- commit `030946c83fe1b7218a21b6d32f9c975b243b7031`
- SHA-256 `8976850314dddab8cfe74f413233a712e7ba4b6ccf72b56cbf635b51f1ea2801`

Build conservatively with `RPM_BUILD_NCPUS=1` and `_smp_build_ncpus 1`.
After installation, launch only through:

```console
eitaas-remmina "$HOME/Downloads/Desktop.rdpw"
```

The launcher uses an isolated configuration directory below
`$XDG_STATE_HOME/eitaas-remmina` (or `~/.local/state/eitaas-remmina`) so user
plugins and settings from the distribution Remmina installation are not mixed
with the prototype.
