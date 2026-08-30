# Remmina upstream submission candidates

This directory contains a generic, unbranded patch series prepared against
Remmina master commit `c620366ed85def5c3de2549eec7fcbef577281d8`:

1. preserve protected `.rdpw` settings through FreeRDP's native parser;
2. select Azure US Government AVD authentication settings for its public
   `.wvd.azure.us` gateway namespace;
3. consume and validate FreeRDP's configured AVD scope and redirect format;
4. handle WebKitGTK client-certificate and certificate-PIN challenges using
   asynchronous PKCS #11 discovery;
5. retain one immutable RDPW buffer and pass only an explicit AVD
   routing/authentication allowlist to FreeRDP's native parser;
6. compile PKCS #11 support only when the AAD/WebKit feature is enabled;
7. validate, own, and transaction-bind OAuth callbacks with state and PKCE;
8. load the selected PKCS #11 certificate away from the GTK thread and bind
   PIN prompts to a bounded certificate transaction; and
9. replace OAuth polling with synchronized, finite completion whose dialog
   is bound to, and torn down with, the transaction that created it.

The patches deliberately omit EITaaS branding, one-shot lifecycle behavior,
core-dump policy, private runtime paths, and the downstream certificate-label
filter. They contain public cloud constants only. Do not add a real `.rdpw`
file, tenant/workspace/resource identifiers, gateway or host values copied
from a profile, login hints, certificate metadata, tokens, or PINs to an
upstream report or test fixture.

Security hardening is tracked in EITaaS-Linux issues #49–#59. The prepared
branches bind protected-profile content before parsing, restrict OAuth
settings to supported cloud/client combinations, bind CAC challenges to the
verified HTTPS authentication origin, correlate PIN requests, and bound and
cancel PKCS #11 discovery. These controls must remain equivalent in the
GitLab contribution branches. No upstream merge request should be opened
until the corresponding issue has a developer-attested verification comment.
The current reviewed branch heads are `cb56a41f3` for
`contrib/rdpw-govcloud`, `2fde8a23e` for `contrib/avd-settings-auth`, and
`b7c20fa7b` for `contrib/webkit-pkcs11-auth`.

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

Accordingly, the Remmina patches should be described as tested with FreeRDP
3.31.0, while **FreeRDP 3.31.0 or newer is required for complete sovereign-cloud
support when SSO-MIB is enabled**. Browser fallback is not evidence that the
older identity-broker path works. EITaaS bundles 3.31.0 because that exact
Remmina/FreeRDP combination passed GovCloud browser authentication, CAC login,
smart-card redirection, removal/reinsertion, and reconnect testing, and because
pinning the pair avoids distribution ABI and feature differences.

Relevant upstream comparison:
<https://github.com/FreeRDP/FreeRDP/compare/3.30.0...3.31.0>.

## Apply and validate

Apply the series in lexical order to the recorded Remmina commit. A minimal
RDP-plugin build with WebKit AAD support is:

```console
cmake -S . -B build -G Ninja \
  -DWITH_FREERDP3=ON \
  -DWITH_RDP=ON \
  -DWITH_RDP_AUTH_AAD=ON \
  -DWITH_SSO_MIB=OFF
cmake --build build --target remmina-plugin-rdp --parallel 1
```

The prepared series builds with FreeRDP 3.31.0. Hardware validation remains
necessary because CI cannot prove WebKit client-certificate behavior, PIN
entry, or card redirection.

Before submission, rebase each logical change on the latest Remmina master and
follow its contribution process. The four files are review artifacts, not a
claim that Remmina or FreeRDP maintainers have accepted the design.
