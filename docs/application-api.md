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

## Threading and lifecycle

Calls are synchronous. GUI frontends must run blocking operations on a worker
thread and marshal progress events onto their toolkit event loop. Progress
callbacks execute on the calling worker thread.

`Application.connect` accepts a `threading.Event`. Setting it terminates the
FreeRDP child, waits up to five seconds, then kills it if required. Frontends
must set the event during shutdown and wait for their worker to finish.

The child currently owns its authentication interaction and standard streams.
Future browser/callback integration must validate endpoints in the core and
must never deliver raw callback URLs or tokens to presentation code.

## Compatibility

Dataclass fields and stable error codes form the public application contract.
New optional fields may be added in minor releases. Removing or changing fields
requires a major version change.
