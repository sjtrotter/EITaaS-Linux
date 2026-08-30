# Shared application API

`eitaas.api.Application` is the presentation-neutral boundary used by the CLI,
GTK frontend, and Qt frontend. Presentation code must not import platform
modules directly, parse CLI output, or construct client arguments.

## Contract

- Every operation returns a typed `Result` containing either a value or an
  `ApplicationError` with a stable code, redacted message, and optional recovery
  guidance.
- Results expose display names instead of full local paths where possible.
- Profile values remain redacted according to the core profile policy.
- Launcher arguments and child-process output are not emitted as progress
  events.
- The application layer never accepts, requests, or returns a CAC PIN.
- `Application.diagnostics` composes a support-safe report from the same typed
  results. It omits full profile paths, child output, and command arguments.

## Launching a connection

`Application.launch(request, on_progress=None, cancel=None)` takes a
`ConnectionRequest(profile)` and returns `Result[ConnectionResult]`
(`exit_code`, `cancelled`). It validates the profile with
`profile.validate_profile` plus the launcher's `.rdpw`-only rule, resolves
`eitaas-remmina` (`/usr/bin/eitaas-remmina`, then `PATH`), and runs
exactly `[launcher, profile]` with no shell, no environment changes, and all
standard streams on `DEVNULL`. Progress phases are `validating`, `starting`
(cancellable), and `cancelling`. The stable error code is `launch_failed`.

The Python layer holds no connection policy. Endpoint allowlisting, the RDPW
native-settings allowlist, clipboard handling, and refusal of the terminal
OAuth fallback are enforced inside the bundled client by the Remmina patches
in `packaging/remmina/`.

`DoctorReport.remmina` (`RemminaBundleSummary`) describes the installed bundle:
launcher on `PATH`, private client binary and its path, pinned Remmina and
FreeRDP versions from the installed `sources.json` (or `"unknown"`), and
whether the FreeRDP client library links SSO-MIB (`None` when no library could
be inspected). `DoctorReport.identity_broker` is unchanged.

## Threading and lifecycle

Calls are synchronous. GUI frontends must run blocking operations on a worker
thread and marshal progress events onto their toolkit event loop. Progress
callbacks execute on the calling worker thread.

`Application.doctor_async` and `Application.smartcard_status_async` return
futures backed by bounded worker threads so GUI callers do not block their
toolkit event loop on PC/SC subprocesses. The synchronous forms remain for the
CLI. `doctor` includes the sanitized smart-card component summary and requires
it to be healthy before reporting overall readiness.

`Application.launch` accepts a `threading.Event`. Setting it terminates the
`eitaas-remmina` child, waits up to five seconds, then kills it if required.
Frontends must set the event during shutdown and wait for their worker to
finish.

The child owns its identity-broker or embedded-WebView authentication
interaction and does not inherit terminal streams. Callback URLs,
authorization codes, and tokens must not reach presentation code, process
arguments, or logs.

## Compatibility

Dataclass fields and stable error codes form the public application contract.
New optional fields may be added in minor releases. Removing or changing fields
requires a major version change.

**Breaking change in the 0.1.0 development line (#69):** `Application.connect`,
`ConnectionRequest.backend`, `ConnectionRequest.clipboard`,
`FreeRDPClientSummary`, `DoctorReport.freerdp`, and the `connection_failed`
error code were removed. Use `Application.launch`, `ConnectionRequest(profile)`,
`DoctorReport.remmina`, and `launch_failed`. No release carried the old
surface, so the package version is unchanged.
