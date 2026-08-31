# Support policy

EITaaS-Linux is community-supported software and is not an official Microsoft
or United States Government client. Azure Virtual Desktop, Microsoft identity
flows, distribution packages, and FreeRDP behavior can change independently.

Supported combinations are those exercised by the current CI matrix and the
manual release checklist. The per-artifact gate table — what is built and
linted automatically, and what has passed smart-card/AVD hardware validation —
is in [`docs/supported-platforms.md`](docs/supported-platforms.md). A
successful diagnostic check does not guarantee that an organization permits a
particular client or redirection feature.

Before filing a public issue, run `eitaas doctor` and remove any identifying or
operational data. For a failed connection, EITaaS Connect's **Copy diagnostic
log** button provides the redacted session log; the same file is under
`$XDG_STATE_HOME/eitaas-remmina/logs/` and `eitaas doctor --json` names the
newest one as `latest_session_log`. Redaction is best effort — read a log
before attaching it. Never post a real connection profile or authentication
URL.
