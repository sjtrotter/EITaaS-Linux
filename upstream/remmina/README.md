# Remmina upstream submission candidates

This directory contains a generic, unbranded patch series prepared against
Remmina master commit `c620366ed85def5c3de2549eec7fcbef577281d8`. It is one
linear series exported with `git format-patch` from the local GitLab-fork
branch `contrib/eitaas-series-v4` (head `0ab01e608`); each commit is a
complete logical change with no fix-up of an earlier commit:

1. `0001-RDP-preserve-protected-RDPW-settings.patch` (`15f44629c`) reads a
   protected `.rdpw` profile once into a bounded buffer, imports the generic
   fields from that buffer, and passes only an explicit AVD
   routing/authentication allowlist to FreeRDP's native parser before
   connecting;
2. `0002-RDP-select-Azure-US-Government-AVD-authentication.patch`
   (`456f88065`) selects the Azure US Government authority, scope, and
   redirect format for gateways in the public `.wvd.azure.us` namespace;
3. `0003-RDP-honor-configured-AVD-scope-and-redirect-format.patch`
   (`fb4319f8d`) makes the WebKit token path consume FreeRDP's configured AVD
   scope and redirect format after validating the cloud/client combination;
4. `0004-RDP-bind-and-own-OAuth-callback-results.patch` (`7310296d6`)
   replaces the polled, borrowed callback URI with a reference-counted OAuth
   transaction: exact redirect/state validation, PKCE S256, one terminal
   result, a finite wait, and a dialog torn down with its transaction; and
5. `0005-RDP-handle-PKCS11-client-certificates-in-WebKit.patch`
   (`63a378399`) handles WebKitGTK client-certificate and certificate-PIN
   challenges with bounded, cancellable PKCS #11 discovery, asynchronous
   certificate loading, origin-bound PIN transactions, and a held toplevel,
   and logs every stage through `REMMINA_PLUGIN_DEBUG`/`REMMINA_PLUGIN_WARNING`
   with stable `smartcard-auth: <code>` reason codes (counts, the verified
   sign-in host, and codes only; no URIs, labels, PINs, or callback URLs);
   the sources compile only when `WITH_RDP_AUTH_AAD` is enabled; and
6. `0006-RDP-extend-ARM-gateway-response-timeout.patch` (`0ab01e608`)
   applies the profile timeout to `FreeRDP_TcpConnectTimeout` as well as
   `FreeRDP_TcpAckTimeout` (matching FreeRDP's own /timeout option), and
   raises the ARM gateway response wait to 60 seconds when the ARM
   transport is selected and the profile sets no timeout of its own (the
   ARM connection request is not idempotent and is never re-sent), logging
   `avd-arm: response-timeout-ms=60000` at debug level.

The patches deliberately omit EITaaS branding, one-shot lifecycle behavior,
core-dump policy, private runtime paths, and the downstream certificate-label
filter. They contain public cloud constants only. Do not add a real `.rdpw`
file, tenant/workspace/resource identifiers, gateway or host values copied
from a profile, login hints, certificate metadata, tokens, or PINs to an
upstream report or test fixture.

Security hardening is tracked in EITaaS-Linux issues #49–#63. The series
binds protected-profile content before parsing, restricts OAuth settings to
supported cloud/client combinations, binds CAC challenges to the verified
HTTPS authentication origin, correlates PIN requests, and bounds and cancels
PKCS #11 discovery. These controls must remain equivalent to the downstream
queue in `packaging/remmina/`. No upstream merge request should be opened
until the corresponding issue has a developer-attested verification comment.
The earlier three-branch exports (`contrib/rdpw-govcloud`,
`contrib/avd-settings-auth`, `contrib/webkit-pkcs11-auth` and their
`-issue60`/`-issue61` follow-ups) and the `contrib/eitaas-series-v2`/`-v2b`,
`contrib/eitaas-series-v3-logging-main`, `contrib/eitaas-series-v3-logging`,
and `contrib/eitaas-series-v3` branches are superseded by this series:
`contrib/eitaas-series-v4` keeps the five commits of `contrib/eitaas-series-v3`
(`63a378399`, whose logging tree matches `contrib/eitaas-series-v3-logging-main`
`6d75d9fe9` with the commit messages reworded to the SSO-MIB-off /
FreeRDP 3.30 wording of EITaaS-Linux #77/#81) unchanged and adds the ARM
gateway response-timeout commit (EITaaS-Linux #84).

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

The `remmina-upstream-series` job in `.github/workflows/ci.yml` performs
exactly these steps on every pull request. The series is formatted with
Remmina's `.uncrustify-remmina.cfg`; only the changed hunks were formatted, so
untouched upstream lines keep their original style. Hardware validation
remains necessary because CI cannot prove WebKit client-certificate behavior,
PIN entry, or card redirection.

Before submission, rebase the series on the latest Remmina master and follow
its contribution process. The six files are review artifacts, not a claim
that Remmina or FreeRDP maintainers have accepted the design.
