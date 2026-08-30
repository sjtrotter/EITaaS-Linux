# Remmina upstream patch security review

- Status: blocking findings confirmed
- Review date: 2026-08-30
- Reviewer: independent Codex adversarial review, subsequently re-vetted against source and API contracts
- Remmina base: `c620366ed85def5c3de2549eec7fcbef577281d8`
- RDPW branch: `8ae503d120f04133363f68f68ffdc666382cf932`
- AVD settings branch: `2fde8a23e77c09f02e7a03b4e715e739f1f62dab`
- WebKit/PKCS #11 branch: `46f3d67a349b371b8aaedad81f4ebd945801ff40`

## Purpose and standard of evidence

This audit records a separate adversarial review of the proposed Remmina
changes. Each reported defect was re-checked against the pinned implementation,
the FreeRDP 3.31.0 source used by EITaaS, or the relevant documented API
ownership/protocol contract. The report distinguishes confirmed defects from
design limitations and unverified concerns. It does not infer exploitability
from a code smell alone.

The current patch series is not ready for upstream submission. The Government
Cloud settings allowlist itself held up under review, but the RDPW and WebKit
series contain confirmed defects, and the existing Remmina OAuth flow contains
two defects directly exercised by the proposed integration.

## Confirmed findings in the proposed changes

### SR-01: native RDPW parsing expands untrusted profile authority

**Severity:** high. **Disposition:** block the RDPW submission.

`rdp_plugin.c` passes the entire user-selected `.rdpw` buffer to
`freerdp_client_settings_parse_connection_file_buffer()`. The preceding SHA-256
comparison checks consistency only; it neither verifies the RDPW signature nor
establishes a trusted publisher.

FreeRDP 3.31.0's parser demonstrably recognizes and applies
`drivestoredirect`, `devicestoredirect`, `usbdevicestoredirect`,
`camerastoredirect`, `redirectlocation`, and `redirectwebauthn`. Depending on
compiled channels, those fields enable local-resource redirection. Builds made
with `WITH_EMBEDDED_CLI_IN_RDP_FILES` also parse lines beginning with `/` as
FreeRDP command-line options. Remmina's prior field-by-field importer did not
give all of these settings authority over the live connection.

The confirmed defect is the policy expansion without validation or consent,
not that every profile is malicious or every channel is present in every
build. Remediation must parse only an explicit set of AVD routing and
authentication fields, preserve Remmina/local-user redirection policy, and
reject embedded CLI input. If signature trust is desired, the signed scope and
signature must be cryptographically verified before it is used as a trust
decision.

### SR-02: RDPW validation does not bind the generic import

**Severity:** high. **Disposition:** block the RDPW submission.

`remmina_rdp_file_import()` performs three independent pathname opens:

1. a bounded, no-follow read used to compute the accepted digest;
2. `g_io_channel_new_file()` for the generic Remmina import; and
3. another bounded, no-follow read used to compare the digest.

The second open is not made from either protected buffer. In a directory an
attacker can modify, the pathname can identify file A for reads one and three
but file B for the generic import. The digest comparison can therefore pass
while generic fields came from B. The second open also lacks the first reader's
regular-file and size checks, so a substituted FIFO can block and a large file
can consume excessive resources. This follows directly from the independent
opens; it does not depend on a probabilistic memory-lifetime assumption.

All import and connection consumers must use one retained immutable buffer.
The generic importer should accept that buffer rather than reopen the pathname.

### SR-03: the PKCS #11 source breaks non-AAD builds

**Severity:** build blocker, not a security vulnerability. **Disposition:**
block the WebKit/PKCS #11 submission.

`rdp_web_auth_pkcs11.c` and its header are included unconditionally in
`REMMINA_PLUGIN_RDP_SRCS`, while WebKit include directories and libraries are
added only when the AAD feature checks succeed. A build with
`WITH_RDP_AUTH_AAD=OFF` was reproduced failing at the WebKit header include.
The sources must be added only inside the enabled feature block, with the
appropriate dependency/version checks.

### SR-04: rejected initial authentication URI leaves the worker waiting

**Severity:** medium availability defect. **Disposition:** block the
WebKit/PKCS #11 submission.

When the new initial-URI validation rejects a URI, the UI callback destroys the
dialog and returns without storing `AUTH_CANCELLED`. Both token workers poll
`token-uri` without an overall timeout and therefore continue indefinitely.
This is a deterministic control-flow defect. The rejection path must signal a
terminal result; the polling design should subsequently be replaced by bounded,
cancellable synchronization.

### SR-05: the discovery timeout does not cover certificate loading

**Severity:** medium reliability/availability defect. **Disposition:** track in
the proposed PKCS #11 work.

The 15-second timeout bounds the `p11tool` subprocess used for enumeration.
After selection, `g_tls_certificate_new_from_pkcs11_uris()` runs synchronously
on the GTK thread. A slow or broken provider can therefore still freeze the UI,
which matches the original observed symptom class. This is not classified as a
privilege escalation: an installed PKCS #11 provider is native same-user code.
The product must either document that module trust boundary and move loading
off the UI thread, or use an out-of-process broker if hostile providers are in
scope.

### SR-06: PIN authorization state is not bound to one certificate transaction

**Severity:** low security/UI-integrity defect. **Disposition:** track in the
proposed PKCS #11 work.

The WebView stores only `rdp-certificate-host`. It carries no transaction
generation or selected-certificate identity. Two overlapping same-host flows
cannot be distinguished, and the marker is cleared after the first PIN prompt,
so a legitimate retry is rejected. Standalone and off-host PIN prompts are
correctly rejected. Remediation is a serialized, expiring per-WebView state
machine bound to the selected certificate/key and authentication request.

## Confirmed inherited Remmina findings

These findings are present in the reviewed Remmina base rather than introduced
by the proposed commits. They are relevant because the proposed sovereign-cloud
and CAC support directly uses this flow.

### SR-07: OAuth authorization response is not transaction-bound or callback-validated

**Severity:** high protocol-integrity defect. **Disposition:** prepare a
separate upstream prerequisite/fix.

The authorization request contains neither `state` nor PKCE. The policy callback
accepts the first navigation classified by WebKit as a redirect, without
checking that its scheme, host, port, and path equal the redirect URI registered
for the transaction. RFC 9700 requires OAuth clients to prevent CSRF and
requires public clients to use PKCE. The exact established consequence here is
failure to bind the received authorization response to the initiated browser
transaction; this audit does not claim demonstrated token theft.

The implementation must generate transaction-specific PKCE and CSRF binding,
validate the exact callback destination, and reject error/malformed/duplicate
responses. Federated identity navigation must remain possible before the final
callback, so a blanket Microsoft-only navigation allowlist is not proposed.

### SR-08: OAuth callback URI is stored beyond its documented lifetime

**Severity:** high memory-safety/correctness defect. **Disposition:** prepare a
separate upstream prerequisite/fix.

`webkit_uri_request_get_uri()` returns a `const gchar *` owned by the
`WebKitURIRequest`. `SET_TOKEN_URI` stores that pointer with
`g_object_set_data()`, which does not copy or own the pointed-to bytes. The
policy callback then destroys the dialog, returns, and the worker reads and
parses the stored pointer later. No reference to the request or copy of its URI
is retained for that later read.

This is a confirmed violation of the documented ownership lifetime and creates
a dangling-pointer read path. The audit does not claim that arbitrary code
execution has been reproduced. Store an owned copy with
`g_object_set_data_full(..., g_strdup(uri), g_free)` or, preferably, pass an
owned result through a synchronized transaction object.

## Validated controls

- The protected reader uses `O_NOFOLLOW`, `fstat`, a regular-file requirement,
  a 1 MiB limit, `O_CLOEXEC`, and EINTR-aware reads.
- The AVD settings patch uses exact supported commercial and US Government
  constants and constrains tenant syntax and redirect format.
- PKCS #11 enumeration uses a fixed argv vector without a shell, bounded output
  and counts, cancellable subprocess I/O, a timeout, and one active discovery.
- Client-certificate challenges reject proxy, insecure, missing, and mismatched
  origins before enumeration.
- Standalone/off-origin PIN requests fail closed, WebKit credential persistence
  is disabled, and the visible entry is cleared after use.

## Claims not promoted to security issues

- **Unrestricted intermediate WebView navigation:** federated authentication
  legitimately crosses origins. The security requirement is an exact final
  callback and transaction binding, not a simplistic host-only navigation
  policy.
- **Hostile PKCS #11 module as privilege escalation:** loading an installed
  module already executes same-user native code. Synchronous loading is tracked
  as an availability boundary, not elevated privilege.
- **Guaranteed PIN erasure:** clearing the GTK entry is useful but cannot prove
  secure erasure of toolkit, WebKit, TLS, or provider copies.
- **Certificate/private-key cryptographic mismatch:** the code derives a key
  selector from token attributes, but this review did not establish a mismatch
  exploit. It remains a test requirement, not a confirmed vulnerability.
- **FreeRDP 2 and non-Linux compile failures:** static compatibility concerns
  were observed but not reproduced, so they are not reported as confirmed
  defects here.

## Verification performed

- Inspected exact diffs and source at all commit IDs listed above.
- Traced all three RDPW pathname opens and the later native buffer parser.
- Verified the sensitive RDP fields and their settings/channel effects in the
  pinned FreeRDP 3.31.0 `client/common/file.c`.
- Reproduced the AAD-disabled build failure; AAD-enabled builds had passed.
- Verified WebKit URI transfer ownership and GLib data-association semantics
  against their official API documentation.
- Compared the OAuth request/response handling with RFC 9700 requirements.
- Ran `git diff --check` across the proposed series; it passed.

Existing source-string packaging tests do not exercise file replacement,
callback ownership, OAuth transaction binding, asynchronous cancellation, or
optional build matrices. Resolution issues must add behavioral tests for those
properties before developer attestation.

## Remediation status

The following candidate repairs were implemented after the review. They are
not a substitute for the required re-review and hardware validation:

- `contrib/rdpw-govcloud` `cb56a41f3` retains one bounded RDPW buffer, imports
  generic fields from that buffer, rejects embedded CLI lines, and sends only
  an explicit AVD routing/authentication allowlist to the native parser.
- `contrib/webkit-pkcs11-auth` `46aa744f3` gates WebKit/PKCS #11 sources on the
  enabled AAD feature; both enabled and disabled builds pass locally.
- `a25a3c2d7` adds exact callback/state validation, owned callback storage, and
  PKCE S256; `b7c20fa7b` replaces polling with a mutex/condition transaction and
  a finite wait.
- `2c2442d7b` moves selected-certificate loading to a worker while leaving the
  GTK loop responsive, adds a bounded loading dialog, and replaces host-only
  PIN state with a serialized, expiring certificate transaction.
- The downstream Remmina 1.4.43 patch queue and `eitaas_cac_auth.c` contain the
  equivalent changes and compile against the pinned FreeRDP 3.31.0 baseline.

Residual gates are behavioral OAuth tests, sanitizer coverage, a fresh
adversarial review, and CAC hardware validation. Findings remain open until
those gates are attested.

## References

- [WebKitGTK `URIRequest.get_uri` ownership](https://webkitgtk.org/reference/webkit2gtk/stable/method.URIRequest.get_uri.html)
- [GLib `g_object_set_data`](https://docs.gtk.org/gobject/method.Object.set_data.html)
- [OAuth 2.0 Security Best Current Practice, RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html)
- [FreeRDP 3.31.0 RDP file parser](https://github.com/FreeRDP/FreeRDP/blob/3.31.0/client/common/file.c)
- [Reviewed Remmina Web authentication source](https://gitlab.com/Remmina/Remmina/-/blob/c620366ed85def5c3de2549eec7fcbef577281d8/plugins/rdp/rdp_web_auth.c)
