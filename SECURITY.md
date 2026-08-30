# Security policy

## Reporting a vulnerability

Do not open a public issue containing credentials, OAuth callback URLs,
smart-card data, `.rdp`/`.rdpw` contents, tenant or host-pool identifiers, packet captures,
or operational details about government systems.

Use GitHub private vulnerability reporting for this repository. If that option
is unavailable, contact the maintainer privately through their GitHub profile
without attaching sensitive material to the initial message.

## Security boundaries

EITaaS-Linux is an unprivileged wrapper and diagnostic tool. It does not make a
multi-user Linux desktop safe against malicious software running as the same
user. Any process with access to the user's PC/SC session may be able to ask an
inserted smart card to perform operations; the card PIN and card policy remain
important controls.

The project does not disable TLS or RDP certificate verification by default,
does not collect PINs, and does not install trust anchors or polkit rules during
ordinary installation.
