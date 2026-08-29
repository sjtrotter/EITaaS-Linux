# Shared application API

`eitaas.api.Application` is the presentation-neutral boundary used by the CLI,
GTK frontend, and Qt frontend. Presentation code must not import platform
modules directly, parse CLI output, or construct FreeRDP arguments.

## Contract

- Every operation returns a typed `Result` containing either a value or an
  `ApplicationError` with a stable code, redacted message, and optional recovery
  guidance.
- Results expose display names instead of full local paths where possible.
- Profile values remain redacted according to the core profile policy.
- Connection arguments and child-process output are not emitted as progress
  events.
- The application layer never accepts, requests, or returns a CAC PIN.
- `Application.diagnostics` composes a support-safe report from the same typed
  results. It omits full profile paths, child output, and command arguments.

## Threading and lifecycle

Calls are synchronous. GUI frontends must run blocking operations on a worker
thread and marshal progress events onto their toolkit event loop. Progress
callbacks execute on the calling worker thread.

`Application.doctor_async` and `Application.smartcard_status_async` return
futures backed by bounded worker threads so GUI callers do not block their
toolkit event loop on PC/SC subprocesses. The synchronous forms remain for the
CLI. `doctor` includes the sanitized smart-card component summary and requires
it to be healthy before reporting overall readiness.

`Application.connect` accepts a `threading.Event`. Setting it terminates the
FreeRDP child, waits up to five seconds, then kills it if required. Frontends
must set the event during shutdown and wait for their worker to finish.

`ConnectionRequest.single_monitor` appends reviewed FreeRDP display overrides
after the protected profile. It disables fullscreen, multimonitor, spanning,
while retaining the profile's resolution and scaling behavior.

The child owns its identity-broker or embedded-WebView authentication
interaction and does not inherit terminal streams. The core refuses clients
that would use FreeRDP's terminal URL/callback fallback. Callback URLs,
authorization codes, and tokens must not reach presentation code, process
arguments, or logs.

## Compatibility

Dataclass fields and stable error codes form the public application contract.
New optional fields may be added in minor releases. Removing or changing fields
requires a major version change.
