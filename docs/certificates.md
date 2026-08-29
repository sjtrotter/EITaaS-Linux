# Certificate handling

Certificate trust is an explicit administrative decision. EITaaS-Linux never
downloads certificates during package installation and does not automatically
trust every certificate in a bundle.

`eitaas certificates fetch` accepts only an official `cyber.mil` HTTPS URL and
requires an expected SHA-256 digest obtained through an independent trusted
channel. `eitaas certificates inspect` prints the bundle digest, subjects,
issuers, fingerprints, and whether each certificate appears self-signed.

Inspection does not prove that a certificate is authorized or safe to trust.
Self-signed roots, intermediates, OS trust stores, Firefox/NSS databases, and
revocation checking require distinct handling. Installation commands are
intentionally deferred until an authoritative update and rollback design is
validated.

Obtain the expected digest through an independently authenticated channel; a
digest displayed beside a download on the same compromised page does not add
meaningful protection.
