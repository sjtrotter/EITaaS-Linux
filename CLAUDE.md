# CLAUDE.md — EITaaS-Linux

Guidance for AI agents (Claude, Codex, subagents) working in this repository.
Humans own every decision. Issues #49–#64 require AI assistance to be disclosed in any
upstream Remmina/FreeRDP submission; treat that as policy.

## What this repository is

Community Linux tooling for Azure Virtual Desktop (US Government cloud) with CAC
smart-card redirection. One installable deliverable per distribution — the
`eitaas-linux` package (#80) — built from three source trees:

- `src/eitaas/` — stdlib-only Python ≥ 3.10 CLI (`eitaas doctor|inspect-profile|connect|profile|smartcard|certificates`).
  `api.py` is the presentation-neutral facade; frontends never import platform modules directly.
  `connect` only validates the profile and runs `eitaas-remmina PROFILE` (`Application.launch`);
  Python holds no RDP/OAuth policy — that lives in the Remmina patches.
  `profiles.py` is the private profile store (`$XDG_DATA_HOME/eitaas-remmina/profiles/`, names only)
  used by `eitaas profile` and the GUI; `connect` without an argument uses its default.
- `src/eitaas_gui/` — GTK 4/Libadwaita helper `eitaas-gui` ("EITaaS Connect"), shipped in the single
  `eitaas-linux` package; imports `eitaas.api` only. `viewmodel.py` is toolkit-free and tested without GTK.
- `packaging/remmina/` — the bundle inputs for the product client: the pinned manifest, the ordered
  patch series, `eitaas_cac_auth.c` (WebKit CAC / PKCS #11 auth), the `eitaas-remmina` launcher, and the
  notices for the isolated one-shot Remmina 1.4.43 + FreeRDP 3.30.x build.
  `upstream/remmina/` holds the unbranded upstream-candidate exports of the same changes.

Read `README.md`, `docs/adr/*.md`, and `docs/audits/*.md` before changing behavior.
ADR-0002 fixes the product boundary: one-shot `eitaas-remmina PROFILE.rdpw`; no plugin,
no connection-manager mode, no Flatpak/AppImage.

## Non-negotiable security invariants

- Certificate verification stays on. Never add a cert-bypass switch or suggest one.
- Never capture, log, or persist a CAC PIN, OAuth callback, token, or real `.rdpw` content.
  Test fixtures are synthetic (`tests/fixtures/synthetic.rdpw`) — no tenant/workspace/gateway values.
- Refuse FreeRDP's terminal URL/callback OAuth fallback; only the embedded WebView
  (enforced in the Remmina patches, #51/#58; Python never builds FreeRDP arguments).
- Python profiles: regular file, owned by the user, mode `0600`, ≤ 1 MiB, checked via `lstat`
  (`profile.validate_profile`; the subsequent read-by-path is a known small TOCTOU gap — do not widen it).
- C profiles (Remmina patches): `O_NOFOLLOW` + `fstat`, ≤ 1 MiB, one immutable buffer parsed once pre-connect.
- Errors cross the API boundary through `redaction.redact` (JWTs, `key=value` secrets, URL query values);
  API results expose basenames, never full profile paths; raw child output is never returned — `launch`
  writes it redacted line-by-line to the private session log (`remmina.SessionLog`, 0700/0600, capped,
  rotated) and only that redacted log is served back (`Application.session_log`).
- Child processes: fixed argv, no shell, timeouts, bounded output, stdio to `DEVNULL` unless required
  (the `eitaas-remmina` child's stdout/stderr go to the session log; stdin stays `DEVNULL`).
- Remmina smart-card logging (`eitaas_cac_auth.c` / `rdp_web_auth_pkcs11.c`): stable `smartcard-auth: <code>`
  reason codes, counts, and the verified sign-in host only — never PKCS #11 URIs, labels, serials, PINs, tokens.
- Untrusted `.rdpw` content reaches FreeRDP's native parser only through the explicit allowlist
  (`packaging/remmina/0005/0006-*.patch`, `upstream/remmina/0001-*.patch`).
- OAuth: `state` + PKCE S256, exact callback scheme/host/port/path, one terminal result per transaction
  (`packaging/remmina/0006-*.patch`, `upstream/remmina/0004-*.patch`; remaining gaps tracked in #60).
- No polkit/pcsc-lite overrides, no automatic trust-store changes, no `sudo` in diagnostics.

## Engineering standards

**Single source of truth (SSOT).**
- Version pins, patch order, and downstream sources live in `packaging/remmina/sources.json`; it is the
  intended SSOT for the Remmina bundle (aligning CI/spec/script strings to it is tracked in #64).
  `scripts/check-version-consistency.py` guards the single package version (pyproject.toml) across
  RPM/DEB/Arch, the man pages, and the AppStream metainfo; the pinned Remmina/FreeRDP versions never
  become part of it.
  Never add a new hard-coded version string a manifest already holds.
- Cloud constants (authorities, scopes, hosts) are defined once per language and referenced.
- The downstream patch queue and the upstream series must implement the *same* behavior; a fix
  applied to one must be applied to the other in the same PR.
- Documentation states what code does; do not describe controls that are not implemented.

**Clean code.**
- Small, single-purpose functions; explicit ownership of every pointer/handle in C (who frees, on which thread).
- No duplicated decoders/validators — factor and reuse (e.g. one BOM/UTF-16 RDPW decoder).
- No dead code, no commented-out code, no "fix-up of my own earlier commit" left in a series bound upstream.
- Fail closed: every validation failure produces exactly one terminal result and releases resources.
- Prefer stdlib; no new Python runtime dependencies without an ADR.

**Tests.** `PYTHONPATH=src python -m unittest discover -s tests`. Add behavioral tests, not string-grep
tests, when the property can be exercised (parsing, redaction, selection, patch application, builds).
Every PR keeps the suite green and CI green (`.github/workflows/ci.yml`).

## Remmina / FreeRDP upstream conventions

Code destined for `upstream/remmina/` or the GitLab `contrib/*` branches follows Remmina's style:
- Format with `.uncrustify-remmina.cfg` from a Remmina checkout (not vendored here; tabs, 8-column indent,
  `type *name` pointer spacing, function-definition brace on its own line, `if (x) {` on one line).
- GLib/GTK idioms: `g_*` allocators paired with `g_free`, WinPR/FreeRDP allocations with `free`;
  GTK calls on the main thread only; `g_object_ref` anything used across a nested main loop.
- Commit subjects use the component prefix (`RDP: ...`), imperative mood, with a body explaining why.
- No EITaaS branding, private paths, core-dump policy, or product-specific lifecycle in upstream patches.
- Describe FreeRDP >= 3.16 as *required* (`GatewayAvdScope`/`GatewayAvdAccessAadFormat` APIs) and the
  pinned 3.30.x line as *tested*; make no SSO-MIB claims (the bundle builds `WITH_SSO_MIB=OFF`).
- Regenerate patch files with `git format-patch` from real commits; never hand-edit a diff.
- Verify the series applies onto the pinned base with `git am` and builds `remmina-plugin-rdp`
  with `WITH_RDP_AUTH_AAD=ON` and `OFF` (CI job `remmina-upstream-series`; base and branch head are
  recorded in `upstream/remmina/README.md`). Keep it one linear, squashed series.

## Workflow

1. Work from a GitHub issue with acceptance criteria; file one if none exists.
2. Branch per issue, one PR per issue, PR body references the issue and lists verification commands run.
3. Every PR receives an independent adversarial review before merge; findings are fixed on the same PR.
4. Gate issues #49–#64 (security/reliability/upstream/packaging) close only after: equivalent downstream + upstream change,
   behavioral tests, sanitizer run where applicable, developer attestation, and hardware validation
   where the criteria require it. Never tick a checkbox on behalf of the developer.
5. You may push branches to the GitLab fork; never open GitLab merge requests — the owner does. Report SHAs.
6. Orchestrate non-trivial work: the lead agent plans and delegates well-bounded tasks to the
   appropriate tier of subagent **and to Codex harnesses** (`codex exec`, `codex exec review`) —
   Codex for independent implementation/review passes and second opinions; Claude subagents for
   worktree-isolated fixes and fresh-context adversarial review. Trivial edits need no delegation.
   Subagents may delegate further. Every delegated change still lands as a reviewed PR.
7. Do not commit `.build/`, `dist/`, real profiles, keys, captures, or agent state
   (`.claude/`, `.codex/`, `.agents/`, `AGENTS.local.md`, `CLAUDE.local.md`) — see `.gitignore`.

## Useful paths

- Pinned Remmina source for downstream work: `Remmina-030946c8…` (see `sources.json`); build recipe in
  `packaging/rpm/eitaas-linux.spec` / `packaging/debian/rules` / `packaging/arch/PKGBUILD` (#80: one
  binary package `eitaas-linux` per distribution contains the bundle, the CLI, and the GUI).
- Combined package builds: `scripts/build-rpm.sh`, `build-deb.sh`, `build-arch.sh`; corresponding source is
  assembled by `scripts/prepare-bundle-source.py`; lifecycle checks are `scripts/test-{deb,rpm,arch}-lifecycle.sh`.
- Local build trees may exist under `.build/` (ignored, machine-local); if present, `.build/remmina-poc/prefix`
  holds an installed FreeRDP for plugin builds (check its version against `sources.json`).
- Support matrix and gates: `docs/supported-platforms.md`. Release: `docs/release-checklist.md`.
