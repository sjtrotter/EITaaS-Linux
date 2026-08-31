# Release integrity and signing

Release publication is intentionally separated from ordinary CI. Pull requests
and manual workflow runs may produce unsigned candidates, but only a `v*` tag
can enter the protected `release` environment and request provenance
attestations.

## Release identity

Create the final annotated tag locally with a configured GPG or SSH signing key:

```bash
git tag -s v0.2.0 <release-commit>
git tag -v v0.2.0
git push origin v0.2.0
```

The release workflow rejects a tag that does not exactly match every project
and native-package version declaration. Do not create a release tag until the
release commit has passed CI and the manual AVD/smart-card matrix.

## Checksums and provenance

The workflow gathers the canonical source archive, Python wheel and sdist,
SBOM, DEB and Debian source package, RPM/SRPM, and Arch package before generating
`SHA256SUMS`. It then
checks the manifest itself. For a tag build, GitHub creates keyless provenance
attestations after the protected environment is approved.

Verify a downloaded artifact's GitHub provenance with:

```bash
gh attestation verify eitaas-linux-0.2.0.tar.gz \
  --repo sjtrotter/EITaaS-Linux
```

An attestation identifies the repository, workflow, commit, and triggering
event that produced an artifact. It does not assert that the software is free
of vulnerabilities.

## Manual checksum signature

For the initial releases, keep the private signing key off GitHub and sign the
checksum manifest on a trusted local system:

```bash
gpg --armor --detach-sign SHA256SUMS
gpg --verify SHA256SUMS.asc SHA256SUMS
sha256sum --check SHA256SUMS
```

Publish `SHA256SUMS.asc` alongside the exact manifest and artifacts downloaded
from the approved tag workflow. Publish the release-key fingerprint through an
independent, stable project channel. Never upload a personal primary private
key or its passphrase to the repository or an Actions artifact.

If automated OpenPGP signing is added later, use a dedicated, expiring release
subkey stored only as protected `release` environment secrets. Require manual
environment approval and retain a documented revocation and rotation process.
