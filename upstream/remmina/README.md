# Remmina upstream submission candidates

This directory contains a generic, unbranded patch series prepared against
Remmina master commit `c620366ed85def5c3de2549eec7fcbef577281d8`. It is one
linear series exported with `git format-patch` from the local GitLab-fork
branch `contrib/eitaas-series-v5` (head `2f5e58e5b`); each commit is a
complete logical change with no fix-up of an earlier commit:

1. `0001-RDP-preserve-protected-RDPW-settings.patch` (`e8c8dd2d4`) reads a
   protected `.rdpw` profile once into a bounded buffer, imports the generic
   fields from that buffer, and passes only an explicit AVD
   routing/authentication allowlist to FreeRDP's native parser before
   connecting. Reading, decoding, classifying, and filtering live in the
   GLib-only `plugins/rdp/rdp_rdpw.c`, so the importer and the connection
   path share one decoder. A file that selects the ARM resource provider but
   names no gateway host is refused at import; a build without
   `WITH_RDP_AUTH_AAD` refuses to connect an AVD profile with an explicit
   error; and the shared MIME type gains the `*.rdpw`/`*.RDPW` globs, which
   is all the file association needs because both desktop entries already
   declare `application/x-remmina`;
2. `0002-RDP-select-Azure-US-Government-AVD-authentication.patch`
   (`0eade1961`) collects the public authority, scope, and redirect format of
   every supported cloud in one table (`plugins/rdp/rdp_avd_cloud.h`) and
   selects the Azure US Government row for gateways in the public
   `.wvd.azure.us` namespace, leaving an authority that is not FreeRDP's
   default untouched;
3. `0003-RDP-honor-configured-AVD-scope-and-redirect-format.patch`
   (`c2e35ea36`) makes the WebKit token path consume FreeRDP's configured AVD
   scope and redirect format after validating them against that same table;
4. `0004-RDP-bind-and-own-OAuth-callback-results.patch` (`38822ac92`)
   replaces the polled, borrowed callback URI with a reference-counted OAuth
   transaction: exact redirect/state validation, PKCE S256, one terminal
   result, a finite wait, and a dialog torn down with its transaction, and
   lists `rdp_web_auth.c` in `po/POTFILES.in`;
5. `0005-RDP-handle-PKCS11-client-certificates-in-WebKit.patch`
   (`50a52599b`) handles WebKitGTK client-certificate and certificate-PIN
   challenges with bounded, cancellable PKCS #11 discovery, asynchronous
   certificate loading, origin-bound PIN transactions, and a held toplevel,
   and logs every stage through `REMMINA_PLUGIN_DEBUG`/`REMMINA_PLUGIN_WARNING`
   with stable `smartcard-auth: <code>` reason codes (counts, the verified
   sign-in host, and codes only; no URIs, labels, PINs, or callback URLs);
   the sources compile only when `WITH_RDP_AUTH_AAD` is enabled, every string
   they show is translatable, and `p11tool` is resolved with
   `g_find_program_in_path()` (override: `-DREMMINA_P11TOOL=/path/to/p11tool`);
6. `0006-RDP-extend-ARM-gateway-response-timeout.patch` (`69e04b6ac`)
   applies the profile timeout to `FreeRDP_TcpConnectTimeout` as well as
   `FreeRDP_TcpAckTimeout` (matching FreeRDP's own /timeout option), and
   raises the ARM gateway response wait to 60 seconds when the ARM
   transport is selected and the profile sets no timeout of its own (the
   ARM connection request is not idempotent and is never re-sent), logging
   `avd-arm: response-timeout-ms=60000` at debug level; and
7. `0007-RDP-test-the-protected-connection-file-helpers.patch` (`2f5e58e5b`)
   adds a CTest target for the RDPW helpers — bounds and file-type checks,
   the refusal to follow a symbolic link, UTF-8/UTF-16 decoding, the ARM
   classification, and the allowlist — against a synthetic fixture, opt-in
   through `-DBUILD_TESTING=ON`.

The patches deliberately omit EITaaS branding, one-shot lifecycle behavior,
core-dump policy, private runtime paths, and the downstream certificate-label
filter. They contain public cloud constants only. Do not add a real `.rdpw`
file, tenant/workspace/resource identifiers, gateway or host values copied
from a profile, login hints, certificate metadata, tokens, or PINs to an
upstream report or test fixture.

Security hardening is tracked in EITaaS-Linux issues #49–#63. The series
binds protected-profile content before parsing, restricts OAuth settings to
supported cloud/client combinations, binds smart-card challenges to the
verified HTTPS authentication origin, correlates PIN requests, and bounds and
cancels PKCS #11 discovery. Untrusted profile content never reaches `g_error()`:
every rejection is a plugin error the user sees, not an abort. These controls
must remain equivalent to the downstream queue in `packaging/remmina/`. No
upstream merge request should be opened until the corresponding issue has a
developer-attested verification comment.
The earlier three-branch exports (`contrib/rdpw-govcloud`,
`contrib/avd-settings-auth`, `contrib/webkit-pkcs11-auth` and their
`-issue60`/`-issue61` follow-ups) and the `contrib/eitaas-series-v2`/`-v2b`,
`contrib/eitaas-series-v3-logging-main`, `contrib/eitaas-series-v3-logging`,
`contrib/eitaas-series-v3`, and `contrib/eitaas-series-v4` branches are
superseded by this series: `contrib/eitaas-series-v5` keeps the six commits of
`contrib/eitaas-series-v4` (head `0ab01e608`) in the same order, amends them
with the gaps found by the EITaaS-Linux #79 gap review (file association,
`p11tool` lookup, non-AAD builds, ARM validation, translation, one constants
table), and adds the helper test as a seventh commit.

## FreeRDP compatibility

The series requires FreeRDP 3.16.0 or newer and is tested with FreeRDP 3.30.0
(the version EITaaS pins in `packaging/remmina/sources.json`). The binding
symbols are `FreeRDP_GatewayAvdScope` and `FreeRDP_GatewayAvdAccessAadFormat`,
both added in FreeRDP 3.16.0 (commit `6168a7bf`);
`FreeRDP_GatewayAzureActiveDirectory` and `FreeRDP_GatewayAvdUseTenantid` need
3.10.0, and everything else the series uses predates FreeRDP 3.0. Each commit
body states the same tested version and floor. The series makes no claim about FreeRDP's SSO-MIB identity-broker
path: EITaaS builds with `WITH_SSO_MIB=OFF` and validates only the WebKit
browser path, so do not present browser results as evidence for the broker
route or vice versa.

## Runtime dependencies

Smart-card sign-in lists the card's certificates with GnuTLS' `p11tool`,
found in `PATH` when a card is read: package `gnutls-bin` on Debian and
derivatives, `gnutls-utils` on Fedora and SUSE. It is a runtime dependency of
that path only — the plugin builds and every other connection works without
it, and a build that must pin an absolute path can pass
`-DREMMINA_P11TOOL=/path/to/p11tool`. When no `p11tool` is present, the
certificate dialog names the package instead of showing an empty list. The
PKCS #11 module for the card itself (`opensc-pkcs11`, registered with
p11-kit) is the other runtime dependency.

## Apply and validate

Apply the series with `git am` onto the recorded base commit; the patches
apply in file-name order and do not apply to Remmina 1.4.43 (that release is
served by the downstream queue instead):

```console
git clone https://gitlab.com/Remmina/Remmina.git
cd Remmina
git checkout c620366ed85def5c3de2549eec7fcbef577281d8
git am /path/to/EITaaS-Linux/upstream/remmina/*.patch
```

A minimal RDP-plugin build against an installed FreeRDP 3.30.0, once with
WebKit AAD support and once without it, is:

```console
for aad in ON OFF; do
  cmake -S . -B build-$aad -G Ninja \
    -DCMAKE_PREFIX_PATH=/path/to/freerdp-3.30.0 \
    -DWITH_FREERDP3=ON \
    -DWITH_RDP=ON \
    -DWITH_RDP_AUTH_AAD=$aad \
    -DWITH_SSO_MIB=OFF
  cmake --build build-$aad --target remmina-plugin-rdp
done
```

The helper test that commit 7 adds is opt-in and needs neither FreeRDP nor a
display:

```console
cmake -S . -B build-test -G Ninja -DBUILD_TESTING=ON
cmake --build build-test --target test-rdp-rdpw
ctest --test-dir build-test
```

The `remmina-upstream-series` job in `.github/workflows/ci.yml` performs
exactly these steps on every pull request. The series is formatted with
Remmina's `.uncrustify-remmina.cfg`; only the changed hunks were formatted, so
untouched upstream lines keep their original style. Hardware validation
remains necessary because CI cannot prove WebKit client-certificate behavior,
PIN entry, or card redirection.

Before submission, rebase the series on the latest Remmina master and follow
its contribution process. The seven files are review artifacts, not a claim
that Remmina or FreeRDP maintainers have accepted the design.
