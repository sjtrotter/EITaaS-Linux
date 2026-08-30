# Remmina upstream submission candidates

This directory contains a generic, unbranded patch series prepared against
Remmina master commit `c620366ed85def5c3de2549eec7fcbef577281d8`. It is one
linear series exported with `git format-patch` from the local GitLab-fork
branch `contrib/eitaas-series-v3-logging-main` (head `6d75d9fe9`); each commit is a
complete logical change with no fix-up of an earlier commit:

1. `0001-RDP-preserve-protected-RDPW-settings.patch` (`fb4db9ea7`) reads a
   protected `.rdpw` profile once into a bounded buffer, imports the generic
   fields from that buffer, and passes only an explicit AVD
   routing/authentication allowlist to FreeRDP's native parser before
   connecting;
2. `0002-RDP-select-Azure-US-Government-AVD-authentication.patch`
   (`3b4eb7823`) selects the Azure US Government authority, scope, and
   redirect format for gateways in the public `.wvd.azure.us` namespace;
3. `0003-RDP-honor-configured-AVD-scope-and-redirect-format.patch`
   (`8010014ef`) makes the WebKit token path consume FreeRDP's configured AVD
   scope and redirect format after validating the cloud/client combination;
4. `0004-RDP-bind-and-own-OAuth-callback-results.patch` (`cb7cb20f2`)
   replaces the polled, borrowed callback URI with a reference-counted OAuth
   transaction: exact redirect/state validation, PKCE S256, one terminal
   result, a finite wait, and a dialog torn down with its transaction; and
5. `0005-RDP-handle-PKCS11-client-certificates-in-WebKit.patch`
   (`6d75d9fe9`) handles WebKitGTK client-certificate and certificate-PIN
   challenges with bounded, cancellable PKCS #11 discovery, asynchronous
   certificate loading, origin-bound PIN transactions, and a held toplevel,
   and logs every stage through `REMMINA_PLUGIN_DEBUG`/`REMMINA_PLUGIN_WARNING`
   with stable `smartcard-auth: <code>` reason codes (counts, the verified
   sign-in host, and codes only; no URIs, labels, PINs, or callback URLs);
   the sources compile only when `WITH_RDP_AUTH_AAD` is enabled.

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
`-issue60`/`-issue61` follow-ups) and the `contrib/eitaas-series-v2`/`-v2b`
branches are superseded by this series. The same logging commit rebased onto
the SSO-MIB-off / FreeRDP 3.30-wording series of `contrib/eitaas-series-v2b`
(EITaaS-Linux #81) is pushed as `contrib/eitaas-series-v3-logging` (head
`383b1e56e`, identical plugin tree); whichever of the two lands second is
re-exported from the other.

## FreeRDP compatibility

FreeRDP 3.31.0 is the EITaaS tested and pinned version, but it is important not
to overstate the requirement in an upstream proposal:

- the `.rdpw`, AVD-setting, WebKit, and PKCS #11 changes use FreeRDP APIs that
  are already present in 3.30.0;
- FreeRDP 3.30.0's SSO-MIB path creates its public client with the fixed
  commercial `common` authority;
- FreeRDP 3.31.0 instead builds the SSO-MIB authority from
  `FreeRDP_GatewayAzureActiveDirectory` and the selected tenant. That change
  is required for the identity-broker path to honor a sovereign authority such
  as `login.microsoftonline.us`.

Accordingly, each commit describes itself as tested with FreeRDP 3.31.0,
while **FreeRDP 3.31.0 or newer is required for complete sovereign-cloud
support when SSO-MIB is enabled**. Browser fallback is not evidence that the
older identity-broker path works. EITaaS bundles 3.31.0 because that exact
Remmina/FreeRDP combination passed GovCloud browser authentication, CAC login,
smart-card redirection, removal/reinsertion, and reconnect testing, and because
pinning the pair avoids distribution ABI and feature differences.

Relevant upstream comparison:
<https://github.com/FreeRDP/FreeRDP/compare/3.30.0...3.31.0>.

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

A minimal RDP-plugin build against an installed FreeRDP 3.31.0, once with
WebKit AAD support and once without it, is:

```console
for aad in ON OFF; do
  cmake -S . -B build-$aad -G Ninja \
    -DCMAKE_PREFIX_PATH=/path/to/freerdp-3.31.0 \
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
its contribution process. The five files are review artifacts, not a claim
that Remmina or FreeRDP maintainers have accepted the design.
